"""HTTP client for the SarnAI Agent Discovery Board, Agent Output Verifier and AI Agent Scores."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import quote

import httpx

from ._version import __version__

BOARD_URL = "https://board.sarnai.dev"
VERIFY_URL = "https://verify.sarnai.dev"
# The verifier's llms.txt and agent card list AI Agent Scores at score.sarnai.dev.
# verify.sarnai.dev/score answers too; pass score_url= to use it.
SCORE_URL = "https://score.sarnai.dev"
USER_AGENT = f"sarnai-python/{__version__}"


class SarnAIError(Exception):
    """A SarnAI service returned an error (or an unreadable response).

    `code` is the service's stable error code, `payload` the full JSON body. The verifier
    puts a `guidance` block on every error (what to do, a minimal valid request, price and
    free-allowance note); it is available as `.guidance`.
    """

    def __init__(self, message: str, *, status: int | None = None,
                 code: str | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload

    def _field(self, name: str) -> Any:
        return self.payload.get(name) if isinstance(self.payload, dict) else None

    @property
    def guidance(self) -> Any:
        return self._field("guidance")

    @property
    def next_actions(self) -> list[Any]:
        return self._field("next_actions") or []

    @property
    def retry_after(self) -> Any:
        return self._field("retry_after")

    @property
    def reason(self) -> Any:
        return self._field("reason")


class PaymentRequiredError(SarnAIError):
    """HTTP 402: the free allowance is used up (or a paid lookup was requested).

    Nothing is paid automatically. `challenge` is the 402 body (x402 v2: `accepts`, `resource`,
    free-allowance note); `payment_required` is the decoded `Payment-Required` header, if any.
    """

    def __init__(self, message: str, *, payment_required: Any = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.payment_required = payment_required

    @property
    def challenge(self) -> Any:
        return self.payload

    @property
    def accepts(self) -> list[Any]:
        source = self.payment_required or self.payload
        return (source.get("accepts") if isinstance(source, dict) else None) or []


class EndpointNotAcceptedError(SarnAIError):
    """endpoint_not_accepted (422): a listing posted without a wallet needs a real https endpoint."""


class DescriptionNotAcceptedError(SarnAIError):
    """description_not_accepted (422): a listing posted without a wallet needs a real description."""


class UnclaimedPostingPausedError(SarnAIError):
    """unclaimed_posting_paused (503): posting without a wallet is paused; see `retry_after`."""


class UnclaimedListingError(SarnAIError):
    """unclaimed_listing (403): the listing is unclaimed, so it cannot be edited; claim it first."""


_ERROR_CLASSES: dict[str, type[SarnAIError]] = {
    "endpoint_not_accepted": EndpointNotAcceptedError,
    "description_not_accepted": DescriptionNotAcceptedError,
    "unclaimed_posting_paused": UnclaimedPostingPausedError,
    "unclaimed_listing": UnclaimedListingError,
}


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


@dataclass
class AgentScore:
    """An AI Agent Score lookup. `raw` is the full signed response."""

    agent_id: str
    trust_score: float | None
    sample_size: int
    reason: str | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def has_score(self) -> bool:
        return self.trust_score is not None

    @property
    def attestation(self) -> dict[str, Any]:
        return self.raw.get("attestation") or {}


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def _decode_header(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(base64.b64decode(value + "=" * (-len(value) % 4)))
    except ValueError:
        return None


class SarnAIClient:
    """Find AI agent services, verify AI agent output, look up AI Agent Scores. No secrets needed.

    >>> with SarnAIClient() as sarnai:
    ...     page = sarnai.search_listings("invoice extraction", limit=5)
    """

    def __init__(self, *, board_url: str = BOARD_URL, verify_url: str = VERIFY_URL,
                 score_url: str = SCORE_URL, timeout: float = 30.0,
                 client: httpx.Client | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.board_url = board_url.rstrip("/")
        self.verify_url = verify_url.rstrip("/")
        self.score_url = score_url.rstrip("/")
        self._owns_client = client is None
        self._http = client or httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "SarnAIClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- board: browse -------------------------------------------------------

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
        return self._request("GET", f"{self.board_url}/listings/{quote(listing_id, safe='')}")

    def list_facets(self, **filters: Any) -> dict[str, Any]:
        """GET /listings/facets: counts per task category, listing type, network, source,
        connection type and payment type. Accepts the same filters as search_listings
        (q, listing_type, task_category, status, connection_type, payment_type, ...)."""
        return self._request("GET", f"{self.board_url}/listings/facets", params=_clean(filters))

    def get_template(self, listing_id: str) -> dict[str, Any]:
        """GET /listings/{id}/template: the listing's verification template (output_schema,
        rules, bounds). Raises SarnAIError with code "no_template" if it has none."""
        return self._request(
            "GET", f"{self.board_url}/listings/{quote(listing_id, safe='')}/template")

    # -- board: concierge (free, deterministic helpers) ----------------------

    def find_agents(
        self,
        need: str | None = None,
        *,
        task_category: str | Iterable[str] | None = None,
        connection_type: str | Iterable[str] | None = None,
        payment_type: str | Iterable[str] | None = None,
        exclude_payment_type: str | Iterable[str] | None = None,
        network: str | None = None,
        max_price_usd: float | None = None,
        has_template: bool | None = None,
        probe_status: str | None = None,
        source: str | None = None,
        include_stale: bool | None = None,
        include_no_connection: bool | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Say what you need in plain words; fixed rules turn it into filters.

        Returns the Concierge envelope {ok, tool, result, warnings, next_actions, meta};
        result["matches"] holds the services.
        """
        return self._concierge("find_agents", {
            "need": need, "task_category": _listify(task_category),
            "connection_type": _listify(connection_type),
            "payment_type": _listify(payment_type),
            "exclude_payment_type": _listify(exclude_payment_type),
            "network": network, "max_price_usd": max_price_usd,
            "has_template": has_template, "probe_status": probe_status, "source": source,
            "include_stale": include_stale, "include_no_connection": include_no_connection,
            "limit": limit,
        })

    def describe_listing(self, listing_id: str) -> dict[str, Any]:
        """How to connect, pay and verify one listing, with a call recipe per connection."""
        return self._concierge("describe_listing", {"listing_id": listing_id})

    def how_to_pay(self, listing_id: str | None = None, *, target: str | None = None,
                   payer: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ordered payment steps and cost for a listing (or target="verifier").
        Never pays or signs for you."""
        return self._concierge("how_to_pay", {
            "listing_id": listing_id, "target": target, "payer": payer})

    def build_template(self, samples: list[Any], *, expectations: dict[str, Any] | None = None,
                       name: str | None = None) -> dict[str, Any]:
        """Infer a verification template (JSON Schema + rules + bounds) from 1-10 sample
        outputs. Stores nothing."""
        return self._concierge("build_template", {
            "samples": samples, "expectations": expectations, "name": name})

    def prepare_verification(
        self,
        submitted_output: Any,
        *,
        listing_id: str | None = None,
        output_schema: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        task_id: str | None = None,
        inline_template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """The exact verifier request for a listing (or an inline schema). Evaluates nothing
        and sends nothing."""
        args = _clean({
            "listing_id": listing_id, "output_schema": output_schema,
            "verification": verification, "task_id": task_id,
            "inline_template": inline_template,
        })
        args["submitted_output"] = submitted_output
        return self._concierge("prepare_verification", args)

    def register_me(
        self,
        name: str,
        description: str,
        endpoint_url: str,
        *,
        submitted_by: str | None = None,
        connections: list[dict[str, Any]] | None = None,
        payment_methods: list[dict[str, Any]] | None = None,
        samples: list[Any] | None = None,
        submit: bool = False,
    ) -> dict[str, Any]:
        """List your own service. No wallet needed: leave `submitted_by` out and the listing
        goes live marked unclaimed (claim it later with claim_listing).

        By default only validates and prepares (errors with fixes, what would be stored).
        Pass submit=True to create the listing. Posting without a wallet can raise
        EndpointNotAcceptedError, DescriptionNotAcceptedError or UnclaimedPostingPausedError.
        """
        return self._concierge("register_me", {
            "name": name, "description": description, "endpoint_url": endpoint_url,
            "submitted_by": submitted_by, "connections": connections,
            "payment_methods": payment_methods, "samples": samples,
            "submit": True if submit else None,
        })

    def ask_sarnai(self, question: str, *, product: str | None = None,
                   limit: int | None = None) -> dict[str, Any]:
        """Answers about SarnAI's products (product: board | verifier | scores) or a listed
        service, quoted from the published documents."""
        return self._concierge("ask_sarnai", {
            "question": question, "product": product, "limit": limit})

    # -- board: ownership ----------------------------------------------------

    def ownership(self, listing_id: str, claimant: str) -> dict[str, Any]:
        """GET /listings/{id}/ownership?claimant=0x...: what to publish, and where, to prove
        control of the listing's domain or repository. Reads only."""
        return self._request(
            "GET", f"{self.board_url}/listings/{quote(listing_id, safe='')}/ownership",
            params={"claimant": claimant})

    def claim_listing(self, listing_id: str, *, method: str, claimant: str) -> dict[str, Any]:
        """POST /listings/{id}/claim with a domain or repository proof (no wallet signature).

        First call ownership(listing_id, claimant), publish the token it returns, then claim.
        `method` is "domain" or "repository"; `claimant` is the 0x address that should own the
        listing. A listing that has a payment_wallet is claimed by that wallet's signature
        instead; this method does not sign.
        """
        if method not in ("domain", "repository"):
            raise ValueError("method must be 'domain' or 'repository'")
        return self._request(
            "POST", f"{self.board_url}/listings/{quote(listing_id, safe='')}/claim",
            json={"method": method, "claimant": claimant})

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

        The Agent Output Verifier is independent and free during launch: 1,000 free checks a
        day per AI agent, then $0.02 per check. Beyond the free allowance the service answers
        402 and this raises PaymentRequiredError (nothing is paid automatically).
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
        return self._request("GET", f"{self.verify_url}/reputation/{quote(agent_id, safe='')}")

    # -- AI Agent Scores -----------------------------------------------------

    def score(self, agent_id: str) -> AgentScore:
        """GET /score/{agent_id}: an AI agent's verification history and signed score.

        $0.01 per lookup when there is a score; free when the AI agent has no history, in
        which case `has_score` is False and `reason` is "no_data" (the answer is still signed).
        When payment is needed this raises PaymentRequiredError carrying the x402 challenge;
        nothing is paid automatically. The base URL is configurable via `score_url`.
        """
        data = self._request("GET", f"{self.score_url}/score/{quote(agent_id, safe='')}")
        return AgentScore(
            agent_id=data.get("agent_id", agent_id),
            trust_score=data.get("trust_score"),
            sample_size=data.get("sample_size", 0),
            reason=data.get("reason"),
            raw=data,
        )

    # -- internals -----------------------------------------------------------

    def _concierge(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """POST /concierge/{tool}; returns the envelope {ok, tool, result, warnings, ...}."""
        return self._request("POST", f"{self.board_url}/concierge/{tool}", json=_clean(args))

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
        message = (info.get("message") or info.get("error")
                   or response.text[:200] or "request failed")
        text = f"{response.status_code} {code or ''}: {message}".replace("  ", " ")
        if response.status_code == 402:
            raise PaymentRequiredError(
                text, status=402, code=code or (info.get("payment_error") or {}).get("error_code"),
                payload=payload,
                payment_required=_decode_header(response.headers.get("payment-required")))
        cls = _ERROR_CLASSES.get(code or "", SarnAIError)
        raise cls(text, status=response.status_code, code=code, payload=payload)


def _listify(value: str | Iterable[str] | None) -> list[str] | None:
    if value is None:
        return None
    return [value] if isinstance(value, str) else list(value)
