import json

import httpx
import pytest

from sarnai import PaymentRequiredError, SarnAIClient, SarnAIError
from sarnai import _tools


def make_client(handler):
    return SarnAIClient(transport=httpx.MockTransport(handler))


def test_search_builds_query():
    seen = {}

    def handler(request):
        seen["url"] = request.url
        return httpx.Response(200, json={"listings": [], "total": 0})

    make_client(handler).search_listings("invoice", task_category=["a", "b"], limit=3)
    assert seen["url"].path == "/listings"
    assert seen["url"].params["q"] == "invoice"
    assert seen["url"].params.get_list("task_category") == ["a", "b"]
    assert seen["url"].params["limit"] == "3"


def test_board_error_code():
    client = make_client(lambda r: httpx.Response(
        404, json={"error_code": "not_found", "message": "No such listing"}))
    with pytest.raises(SarnAIError) as info:
        client.get_listing("x")
    assert info.value.code == "not_found" and info.value.status == 404


def test_verify_402_and_body():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(402, json={"error_code": "no_payment", "message": "pay"})

    with pytest.raises(PaymentRequiredError):
        make_client(handler).verify_output({"type": "object"}, None, compact=True)
    assert "submitted_output" in seen["body"] and seen["body"]["detail"] == "compact"
    assert seen["body"]["task_id"]


def test_verify_result():
    client = make_client(lambda r: httpx.Response(200, json={
        "result": "pass", "verification_id": "v", "task_id": "t"}))
    assert client.verify_output({"type": "object"}, {}).passed


def test_tool_helpers_accept_json_strings():
    def handler(request):
        return httpx.Response(200, json={"result": "fail", "verification_id": "v",
                                         "task_id": "t", "errors": ["e"], "hints": []})

    out = json.loads(_tools.verify_output('{"type": "object"}', '{"a": 1}',
                                          client=make_client(handler)))
    assert out["result"] == "fail" and out["errors"] == ["e"]
    assert "error" in json.loads(_tools.verify_output("nope", {}))


def test_langchain_tool_names():
    pytest.importorskip("langchain_core")
    from sarnai.langchain import tools

    assert [t.name for t in tools] == ["find_service", "verify_output"]
