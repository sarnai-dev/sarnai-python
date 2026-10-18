import json
import re
from pathlib import Path

import httpx
import pytest

from sarnai import (DescriptionNotAcceptedError, EndpointNotAcceptedError, SarnAIClient,
                    SarnAIError, _tools)

PROBLEMS = [
    {"field": "description", "code": "validation_error",
     "problem": "description is empty", "fix": "Say what the service does, in 1-2000 characters."},
    {"field": "endpoint_url", "code": "validation_error",
     "problem": "endpoint_url must be https://", "fix": "Use an https:// address."},
]


def board_422(problems=PROBLEMS, **extra):
    body = {"ok": False, "tool": "register_me", "error_code": "invalid_listing",
            "message": "The listing is not valid as given.",
            "detail": problems, "fix": "Apply every fix in errors and call again.",
            "result": {"valid": False, "errors": problems, "arguments": {"name": "x"}},
            "next_actions": [{"method": "MCP_TOOL", "path": "register_me",
                              "description": "Call again with the fixes applied."}]}
    body.update(extra)
    return body


def client_with(body, status=422):
    return SarnAIClient(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


def register(client):
    return client.register_me("x", "", "http://nope")


def test_errors_carry_every_problem_with_field_code_problem_fix():
    with pytest.raises(SarnAIError) as info:
        register(client_with(board_422()))
    err = info.value
    assert [(e["field"], e["code"], e["problem"], e["fix"]) for e in err.errors] == [
        (p["field"], p["code"], p["problem"], p["fix"]) for p in PROBLEMS]
    assert err.fix == "Apply every fix in errors and call again."
    assert err.next_actions and err.code == "invalid_listing" and err.status == 422
    # The message names every problem, not only the first.
    assert "description is empty" in str(err) and "endpoint_url must be https://" in str(err)


def test_errors_fall_back_to_detail_list():
    body = board_422()
    del body["result"]
    with pytest.raises(SarnAIError) as info:
        register(client_with(body))
    assert len(info.value.errors) == 2


def test_errors_empty_for_plain_errors():
    with pytest.raises(SarnAIError) as info:
        register(client_with({"error_code": "not_found", "message": "no", "detail": "no"}, 404))
    assert info.value.errors == [] and info.value.fix is None


@pytest.mark.parametrize("nested,cls", [
    ("endpoint_not_accepted", EndpointNotAcceptedError),
    ("description_not_accepted", DescriptionNotAcceptedError),
])
def test_nested_codes_raise_typed_errors(nested, cls):
    problems = [{"field": "endpoint_url", "code": nested, "problem": "refused",
                 "fix": "Use a public https host.", "reason": "localhost"}]
    with pytest.raises(cls) as info:
        register(client_with(board_422(problems)))
    err = info.value
    assert isinstance(err, SarnAIError) and err.code == "invalid_listing"
    assert nested in err.codes and err.errors[0]["fix"] == "Use a public https host."
    assert err.errors[0]["reason"] == "localhost"


def test_unrelated_nested_code_stays_plain():
    with pytest.raises(SarnAIError) as info:
        register(client_with(board_422()))
    assert type(info.value) is SarnAIError


def test_tool_output_includes_errors_fix_next_actions():
    out = json.loads(_tools.register_me("x", "", "http://nope", client=client_with(board_422())))
    assert [e["fix"] for e in out["errors"]] == [p["fix"] for p in PROBLEMS]
    assert out["fix"] and out["next_actions"] and out["code"] == "invalid_listing"


def test_tool_passes_connections_and_payment_methods():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"valid": True}})

    c = SarnAIClient(transport=httpx.MockTransport(handler))
    _tools.register_me("n", "d", "https://example.org/x", False,
                       '[{"type": "mcp", "url": "https://example.org/mcp"}]',
                       [{"type": "free"}], client=c)
    assert seen[0]["connections"] == [{"type": "mcp", "url": "https://example.org/mcp"}]
    assert seen[0]["payment_methods"] == [{"type": "free"}] and "submit" not in seen[0]


def test_register_me_description_states_limits_and_rules():
    text = " ".join(_tools.REGISTER_ME_DESCRIPTION.split())
    for needle in ("name 1-200 characters", "description 1-2000 characters", "public host",
                   "no user name or password", "lowercase types", "mcp, a2a, rest, x402",
                   "free, x402", "every connection needs a url",
                   "apply every fix in errors and call again"):
        assert needle in text, needle


def test_readme_register_me_example_cannot_publish():
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    for block in re.findall(r"```python\n(.*?)```", readme, flags=re.S):
        if "register_me" in block:
            assert "submit=True" not in block
    assert "publishes the listing for real" in " ".join(readme.split())


def test_changelog_has_current_version():
    import sarnai

    changelog = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text()
    assert f"## {sarnai.__version__}" in changelog
