import json
import os
import subprocess
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

DEFAULT_NAMESPACE = os.getenv("K8S_NAMESPACE", "ai-sre-lab")


def run_kubectl(args, timeout=20):
    """Run kubectl safely and return stdout or a readable error."""
    command = ["kubectl"] + list(args)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out: {' '.join(command)}"}
    except FileNotFoundError:
        return {"ok": False, "error": "kubectl was not found. Install kubectl first."}

    if result.returncode != 0:
        return {
            "ok": False,
            "error": result.stderr.strip() or result.stdout.strip()
        }
    return {"ok": True, "output": result.stdout.strip()}


def list_pods(namespace=DEFAULT_NAMESPACE):
    """Return the names of all pods in a namespace."""
    result = run_kubectl([
        "get", "pods", "-n", namespace,
        "-o", "jsonpath={.items[*].metadata.name}"
    ])
    if not result["ok"]:
        return result
    return {"ok": True, "pods": result["output"].split()}


def get_configured_resources(pod):
    """Read CPU/RAM requests and limits from the pod spec (configuration, not usage)."""
    resources = []
    for container in pod.get("spec", {}).get("containers", []):
        settings = container.get("resources", {})
        requests = settings.get("requests", {})
        limits = settings.get("limits", {})
        resources.append({
            "container": container.get("name", "unknown"),
            "image": container.get("image", "unknown"),
            "cpu_request": requests.get("cpu", "Not set"),
            "cpu_limit": limits.get("cpu", "Not set"),
            "memory_request": requests.get("memory", "Not set"),
            "memory_limit": limits.get("memory", "Not set"),
        })
    return resources


def get_pod_status(pod_name, namespace=DEFAULT_NAMESPACE):
    result = run_kubectl([
        "get", "pod", pod_name, "-n", namespace, "-o", "json"
    ])
    if not result["ok"]:
        return result

    try:
        pod = json.loads(result["output"])
    except json.JSONDecodeError:
        return {"ok": False, "error": "kubectl returned output that is not valid JSON."}

    statuses = pod.get("status", {}).get("containerStatuses", [])
    containers = []
    for item in statuses:
        state = item.get("state", {})
        waiting_reason = state.get("waiting", {}).get("reason", "")
        containers.append({
            "name": item.get("name", "unknown"),
            "ready": item.get("ready", False),
            "restart_count": item.get("restartCount", 0),
            "waiting_reason": waiting_reason,
            "state": state
        })

    return {
        "ok": True,
        "name": pod["metadata"]["name"],
        "namespace": pod["metadata"]["namespace"],
        "phase": pod.get("status", {}).get("phase", "Unknown"),
        "node": pod.get("spec", {}).get("nodeName", "Not scheduled"),
        "pod_ip": pod.get("status", {}).get("podIP", "Not assigned"),
        "created": pod.get("metadata", {}).get("creationTimestamp", "Unknown"),
        "labels": pod.get("metadata", {}).get("labels", {}),
        "containers": containers,
        "configured_resources": get_configured_resources(pod),
        "owner_references": pod.get("metadata", {}).get("ownerReferences", [])
    }


def get_pod_logs(pod_name, namespace=DEFAULT_NAMESPACE, tail=80):
    result = run_kubectl([
        "logs", pod_name, "-n", namespace, "--all-containers=true",
        f"--tail={int(tail)}"
    ])
    if not result["ok"]:
        return result
    return {"ok": True, "logs": result["output"] or "(No log lines returned)"}


def get_pod_events(pod_name, namespace=DEFAULT_NAMESPACE):
    result = run_kubectl([
        "get", "events", "-n", namespace,
        "--field-selector", f"involvedObject.name={pod_name}",
        "--sort-by=.lastTimestamp", "-o", "wide"
    ])
    if not result["ok"]:
        return result
    return {"ok": True, "events": result["output"] or "(No events returned)"}


def get_pod_metrics(pod_name, namespace=DEFAULT_NAMESPACE):
    """Read live CPU/RAM usage from Metrics Server via kubectl top."""
    result = run_kubectl([
        "top", "pod", pod_name, "-n", namespace, "--containers"
    ])
    if not result["ok"]:
        return {
            "ok": False,
            "cpu_ram": "Unavailable",
            "note": "kubectl top failed. Metrics Server may not be installed, "
                    "may not be ready, or the pod may not have metrics yet.",
            "error": result["error"]
        }
    return {"ok": True, "cpu_ram": result["output"]}


def get_pod_description(pod_name, namespace=DEFAULT_NAMESPACE):
    result = run_kubectl(["describe", "pod", pod_name, "-n", namespace])
    if not result["ok"]:
        return result
    return {"ok": True, "description": result["output"]}


def collect_pod_evidence(pod_name, namespace=DEFAULT_NAMESPACE):
    """Gather the evidence used by the AI and the report writer."""
    return {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "pod": get_pod_status(pod_name, namespace),
        "metrics": get_pod_metrics(pod_name, namespace),
        "events": get_pod_events(pod_name, namespace),
        "logs": get_pod_logs(pod_name, namespace),
        "description": get_pod_description(pod_name, namespace)
    }
