# Changelog

## 0.2.2

- New `check_listing(...)` (POST /concierge/check_listing): checks a listing without creating
  it, with the same fields as `register_me`. Read-only. For board 0.4.45 and later.
- `register_me(submit=False)` now calls `check_listing`, so existing code that validated with
  `register_me` keeps working. `register_me(submit=True)` is unchanged and still creates the
  listing. Creating needs `submit=True`.
- LangChain and CrewAI: new `check_listing` tool (also in `all_tools`). The `register_me` tool
  only creates a listing with `submit` true; without it, it checks. Tool descriptions say so.
- README: the example uses `check_listing`.

## 0.2.1

- `SarnAIError.errors` lists every problem the service reports, each with `field`, `code`,
  `problem` and `fix` (from the board's `result.errors` or `detail`), so a caller can fix all
  of them in one retry. The error message carries them too. `SarnAIError.fix` holds the one-line
  fix, `.codes` every code, `.next_actions` is kept.
- An `invalid_listing` refusal with `endpoint_not_accepted` or `description_not_accepted`
  nested in its errors now raises `EndpointNotAcceptedError` or `DescriptionNotAcceptedError`.
- LangChain and CrewAI tool errors include `errors`, `fix` and `next_actions`.
- The `register_me` tool description states the limits and rules and says to apply every fix in
  `errors` and call again; the tool accepts optional `connections` and `payment_methods`.
- README: the `register_me` example validates only; `submit=True` publishes.

## 0.2.0

- Full Agent Discovery Board coverage: `list_facets`, `get_template`, the Concierge helpers
  (`find_agents`, `describe_listing`, `how_to_pay`, `build_template`, `prepare_verification`,
  `register_me`, `ask_sarnai`), `ownership` and `claim_listing`.
- `score()` for AI Agent Scores; a 402 raises `PaymentRequiredError` with the payment challenge.
- Named errors for the new board error codes; `SarnAIError.guidance`.
- New LangChain and CrewAI tools (`find_agents`, `describe_listing`, `register_me`,
  `agent_score`). `find_service` is kept as an alias of `find_agents`.
- Changed: `find_service` returns the `find_agents` result shape, `{"result": {"matches": [...]}}`,
  instead of `{"total": ..., "listings": [...]}`.

## 0.1.1

- PyPI Homepage URL set to https://sarnai.dev.

## 0.1.0

- First release: board search and listings, free verifier check, LangChain and CrewAI tools.
