"""Tests against the live SarnAI services. Skip with: pytest -m "not live"."""

import json

import pytest

from sarnai import SarnAIClient, SarnAIError

pytestmark = pytest.mark.live

SCHEMA = {"type": "object", "required": ["total"], "properties": {"total": {"type": "number"}}}


@pytest.fixture
def client():
    with SarnAIClient() as c:
        yield c


def test_search_and_get_listing(client):
    page = client.search_listings("verify", limit=2)
    assert page["listings"] and "next_cursor" in page
    listing = client.get_listing(page["listings"][0]["id"])
    assert listing["id"] == page["listings"][0]["id"]


def test_get_missing_listing(client):
    with pytest.raises(SarnAIError) as info:
        client.get_listing("00000000-0000-0000-0000-000000000000")
    assert info.value.status in (404, 422)


def test_verify_pass_and_fail(client):
    # agent_id with the reserved 'test-' prefix is never recorded.
    ok = client.verify_output(SCHEMA, {"total": 3}, agent_id="test-sarnai-python")
    bad = client.verify_output(SCHEMA, {"total": "x"}, agent_id="test-sarnai-python")
    assert ok.passed and not bad.passed
    assert bad.attestation["algorithm"] == "Ed25519"


def test_tools_end_to_end():
    from sarnai import _tools

    found = json.loads(_tools.find_service("verification", 2))
    assert found["result"]["matches"]
    res = json.loads(_tools.verify_output(SCHEMA, {"total": 1}))
    assert res["result"] == "pass"


def test_compact_detail(client):
    res = client.verify_output(SCHEMA, {"total": "x"}, agent_id="test-sarnai-python",
                               compact=True)
    assert not res.passed and "errors" not in res.raw
    assert res.attestation["algorithm"] == "Ed25519"
