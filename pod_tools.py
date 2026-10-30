# pod_tools.py
# Read-only functions that collect information about a Kubernetes pod.
# Every function runs one kubectl command and returns a Python dictionary.
# The dictionary always has "ok": True (it worked) or "ok": False (with an "error").

import json
import re
import subprocess
from datetime import datetime, timezone

# Kubernetes names may only contain lowercase letters, numbers, "-" and ".".
NAME_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")


def validate_name(value, label):
    """Stop unsafe names before they reach kubectl."""
    if not value or len(value) > 253 or not NAME_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def run_kubectl(args):
    """Run a kubectl command and return its output or a readable error."""
    command = ["kubectl"] + args
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return {"ok": False, "error": "kubectl was not found. Install kubectl first."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "kubectl did not answer within 20 seconds."}

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        return {"ok": False, "error": error}

    return {"ok": True, "output": result.stdout.strip()}


def list_pods(namespace):
    """Return the names of all pods in a namespace."""
    result = run_kubectl(["get", "pods", "-n", namespace,
                          "-o", "jsonpath={.items[*].metadata.name}"])
    if not result["ok"]:
        return result
    return {"ok": True, "pods": result["output"].split()}


def get_configured_resources(pod):
    """Read CPU/RAM requests and limits from the pod spec.
    These are settings, not real usage."""
    resources = []
    for container in pod["spec"]["containers"]:
        settings = container.get("resources", {})
        requests = settings.get("requests", {})
        limits = settings.get("limits", {})
        resources.append({
            "container": container["name"],
            "image": container["image"],
            "cpu_request": requests.get("cpu", "Not set"),
            "cpu_limit": limits.get("cpu", "Not set"),
            "memory_request": requests.get("memory", "Not set"),
            "memory_limit": limits.get("memory", "Not set"),
        })
    return resources


def get_pod_status(pod_name, namespace):
    """Read the pod's phase, node, IP, labels and the state of each container."""
    result = run_kubectl(["get", "pod", pod_name, "-n", namespace, "-o", "json"])
    if not result["ok"]:
        return result

    pod = json.loads(result["output"])
    status = pod.get("status", {})

    containers = []
    for item in status.get("containerStatuses", []):
        state = item.get("state", {})
        containers.append({
            "name": item["name"],
            "ready": item.get("ready", False),
            "restart_count": item.get("restartCount", 0),
            "waiting_reason": state.get("waiting", {}).get("reason", ""),
            "state": state,
            "last_state": item.get("lastState", {}),
        })

    return {
        "ok": True,
        "name": pod["metadata"]["name"],
        "namespace": pod["metadata"]["namespace"],
        "phase": status.get("phase", "Unknown"),
        "node": pod["spec"].get("nodeName", "Not scheduled"),
        "pod_ip": status.get("podIP", "Not assigned"),
        "created": pod["metadata"].get("creationTimestamp", "Unknown"),
        "labels": pod["metadata"].get("labels", {}),
        "containers": containers,
        "configured_resources": get_configured_resources(pod),
        "owner_references": pod["metadata"].get("ownerReferences", []),
    }


def get_pod_logs(pod_name, namespace):
    """Read the last 80 log lines from all containers in the pod."""
    result = run_kubectl(["logs", pod_name, "-n", namespace,
                          "--all-containers=true", "--tail=80"])
    if not result["ok"]:
        return result
    return {"ok": True, "logs": result["output"] or "(No log lines returned)"}


def get_pod_previous_logs(pod_name, namespace):
    """Read the logs of the previous container run (useful after a crash)."""
    result = run_kubectl(["logs", pod_name, "-n", namespace,
                          "--all-containers=true", "--tail=80", "--previous"])
    if not result["ok"]:
        return result
    return {"ok": True, "logs": result["output"] or "(No log lines returned)"}


def get_pod_events(pod_name, namespace):
    """Read the Kubernetes events for the pod, with UTC timestamps."""
    columns = ("custom-columns=FIRST_SEEN:.firstTimestamp,LAST_SEEN:.lastTimestamp,"
               "COUNT:.count,TYPE:.type,REASON:.reason,SOURCE:.source.component,"
               "MESSAGE:.message")
    result = run_kubectl(["get", "events", "-n", namespace,
                          "--field-selector", f"involvedObject.name={pod_name}",
                          "--sort-by=.lastTimestamp", "-o", columns])
    if not result["ok"]:
        return result
    return {"ok": True, "events": result["output"] or "(No events returned)"}


def get_pod_metrics(pod_name, namespace):
    """Read live CPU and RAM usage with kubectl top (needs Metrics Server)."""
    result = run_kubectl(["top", "pod", pod_name, "-n", namespace, "--containers"])
    if not result["ok"]:
        return {
            "ok": False,
            "cpu_ram": "Unavailable",
            "note": "kubectl top failed. Metrics Server may not be installed, "
                    "may not be ready, or the pod may not have metrics yet.",
            "error": result["error"],
        }
    return {"ok": True, "cpu_ram": result["output"]}


def get_pod_description(pod_name, namespace):
    """Read the full 'kubectl describe pod' output."""
    result = run_kubectl(["describe", "pod", pod_name, "-n", namespace])
    if not result["ok"]:
        return result
    return {"ok": True, "description": result["output"]}


def get_node_description(node_name):
    """Read the full 'kubectl describe node' output (conditions, taints, events)."""
    result = run_kubectl(["describe", "node", node_name])
    if not result["ok"]:
        return result
    return {"ok": True, "description": result["output"]}


def collect_pod_evidence(pod_name, namespace):
    """Collect all standard evidence for the report in one dictionary."""
    return {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "pod": get_pod_status(pod_name, namespace),
        "metrics": get_pod_metrics(pod_name, namespace),
        "events": get_pod_events(pod_name, namespace),
        "logs": get_pod_logs(pod_name, namespace),
        "previous_logs": get_pod_previous_logs(pod_name, namespace),
        "description": get_pod_description(pod_name, namespace),
    }
