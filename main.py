import argparse
import json
import re

from dotenv import load_dotenv

from pod_tools import collect_pod_evidence, list_pods
from claude_client import explain_incident
from reporting import create_markdown_report
from agent_tools import inspect_pod, read_pod_logs, read_pod_events, read_pod_cpu_ram

load_dotenv()

NAME_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")


def validate_name(value, label):
    if not value or len(value) > 253 or not NAME_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def choose_pod(namespace):
    """Show the pods in the namespace and let the user pick one."""
    result = list_pods(namespace)
    if not result["ok"]:
        print("Could not list pods:", result["error"])
        raise SystemExit(1)
    if not result["pods"]:
        print(f"No pods found in namespace {namespace}.")
        raise SystemExit(1)

    print(f"Pods in namespace {namespace}:")
    for number, name in enumerate(result["pods"], start=1):
        print(f"  {number}. {name}")

    answer = input("Enter a number or the exact pod name: ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(result["pods"]):
        return result["pods"][int(answer) - 1]
    return answer


def main():
    parser = argparse.ArgumentParser(
        description="Investigate a Kubernetes pod and create a Markdown RCA report."
    )
    parser.add_argument("--pod", help="Exact pod name (leave out to choose from a list)")
    parser.add_argument("--namespace", default="ai-sre-lab", help="Kubernetes namespace")
    args = parser.parse_args()

    try:
        namespace = validate_name(args.namespace, "namespace")
        pod_name = args.pod or choose_pod(namespace)
        pod_name = validate_name(pod_name, "pod name")
    except ValueError as error:
        print(error)
        print("Names may only use lowercase letters, numbers, '-' and '.'.")
        raise SystemExit(1)

    print(f"\nInvestigating pod {pod_name} in namespace {namespace} (read-only).")

    print("\n[1/5] Checking pod status with LangChain tool...")
    status = inspect_pod.invoke({"pod_name": pod_name, "namespace": namespace})
    if not status.get("ok"):
        print("Could not inspect pod:", status.get("error", status))
        print("Check the pod name and namespace using: kubectl get pods -n", namespace)
        raise SystemExit(1)
    print(json.dumps(status, indent=2))

    print("\n[2/5] Reading logs with LangChain tool...")
    print(read_pod_logs.invoke({"pod_name": pod_name, "namespace": namespace}))

    print("\n[3/5] Reading events with LangChain tool...")
    print(read_pod_events.invoke({"pod_name": pod_name, "namespace": namespace}))

    print("\n[4/5] Reading CPU/RAM with LangChain tool...")
    print(read_pod_cpu_ram.invoke({"pod_name": pod_name, "namespace": namespace}))

    print("\n[5/5] Collecting full evidence and asking Claude for a root cause analysis...")
    evidence = collect_pod_evidence(pod_name, namespace)
    explanation = explain_incident(evidence)
    report_path = create_markdown_report(
        pod_name, namespace, evidence, explanation
    )

    print("\nReport created successfully:")
    print(report_path)
    print("\nOpen it with:")
    print(f"cat {report_path}")


if __name__ == "__main__":
    main()
