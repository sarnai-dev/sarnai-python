"""register_me error handling against the live board. Skip with: pytest -m "not live".

Validate-only: every call omits submit, so nothing is ever published. All names start with
"test-" except the localhost case, because test- names are exempt from the host rule.
"""

import json

import pytest

from sarnai import EndpointNotAcceptedError, SarnAIClient, SarnAIError, _tools

pytestmark = pytest.mark.live

# Two problems at once: empty description and a non-https endpoint.
BAD = dict(name="test-sarnai-python-two-problems", description="",
           endpoint_url="http://example.org/api")


@pytest.fixture
def client():
    with SarnAIClient() as c:
        yield c


def test_two_problems_come_back_together_with_fixes(client):
    with pytest.raises(SarnAIError) as info:
        client.register_me(**BAD)
    err = info.value
    assert err.status == 422 and err.code == "invalid_listing"
    fields = {e["field"] for e in err.errors}
    assert len(err.errors) >= 2 and any("description" in str(f) for f in fields)
    assert any("endpoint" in str(f) for f in fields)
    assert all(e["fix"] and e["problem"] for e in err.errors)
    assert err.fix and err.next_actions


def test_tool_output_carries_every_fix():
    out = json.loads(_tools.register_me(**BAD))
    assert len(out["errors"]) >= 2
    assert all(e["fix"] for e in out["errors"])
    assert out["fix"] and out["next_actions"]


def test_same_call_is_valid_after_applying_the_fixes(client):
    with pytest.raises(SarnAIError) as info:
        client.register_me(**BAD)
    assert info.value.errors
    fixed = dict(BAD, description="A probe used only to check validation output, nothing more.",
                 endpoint_url="https://test-sarnai-python.example.invalid/api")
    env = client.register_me(**fixed)
    assert env["ok"] and env["result"]["valid"] and env["result"]["submitted"] is False


def test_localhost_endpoint_raises_endpoint_not_accepted(client):
    # A plain name: test- names are exempt from the host rule. Still validate-only.
    with pytest.raises(EndpointNotAcceptedError) as info:
        client.register_me("sarnai-python-localhost-probe",
                           "A probe used only to check validation output, nothing more.",
                           "https://localhost:8000/api")
    assert isinstance(info.value, SarnAIError)
    assert "endpoint_not_accepted" in info.value.codes
    assert info.value.errors and all(e["fix"] for e in info.value.errors)
