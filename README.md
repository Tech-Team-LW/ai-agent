# AI-Powered Kubernetes Incident Investigation Agent

**A complete implementation guide: RHEL 10 · k3d · Kubernetes · Python · LangChain · Claude API · pytest**

This guide explains **what** we are building and **how** we build it, from an empty RHEL 10 machine to a working agent that investigates a Kubernetes Pod and writes a Markdown incident report.

Everything in this README is based on the actual files in this project. Where the project and the original manual (`agent/manual.docs`) are different, this README follows the **current code** and says so clearly. See [Appendix A](#appendix-a--differences-between-manualdocs-and-the-current-code) and [Appendix B](#appendix-b--known-gaps-and-items-not-implemented).

**How the outputs in this guide were produced:** The cluster, HTTPD application, agent runs, and reports shown in Phases 2 and 8 were recorded from a real run of this project on RHEL 10.0 (k3d v5.9.0, k3s v1.35.5, Python 3.12.9) on 30–31 October 2026. Pod names, IPs, ages, and timestamps will be different on your machine. Outputs marked **illustrative** were not recorded and only show the expected shape. The first recorded runs had no Claude API key configured, so those reports show the "AI explanation unavailable" message. The runs were then repeated with a valid key, and Phases 6 and 8 include Claude's real (shortened) analysis.

---

## Table of Contents

- [Part 1 — What Are We Building?](#part-1--what-are-we-building)
- [Part 2 — The Technologies and Why We Need Them](#part-2--the-technologies-and-why-we-need-them)
- [Part 3 — Architecture: How the Pieces Work Together](#part-3--architecture-how-the-pieces-work-together)
- [Part 4 — Project Folder Structure](#part-4--project-folder-structure)
- [Phase 1 — Prepare the RHEL 10 Environment](#phase-1--prepare-the-rhel-10-environment)
- [Phase 2 — Create the Kubernetes Cluster](#phase-2--create-the-kubernetes-cluster)
- [Phase 3 — Create the Python Project](#phase-3--create-the-python-project)
- [Phase 4 — Build the Kubernetes Diagnostic Tools](#phase-4--build-the-kubernetes-diagnostic-tools)
- [Phase 5 — Connect the Agent with Claude AI](#phase-5--connect-the-agent-with-claude-ai)
- [Phase 6 — Generate the Incident and RCA Report](#phase-6--generate-the-incident-and-rca-report)
- [Phase 7 — Connect Everything Through main.py](#phase-7--connect-everything-through-mainpy)
- [Phase 8 — Testing and Real Incident Investigation](#phase-8--testing-and-real-incident-investigation)
- [Troubleshooting](#troubleshooting)
- [Security and Project Limitations](#security-and-project-limitations)
- [Quick Reference](#quick-reference)
- [Appendix A — Differences Between manual.docs and the Current Code](#appendix-a--differences-between-manualdocs-and-the-current-code)
- [Appendix B — Known Gaps and Items Not Implemented](#appendix-b--known-gaps-and-items-not-implemented)

---

## Part 1 — What Are We Building?

### The problem

In Kubernetes, applications run inside containers. Containers run inside **Pods**. A Pod is the smallest unit that Kubernetes schedules and manages.

Sometimes a Pod fails. Common reasons include:

- **Incorrect container image.** The image name or tag does not exist.
- **`ErrImagePull` / `ImagePullBackOff`.** Kubernetes cannot download the image, so it keeps retrying with a delay.
- **`CrashLoopBackOff`.** The container starts, crashes, and Kubernetes keeps restarting it.
- **Application errors.** The program inside the container prints errors or exits.
- **Resource problems.** The Pod cannot be scheduled because the cluster lacks CPU or memory, or the container uses more memory than its limit.
- **Configuration problems.** Wrong ports, missing settings, wrong labels, and similar mistakes.

To find the cause, a DevOps engineer usually runs several commands one after another:

```bash
kubectl get pod <pod> -n <namespace>
kubectl describe pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace>
kubectl get events -n <namespace>
kubectl top pod <pod> -n <namespace>
```

Then the engineer reads all the output, connects the facts, and writes a summary. This takes time and is easy to do inconsistently.

### The solution

We build a **Python-based agent** that automates this investigation. With one command, the agent:

1. Connects to a Kubernetes cluster using Python and `kubectl`.
2. Collects Pod information (phase, node, IP, labels, owner).
3. Checks Pod and container status (ready, restart count, waiting reason, and the previous container's exit reason).
4. Collects container logs, including logs from the previous run of a crashed container.
5. Reads Kubernetes events for the Pod, with absolute timestamps.
6. Collects live CPU and RAM usage when Kubernetes metrics are available.
7. Reads the configured CPU and memory requests and limits from the Pod spec.
8. Sends all the collected evidence to Claude AI.
9. Asks Claude to write a **Root Cause Analysis (RCA)**: summary, impact, timeline, confirmed observations, root cause, contributing factors, five whys, corrective and preventive actions, verification steps, and confidence level.
10. Generates a detailed Markdown incident and RCA report.
11. Saves the report in the project's `reports/` directory.

### What the agent does **not** do

This is a **read-only investigation system**.

- It does **not** restart, delete, scale, patch, or repair any Kubernetes resource.
- It does **not** perform automatic remediation or "self-healing".
- It only runs read-only `kubectl` commands: `get`, `logs`, `top`, and `describe`.

Claude's analysis is **advisory**. A human engineer must review the report and decide what to change.

### One-line summary

> Kubernetes supplies the facts. Python collects and records them. Claude writes the root cause analysis from them. You decide what to do next.

---

## Part 2 — The Technologies and Why We Need Them

Each technology below is explained in four parts: what it is, why we need it, how it works here, and where we use it.

### RHEL 10 (Red Hat Enterprise Linux 10)

- **What it is:** An enterprise Linux operating system from Red Hat.
- **Why we need it:** It is a stable, common server platform in companies. Building the lab on RHEL makes the skills directly useful at work.
- **How it works here:** It is the host machine. Docker, k3d, kubectl, and Python all run on it. Packages are installed with `dnf`.
- **Where we use it:** Phase 1 (environment setup). Every terminal command in this guide runs on the RHEL 10 host.

### Docker

- **What it is:** A container engine. It runs applications in isolated containers.
- **Why we need it:** k3d does not install Kubernetes directly on your machine. It runs each Kubernetes node as a Docker container. Without Docker, k3d cannot work.
- **How it works here:** When you create a k3d cluster, Docker starts containers such as `k3d-pod-lab-server-0` and `k3d-pod-lab-agent-0`. Each one is a Kubernetes node.
- **Where we use it:** Phase 1 (install) and Phase 2 (cluster runs inside Docker).

### Kubernetes

- **What it is:** A container orchestration platform. It schedules Pods onto nodes, restarts failed containers, and manages Deployments and Services.
- **Why we need it:** It is the system we investigate. Pods, events, logs, and metrics all come from Kubernetes.
- **How it works here:** A small local cluster runs a healthy Apache HTTPD web server (Deployment + Service) and a deliberately broken Pod.
- **Where we use it:** Phases 2, 4, and 8.

### k3d and k3s

- **What it is:** **k3s** is a lightweight, certified Kubernetes distribution. **k3d** is a tool that runs k3s inside Docker containers.
- **Why we need it:** It gives us a real multi-node Kubernetes cluster on one machine in about a minute, without virtual machines or cloud accounts.
- **How it works here:** `k3d cluster create pod-lab --agents 1 --servers 1` creates one control-plane node (server) and one worker node (agent), both as Docker containers. k3d also updates your kubeconfig so `kubectl` can reach the cluster. k3s includes Metrics Server by default, which is what makes `kubectl top` work.
- **Where we use it:** Phase 2.

### kubectl

- **What it is:** The official Kubernetes command-line client.
- **Why we need it:** Our Python code does not use a Kubernetes client library. It runs `kubectl` as a subprocess. `kubectl` already knows how to authenticate to the cluster (through `~/.kube/config`), so Python does not need to handle certificates or tokens.
- **How it works here:** `pod_tools.py` builds commands such as `kubectl get pod <name> -n <ns> -o json` and reads the output.
- **Where we use it:** Phase 1 (install), Phase 2 (cluster checks), Phase 4 (Python calls it), Phase 8 (manual verification).

### Python

- **What it is:** A general-purpose programming language.
- **Why we need it:** It is easy to read, has excellent libraries for AI and automation, and is widely used in DevOps.
- **How it works here:** All agent logic is in Python files: data collection, Claude calls, report writing, and the command-line entry point.
- **Where we use it:** Phases 3 to 8. The project was tested with Python 3.12.9.

### Python virtual environment (`venv`)

- **What it is:** A private folder (`.venv/`) that holds this project's Python packages.
- **Why we need it:** It keeps project packages separate from the system Python. This avoids version conflicts and avoids changing system packages with `sudo pip`.
- **How it works here:** `python3 -m venv .venv` creates it. `source .venv/bin/activate` makes `python` and `pip` point to it.
- **Where we use it:** Phase 3 onward. Always activate it before running the agent or tests.

### Claude AI and the Claude API

- **What it is:** Claude is a large language model built by Anthropic. The **Claude API** is the HTTPS interface that lets programs send text to Claude and receive a response. The `anthropic` Python package is the official client for this API.
- **Why we need it:** Raw Kubernetes output is long and technical. Claude reads all the evidence together and writes a structured Root Cause Analysis: summary, impact, timeline, confirmed observations, root cause, five whys, corrective and preventive actions, and confidence level.
- **How it works here:** `claude_client.py` builds a prompt that contains strict rules and the evidence as JSON. It calls `client.messages.create(...)` and returns Claude's text.
- **Where we use it:** Phase 5. An API key and a model ID are required (set in `.env`).

### LangChain (`langchain-core`)

- **What it is:** A framework for building applications with language models. `langchain-core` contains its basic building blocks, including the **tool** abstraction.
- **Why we need it:** LangChain gives Python functions a standard "tool" format: a name, a description, and typed input arguments. This is the format AI agents use to describe their capabilities. It prepares the project for a future version where a model could choose tools.
- **How it works here:** `agent_tools.py` wraps four diagnostic functions with the `@tool` decorator. `main.py` calls these tools with `.invoke(...)` in a **fixed order**. In this version, Claude does **not** choose or run tools. Python controls the order.
- **Where we use it:** Phase 5 (`agent_tools.py`) and Phase 7 (`main.py`).

### python-dotenv

- **What it is:** A small library that reads `KEY=value` lines from a `.env` file into environment variables.
- **Why we need it:** It keeps the API key and settings out of the source code.
- **How it works here:** Every Python module calls `load_dotenv()` at import time. Then `os.getenv("ANTHROPIC_API_KEY")` and similar calls can read the values.
- **Where we use it:** All Python modules.

### pytest

- **What it is:** A Python testing framework.
- **Why we need it:** It checks that the code behaves correctly without needing a live cluster or a real API key.
- **How it works here:** The tests replace `run_kubectl` with fake functions (using `monkeypatch`) and write reports into temporary folders.
- **Where we use it:** Phase 8.

### What is an "AI agent" in this project?

A normal chatbot answers a question. An **AI agent** follows a task: it uses tools, gathers results, and produces an answer based on those results.

In this project:

- **Python** is the controller. It decides which tools to run and in what order.
- **Tools** are Python functions that read real data from Kubernetes.
- **Claude** is the analyst. It receives the collected evidence and explains it.

This is a deliberate safety choice. Claude never receives shell access and never runs commands. It only reads evidence that Python has already collected.

---

## Part 3 — Architecture: How the Pieces Work Together

### High-level flow

```text
                    ┌─────────────────────────────┐
  You (terminal) ──▶│  main.py                    │  validates pod name + namespace
                    │  (entry point / controller) │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼─────────────────────────┬─────────────────────┐
          ▼                        ▼                         ▼                     ▼
 ┌──────────────────┐   ┌────────────────────┐   ┌────────────────────┐  ┌──────────────────┐
 │ agent_tools.py   │   │ pod_tools.py       │   │ claude_client.py   │  │ reporting.py     │
 │ LangChain @tool  │──▶│ collect_pod_       │   │ build_prompt()     │  │ create_markdown_ │
 │ wrappers (steps  │   │ evidence() and     │   │ explain_incident() │  │ report()         │
 │ 1–4, display)    │   │ kubectl helpers    │   └─────────┬──────────┘  └────────┬─────────┘
 └──────────────────┘   └─────────┬──────────┘             │                      │
                                  │ subprocess             │ HTTPS                │ write file
                                  ▼                        ▼                      ▼
                        ┌──────────────────┐     ┌──────────────────┐   ┌───────────────────────┐
                        │ kubectl          │     │ Claude API       │   │ reports/incident_     │
                        │  └▶ k3d cluster  │     │ (Anthropic)      │   │ <ns>_<pod>_<time>.md  │
                        │   (K8s API +     │     └──────────────────┘   └───────────────────────┘
                        │   Metrics Server)│
                        └──────────────────┘
```

### Step-by-step data flow

1. You run `python main.py --pod <name> --namespace ai-sre-lab`. If you leave out `--pod`, the program lists the Pods and asks you to choose one.
2. `main.py` validates the names so that only safe Kubernetes-style names reach `kubectl`.
3. `main.py` calls four LangChain tools (`inspect_pod`, `read_pod_logs`, `read_pod_events`, `read_pod_cpu_ram`) and prints their results. If the Pod cannot be inspected, the program stops here and **no report is created**.
4. `main.py` calls `collect_pod_evidence()`, which gathers status (including the previous container state), metrics, events, current logs, previous logs, and `describe` output into one Python dictionary.
5. `claude_client.explain_incident()` sends this evidence to Claude and returns the Root Cause Analysis text, or a clear "AI explanation unavailable" message.
6. `reporting.create_markdown_report()` writes the evidence and the analysis into a Markdown file in `reports/`.
7. `main.py` prints the report path.

### Which file uses which file

| File | Imports from | Used by |
|---|---|---|
| `pod_tools.py` | `dotenv` | `agent_tools.py`, `main.py`, `tests/test_pod_tools.py` |
| `agent_tools.py` | `langchain_core`, `dotenv`, `pod_tools` | `main.py` |
| `claude_client.py` | `anthropic`, `dotenv` | `main.py`, `tests/test_pod_tools.py` |
| `reporting.py` | `dotenv` | `main.py`, `tests/test_pod_tools.py` |
| `main.py` | `dotenv`, `pod_tools`, `claude_client`, `reporting`, `agent_tools` | You (command line), `tests/test_pod_tools.py` |

---

## Part 4 — Project Folder Structure

This is the actual structure of the project (generated files such as `.venv/`, `__pycache__/` and `.pytest_cache/` are left out):

```text
agent/
│
├── README.md               ← this guide
├── manual.docs             ← original course manual (kept unchanged)
├── requirements.txt        ← Python packages
├── .env                    ← your private settings and API key (never commit)
├── .env.example            ← safe template for .env
├── .gitignore              ← files Git must ignore
├── pytest.ini              ← pytest configuration
│
├── main.py                 ← entry point; runs the full investigation
├── pod_tools.py            ← read-only kubectl diagnostic functions
├── agent_tools.py          ← LangChain @tool wrappers around pod_tools
├── claude_client.py        ← builds the prompt and calls the Claude API
├── reporting.py            ← writes the Markdown incident report
│
├── k8s/
│   ├── demo.yaml           ← healthy HTTPD Deployment + Service (demo-web)
│   ├── broken-pod.yaml     ← deliberately broken Pod (invalid image tag)
│   └── crashloop-pod.yaml  ← deliberately crashing Pod (CrashLoopBackOff)
│
├── tests/
│   └── test_pod_tools.py   ← automated tests (17 test cases)
│
└── reports/
    └── .gitkeep            ← keeps the empty folder in Git; reports are written here
```

> **Note:** The project folder also contains `README.backup.md`, an older copy of a previous README. It is not used by the code. The `reports/` folder may also contain older reports from before the demo application was switched from NGINX to HTTPD (Pod names starting `demo-web-66d4d546b-`). They are kept as history and are ignored by Git.

### What each file and folder does

| Path | Purpose | Why we need it | Used by |
|---|---|---|---|
| `agent/README.md` | Project guide | Explains how to build, run, and test the project | People |
| `agent/manual.docs` | Original manual | Primary reference that this project was built from | People |
| `agent/requirements.txt` | Package list | `pip install -r requirements.txt` installs everything | pip |
| `agent/.env` | Real settings | Holds the API key, model ID, namespace, report folder | All Python modules via `load_dotenv()` |
| `agent/.env.example` | Settings template | Shows which variables exist without exposing secrets | You (copy to `.env`) |
| `agent/.gitignore` | Git ignore rules | Keeps secrets, the venv, caches, and reports out of Git | Git |
| `agent/pytest.ini` | Test settings | Adds the project root to Python's import path for tests | pytest |
| `agent/main.py` | Entry point | Validates input and runs the whole workflow | You |
| `agent/pod_tools.py` | Diagnostic layer | The only file that talks to Kubernetes | `agent_tools.py`, `main.py`, tests |
| `agent/agent_tools.py` | Tool layer | Presents diagnostics as LangChain tools | `main.py` |
| `agent/claude_client.py` | AI layer | The only file that talks to the Claude API | `main.py`, tests |
| `agent/reporting.py` | Report layer | Turns evidence and analysis into a Markdown file | `main.py`, tests |
| `agent/k8s/demo.yaml` | Healthy workload | Apache HTTPD Deployment and Service; gives us a working Pod to investigate | `kubectl apply` |
| `agent/k8s/broken-pod.yaml` | Broken workload | Gives us a realistic `ImagePullBackOff` incident | `kubectl apply` |
| `agent/k8s/crashloop-pod.yaml` | Crashing workload | Gives us a realistic `CrashLoopBackOff` incident for RCA testing | `kubectl apply` |
| `agent/tests/test_pod_tools.py` | Tests | Verifies parsing, reporting, validation, and error handling | pytest |
| `agent/reports/` | Output folder | Generated incident reports are saved here | `reporting.py` |

In this guide, the project lives at **`~/agent`**. (The original manual used `~/pod-investigation-agent`. Either location works, as long as you use it consistently.)

---

## Phase 1 — Prepare the RHEL 10 Environment

**Goal:** Install and verify Python, Docker, kubectl, and k3d on RHEL 10.

**Where to run:** All commands in this phase run in a terminal on the RHEL 10 host. Commands with `sudo` need administrator rights.

> Use a test machine or a lab VM. Do not build this lab on a production server.

### Step 1.1 — Update the system and install basic tools

```bash
sudo dnf update -y
sudo dnf install -y curl git vim tar gzip
```

- `dnf update -y` installs the latest package updates. `-y` answers "yes" automatically.
- `dnf install` installs tools we use later: `curl` (downloads), `git` (version control), `vim` (editor), `tar` and `gzip` (archives).

**Verify:**

```bash
cat /etc/redhat-release
curl --version | head -1
git --version
```

Illustrative output:

```text
Red Hat Enterprise Linux release 10.0 (Coughlan)
curl 8.x.x ...
git version 2.x.x
```

**If it fails:** Check that the system is registered with Red Hat (`sudo subscription-manager status`) and that it has internet access. Without a registered subscription, RHEL repositories are not available.

### Step 1.2 — Install Python tools

```bash
sudo dnf install -y python3 python3-pip python3-devel gcc
```

- `python3` — the Python interpreter.
- `python3-pip` — the Python package installer.
- `python3-devel` and `gcc` — headers and a compiler, needed if a Python package must be built from source.

**Verify:**

```bash
python3 --version
python3 -m venv --help | head -1
```

Illustrative output:

```text
Python 3.12.9
usage: venv [-h] [--system-site-packages] [--symlinks | --copies] ...
```

**If it fails:** If `python3 -m venv` is not found, reinstall `python3`. This project was tested with Python 3.12.

### Step 1.3 — Install and start Docker

k3d needs Docker Engine. Follow the official Docker documentation for RHEL ("Install Docker Engine on RHEL") because repository details can change. The usual steps are:

```bash
# Remove packages that conflict with Docker Engine (ignore "No match" messages)
sudo dnf remove -y docker docker-client docker-client-latest docker-common \
  docker-latest docker-latest-logrotate docker-logrotate docker-engine podman runc

# Add the official Docker repository
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo

# Install Docker Engine
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker now and on every boot
sudo systemctl enable --now docker
```

- `dnf remove ... podman runc` removes packages that conflict with Docker's `containerd.io`. Skip this if you need Podman on this machine, and check the official docs for alternatives.
- `config-manager --add-repo` adds Docker's package repository.
- `systemctl enable --now docker` starts the Docker service immediately and enables it at boot.

**Verify:**

```bash
sudo systemctl status docker --no-pager
docker version
docker run --rm hello-world
docker ps
```

Successful results:

- `systemctl status` shows `Active: active (running)`.
- `docker version` shows both a **Client** and a **Server** section. If only the client appears, the daemon is not reachable.
- `hello-world` prints `Hello from Docker!`.
- `docker ps` prints a header line (and possibly no containers).

**Required if you are not logged in as root — run Docker without `sudo`:**

```bash
sudo usermod -aG docker $USER
# Log out and log in again, then:
docker ps
```

> Membership in the `docker` group gives root-equivalent power on the host. Only do this on a lab machine.

**Why this matters:** From Phase 2 onward, run `k3d`, `kubectl`, and `python` as your **normal user, without `sudo`**. There are two reasons:

1. On RHEL, `sudo` uses a restricted `PATH` (`/sbin:/bin:/usr/sbin:/usr/bin`) that does **not** include `/usr/local/bin`. So `sudo k3d ...` or `sudo kubectl ...` fails with `command not found`.
2. k3d writes the cluster credentials to the kubeconfig of the user who ran it. If you create the cluster as root, your normal user's `kubectl` (and therefore the agent) cannot connect.

If you work as `root` (as in the recorded run for this guide), you can skip the group change.

**If it fails:** See [Docker service not running](#1-docker-service-not-running).

### Step 1.4 — Install kubectl

Install the current stable `kubectl` binary from the official Kubernetes site:

```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
rm kubectl
```

- The inner `curl` reads the latest stable version number. The outer `curl` downloads that version.
- `install ... -m 0755` copies the binary to `/usr/local/bin` and makes it executable.
- On ARM64 machines, replace `amd64` with `arm64`.

**Verify:**

```bash
kubectl version --client
```

Recorded output (your version may differ):

```text
Client Version: v1.37.1
Kustomize Version: v5.8.1
```

**If it fails:** If you see `command not found`, check that `/usr/local/bin` is in your `PATH` (`echo $PATH`).

### Step 1.5 — Install k3d

The k3d project provides an install script. Review a script before running it:

```bash
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh -o install-k3d.sh
less install-k3d.sh          # review the script
bash install-k3d.sh
rm install-k3d.sh
```

**Verify:**

```bash
k3d version
```

Recorded output:

```text
k3d version v5.9.0
k3s version v1.35.5-k3s1 (default)
```

### Step 1.6 — Final check

Run all three checks together:

```bash
docker ps
kubectl version --client
k3d version
```

If all three work, Phase 1 is complete.

---

## Phase 2 — Create the Kubernetes Cluster

**Goal:** Create a local two-node Kubernetes cluster, connect `kubectl` to it, and deploy the healthy demo application.

**Where to run:** The RHEL 10 terminal.

### How k3d runs Kubernetes using Docker

```text
RHEL 10 host
└── Docker Engine
    ├── container: k3d-pod-lab-server-0   ← Kubernetes control plane + node (k3s server)
    ├── container: k3d-pod-lab-agent-0    ← Kubernetes worker node (k3s agent)
    └── container: k3d-pod-lab-serverlb   ← load balancer in front of the API server
```

Each Docker container acts like a Kubernetes node. Pods run inside these containers (using containerd inside k3s). Because everything is containerised, you can create and delete the whole cluster in seconds.

### Step 2.1 — Create the cluster

```bash
k3d cluster create pod-lab --agents 1 --servers 1
```

- `pod-lab` is the cluster name.
- `--servers 1` creates one control-plane node.
- `--agents 1` creates one worker node.
- k3d automatically adds a context called `k3d-pod-lab` to `~/.kube/config` and makes it the current context.

Recorded output (last lines; the full output is longer):

```text
INFO[0043] Starting agents...
INFO[0044] Starting node 'k3d-pod-lab-agent-0'
INFO[0063] Starting helpers...
INFO[0063] Starting node 'k3d-pod-lab-serverlb'
INFO[0073] Injecting records for hostAliases (incl. host.k3d.internal) and for 3 network members into CoreDNS configmap...
INFO[0076] Cluster 'pod-lab' created successfully!
INFO[0077] You can now use it like this:
kubectl cluster-info
```

The first run takes longer because Docker downloads the k3s images.

### Step 2.2 — Check cluster status and the kubectl connection

```bash
k3d cluster list
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
```

- `k3d cluster list` shows the cluster and how many servers and agents are running.
- `kubectl config current-context` should print `k3d-pod-lab`. This confirms `kubectl` is connected to the right cluster.
- `kubectl cluster-info` shows the API server address.
- `kubectl get nodes` lists the nodes.

Recorded output:

```text
$ kubectl config current-context
k3d-pod-lab

$ kubectl get nodes
NAME                   STATUS   ROLES           AGE   VERSION
k3d-pod-lab-agent-0    Ready    <none>          15s   v1.35.5+k3s1
k3d-pod-lab-server-0   Ready    control-plane   33s   v1.35.5+k3s1
```

Both nodes should be `Ready`. If a node shows `NotReady`, wait 30 seconds and check again.

**If it fails:** See [kubectl connection errors](#3-kubectl-connection-errors).

### Step 2.3 — Check Metrics Server (needed for CPU/RAM usage)

k3s ships Metrics Server by default. It provides the data behind `kubectl top`.

```bash
kubectl -n kube-system get deployment metrics-server
kubectl top nodes
```

Recorded output:

```text
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
metrics-server   1/1     1            1           106s
```

Metrics can take about a minute to appear after the cluster starts. If `kubectl top nodes` says `metrics not available yet`, wait and try again.

If the `metrics-server` Deployment does not exist (for example, if the cluster was created with it disabled), see [Missing Kubernetes metrics](#7-missing-kubernetes-metrics). The agent still works without metrics; the report will say CPU/RAM usage is unavailable.

### Step 2.4 — Create the namespace

All lab resources use the namespace **`ai-sre-lab`**. A namespace is a named group of resources inside a cluster.

```bash
kubectl create namespace ai-sre-lab
kubectl get namespace ai-sre-lab
```

If you see `AlreadyExists`, that is fine.

### Step 2.5 — Create the project folder

```bash
mkdir -p ~/agent/k8s
cd ~/agent
```

### Step 2.6 — Create the HTTPD Deployment and Service

**File: `agent/k8s/demo.yaml`**

This file contains **two** Kubernetes objects, separated by `---`:

1. A **Deployment** called `demo-web` that runs the **Apache HTTPD** web server. A Deployment keeps the requested number of Pods running. If the Pod is deleted or crashes, the Deployment creates a new one.
2. A **Service** called `demo-web` that gives the web server a stable name and IP address inside the cluster.

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
        - name: httpd
          image: httpd:2.4
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "250m"
              memory: "128Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: demo-web
  namespace: ai-sre-lab
spec:
  selector:
    app: demo-web
  ports:
    - port: 80
      targetPort: 80
```

**Deployment explanation:**

| Field | Meaning |
|---|---|
| `kind: Deployment` | Manages a ReplicaSet, which manages the Pods. |
| `metadata.namespace: ai-sre-lab` | Creates it in the lab namespace. |
| `replicas: 1` | Keep exactly one Pod running. |
| `selector.matchLabels` / `template.metadata.labels` | The Deployment finds its Pods by the label `app: demo-web`. These two must match. |
| `containers[0].name: httpd` | Container name. It appears in logs, metrics, and the report. |
| `image: httpd:2.4` | The official Apache HTTP Server image, version 2.4 series, from Docker Hub. |
| `containerPort: 80` | HTTPD listens on port 80. |
| `resources.requests` | The minimum the scheduler reserves: 50 millicores of CPU (0.05 CPU) and 64 MiB of memory. |
| `resources.limits` | The maximum allowed: 250 millicores of CPU and 128 MiB of memory. |

**Service explanation:**

| Field | Meaning |
|---|---|
| `kind: Service` | A stable network endpoint in front of one or more Pods. Pod IPs change when Pods are recreated; the Service name and IP do not. |
| `metadata.name: demo-web` | Inside the cluster, the application is reachable as `http://demo-web` (same namespace) or `http://demo-web.ai-sre-lab.svc.cluster.local`. |
| `spec.selector: app: demo-web` | Sends traffic to Pods with this label, which are the Pods created by the Deployment. |
| `port: 80` | The port the Service listens on. |
| `targetPort: 80` | The container port the traffic is forwarded to. |
| (no `type`) | The default type is `ClusterIP`: reachable only from inside the cluster. We use `kubectl port-forward` to reach it from the host. |

> The agent investigates **Pods**. The Service is not investigated by the agent; it is part of the demo application so that you can verify the application really serves traffic.

### Step 2.7 — Deploy and check the application

```bash
kubectl apply -f ~/agent/k8s/demo.yaml
kubectl rollout status deployment/demo-web -n ai-sre-lab
kubectl get deployment,pods,service -n ai-sre-lab -o wide
```

- `apply -f` creates or updates both objects in the file.
- `rollout status` waits until the Deployment is ready. The first time, this includes downloading the `httpd:2.4` image (it took about one minute in the recorded run).
- `get deployment,pods,service -o wide` shows all three resource types with extra columns.

Recorded output:

```text
deployment.apps/demo-web created
service/demo-web created

Waiting for deployment "demo-web" rollout to finish: 0 of 1 updated replicas are available...
deployment "demo-web" successfully rolled out

NAME                       READY   UP-TO-DATE   AVAILABLE   AGE   CONTAINERS   IMAGES      SELECTOR
deployment.apps/demo-web   1/1     1            1           76s   httpd        httpd:2.4   app=demo-web

NAME                            READY   STATUS    RESTARTS   AGE   IP          NODE                  NOMINATED NODE   READINESS GATES
pod/demo-web-665f97df4c-mj54n   1/1     Running   0          76s   10.42.1.4   k3d-pod-lab-agent-0   <none>           <none>

NAME               TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)   AGE   SELECTOR
service/demo-web   ClusterIP   10.43.94.46   <none>        80/TCP    76s   app=demo-web
```

What to check:

| Resource | Healthy result |
|---|---|
| Deployment | `READY 1/1`, `AVAILABLE 1` |
| Pod | `READY 1/1`, `STATUS Running`, `RESTARTS 0` |
| Service | `TYPE ClusterIP` with a cluster IP and `80/TCP` |

**Write down the Pod name.** It looks like `demo-web-<replicaset-hash>-<random>` (in the recorded run: `demo-web-665f97df4c-mj54n`). It changes every time the Pod is recreated, so always copy it from your own output.

**Check that the Service is connected to the Pod:**

```bash
kubectl get endpointslices -n ai-sre-lab -l kubernetes.io/service-name=demo-web
```

Recorded output:

```text
NAME             ADDRESSTYPE   PORTS   ENDPOINTS   AGE
demo-web-grpkl   IPv4          80      10.42.1.4   86s
```

The `ENDPOINTS` value must be the Pod IP. If it is empty, the Service selector does not match the Pod labels.

**Check that HTTPD responds (from the host):**

```bash
kubectl port-forward service/demo-web 8080:80 -n ai-sre-lab
```

This forwards port 8080 on your machine to port 80 of the Service. Leave it running, and in a **second terminal** run:

```bash
curl -i http://localhost:8080
```

Recorded output (headers shortened):

```text
HTTP/1.1 200 OK
Server: Apache/2.4.69 (Unix)
Content-Length: 191
Content-Type: text/html

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
<head>
<title>It works! Apache httpd</title>
</head>
<body>
<p>It works!</p>
</body>
</html>
```

`HTTP/1.1 200 OK` and "It works!" confirm that HTTPD is serving traffic through the Service. Press `Ctrl+C` in the first terminal to stop port-forwarding.

**Optional — check the Service from inside the cluster:**

```bash
kubectl run curl-test --rm -i --restart=Never --image=busybox:1.36 -n ai-sre-lab -- wget -qO- http://demo-web
```

This starts a temporary BusyBox Pod, fetches `http://demo-web` using the Service name, prints the same "It works!" page, and then deletes the temporary Pod (`--rm`).

`wget` finishes very quickly, so `kubectl` may also print messages like `If you don't see a command prompt, try pressing enter.` and `warning: couldn't attach to pod/curl-test, falling back to streaming logs`. These are harmless; the page is still printed and the Pod is still deleted (`pod "curl-test" deleted`). Do not pipe this command into `head` or press `Ctrl+C` early, because that stops `kubectl` before it can delete the Pod. If a `curl-test` Pod is left behind, remove it:

```bash
kubectl delete pod curl-test -n ai-sre-lab --ignore-not-found
```

**Check the configured resources and live usage:**

```bash
kubectl top pod -n ai-sre-lab --containers
kubectl describe pod -n ai-sre-lab -l app=demo-web | grep -A6 Limits
```

Recorded `kubectl top` output:

```text
POD                         NAME    CPU(cores)   MEMORY(bytes)
demo-web-665f97df4c-mj54n   httpd   2m           6Mi
```

If `kubectl top` says `metrics not available yet`, wait a minute and try again.

---

## Phase 3 — Create the Python Project

**Goal:** Create the project folders, a virtual environment, install dependencies, and configure settings.

**Where to run:** The RHEL 10 terminal, inside `~/agent`.

### Why Python?

Python is readable, has an official Anthropic SDK and LangChain support, and has a standard `subprocess` module to run `kubectl`. These three things are all this project needs.

### How to create the files in this guide

Every file in this guide is introduced with its exact path, for example **File: `agent/pod_tools.py`**. `agent/` means your project folder, `~/agent`. To create a file, open it in an editor, paste the **complete** code block shown under that heading, and save:

```bash
cd ~/agent
vim pod_tools.py        # paste the code, then save with :wq
```

Copy the code blocks exactly. Python depends on indentation, so do not change the spaces at the start of lines. If your editor auto-indents pasted text, use `:set paste` in vim before pasting.

### Step 3.1 — Create folders and the virtual environment

```bash
mkdir -p ~/agent/reports ~/agent/tests ~/agent/k8s
cd ~/agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

- `mkdir -p` creates the folders (no error if they exist).
- `python3 -m venv .venv` creates the virtual environment in `.venv/`.
- `source .venv/bin/activate` activates it. Your prompt changes to start with `(.venv)`.
- `pip install --upgrade pip` updates pip inside the venv only.

**Verify:**

```bash
which python
```

It should print `/root/agent/.venv/bin/python` (or `/home/<user>/agent/.venv/bin/python`). If it prints `/usr/bin/python`, the venv is not active.

> You must run `source .venv/bin/activate` in **every new terminal** before running the agent or tests.

### Step 3.2 — Create `requirements.txt`

**File: `agent/requirements.txt`**

```text
anthropic
langchain-core
python-dotenv
pytest
```

| Package | Why we need it | Used in |
|---|---|---|
| `anthropic` | Official Claude API client | `claude_client.py` |
| `langchain-core` | Provides the `@tool` decorator | `agent_tools.py` |
| `python-dotenv` | Loads `.env` into environment variables | All Python modules |
| `pytest` | Runs automated tests | `tests/test_pod_tools.py` |

The versions are not pinned, so `pip` installs the latest releases. This project was verified with:

```text
anthropic       2.3.0
langchain-core  1.7.3
python-dotenv   1.2.4
pytest          9.2.0
```

If a future release breaks something, you can pin these versions, for example `anthropic==2.3.0`.

**Install:**

```bash
cd ~/agent
source .venv/bin/activate
pip install -r requirements.txt
```

**Verify:**

```bash
pip list | grep -Ei 'anthropic|langchain-core|dotenv|pytest'
python -c "import anthropic, langchain_core, dotenv; print('imports OK')"
```

### Step 3.3 — Create `.gitignore`

**File: `agent/.gitignore`**

```text
.venv/
.env
__pycache__/
.pytest_cache/
reports/*.md
```

| Line | Why it is ignored |
|---|---|
| `.venv/` | Large, machine-specific; recreate it with `pip install -r requirements.txt`. |
| `.env` | **Contains your API key.** Must never be committed. |
| `__pycache__/` | Python bytecode cache, generated automatically. |
| `.pytest_cache/` | pytest cache, generated automatically. |
| `reports/*.md` | Generated reports can contain logs, IPs, and cluster details. `reports/.gitkeep` is not a `.md` file, so the empty folder stays in Git. |

### Step 3.4 — Create `.env.example` and `.env`

**File: `agent/.env.example`**

```text
ANTHROPIC_API_KEY=replace_with_your_real_key
ANTHROPIC_MODEL=claude-opus-5-5
K8S_NAMESPACE=ai-sre-lab
REPORT_DIR=reports
```

This is a **safe template**. It contains no secret. Create your real `.env` from it and restrict its permissions:

```bash
cd ~/agent
cp .env.example .env
chmod 600 .env
vim .env
```

**File: `agent/.env`** — edit the values:

```text
ANTHROPIC_API_KEY=<your-real-anthropic-api-key>
ANTHROPIC_MODEL=<a-model-id-available-in-your-account>
K8S_NAMESPACE=ai-sre-lab
REPORT_DIR=reports
```

| Variable | Read by | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | `claude_client.py` | Your Claude API key from the Anthropic Console. |
| `ANTHROPIC_MODEL` | `claude_client.py` | The Claude model ID to use. |
| `K8S_NAMESPACE` | `pod_tools.py` (`DEFAULT_NAMESPACE`) | Default namespace when a `pod_tools` function is called without one. |
| `REPORT_DIR` | `reporting.py` | Folder for reports. A relative path is relative to the directory you run the command from. |

**About the model ID:** `.env.example` contains `claude-opus-5-5`. Model availability depends on your Anthropic account and changes over time. Before running, check the model list in your Anthropic Console (or the Anthropic models documentation) and set `ANTHROPIC_MODEL` to a model ID that is **currently available to your account**. If the ID is wrong, the report will say `model '...' was not found`.

**About `K8S_NAMESPACE`:** `main.py` always passes a namespace explicitly (from `--namespace`, default `ai-sre-lab`), and `agent_tools.py` also defaults to `ai-sre-lab`. So when you run `main.py`, `K8S_NAMESPACE` has no effect; use `--namespace` instead. It only matters if you call `pod_tools` functions directly without a namespace.

### Why API keys must be private

- Anyone who has your key can use the API **on your account and your bill**.
- Keys pushed to Git (even to a private repo, even if deleted later) stay in Git history and are often found by automated scanners.
- Never paste the key into chats, tickets, screenshots, or source code.
- If a key leaks, **revoke it immediately** in the Anthropic Console and create a new one.

The code reads the key only from the environment. It never prints or writes the key.

> `load_dotenv()` does **not** override variables already set in your shell. If you exported `ANTHROPIC_API_KEY` earlier in the terminal, that value wins over `.env`.

### Step 3.5 — Create `pytest.ini`

**File: `agent/pytest.ini`**

```ini
[pytest]
pythonpath = .
```

`pythonpath = .` adds the project root to Python's import path during tests. Because of this, `tests/test_pod_tools.py` can write `import pod_tools` and `import main` even though it lives in the `tests/` subfolder.

### Step 3.6 — Create the reports folder placeholder

```bash
touch ~/agent/reports/.gitkeep
```

`reporting.py` also creates the folder automatically if it is missing. The `.gitkeep` file only makes sure the empty folder exists in Git.

---

## Phase 4 — Build the Kubernetes Diagnostic Tools

**Goal:** Write Python functions that collect real, read-only information about a Pod.

### How Python talks to Kubernetes in this project

```text
Python function ──▶ subprocess.run(["kubectl", "get", "pod", ...]) ──▶ kubectl ──▶ Kubernetes API
       ▲                                                                   │
       └──────────────── stdout (text or JSON) / stderr (error) ◀──────────┘
```

- Python does **not** use a Kubernetes client library.
- It runs `kubectl` with an **argument list** (not a shell string). This means characters like `;` or `|` in a name cannot run extra shell commands.
- `kubectl` uses your existing kubeconfig (`~/.kube/config`) for the cluster address and credentials.
- Every function returns a **dictionary** that always contains `"ok": True` or `"ok": False`. On failure, the dictionary contains an `"error"` message. Functions never crash the program with a raw exception because of a `kubectl` failure.

### File: `agent/pod_tools.py`

This is the diagnostic layer and the only file that runs `kubectl`. All commands are read-only.

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
            "state": state,
            "last_state": item.get("lastState", {})
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


def get_pod_previous_logs(pod_name, namespace=DEFAULT_NAMESPACE, tail=80):
    """Read logs from the previous (crashed or restarted) container instance."""
    result = run_kubectl([
        "logs", pod_name, "-n", namespace, "--all-containers=true",
        "--previous", f"--tail={int(tail)}"
    ])
    if not result["ok"]:
        return {
            "ok": False,
            "note": "No previous container logs. This is normal if the container "
                    "has never restarted or never started.",
            "error": result["error"]
        }
    return {"ok": True, "logs": result["output"] or "(No log lines returned)"}


def get_pod_events(pod_name, namespace=DEFAULT_NAMESPACE):
    result = run_kubectl([
        "get", "events", "-n", namespace,
        "--field-selector", f"involvedObject.name={pod_name}",
        "--sort-by=.lastTimestamp",
        "-o", "custom-columns=FIRST_SEEN:.firstTimestamp,LAST_SEEN:.lastTimestamp,"
              "COUNT:.count,TYPE:.type,REASON:.reason,SOURCE:.source.component,"
              "MESSAGE:.message"
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
        "previous_logs": get_pod_previous_logs(pod_name, namespace),
        "description": get_pod_description(pod_name, namespace)
    }
```

### Imports and module-level setup

| Line | Purpose |
|---|---|
| `import json` | Parse the JSON returned by `kubectl get pod -o json`. |
| `import os` | Read environment variables with `os.getenv`. |
| `import subprocess` | Run `kubectl` as a child process. |
| `from datetime import datetime, timezone` | Record when evidence was collected, in UTC. |
| `from dotenv import load_dotenv` / `load_dotenv()` | Load `.env` when this module is imported. |
| `DEFAULT_NAMESPACE = os.getenv("K8S_NAMESPACE", "ai-sre-lab")` | Default namespace for every function below. Falls back to `ai-sre-lab` if the variable is not set. |

### Function: `run_kubectl(args, timeout=20)`

The foundation of every other function.

- **Receives:** `args`, a list of `kubectl` arguments such as `["get", "pod", "x", "-n", "ai-sre-lab"]`, and an optional `timeout` in seconds (default 20).
- **Executes:** `subprocess.run(["kubectl", ...], capture_output=True, text=True, timeout=timeout, check=False)`.
  - `capture_output=True` captures stdout and stderr instead of printing them.
  - `text=True` returns strings instead of bytes.
  - `check=False` means a non-zero exit code does not raise an exception; we inspect `returncode` ourselves.
- **Returns:**
  - Success: `{"ok": True, "output": "<stdout>"}`.
  - `kubectl` error (non-zero exit): `{"ok": False, "error": "<stderr, or stdout if stderr is empty>"}`.
  - Timeout: `{"ok": False, "error": "Command timed out: kubectl ..."}`.
  - `kubectl` not installed: `{"ok": False, "error": "kubectl was not found. Install kubectl first."}`.
- **Used by:** every other function in this file. Tests replace it with a fake to simulate Kubernetes.

### Function: `list_pods(namespace)`

- **Receives:** a namespace.
- **Executes:** `kubectl get pods -n <ns> -o jsonpath={.items[*].metadata.name}` — prints only Pod names separated by spaces.
- **Returns:** `{"ok": True, "pods": ["pod-a", "pod-b"]}` or the error dictionary.
- **Used by:** `main.choose_pod()` when you do not pass `--pod`.

### Function: `get_configured_resources(pod)`

- **Receives:** the full Pod dictionary (already parsed from JSON). It does **not** run `kubectl`.
- **Does:** for each container in `spec.containers`, reads `resources.requests` and `resources.limits`. Missing values become `"Not set"`.
- **Returns:** a list such as:

  ```python
  [{"container": "httpd", "image": "httpd:2.4",
    "cpu_request": "50m", "cpu_limit": "250m",
    "memory_request": "64Mi", "memory_limit": "128Mi"}]
  ```

- **Used by:** `get_pod_status()`. The report shows this list as a table.

### Function: `get_pod_status(pod_name, namespace)`

The main "Pod information" and "Pod status" function.

- **Receives:** Pod name and namespace.
- **Executes:** `kubectl get pod <name> -n <ns> -o json`.
- **Does:**
  1. Returns the error dictionary if `kubectl` fails (for example, `pods "x" not found`).
  2. Parses the JSON. If it is not valid JSON, returns a clear error.
  3. For each entry in `status.containerStatuses`, records the container name, `ready`, `restart_count`, the full current `state` object, `waiting_reason` (for example `ImagePullBackOff`, `ErrImagePull`, or `CrashLoopBackOff`; an empty string if the container is not waiting), and `last_state`.
  4. `last_state` comes from `lastState` in the Pod JSON. It describes the **previous** container run, for example `{"terminated": {"exitCode": 1, "reason": "Error"}}` or `"reason": "OOMKilled"`. It is empty if the container has never restarted. This is key evidence for an RCA of a crashing Pod.
- **Returns:** a dictionary with these keys:

  | Key | Source in Pod JSON | Default if missing |
  |---|---|---|
  | `ok` | — | `True` |
  | `name`, `namespace` | `metadata.name`, `metadata.namespace` | (required) |
  | `phase` | `status.phase` (`Pending`, `Running`, `Succeeded`, `Failed`, `Unknown`) | `"Unknown"` |
  | `node` | `spec.nodeName` | `"Not scheduled"` |
  | `pod_ip` | `status.podIP` | `"Not assigned"` |
  | `created` | `metadata.creationTimestamp` | `"Unknown"` |
  | `labels` | `metadata.labels` | `{}` |
  | `containers` | `status.containerStatuses` (processed) | `[]` |
  | `configured_resources` | `spec.containers[].resources` | `[]` |
  | `owner_references` | `metadata.ownerReferences` (e.g. the ReplicaSet) | `[]` |

- **Used by:** `agent_tools.inspect_pod` (step 1 in `main.py`) and `collect_pod_evidence()`.

> Note: the Pod **phase** and the container **waiting reason** are different. A Pod with an image problem usually has phase `Pending` while its container's waiting reason is `ImagePullBackOff`. The agent records both.

### Function: `get_pod_logs(pod_name, namespace, tail=80)`

- **Executes:** `kubectl logs <name> -n <ns> --all-containers=true --tail=80`.
  - `--all-containers=true` includes every container in the Pod.
  - `--tail=80` returns only the last 80 lines. `int(tail)` makes sure the value is a number.
- **Returns:** `{"ok": True, "logs": "<lines>"}`, or `"(No log lines returned)"` if the container wrote nothing, or the error dictionary.
- **Important:** If the container never started (for example, image pull failure), `kubectl logs` fails. The error text (for example `container "web" in pod "broken-image-demo" is waiting to start: trying and failing to pull image`) is shown in the report instead of logs. This is real evidence too.
- It reads logs of the **current** container instance. Logs of the previous instance are read by `get_pod_previous_logs()`.

### Function: `get_pod_previous_logs(pod_name, namespace, tail=80)`

- **Why:** When a container crashes and restarts, the useful error message is often in the logs of the **previous** run, not the new one. An RCA of a `CrashLoopBackOff` Pod needs these logs.
- **Executes:** `kubectl logs <name> -n <ns> --all-containers=true --previous --tail=80`.
- **Returns on success:** `{"ok": True, "logs": "<lines>"}`.
- **Returns on failure:**

  ```python
  {"ok": False,
   "note": "No previous container logs. This is normal if the container has never restarted or never started.",
   "error": "<the real kubectl error>"}
  ```

- **When it fails (normal cases):**
  - The container never restarted: `previous terminated container "web" in pod "..." not found`.
  - Timing: while a crashed container is waiting for its next restart, Kubernetes may have already removed the older run, and `kubectl` says `unable to retrieve container logs for containerd://...`. In that situation, the **current** logs (from `get_pod_logs()`) already show the last crash output. That's why the agent collects both.

### Function: `get_pod_events(pod_name, namespace)`

- **Executes:** `kubectl get events -n <ns> --field-selector involvedObject.name=<pod> --sort-by=.lastTimestamp -o custom-columns=...`.
  - `--field-selector` keeps only events about this Pod.
  - `--sort-by=.lastTimestamp` puts the newest events last.
  - `-o custom-columns=` prints these columns: `FIRST_SEEN`, `LAST_SEEN`, `COUNT`, `TYPE`, `REASON`, `SOURCE`, `MESSAGE`.
- **Why custom columns:** The default output shows relative ages such as `29m`. An RCA needs a **timeline**, so the agent records **absolute UTC timestamps** (for example `2026-10-30T22:38:35Z`). `FIRST_SEEN` and `LAST_SEEN` with `COUNT` show when a repeated event started, when it last happened, and how often.
- **Note on `<nil>`:** Some events (for example `Scheduled` from the scheduler) store their time in a different field, so `FIRST_SEEN` and `LAST_SEEN` show `<nil>`. Claude is told to use only timestamps that exist, so it writes "Not recorded" for those.
- **Returns:** `{"ok": True, "events": "<table>"}`, or `"(No events returned)"` when there are none, or the error dictionary.
- **Note:** Kubernetes deletes old events after a retention period (one hour by default). For an older, stable Pod, "(No events returned)" is normal.

### Function: `get_pod_metrics(pod_name, namespace)`

- **Executes:** `kubectl top pod <name> -n <ns> --containers` — live CPU and memory per container, from Metrics Server.
- **Returns on success:** `{"ok": True, "cpu_ram": "<kubectl top table>"}`.
- **Returns on failure:**

  ```python
  {"ok": False,
   "cpu_ram": "Unavailable",
   "note": "kubectl top failed. Metrics Server may not be installed, may not be ready, or the pod may not have metrics yet.",
   "error": "<the real kubectl error>"}
  ```

- **No invented values:** When metrics fail, the value is the word `Unavailable`. The code never estimates, guesses, or copies a limit into the usage field.

### Function: `get_pod_description(pod_name, namespace)`

- **Executes:** `kubectl describe pod <name> -n <ns>`.
- **Returns:** `{"ok": True, "description": "<full text>"}` or the error dictionary.
- **Why:** `describe` combines spec, status, conditions, QoS class, volumes, and recent events in a human-readable form. It is useful context for Claude and for the engineer.

### Function: `collect_pod_evidence(pod_name, namespace)`

- **Does:** calls the six collection functions and puts the results in one dictionary.
- **Returns:**

  ```python
  {
      "collected_at_utc": "2026-10-29T22:05:25.106982+00:00",
      "pod": {...},          # get_pod_status()
      "metrics": {...},      # get_pod_metrics()
      "events": {...},       # get_pod_events()
      "logs": {...},          # get_pod_logs()
      "previous_logs": {...}, # get_pod_previous_logs()
      "description": {...}    # get_pod_description()
  }
  ```

- **Used by:** `main.py` step 5. This dictionary is sent to Claude **and** passed to the report writer, so the report and the AI analysis use the same evidence.
- Each part can fail independently. For example, `logs` can be an error while `events` succeeds. One failure does not stop the others.

### Live CPU/RAM usage vs. configured requests and limits

This difference is important and easy to confuse.

| | Live usage | Configured requests / limits |
|---|---|---|
| **What it is** | What the container is **actually using now** | What the Pod spec **says** it may reserve or use |
| **Source** | Metrics Server, via `kubectl top` | The Pod spec, via `kubectl get pod -o json` |
| **Function** | `get_pod_metrics()` | `get_configured_resources()` (inside `get_pod_status()`) |
| **Example** (recorded, HTTPD Pod) | `httpd  1m  6Mi` | request `50m`/`64Mi`, limit `250m`/`128Mi` |
| **Available when** | Metrics Server works **and** the container is running | Always, if the Pod object exists |
| **Report section** | "Actual CPU and RAM usage (live, from kubectl top)" | "Configured CPU and RAM (requests and limits from the pod spec)" |

- A **request** is what the scheduler reserves for the container.
- A **limit** is the maximum. A container that exceeds its memory limit is killed (`OOMKilled`). A container that reaches its CPU limit is slowed down (throttled).
- A request or limit is **never** a measurement. The prompt to Claude says this explicitly.

### Step 4.1 — Test the diagnostic commands by hand

Before trusting the Python code, run the same commands manually. Replace `<POD>` with your Pod name.

```bash
kubectl get pods -n ai-sre-lab
kubectl get pod <POD> -n ai-sre-lab -o json | head -30
kubectl logs <POD> -n ai-sre-lab --all-containers=true --tail=10
kubectl get events -n ai-sre-lab --field-selector involvedObject.name=<POD>
kubectl top pod <POD> -n ai-sre-lab --containers
kubectl describe pod <POD> -n ai-sre-lab
```

### Step 4.2 — Test the functions from Python

```bash
cd ~/agent
source .venv/bin/activate
python -c "from pod_tools import list_pods; print(list_pods('ai-sre-lab'))"
python -c "from pod_tools import get_pod_metrics; print(get_pod_metrics('<POD>', 'ai-sre-lab'))"
```

Illustrative output (your Pod name and values will differ; the second line uses the values recorded from the HTTPD Pod):

```text
{'ok': True, 'pods': ['demo-web-665f97df4c-mj54n']}
{'ok': True, 'cpu_ram': 'POD                         NAME    CPU(cores)   MEMORY(bytes)   \ndemo-web-665f97df4c-mj54n   httpd   1m           6Mi'}
```

---

## Phase 5 — Connect the Agent with Claude AI

**Goal:** Wrap the diagnostic functions as LangChain tools and send the collected evidence to Claude, which writes the Root Cause Analysis.

### Key ideas

- **AI agent:** A program that completes a task by using tools and then reasoning over the results. Here, Python runs the tools and Claude reasons over the results.
- **Claude:** Anthropic's large language model. It reads text and writes text.
- **Claude API:** An HTTPS API. Your program sends a "message" (the prompt) with a model ID and an API key. The API returns Claude's response.
- **LangChain tool:** A Python function with a name, description, and typed arguments in a standard format. The `@tool` decorator creates it from a normal function. Its docstring becomes the tool description; its type hints become the input schema.

### How the agent workflow is actually wired

Be precise about what this version does:

1. `main.py` calls the LangChain tools in a **fixed sequence** using `.invoke(...)`.
2. `main.py` calls `collect_pod_evidence()` to gather the complete evidence.
3. `main.py` passes that evidence to `claude_client.explain_incident()`.
4. Claude receives **text only**. It does **not** select tools, call tools, or run commands.

The tools are **not** bound to the Claude model, and `claude_client.py` does not use LangChain. LangChain is used here to give the diagnostics a standard tool interface, which a future version could hand to a model. Keeping Python in control makes the behaviour predictable, testable, and safe.

### File: `agent/agent_tools.py`

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

**Explanation:**

- `from langchain_core.tools import tool` imports the decorator.
- It imports four functions from `pod_tools.py`. Each tool is a thin wrapper that only forwards its arguments.
- `@tool` turns each function into a LangChain `StructuredTool`:
  - **Name:** the function name, for example `inspect_pod`.
  - **Description:** the docstring, for example "Read the current status, node, labels and container state of one pod."
  - **Arguments schema:** from the type hints — `pod_name: str` (required) and `namespace: str` (optional, default `"ai-sre-lab"`).
- A LangChain tool is called with a dictionary:

  ```python
  inspect_pod.invoke({"pod_name": "demo-web-66d4d546b-2jv7k", "namespace": "ai-sre-lab"})
  ```

  It returns the same dictionary as the underlying `pod_tools` function.

| Tool | Wraps | Purpose |
|---|---|---|
| `inspect_pod` | `get_pod_status` | Status, node, labels, container state, configured resources |
| `read_pod_logs` | `get_pod_logs` | Last 80 log lines from all containers |
| `read_pod_events` | `get_pod_events` | Events for this Pod |
| `read_pod_cpu_ram` | `get_pod_metrics` | Live CPU and memory from `kubectl top` |

`get_pod_description` and `list_pods` are **not** wrapped as tools. `main.py` uses them directly.

**Check the tools:**

```bash
cd ~/agent
source .venv/bin/activate
python -c "from agent_tools import inspect_pod; print(inspect_pod.name); print(inspect_pod.description); print(inspect_pod.args)"
```

Recorded output:

```text
inspect_pod
Read the current status, node, labels and container state of one pod.
{'pod_name': {'title': 'Pod Name', 'type': 'string'}, 'namespace': {'default': 'ai-sre-lab', 'title': 'Namespace', 'type': 'string'}}
```

### File: `agent/claude_client.py`

This is the only file that talks to the Claude API.

```python
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

PLACEHOLDER_KEY = "replace_with_your_real_key"


def build_prompt(evidence):
    return f"""
You are a careful Site Reliability Engineer writing a Root Cause Analysis (RCA)
for one Kubernetes pod.
Use only the evidence below. Do not invent CPU, RAM, timestamps, or events.
"metrics" is live usage from kubectl top. "configured_resources" are requests
and limits from the pod spec. Never present a request or limit as actual usage.
If CPU/RAM metrics are unavailable, say so.
"last_state" and "previous_logs" describe the previous container run (for
example an OOMKilled or crashed container). Use them when the pod restarted.
Event times in "events" are absolute UTC timestamps; use them for the timeline.

Write the RCA in Markdown with exactly these sections, using level-3 headings
(###), so it fits inside the report:
### 1. Executive summary
Two or three sentences: what failed, the root cause, and the current state.
### 2. Problem statement
Pod, namespace, node, symptom, and when it was first observed.
### 3. Impact
What is affected according to the evidence (for example: container never
started, no logs, restarts). Say "unknown" for anything the evidence cannot show.
### 4. Timeline (UTC)
A table of events in time order, taken only from timestamps in the evidence.
### 5. Confirmed observations
Facts directly visible in the evidence.
### 6. Root cause
Label it "Confirmed root cause" only if the evidence directly proves it.
Otherwise label it "Most likely root cause (not confirmed)" and say what is
missing. If the pod is healthy and shows no failure, write "No incident
detected" and explain why; do not invent a root cause.
### 7. Contributing factors
Configuration or conditions that made the problem possible or worse.
### 8. Five whys
A short chain from the symptom to the root cause. Stop where the evidence ends.
### 9. Corrective actions
Immediate fix steps for a human to review and run. Mark each as
"not performed by the agent; requires human approval".
### 10. Preventive actions
Changes that would stop this from happening again.
### 11. Verification steps
Read-only commands to confirm the fix worked.
### 12. Confidence level and evidence gaps
Low, medium, or high, and why. List evidence that would raise confidence.

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

#### Imports and constants

| Line | Purpose |
|---|---|
| `import json` | Convert the evidence dictionary to formatted JSON text for the prompt. |
| `import os` | Read `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`. |
| `import anthropic` | Official Claude SDK. Provides the client and the error classes. |
| `load_dotenv()` | Loads `.env` so the variables exist. |
| `PLACEHOLDER_KEY` | The dummy value from `.env.example`. If the key still equals it, the code does not call the API. |

#### Function: `build_prompt(evidence)`

- **Receives:** the evidence dictionary from `collect_pod_evidence()`.
- **Returns:** a single prompt string.
- **How the prompt controls Claude:**

  | Prompt part | Why it is there |
  |---|---|
  | "You are a careful Site Reliability Engineer writing a Root Cause Analysis (RCA)..." | Sets the role and the type of document. |
  | "Use only the evidence below. Do not invent CPU, RAM, timestamps, or events." | Prevents made-up values. |
  | Explanation of `metrics` vs `configured_resources` | Prevents Claude from presenting a limit as usage. |
  | "If CPU/RAM metrics are unavailable, say so." | Forces honest handling of missing data. |
  | Explanation of `last_state` and `previous_logs` | Tells Claude where to find evidence about earlier crashes (exit code, OOMKilled, last error lines). |
  | "Event times ... are absolute UTC timestamps; use them for the timeline." | Builds the RCA timeline from real times only. |
  | Twelve required sections with `###` headings | Gives every RCA the same structure (see the table below). The `###` level fits under the report's `##` heading. |
  | "Confirmed root cause" only if the evidence proves it; otherwise "Most likely root cause (not confirmed)" | Stops the AI from overstating its certainty. |
  | "If the pod is healthy ... write 'No incident detected' ... do not invent a root cause." | Prevents a made-up RCA for a healthy Pod. |
  | Corrective actions marked "not performed by the agent; requires human approval" | Makes the read-only boundary explicit in the RCA itself. |
  | "Do not claim you changed the cluster." | Matches the read-only design. |
  | `EVIDENCE JSON:` + `json.dumps(evidence, indent=2)` | The complete evidence, formatted for readability. |

- The full evidence is sent, including the complete `describe` output, current logs, and previous logs (up to 80 lines each). It is not truncated.

**The twelve RCA sections Claude is asked to write:**

| # | Section | What it contains |
|---|---|---|
| 1 | Executive summary | Two or three sentences: what failed, the root cause, the current state |
| 2 | Problem statement | Pod, namespace, node, symptom, first observed time |
| 3 | Impact | What is affected according to the evidence; "unknown" where the evidence cannot show it |
| 4 | Timeline (UTC) | A table of events in time order, from real timestamps only |
| 5 | Confirmed observations | Facts directly visible in the evidence |
| 6 | Root cause | "Confirmed root cause", "Most likely root cause (not confirmed)", or "No incident detected" |
| 7 | Contributing factors | Configuration or conditions that made the problem possible or worse |
| 8 | Five whys | A chain from symptom to root cause, stopping where the evidence ends |
| 9 | Corrective actions | Immediate fix steps for a human, each marked "not performed by the agent; requires human approval" |
| 10 | Preventive actions | Changes that stop it from happening again |
| 11 | Verification steps | Read-only commands to confirm the fix |
| 12 | Confidence level and evidence gaps | Low / medium / high, and what evidence would raise confidence |

> The sections are requested in the prompt but not enforced by code. Claude follows them very consistently, but the wording and level of detail differ on every run.

#### Function: `explain_incident(evidence)`

- **Receives:** the evidence dictionary.
- **Step 1 — configuration checks (no network call):**
  - If `ANTHROPIC_API_KEY` is missing or still the placeholder, it returns `"AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env. ..."`.
  - If `ANTHROPIC_MODEL` is missing, it returns `"AI explanation unavailable: set ANTHROPIC_MODEL in .env."`.
- **Step 2 — API call:**
  - `anthropic.Anthropic(api_key=api_key)` creates the client.
  - `client.messages.create(model=..., max_tokens=8000, messages=[{"role": "user", "content": prompt}])` sends one user message. `max_tokens=8000` is the upper limit on the length of Claude's answer.
- **Step 3 — error handling.** Each known API error becomes a clear message instead of a crash:

  | Exception | Typical cause | Message returned |
  |---|---|---|
  | `AuthenticationError` (401) | Wrong or revoked key | "the API key was rejected" |
  | `NotFoundError` (404) | Model ID not available | "model '...' was not found" |
  | `RateLimitError` (429) | Rate limit or quota | "rate limit or quota reached" |
  | `APIConnectionError` | No network, DNS, proxy, timeout | "could not connect to the Claude API" |
  | `APIStatusError` | Any other HTTP error (e.g. 400, 500, 529) | "API error <code>: <message>" |

  The specific errors are listed before `APIStatusError` because they are subclasses of it (except `APIConnectionError`), so Python must check them first.
- **Step 4 — read the response:**
  - If `stop_reason == "refusal"`, it returns "Claude declined this request."
  - Otherwise it joins all content blocks of type `"text"` and returns the text.
  - If there is no text, it returns "Claude returned no text."
- **Returns:** always a string. `main.py` never has to handle an exception from this function for API problems, and the report is still created when the AI is unavailable.

**How settings flow from `.env` to the API call:**

```text
.env ──load_dotenv()──▶ os.environ ──os.getenv()──▶ api_key, model ──▶ anthropic.Anthropic(...).messages.create(model=model, ...)
```

**Check the Claude connection (optional):**

```bash
cd ~/agent
source .venv/bin/activate
python -c "from claude_client import explain_incident; print(explain_incident({'note': 'connection test, no pod data'}))"
```

With a valid key and model, Claude returns a short Markdown answer (it will say there is no real evidence). With a placeholder key, you will see the "AI explanation unavailable" message. Either result shows the code path works.

---

## Phase 6 — Generate the Incident and RCA Report

**Goal:** Save the evidence and Claude's analysis as a Markdown report.

### Why incident reports are useful

- They give a **single record** of what was observed and when.
- They can be shared with teammates, attached to tickets, and reviewed later.
- They separate **facts** (raw Kubernetes output) from **interpretation** (Claude's analysis), so a reader can check the analysis against the evidence.

### What is an RCA?

A **Root Cause Analysis (RCA)** answers four questions about an incident:

1. **What happened?** (problem statement, impact, timeline)
2. **Why did it happen?** (root cause, contributing factors, five whys)
3. **How do we fix it now?** (corrective actions)
4. **How do we stop it happening again?** (preventive actions)

A good RCA is based on evidence, not guesses. This project gets its evidence from Kubernetes (Phase 4), asks Claude to write the RCA from that evidence only (Phase 5), and saves both the evidence and the RCA in one Markdown file (this phase). The reader can check every RCA statement against the raw evidence in the same file.

### File: `agent/reporting.py`

````python
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
    previous_logs = evidence.get("previous_logs", {})
    description = evidence.get("description", {})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = report_dir / f"incident_{safe_filename(namespace)}_{safe_filename(pod_name)}_{timestamp}.md"

    cpu_ram = metrics.get("cpu_ram", "Unavailable") if metrics.get("ok") else "Unavailable"
    metrics_note = ""
    if not metrics.get("ok"):
        metrics_note = "**Live metrics could not be retrieved.** " + metrics.get("note", "")
        if metrics.get("error"):
            metrics_note += f"\n\nKubernetes said: `{metrics['error']}`"

    content = f"""# Kubernetes Pod Incident and Root Cause Analysis (RCA) Report

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

## Previous container logs (before the last restart)

```text
{previous_logs.get("logs", previous_logs.get("error", "Unavailable"))}
```

## Pod description

```text
{description.get("description", description.get("error", "Unavailable"))[:8000]}
```

## Root cause analysis (AI-generated, advisory)

{ai_explanation}

## Verification and limitations

- This report is based on evidence collected from the current Kubernetes cluster.
- The AI explanation is advisory; verify recommendations before making changes.
- This program did not restart, delete, or modify the pod.
- Missing metrics or unavailable logs are reported as unavailable, not guessed.
"""
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)
````

#### Imports

| Import | Purpose |
|---|---|
| `json` | Pretty-print the container state list. |
| `os` | Read `REPORT_DIR`. |
| `re` | Regular expression used by `safe_filename`. |
| `datetime` | Report timestamp and filename timestamp (local time). |
| `pathlib.Path` | Build file paths and create the folder. |
| `load_dotenv` | Load `REPORT_DIR` from `.env`. |

#### Function: `safe_filename(value)`

- **Receives:** a string (namespace or Pod name).
- **Does:** replaces every run of characters that are not letters, digits, `_`, `.`, or `-` with a single `_`.
- **Returns:** a string that is safe to use in a filename. Valid Kubernetes names are already safe, so they are returned unchanged.

#### Function: `configured_resources_table(resources)`

- **Receives:** the `configured_resources` list from `get_pod_status()`.
- **Returns:** a Markdown table with one row per container, or the line `Configured requests/limits: Unavailable (pod details could not be read).` if the list is empty.

#### Function: `create_markdown_report(pod_name, namespace, evidence, ai_explanation)`

- **Receives:**
  - `pod_name`, `namespace` — from `main.py`.
  - `evidence` — the dictionary from `collect_pod_evidence()`.
  - `ai_explanation` — the string from `explain_incident()`.
- **Step 1 — folder:** reads `REPORT_DIR` (default `reports`) and creates it if needed (`mkdir(parents=True, exist_ok=True)`).
- **Step 2 — evidence parts:** reads each section with `.get(..., {})`, so a missing section never causes a crash.
- **Step 3 — filename:**

  ```text
  incident_<namespace>_<pod-name>_<YYYYMMDD_HHMMSS>.md
  ```

  The timestamp uses the machine's **local time**. Example from this project:
  `reports/incident_ai-sre-lab_broken-image-demo_20261031_024857.md`.
  Each run creates a **new** file, so earlier reports are never overwritten.
- **Step 4 — metrics handling:**
  - If `metrics["ok"]` is true, the `kubectl top` table is shown.
  - Otherwise, the usage box shows `Unavailable`, followed by a bold **"Live metrics could not be retrieved."** line, the explanatory note, and the real Kubernetes error.
- **Step 5 — fallbacks for each section:** `events.get("events", events.get("error", "Unavailable"))` means: show the events if present; otherwise show the error message; otherwise show `Unavailable`. Logs and description work the same way.
- **Step 6 — size limit:** only the first 8,000 characters of the `describe` output are written to the report (`[:8000]`). Claude still receives the full text.
- **Step 7 — write:** writes the file as UTF-8 and returns the path as a string.

### Report sections and where each value comes from

| Report section / field | Source | Fact or interpretation? |
|---|---|---|
| Generated at (local time) | `datetime.now()` in `reporting.py` | Fact |
| Evidence collected at (UTC) | `collected_at_utc` | Fact |
| Pod name, Namespace | `main.py` arguments | Fact |
| Status, Node, Pod IP, Created | `get_pod_status()` | Fact |
| Actual CPU and RAM usage | `get_pod_metrics()` | Fact (or "Unavailable") |
| Configured CPU and RAM | `get_configured_resources()` | Fact (configuration) |
| Container state | `get_pod_status()["containers"]` | Fact |
| Kubernetes events | `get_pod_events()` | Fact |
| Recent logs | `get_pod_logs()` | Fact (or the `kubectl` error) |
| Previous container logs | `get_pod_previous_logs()` | Fact (or the `kubectl` error) |
| Pod description | `get_pod_description()` | Fact |
| Root cause analysis (AI-generated, advisory): the twelve RCA sections | `explain_incident()` | **Interpretation** — advisory |
| Verification and limitations | Fixed text | Statement of scope |

**Facts vs interpretation:** Everything above the "Root cause analysis" heading is raw evidence. Inside the RCA, Claude is instructed to list **confirmed observations** (directly visible in the evidence) separately, and to call a root cause "Confirmed" only when the evidence proves it. Otherwise it must say "Most likely root cause (not confirmed)". Always verify an unconfirmed root cause before acting.

### Example RCA report (crash-looping Pod)

The excerpt below is a **real RCA report generated by this project** with a valid API key: `reports/incident_ai-sre-lab_crashloop-demo_20261031_041101.md`. The Pod comes from `k8s/crashloop-pod.yaml` (see [Step 8.9](#step-89--rca-of-a-crash-looping-pod)). The report is long, so it is shortened here: `[...]` marks removed text.

**Part 1 — Evidence collected by Python (facts):**

```markdown
# Kubernetes Pod Incident and Root Cause Analysis (RCA) Report

- **Generated at (local time):** 2026-10-31T04:11:01
- **Evidence collected at (UTC):** 2026-10-30T22:40:00.486190+00:00
- **Pod name:** crashloop-demo
- **Namespace:** ai-sre-lab
- **Status:** Running
- **Node:** k3d-pod-lab-agent-0
- **Pod IP:** 10.42.1.10
- **Created:** 2026-10-30T22:38:27Z

## Actual CPU and RAM usage (live, from kubectl top)

    Unavailable

**Live metrics could not be retrieved.** [...]
Kubernetes said: `Error from server (NotFound): podmetrics.metrics.k8s.io "ai-sre-lab/crashloop-demo" not found`

## Configured CPU and RAM (requests and limits from the pod spec)

| Container | CPU request | CPU limit | Memory request | Memory limit |
|---|---|---|---|---|
| app | 10m | 100m | 16Mi | 32Mi |

## Container state

    [
      {
        "name": "app",
        "ready": false,
        "restart_count": 3,
        "waiting_reason": "",
        "state": {
          "terminated": { [...] "exitCode": 1, "finishedAt": "2026-10-30T22:39:12Z", "reason": "Error", [...] }
        },
        "last_state": {
          "terminated": { [...] "exitCode": 1, "finishedAt": "2026-10-30T22:38:49Z", "reason": "Error", [...] }
        }
      }
    ]

## Kubernetes events

    FIRST_SEEN             LAST_SEEN              COUNT    TYPE      REASON      SOURCE    MESSAGE
    <nil>                  <nil>                  <none>   Normal    Scheduled   <none>    Successfully assigned ai-sre-lab/crashloop-demo to k3d-pod-lab-agent-0
    2026-10-30T22:38:31Z   2026-10-30T22:39:11Z   4        Normal    Pulled      kubelet   Container image "busybox:1.36" already present on machine [...]
    2026-10-30T22:38:31Z   2026-10-30T22:39:11Z   4        Normal    Created     kubelet   Container created
    2026-10-30T22:38:32Z   2026-10-30T22:39:12Z   4        Normal    Started     kubelet   Container started
    2026-10-30T22:38:35Z   2026-10-30T22:39:14Z   4        Warning   BackOff     kubelet   Back-off restarting failed container app in pod crashloop-demo_ai-sre-lab(...)

## Recent logs

    Starting payment-api v1.4.2
    Loading configuration from /etc/app/config.yaml
    ERROR: configuration file /etc/app/config.yaml not found

## Previous container logs (before the last restart)

    unable to retrieve container logs for containerd://d444ce82359c263fd4a9165bc1ed0774d51b816a164690950d8260d9e8dfa476

## Pod description
[...]
```

> In the real file, the evidence blocks use ```` ```text ```` and ```` ```json ```` fences. They are indented here only so the example displays correctly inside this README.

Things to notice in the evidence:

- **Status is `Running`** even though the container keeps crashing. For a restarting container, Kubernetes keeps the Pod phase `Running`. The real story is in **Container state**: `terminated`, `exitCode: 1`, `restart_count: 3`, and `last_state` showing the previous run also failed with exit code 1.
- **Events have absolute times.** `COUNT 4` with `FIRST_SEEN` and `LAST_SEEN` shows four start/crash cycles in about 40 seconds.
- **Current logs show the crash** because the container had just terminated. The previous-logs request failed for timing reasons (see `get_pod_previous_logs()` in Phase 4). The report shows that error honestly.

**Part 2 — Root cause analysis written by Claude (interpretation), shortened:**

````markdown
## Root cause analysis (AI-generated, advisory)

### 1. Executive summary
The `app` container in pod `crashloop-demo` exits with code 1 about as soon as it starts. Kubernetes has
restarted it 3 times and is now applying restart back-off. The root cause is the container's configured
command. It is a `sh -c` script that prints a "configuration file not found" message and then runs
`exit 1` unconditionally. It never checks for the file. [...]

### 2. Problem statement
- **Pod:** `crashloop-demo`
- **Namespace:** `ai-sre-lab`
- **Node:** `k3d-pod-lab-agent-0` (172.24.0.3)
- **Symptom:** Container `app` repeatedly terminates with `reason: Error`, `exitCode: 1`. [...]
- **First observed:** The first `BackOff` warning was at **2026-10-30T22:38:35Z**, about 8 seconds after pod creation (22:38:27Z).

### 3. Impact
- **Container availability:** Container `app` has never reached Ready. [...]
- **Service / user impact:** Unknown. The log text mentions "payment-api v1.4.2", but the evidence shows
  no Service, no ports, no owner controller and no traffic data. [...]
- **Resource usage:** Unknown. Metrics are unavailable [...]

### 4. Timeline (UTC)
| Time (UTC) | Event | Source |
|---|---|---|
| Not recorded (`<nil>`) | `Scheduled`: pod assigned to `k3d-pod-lab-agent-0` | events |
| 2026-10-30T22:38:27Z | Pod created / Start Time | pod.created, description |
| 2026-10-30T22:38:32Z | First `Started` | events |
| 2026-10-30T22:38:35Z | First `Warning BackOff`: restarting failed container `app` | events |
| 2026-10-30T22:38:49Z | Previous run started and terminated: Error, exit code 1 | last_state |
| 2026-10-30T22:39:12Z | Last `Started` (4th occurrence). Current run started and terminated: Error, exit code 1 | events, state |
| 2026-10-30T22:40:00Z | Evidence collected: phase `Running`, container Terminated, restart count 3, Ready false | collected_at_utc |
[...]

### 6. Root cause
**Confirmed root cause:** The container's configured command (`sh -c … exit 1`) terminates the process
with exit code 1 on every run, regardless of conditions. [...]

**Clarification on the log message:** The line "configuration file /etc/app/config.yaml not found" is
printed by a hard-coded `echo`. It is not the result of an actual file check. [...] adding a config file
or ConfigMap mount **would not fix this pod**, because `exit 1` executes unconditionally.

### 7. Contributing factors
- **Misleading error message:** The log points to a missing config file, which could send responders
  toward a ConfigMap fix that would not resolve the crash.
- **No controller:** Empty `owner_references` means there is no Deployment managing rollout or rollback. [...]
- **Not a factor:** Memory and CPU limits. The termination reason is `Error`, not `OOMKilled` [...]

### 8. Five whys
1. **Why is the pod not Ready and in back-off?** Container `app` keeps terminating with exit code 1 [...]
2. **Why does the container exit with code 1?** Its command is a shell script that ends with `exit 1`.
3. **Why does the script exit 1?** The `exit 1` is unconditional. [...]
4. **Why is the pod running this script instead of a working application?** Unknown. The evidence does not
   show who authored the manifest or whether it was intentional [...]
5. Stopping here; the evidence ends at the pod spec.

### 9. Corrective actions
[...]
3. **Correct the manifest.** *Not performed by the agent; requires human approval.*
   - Replace the `sh -c … exit 1` command with the real application image and entrypoint. [...]

### 10. Preventive actions
- **Use a controller:** Run workloads under a Deployment rather than as bare pods [...]
- **Alerting and metrics:** Alert on `kube_pod_container_status_restarts_total` increases [...]

### 11. Verification steps
All commands below are read-only.
```sh
kubectl get pod crashloop-demo -n ai-sre-lab -o wide
kubectl describe pod crashloop-demo -n ai-sre-lab
kubectl logs crashloop-demo -n ai-sre-lab -c app
[...]
```

### 12. Confidence level and evidence gaps
**Confidence: High** that the crash is caused by the container command's unconditional `exit 1`. The spec
shows the command, the logs match its output exactly, and exit code 1 is recorded for both observed runs.

**Confidence: Low** on intent, meaning whether this is a deliberate demo or a misdeployed `payment-api`,
and on any business impact.

**Evidence gaps:**
- **Previous logs:** These were unavailable. The current logs plus the identical exit codes make it highly
  likely they were the same, but this is not directly confirmed.
[...]
````

What this shows about the RCA design:

- **Facts vs interpretation:** Everything in Part 1 is raw Kubernetes output. Part 2 is Claude's analysis, and it cites where each fact came from (`events`, `last_state`, `collected_at_utc`).
- **Confirmed only when proven:** It labelled the root cause "Confirmed" because the spec, logs, and exit codes all prove it, and kept intent and business impact as "unknown" or "Low".
- **Thinks beyond the obvious:** It noticed that the "config file not found" message is a hard-coded `echo`, so a ConfigMap fix alone would not work. A quick reading of the logs would have missed this.
- **No invented numbers:** CPU/RAM are reported as unavailable, and the missing `Scheduled` timestamp is written as "Not recorded".
- **Read-only:** Every corrective action is marked "not performed by the agent; requires human approval". The agent changed nothing.

---

## Phase 7 — Connect Everything Through main.py

**Goal:** Build the entry point that validates input, runs the diagnostics, calls Claude, and writes the report.

### File: `agent/main.py`

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
```

#### Imports

| Import | Purpose |
|---|---|
| `argparse` | Reads `--pod` and `--namespace` from the command line. |
| `json` | Pretty-prints the status dictionary in step 1. |
| `re` | Compiles the name validation pattern. |
| `collect_pod_evidence`, `list_pods` | From `pod_tools.py`. |
| `explain_incident` | From `claude_client.py`. |
| `create_markdown_report` | From `reporting.py`. |
| `inspect_pod`, `read_pod_logs`, `read_pod_events`, `read_pod_cpu_ram` | LangChain tools from `agent_tools.py`. |

#### `NAME_PATTERN` and `validate_name(value, label)`

- `NAME_PATTERN` allows only lowercase letters, digits, `-`, and `.`. The name must start and end with a letter or digit. This follows the Kubernetes naming rules for Pods.
- `validate_name` raises `ValueError` if the value is empty, longer than 253 characters, or does not match the pattern. Otherwise, it returns the value.
- **Why:** it rejects input such as `Bad_Name`, `pod;rm -rf`, or `-starts-with-dash` before anything reaches `kubectl`. (The argument-list `subprocess` call is already safe against shell injection; validation adds a second layer and gives a clearer error.)

#### `choose_pod(namespace)`

- Used only when `--pod` is not given.
- Calls `list_pods()`. Exits with code 1 if the Pods cannot be listed or there are none.
- Prints a numbered list, then reads your answer with `input()`.
- If you type a valid number, it returns that Pod name. Otherwise, it returns what you typed. That value is then checked by `validate_name()`.

#### `main()` — execution flow step by step

1. **The application starts.** `python main.py ...` runs `main()` (because of `if __name__ == "__main__":`). Importing the modules runs `load_dotenv()`.
2. **It receives the target Pod and namespace.** `argparse` reads `--pod` (optional) and `--namespace` (default `ai-sre-lab`). The namespace is validated first. Then the Pod name comes from `--pod` or from `choose_pod()`, and is validated. Invalid names print an error and exit with code 1.
3. **Python checks that the Pod exists — `[1/5]`.** `inspect_pod.invoke(...)` runs `get_pod_status()`. If `ok` is false (for example `pods "ghost" not found`), the program prints the error and a hint, then exits with code 1. **No report is created and Claude is not called.** On success, the status is printed as JSON.
4. **Python shows the other diagnostics — `[2/5]` to `[4/5]`.** It invokes `read_pod_logs`, `read_pod_events`, and `read_pod_cpu_ram`, and prints each result dictionary. These steps are for **on-screen visibility**. A failure here (for example, no logs) does **not** stop the program.
5. **The diagnostic results are prepared — `[5/5]`.** `collect_pod_evidence()` gathers status, metrics, events, current logs, previous logs, and description into one dictionary with a UTC timestamp.
6. **Claude writes the Root Cause Analysis.** `explain_incident(evidence)` returns Claude's twelve-section Markdown RCA, or an "AI explanation unavailable" message.
7. **The report generator creates the incident report.** `create_markdown_report(...)` builds the Markdown.
8. **The report is saved inside `reports/`.** The path is printed, along with a `cat` command to open it.

> **Note:** Steps 1–4 and step 5 call `kubectl` separately. So each command runs twice: once for display, once for the evidence. The report uses the step 5 data. If the Pod changes in the seconds between them, the screen output and the report can differ slightly.

### How the Python files communicate

```text
main.py
 ├─ validate_name()  ─ local
 ├─ choose_pod() ───────────────▶ pod_tools.list_pods() ─▶ kubectl get pods
 ├─ inspect_pod.invoke() ───────▶ agent_tools ─▶ pod_tools.get_pod_status() ─▶ kubectl get pod -o json
 ├─ read_pod_logs.invoke() ─────▶ agent_tools ─▶ pod_tools.get_pod_logs()   ─▶ kubectl logs
 ├─ read_pod_events.invoke() ───▶ agent_tools ─▶ pod_tools.get_pod_events() ─▶ kubectl get events
 ├─ read_pod_cpu_ram.invoke() ──▶ agent_tools ─▶ pod_tools.get_pod_metrics()─▶ kubectl top pod
 ├─ collect_pod_evidence() ─────▶ pod_tools (all six collectors, including previous logs + describe)
 ├─ explain_incident(evidence) ─▶ claude_client ─▶ Claude API
 └─ create_markdown_report(...) ▶ reporting ─▶ reports/incident_*.md
```

### Command to run the application

**Where to run:** inside `~/agent`, with the virtual environment active.

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod <REAL_POD_NAME> --namespace ai-sre-lab
```

Or choose the Pod from a list:

```bash
python main.py --namespace ai-sre-lab
```

Help:

```bash
python main.py --help
```

> **Run it from the project folder.** `REPORT_DIR=reports` is a relative path. If you run `python ~/agent/main.py` from another folder, the `reports/` folder is created in that other folder.

**Exit codes:** `0` when the report is created; `1` for an invalid name, a Pod that cannot be inspected, or a namespace with no Pods.

---

## Phase 8 — Testing and Real Incident Investigation

**Goal:** Run the automated tests, then investigate a healthy Pod and a broken Pod on the real cluster and compare the reports.

### Part A — Automated tests with pytest

#### File: `agent/tests/test_pod_tools.py`

The tests do **not** need a cluster or an API key. They replace `run_kubectl` with fake functions and write reports into temporary folders.

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
                "image": "httpd:2.4",
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
            "containers": [{"name": "httpd", "ready": True, "restart_count": 0}]
        },
        "metrics": {"ok": True, "cpu_ram": "httpd 2m 12Mi"},
        "events": {"ok": True, "events": "No events"},
        "logs": {"ok": True, "logs": "httpd started"},
        "description": {"ok": True, "description": "Pod description"}
    }
    path = create_markdown_report(
        "demo-web-abc", "ai-sre-lab", evidence, "No issue observed."
    )
    content = open(path, encoding="utf-8").read()
    assert "demo-web-abc" in content
    assert "ai-sre-lab" in content
    assert "httpd 2m 12Mi" in content
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
                "container": "httpd", "image": "httpd:2.4",
                "cpu_request": "50m", "cpu_limit": "250m",
                "memory_request": "64Mi", "memory_limit": "128Mi",
            }],
        },
        "metrics": {"ok": True, "cpu_ram": "httpd 1m 5Mi"},
    }
    path = create_markdown_report("demo-web-abc", "ai-sre-lab", evidence, "OK")
    content = open(path, encoding="utf-8").read()
    assert "Actual CPU and RAM usage" in content
    assert "Configured CPU and RAM" in content
    assert "| httpd | 50m | 250m | 64Mi | 128Mi |" in content


def test_missing_api_key_gives_clear_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "replace_with_your_real_key")
    message = claude_client.explain_incident({"pod": {}})
    assert "AI explanation unavailable" in message


# ---------- RCA tests ----------

def test_last_state_is_recorded_for_restarted_container(monkeypatch):
    pod = json.loads(fake_pod_json("crashloop-demo", "Running", ready=False,
                                   waiting_reason="CrashLoopBackOff"))
    pod["status"]["containerStatuses"][0]["restartCount"] = 4
    pod["status"]["containerStatuses"][0]["lastState"] = {
        "terminated": {"exitCode": 1, "reason": "Error"}
    }
    monkeypatch.setattr(
        pod_tools, "run_kubectl",
        lambda args, timeout=20: {"ok": True, "output": json.dumps(pod)}
    )
    status = get_pod_status("crashloop-demo", "ai-sre-lab")
    container = status["containers"][0]
    assert container["waiting_reason"] == "CrashLoopBackOff"
    assert container["restart_count"] == 4
    assert container["last_state"]["terminated"]["exitCode"] == 1


def test_previous_logs_error_is_reported(monkeypatch):
    calls = []

    def fake_run(args, timeout=20):
        calls.append(args)
        return {"ok": False, "error": 'previous terminated container "web" not found'}

    monkeypatch.setattr(pod_tools, "run_kubectl", fake_run)
    result = pod_tools.get_pod_previous_logs("demo-web-abc", "ai-sre-lab")
    assert result["ok"] is False
    assert "not found" in result["error"]
    assert "--previous" in calls[0]


def test_prompt_asks_for_rca_sections():
    prompt = claude_client.build_prompt({"pod": {"phase": "Pending"}})
    for section in ["Executive summary", "Timeline (UTC)", "Root cause",
                    "Five whys", "Corrective actions", "Preventive actions",
                    "Confidence level and evidence gaps"]:
        assert section in prompt
    assert '"phase": "Pending"' in prompt


def test_report_contains_rca_and_previous_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {"phase": "Running"},
        "metrics": {"ok": True, "cpu_ram": "web 1m 2Mi"},
        "previous_logs": {"ok": True, "logs": "ERROR: config file not found"},
    }
    path = create_markdown_report(
        "crashloop-demo", "ai-sre-lab", evidence, "### 6. Root cause\nBad config."
    )
    content = open(path, encoding="utf-8").read()
    assert "Root Cause Analysis (RCA) Report" in content
    assert "## Previous container logs" in content
    assert "ERROR: config file not found" in content
    assert "## Root cause analysis (AI-generated, advisory)" in content
    assert "Bad config." in content
```

**Testing techniques used:**

- **`monkeypatch.setattr(pod_tools, "run_kubectl", ...)`** replaces the real `kubectl` runner with a lambda that returns fake output. Because `get_pod_status` and the others look up `run_kubectl` in the `pod_tools` module at call time, they use the fake one. No cluster is needed.
- **`monkeypatch.setenv(...)`** sets an environment variable only for that test.
- **`tmp_path`** is a temporary directory created by pytest. Reports written there do not touch your real `reports/` folder.
- **`fake_pod_json(...)`** builds a small Pod JSON that looks like real `kubectl get pod -o json` output, either running or waiting.

**What each test checks:**

| # | Test | What it proves |
|---|---|---|
| 1 | `test_metrics_error_is_reported` | When `kubectl top` fails, `get_pod_metrics` returns `ok: False`, `cpu_ram: "Unavailable"`, and keeps the real error. |
| 2 | `test_report_contains_pod_identity_and_metrics` | The report includes the Pod name, namespace, the metrics text, and the AI explanation. |
| 3 | `test_report_marks_missing_metrics` | When metrics fail, the report says "Unavailable", includes the note, and shows "Live metrics could not be retrieved". |
| 4 | `test_healthy_pod_status_is_parsed` | A running Pod's JSON is parsed correctly: name, namespace, phase `Running`, ready `True`, CPU limit `250m`. |
| 5 | `test_broken_pod_status_shows_waiting_reason` | A broken Pod shows phase `Pending`, ready `False`, waiting reason `ImagePullBackOff`. |
| 6 | `test_missing_pod_returns_error` | A "not found" error is returned as `ok: False` with the message. |
| 7 | `test_missing_pod_does_not_create_report` | Running `main.main()` for a missing Pod exits (`SystemExit`) and creates **no** report file. |
| 8–11 | `test_invalid_names_are_rejected` (4 cases) | `""`, `"Bad_Name"`, `"pod;rm -rf"`, and `"-starts-with-dash"` are all rejected with `ValueError`. |
| 12 | `test_report_separates_usage_from_configured_limits` | The report has separate "Actual" and "Configured" sections, and the limits table row is correct. |
| 13 | `test_missing_api_key_gives_clear_message` | With the placeholder key, `explain_incident` returns "AI explanation unavailable" and makes no API call. |
| 14 | `test_last_state_is_recorded_for_restarted_container` | For a crash-looping Pod, `get_pod_status` records `waiting_reason: CrashLoopBackOff`, the restart count, and `last_state` with the previous exit code. |
| 15 | `test_previous_logs_error_is_reported` | `get_pod_previous_logs` really uses `--previous`, and returns `ok: False` with the real error when there is no previous container. |
| 16 | `test_prompt_asks_for_rca_sections` | The prompt asks for the RCA sections (executive summary, timeline, root cause, five whys, corrective and preventive actions, confidence and evidence gaps) and contains the evidence. |
| 17 | `test_report_contains_rca_and_previous_logs` | The report has the RCA title, the "Previous container logs" section with its content, and the "Root cause analysis (AI-generated, advisory)" section. |

#### Run the tests

**Where to run:** `~/agent`, with the venv active.

```bash
cd ~/agent
source .venv/bin/activate
pytest -v
```

Quiet mode:

```bash
pytest -q
```

Run one test:

```bash
pytest -v tests/test_pod_tools.py::test_broken_pod_status_shows_waiting_reason
```

**Expected result.** This output was recorded on this project (the timing will differ on your machine):

```text
collected 17 items

tests/test_pod_tools.py::test_metrics_error_is_reported PASSED           [  5%]
tests/test_pod_tools.py::test_report_contains_pod_identity_and_metrics PASSED [ 11%]
tests/test_pod_tools.py::test_report_marks_missing_metrics PASSED        [ 17%]
tests/test_pod_tools.py::test_healthy_pod_status_is_parsed PASSED        [ 23%]
tests/test_pod_tools.py::test_broken_pod_status_shows_waiting_reason PASSED [ 29%]
tests/test_pod_tools.py::test_missing_pod_returns_error PASSED           [ 35%]
tests/test_pod_tools.py::test_missing_pod_does_not_create_report PASSED  [ 41%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[] PASSED        [ 47%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[Bad_Name] PASSED [ 52%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[pod;rm -rf] PASSED [ 58%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[-starts-with-dash] PASSED [ 64%]
tests/test_pod_tools.py::test_report_separates_usage_from_configured_limits PASSED [ 70%]
tests/test_pod_tools.py::test_missing_api_key_gives_clear_message PASSED [ 76%]
tests/test_pod_tools.py::test_last_state_is_recorded_for_restarted_container PASSED [ 82%]
tests/test_pod_tools.py::test_previous_logs_error_is_reported PASSED     [ 88%]
tests/test_pod_tools.py::test_prompt_asks_for_rca_sections PASSED        [ 94%]
tests/test_pod_tools.py::test_report_contains_rca_and_previous_logs PASSED [100%]

============================== 17 passed in 4.72s ==============================
```

### Part B — Real investigation on the cluster

#### Step 8.1 — Start the Kubernetes cluster

If the cluster already exists but is stopped (for example, after a reboot):

```bash
k3d cluster list
k3d cluster start pod-lab
kubectl get nodes
```

If it does not exist, create it (Phase 2):

```bash
k3d cluster create pod-lab --agents 1 --servers 1
kubectl create namespace ai-sre-lab
```

Both nodes must be `Ready` before you continue.

#### Step 8.2 — Deploy the healthy HTTPD application

```bash
kubectl apply -f ~/agent/k8s/demo.yaml
kubectl rollout status deployment/demo-web -n ai-sre-lab
kubectl get deployment,pods,service -n ai-sre-lab
kubectl top pod -n ai-sre-lab
```

Copy the exact `demo-web-...` Pod name. Wait until `kubectl top` shows numbers (this can take a minute after the Pod starts). Optionally confirm the application responds with the port-forward and `curl` check from [Step 2.7](#step-27--deploy-and-check-the-application).

You can also store the Pod name in a shell variable so you do not have to copy it:

```bash
POD=$(kubectl get pods -n ai-sre-lab -l app=demo-web -o jsonpath='{.items[0].metadata.name}')
echo $POD
```

#### Step 8.3 — Run the agent against the healthy Pod

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod $POD --namespace ai-sre-lab
```

(Or type the Pod name instead of `$POD`.)

Recorded terminal output (long lines and the middle of the JSON are shortened with `...`):

```text
Investigating pod demo-web-665f97df4c-mj54n in namespace ai-sre-lab (read-only).

[1/5] Checking pod status with LangChain tool...
{
  "ok": true,
  "name": "demo-web-665f97df4c-mj54n",
  "namespace": "ai-sre-lab",
  "phase": "Running",
  "node": "k3d-pod-lab-agent-0",
  "pod_ip": "10.42.1.4",
  "created": "2026-10-30T21:15:54Z",
  "labels": {
    "app": "demo-web",
    "pod-template-hash": "665f97df4c"
  },
  "containers": [
    {
      "name": "httpd",
      "ready": true,
      "restart_count": 0,
      "waiting_reason": "",
      ...
  "configured_resources": [
    {
      "container": "httpd",
      "image": "httpd:2.4",
      "cpu_request": "50m",
      "cpu_limit": "250m",
      "memory_request": "64Mi",
      "memory_limit": "128Mi"
    }
  ],
  "owner_references": [
    {
      ...
      "kind": "ReplicaSet",
      "name": "demo-web-665f97df4c",
      ...
}

[2/5] Reading logs with LangChain tool...
{'ok': True, 'logs': 'AH00558: httpd: Could not reliably determine the server\'s fully qualified domain name, ...'}

[3/5] Reading events with LangChain tool...
{'ok': True, 'events': 'LAST SEEN   TYPE     REASON      OBJECT ...'}

[4/5] Reading CPU/RAM with LangChain tool...
{'ok': True, 'cpu_ram': 'POD                         NAME    CPU(cores)   MEMORY(bytes)   \ndemo-web-665f97df4c-mj54n   httpd   1m           6Mi'}

[5/5] Collecting full evidence and asking Claude for a root cause analysis...

Report created successfully:
reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_041322.md

Open it with:
cat reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_041322.md
```

The `owner_references` show that the Pod is controlled by the ReplicaSet `demo-web-665f97df4c`, which belongs to the `demo-web` Deployment. With a real API key, step 5 takes longer (up to a minute or more) because it waits for Claude's full response.

#### Step 8.4 — Verify the healthy report

```bash
ls -lh ~/agent/reports
cat ~/agent/reports/incident_ai-sre-lab_<POD_NAME>_<TIMESTAMP>.md
```

Use the exact path printed by the program. Key parts of the recorded healthy reports. The events are from the RCA run about an hour after the Pod started (`reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_041322.md`); the start-up events had already expired by then, which is normal:

```text
- **Pod name:** demo-web-665f97df4c-mj54n
- **Namespace:** ai-sre-lab
- **Status:** Running
- **Node:** k3d-pod-lab-agent-0
- **Pod IP:** 10.42.1.4

## Actual CPU and RAM usage (live, from kubectl top)
POD                         NAME    CPU(cores)   MEMORY(bytes)
demo-web-665f97df4c-mj54n   httpd   1m           6Mi

## Configured CPU and RAM (requests and limits from the pod spec)
| httpd | 50m | 250m | 64Mi | 128Mi |

## Kubernetes events
FIRST_SEEN             LAST_SEEN              COUNT   TYPE      REASON                 SOURCE                      MESSAGE
2026-10-30T21:58:45Z   2026-10-30T21:58:45Z   1       Warning   NodeNotReady           node-controller             Node is not ready
2026-10-30T21:58:56Z   2026-10-30T21:58:56Z   1       Normal    TaintManagerEviction   taint-eviction-controller   Cancelling deletion of Pod ai-sre-lab/demo-web-665f97df4c-mj54n

## Recent logs
AH00558: httpd: Could not reliably determine the server's fully qualified domain name, using 10.42.1.4. Set the 'ServerName' directive globally to suppress this message
AH00558: httpd: Could not reliably determine the server's fully qualified domain name, using 10.42.1.4. Set the 'ServerName' directive globally to suppress this message
[Fri Oct 30 21:17:05.029354 2026] [mpm_event:notice] [pid 1:tid 1] AH00489: Apache/2.4.69 (Unix) configured -- resuming normal operations
[Fri Oct 30 21:17:05.070251 2026] [core:notice] [pid 1:tid 1] AH00094: Command line: 'httpd -D FOREGROUND'
127.0.0.1 - - [30/Oct/2026:21:17:24 +0000] "GET / HTTP/1.1" 200 191
10.42.1.5 - - [30/Oct/2026:21:17:39 +0000] "GET / HTTP/1.1" 200 191

## Previous container logs (before the last restart)
Error from server (BadRequest): previous terminated container "httpd" in pod "demo-web-665f97df4c-mj54n" not found
```

The previous-logs error is expected: the `httpd` container has never restarted, so there is no previous run.

**How to read the HTTPD logs:**

| Log line | Meaning | Problem? |
|---|---|---|
| `AH00558: ... Could not reliably determine the server's fully qualified domain name` | HTTPD has no `ServerName` setting, so it uses the Pod IP. This is a normal start-up message for the default `httpd` image. | No. It is informational. |
| `AH00489: Apache/2.4.69 (Unix) configured -- resuming normal operations` | HTTPD started successfully. | No |
| `AH00094: Command line: 'httpd -D FOREGROUND'` | HTTPD runs in the foreground, as a container's main process must. | No |
| `"GET / HTTP/1.1" 200 191` | Access log: a request for `/` returned HTTP 200 with 191 bytes. These come from the `curl` and BusyBox checks in Step 2.7. | No |

This is a good example of why the RCA prompt asks Claude to separate **confirmed observations** from conclusions: a log line can look like a warning without indicating an incident.

Check that:

- [ ] Pod name and namespace are correct.
- [ ] Status is `Running` and the `httpd` container is `ready: true` with `restart_count: 0`.
- [ ] Live usage shows real numbers (or "Unavailable" with a reason).
- [ ] Configured requests and limits match `k8s/demo.yaml` (`50m`/`250m`, `64Mi`/`128Mi`).
- [ ] Events show `Scheduled`, `Pulling`, `Pulled`, `Created`, `Started` with absolute UTC times (if they have not expired yet; Kubernetes keeps events for about one hour).
- [ ] Logs show HTTPD start-up lines (and access log lines if you sent requests).
- [ ] The "Root cause analysis" section is present (for a healthy Pod it should say **No incident detected**), or it clearly says why AI was unavailable.

**What Claude's RCA said in the recorded healthy report** (`reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_041322.md`):

- **Root cause: "No incident detected" for this pod.** The Pod never failed, restarted, or was evicted, and it served HTTP 200 responses before and after the node event. Claude did **not** invent a root cause.
- **A real event on the timeline:** node `k3d-pod-lab-agent-0` was reported `NotReady` at **21:58:45Z**, and the pending eviction of this Pod was cancelled 11 seconds later at **21:58:56Z**. The absolute event timestamps made this precise timeline possible.
- **Honest confidence:** **High** that the Pod is healthy. **Low** on why the node became NotReady, because no node-level evidence was collected. Claude listed node conditions and k3s agent logs as the evidence that would raise confidence.
- **`AH00558` is cosmetic**, normal for a default httpd image.

This is a good example of the agent's value. A "healthy" Pod still had a short node problem in its history. The agent surfaced it with honest confidence levels, and changed nothing.

#### Step 8.5 — Deploy the deliberately broken Pod

**File: `agent/k8s/broken-pod.yaml`**

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
      image: httpd:tag-that-does-not-exist
```

**Explanation:**

- `kind: Pod` — a bare Pod, not a Deployment. It has a fixed name (`broken-image-demo`), which makes it easy to investigate.
- `image: httpd:tag-that-does-not-exist` — the `httpd` repository exists, but this tag does not. The image pull will fail.
- No `resources` block, so the report's configured table shows `Not set`, and the Pod's QoS class is `BestEffort`.
- Its label is `app: broken-image-demo`, so the `demo-web` Service does **not** send traffic to it, and it does not affect the healthy Deployment.

```bash
kubectl apply -f ~/agent/k8s/broken-pod.yaml
kubectl get pod broken-image-demo -n ai-sre-lab -w
```

`-w` watches for status changes. Wait until the status becomes `ErrImagePull` or `ImagePullBackOff`, then press `Ctrl+C`.

#### Step 8.6 — Check its Kubernetes status

```bash
kubectl get pod broken-image-demo -n ai-sre-lab
kubectl logs broken-image-demo -n ai-sre-lab
kubectl top pod broken-image-demo -n ai-sre-lab
kubectl describe pod broken-image-demo -n ai-sre-lab | tail -15
```

Recorded output of the first three commands:

```text
NAME                READY   STATUS             RESTARTS   AGE
broken-image-demo   0/1     ImagePullBackOff   0          18s

Error from server (BadRequest): container "web" in pod "broken-image-demo" is waiting to start: trying and failing to pull image

Error from server (NotFound): pods "broken-image-demo" not found
```

**Understanding the statuses:**

| Status | Meaning |
|---|---|
| `ContainerCreating` | Kubernetes is preparing the container (pulling the image). |
| `ErrImagePull` | The image pull just **failed**. |
| `ImagePullBackOff` | Kubernetes is **waiting before retrying** the pull. The wait time grows after each failure (up to five minutes). |

The status switches between `ErrImagePull` and `ImagePullBackOff` while Kubernetes keeps retrying. The Pod phase stays `Pending` because the container never started.

**Expect missing data:** Because the container never started:

- `kubectl logs` fails with a "waiting to start" error. **There are no application logs.**
- `kubectl top` fails with `NotFound`. The Pod object exists, but Metrics Server has no measurements for it because no container is running. **There are no live CPU/RAM metrics.**

This is normal, and the agent records it honestly.

#### Step 8.7 — Run the agent against the broken Pod

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod broken-image-demo --namespace ai-sre-lab
```

Recorded output from step 2 onward (step 1 printed the Pod status JSON; long lines shortened with `...`):

```text
[2/5] Reading logs with LangChain tool...
{'ok': False, 'error': 'Error from server (BadRequest): container "web" in pod "broken-image-demo" is waiting to start: trying and failing to pull image'}

[3/5] Reading events with LangChain tool...
{'ok': True, 'events': 'LAST SEEN   TYPE      REASON      OBJECT ...'}

[4/5] Reading CPU/RAM with LangChain tool...
{'ok': False, 'cpu_ram': 'Unavailable', 'note': 'kubectl top failed. Metrics Server may not be installed, may not be ready, or the pod may not have metrics yet.', 'error': 'Error from server (NotFound): pods "broken-image-demo" not found'}

[5/5] Collecting full evidence and asking Claude for a root cause analysis...

Report created successfully:
reports/incident_ai-sre-lab_broken-image-demo_20261031_041222.md

Open it with:
cat reports/incident_ai-sre-lab_broken-image-demo_20261031_041222.md
```

Step `[1/5]` succeeds because the Pod object exists. Steps `[2/5]` and `[4/5]` return `ok: False`. This is expected: the program continues and records these failures as evidence.

#### Step 8.8 — Verify the broken Pod report

Open the report path printed by the program. Check that:

- [ ] Status is `Pending`.
- [ ] Container state shows `ready: false` and `waiting_reason: "ImagePullBackOff"` (or `ErrImagePull`), with the pull error message.
- [ ] Live CPU/RAM is `Unavailable`, with "Live metrics could not be retrieved" and the real Kubernetes error.
- [ ] The configured table shows `Not set` for every value.
- [ ] Events show `Failed to pull image "httpd:tag-that-does-not-exist" ... NotFound`, `ErrImagePull`, and `ImagePullBackOff`.
- [ ] Recent logs show the "waiting to start" error, not application logs.
- [ ] If the AI is configured, the RCA says **Confirmed root cause:** the image tag `httpd:tag-that-does-not-exist` does not exist, with **High** confidence.
- [ ] The previous-logs section shows an error: the container never started, so there is no previous run.

Key lines from the recorded RCA (`reports/incident_ai-sre-lab_broken-image-demo_20261031_041222.md`), shortened:

```markdown
### 1. Executive summary
The `web` container in pod `ai-sre-lab/broken-image-demo` has never started because the kubelet cannot pull
the image `httpd:tag-that-does-not-exist`. The registry returned `NotFound` for
`docker.io/library/httpd:tag-that-does-not-exist`, so the image reference points to a tag that does not exist. [...]

### 6. Root cause
**Confirmed root cause:** The pod spec references the image tag `httpd:tag-that-does-not-exist`. That tag does
not exist in `docker.io/library/httpd`.
- The container runtime's pull failed with `code = NotFound ... failed to resolve reference ... not found`.
- The kubelet therefore entered exponential back-off (`ImagePullBackOff`).
- The container has never been created as a result.

### 12. Confidence level and evidence gaps
**Confidence: High** for the root cause. The container status contains the runtime's explicit `NotFound` error
for the exact image reference. [...]
```

A complete RCA example (crash-looping Pod) is shown in [Example RCA report](#example-rca-report-crash-looping-pod) in Phase 6.

#### Step 8.9 — RCA of a crash-looping Pod

`ImagePullBackOff` is a failure where the container never starts. The second common failure is **`CrashLoopBackOff`**: the container starts, crashes, and Kubernetes keeps restarting it. This test shows how the RCA uses the **previous container state** (`last_state`) and the crash logs.

**File: `agent/k8s/crashloop-pod.yaml`**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: crashloop-demo
  namespace: ai-sre-lab
  labels:
    app: crashloop-demo
spec:
  containers:
    - name: app
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "Starting payment-api v1.4.2"
          echo "Loading configuration from /etc/app/config.yaml"
          echo "ERROR: configuration file /etc/app/config.yaml not found" >&2
          exit 1
      resources:
        requests:
          cpu: "10m"
          memory: "16Mi"
        limits:
          cpu: "100m"
          memory: "32Mi"
```

**Explanation:**

- `image: busybox:1.36` — a tiny image with a shell. It simulates an application.
- `command:` — a shell script that prints start-up lines, prints a config error to stderr, and exits with code `1` (failure).
- A bare Pod uses `restartPolicy: Always` by default, so Kubernetes restarts the container after every exit, with an increasing delay. This produces `CrashLoopBackOff`.
- The script **always** exits 1. It does not actually check for the file. This is deliberate: it tests whether the RCA reads the evidence carefully instead of trusting the error message.
- `resources` are set, so the report shows a configured table and the Pod is `Burstable`.

**Deploy it and watch it crash:**

```bash
kubectl apply -f ~/agent/k8s/crashloop-pod.yaml
kubectl get pod crashloop-demo -n ai-sre-lab -w
```

Wait until `RESTARTS` is 3 or more (about one minute), then press `Ctrl+C`. The `STATUS` column changes between `Error`, `CrashLoopBackOff`, and (briefly) `Running`.

Recorded output:

```text
NAME             READY   STATUS   RESTARTS      AGE
crashloop-demo   0/1     Error    3 (30s ago)   52s
```

**Check the crash logs by hand:**

```bash
kubectl logs crashloop-demo -n ai-sre-lab
kubectl logs crashloop-demo -n ai-sre-lab --previous
```

Recorded output:

```text
Starting payment-api v1.4.2
Loading configuration from /etc/app/config.yaml
ERROR: configuration file /etc/app/config.yaml not found

unable to retrieve container logs for containerd://d444ce82359c263fd4a9165bc1ed0774d51b816a164690950d8260d9e8dfa476
```

The `--previous` error is a timing effect: while the crashed container waits for its next restart, the regular logs already show the last crash, and the older run may already be removed. Try again a few seconds later and you may get the previous logs. The agent collects both, so either way the crash output is in the report.

**Run the RCA:**

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod crashloop-demo --namespace ai-sre-lab
```

Recorded output (step lines only):

```text
[1/5] Checking pod status with LangChain tool...
[2/5] Reading logs with LangChain tool...
[3/5] Reading events with LangChain tool...
[4/5] Reading CPU/RAM with LangChain tool...
[5/5] Collecting full evidence and asking Claude for a root cause analysis...
reports/incident_ai-sre-lab_crashloop-demo_20261031_041101.md
```

**Verify the crash-loop RCA report.** Check that:

- [ ] **Status** is `Running`. This is correct Kubernetes behaviour for a restarting container; the real problem is in Container state.
- [ ] **Container state** shows `restart_count` of 3 or more, `terminated` with `exitCode: 1`, and `last_state` with another `exitCode: 1`.
- [ ] **Events** show `Started` and `BackOff` with `COUNT` greater than 1 and absolute times.
- [ ] **Recent logs** (or **Previous container logs**) show `ERROR: configuration file /etc/app/config.yaml not found`.
- [ ] The **RCA** identifies the unconditional `exit 1` in the container command as the **confirmed root cause**, rules out `OOMKilled` (reason is `Error`), and marks all fixes as requiring human approval.

The recorded report is shown in full (shortened) in [Example RCA report](#example-rca-report-crash-looping-pod) in Phase 6. In that run, Claude also noticed that the "config file not found" message is a hard-coded `echo`, so mounting a config file alone would not fix the Pod.

#### Step 8.10 — Compare the three RCA reports

All values below are from the recorded RCA reports.

| Check | Healthy (`demo-web-...`) | Broken image (`broken-image-demo`) | Crash loop (`crashloop-demo`) |
|---|---|---|---|
| Status (phase) | `Running` | `Pending` | `Running` (restarting) |
| Container | `httpd`, ready `true`, restarts 0 | `web`, ready `false`, restarts 0 | `app`, ready `false`, restarts 3 |
| Current state | `running` | `waiting`: `ImagePullBackOff` | `terminated`: `Error`, exit code 1 |
| `last_state` | empty | empty | `terminated`: `Error`, exit code 1 |
| Live CPU/RAM | `1m` CPU, `6Mi` memory | `Unavailable` | `Unavailable` |
| Configured requests/limits | `50m`/`250m`, `64Mi`/`128Mi` | `Not set` | `10m`/`100m`, `16Mi`/`32Mi` |
| Logs | HTTPD start-up + access lines | "waiting to start" error | the crash output with the config error |
| Previous logs | none (never restarted) | none (never started) | timing error in the recorded run |
| **RCA root cause** | **No incident detected** | **Confirmed:** image tag does not exist | **Confirmed:** command always runs `exit 1` |
| **RCA confidence** | High (Pod healthy); Low (node blip cause) | High | High (cause); Low (intent, impact) |

#### Step 8.11 — Test error handling (missing Pod and invalid name)

```bash
python main.py --pod pod-that-does-not-exist --namespace ai-sre-lab
python main.py --pod Bad_Name --namespace ai-sre-lab
```

Recorded output:

```text
Investigating pod pod-that-does-not-exist in namespace ai-sre-lab (read-only).

[1/5] Checking pod status with LangChain tool...
Could not inspect pod: Error from server (NotFound): pods "pod-that-does-not-exist" not found
Check the pod name and namespace using: kubectl get pods -n ai-sre-lab
```

```text
Invalid pod name: 'Bad_Name'
Names may only use lowercase letters, numbers, '-' and '.'.
```

In both cases, the program exits with code 1 and **no report is created**. In the recorded run, `ls reports/` showed no new file after these commands.

#### Step 8.12 — Clean up the test Pods

This is a manual step by you. The agent never deletes anything.

```bash
kubectl delete pod broken-image-demo -n ai-sre-lab
kubectl delete pod crashloop-demo -n ai-sre-lab
```

This removes only the two deliberately broken test Pods. The healthy Deployment keeps running.

To delete the whole lab cluster when you are finished:

```bash
k3d cluster delete pod-lab
```

---

## Troubleshooting

Each issue lists: what it means, how to identify it, how to fix it, and how to verify the fix.

### 1. Docker service not running

- **Meaning:** The Docker daemon is stopped, so k3d cannot start node containers.
- **Identify:** `docker ps` shows `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`. `docker version` shows only a Client section.
- **Fix:**

  ```bash
  sudo systemctl enable --now docker
  sudo systemctl status docker --no-pager
  sudo journalctl -u docker --no-pager | tail -30
  ```

  If you get `permission denied` on `/var/run/docker.sock`, use `sudo` or add your user to the `docker` group and log in again.
- **Verify:** `docker ps` prints a header without errors.

### 2. k3d cluster creation failure

- **Meaning:** k3d could not create the containers or network.
- **Identify:** `k3d cluster create` exits with an error, such as "cluster already exists", "port is already allocated", or Docker connection errors.
- **Fix:**
  - Docker must be running (issue 1).
  - If the cluster already exists: `k3d cluster list`, then `k3d cluster start pod-lab`, or delete and recreate it with `k3d cluster delete pod-lab`.
  - Check free disk space: `df -h /var/lib/docker`.
  - Check what is left over: `docker ps -a | grep k3d`.
- **Verify:** `k3d cluster list` shows `pod-lab` with `1/1` servers and `1/1` agents, and `kubectl get nodes` shows two `Ready` nodes.

### 3. kubectl connection errors

- **Meaning:** `kubectl` cannot reach the Kubernetes API server.
- **Identify:** `The connection to the server 0.0.0.0:<port> was refused`, or `kubectl get nodes` hangs. The agent prints `Could not inspect pod: ...` with the same error.
- **Fix:**

  ```bash
  k3d cluster list                       # is the cluster there and running?
  k3d cluster start pod-lab              # start it if stopped (e.g. after reboot)
  kubectl config get-contexts            # is k3d-pod-lab present?
  kubectl config use-context k3d-pod-lab
  k3d kubeconfig merge pod-lab --kubeconfig-switch-context   # rewrite kubeconfig if needed
  ```

- **Verify:** `kubectl get nodes` lists both nodes as `Ready`.

### 4. Pod stuck in Pending

- **Meaning:** The Pod exists but no container is running yet. It may not be scheduled, or the image cannot be pulled.
- **Identify:** `kubectl get pod <pod> -n ai-sre-lab` shows `Pending`. In the agent's report, look at **Node** (`Not scheduled` means scheduling failed), **Container state**, and **Events**.
- **Fix:** Read the events: `kubectl describe pod <pod> -n ai-sre-lab`.
  - `FailedScheduling` with `Insufficient cpu` or `Insufficient memory` — the requests are too large for the nodes. Check with `kubectl describe nodes`.
  - A waiting reason of `ErrImagePull` or `ImagePullBackOff` — see issue 5.
- **Verify:** After a human fixes the cause, the Pod reaches `Running`.

### 5. ImagePullBackOff / ErrImagePull

- **Meaning:** Kubernetes cannot download the container image.
- **Identify:** Status `ErrImagePull` or `ImagePullBackOff`. Events contain `Failed to pull image`. The report shows `waiting_reason: "ImagePullBackOff"`.
- **Fix:** Check the image name and tag (`kubectl get pod <pod> -n ai-sre-lab -o jsonpath='{.spec.containers[*].image}'`). Check that the node has internet access, and whether the registry needs credentials (`imagePullSecrets`). For `broken-image-demo`, the failure is intentional.
- **Verify:** After the image reference is corrected and the Pod is recreated, the events show `Pulled` and `Started`.

### 6. CrashLoopBackOff

- **Meaning:** The container starts and then exits again and again. Kubernetes waits longer between each restart.
- **Identify:** Status `CrashLoopBackOff` (or `Error` between restarts). `restart_count` increases. In the report, Container state shows `waiting_reason: "CrashLoopBackOff"` or a `terminated` state, and `last_state` shows the previous exit code and reason.
- **Troubleshoot:** Run the agent; its RCA uses `last_state`, current logs, and previous logs. To check by hand:

  ```bash
  kubectl logs <pod> -n ai-sre-lab --previous
  kubectl describe pod <pod> -n ai-sre-lab | grep -A5 "Last State"
  ```

  A `Last State` reason of `OOMKilled` means the container hit its memory limit. A reason of `Error` with a non-zero exit code means the application itself exited with a failure. If `--previous` says `unable to retrieve container logs`, wait a few seconds and try again; the regular `kubectl logs` usually shows the last crash in the meantime. See [Step 8.9](#step-89--rca-of-a-crash-looping-pod) for a full example.
- **Verify:** After the fix, the Pod stays `Running` and the restart count stops increasing.

### 7. Missing Kubernetes metrics

- **Meaning:** `kubectl top` cannot get data, so the report shows CPU/RAM as `Unavailable`.
- **Identify:** The report says **"Live metrics could not be retrieved."** and includes the Kubernetes error, for example `Metrics API not available` or `metrics not available yet`.
- **Fix:**

  ```bash
  kubectl -n kube-system get deployment metrics-server
  kubectl -n kube-system logs deployment/metrics-server | tail -20
  kubectl top nodes
  ```

  - If the Pod started recently, wait a minute.
  - If the container is not running (for example, `ImagePullBackOff`), there is nothing to measure. This is expected.
  - If `metrics-server` is missing, install it from the official release manifest (as described in `manual.docs`):

    ```bash
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
    kubectl -n kube-system rollout status deployment/metrics-server --timeout=120s
    ```

    If it then fails with kubelet certificate errors, the manual describes `--kubelet-insecure-tls` as a workaround **for a disposable local lab only**. It weakens certificate checks and must never be used in production.
- **Verify:** `kubectl top pod -n ai-sre-lab` shows numbers, and a new report shows a live usage table.

### 8. Python dependency errors

- **Meaning:** A required package is missing, or the wrong Python is being used.
- **Identify:** `ModuleNotFoundError: No module named 'anthropic'` (or `langchain_core`, `dotenv`).
- **Fix:**

  ```bash
  cd ~/agent
  source .venv/bin/activate
  which python            # must point inside .venv
  pip install -r requirements.txt
  ```

  If the venv is broken, recreate it: `rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- **Verify:** `python -c "import anthropic, langchain_core, dotenv; print('imports OK')"`.

### 9. Missing environment variables

- **Meaning:** `.env` is missing, in the wrong place, or incomplete.
- **Identify:** The report's AI section says `set a valid ANTHROPIC_API_KEY in .env` or `set ANTHROPIC_MODEL in .env`.
- **Fix:**

  ```bash
  cd ~/agent
  ls -la .env                                   # must exist in the project folder
  grep -o '^[A-Z_]*=' .env                      # show variable names only (not values)
  ```

  Make sure `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` are present, with no spaces around `=`. Also check that an old shell variable is not overriding `.env`: `env | grep -o '^ANTHROPIC_[A-Z_]*'`. If one is listed, run `unset ANTHROPIC_API_KEY` (or the model variable) and try again.
- **Verify:** A new report contains Claude's analysis instead of the "unavailable" message.

### 10. Invalid Claude API key

- **Meaning:** The API rejected the key (HTTP 401).
- **Identify:** The report says `the API key was rejected. Check ANTHROPIC_API_KEY.`
- **Fix:** Create a new key in the Anthropic Console, paste it into `.env` with no quotes or extra spaces, and check that the key's workspace is active and has billing set up.
- **Verify:** Run the connection check from Phase 5, or generate a new report.

### 11. Claude API errors

- **Identify and fix by message:**

  | Message in the report | Meaning | Fix |
  |---|---|---|
  | `model '...' was not found` | The model ID is wrong or not available to your account | Set `ANTHROPIC_MODEL` to a model ID listed in your Anthropic Console |
  | `rate limit or quota reached` | Too many requests, or spending limit reached | Wait and retry; check usage limits and billing |
  | `could not connect to the Claude API` | Network, DNS, proxy, or firewall problem | `curl -I https://api.anthropic.com` from the host; check proxy settings |
  | `API error <code>: <message>` | Another API error (e.g. 400, 500, 529 overloaded) | Read the message; for 5xx/529, retry later |
  | `Claude declined this request.` | The model refused | Check the evidence content; retry |

- **Verify:** A new report contains the twelve-section RCA.

### 12. Report generation failures

- **Meaning:** The report file could not be written, or it was written somewhere unexpected.
- **Identify:** A Python traceback with `PermissionError` or `OSError` after step `[5/5]`, or the report is not in `~/agent/reports`.
- **Fix:**
  - Run from the project folder (`cd ~/agent`), because `REPORT_DIR=reports` is relative.
  - Check write permission: `ls -ld reports` and `touch reports/test && rm reports/test`.
  - Check disk space: `df -h .`.
  - Check `REPORT_DIR` in `.env`.
- **Verify:** `ls -lh reports/` shows a new `incident_<ns>_<pod>_<timestamp>.md` file.

### 13. pytest failures

- **Meaning:** A test assertion failed, or tests cannot import the project modules.
- **Identify:** `pytest -v` shows `FAILED` or `ModuleNotFoundError: No module named 'pod_tools'`.
- **Fix:**
  - Run pytest from the project root (`~/agent`), where `pytest.ini` is located. `pythonpath = .` only applies from there.
  - Activate the venv.
  - Read the first traceback line that points to a project file. If you changed messages in the code (for example, "Live metrics could not be retrieved"), the tests that check that text will fail.
  - Run one test with more detail: `pytest -v tests/test_pod_tools.py::<test_name>`.
- **Verify:** `pytest -q` reports `17 passed`.

---

## Security and Project Limitations

### Protecting the API key

- The key lives only in `agent/.env`, which is listed in `.gitignore`.
- `chmod 600 .env` makes the file readable only by your user.
- The code never prints or logs the key.
- Commit `.env.example` (placeholder values) and **never** commit `.env`.
- Before your first commit, check:

  ```bash
  git init          # only if this is not yet a Git repository
  git status --ignored
  ```

  `.env` must be listed under "Ignored files", not under "Untracked files".
- If a key was ever committed or shared, **revoke it** in the Anthropic Console. Deleting the file from Git is not enough, because the key stays in Git history.

### Report contents

Reports contain logs, Pod IPs, node names, and `describe` output. They are ignored by Git (`reports/*.md`) for this reason. Review a report before sharing it outside your team. The same evidence is sent to the Claude API, so do not run the agent against Pods whose logs contain data that your organisation does not allow to be sent to an external service.

### Why the agent is read-only

- It only runs `kubectl get`, `logs`, `top`, and `describe`. None of these change the cluster.
- Claude receives text and returns text. It has no shell, no `kubectl`, and no write access.
- An AI model can be wrong. Its analysis can sound confident and still be incorrect. Changes to a cluster can cause outages, so a human must review the evidence and decide.
- For extra safety, run the agent with a Kubernetes identity that only has read (`get`, `list`, `watch`) permissions on Pods, Pod logs, events, and metrics.

### What the agent can do

- Investigate one Pod per run in a chosen namespace.
- Collect Pod status, container states, waiting reasons, restart counts, node, IP, labels, and owner.
- Read the last 80 log lines from all containers.
- Read events for the Pod.
- Read live CPU/RAM usage when Metrics Server provides it.
- Read configured CPU/memory requests and limits.
- Ask Claude for a structured Root Cause Analysis: timeline, confirmed observations, root cause (confirmed or not), five whys, corrective and preventive actions, and confidence level.
- Say "No incident detected" for a healthy Pod instead of inventing a root cause.
- Save a timestamped Markdown report, even when the AI is unavailable.
- Reject unsafe or invalid names, and refuse to create a report for a Pod that does not exist.

### What the agent cannot do (in this implementation)

- It does **not** restart, delete, scale, patch, roll back, or repair anything. It is **not** a self-healing system.
- It does **not** let Claude choose or run tools. The tool order is fixed in `main.py`.
- It does **not** investigate a whole Deployment, Service, node, or namespace at once. It investigates one Pod at a time.
- It does **not** monitor continuously or send alerts. It runs once when you start it.
- It does **not** estimate CPU/RAM when metrics are unavailable.
- It does **not** include a "safety checkpoint before restart" (the manual mentions one), because no restart feature exists.

---

## Quick Reference

```bash
# Start lab
k3d cluster start pod-lab            # or: k3d cluster create pod-lab --agents 1 --servers 1
kubectl get nodes

# Workloads
kubectl apply -f ~/agent/k8s/demo.yaml
kubectl apply -f ~/agent/k8s/broken-pod.yaml
kubectl get pods -n ai-sre-lab -o wide

# Agent
cd ~/agent && source .venv/bin/activate
python main.py --pod <POD_NAME> --namespace ai-sre-lab
python main.py --namespace ai-sre-lab          # choose from a list
ls -lh reports/

# Tests
pytest -v

# Clean up
kubectl delete pod broken-image-demo -n ai-sre-lab
k3d cluster delete pod-lab
```

---

## Appendix A — Differences Between manual.docs and the Current Code

The project files have evolved beyond the code printed in `manual.docs`. This README documents the **current files**. The main differences are:

| Area | `manual.docs` | Current project files |
|---|---|---|
| `pod_tools.py` | No `list_pods()` or `get_configured_resources()`; no `waiting_reason`; unused `from pathlib import Path`; no handling for invalid JSON | All of these are added; invalid JSON returns a clear error |
| `claude_client.py` | Single prompt inside `explain_incident()`; evidence cut at 18,000 characters; `max_tokens=900`; one catch-all `except Exception` | Separate `build_prompt()`; full evidence; `max_tokens=8000`; specific API error handling; refusal check; twelve-section RCA prompt |
| `reporting.py` | One combined CPU/RAM section | Separate "Actual usage" and "Configured requests/limits" sections; UTC collection time; clearer missing-metrics note |
| `main.py` | `--pod` is required | `--pod` is optional; `choose_pod()` lists Pods; friendly error on invalid names |
| Tests | 3 tests, NGINX sample data | 17 test cases (14 test functions, one parametrised ×4), HTTPD sample data, RCA tests |
| AI output | General explanation | Structured 12-section Root Cause Analysis |
| Evidence | Current logs, events with relative ages | Adds previous container state (`last_state`), previous container logs, and events with absolute UTC timestamps |
| Crash test Pod | Not included | `k8s/crashloop-pod.yaml` |
| Model in `.env` | `claude-3-5-sonnet-latest` | `.env.example` uses `claude-opus-5-5`; always confirm availability in your account |
| Demo application (`k8s/demo.yaml`) | NGINX (`nginx:stable`) Deployment only | Apache HTTPD (`httpd:2.4`) Deployment **and** a `ClusterIP` Service, both named `demo-web` |
| Broken Pod image | `nginx:tag-that-does-not-exist` | `httpd:tag-that-does-not-exist` |
| Project folder | `~/pod-investigation-agent` | This project is in `agent/` (`~/agent` in this guide) |
| `pytest.ini` | Not mentioned | Present (`pythonpath = .`) |
| `.env.example` | Not mentioned | Present |
| Phase numbering | Phase 6 = workflow, 7 = tests, 8 = live report | This README follows the phase structure requested for the documentation |

---

## Appendix B — Known Gaps and Items Not Implemented

These items are mentioned in the manual or are common expectations, but they are **not** in the current project. They are listed here instead of being invented:

1. **Metrics Server installation** is not automated. k3s includes it by default (confirmed in the recorded run). The manual's install steps are summarised in Troubleshooting issue 7.
2. **Restart safety checkpoint.** `manual.docs` mentions "a safety checkpoint before any restart action". No restart action exists, so there is no checkpoint.
3. **`create_report()` tool.** The manual lists it as an example tool name. The actual function is `reporting.create_markdown_report()`, and it is not a LangChain tool.
4. **Model-driven tool selection.** The LangChain tools are defined but are called by Python in a fixed order. They are not bound to Claude.
5. **Previous-container logs can be missed by timing.** `kubectl logs --previous` is collected, but while a crashed container waits to restart, the older run may already be removed. The current logs then contain the crash output instead.
6. **`K8S_NAMESPACE`** has no effect when running `main.py`, because `main.py` and `agent_tools.py` use their own default `ai-sre-lab`. Use `--namespace`.
7. **Pinned dependency versions.** `requirements.txt` is unpinned. The tested versions are listed in Phase 3.
8. **Service investigation.** The demo application has a Service, but the agent investigates Pods only. It does not check Services, endpoints, or Ingress.
9. **AI output varies.** Claude's analysis is generated fresh on every run, so wording, structure details, and length differ between runs even for the same Pod. The twelve requested RCA sections are always asked for, but not enforced by code.
10. **Docker, kubectl, and k3d install steps** are not specified in detail in `manual.docs`; it refers to the official instructions. The commands in Phase 1 follow those official sources and may need adjusting as upstream instructions change.
