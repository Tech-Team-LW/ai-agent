# main.py
# Start LW-RCA-analyzer from the terminal:
#   python main.py --pod <pod-name> --namespace ai-sre-lab
# Leave out --pod to choose a pod from a list.

import argparse

from agent import AGENT_NAME, investigate_pod
from pod_tools import collect_pod_evidence, get_pod_status, list_pods, validate_name
from reporting import create_markdown_report


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
    # 1. Read the command-line options.
    parser = argparse.ArgumentParser(
        description=f"{AGENT_NAME}: investigate a Kubernetes pod and write an RCA report."
    )
    parser.add_argument("--pod", help="Exact pod name (leave out to choose from a list)")
    parser.add_argument("--namespace", default="ai-sre-lab", help="Kubernetes namespace")
    args = parser.parse_args()

    # 2. Check the names, so only safe names reach kubectl.
    try:
        namespace = validate_name(args.namespace, "namespace")
        pod_name = args.pod or choose_pod(namespace)
        pod_name = validate_name(pod_name, "pod name")
    except ValueError as error:
        print(error)
        print("Names may only use lowercase letters, numbers, '-' and '.'.")
        raise SystemExit(1)

    print(f"\n=== {AGENT_NAME} ===")
    print(f"Investigating pod {pod_name} in namespace {namespace} (read-only).")

    # 3. Make sure the pod exists before calling the AI.
    print("\n[1/3] Checking that the pod exists...")
    status = get_pod_status(pod_name, namespace)
    if not status["ok"]:
        print("Could not find the pod:", status["error"])
        print("Check the pod name and namespace with: kubectl get pods -n", namespace)
        raise SystemExit(1)
    print(f"Pod found: phase={status['phase']}, node={status['node']}")

    # 4. Let the AI agent investigate. It prints each tool it uses.
    print(f"\n[2/3] {AGENT_NAME} is investigating (Claude chooses the read-only tools)...")
    rca, steps = investigate_pod(pod_name, namespace)

    # 5. Collect the standard evidence and write the report.
    print("\n[3/3] Collecting evidence and writing the RCA report...")
    evidence = collect_pod_evidence(pod_name, namespace)
    report_path = create_markdown_report(pod_name, namespace, evidence, rca, steps)

    print("\nReport created successfully:")
    print(report_path)
    print("\nOpen it with:")
    print(f"cat {report_path}")


if __name__ == "__main__":
    main()
