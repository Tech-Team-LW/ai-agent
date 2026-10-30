# agent.py
# LW-RCA-analyzer: the AI agent.
# Claude decides which read-only tools to call. Python runs them and sends back
# the results. This repeats until Claude writes the Root Cause Analysis (RCA).

import json
import os

import anthropic
from dotenv import load_dotenv

from agent_tools import ALL_TOOLS
from pod_tools import validate_name

load_dotenv()

AGENT_NAME = "LW-RCA-analyzer"
MAX_STEPS = 10  # the agent may ask Claude at most 10 times

SYSTEM_PROMPT = """
You are LW-RCA-analyzer, a careful Site Reliability Engineer agent.
You investigate one Kubernetes pod and write a Root Cause Analysis (RCA).

You have read-only tools. Decide yourself which tools to call next, based on
what you have learned so far. For example: if events mention a node problem,
describe the node; if a container restarted, read its previous logs.
Stop calling tools when you have enough evidence.

Rules:
- Use only evidence returned by the tools. Do not invent CPU, RAM, timestamps, or events.
- "read_pod_cpu_ram" is live usage. Requests and limits from the pod spec are
  settings, not real usage. If metrics are unavailable, say so.
- You cannot change the cluster. Do not claim you changed anything.

When you are done, write the RCA in Markdown with exactly these sections,
using level-3 headings (###):
### 1. Executive summary
### 2. Problem statement
### 3. Impact
### 4. Timeline (UTC)
### 5. Confirmed observations
### 6. Root cause
### 7. Contributing factors
### 8. Five whys
### 9. Corrective actions
### 10. Preventive actions
### 11. Verification steps
### 12. Confidence level and evidence gaps

In "Root cause", write "Confirmed root cause" only if the evidence directly proves
it; otherwise write "Most likely root cause (not confirmed)". If the pod is healthy,
write "No incident detected" and do not invent a root cause. Mark every corrective
action as "not performed by the agent; requires human approval".
"""


def tool_definitions():
    """Describe our LangChain tools in the format the Claude API expects."""
    definitions = []
    for tool in ALL_TOOLS:
        definitions.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.tool_call_schema.model_json_schema(),
        })
    return definitions


def run_tool(name, tool_input):
    """Run one tool that Claude asked for. Always returns text for Claude."""
    # 1. Find the tool. Claude may only use tools from ALL_TOOLS.
    chosen_tool = None
    for tool in ALL_TOOLS:
        if tool.name == name:
            chosen_tool = tool
    if chosen_tool is None:
        return json.dumps({"ok": False, "error": f"Unknown tool: {name}"})

    # 2. Check every name Claude sent (pod, namespace, node) before using it.
    try:
        for key, value in tool_input.items():
            validate_name(str(value), key)
        result = chosen_tool.invoke(tool_input)
    except Exception as error:
        return json.dumps({"ok": False, "error": str(error)})

    # 3. Send the result back to Claude as text.
    return json.dumps(result)


def investigate_pod(pod_name, namespace):
    """Run the agent. Returns the RCA text and the list of tools it used."""
    steps = []
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL")

    if not api_key or api_key == "replace_with_your_real_key":
        return "AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env.", steps
    if not model:
        return "AI explanation unavailable: set ANTHROPIC_MODEL in .env.", steps

    client = anthropic.Anthropic(api_key=api_key)

    # The conversation starts with the task.
    messages = [{
        "role": "user",
        "content": f"Investigate pod {pod_name} in namespace {namespace} and write the RCA.",
    }]

    for step in range(1, MAX_STEPS + 1):
        # On the last step, switch tools off so Claude must write the RCA.
        if step == MAX_STEPS:
            tool_choice = {"type": "none"}
        else:
            tool_choice = {"type": "auto"}

        # Ask Claude what to do next.
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=tool_definitions(),
                tool_choice=tool_choice,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            return "AI explanation unavailable: the API key was rejected.", steps
        except anthropic.NotFoundError:
            return f"AI explanation unavailable: model {model!r} was not found.", steps
        except anthropic.RateLimitError:
            return "AI explanation unavailable: rate limit or quota reached.", steps
        except anthropic.APIConnectionError:
            return "AI explanation unavailable: could not connect to the Claude API.", steps
        except anthropic.APIStatusError as error:
            return f"AI explanation unavailable: API error {error.status_code}.", steps

        if response.stop_reason == "refusal":
            return "AI explanation unavailable: Claude declined this request.", steps

        # If Claude did not ask for a tool, it has finished. Its text is the RCA.
        if response.stop_reason != "tool_use":
            rca = ""
            for block in response.content:
                if block.type == "text":
                    rca += block.text
            return rca.strip(), steps

        # Claude asked for tools. Save Claude's message in the conversation.
        messages.append({"role": "assistant", "content": response.content})

        # Run every tool Claude asked for and collect the results.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  Step {step}: {block.name} {json.dumps(block.input)}")
                steps.append({"step": step, "tool": block.name, "input": block.input})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": run_tool(block.name, block.input),
                })

        # Send all tool results back to Claude in one message.
        messages.append({"role": "user", "content": results})

    return "AI explanation unavailable: the agent stopped without an RCA.", steps
