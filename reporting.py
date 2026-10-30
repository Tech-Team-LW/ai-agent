import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def configured_resources_table(resources):
    """Build a Markdown table of configured requests and limits."""
    if not resources:
        return "Configured requests/limits: Unavailable (pod details could not be read)."
    lines = [
        "| Container | CPU request | CPU limit | Memory request | Memory limit |",
        "|---|---|---|---|---|",
    ]
    for item in resources:
        lines.append(
            f"| {item['container']} | {item['cpu_request']} | {item['cpu_limit']} "
            f"| {item['memory_request']} | {item['memory_limit']} |"
        )
    return "\n".join(lines)


def create_markdown_report(pod_name, namespace, evidence, ai_explanation):
    report_dir = Path(os.getenv("REPORT_DIR", "reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    pod = evidence.get("pod", {})
    metrics = evidence.get("metrics", {})
    events = evidence.get("events", {})
    logs = evidence.get("logs", {})
    description = evidence.get("description", {})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = report_dir / f"incident_{safe_filename(namespace)}_{safe_filename(pod_name)}_{timestamp}.md"

    cpu_ram = metrics.get("cpu_ram", "Unavailable") if metrics.get("ok") else "Unavailable"
    metrics_note = ""
    if not metrics.get("ok"):
        metrics_note = "**Live metrics could not be retrieved.** " + metrics.get("note", "")
        if metrics.get("error"):
            metrics_note += f"\n\nKubernetes said: `{metrics['error']}`"

    content = f"""# Kubernetes Pod Incident Report

- **Generated at (local time):** {datetime.now().isoformat(timespec="seconds")}
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

{configured_resources_table(pod.get("configured_resources", []))}

> Requests and limits are configuration settings, not measurements.

## Container state

```json
{json.dumps(pod.get("containers", []), indent=2)}
```

## Kubernetes events

```text
{events.get("events", events.get("error", "Unavailable"))}
```

## Recent logs

```text
{logs.get("logs", logs.get("error", "Unavailable"))}
```

## Pod description

```text
{description.get("description", description.get("error", "Unavailable"))[:8000]}
```

## AI investigation

{ai_explanation}

## Verification and limitations

- This report is based on evidence collected from the current Kubernetes cluster.
- The AI explanation is advisory; verify recommendations before making changes.
- This program did not restart, delete, or modify the pod.
- Missing metrics or unavailable logs are reported as unavailable, not guessed.
"""
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)
