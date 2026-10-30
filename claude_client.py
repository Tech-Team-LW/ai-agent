import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

PLACEHOLDER_KEY = "replace_with_your_real_key"


def build_prompt(evidence):
    return f"""
You are a careful Site Reliability Engineer writing a Root Cause Analysis (RCA)
for one Kubernetes pod.
Use only the evidence below. Do not invent CPU, RAM, timestamps, or events.
"metrics" is live usage from kubectl top. "configured_resources" are requests
and limits from the pod spec. Never present a request or limit as actual usage.
If CPU/RAM metrics are unavailable, say so.
"last_state" and "previous_logs" describe the previous container run (for
example an OOMKilled or crashed container). Use them when the pod restarted.
Event times in "events" are absolute UTC timestamps; use them for the timeline.

Write the RCA in Markdown with exactly these sections, using level-3 headings
(###), so it fits inside the report:
### 1. Executive summary
Two or three sentences: what failed, the root cause, and the current state.
### 2. Problem statement
Pod, namespace, node, symptom, and when it was first observed.
### 3. Impact
What is affected according to the evidence (for example: container never
started, no logs, restarts). Say "unknown" for anything the evidence cannot show.
### 4. Timeline (UTC)
A table of events in time order, taken only from timestamps in the evidence.
### 5. Confirmed observations
Facts directly visible in the evidence.
### 6. Root cause
Label it "Confirmed root cause" only if the evidence directly proves it.
Otherwise label it "Most likely root cause (not confirmed)" and say what is
missing. If the pod is healthy and shows no failure, write "No incident
detected" and explain why; do not invent a root cause.
### 7. Contributing factors
Configuration or conditions that made the problem possible or worse.
### 8. Five whys
A short chain from the symptom to the root cause. Stop where the evidence ends.
### 9. Corrective actions
Immediate fix steps for a human to review and run. Mark each as
"not performed by the agent; requires human approval".
### 10. Preventive actions
Changes that would stop this from happening again.
### 11. Verification steps
Read-only commands to confirm the fix worked.
### 12. Confidence level and evidence gaps
Low, medium, or high, and why. List evidence that would raise confidence.

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
