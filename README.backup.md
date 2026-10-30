# AI-Powered Kubernetes Pod Investigation Agent

**Agentic AI for DevOps & IT Automation — a practical, beginner-friendly build**

RHEL 10 | k3d Kubernetes | Python | Claude API | LangChain | pytest

---

## 1. Overview

Imagine a developer says: *"My application pod is not working."*

Instead of typing many `kubectl` commands by hand, you run **one Python program**. It:

1. Checks a real Kubernetes pod.
2. Collects real evidence: status, node, container readiness, restarts, logs, events, CPU and RAM usage.
3. Asks Claude to explain that evidence.
4. Saves a professional Markdown incident report in `reports/`.

The agent **never invents CPU or RAM numbers**. If Kubernetes metrics are not available, the report says so.

### What you will build

- A Python command-line app that accepts a pod name and namespace (or lets you pick a pod from a list).
- Read-only diagnostic tools that run `kubectl`.
- LangChain tool wrappers around those diagnostic functions.
- A Claude-powered explanation that separates **confirmed observations** from **possible causes**.
- A Markdown report generator.
- Automated `pytest` tests that run without a cluster.
- Two real reports: one for a healthy pod and one for a deliberately broken pod.

### Safety boundary

- The tool is **read-only**. It never restarts, deletes, or changes a pod.
- Claude never gets shell access. Python decides which commands run; Claude only reads the results.
- Use this lab on a test machine, never against a production cluster.
- Never commit `.env` or your API key to Git.

---

## 2. Main ideas in simple English

**AI agent** — A normal chatbot only answers questions. An agent follows a task, uses tools, looks at the results, and then produces an answer. Here, **Python controls the steps** and **Claude explains the evidence**.

**Tool** — A normal Python function the agent can use, for example `get_pod_status()` or `get_pod_metrics()`. A tool must return real data or a clear error.

**Claude API** — Anthropic's API for sending text to Claude and getting a reply. We send Claude the collected evidence as JSON and ask for an incident explanation.

**LangChain** — A library that gives Python functions a standard "tool" format (a name, a description, and typed inputs). We use `langchain-core`'s `@tool` decorator. In this beginner version our own Python code calls the tools in a fixed order, which keeps the flow easy to read and test.

**Real report** — Built from the Kubernetes API and `kubectl top`. CPU/RAM usage needs **Metrics Server**. If it is missing, the report shows `Unavailable` instead of made-up values.

**Actual usage vs configured resources** — These are different things:

| Value | Where it comes from | Meaning |
|---|---|---|
| Actual CPU / RAM usage | `kubectl top pod` (Metrics Server) | What the pod is really using right now |
| CPU / memory **requests** | Pod spec | The minimum the scheduler reserves |
| CPU / memory **limits** | Pod spec | The maximum the container is allowed |

The report shows them in separate sections and never mixes them up.

---

## 3. How the agent works

```text
 You
  │  python main.py --pod <name> --namespace ai-sre-lab
  ▼
main.py ── validates the names (lowercase letters, numbers, '-' and '.')
  │
  ├─[1/5] inspect_pod        (LangChain tool) ─┐
  ├─[2/5] read_pod_logs      (LangChain tool)  │  agent_tools.py
  ├─[3/5] read_pod_events    (LangChain tool)  │      │
  ├─[4/5] read_pod_cpu_ram   (LangChain tool) ─┘      ▼
  │                                             pod_tools.py ── read-only kubectl
  │                                                                   │
  │                                                                   ▼
  │                                                       k3d Kubernetes cluster
  └─[5/5] collect_pod_evidence() ──► claude_client.py ──► Claude API
                     │                         │
                     └──────────┬──────────────┘
                                ▼
                          reporting.py ──► reports/incident_<ns>_<pod>_<time>.md
```

- **Python** runs `kubectl`, handles errors, and writes files.
- **Kubernetes** supplies the facts.
- **Claude** explains the facts. It does not run commands and does not change the cluster.
- **You** read the report and decide what to do.

---

## 4. Project structure

```text
~/agent/
├── manual.docs            original course manual (do not edit)
├── README.md              this practical manual
├── requirements.txt       Python packages
├── .gitignore             keeps .env, .venv and reports out of Git
├── .env.example           configuration template (placeholders only)
├── .env                   your real configuration (private, git-ignored)
├── pytest.ini             tells pytest to import modules from the project folder
├── main.py                entry point: validate → collect → explain → report
├── pod_tools.py           read-only kubectl diagnostic functions
├── agent_tools.py         LangChain @tool wrappers around pod_tools
├── claude_client.py       sends evidence to Claude and returns the explanation
├── reporting.py           writes the Markdown incident report
├── k8s/
│   ├── demo.yaml          healthy NGINX Deployment
│   └── broken-pod.yaml    pod with a non-existent image (ImagePullBackOff)
├── tests/
│   └── test_pod_tools.py  automated tests (no cluster needed)
└── reports/               generated incident reports
```

| File | Purpose |
|---|---|
| `pod_tools.py` | Runs `kubectl` safely, parses pod JSON, reads logs, events, metrics and description |
| `agent_tools.py` | Describes four diagnostic functions as LangChain tools |
| `claude_client.py` | Builds the prompt, calls Claude, converts API errors into clear messages |
| `reporting.py` | Turns evidence + AI text into a Markdown file |
| `main.py` | Command-line interface and the 5-step investigation workflow |
| `tests/test_pod_tools.py` | Tests healthy, broken, missing pod, missing metrics, invalid names, report content |

---

## 5. The eight phases

| Phase | What we do | Result |
|---|---|---|
| 1 | Prepare RHEL 10, Python, Docker, k3d and kubectl | Local lab ready |
| 2 | Create a Kubernetes cluster and run a sample pod | Real pod running |
| 3 | Create the Python project | Python environment ready |
| 4 | Build simple diagnostic tools | Status, logs, events and metrics |
| 5 | Connect Claude API and LangChain | AI explains collected evidence |
| 6 | Build the investigation flow and report | Controlled, read-only investigation |
| 7 | Test healthy, broken and error scenarios | Tests and troubleshooting |
| 8 | Run against real pods and compare reports | Markdown reports with CPU/RAM/name/namespace |

---

## PHASE 1 — Prepare RHEL 10

**What are we doing?** Installing and checking the basic tools: Python, Docker, kubectl and k3d.

**Why?** k3d runs Kubernetes inside Docker containers, kubectl talks to that cluster, and Python runs our agent.

**Terminal location:** any directory.

### Step 1.1 — Update the system and install basic tools

**Terminal (any directory):**

```bash
sudo dnf update -y
sudo dnf install -y curl git vim tar gzip
```

### Step 1.2 — Install Python tools

**Terminal (any directory):**

```bash
sudo dnf install -y python3 python3-pip python3-devel gcc
python3 --version
```

Expected: `Python 3.12.x` (any Python 3.10 or newer works).

### Step 1.3 — Check Docker

If Docker is not installed, install Docker Engine using the official Docker instructions for RHEL, then return here.

**Terminal (any directory):**

```bash
sudo systemctl enable --now docker
sudo systemctl status docker --no-pager
docker version
docker ps
```

Expected: `Active: active (running)` and `docker ps` prints a table header without errors.

If your user cannot run Docker, use `sudo` or add your user to the `docker` group and sign in again. Note: membership in the `docker` group grants powerful host access.

### Step 1.4 — Install kubectl and k3d

Install the current stable `kubectl` and `k3d` from their official installation pages. Then verify:

**Terminal (any directory):**

```bash
kubectl version --client
k3d version
```

Expected (versions may differ):

```text
Client Version: v1.37.1
k3d version v5.9.0
```

**Troubleshooting**

- `command not found` → finish the official installation, and check that the install folder (for example `/usr/local/bin` or `~/.local/bin`) is in your `PATH`.
- `permission denied ... docker.sock` → use `sudo` or add yourself to the `docker` group.

---

## PHASE 2 — Create the cluster and run a pod

**What are we doing?** Creating a small local Kubernetes cluster and running NGINX as the application we will investigate.

**Why?** The agent must investigate a *real* pod, not fake data.

> This phase changes your system: it creates Docker containers and updates `~/.kube/config`.

### Step 2.1 — Create the k3d cluster

**Terminal (any directory):**

```bash
k3d cluster create pod-lab --agents 1 --servers 1
```

### Step 2.2 — Check the cluster

**Terminal (any directory):**

```bash
kubectl cluster-info
kubectl get nodes
```

Expected:

```text
NAME                   STATUS   ROLES           AGE   VERSION
k3d-pod-lab-agent-0    Ready    <none>          11s   v1.35.5+k3s1
k3d-pod-lab-server-0   Ready    control-plane   17s   v1.35.5+k3s1
```

`kubectl cluster-info` should also list `Metrics-server is running at ...`. k3d (k3s) includes Metrics Server by default, which we need for live CPU/RAM.

### Step 2.3 — Create the namespace

**Terminal (any directory):**

```bash
kubectl create namespace ai-sre-lab
kubectl get namespace ai-sre-lab
```

If it says `AlreadyExists`, that is fine.

### Step 2.4 — Create the sample Deployment

**Terminal:**

```bash
mkdir -p ~/agent/k8s
cd ~/agent
```

A Deployment keeps the NGINX pod running even if it exits. The `resources` section sets the **configured** requests and limits (not actual usage).

**File:** `~/agent/k8s/demo.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-web
  namespace: ai-sre-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-web
  template:
    metadata:
      labels:
        app: demo-web
    spec:
      containers:
        - name: nginx
          image: nginx:stable
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "250m"
              memory: "128Mi"
```

Apply it and wait for the pod.

**Terminal (`~/agent`):**

```bash
kubectl apply -f ~/agent/k8s/demo.yaml
kubectl rollout status deployment/demo-web -n ai-sre-lab
kubectl get pods -n ai-sre-lab -o wide
```

Expected:

```text
deployment "demo-web" successfully rolled out
NAME                       READY   STATUS    RESTARTS   AGE   IP          NODE
demo-web-66d4d546b-2jv7k   1/1     Running   0          50s   10.42.1.4   k3d-pod-lab-agent-0
```

Write down **your** pod name. It starts with `demo-web-` followed by a random suffix that is different on every machine.

**Troubleshooting**

- `connection refused` from kubectl → run `k3d cluster list`; if `pod-lab` is missing, create it again. If it exists but is stopped: `k3d cluster start pod-lab`.
- Pod stuck in `ContainerCreating` → wait; the first image download can take a minute. Check `kubectl describe pod -n ai-sre-lab <pod>`.

---

## PHASE 3 — Create the Python project

**What are we doing?** Creating the project folders, a virtual environment, and the configuration files.

**Why?** A virtual environment keeps this project's packages separate from the system Python. `.env` keeps secrets out of the code.

### Step 3.1 — Create folders and the virtual environment

**Terminal:**

```bash
mkdir -p ~/agent/reports ~/agent/tests
cd ~/agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

After `source .venv/bin/activate` your prompt starts with `(.venv)`. Activate it again in every new terminal.

### Step 3.2 — requirements.txt

**File:** `~/agent/requirements.txt`

```text
anthropic
langchain-core
python-dotenv
pytest
```

| Package | Why we need it |
|---|---|
| `anthropic` | Official Python SDK for the Claude API |
| `langchain-core` | The `@tool` decorator for our diagnostic tools |
| `python-dotenv` | Loads settings from `.env` |
| `pytest` | Runs the automated tests |

**Terminal (`~/agent`, venv active):**

```bash
pip install -r requirements.txt
pip list | grep -iE "^(anthropic|langchain-core|python-dotenv|pytest) "
```

### Step 3.3 — .gitignore

**File:** `~/agent/.gitignore`

```text
.venv/
.env
__pycache__/
.pytest_cache/
reports/*.md
```

This stops Git from saving your virtual environment, your secret `.env`, Python caches, and generated reports.

### Step 3.4 — Configure the Claude API key

Create an API key in your Anthropic Console account. Keep it private: never paste it into a chat, screenshot, README, or Git repository.

The project ships a template with placeholders only:

**File:** `~/agent/.env.example`

```text
ANTHROPIC_API_KEY=replace_with_your_real_key
ANTHROPIC_MODEL=claude-opus-5-5
K8S_NAMESPACE=ai-sre-lab
REPORT_DIR=reports
```

Copy it to `.env`, make it private, then edit it:

**Terminal (`~/agent`):**

```bash
cp .env.example .env
chmod 600 .env
vim .env
```

In `.env`, replace `replace_with_your_real_key` with your real key. Keep the other lines.

| Setting | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Your secret Claude API key |
| `ANTHROPIC_MODEL` | Claude model to use (`claude-opus-5-5`). If your account cannot use it, put another currently available Claude model name here |
| `K8S_NAMESPACE` | Default namespace for the diagnostic functions |
| `REPORT_DIR` | Folder where reports are saved |

> The original manual used `claude-3-5-sonnet-latest`. That model is retired, so this project uses a current model name.

Without a valid key the program still works: reports are created and the AI section says *"AI explanation unavailable"*.

### Step 3.5 — pytest.ini

**File:** `~/agent/pytest.ini`

```ini
[pytest]
pythonpath = .
```

This tells pytest to import `pod_tools`, `main` and the other modules from the project folder when the tests in `tests/` run.

---

## PHASE 4 — Build the diagnostic tools

**What are we doing?** Writing simple Python functions that read real Kubernetes information through `kubectl`.

**Why?** `kubectl` is already configured to talk to the k3d cluster, so it is the simplest reliable source of facts.

### Step 4.1 — pod_tools.py

**File:** `~/agent/pod_tools.py`

```python
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
```

**Explanation in simple English**

- `run_kubectl(args)` — runs `kubectl` with a **list** of arguments (never a shell string), so names cannot inject extra commands. It returns `{"ok": True, "output": ...}` or `{"ok": False, "error": ...}` and never crashes on timeouts or a missing `kubectl`.
- `list_pods()` — returns the pod names in a namespace; `main.py` uses it to let you pick a pod.
- `get_pod_status()` — reads the pod JSON and keeps the useful parts: phase, node, IP, creation time, labels, readiness, restart count, waiting reason (for example `ImagePullBackOff`), and owner.
- `get_configured_resources()` — reads CPU/memory **requests and limits** from the pod spec. These are settings, not measurements.
- `get_pod_logs()` — last 80 log lines from all containers.
- `get_pod_events()` — Kubernetes events for this pod, oldest first.
- `get_pod_metrics()` — **actual** CPU/RAM from `kubectl top pod --containers`. If it fails, it returns `"Unavailable"` plus the reason.
- `get_pod_description()` — full `kubectl describe pod` output.
- `collect_pod_evidence()` — calls all of the above and adds a UTC timestamp.

Every command is read-only (`get`, `logs`, `top`, `describe`).

### Step 4.2 — Test the same commands manually

**Terminal (any directory):**

```bash
kubectl get pods -n ai-sre-lab
kubectl top pod -n ai-sre-lab
kubectl describe pod -n ai-sre-lab
```

Expected for `kubectl top` (numbers will differ):

```text
NAME                       CPU(cores)   MEMORY(bytes)
demo-web-66d4d546b-2jv7k   0m           4Mi
```

`0m` CPU is normal for an idle NGINX: it means less than one millicore.

Quick Python check.

**Terminal (`~/agent`, venv active):**

```bash
python -c "import pod_tools as p; print(p.list_pods()); print(p.get_pod_status('pod-that-does-not-exist'))"
```

Expected: your pod list, then `{'ok': False, 'error': 'Error from server (NotFound): pods "pod-that-does-not-exist" not found'}`.

### Step 4.3 — Enable and check CPU/RAM metrics

k3d normally includes Metrics Server. Check it:

**Terminal (any directory):**

```bash
kubectl -n kube-system get deployment metrics-server
kubectl top pod -n ai-sre-lab
```

If `metrics-server` is **not found**, install the official manifest (this downloads a live upstream file):

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system rollout status deployment/metrics-server --timeout=120s
kubectl top pod -n ai-sre-lab
```

If Metrics Server cannot scrape the kubelet because of certificate verification errors, do not silently ignore it. On a **disposable local lab cluster only**, you can add `--kubelet-insecure-tls` to the metrics-server container arguments. This weakens kubelet certificate checks and must never be copied to production:

```bash
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n kube-system rollout status deployment/metrics-server --timeout=120s
```

**Troubleshooting**

- `error: Metrics API not available` → Metrics Server is missing or not ready; wait 30–60 seconds after it starts.
- `pods "<name>" not found` from `kubectl top` for a pod that exists → that pod has no metrics yet (for example, its container never started). The report marks CPU/RAM as unavailable.

---

## PHASE 5 — Connect Claude and LangChain

**What are we doing?** Sending the collected evidence to Claude and wrapping our diagnostic functions as LangChain tools.

**Why?** Claude turns raw `kubectl` output into a readable explanation. We give Claude the real tool output, so it does not need to guess.

### Step 5.1 — claude_client.py

**File:** `~/agent/claude_client.py`

```python
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

PLACEHOLDER_KEY = "replace_with_your_real_key"


def build_prompt(evidence):
    return f"""
You are a careful DevOps incident investigator.
Use only the evidence below. Do not invent CPU, RAM, timestamps, or events.
"metrics" is live usage from kubectl top. "configured_resources" are requests
and limits from the pod spec. Never present a request or limit as actual usage.
If CPU/RAM metrics are unavailable, say so.

Write these sections in Markdown:
1. Incident summary
2. Confirmed observations (facts directly visible in the evidence)
3. Possible causes (hypotheses, clearly labelled as not yet confirmed)
4. Recommended next checks (read-only commands first)
5. Confidence level (low, medium, or high) and why

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
```

**Explanation in simple English**

- The key and model are read from `.env`. They are never written in the code or printed.
- If the key is missing or still the placeholder, the function returns a clear message and **does not call the API**.
- `build_prompt()` tells Claude to use **only** the evidence, never invent CPU/RAM, keep requests/limits separate from usage, and split *confirmed observations* from *possible causes*.
- API errors (bad key, unknown model, rate limit, network problem) become one-line messages. The report is still created.
- If Claude declines the request (`stop_reason == "refusal"`), we say so instead of printing an empty answer.
- `max_tokens=8000` gives the current models room to think and answer fully.

### Step 5.2 — agent_tools.py (LangChain tools)

**File:** `~/agent/agent_tools.py`

```python
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
```

**Explanation in simple English**

- `@tool` turns each function into a LangChain tool with a name, a description (the docstring), and typed inputs.
- You run a tool with `.invoke({...})`, for example `inspect_pod.invoke({"pod_name": "...", "namespace": "ai-sre-lab"})`.
- In this beginner version **our Python code** calls the tools in a fixed order. The model is never given direct shell access.

**Quick check — Terminal (`~/agent`, venv active):**

```bash
python -c "from agent_tools import inspect_pod; print(inspect_pod.name, '-', inspect_pod.description)"
python -c "from claude_client import explain_incident; print(explain_incident({}))"
```

Expected (without a real key): the tool name and description, then `AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env. ...`

---

## PHASE 6 — Build the investigation and report workflow

### Step 6.1 — reporting.py

**What are we doing?** Writing the Markdown report from real evidence.

**File:** `~/agent/reporting.py`

```python
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
```

**Explanation in simple English**

- `safe_filename()` replaces unusual characters so the file name is always safe.
- The report is saved as `reports/incident_<namespace>_<pod>_<YYYYmmdd_HHMMSS>.md`.
- **Actual CPU and RAM usage** is copied directly from `kubectl top`. If metrics failed, it says `Unavailable` and shows the reason from Kubernetes.
- **Configured CPU and RAM** is a separate table built from the pod spec's requests and limits.
- Container state, events, logs and `kubectl describe` follow, then Claude's explanation and a limitations section confirming that nothing was changed.

### Step 6.2 — main.py

**What are we doing?** Creating the entry point that controls the whole investigation.

**File:** `~/agent/main.py`

```python
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
        description="Investigate a Kubernetes pod and create a Markdown report."
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

    print("\n[5/5] Collecting full evidence and asking Claude for an explanation...")
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
```

**Explanation in simple English**

- `validate_name()` only accepts valid Kubernetes names (lowercase letters, numbers, `-` and `.`, max 253 characters). Anything else stops the program before any command runs.
- `choose_pod()` runs when you leave out `--pod`: it lists the pods and lets you type a number or a name.
- Step 1 checks the pod. If it does not exist, the program prints the Kubernetes error and exits with code 1, **without creating a misleading report**.
- Steps 2–4 show logs, events and CPU/RAM on screen using the LangChain tools.
- Step 5 collects all evidence, asks Claude for an explanation, and saves the report.

**Safety note:** this version is read-only. It investigates and reports but never restarts or deletes a pod.

---

## PHASE 7 — Test the project

**What are we doing?** Testing normal and error situations before the live demo.

**Why?** Tests prove the important behaviours (correct pod name/namespace in the report, honest missing metrics, clean handling of missing or invalid pods) without needing a running cluster.

### Step 7.1 — tests/test_pod_tools.py

The tests replace `run_kubectl` with a fake function (`monkeypatch`), so they do not need Kubernetes or an API key.

**File:** `~/agent/tests/test_pod_tools.py`

```python
import json
import sys

import pytest

import claude_client
import main
import pod_tools
from pod_tools import get_pod_metrics, get_pod_status
from reporting import create_markdown_report


def fake_pod_json(name, phase, ready, waiting_reason=None):
    """Build a small pod JSON like `kubectl get pod -o json` returns."""
    state = {"running": {"startedAt": "2026-10-30T00:00:00Z"}}
    if waiting_reason:
        state = {"waiting": {"reason": waiting_reason}}
    pod = {
        "metadata": {
            "name": name,
            "namespace": "ai-sre-lab",
            "creationTimestamp": "2026-10-30T00:00:00Z",
            "labels": {"app": name},
        },
        "spec": {
            "nodeName": "k3d-pod-lab-agent-0",
            "containers": [{
                "name": "web",
                "image": "nginx:stable",
                "resources": {
                    "requests": {"cpu": "50m", "memory": "64Mi"},
                    "limits": {"cpu": "250m", "memory": "128Mi"},
                },
            }],
        },
        "status": {
            "phase": phase,
            "podIP": "10.42.0.10",
            "containerStatuses": [{
                "name": "web", "ready": ready, "restartCount": 0, "state": state
            }],
        },
    }
    return json.dumps(pod)


# ---------- Tests from the manual ----------

def test_metrics_error_is_reported(monkeypatch):
    monkeypatch.setattr(
        pod_tools,
        "run_kubectl",
        lambda args, timeout=20: {"ok": False, "error": "metrics unavailable"}
    )
    result = get_pod_metrics("demo-web-abc", "ai-sre-lab")
    assert result["ok"] is False
    assert result["cpu_ram"] == "Unavailable"
    assert "metrics unavailable" in result["error"]


def test_report_contains_pod_identity_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {
            "phase": "Running",
            "node": "k3d-pod-lab-agent-0",
            "pod_ip": "10.42.0.10",
            "created": "2026-10-30T00:00:00Z",
            "containers": [{"name": "nginx", "ready": True, "restart_count": 0}]
        },
        "metrics": {"ok": True, "cpu_ram": "nginx 2m 12Mi"},
        "events": {"ok": True, "events": "No events"},
        "logs": {"ok": True, "logs": "nginx started"},
        "description": {"ok": True, "description": "Pod description"}
    }
    path = create_markdown_report(
        "demo-web-abc", "ai-sre-lab", evidence, "No issue observed."
    )
    content = open(path, encoding="utf-8").read()
    assert "demo-web-abc" in content
    assert "ai-sre-lab" in content
    assert "nginx 2m 12Mi" in content
    assert "No issue observed." in content


def test_report_marks_missing_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {"phase": "Running", "node": "node-1"},
        "metrics": {"ok": False, "cpu_ram": "Unavailable", "note": "Metrics Server missing"},
        "events": {"events": "Unavailable"},
        "logs": {"logs": "Unavailable"},
        "description": {"description": "Unavailable"}
    }
    path = create_markdown_report(
        "demo-web-abc", "ai-sre-lab", evidence, "Metrics not available."
    )
    content = open(path, encoding="utf-8").read()
    assert "Unavailable" in content
    assert "Metrics Server missing" in content
    assert "Live metrics could not be retrieved" in content


# ---------- Extra tests ----------

def test_healthy_pod_status_is_parsed(monkeypatch):
    output = fake_pod_json("demo-web-abc", "Running", ready=True)
    monkeypatch.setattr(
        pod_tools, "run_kubectl", lambda args, timeout=20: {"ok": True, "output": output}
    )
    status = get_pod_status("demo-web-abc", "ai-sre-lab")
    assert status["ok"] is True
    assert status["name"] == "demo-web-abc"
    assert status["namespace"] == "ai-sre-lab"
    assert status["phase"] == "Running"
    assert status["containers"][0]["ready"] is True
    assert status["configured_resources"][0]["cpu_limit"] == "250m"


def test_broken_pod_status_shows_waiting_reason(monkeypatch):
    output = fake_pod_json("broken-image-demo", "Pending", ready=False,
                           waiting_reason="ImagePullBackOff")
    monkeypatch.setattr(
        pod_tools, "run_kubectl", lambda args, timeout=20: {"ok": True, "output": output}
    )
    status = get_pod_status("broken-image-demo", "ai-sre-lab")
    assert status["phase"] == "Pending"
    assert status["containers"][0]["ready"] is False
    assert status["containers"][0]["waiting_reason"] == "ImagePullBackOff"


def test_missing_pod_returns_error(monkeypatch):
    monkeypatch.setattr(
        pod_tools, "run_kubectl",
        lambda args, timeout=20: {"ok": False, "error": 'pods "ghost" not found'}
    )
    status = get_pod_status("ghost", "ai-sre-lab")
    assert status["ok"] is False
    assert "not found" in status["error"]


def test_missing_pod_does_not_create_report(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(
        pod_tools, "run_kubectl",
        lambda args, timeout=20: {"ok": False, "error": 'pods "ghost" not found'}
    )
    monkeypatch.setattr(sys, "argv", ["main.py", "--pod", "ghost"])
    with pytest.raises(SystemExit):
        main.main()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad_name", ["", "Bad_Name", "pod;rm -rf", "-starts-with-dash"])
def test_invalid_names_are_rejected(bad_name):
    with pytest.raises(ValueError):
        main.validate_name(bad_name, "pod name")


def test_report_separates_usage_from_configured_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {
            "phase": "Running",
            "configured_resources": [{
                "container": "nginx", "image": "nginx:stable",
                "cpu_request": "50m", "cpu_limit": "250m",
                "memory_request": "64Mi", "memory_limit": "128Mi",
            }],
        },
        "metrics": {"ok": True, "cpu_ram": "nginx 1m 5Mi"},
    }
    path = create_markdown_report("demo-web-abc", "ai-sre-lab", evidence, "OK")
    content = open(path, encoding="utf-8").read()
    assert "Actual CPU and RAM usage" in content
    assert "Configured CPU and RAM" in content
    assert "| nginx | 50m | 250m | 64Mi | 128Mi |" in content


def test_missing_api_key_gives_clear_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "replace_with_your_real_key")
    message = claude_client.explain_incident({"pod": {}})
    assert "AI explanation unavailable" in message
```

| Test | What it proves |
|---|---|
| `test_metrics_error_is_reported` | A metrics failure becomes `Unavailable` plus the error |
| `test_report_contains_pod_identity_and_metrics` | The report has the correct pod name, namespace, metrics and AI text |
| `test_report_marks_missing_metrics` | Missing metrics are clearly marked, never invented |
| `test_healthy_pod_status_is_parsed` | A Running, ready pod is read correctly, including limits |
| `test_broken_pod_status_shows_waiting_reason` | A Pending pod shows `ImagePullBackOff` |
| `test_missing_pod_returns_error` | A missing pod returns a clear error |
| `test_missing_pod_does_not_create_report` | The full program exits and writes **no** report for a missing pod |
| `test_invalid_names_are_rejected` (4 cases) | Empty, uppercase, shell characters and a leading dash are rejected |
| `test_report_separates_usage_from_configured_limits` | Actual usage and requests/limits appear in separate sections |
| `test_missing_api_key_gives_clear_message` | No API key gives a clear message instead of a crash |

### Step 7.2 — Run the automated tests

**Terminal (`~/agent`, venv active):**

```bash
cd ~/agent
source .venv/bin/activate
pytest -v
```

Expected:

```text
collected 13 items
...
============================== 13 passed ==============================
```

If a test fails, read the first traceback line that points to one of your project files, fix it, and run `pytest -v` again.

### Step 7.3 — Test a missing pod and an invalid name

**Terminal (`~/agent`, venv active):**

```bash
python main.py --pod pod-that-does-not-exist --namespace ai-sre-lab
echo "exit code: $?"
python main.py --pod 'Bad_Name;rm'
```

Expected:

```text
[1/5] Checking pod status with LangChain tool...
Could not inspect pod: Error from server (NotFound): pods "pod-that-does-not-exist" not found
Check the pod name and namespace using: kubectl get pods -n ai-sre-lab
exit code: 1
Invalid pod name: 'Bad_Name;rm'
Names may only use lowercase letters, numbers, '-' and '.'.
```

No report file is created for either command.

### Step 7.4 — Create a controlled broken pod

This pod asks for an image tag that does not exist, so Kubernetes cannot pull it. It does not touch the healthy Deployment.

**File:** `~/agent/k8s/broken-pod.yaml`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: broken-image-demo
  namespace: ai-sre-lab
  labels:
    app: broken-image-demo
spec:
  containers:
    - name: web
      image: nginx:tag-that-does-not-exist
```

**Terminal (`~/agent`):**

```bash
kubectl apply -f ~/agent/k8s/broken-pod.yaml
kubectl get pod broken-image-demo -n ai-sre-lab -w
```

Wait until `STATUS` shows `ErrImagePull` or `ImagePullBackOff`, then press **Ctrl+C**.

### Troubleshooting checklist

| Problem | What to do |
|---|---|
| kubectl cannot connect | `kubectl get nodes`, `k3d cluster list`, `k3d cluster start pod-lab` |
| Pod name not found | `kubectl get pods -n ai-sre-lab` and copy the exact name |
| Logs unavailable | The container never started; a failed image pull has events but no logs |
| `kubectl top` fails | Check `kubectl -n kube-system get deployment metrics-server`, wait for metrics |
| Claude API fails | Check the key, model name, network access and quota; the report is still created with an AI-unavailable note |
| `ModuleNotFoundError` | `source .venv/bin/activate` and `pip install -r requirements.txt` |
| pytest cannot import `pod_tools` | Run pytest from `~/agent`, where `pytest.ini` lives |

---

## PHASE 8 — Run a pod and generate a real incident report

**What are we doing?** Running the agent against real pods in the k3d cluster.

### Step 8.1 — Make sure a pod is running

**Terminal (any directory):**

```bash
kubectl get pods -n ai-sre-lab -o wide
kubectl rollout status deployment/demo-web -n ai-sre-lab
```

### Step 8.2 — Run the agent for the healthy pod

**Option A — choose from a list.**

**Terminal (`~/agent`, venv active):**

```bash
cd ~/agent
source .venv/bin/activate
python main.py
```

Expected:

```text
Pods in namespace ai-sre-lab:
  1. broken-image-demo
  2. demo-web-66d4d546b-2jv7k
Enter a number or the exact pod name: 2
```

**Option B — type the exact name.** Replace `<REAL_POD_NAME>` with your pod name:

```bash
python main.py --pod <REAL_POD_NAME> --namespace ai-sre-lab
```

Either way the terminal shows five stages and ends with the report path:

```text
Investigating pod demo-web-66d4d546b-2jv7k in namespace ai-sre-lab (read-only).

[1/5] Checking pod status with LangChain tool...
[2/5] Reading logs with LangChain tool...
[3/5] Reading events with LangChain tool...
[4/5] Reading CPU/RAM with LangChain tool...
[5/5] Collecting full evidence and asking Claude for an explanation...

Report created successfully:
reports/incident_ai-sre-lab_demo-web-66d4d546b-2jv7k_20261030_033241.md
```

### Step 8.3 — Open and inspect the report

**Terminal (`~/agent`):**

```bash
ls -lh ~/agent/reports
cat <path printed by the program>
```

Example from a real run (healthy pod):

```markdown
- **Pod name:** demo-web-66d4d546b-2jv7k
- **Namespace:** ai-sre-lab
- **Status:** Running
- **Node:** k3d-pod-lab-agent-0

## Actual CPU and RAM usage (live, from kubectl top)
POD                        NAME    CPU(cores)   MEMORY(bytes)
demo-web-66d4d546b-2jv7k   nginx   0m           4Mi

## Configured CPU and RAM (requests and limits from the pod spec)
| nginx | 50m | 250m | 64Mi | 128Mi |
```

The report should contain:

- Pod name and namespace.
- Phase, node, pod IP, creation time, container readiness and restart counts.
- Live CPU and memory usage from `kubectl top`, or an honest `Unavailable` message.
- Configured requests and limits in a separate table.
- Recent events and logs.
- Claude's investigation: summary, confirmed observations, possible causes, next checks, confidence.
- A note confirming the tool did not change the cluster.

### Step 8.4 — Generate a report for the broken pod

**Terminal (`~/agent`, venv active):**

```bash
python main.py --pod broken-image-demo --namespace ai-sre-lab
```

Expected findings (from a real run):

```text
- **Status:** Pending
## Actual CPU and RAM usage (live, from kubectl top)
Unavailable
**Live metrics could not be retrieved.** ...
Kubernetes said: `Error from server (NotFound): pods "broken-image-demo" not found`

## Kubernetes events
Warning   Failed   ...   Error: ImagePullBackOff
Warning   Failed   ...   Failed to pull image "nginx:tag-that-does-not-exist": ... not found

## Recent logs
Error from server (BadRequest): container "web" in pod "broken-image-demo" is waiting to start: trying and failing to pull image
```

`kubectl top` says *not found* because Metrics Server has no data for a container that never started. The pod itself exists. The report states this instead of inventing numbers.

### Step 8.5 — Compare the two reports

| Check | Healthy pod | Broken image pod |
|---|---|---|
| Pod name / namespace | `demo-web-…` / ai-sre-lab | `broken-image-demo` / ai-sre-lab |
| Status | Running, ready, 0 restarts | Pending, not ready, `ImagePullBackOff` |
| Actual CPU / RAM | Real values (e.g. `0m` / `4Mi`) | Unavailable (container never started) |
| Configured resources | 50m/250m CPU, 64Mi/128Mi memory | Not set |
| Evidence | Logs, `Scheduled`/`Pulled`/`Started` events | Image-pull failure events, no logs |
| AI conclusion | Pod looks healthy | Likely wrong image tag, backed by events |

Quick automatic check that both reports exist and contain the right identity.

**Terminal (`~/agent`):**

```bash
grep -l "Namespace:\*\* ai-sre-lab" reports/*.md
grep -H -E "Pod name|Status" reports/*.md
```

### Step 8.6 — Clean up the broken test pod

**Terminal (any directory):**

```bash
kubectl delete pod broken-image-demo -n ai-sre-lab
```

This deletes only the deliberately broken test pod. The healthy Deployment keeps running.

---

## 6. Running the project — quick reference

**Terminal (`~/agent`):**

```bash
cd ~/agent
source .venv/bin/activate
pytest -v                                                  # run tests
python main.py                                             # choose a pod from a list
python main.py --pod <REAL_POD_NAME> --namespace ai-sre-lab   # investigate one pod
ls -lh reports/                                            # see reports
```

---

## 7. Troubleshooting common errors

| Error message | Cause | Fix |
|---|---|---|
| `kubectl was not found` | kubectl missing from `PATH` | Install kubectl, check `which kubectl` |
| `connection refused` / `Unable to connect to the server` | Cluster stopped or kubeconfig points to an old cluster | `k3d cluster list`, `k3d cluster start pod-lab`, `kubectl config use-context k3d-pod-lab` |
| `Invalid pod name: ...` | Name has uppercase, spaces or symbols | Copy the exact name from `kubectl get pods -n ai-sre-lab` |
| `Could not inspect pod: ... not found` | Wrong name or namespace | Check both with `kubectl get pods -A` |
| CPU/RAM `Unavailable` for a running pod | Metrics Server missing or still starting | Phase 4, Step 4.3; wait 60 seconds and retry |
| `AI explanation unavailable: set a valid ANTHROPIC_API_KEY` | Placeholder key in `.env` | Put your real key in `.env` |
| `AI explanation unavailable: the API key was rejected` | Wrong or revoked key | Create a new key in the Anthropic Console |
| `AI explanation unavailable: model ... was not found` | Model name not available to your account | Change `ANTHROPIC_MODEL` in `.env` |
| `AI explanation unavailable: rate limit or quota reached` | Too many requests or no credit | Wait, or check your account billing |
| `AI explanation unavailable: could not connect` | No internet or a proxy blocks the API | Check network/firewall access to `api.anthropic.com` |
| `ModuleNotFoundError: No module named 'anthropic'` | venv not active | `source .venv/bin/activate` |

---

## 8. Cleanup

**Terminal (any directory):**

```bash
# Remove only the broken test pod
kubectl delete pod broken-image-demo -n ai-sre-lab

# Remove the whole lab namespace (healthy Deployment too)
kubectl delete namespace ai-sre-lab

# Delete the entire local cluster (removes its Docker containers)
k3d cluster delete pod-lab
```

To remove the Python environment: `rm -rf ~/agent/.venv` (recreate it with Phase 3).

---

## 9. Final project checklist

- [ ] RHEL 10 lab and k3d cluster `pod-lab` are working (`kubectl get nodes`).
- [ ] The healthy NGINX Deployment is running in `ai-sre-lab`.
- [ ] The Python virtual environment and packages are installed.
- [ ] Diagnostic tools read pod status, logs, events and metrics.
- [ ] Claude explanation works, or the report clearly says why AI was unavailable.
- [ ] `pytest -v` shows 13 passed.
- [ ] A report for the healthy pod is saved in `reports/`.
- [ ] A report for `broken-image-demo` is saved in `reports/`.
- [ ] Each report includes pod name, namespace, and real CPU/RAM or an honest unavailable message.
- [ ] Actual usage and configured requests/limits are in separate sections.
- [ ] No automatic restart, deletion or other remediation happens.
- [ ] `.env` is not tracked by Git (`git check-ignore .env` prints `.env`).

## 10. Deliverables

- Python source: `pod_tools.py`, `agent_tools.py`, `claude_client.py`, `reporting.py`, `main.py`
- Kubernetes YAML: `k8s/demo.yaml`, `k8s/broken-pod.yaml`
- Configuration template: `.env.example` (real key only in your private `.env`)
- Tests: `tests/test_pod_tools.py` and the `pytest -v` output
- Markdown incident reports in `reports/`
- One repeatable command:

```bash
python main.py --pod <REAL_POD_NAME> --namespace ai-sre-lab
```

> The AI is an assistant to the investigation, not a replacement for evidence. Kubernetes supplies the facts; the program records them; Claude explains them; you decide what to do next.
