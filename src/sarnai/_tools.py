"""Framework-neutral logic shared by the LangChain and CrewAI tools."""

from __future__ import annotations

import json
from typing import Any

from .client import SarnAIClient, SarnAIError

FIND_SERVICE_DESCRIPTION = (
    "Find AI agent services on the SarnAI Agent Discovery Board (MCP servers, x402 "
    "services, REST APIs). Input: plain-words query. Returns JSON with matching "
    "listings: id, name, description, endpoint_url, connection types, payment types."
)

VERIFY_OUTPUT_DESCRIPTION = (
    "Verify an agent's JSON output against a JSON Schema with the SarnAI Agent Output "
    "Verifier (free REST check). Input: expected_schema (JSON Schema, object or JSON "
    "string) and submitted_output (the output to check, as JSON). Returns JSON with "
    "result pass/fail, errors, and fix hints."
)

_LISTING_KEYS = ("id", "name", "description", "listing_type", "task_categories",
                 "endpoint_url", "pricing_amount", "stale")


def _load(value: Any) -> Any:
    """Models often pass JSON as a string; accept both."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def find_service(query: str, limit: int = 5, *, client: SarnAIClient | None = None) -> str:
    own = client or SarnAIClient()
    try:
        page = own.search_listings(query, limit=limit)
    except SarnAIError as exc:
        return json.dumps({"error": str(exc)})
    finally:
        if client is None:
            own.close()
    listings = []
    for item in page.get("listings", []):
        row = {k: item.get(k) for k in _LISTING_KEYS}
        row["connection_types"] = [c.get("type") for c in item.get("connections") or []]
        row["payment_types"] = [p.get("type") for p in item.get("payment_methods") or []]
        listings.append(row)
    return json.dumps({"total": page.get("total"), "listings": listings})


def verify_output(expected_schema: Any, submitted_output: Any, *,
                  client: SarnAIClient | None = None) -> str:
    schema = _load(expected_schema)
    if not isinstance(schema, dict):
        return json.dumps({"error": "expected_schema must be a JSON Schema object"})
    own = client or SarnAIClient()
    try:
        result = own.verify_output(schema, _load(submitted_output))
    except SarnAIError as exc:
        return json.dumps({"error": str(exc)})
    finally:
        if client is None:
            own.close()
    return json.dumps({
        "result": result.result,
        "verification_id": result.verification_id,
        "errors": result.errors,
        "hints": result.hints,
        "next_actions": result.raw.get("next_actions", []),
    })
