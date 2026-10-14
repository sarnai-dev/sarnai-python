import base64
import json
import re
from pathlib import Path

import httpx
import pytest

import sarnai
from sarnai import (DescriptionNotAcceptedError, EndpointNotAcceptedError, PaymentRequiredError,
                    SarnAIClient, SarnAIError, UnclaimedListingError,
                    UnclaimedPostingPausedError, _tools)


def make_client(handler, **kwargs):
    return SarnAIClient(transport=httpx.MockTransport(handler), **kwargs)


def recorder(response=None):
    seen = []

    def handler(request):
        seen.append(request)
        return response or httpx.Response(200, json={"ok": True, "result": {"matches": []}})

    return seen, handler


@pytest.mark.parametrize("code,cls,status", [
    ("endpoint_not_accepted", EndpointNotAcceptedError, 422),
    ("description_not_accepted", DescriptionNotAcceptedError, 422),
    ("unclaimed_posting_paused", UnclaimedPostingPausedError, 503),
    ("unclaimed_listing", UnclaimedListingError, 403),
])
def test_named_board_errors(code, cls, status):
    client = make_client(lambda r: httpx.Response(status, json={
        "error_code": code, "message": "no", "reason": "why", "retry_after": 30}))
    with pytest.raises(cls) as info:
        client.get_listing("x")
    assert isinstance(info.value, SarnAIError)
    assert info.value.code == code and info.value.status == status
    assert info.value.reason == "why" and info.value.retry_after == 30


def test_unknown_code_is_plain_error():
    client = make_client(lambda r: httpx.Response(404, json={"error_code": "not_found"}))
    with pytest.raises(SarnAIError) as info:
        client.get_listing("x")
    assert type(info.value) is SarnAIError


def test_verifier_error_guidance():
    guidance = {"what_to_do": "fix", "example_request": {"task_id": "t"}}
    client = make_client(lambda r: httpx.Response(422, json={
        "code": "invalid_request", "message": "bad", "guidance": guidance}))
    with pytest.raises(SarnAIError) as info:
        client.verify_output({"type": "object"}, {})
    assert info.value.guidance == guidance


def test_score_default_url_and_no_data():
    seen, handler = recorder(httpx.Response(200, json={
        "agent_id": "a", "trust_score": None, "sample_size": 0, "reason": "no_data"}))
    result = make_client(handler).score("a")
    assert str(seen[0].url) == "https://score.sarnai.dev/score/a"
    assert not result.has_score and result.reason == "no_data"


def test_score_url_configurable():
    seen, handler = recorder(httpx.Response(200, json={"trust_score": 0.9, "sample_size": 4}))
    result = make_client(handler, score_url="https://verify.sarnai.dev/").score("a b")
    assert str(seen[0].url) == "https://verify.sarnai.dev/score/a%20b"
    assert result.has_score


def test_score_402_carries_challenge_and_does_not_pay():
    header = {"x402Version": 2, "accepts": [{"network": "eip155:8453", "amount": "10000"}]}
    seen, handler = recorder(httpx.Response(
        402, json={"x402Version": 2, "accepts": header["accepts"], "error": "pay"},
        headers={"Payment-Required": base64.b64encode(json.dumps(header).encode()).decode()}))
    with pytest.raises(PaymentRequiredError) as info:
        make_client(handler).score("a")
    err = info.value
    assert len(seen) == 1 and "payment-signature" not in seen[0].headers
    assert err.challenge["x402Version"] == 2 and err.payment_required == header
    assert err.accepts == header["accepts"] and err.status == 402


def test_facets_template_ownership_claim_requests():
    seen, handler = recorder(httpx.Response(200, json={}))
    c = make_client(handler)
    c.list_facets(listing_type="offering")
    c.get_template("L1")
    c.ownership("L1", "0xabc")
    c.claim_listing("L1", method="domain", claimant="0xabc")
    facets, template, ownership, claim = seen
    assert facets.url.path == "/listings/facets" and facets.url.params["listing_type"] == "offering"
    assert template.url.path == "/listings/L1/template"
    assert ownership.url.path == "/listings/L1/ownership" and ownership.url.params["claimant"] == "0xabc"
    assert claim.method == "POST" and claim.url.path == "/listings/L1/claim"
    assert json.loads(claim.content) == {"method": "domain", "claimant": "0xabc"}
    assert "x-wallet-auth" not in claim.headers
    with pytest.raises(ValueError):
        c.claim_listing("L1", method="wallet", claimant="0xabc")


def test_concierge_routes_and_register_me_without_wallet():
    seen, handler = recorder()
    c = make_client(handler)
    c.find_agents("web search", limit=2, exclude_payment_type="x402")
    c.describe_listing("L1")
    c.how_to_pay(target="verifier")
    c.build_template([{"a": 1}])
    c.prepare_verification({"a": 1}, listing_id="L1")
    c.register_me("n", "d", "https://example.org/x")
    c.register_me("n", "d", "https://example.org/x", submit=True)
    c.ask_sarnai("what does it cost", product="verifier")
    assert [r.url.path for r in seen] == [
        f"/concierge/{t}" for t in ("find_agents", "describe_listing", "how_to_pay",
                                    "build_template", "prepare_verification", "register_me",
                                    "register_me", "ask_sarnai")]
    assert json.loads(seen[0].content) == {
        "need": "web search", "exclude_payment_type": ["x402"], "limit": 2}
    dry, live = json.loads(seen[5].content), json.loads(seen[6].content)
    assert "submitted_by" not in dry and "submit" not in dry
    assert "submitted_by" not in live and live["submit"] is True


def test_find_service_is_an_alias_of_find_agents():
    seen, handler = recorder()
    c = make_client(handler)
    assert _tools.find_service("web search", 3, client=c) == _tools.find_agents(
        "web search", 3, client=c)
    assert json.loads(seen[0].content) == json.loads(seen[1].content) == {
        "need": "web search", "limit": 3}


def test_tool_error_includes_guidance_and_payment_details():
    guidance = {"what_to_do": "fix"}
    c = make_client(lambda r: httpx.Response(422, json={
        "code": "invalid_request", "message": "bad", "guidance": guidance}))
    out = json.loads(_tools.verify_output({"type": "object"}, {}, client=c))
    assert out["guidance"] == guidance and out["code"] == "invalid_request"
    c = make_client(lambda r: httpx.Response(402, json={"accepts": [{"amount": "1"}]}))
    out = json.loads(_tools.agent_score("a", client=c))
    assert out["payment_required"] is True and out["accepts"] == [{"amount": "1"}]


def test_langchain_tools_and_legacy_names():
    pytest.importorskip("langchain_core")
    from sarnai import langchain as lc

    assert [t.name for t in lc.tools] == ["find_service", "verify_output"]
    assert [t.name for t in lc.all_tools] == [
        "find_agents", "describe_listing", "register_me", "verify_output", "agent_score"]
    assert lc.find_service.name == "find_service"


def test_version_matches_user_agent():
    assert sarnai.__version__ == "0.2.0"


# -- public wording --------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = {
    "README": (ROOT / "README.md").read_text(),
    "descriptions": " ".join(getattr(_tools, n) for n in dir(_tools) if n.endswith("_DESCRIPTION")),
}


@pytest.mark.parametrize("name", PUBLIC)
def test_no_internal_wording(name):
    text = PUBLIC[name].lower()
    for word in ("roadmap", "strategy", "internal", "todo", "competitor", "monetiz"):
        assert word not in text


def test_prices_and_terms_in_public_text():
    readme = PUBLIC["README"]
    for needle in ("AI Agent Scores", "independent", "1,000 free checks a day per AI agent",
                   "$0.02 per check", "$0.01 per lookup", "free when the AI agent has no history"):
        assert needle in readme
    verify = _tools.VERIFY_OUTPUT_DESCRIPTION
    assert "independent" in verify and "1,000 free checks a day per AI agent" in verify
    assert "$0.02 per check" in verify
    score = _tools.AGENT_SCORE_DESCRIPTION
    assert "$0.01 per lookup when there is a score" in score
    assert "free when the AI agent has no history" in score


def test_running_text_says_ai_agent():
    # "agent" as a bare noun in running text should be "AI agent" (product and API names excepted).
    allowed = re.compile(r"(AI agent|AI Agent|Agent Discovery|Agent Output|Agent Scores?|"
                         r"find_agents|agent_score|agent_id|AI-agent|ai-agents|agents)", re.I)
    for text in PUBLIC.values():
        text = re.sub(r"```.*?```", "", text, flags=re.S)  # code blocks
        text = re.sub(r"`[^`]*`", "", text)  # inline code
        for sentence in re.split(r"[.\n]", text):
            for m in re.finditer(r"\bagent\b", sentence):
                start = max(0, m.start() - 12)
                assert allowed.search(sentence[start:m.end() + 8]), sentence
