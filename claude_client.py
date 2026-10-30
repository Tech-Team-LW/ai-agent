import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

PLACEHOLDER_KEY = "replace_with_your_real_key"


def build_prompt(evidence):
    return f"""
You are a careful DevOps incident investigator.
Use only the evidence below. Do not invent CPU, RAM, timestamps, or events.
"metrics" is live usage from kubectl top. "configured_resources" are requests
and limits from the pod spec. Never present a request or limit as actual usage.
If CPU/RAM metrics are unavailable, say so.

Write these sections in Markdown:
1. Incident summary
2. Confirmed observations (facts directly visible in the evidence)
3. Possible causes (hypotheses, clearly labelled as not yet confirmed)
4. Recommended next checks (read-only commands first)
5. Confidence level (low, medium, or high) and why

Do not claim you changed the cluster.

EVIDENCE JSON:
{json.dumps(evidence, indent=2)}
"""


def explain_incident(evidence):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL")

    if not api_key or api_key == PLACEHOLDER_KEY:
        return (
            "AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env. "
            "The collected Kubernetes evidence is still included in the report."
        )
    if not model:
        return "AI explanation unavailable: set ANTHROPIC_MODEL in .env."

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": build_prompt(evidence)}]
        )
    except anthropic.AuthenticationError:
        return "AI explanation unavailable: the API key was rejected. Check ANTHROPIC_API_KEY."
    except anthropic.NotFoundError:
        return f"AI explanation unavailable: model {model!r} was not found. Check ANTHROPIC_MODEL."
    except anthropic.RateLimitError:
        return "AI explanation unavailable: rate limit or quota reached. Try again later."
    except anthropic.APIConnectionError:
        return "AI explanation unavailable: could not connect to the Claude API. Check network access."
    except anthropic.APIStatusError as exc:
        return f"AI explanation unavailable: API error {exc.status_code}: {exc.message}"

    if response.stop_reason == "refusal":
        return "AI explanation unavailable: Claude declined this request."

    pieces = []
    for block in response.content:
        if block.type == "text":
            pieces.append(block.text)
    return "\n".join(pieces).strip() or "Claude returned no text."
