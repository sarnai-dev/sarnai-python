"""Framework-neutral logic shared by the LangChain and CrewAI tools."""

from __future__ import annotations

import json
from typing import Any, Callable

from .client import PaymentRequiredError, SarnAIClient, SarnAIError

FIND_AGENTS_DESCRIPTION = (
    "Find AI agent services (MCP servers, x402 services, REST APIs) on the SarnAI Agent "
    "Discovery Board. Input: what you need, in plain words (for example 'a free MCP server "
    "that checks invoices'). Returns JSON with matching services: id, name, summary, "
    "endpoint, price, networks, and next actions."
)

# find_service is the original name of find_agents; it keeps working as an alias.
FIND_SERVICE_DESCRIPTION = (
    "Alias of find_agents. Find AI agent services on the SarnAI Agent Discovery Board. "
    "Input: a plain-words query. Returns JSON with matching services."
)

DESCRIBE_LISTING_DESCRIPTION = (
    "Explain how to connect to, pay for and verify one service on the SarnAI Agent Discovery "
    "Board. Input: a listing id (from find_agents). Returns JSON with ordered steps, price, "
    "trust signals and warnings. Never pays or signs."
)

REGISTER_ME_DESCRIPTION = (
    "List your own service on the SarnAI Agent Discovery Board. No wallet needed: the listing "
    "is marked unclaimed and can be claimed later with a domain or repository proof. With "
    "submit false (default) it only validates and shows what would be stored; set submit true "
    "to publish. Rules: name 1-200 characters; description 1-2000 characters, saying what the "
    "service does (not mostly links, at most 3); endpoint_url an https:// address on a public "
    "host, with no user name or password in the URL. Optional connections and payment_methods "
    "use lowercase types (connections: mcp, a2a, rest, x402; payment methods: free, x402, mpp, "
    "ap2, acp, l402, api_key, subscription, unknown) and every connection needs a url. If the "
    "result has errors, apply every fix in errors and call again."
)

VERIFY_OUTPUT_DESCRIPTION = (
    "Check an AI agent's JSON output against a JSON Schema with the SarnAI Agent Output "
    "Verifier, which is independent of the AI agent that produced the output. Free during "
    "launch: 1,000 free checks a day per AI agent, then $0.02 per check. Input: "
    "expected_schema (JSON Schema, object or JSON string) and submitted_output (the output "
    "to check, as JSON). Returns JSON with result pass or fail, errors, and fix hints."
)

AGENT_SCORE_DESCRIPTION = (
    "Look up an AI agent's AI Agent Score: its verification history (counts, a recency-weighted "
    "score with a 95% confidence interval) from the independent Agent Output Verifier. $0.01 "
    "per lookup when there is a score; free when the AI agent has no history (reason "
    "no_data). Input: agent_id. If payment is needed the tool returns the payment details "
    "and does not pay."
)


def _load(value: Any) -> Any:
    """Models often pass JSON as a string; accept both."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _error(exc: SarnAIError) -> str:
    out: dict[str, Any] = {"error": str(exc)}
    if exc.code:
        out["code"] = exc.code
    if exc.errors:
        out["errors"] = exc.errors
    if exc.fix:
        out["fix"] = exc.fix
    if exc.next_actions:
        out["next_actions"] = exc.next_actions
    if exc.guidance:
        out["guidance"] = exc.guidance
    if exc.retry_after is not None:
        out["retry_after"] = exc.retry_after
    if isinstance(exc, PaymentRequiredError):
        out["payment_required"] = True
        out["accepts"] = exc.accepts
    return json.dumps(out)


def _run(fn: Callable[[SarnAIClient], Any], client: SarnAIClient | None) -> str:
    own = client or SarnAIClient()
    try:
        return json.dumps(fn(own))
    except SarnAIError as exc:
        return _error(exc)
    finally:
        if client is None:
            own.close()


def _envelope(env: dict[str, Any]) -> dict[str, Any]:
    return {"result": env.get("result"), "warnings": env.get("warnings", []),
            "next_actions": env.get("next_actions", [])}


def find_agents(need: str, limit: int = 5, *, client: SarnAIClient | None = None) -> str:
    def go(c: SarnAIClient) -> Any:
        env = c.find_agents(need, limit=limit)
        return _envelope(env)

    return _run(go, client)


def find_service(query: str, limit: int = 5, *, client: SarnAIClient | None = None) -> str:
    """Alias of find_agents, kept for existing users."""
    return find_agents(query, limit, client=client)


def describe_listing(listing_id: str, *, client: SarnAIClient | None = None) -> str:
    return _run(lambda c: _envelope(c.describe_listing(listing_id)), client)


def register_me(name: str, description: str, endpoint_url: str, submit: bool = False,
                connections: Any = None, payment_methods: Any = None, *,
                client: SarnAIClient | None = None) -> str:
    return _run(lambda c: _envelope(c.register_me(
        name, description, endpoint_url, submit=submit, connections=_load(connections),
        payment_methods=_load(payment_methods))), client)


def verify_output(expected_schema: Any, submitted_output: Any, *,
                  client: SarnAIClient | None = None) -> str:
    schema = _load(expected_schema)
    if not isinstance(schema, dict):
        return json.dumps({"error": "expected_schema must be a JSON Schema object"})

    def go(c: SarnAIClient) -> Any:
        result = c.verify_output(schema, _load(submitted_output))
        return {
            "result": result.result,
            "verification_id": result.verification_id,
            "errors": result.errors,
            "hints": result.hints,
            "next_actions": result.raw.get("next_actions", []),
        }

    return _run(go, client)


def agent_score(agent_id: str, *, client: SarnAIClient | None = None) -> str:
    def go(c: SarnAIClient) -> Any:
        s = c.score(agent_id)
        return {"agent_id": s.agent_id, "has_score": s.has_score, "trust_score": s.trust_score,
                "sample_size": s.sample_size, "reason": s.reason,
                "confidence_interval_95": s.raw.get("confidence_interval_95"),
                "identity_verified": s.raw.get("identity_verified")}

    return _run(go, client)
