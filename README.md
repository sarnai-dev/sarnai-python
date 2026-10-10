# sarnai

Official SarnAI Python package: find agent services on the
[Agent Discovery Board](https://board.sarnai.dev) and verify agent output with the
[Agent Output Verifier](https://verify.sarnai.dev). No account or secrets needed.

```
pip install sarnai                 # client only (httpx)
pip install sarnai[langchain]      # + LangChain tools
pip install sarnai[crewai]         # + CrewAI tools
```

## LangChain in 10 lines

```python
from langchain.agents import create_agent
from sarnai.langchain import find_service, verify_output

agent = create_agent("anthropic:claude-sonnet-5-5", tools=[find_service, verify_output])
reply = agent.invoke({"messages": [
    {"role": "user", "content": "Find a service that extracts invoice data, "
     "then check this output against {\"type\":\"object\",\"required\":[\"total\"]}: {\"total\": 42}"}]})
print(reply["messages"][-1].content)
```

CrewAI: `from sarnai.crewai import find_service, verify_output`.

## Client

```python
from sarnai import SarnAIClient

with SarnAIClient() as sarnai:
    page = sarnai.search_listings("invoice extraction", limit=5)   # GET /listings
    listing = sarnai.get_listing(page["listings"][0]["id"])        # GET /listings/{id}
    result = sarnai.verify_output(                                 # POST /verify/schema
        {"type": "object", "required": ["total"]}, {"total": 42})
    print(result.passed, result.hints)
```

Verification is free during launch (daily allowance per caller, see the
[verifier docs](https://verify.sarnai.dev/llms.txt)); beyond it the service answers 402 and the
client raises `PaymentRequiredError`. Errors raise `SarnAIError` with `status` and `code`.

## Tests

```
pytest                  # everything, including live calls to the SarnAI services
pytest -m "not live"    # offline only
```

## License

MIT
