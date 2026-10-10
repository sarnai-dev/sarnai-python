"""HTTP client for the SarnAI Agent Discovery Board and Agent Output Verifier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

from ._version import __version__

BOARD_URL = "https://board.sarnai.dev"
VERIFY_URL = "https://verify.sarnai.dev"
USER_AGENT = f"sarnai-python/{__version__}"


class SarnAIError(Exception):
    """A SarnAI service returned an error (or an unreadable response)."""

    def __init__(self, message: str, *, status: int | None = None,
                 code: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload


class PaymentRequiredError(SarnAIError):
    """HTTP 402: the free allowance is used up and x402 payment is needed."""


@dataclass
class VerifyResult:
    """Outcome of a verification. `raw` is the full signed response."""

    result: str
    verification_id: str
    task_id: str
    raw: dict[str, Any] = field(repr=False)

    @property
    def passed(self) -> bool:
        return self.result == "pass"

    @property
    def errors(self) -> list[Any]:
        return self.raw.get("errors") or []

    @property
    def hints(self) -> list[Any]:
        return self.raw.get("hints") or []

    @property
    def attestation(self) -> dict[str, Any]:
        return self.raw.get("attestation") or {}


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


class SarnAIClient:
    """Find services on the board and verify outputs. No secrets needed.

    >>> with SarnAIClient() as sarnai:
    ...     page = sarnai.search_listings("invoice extraction", limit=5)
    """

    def __init__(self, *, board_url: str = BOARD_URL, verify_url: str = VERIFY_URL,
                 timeout: float = 30.0, client: httpx.Client | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.board_url = board_url.rstrip("/")
        self.verify_url = verify_url.rstrip("/")
        self._owns_client = client is None
        self._http = client or httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "SarnAIClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- board ---------------------------------------------------------------

    def search_listings(
        self,
        q: str | None = None,
        *,
        listing_type: str | None = None,
        task_category: str | Iterable[str] | None = None,
        connection_type: str | Iterable[str] | None = None,
        payment_type: str | Iterable[str] | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /listings. Returns {listings, total, limit, offset, next_cursor}.

        Without `q`, newest activity first; with `q`, ranked full-text search.
        Pass `next_cursor` back as `cursor` for the next page (with the same `q`).
        """
        params: dict[str, Any] = _clean({
            "q": q, "listing_type": listing_type, "status": status,
            "limit": limit, "cursor": cursor,
        })
        for key, value in (("task_category", task_category),
                           ("connection_type", connection_type),
                           ("payment_type", payment_type)):
            if value is not None:
                params[key] = [value] if isinstance(value, str) else list(value)
        return self._request("GET", f"{self.board_url}/listings", params=params)

    def get_listing(self, listing_id: str) -> dict[str, Any]:
        """GET /listings/{id}."""
        return self._request("GET", f"{self.board_url}/listings/{listing_id}")

    # -- verifier ------------------------------------------------------------

    def verify_output(
        self,
        expected_schema: dict[str, Any],
        submitted_output: Any,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        rules: list[dict[str, Any]] | None = None,
        bounds: dict[str, Any] | None = None,
        enforce_rules: bool | None = None,
        strict_content_check: bool | None = None,
        compact: bool = False,
        endpoint: str = "schema",
    ) -> VerifyResult:
        """POST /verify/schema (or /verify/deliverable with endpoint="deliverable").

        Free during launch (see the verifier's llms.txt for the daily allowance).
        Beyond it the service answers 402 and this raises PaymentRequiredError.
        """
        if endpoint not in ("schema", "deliverable"):
            raise ValueError("endpoint must be 'schema' or 'deliverable'")
        body = _clean({
            "task_id": task_id or str(uuid.uuid4()),
            "expected_schema": expected_schema,
            "submitted_output": submitted_output,
            "agent_id": agent_id,
            "rules": rules,
            "bounds": bounds,
            "enforce_rules": enforce_rules,
            "strict_content_check": strict_content_check,
            "detail": "compact" if compact else None,
        })
        # submitted_output may legitimately be null; _clean would drop it.
        body["submitted_output"] = submitted_output
        data = self._request("POST", f"{self.verify_url}/verify/{endpoint}", json=body)
        return VerifyResult(
            result=data["result"],
            verification_id=data.get("verification_id", ""),
            task_id=data.get("task_id", body["task_id"]),
            raw=data,
        )

    def reputation(self, agent_id: str) -> dict[str, Any]:
        """GET /reputation/{agent_id}: free pass/fail call history."""
        return self._request("GET", f"{self.verify_url}/reputation/{agent_id}")

    # -- internals -----------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(
                method, url, headers={"User-Agent": USER_AGENT}, **kwargs)
        except httpx.HTTPError as exc:
            raise SarnAIError(f"request to {url} failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.is_success:
            if payload is None:
                raise SarnAIError("response was not JSON", status=response.status_code)
            return payload
        # Board errors use `error_code`, the verifier uses `code`.
        info = payload if isinstance(payload, dict) else {}
        code = info.get("error_code") or info.get("code")
        message = info.get("message") or response.text[:200] or "request failed"
        cls = PaymentRequiredError if response.status_code == 402 else SarnAIError
        raise cls(f"{response.status_code} {code or ''}: {message}".replace("  ", " "),
                  status=response.status_code, code=code, payload=payload)
