from langchain_core.tools import tool
from dotenv import load_dotenv

from pod_tools import (
    get_pod_status,
    get_pod_logs,
    get_pod_events,
    get_pod_metrics,
)

load_dotenv()


@tool
def inspect_pod(pod_name: str, namespace: str = "ai-sre-lab") -> dict:
    """Read the current status, node, labels and container state of one pod."""
    return get_pod_status(pod_name, namespace)


@tool
def read_pod_logs(pod_name: str, namespace: str = "ai-sre-lab") -> dict:
    """Read the latest log lines from all containers in one pod."""
    return get_pod_logs(pod_name, namespace)


@tool
def read_pod_events(pod_name: str, namespace: str = "ai-sre-lab") -> dict:
    """Read Kubernetes events related to one pod."""
    return get_pod_events(pod_name, namespace)


@tool
def read_pod_cpu_ram(pod_name: str, namespace: str = "ai-sre-lab") -> dict:
    """Read live pod/container CPU and memory usage using kubectl top."""
    return get_pod_metrics(pod_name, namespace)
