"""v0.2.0 tests against the live SarnAI services. Skip with: pytest -m "not live".

Read-only or validate-only: nothing is created, claimed or paid for.
"""

import json

import pytest

from sarnai import PaymentRequiredError, SarnAIClient, SarnAIError, _tools

pytestmark = pytest.mark.live


@pytest.fixture
def client():
    with SarnAIClient() as c:
        yield c


def test_find_agents_and_describe(client):
    env = client.find_agents("web search", limit=2)
    assert env["ok"] and env["result"]["matches"]
    listing_id = env["result"]["matches"][0]["listing_id"]
    assert client.describe_listing(listing_id)["ok"]


def test_how_to_pay_verifier(client):
    assert client.how_to_pay(target="verifier")["ok"]


def test_build_and_prepare(client):
    samples = [{"total": 1.5, "currency": "USD"}, {"total": 2, "currency": "EUR"}]
    assert client.build_template(samples)["ok"]
    env = client.prepare_verification({"total": 1}, output_schema={"type": "object"})
    assert env["ok"]


def test_register_me_validates_without_wallet(client):
    env = client.register_me("test-sarnai-python-probe",
                             "A probe used only to check validation output, nothing more.",
                             "https://example.org/api")
    assert env["ok"] and env["result"]["valid"] and env["result"]["submitted"] is False


def test_ask_sarnai(client):
    assert client.ask_sarnai("What does the verifier cost?", product="verifier")["ok"]


def test_facets_and_template(client):
    facets = client.list_facets(listing_type="offering")
    assert facets["total"] > 0 and "by_task_category" in facets
    page = client.search_listings("invoice", listing_type="verification_profile", limit=5)
    with_template = [x for x in page["listings"] if x.get("output_schema")]
    if with_template:
        assert "output_schema" in client.get_template(with_template[0]["id"])
    missing = client.search_listings("web search", limit=1)["listings"][0]["id"]
    try:
        client.get_template(missing)
    except SarnAIError as exc:
        assert exc.code == "no_template"


def test_ownership_and_claim_failure_path(client):
    listing_id = client.search_listings("web search", limit=1)["listings"][0]["id"]
    info = client.ownership(listing_id, "0x" + "1" * 40)
    assert info["listing_id"] == listing_id
    # A claim on a listing that does not exist changes nothing.
    with pytest.raises(SarnAIError) as err:
        client.claim_listing("00000000-0000-0000-0000-000000000000",
                             method="domain", claimant="0x" + "1" * 40)
    assert err.value.status in (404, 422)


@pytest.mark.parametrize("score_url", [None, "https://verify.sarnai.dev"])
def test_score_no_data_is_free_and_signed(score_url):
    kwargs = {"score_url": score_url} if score_url else {}
    with SarnAIClient(**kwargs) as c:
        result = c.score("test-sarnai-python-nohistory")
    assert not result.has_score and result.reason == "no_data"
    assert result.attestation["algorithm"] == "Ed25519"


def test_verifier_error_has_guidance(client):
    with pytest.raises(SarnAIError) as err:
        client.verify_output({"type": "nonsense"}, {}, agent_id="test-sarnai-python")
    assert err.value.guidance


def test_402_challenge_is_carried_not_paid(client):
    # An empty POST is the x402 discovery probe: answered with 402, nothing charged.
    with pytest.raises(PaymentRequiredError) as err:
        client._request("POST", f"{client.verify_url}/verify/schema")
    assert err.value.accepts and err.value.challenge["x402Version"] == 2
    assert err.value.payment_required["x402Version"] == 2


def test_new_tools_end_to_end():
    found = json.loads(_tools.find_service("web search", 2))
    assert found["result"]["matches"]
    score = json.loads(_tools.agent_score("test-sarnai-python-nohistory"))
    assert score["has_score"] is False and score["reason"] == "no_data"
