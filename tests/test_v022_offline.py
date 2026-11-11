import json

import httpx
import pytest

import sarnai
from sarnai import (DescriptionNotAcceptedError, EndpointNotAcceptedError, SarnAIClient,
                    SarnAIError, _tools)

ARGS = ("My service", "What it does, in plain words.", "https://example.org/api")
EXTRA = dict(connections=[{"type": "mcp", "url": "https://example.org/mcp"}],
             payment_methods=[{"type": "free"}], samples=[{"a": 1}],
             submitted_by="0x" + "2" * 40)


def board():
    """A fake board 0.4.45: register_me without submit answers submit_required."""
    seen = []

    def handler(request):
        body = json.loads(request.content) if request.content else {}
        seen.append((request.url.path, body))
        if request.url.path == "/concierge/register_me" and not body.get("submit"):
            return httpx.Response(422, json={
                "ok": False, "tool": "register_me", "error_code": "submit_required",
                "message": "register_me creates a listing and needs submit true.",
                "fix": "To only check a listing call check_listing; to create it send submit true.",
                "next_actions": [{"method": "MCP_TOOL", "path": "check_listing",
                                  "description": "Check the listing without creating it."}]})
        return httpx.Response(200, json={"ok": True, "tool": request.url.path.rsplit("/", 1)[1],
                                         "result": {"valid": True, "submitted": bool(body.get("submit"))},
                                         "warnings": [], "next_actions": []})

    return seen, SarnAIClient(transport=httpx.MockTransport(handler))


def test_check_listing_posts_to_check_listing_with_register_me_fields():
    seen, c = board()
    env = c.check_listing(*ARGS, **EXTRA)
    path, body = seen[0]
    assert path == "/concierge/check_listing" and env["result"]["valid"] is True
    assert body == {"name": ARGS[0], "description": ARGS[1], "endpoint_url": ARGS[2],
                    "submitted_by": EXTRA["submitted_by"], "connections": EXTRA["connections"],
                    "payment_methods": EXTRA["payment_methods"], "samples": EXTRA["samples"]}
    assert "submit" not in body


def test_check_listing_takes_no_submit():
    _, c = board()
    with pytest.raises(TypeError):
        c.check_listing(*ARGS, submit=True)


def test_register_me_without_submit_calls_check_listing():
    seen, c = board()
    env = c.register_me(*ARGS, **EXTRA)
    path, body = seen[0]
    assert path == "/concierge/check_listing" and "submit" not in body
    assert env["result"]["submitted"] is False
    assert len(seen) == 1  # nothing was sent to register_me


def test_register_me_submit_true_is_unchanged():
    seen, c = board()
    env = c.register_me(*ARGS, submit=True, **EXTRA)
    path, body = seen[0]
    assert path == "/concierge/register_me" and body["submit"] is True
    assert body["name"] == ARGS[0] and body["connections"] == EXTRA["connections"]
    assert env["result"]["submitted"] is True


def test_board_answers_submit_required_to_register_me_without_submit():
    # What the board 0.4.45 does to a bare register_me call; the package never sends one,
    # but the error must come through whole if a caller does.
    _, c = board()
    with pytest.raises(SarnAIError) as info:
        c._concierge("register_me", {"name": "x"})
    err = info.value
    assert err.code == "submit_required" and err.status == 422
    assert "check_listing" in err.fix and "submit true" in err.fix
    assert err.next_actions[0]["path"] == "check_listing"
    assert type(err) is SarnAIError


def test_tool_submit_required_error_comes_through_with_fix_and_next_actions():
    _, c = board()
    out = json.loads(_tools._run(lambda cl: cl._concierge("register_me", {"name": "x"}), c))
    assert out["code"] == "submit_required" and "check_listing" in out["fix"]
    assert out["next_actions"][0]["path"] == "check_listing"


def test_tools_check_with_check_listing_and_create_with_submit():
    seen, c = board()
    _tools.check_listing(*ARGS, client=c)
    _tools.register_me(*ARGS, client=c)                  # no submit: checks
    _tools.register_me(*ARGS, submit=True, client=c)     # creates
    assert [p for p, _ in seen] == [
        "/concierge/check_listing", "/concierge/check_listing", "/concierge/register_me"]
    assert seen[2][1]["submit"] is True and "submit" not in seen[1][1]


def test_check_listing_errors_are_typed_and_carry_every_fix():
    problems = [{"field": "endpoint_url", "code": "endpoint_not_accepted", "problem": "private",
                 "fix": "Use a public https host."},
                {"field": "description", "code": "description_not_accepted", "problem": "links",
                 "fix": "Say what the service does."}]
    body = {"ok": False, "error_code": "invalid_listing", "message": "bad", "detail": problems,
            "fix": "Apply every fix.", "result": {"errors": problems}, "next_actions": []}
    c = SarnAIClient(transport=httpx.MockTransport(lambda r: httpx.Response(422, json=body)))
    with pytest.raises((EndpointNotAcceptedError, DescriptionNotAcceptedError)) as info:
        c.check_listing(*ARGS)
    assert [e["fix"] for e in info.value.errors] == [p["fix"] for p in problems]


def test_tool_descriptions():
    check = " ".join(_tools.CHECK_LISTING_DESCRIPTION.split())
    for needle in ("without creating it", "Read-only", "nothing is published", "name 1-200",
                   "description 1-2000", "public host", "apply every fix in errors and call again",
                   "register_me with submit true"):
        assert needle in check, needle
    reg = " ".join(_tools.REGISTER_ME_DESCRIPTION.split())
    for needle in ("Creating needs submit true", "publishes nothing", "check_listing",
                   "apply every fix in errors and call again"):
        assert needle in reg, needle


def test_langchain_check_listing_tool():
    pytest.importorskip("langchain_core")
    from sarnai import langchain as lc

    assert lc.check_listing.name == "check_listing"
    assert [t.name for t in lc.all_tools] == [
        "find_agents", "describe_listing", "check_listing", "register_me", "verify_output",
        "agent_score"]
    assert [t.name for t in lc.tools] == ["find_service", "verify_output"]


def test_version():
    assert sarnai.__version__ == "0.2.2"
