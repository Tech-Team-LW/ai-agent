# agent_tools.py
# The tools that the LW-RCA-analyzer agent is allowed to use.
# @tool turns a normal Python function into a LangChain tool.
# The docstring tells Claude what the tool does. Every tool is read-only.

from langchain_core.tools import tool

import pod_tools


@tool
def inspect_pod(pod_name: str, namespace: str) -> dict:
    """Read the current status, node, labels and container state of one pod."""
    return pod_tools.get_pod_status(pod_name, namespace)


@tool
def read_pod_logs(pod_name: str, namespace: str) -> dict:
    """Read the latest log lines from all containers in one pod."""
    return pod_tools.get_pod_logs(pod_name, namespace)


@tool
def read_previous_pod_logs(pod_name: str, namespace: str) -> dict:
    """Read logs from the previous run of a container that crashed or restarted."""
    return pod_tools.get_pod_previous_logs(pod_name, namespace)


@tool
def read_pod_events(pod_name: str, namespace: str) -> dict:
    """Read Kubernetes events related to one pod, with UTC timestamps."""
    return pod_tools.get_pod_events(pod_name, namespace)


@tool
def read_pod_cpu_ram(pod_name: str, namespace: str) -> dict:
    """Read live pod/container CPU and memory usage using kubectl top."""
    return pod_tools.get_pod_metrics(pod_name, namespace)


@tool
def describe_pod(pod_name: str, namespace: str) -> dict:
    """Read the full kubectl describe output of one pod."""
    return pod_tools.get_pod_description(pod_name, namespace)


@tool
def describe_node(node_name: str) -> dict:
    """Read the kubectl describe output of a node: conditions, taints and events."""
    return pod_tools.get_node_description(node_name)


# The complete list of tools the agent may use.
ALL_TOOLS = [
    inspect_pod,
    read_pod_logs,
    read_previous_pod_logs,
    read_pod_events,
    read_pod_cpu_ram,
    describe_pod,
    describe_node,
]
