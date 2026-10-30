# reporting.py
# Writes the LW-RCA-analyzer report as a Markdown file in the reports/ folder.

import json
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def text_or_error(result, key):
    """Return result[key] if it exists, otherwise the error message."""
    if key in result:
        return result[key]
    if "error" in result:
        return result["error"]
    return "Unavailable"


def resources_table(resources):
    """Build a Markdown table of the configured CPU/RAM requests and limits."""
    if not resources:
        return "Configured requests/limits: Unavailable (pod details could not be read)."
    lines = [
        "| Container | CPU request | CPU limit | Memory request | Memory limit |",
        "|---|---|---|---|---|",
    ]
    for item in resources:
        lines.append(f"| {item['container']} | {item['cpu_request']} | {item['cpu_limit']} "
                     f"| {item['memory_request']} | {item['memory_limit']} |")
    return "\n".join(lines)


def steps_list(agent_steps):
    """Build a Markdown list of the tools the agent used."""
    if not agent_steps:
        return "No tools were called by the AI agent."
    lines = []
    for item in agent_steps:
        lines.append(f"- Step {item['step']}: `{item['tool']}` with `{json.dumps(item['input'])}`")
    return "\n".join(lines)


def create_markdown_report(pod_name, namespace, evidence, rca, agent_steps=None):
    """Write the report file and return its path."""
    # 1. Make sure the reports folder exists.
    report_dir = os.getenv("REPORT_DIR", "reports")
    os.makedirs(report_dir, exist_ok=True)

    # 2. Build the file name, for example: incident_ai-sre-lab_my-pod_20261031_041101.md
    now = datetime.now()
    file_name = f"incident_{namespace}_{pod_name}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    file_path = os.path.join(report_dir, file_name)

    # 3. Take each part of the evidence (an empty dictionary if it is missing).
    pod = evidence.get("pod", {})
    metrics = evidence.get("metrics", {})

    # 4. Live CPU/RAM usage. If it failed, explain why instead of inventing numbers.
    if metrics.get("ok"):
        cpu_ram = metrics["cpu_ram"]
        metrics_note = ""
    else:
        cpu_ram = "Unavailable"
        metrics_note = "**Live metrics could not be retrieved.** " + metrics.get("note", "")
        if "error" in metrics:
            metrics_note += f"\n\nKubernetes said: `{metrics['error']}`"

    # 5. The text of each evidence section.
    events = text_or_error(evidence.get("events", {}), "events")
    logs = text_or_error(evidence.get("logs", {}), "logs")
    previous_logs = text_or_error(evidence.get("previous_logs", {}), "logs")
    description = text_or_error(evidence.get("description", {}), "description")
    containers = json.dumps(pod.get("containers", []), indent=2)

    # 6. Put everything into one Markdown document.
    content = f"""# LW-RCA-analyzer: Kubernetes Pod Incident and Root Cause Analysis (RCA) Report

- **Generated at (local time):** {now.isoformat(timespec="seconds")}
- **Evidence collected at (UTC):** {evidence.get("collected_at_utc", "Unknown")}
- **Pod name:** {pod_name}
- **Namespace:** {namespace}
- **Status:** {pod.get("phase", "Unknown")}
- **Node:** {pod.get("node", "Unknown")}
- **Pod IP:** {pod.get("pod_ip", "Unknown")}
- **Created:** {pod.get("created", "Unknown")}

## Actual CPU and RAM usage (live, from kubectl top)

```text
{cpu_ram}
```

{metrics_note}

> CPU/RAM above is live usage from Kubernetes Metrics Server when available. It is not the pod's configured limit. If marked unavailable, no usage number was invented.

## Configured CPU and RAM (requests and limits from the pod spec)

{resources_table(pod.get("configured_resources", []))}

> Requests and limits are configuration settings, not measurements.

## Container state

```json
{containers}
```

## Kubernetes events

```text
{events}
```

## Recent logs

```text
{logs}
```

## Previous container logs (before the last restart)

```text
{previous_logs}
```

## Pod description

```text
{description}
```

## AI agent investigation steps

LW-RCA-analyzer chose these read-only tools itself. Tools with the same step number were called together.

{steps_list(agent_steps)}

## Root cause analysis (AI-generated, advisory)

{rca}

## Verification and limitations

- This report is based on evidence collected from the current Kubernetes cluster.
- The AI analysis is advisory; verify recommendations before making changes.
- LW-RCA-analyzer did not restart, delete, or modify the pod.
- Missing metrics or unavailable logs are reported as unavailable, not guessed.
"""

    # 7. Save the file.
    with open(file_path, "w", encoding="utf-8") as report_file:
        report_file.write(content)
    return file_path
