# LW-RCA-analyzer

**An AI agent that investigates a Kubernetes Pod and writes a Root Cause Analysis (RCA) report**

RHEL 10 · k3d · Kubernetes · Python · LangChain · Claude API · pytest

This guide builds **LW-RCA-analyzer** step by step, from an empty RHEL 10 machine to a working AI agent. It explains **what** we build and **how** we build it. Every file is shown in full, with its exact path and a simple explanation.

> **How this guide was tested:** Every command, file, and output in this guide was run on RHEL 10.0 with k3d v5.9.0, k3s v1.35.5, Python 3.12.9, `anthropic` 2.3.0, and `langchain-core` 1.7.3, on 30–31 October 2026. The project was rebuilt from this README alone, and all tests passed. Outputs marked **"Recorded output"** are real. Pod names, IP addresses, times, and Claude's wording will be different on your machine.

---

## Table of Contents

- [Part 1 — What Are We Building?](#part-1--what-are-we-building)
- [Part 2 — The Technologies](#part-2--the-technologies)
- [Part 3 — How LW-RCA-analyzer Works](#part-3--how-lw-rca-analyzer-works)
- [Part 4 — Project Folder Structure](#part-4--project-folder-structure)
- [Phase 1 — Prepare the RHEL 10 Environment](#phase-1--prepare-the-rhel-10-environment)
- [Phase 2 — Create the Kubernetes Cluster](#phase-2--create-the-kubernetes-cluster)
- [Phase 3 — Create the Python Project](#phase-3--create-the-python-project)
- [Phase 4 — Build the Kubernetes Tools (`pod_tools.py`)](#phase-4--build-the-kubernetes-tools-pod_toolspy)
- [Phase 5 — Build the AI Agent (`agent_tools.py` and `agent.py`)](#phase-5--build-the-ai-agent-agent_toolspy-and-agentpy)
- [Phase 6 — Write the RCA Report (`reporting.py`)](#phase-6--write-the-rca-report-reportingpy)
- [Phase 7 — Connect Everything (`main.py`)](#phase-7--connect-everything-mainpy)
- [Phase 8 — Testing and Real Incident Investigation](#phase-8--testing-and-real-incident-investigation)
- [Troubleshooting](#troubleshooting)
- [Security and Limitations](#security-and-limitations)
- [Quick Reference](#quick-reference)
- [Appendix — Differences from manual.docs](#appendix--differences-from-manualdocs)

---

## Part 1 — What Are We Building?

### The problem

In Kubernetes, applications run in containers, and containers run inside **Pods**. Sometimes a Pod fails. Common reasons are:

- **Wrong container image.** The image name or tag does not exist (`ErrImagePull`, `ImagePullBackOff`).
- **The application crashes.** The container starts, exits with an error, and Kubernetes keeps restarting it (`CrashLoopBackOff`).
- **Resource problems.** Not enough CPU or memory, or the container uses more memory than its limit.
- **Configuration mistakes.** Missing configuration files, wrong ports, wrong settings.
- **Node problems.** The machine (node) running the Pod has a problem.

To find the cause, a DevOps engineer usually runs many commands:

```bash
kubectl get pod <pod> -n <namespace>
kubectl describe pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace>
kubectl logs <pod> -n <namespace> --previous
kubectl get events -n <namespace>
kubectl top pod <pod> -n <namespace>
kubectl describe node <node>
```

Then the engineer reads all the output, connects the facts, and writes a report. This takes time.

### The solution: LW-RCA-analyzer

**LW-RCA-analyzer** is a Python AI agent. You give it a Pod name. Then:

1. **Claude AI decides** which checks to run (Pod status, logs, previous logs, events, CPU/RAM, `describe pod`, `describe node`).
2. **Python runs** those checks with read-only `kubectl` commands and gives the results back to Claude.
3. Claude looks at the results and **decides what to check next**, until it has enough evidence.
4. Claude writes a **Root Cause Analysis (RCA)**: summary, impact, timeline, confirmed facts, root cause, five whys, fixes, prevention, and confidence level.
5. Python saves everything as a **Markdown report** in the `reports/` folder.

### What LW-RCA-analyzer does **not** do

LW-RCA-analyzer is **read-only**:

- It does **not** restart, delete, scale, or change anything in the cluster.
- It does **not** repair problems automatically. It is **not** a self-healing system.
- It only runs `kubectl get`, `kubectl logs`, `kubectl top`, and `kubectl describe`.

The RCA is **advice**. A human engineer reads the report and decides what to change.

> **In one sentence:** Kubernetes supplies the facts, Claude decides what to check and writes the RCA, Python safely runs the checks and saves the report, and you decide what to do next.

---

## Part 2 — The Technologies

| Technology | What it is | Why we need it | Where we use it |
|---|---|---|---|
| **RHEL 10** | Red Hat Enterprise Linux, an enterprise Linux server OS | It is the host machine for the whole lab | Phase 1 |
| **Docker** | Runs applications in containers | k3d runs each Kubernetes node as a Docker container | Phase 1, 2 |
| **Kubernetes** | Runs and manages containers in Pods | It is the system we investigate | Phase 2, 8 |
| **k3d / k3s** | k3s is a small Kubernetes; k3d runs k3s inside Docker | A real Kubernetes cluster on one machine in about a minute | Phase 2 |
| **kubectl** | The Kubernetes command-line tool | Our Python code runs `kubectl` to read Pod information | Phase 1, 4 |
| **Python** | A simple, popular programming language | All agent code is written in Python | Phase 3–8 |
| **venv** | A private folder for this project's Python packages | Keeps project packages separate from the system | Phase 3 |
| **Claude API** | Anthropic's AI model, used over the internet with an API key | Claude decides which checks to run and writes the RCA | Phase 5 |
| **LangChain (`langchain-core`)** | A library with a standard "tool" format | Turns our Python functions into tools that Claude can choose | Phase 5 |
| **python-dotenv** | Reads settings from a `.env` file | Keeps the API key out of the code | Phase 3, 5, 6 |
| **pytest** | A Python testing tool | Checks the code works, without a cluster or API key | Phase 8 |

### What is an AI agent?

A normal chatbot answers one question. An **AI agent** works on a task by itself:

1. It **decides** which tool to use.
2. It looks at the result.
3. It decides what to do next.
4. It repeats this until it can answer.

In LW-RCA-analyzer:

- **Claude is the decision maker.** It gets the task "investigate pod X" and a list of 7 tools. It chooses the tools.
- **The tools** are small Python functions that read data from Kubernetes.
- **Python is the safe executor.** It runs only the tools Claude asks for, checks every input, and sends the results back.

In the recorded runs, LW-RCA-analyzer chose **different tools for each Pod**:

| Pod | Tools LW-RCA-analyzer chose |
|---|---|
| Healthy web server | status, events, logs, CPU/RAM, then `describe_pod` **and `describe_node`** |
| Pod with a wrong image | status, events, `describe_pod`. It skipped logs because the container never started. |
| Crashing Pod | `describe_pod`, events, logs, **previous logs**, CPU/RAM |

### What is an RCA?

A **Root Cause Analysis (RCA)** answers four questions about an incident:

1. **What happened?** (problem, impact, timeline)
2. **Why did it happen?** (root cause, contributing factors, five whys)
3. **How do we fix it now?** (corrective actions)
4. **How do we stop it happening again?** (preventive actions)

A good RCA is based on evidence, not guesses. LW-RCA-analyzer only uses evidence returned by its tools, and says "Confirmed root cause" only when the evidence proves it.

---

## Part 3 — How LW-RCA-analyzer Works

### The big picture

```text
 You: python main.py --pod <name>
        │
        ▼
 ┌──────────────┐  1. check the Pod exists
 │   main.py    │────────────────────────────────────────────┐
 └──────┬───────┘                                            │
        │ 2. start the agent                                 │
        ▼                                                    │
 ┌──────────────┐  task + 7 tools   ┌──────────────┐        │
 │   agent.py   │──────────────────▶│  Claude API  │        │
 │ (agent loop) │◀──────────────────│ (decides)    │        │
 └──────┬───────┘  "run these tools"└──────────────┘        │
        │ runs the tools Claude chose                        │
        ▼                                                    ▼
 ┌────────────────┐            ┌──────────────┐     ┌──────────────┐
 │ agent_tools.py │───────────▶│ pod_tools.py │────▶│ kubectl ──▶  │
 │ (7 tools)      │            │ (read-only)  │     │ k3d cluster  │
 └────────────────┘            └──────────────┘     └──────────────┘
        │
        │ 3. RCA text + list of tools used
        ▼
 ┌──────────────┐  4. write report   ┌───────────────────────────┐
 │ reporting.py │───────────────────▶│ reports/incident_*.md     │
 └──────────────┘                    └───────────────────────────┘
```

### Step by step

1. You run `python main.py --pod <name> --namespace ai-sre-lab`.
2. `main.py` checks that the names are safe and that the Pod exists. If not, it stops (no AI call, no report).
3. `agent.py` starts the **agent loop**: it sends Claude the task and the 7 tool descriptions. Claude replies with the tools it wants. Python runs them and sends back the results. This repeats until Claude writes the RCA (at most 10 rounds).
4. `main.py` collects a standard set of evidence with `pod_tools.py`, so every report has the same raw facts.
5. `reporting.py` writes the evidence, the list of tools the agent used, and the RCA into a Markdown file.

### Which file does what

| File | Job | Uses |
|---|---|---|
| `pod_tools.py` | Runs read-only `kubectl` commands | `kubectl` |
| `agent_tools.py` | Turns those functions into 7 LangChain tools | `pod_tools.py`, LangChain |
| `agent.py` | The agent loop: talks to Claude and runs the chosen tools | `agent_tools.py`, `pod_tools.py`, Claude API |
| `reporting.py` | Writes the Markdown report | — |
| `main.py` | Starts everything from the terminal | all the files above |

---

## Part 4 — Project Folder Structure

```text
agent/
│
├── README.md               ← this guide
├── manual.docs             ← original course manual (unchanged)
├── requirements.txt        ← Python packages
├── .env                    ← your private API key and settings (never share)
├── .env.example            ← safe template for .env
├── .gitignore              ← files Git must ignore
├── pytest.ini              ← pytest settings
│
├── main.py                 ← start here: runs LW-RCA-analyzer
├── agent.py                ← the AI agent loop (talks to Claude)
├── agent_tools.py          ← the 7 tools the agent may use
├── pod_tools.py            ← read-only kubectl functions
├── reporting.py            ← writes the Markdown report
│
├── k8s/
│   ├── demo.yaml           ← healthy HTTPD web server (Deployment + Service)
│   ├── broken-pod.yaml     ← Pod with a wrong image tag (ImagePullBackOff)
│   └── crashloop-pod.yaml  ← Pod that keeps crashing (CrashLoopBackOff)
│
├── tests/
│   └── test_pod_tools.py   ← automated tests (21 tests)
│
└── reports/                ← reports are saved here
    └── .gitkeep
```

In this guide, the project folder is **`~/agent`**. When the guide says **File: `agent/main.py`**, it means `~/agent/main.py`.

> The project folder may also contain `README.backup.md` (an old README) and older reports in `reports/`. They are not used by the code.

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

**Goal:** Create the project folders, a Python virtual environment, and the settings files.

**Where to run:** The RHEL 10 terminal, as your normal user.

### How to create the files in this guide

Every file is shown with its exact path, for example **File: `agent/pod_tools.py`**. To create a file:

```bash
cd ~/agent
vim pod_tools.py
```

In vim:

1. Type `:set paste` and press Enter. This stops vim from changing the indentation when you paste.
2. Press `i`, then paste the **complete** code block.
3. Press `Esc`, type `:wq`, and press Enter to save.

Copy every code block exactly. **Python uses indentation (spaces at the start of a line) as part of the code.** If the spaces change, the code breaks.

### Step 3.1 — Create the folders and the virtual environment

```bash
mkdir -p ~/agent/reports ~/agent/tests ~/agent/k8s
cd ~/agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

- `mkdir -p` creates the folders.
- `python3 -m venv .venv` creates a virtual environment (a private Python folder) called `.venv`.
- `source .venv/bin/activate` turns it on. Your prompt now starts with `(.venv)`.
- `pip install --upgrade pip` updates pip inside the virtual environment.

**Verify:**

```bash
which python
```

It should print a path that ends with `agent/.venv/bin/python`. If it prints `/usr/bin/python`, run `source .venv/bin/activate` again.

> Run `cd ~/agent` and `source .venv/bin/activate` in **every new terminal** before you run the agent or the tests.

### Step 3.2 — `requirements.txt`

**File: `agent/requirements.txt`**

```text
anthropic
langchain-core
python-dotenv
pytest
```

| Package | Why we need it |
|---|---|
| `anthropic` | The official Python library for the Claude API |
| `langchain-core` | Gives us the `@tool` decorator |
| `python-dotenv` | Reads the `.env` file |
| `pytest` | Runs the automated tests |

Install them:

```bash
pip install -r requirements.txt
```

**Verify:**

```bash
python -c "import anthropic, langchain_core, dotenv; print('imports OK')"
```

Recorded output:

```text
imports OK
```

This project was tested with `anthropic` 2.3.0, `langchain-core` 1.7.3, `python-dotenv` 1.2.4, and `pytest` 9.2.0. Check your versions with `pip list`.

### Step 3.3 — `.gitignore`

**File: `agent/.gitignore`**

```text
.venv/
.env
__pycache__/
.pytest_cache/
reports/*.md
```

This tells Git which files **not** to save:

| Line | Why |
|---|---|
| `.venv/` | Large and machine-specific. Anyone can recreate it with `pip install -r requirements.txt`. |
| `.env` | **Contains your API key.** It must never be shared or committed. |
| `__pycache__/`, `.pytest_cache/` | Files Python and pytest create automatically. |
| `reports/*.md` | Reports contain logs and cluster details. |

### Step 3.4 — `.env.example` and `.env`

**File: `agent/.env.example`**

```text
ANTHROPIC_API_KEY=replace_with_your_real_key
ANTHROPIC_MODEL=claude-opus-5-5
REPORT_DIR=reports
```

This is a safe template with no secret in it. Create your real `.env` from it:

```bash
cd ~/agent
cp .env.example .env
chmod 600 .env
vim .env
```

`chmod 600` makes the file readable only by you. In `.env`, set your values:

```text
ANTHROPIC_API_KEY=<your real API key from the Anthropic Console>
ANTHROPIC_MODEL=<a model ID that is available in your account>
REPORT_DIR=reports
```

| Variable | Used in | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | `agent.py` | Your Claude API key |
| `ANTHROPIC_MODEL` | `agent.py` | Which Claude model to use |
| `REPORT_DIR` | `reporting.py` | The folder for reports (relative to where you run the program) |

**About the model ID:** `.env.example` uses `claude-opus-5-5`. Model availability depends on your Anthropic account. Check the models list in your Anthropic Console and use a model ID that your account can use. If it is wrong, the report says `model '...' was not found`.

**Keep the API key private:**

- Anyone with your key can use the API on your account and your bill.
- Never put the key in code, chats, screenshots, or Git.
- If the key leaks, revoke it in the Anthropic Console and create a new one.

### Step 3.5 — `pytest.ini`

**File: `agent/pytest.ini`**

```ini
[pytest]
pythonpath = .
```

`pythonpath = .` lets the test file in `tests/` import our files (`import agent`, `import pod_tools`) from the project folder.

### Step 3.6 — Keep the `reports` folder in Git

```bash
touch ~/agent/reports/.gitkeep
```

`reporting.py` also creates the `reports/` folder automatically if it is missing.

---

## Phase 4 — Build the Kubernetes Tools (`pod_tools.py`)

**Goal:** Write simple Python functions that read information about a Pod.

### How Python talks to Kubernetes

```text
Python function ──▶ subprocess.run(["kubectl", "get", "pod", ...]) ──▶ kubectl ──▶ Kubernetes
      ▲                                                                     │
      └───────────────────── the output (or the error) ◀────────────────────┘
```

- Python runs `kubectl` like you would in a terminal, and reads what it prints.
- `kubectl` already knows how to reach the cluster (from `~/.kube/config`), so Python needs no passwords or certificates.
- Every function returns a **dictionary**. It always contains `"ok": True` (it worked) or `"ok": False` together with an `"error"` message. A failed command never crashes the program.

### File: `agent/pod_tools.py`

```python
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
```

### Explanation

#### Imports

| Import | Why |
|---|---|
| `json` | Reads the JSON that `kubectl get pod -o json` prints |
| `re` | Regular expressions, used to check names |
| `subprocess` | Runs `kubectl` from Python |
| `datetime`, `timezone` | Records the time the evidence was collected (UTC) |

#### `NAME_PATTERN` and `validate_name(value, label)`

- `NAME_PATTERN` describes a valid Kubernetes name: lowercase letters, numbers, `-` and `.`, starting and ending with a letter or number.
- `validate_name` returns the name if it is valid. If not, it raises a `ValueError` such as `Invalid pod name: 'Bad_Name'`.
- **Why:** It stops unsafe input, like `pod;rm -rf` or `--all`, before it reaches `kubectl`. It is used twice: in `main.py` for your input, and in `agent.py` for every name **Claude** sends to a tool.

#### `run_kubectl(args)`

The base of every other function.

- **Receives:** a list of `kubectl` arguments, for example `["get", "pod", "my-pod", "-n", "ai-sre-lab"]`.
- **Does:** runs `kubectl` with those arguments.
  - `capture_output=True` keeps the output instead of printing it.
  - `text=True` gives the output as text.
  - `timeout=20` stops waiting after 20 seconds.
- **Returns:**
  - Success: `{"ok": True, "output": "<what kubectl printed>"}`
  - Failure: `{"ok": False, "error": "<the error message>"}`
  - Special errors: `kubectl` not installed, or no answer within 20 seconds.

The command is a **list**, not one string. This means characters like `;` or `|` in a name can never start another command.

#### `list_pods(namespace)`

- **Runs:** `kubectl get pods -n <namespace> -o jsonpath={.items[*].metadata.name}` (only the Pod names).
- **Returns:** `{"ok": True, "pods": ["pod-a", "pod-b"]}`.
- **Used by:** `main.py`, when you do not give `--pod`.

#### `get_configured_resources(pod)`

- **Receives:** the Pod data (already read from JSON). It does not run `kubectl`.
- **Returns:** for each container, its CPU/memory **requests** and **limits**, or `"Not set"`.
- **Important:** These are **settings** from the Pod spec, not real usage.

#### `get_pod_status(pod_name, namespace)`

- **Runs:** `kubectl get pod <pod> -n <namespace> -o json`.
- **Returns:** a dictionary with:

  | Key | Meaning |
  |---|---|
  | `phase` | `Pending`, `Running`, `Succeeded`, `Failed`, or `Unknown` |
  | `node` | The node the Pod runs on (or `Not scheduled`) |
  | `pod_ip`, `created`, `labels` | Pod IP, creation time, labels |
  | `containers` | For each container: `ready`, `restart_count`, `waiting_reason` (for example `ImagePullBackOff` or `CrashLoopBackOff`), `state`, and `last_state` |
  | `configured_resources` | Requests and limits (from `get_configured_resources`) |
  | `owner_references` | Who owns the Pod, for example a ReplicaSet |

- `last_state` describes the **previous** container run, for example `{"terminated": {"exitCode": 1, "reason": "Error"}}` or `"reason": "OOMKilled"`. It is very useful for crashing Pods.
- The Pod **phase** and the container **waiting reason** are different things. A Pod with a wrong image has phase `Pending` and waiting reason `ImagePullBackOff`.

#### `get_pod_logs(pod_name, namespace)`

- **Runs:** `kubectl logs <pod> -n <namespace> --all-containers=true --tail=80` (the last 80 lines).
- If the container never started, `kubectl` returns an error such as `container "web" ... is waiting to start`. That error is useful evidence too.

#### `get_pod_previous_logs(pod_name, namespace)`

- **Runs:** the same command with `--previous`, which reads the logs of the **previous** container run.
- **Why:** When a container crashes and restarts, the error is in the previous run.
- It returns an error if the container never restarted (`previous terminated container ... not found`). That is normal.
- Sometimes, right after a crash, it says `unable to retrieve container logs`. Then the normal logs usually already show the crash.

#### `get_pod_events(pod_name, namespace)`

- **Runs:** `kubectl get events` for this Pod only (`--field-selector`), sorted by time, with these columns: `FIRST_SEEN`, `LAST_SEEN`, `COUNT`, `TYPE`, `REASON`, `SOURCE`, `MESSAGE`.
- **Why these columns:** They show **exact UTC times** (like `2026-10-30T22:38:35Z`) instead of "5m ago", so the RCA can build a timeline.
- Kubernetes deletes events after about one hour, so an older Pod may show `(No events returned)`.
- Some events show `<nil>` for the time (for example `Scheduled`). That is normal.

#### `get_pod_metrics(pod_name, namespace)`

- **Runs:** `kubectl top pod <pod> -n <namespace> --containers` (live CPU and memory, from Metrics Server).
- **If it fails**, it returns `"cpu_ram": "Unavailable"` with a note and the real error. **It never makes up numbers.**

#### `get_pod_description(pod_name, namespace)` and `get_node_description(node_name)`

- **Run:** `kubectl describe pod ...` and `kubectl describe node ...`.
- `describe pod` shows the full Pod details, including the container command and mounts.
- `describe node` shows the node's conditions (Ready, memory/disk pressure), taints, and events. The agent uses it when it suspects a node problem.

#### `collect_pod_evidence(pod_name, namespace)`

- Calls six functions and puts all results in one dictionary, with the collection time:

  ```python
  {
      "collected_at_utc": "...",
      "pod": {...},
      "metrics": {...},
      "events": {...},
      "logs": {...},
      "previous_logs": {...},
      "description": {...},
  }
  ```

- **Used by:** `main.py`, after the agent finishes. This gives every report the same basic evidence, so a reader can check the agent's RCA.

### Live usage vs. configured requests and limits

| | Live usage | Requests and limits |
|---|---|---|
| **Meaning** | What the container **uses right now** | What the Pod spec **allows** |
| **Command** | `kubectl top` | `kubectl get pod -o json` |
| **Function** | `get_pod_metrics()` | `get_configured_resources()` |
| **Example** | `httpd  1m  6Mi` | request `50m` / `64Mi`, limit `250m` / `128Mi` |
| **Available when** | Metrics Server works **and** the container is running | Always |

- A **request** is the amount Kubernetes reserves for the container.
- A **limit** is the maximum. Above the memory limit the container is killed (`OOMKilled`).
- A request or limit is **never** a measurement. The report and the agent's instructions both say this.

### Step 4.1 — Test the functions by hand

You can test `pod_tools.py` once the cluster from Phase 2 is running:

```bash
cd ~/agent
source .venv/bin/activate
python -c "import pod_tools; print(pod_tools.list_pods('ai-sre-lab'))"
```

Recorded output:

```text
{'ok': True, 'pods': ['broken-image-demo', 'crashloop-demo', 'demo-web-665f97df4c-mj54n']}
```

At this point in the guide you will see only your `demo-web-...` Pod. The recorded output also shows the two test Pods from Phase 8, because they were running when it was recorded.

Test the name check:

```bash
python -c "import pod_tools; pod_tools.validate_name('Bad_Name', 'pod name')"
```

This prints a traceback that ends with:

```text
ValueError: Invalid pod name: 'Bad_Name'
```

---

## Phase 5 — Build the AI Agent (`agent_tools.py` and `agent.py`)

**Goal:** Give Claude a set of tools, and build the loop in which Claude investigates the Pod by itself.

### Key ideas

- **Claude API:** Your program sends messages, a model ID, your API key, and a list of **tools**. Claude sends back an answer.
- **Tool use:** You describe each tool to Claude (name, description, inputs). Claude **cannot run anything itself**. Instead it answers: "please run `describe_node` with `node_name = k3d-pod-lab-agent-0`". Your Python code runs the tool and sends the result back.
- **LangChain tool:** The `@tool` decorator turns a normal Python function into a tool. The **docstring** becomes the description Claude reads, and the **type hints** (`pod_name: str`) become the inputs.

### File: `agent/agent_tools.py`

```python
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
```

### Explanation

- `from langchain_core.tools import tool` imports the decorator. `import pod_tools` gives access to our kubectl functions.
- Each tool is a small function that calls one `pod_tools` function.
- `@tool` turns it into a LangChain tool:
  - **Name:** the function name, for example `inspect_pod`.
  - **Description:** the docstring. **Claude reads this to decide when to use the tool**, so it must be clear.
  - **Inputs:** from the type hints. `pod_name: str` and `namespace: str` are both required.
- `ALL_TOOLS` is the list of tools the agent may use. **To give the agent a new ability, you add a read-only tool to this list.**

| Tool | Runs | Claude uses it to... |
|---|---|---|
| `inspect_pod` | `kubectl get pod -o json` | see phase, node, container states, `last_state`, limits |
| `read_pod_logs` | `kubectl logs` | read the last 80 log lines |
| `read_previous_pod_logs` | `kubectl logs --previous` | read the logs from before a crash |
| `read_pod_events` | `kubectl get events` | see what happened, with times |
| `read_pod_cpu_ram` | `kubectl top pod` | see live CPU and memory |
| `describe_pod` | `kubectl describe pod` | see full details, command, mounts |
| `describe_node` | `kubectl describe node` | check the node's health |

**Check the tools:**

```bash
python -c "from agent_tools import inspect_pod; print(inspect_pod.name); print(inspect_pod.description); print(inspect_pod.args)"
```

Recorded output:

```text
inspect_pod
Read the current status, node, labels and container state of one pod.
{'pod_name': {'title': 'Pod Name', 'type': 'string'}, 'namespace': {'title': 'Namespace', 'type': 'string'}}
```

### File: `agent/agent.py`

This is the heart of LW-RCA-analyzer.

```python
# agent.py
# LW-RCA-analyzer: the AI agent.
# Claude decides which read-only tools to call. Python runs them and sends back
# the results. This repeats until Claude writes the Root Cause Analysis (RCA).

import json
import os

import anthropic
from dotenv import load_dotenv

from agent_tools import ALL_TOOLS
from pod_tools import validate_name

load_dotenv()

AGENT_NAME = "LW-RCA-analyzer"
MAX_STEPS = 10  # the agent may ask Claude at most 10 times

SYSTEM_PROMPT = """
You are LW-RCA-analyzer, a careful Site Reliability Engineer agent.
You investigate one Kubernetes pod and write a Root Cause Analysis (RCA).

You have read-only tools. Decide yourself which tools to call next, based on
what you have learned so far. For example: if events mention a node problem,
describe the node; if a container restarted, read its previous logs.
Stop calling tools when you have enough evidence.

Rules:
- Use only evidence returned by the tools. Do not invent CPU, RAM, timestamps, or events.
- "read_pod_cpu_ram" is live usage. Requests and limits from the pod spec are
  settings, not real usage. If metrics are unavailable, say so.
- You cannot change the cluster. Do not claim you changed anything.

When you are done, write the RCA in Markdown with exactly these sections,
using level-3 headings (###):
### 1. Executive summary
### 2. Problem statement
### 3. Impact
### 4. Timeline (UTC)
### 5. Confirmed observations
### 6. Root cause
### 7. Contributing factors
### 8. Five whys
### 9. Corrective actions
### 10. Preventive actions
### 11. Verification steps
### 12. Confidence level and evidence gaps

In "Root cause", write "Confirmed root cause" only if the evidence directly proves
it; otherwise write "Most likely root cause (not confirmed)". If the pod is healthy,
write "No incident detected" and do not invent a root cause. Mark every corrective
action as "not performed by the agent; requires human approval".
"""


def tool_definitions():
    """Describe our LangChain tools in the format the Claude API expects."""
    definitions = []
    for tool in ALL_TOOLS:
        definitions.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.tool_call_schema.model_json_schema(),
        })
    return definitions


def run_tool(name, tool_input):
    """Run one tool that Claude asked for. Always returns text for Claude."""
    # 1. Find the tool. Claude may only use tools from ALL_TOOLS.
    chosen_tool = None
    for tool in ALL_TOOLS:
        if tool.name == name:
            chosen_tool = tool
    if chosen_tool is None:
        return json.dumps({"ok": False, "error": f"Unknown tool: {name}"})

    # 2. Check every name Claude sent (pod, namespace, node) before using it.
    try:
        for key, value in tool_input.items():
            validate_name(str(value), key)
        result = chosen_tool.invoke(tool_input)
    except Exception as error:
        return json.dumps({"ok": False, "error": str(error)})

    # 3. Send the result back to Claude as text.
    return json.dumps(result)


def investigate_pod(pod_name, namespace):
    """Run the agent. Returns the RCA text and the list of tools it used."""
    steps = []
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL")

    if not api_key or api_key == "replace_with_your_real_key":
        return "AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env.", steps
    if not model:
        return "AI explanation unavailable: set ANTHROPIC_MODEL in .env.", steps

    client = anthropic.Anthropic(api_key=api_key)

    # The conversation starts with the task.
    messages = [{
        "role": "user",
        "content": f"Investigate pod {pod_name} in namespace {namespace} and write the RCA.",
    }]

    for step in range(1, MAX_STEPS + 1):
        # On the last step, switch tools off so Claude must write the RCA.
        if step == MAX_STEPS:
            tool_choice = {"type": "none"}
        else:
            tool_choice = {"type": "auto"}

        # Ask Claude what to do next.
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=tool_definitions(),
                tool_choice=tool_choice,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            return "AI explanation unavailable: the API key was rejected.", steps
        except anthropic.NotFoundError:
            return f"AI explanation unavailable: model {model!r} was not found.", steps
        except anthropic.RateLimitError:
            return "AI explanation unavailable: rate limit or quota reached.", steps
        except anthropic.APIConnectionError:
            return "AI explanation unavailable: could not connect to the Claude API.", steps
        except anthropic.APIStatusError as error:
            return f"AI explanation unavailable: API error {error.status_code}.", steps

        if response.stop_reason == "refusal":
            return "AI explanation unavailable: Claude declined this request.", steps

        # If Claude did not ask for a tool, it has finished. Its text is the RCA.
        if response.stop_reason != "tool_use":
            rca = ""
            for block in response.content:
                if block.type == "text":
                    rca += block.text
            return rca.strip(), steps

        # Claude asked for tools. Save Claude's message in the conversation.
        messages.append({"role": "assistant", "content": response.content})

        # Run every tool Claude asked for and collect the results.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  Step {step}: {block.name} {json.dumps(block.input)}")
                steps.append({"step": step, "tool": block.name, "input": block.input})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": run_tool(block.name, block.input),
                })

        # Send all tool results back to Claude in one message.
        messages.append({"role": "user", "content": results})

    return "AI explanation unavailable: the agent stopped without an RCA.", steps
```

### Explanation

#### The settings at the top

| Line | Meaning |
|---|---|
| `load_dotenv()` | Reads `.env`, so `os.getenv("ANTHROPIC_API_KEY")` works |
| `AGENT_NAME = "LW-RCA-analyzer"` | The agent's name, shown in the terminal and in `--help` |
| `MAX_STEPS = 10` | The agent may ask Claude at most 10 times. This keeps it from running forever. |
| `SYSTEM_PROMPT` | The agent's instructions, sent to Claude every time |

#### `SYSTEM_PROMPT` — the agent's instructions

| Part | Why it is there |
|---|---|
| "You are LW-RCA-analyzer, a careful Site Reliability Engineer agent." | Gives Claude its role |
| "Decide yourself which tools to call next... if events mention a node problem, describe the node; if a container restarted, read its previous logs." | Makes Claude act as an agent, with two examples |
| "Stop calling tools when you have enough evidence." | Keeps the investigation short |
| "Use only evidence returned by the tools. Do not invent..." | No made-up numbers or events |
| Live usage vs requests/limits | Claude must never present a limit as usage |
| "You cannot change the cluster." | Matches the read-only design |
| The 12 RCA sections | Every RCA has the same structure |
| "Confirmed root cause" only if proven | Claude must not claim more than the evidence shows |
| "No incident detected" for a healthy Pod | No made-up problems |
| "not performed by the agent; requires human approval" | Every fix needs a human decision |

**The 12 RCA sections:**

| # | Section | Contains |
|---|---|---|
| 1 | Executive summary | What failed, why, and the current state, in a few sentences |
| 2 | Problem statement | Pod, namespace, node, symptom, first seen |
| 3 | Impact | What is affected; "unknown" if the evidence cannot show it |
| 4 | Timeline (UTC) | Events in time order, from real timestamps |
| 5 | Confirmed observations | Facts directly seen in the evidence |
| 6 | Root cause | "Confirmed root cause", "Most likely root cause (not confirmed)", or "No incident detected" |
| 7 | Contributing factors | Things that made the problem possible or worse |
| 8 | Five whys | Why → why → why... from symptom to root cause |
| 9 | Corrective actions | Fixes for a human to review and run |
| 10 | Preventive actions | How to stop it happening again |
| 11 | Verification steps | Commands to check that the fix worked |
| 12 | Confidence level and evidence gaps | Low / medium / high, and what evidence is missing |

#### `tool_definitions()`

- Builds the list of tool descriptions that Claude needs: `name`, `description`, and `input_schema`.
- `input_schema` is created by LangChain from the type hints. For `describe_node` it says: "an object with a required text field `node_name`".
- The tools are written once in `agent_tools.py`; this function reuses them.

#### `run_tool(name, tool_input)`

Runs one tool that Claude asked for, in three safe steps:

1. **Find the tool** in `ALL_TOOLS`. If Claude asks for a tool that does not exist (for example `delete_pod`), it returns `Unknown tool`.
2. **Check every name** with `validate_name()`. An unsafe value like `--all; rm -rf /` is refused before `kubectl` runs.
3. **Run the tool** and return the result as JSON text.

If anything goes wrong, it returns `{"ok": false, "error": "..."}`. The error goes back to Claude, and the program does not crash.

#### `investigate_pod(pod_name, namespace)` — the agent loop

**Returns:** two things — the RCA text, and the list of tools used (`steps`).

1. **Check the settings.** If the API key is missing (or still the placeholder) or the model is missing, return a clear "AI explanation unavailable" message.
2. **Create the Claude client** with `anthropic.Anthropic(api_key=api_key)`.
3. **Start the conversation** with one message: "Investigate pod X in namespace Y and write the RCA."
4. **Loop** (`for step in range(1, MAX_STEPS + 1)`):
   - **Choose `tool_choice`.** Normally `{"type": "auto"}` (Claude decides). In the last step, `{"type": "none"}` switches tools off, so Claude must write the RCA.
   - **Ask Claude** with `client.messages.create(...)`: the model, `max_tokens=16000` (maximum answer length), the system prompt, the tools, and the conversation so far.
   - **Handle API errors.** Each error becomes a clear message instead of a crash:

     | Error | Typical cause |
     |---|---|
     | `AuthenticationError` | Wrong or revoked API key |
     | `NotFoundError` | The model ID is not available |
     | `RateLimitError` | Too many requests, or no credit left |
     | `APIConnectionError` | No internet, DNS, or proxy problem |
     | `APIStatusError` | Any other API error (for example 500 or 529) |

   - **If `stop_reason` is `"refusal"`**, Claude declined, so return a message.
   - **If `stop_reason` is not `"tool_use"`**, Claude is finished. Join its text blocks — this is the RCA — and return it.
   - **Otherwise Claude wants tools:**
     - Add Claude's message (`response.content`) to the conversation.
     - For each `tool_use` block: print it (`Step 1: read_pod_events {...}`), save it in `steps`, and run it with `run_tool()`.
     - Each result becomes a `tool_result` with the same `tool_use_id`, so Claude knows which result belongs to which request.
     - Send all results back to Claude in **one** message. The loop starts again.

**Why we send the whole conversation every time:** The Claude API does not remember earlier requests. So each request must contain the full conversation: the task, every tool request Claude made, and every result.

#### Safety rules of the agent

- Claude can only choose from the 7 tools in `ALL_TOOLS`. All are read-only. **No tool can change the cluster.**
- Every name from Claude is checked by `validate_name()` before `kubectl` runs.
- The loop stops after `MAX_STEPS` (10) rounds.

**Check the agent setup** (no API call):

```bash
python -c "from agent import AGENT_NAME, tool_definitions; print(AGENT_NAME); print([t['name'] for t in tool_definitions()])"
```

Recorded output:

```text
LW-RCA-analyzer
['inspect_pod', 'read_pod_logs', 'read_previous_pod_logs', 'read_pod_events', 'read_pod_cpu_ram', 'describe_pod', 'describe_node']
```

---

## Phase 6 — Write the RCA Report (`reporting.py`)

**Goal:** Save the evidence, the agent's steps, and the RCA as one Markdown file.

### Why a report?

- It is a **single record** of what was found and when.
- It can be shared with the team and attached to a ticket.
- It keeps **facts** (raw Kubernetes output) separate from **interpretation** (the AI's RCA), so anyone can check the RCA against the evidence.

### File: `agent/reporting.py`

````python
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
````

> **Note:** This file contains triple backticks (```` ``` ````) inside the Python text. That is correct: they become code blocks in the Markdown report. Copy them exactly.

### Explanation

#### `text_or_error(result, key)`

Each piece of evidence is a dictionary like `{"ok": True, "logs": "..."}` or `{"ok": False, "error": "..."}`. This function returns the text if it is there, otherwise the error message, otherwise `Unavailable`. So the report always shows something useful.

#### `resources_table(resources)`

Builds a Markdown table of the requests and limits, one row per container.

#### `steps_list(agent_steps)`

Builds a list of the tools the agent used, for example:

```text
- Step 2: `describe_node` with `{"node_name": "k3d-pod-lab-agent-0"}`
```

If the agent used no tools (for example, no API key), it writes `No tools were called by the AI agent.`

#### `create_markdown_report(pod_name, namespace, evidence, rca, agent_steps=None)`

Follow the numbered comments in the code:

1. **Folder:** reads `REPORT_DIR` from `.env` (default `reports`) and creates the folder if needed.
2. **File name:** `incident_<namespace>_<pod>_<date>_<time>.md`, using local time, for example `incident_ai-sre-lab_crashloop-demo_20261031_045543.md`. Every run creates a new file.
3. **Evidence parts:** takes each part of the evidence. `.get("pod", {})` gives an empty dictionary if a part is missing, so the code never crashes.
4. **CPU/RAM:** shows the `kubectl top` table, or `Unavailable` with the reason and the real Kubernetes error.
5. **Text sections:** events, logs, previous logs, and the description.
6. **Markdown:** puts everything into one text using an f-string (`f"""..."""`). Each `{...}` is replaced by a value.
7. **Save:** writes the file and returns its path.

### What is in the report

| Section | Comes from | Fact or interpretation? |
|---|---|---|
| Generated at, Evidence collected at | the clock | Fact |
| Pod name, Namespace, Status, Node, Pod IP, Created | `get_pod_status()` | Fact |
| Actual CPU and RAM usage | `get_pod_metrics()` | Fact (or "Unavailable") |
| Configured CPU and RAM | `get_configured_resources()` | Fact (settings) |
| Container state | `get_pod_status()` | Fact |
| Kubernetes events | `get_pod_events()` | Fact |
| Recent logs / Previous container logs | `get_pod_logs()` / `get_pod_previous_logs()` | Fact (or the error) |
| Pod description | `get_pod_description()` | Fact |
| AI agent investigation steps | the agent | Fact (what the agent ran) |
| Root cause analysis | Claude | **Interpretation (advice)** |
| Verification and limitations | fixed text | — |

---

## Phase 7 — Connect Everything (`main.py`)

**Goal:** Create the program you start from the terminal.

### File: `agent/main.py`

```python
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
```

### Explanation

#### Imports

| Import | From |
|---|---|
| `AGENT_NAME`, `investigate_pod` | `agent.py` (the agent) |
| `collect_pod_evidence`, `get_pod_status`, `list_pods`, `validate_name` | `pod_tools.py` |
| `create_markdown_report` | `reporting.py` |

#### `choose_pod(namespace)`

Used when you do not give `--pod`. It lists the Pods with numbers. You type a number or a Pod name.

#### `main()` — step by step

1. **Read the options.** `argparse` reads `--pod` (optional) and `--namespace` (default `ai-sre-lab`).
2. **Check the names** with `validate_name()`. A bad name prints an error and stops the program (exit code 1).
3. **Check that the Pod exists** with `get_pod_status()`. If not, print the error and stop. **No AI call and no report.**
4. **Run the agent:** `investigate_pod()` prints each tool Claude chooses and returns the RCA and the steps.
5. **Collect the evidence and write the report:** `collect_pod_evidence()` then `create_markdown_report()`.
6. **Print the report path.**

`if __name__ == "__main__":` means: run `main()` only when you start this file with `python main.py`.

### How to run LW-RCA-analyzer

**Where:** in `~/agent`, with the virtual environment turned on.

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod <POD_NAME> --namespace ai-sre-lab
```

Or choose the Pod from a list:

```bash
python main.py --namespace ai-sre-lab
```

Show the help:

```bash
python main.py --help
```

Recorded output:

```text
usage: main.py [-h] [--pod POD] [--namespace NAMESPACE]

LW-RCA-analyzer: investigate a Kubernetes pod and write an RCA report.

options:
  -h, --help            show this help message and exit
  --pod POD             Exact pod name (leave out to choose from a list)
  --namespace NAMESPACE
                        Kubernetes namespace
```

> **Always run it from `~/agent`.** `REPORT_DIR=reports` is relative to the folder you are in.

---

## Phase 8 — Testing and Real Incident Investigation

### Part A — Automated tests

#### File: `agent/tests/test_pod_tools.py`

```python
# tests/test_pod_tools.py
# Automated tests for LW-RCA-analyzer.
# They need no cluster and no API key: kubectl and Claude are replaced by fakes.

import json
import sys
from types import SimpleNamespace

import pytest

import agent
import main
import pod_tools
from reporting import create_markdown_report


# ---------- Helpers ----------

def fake_kubectl(output):
    """A fake run_kubectl that always succeeds with the given output."""
    return lambda args: {"ok": True, "output": output}


def failing_kubectl(error):
    """A fake run_kubectl that always fails with the given error."""
    return lambda args: {"ok": False, "error": error}


def fake_pod_json(name, phase, ready, waiting_reason=None):
    """Build a small pod JSON, like 'kubectl get pod -o json' returns."""
    state = {"running": {"startedAt": "2026-10-30T00:00:00Z"}}
    if waiting_reason:
        state = {"waiting": {"reason": waiting_reason}}
    pod = {
        "metadata": {"name": name, "namespace": "ai-sre-lab",
                     "creationTimestamp": "2026-10-30T00:00:00Z", "labels": {"app": name}},
        "spec": {
            "nodeName": "k3d-pod-lab-agent-0",
            "containers": [{
                "name": "web",
                "image": "httpd:2.4",
                "resources": {"requests": {"cpu": "50m", "memory": "64Mi"},
                              "limits": {"cpu": "250m", "memory": "128Mi"}},
            }],
        },
        "status": {
            "phase": phase,
            "podIP": "10.42.0.10",
            "containerStatuses": [{"name": "web", "ready": ready,
                                   "restartCount": 0, "state": state}],
        },
    }
    return json.dumps(pod)


def read_file(path):
    with open(path, encoding="utf-8") as report_file:
        return report_file.read()


# ---------- pod_tools.py ----------

def test_healthy_pod_status_is_parsed(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl",
                        fake_kubectl(fake_pod_json("demo-web-abc", "Running", ready=True)))
    status = pod_tools.get_pod_status("demo-web-abc", "ai-sre-lab")
    assert status["ok"] is True
    assert status["name"] == "demo-web-abc"
    assert status["phase"] == "Running"
    assert status["containers"][0]["ready"] is True
    assert status["configured_resources"][0]["cpu_limit"] == "250m"


def test_broken_pod_status_shows_waiting_reason(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl",
                        fake_kubectl(fake_pod_json("broken-image-demo", "Pending", ready=False,
                                                   waiting_reason="ImagePullBackOff")))
    status = pod_tools.get_pod_status("broken-image-demo", "ai-sre-lab")
    assert status["phase"] == "Pending"
    assert status["containers"][0]["ready"] is False
    assert status["containers"][0]["waiting_reason"] == "ImagePullBackOff"


def test_crashloop_pod_status_shows_last_state(monkeypatch):
    pod = json.loads(fake_pod_json("crashloop-demo", "Running", ready=False,
                                   waiting_reason="CrashLoopBackOff"))
    pod["status"]["containerStatuses"][0]["restartCount"] = 4
    pod["status"]["containerStatuses"][0]["lastState"] = {
        "terminated": {"exitCode": 1, "reason": "Error"}}
    monkeypatch.setattr(pod_tools, "run_kubectl", fake_kubectl(json.dumps(pod)))
    container = pod_tools.get_pod_status("crashloop-demo", "ai-sre-lab")["containers"][0]
    assert container["waiting_reason"] == "CrashLoopBackOff"
    assert container["restart_count"] == 4
    assert container["last_state"]["terminated"]["exitCode"] == 1


def test_missing_pod_returns_error(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl", failing_kubectl('pods "ghost" not found'))
    status = pod_tools.get_pod_status("ghost", "ai-sre-lab")
    assert status["ok"] is False
    assert "not found" in status["error"]


def test_metrics_error_is_reported(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl", failing_kubectl("metrics unavailable"))
    result = pod_tools.get_pod_metrics("demo-web-abc", "ai-sre-lab")
    assert result["ok"] is False
    assert result["cpu_ram"] == "Unavailable"
    assert "metrics unavailable" in result["error"]


def test_previous_logs_use_previous_flag(monkeypatch):
    commands = []

    def remember_command(args):
        commands.append(args)
        return {"ok": False, "error": 'previous terminated container "web" not found'}

    monkeypatch.setattr(pod_tools, "run_kubectl", remember_command)
    result = pod_tools.get_pod_previous_logs("demo-web-abc", "ai-sre-lab")
    assert result["ok"] is False
    assert "--previous" in commands[0]


@pytest.mark.parametrize("bad_name", ["", "Bad_Name", "pod;rm -rf", "-starts-with-dash"])
def test_invalid_names_are_rejected(bad_name):
    with pytest.raises(ValueError):
        pod_tools.validate_name(bad_name, "pod name")


# ---------- reporting.py ----------

def test_report_contains_pod_identity_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {"phase": "Running", "node": "k3d-pod-lab-agent-0"},
        "metrics": {"ok": True, "cpu_ram": "httpd 2m 12Mi"},
        "logs": {"ok": True, "logs": "httpd started"},
    }
    path = create_markdown_report("demo-web-abc", "ai-sre-lab", evidence, "No issue observed.")
    content = read_file(path)
    assert "LW-RCA-analyzer" in content
    assert "demo-web-abc" in content
    assert "ai-sre-lab" in content
    assert "httpd 2m 12Mi" in content
    assert "No issue observed." in content


def test_report_marks_missing_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {"metrics": {"ok": False, "cpu_ram": "Unavailable",
                            "note": "Metrics Server missing", "error": "not found"}}
    content = read_file(create_markdown_report("demo-web-abc", "ai-sre-lab", evidence, "RCA"))
    assert "Live metrics could not be retrieved" in content
    assert "Metrics Server missing" in content
    assert "Kubernetes said: `not found`" in content


def test_report_separates_usage_from_configured_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {
        "pod": {"configured_resources": [{
            "container": "httpd", "image": "httpd:2.4",
            "cpu_request": "50m", "cpu_limit": "250m",
            "memory_request": "64Mi", "memory_limit": "128Mi"}]},
        "metrics": {"ok": True, "cpu_ram": "httpd 1m 5Mi"},
    }
    content = read_file(create_markdown_report("demo-web-abc", "ai-sre-lab", evidence, "RCA"))
    assert "Actual CPU and RAM usage" in content
    assert "Configured CPU and RAM" in content
    assert "| httpd | 50m | 250m | 64Mi | 128Mi |" in content


def test_report_contains_rca_steps_and_previous_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    evidence = {"previous_logs": {"ok": True, "logs": "ERROR: config file not found"}}
    steps = [{"step": 1, "tool": "describe_node", "input": {"node_name": "node-1"}}]
    content = read_file(create_markdown_report("crashloop-demo", "ai-sre-lab", evidence,
                                               "### 6. Root cause\nBad config.", steps))
    assert "## Previous container logs" in content
    assert "ERROR: config file not found" in content
    assert "- Step 1: `describe_node`" in content
    assert "## Root cause analysis (AI-generated, advisory)" in content
    assert "Bad config." in content


# ---------- main.py ----------

def test_missing_pod_does_not_create_report(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path))
    monkeypatch.setattr(pod_tools, "run_kubectl", failing_kubectl('pods "ghost" not found'))
    monkeypatch.setattr(sys, "argv", ["main.py", "--pod", "ghost"])
    with pytest.raises(SystemExit):
        main.main()
    assert list(tmp_path.iterdir()) == []


# ---------- agent.py (Claude is replaced by a fake) ----------

def claude_reply(stop_reason, blocks):
    """Build a fake Claude response."""
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def tool_request(name, tool_input):
    """Build a fake 'please call this tool' block from Claude."""
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id="call-1")


def text_block(text):
    return SimpleNamespace(type="text", text=text)


class FakeClaude:
    """Pretends to be anthropic.Anthropic. Replays prepared replies in order."""

    def __init__(self, replies):
        self.replies = replies
        self.requests = []
        self.messages = self  # so that client.messages.create(...) works

    def create(self, **request):
        self.requests.append(request)
        return self.replies.pop(0)


def use_fake_claude(monkeypatch, fake):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    monkeypatch.setattr(agent.anthropic, "Anthropic", lambda api_key: fake)


def test_missing_api_key_gives_clear_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "replace_with_your_real_key")
    rca, steps = agent.investigate_pod("demo-web-abc", "ai-sre-lab")
    assert "AI explanation unavailable" in rca
    assert steps == []


def test_prompt_asks_for_rca_sections():
    for section in ["Executive summary", "Timeline (UTC)", "Root cause", "Five whys",
                    "Corrective actions", "Preventive actions",
                    "Confidence level and evidence gaps"]:
        assert section in agent.SYSTEM_PROMPT


def test_tool_definitions_describe_every_tool():
    names = [item["name"] for item in agent.tool_definitions()]
    assert names == [tool.name for tool in agent.ALL_TOOLS]
    assert "describe_node" in names


def test_agent_runs_the_tools_claude_chooses(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl", fake_kubectl("Normal  Started  Container started"))
    fake = FakeClaude([
        claude_reply("tool_use", [tool_request("read_pod_events",
                                               {"pod_name": "demo-web-abc", "namespace": "ai-sre-lab"})]),
        claude_reply("end_turn", [text_block("### 6. Root cause\nNo incident detected")]),
    ])
    use_fake_claude(monkeypatch, fake)

    rca, steps = agent.investigate_pod("demo-web-abc", "ai-sre-lab")

    assert "No incident detected" in rca
    assert steps[0]["tool"] == "read_pod_events"
    tool_result = fake.requests[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert "Container started" in tool_result["content"]


def test_agent_rejects_unsafe_tool_input(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl", lambda args: pytest.fail("kubectl must not run"))
    unsafe = json.loads(agent.run_tool("describe_node", {"node_name": "--all; rm -rf /"}))
    assert unsafe["ok"] is False
    unknown = json.loads(agent.run_tool("delete_pod", {"pod_name": "x"}))
    assert "Unknown tool" in unknown["error"]


def test_agent_stops_at_step_limit(monkeypatch):
    monkeypatch.setattr(pod_tools, "run_kubectl", fake_kubectl("{}"))
    replies = []
    for _ in range(agent.MAX_STEPS - 1):
        replies.append(claude_reply("tool_use", [tool_request(
            "describe_pod", {"pod_name": "demo-web-abc", "namespace": "ai-sre-lab"})]))
    replies.append(claude_reply("end_turn", [text_block("Final RCA")]))
    fake = FakeClaude(replies)
    use_fake_claude(monkeypatch, fake)

    rca, steps = agent.investigate_pod("demo-web-abc", "ai-sre-lab")

    assert rca == "Final RCA"
    assert len(fake.requests) == agent.MAX_STEPS
    assert fake.requests[-1]["tool_choice"] == {"type": "none"}
```

#### How the tests work

- **No cluster needed:** `monkeypatch.setattr(pod_tools, "run_kubectl", ...)` replaces the real `kubectl` with a fake one that returns prepared output.
- **No API key needed:** `FakeClaude` pretends to be the Claude client. It returns prepared replies (a tool request, then a final RCA) and remembers what the agent sent.
- **No mess:** `tmp_path` is a temporary folder for test reports.

| Test | What it checks |
|---|---|
| `test_healthy_pod_status_is_parsed` | A running Pod is read correctly (name, phase, ready, CPU limit) |
| `test_broken_pod_status_shows_waiting_reason` | A wrong-image Pod shows `Pending` and `ImagePullBackOff` |
| `test_crashloop_pod_status_shows_last_state` | A crashing Pod shows `CrashLoopBackOff`, restarts, and `last_state` exit code 1 |
| `test_missing_pod_returns_error` | A missing Pod returns `ok: False` with the error |
| `test_metrics_error_is_reported` | Failed metrics give `Unavailable` and keep the real error |
| `test_previous_logs_use_previous_flag` | Previous logs really use `kubectl logs --previous` |
| `test_invalid_names_are_rejected` (4 cases) | `""`, `Bad_Name`, `pod;rm -rf`, `-starts-with-dash` are refused |
| `test_report_contains_pod_identity_and_metrics` | The report has the agent name, Pod, namespace, metrics, and RCA |
| `test_report_marks_missing_metrics` | Missing metrics are explained, not invented |
| `test_report_separates_usage_from_configured_limits` | Usage and limits are in separate sections |
| `test_report_contains_rca_steps_and_previous_logs` | The report has previous logs, the agent steps, and the RCA |
| `test_missing_pod_does_not_create_report` | `main.py` stops for a missing Pod and writes no report |
| `test_missing_api_key_gives_clear_message` | No API key gives a clear message and no tool calls |
| `test_prompt_asks_for_rca_sections` | The instructions ask for the RCA sections |
| `test_tool_definitions_describe_every_tool` | Claude receives all 7 tools, including `describe_node` |
| `test_agent_runs_the_tools_claude_chooses` | The agent runs the tool Claude asks for and sends the result back |
| `test_agent_rejects_unsafe_tool_input` | Unsafe input and unknown tools are refused without running `kubectl` |
| `test_agent_stops_at_step_limit` | The loop stops after 10 rounds and switches tools off at the end |

#### Run the tests

```bash
cd ~/agent
source .venv/bin/activate
pytest -v
```

Recorded output:

```text
collected 21 items

tests/test_pod_tools.py::test_healthy_pod_status_is_parsed PASSED        [  4%]
tests/test_pod_tools.py::test_broken_pod_status_shows_waiting_reason PASSED [  9%]
tests/test_pod_tools.py::test_crashloop_pod_status_shows_last_state PASSED [ 14%]
tests/test_pod_tools.py::test_missing_pod_returns_error PASSED           [ 19%]
tests/test_pod_tools.py::test_metrics_error_is_reported PASSED           [ 23%]
tests/test_pod_tools.py::test_previous_logs_use_previous_flag PASSED     [ 28%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[] PASSED        [ 33%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[Bad_Name] PASSED [ 38%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[pod;rm -rf] PASSED [ 42%]
tests/test_pod_tools.py::test_invalid_names_are_rejected[-starts-with-dash] PASSED [ 47%]
tests/test_pod_tools.py::test_report_contains_pod_identity_and_metrics PASSED [ 52%]
tests/test_pod_tools.py::test_report_marks_missing_metrics PASSED        [ 57%]
tests/test_pod_tools.py::test_report_separates_usage_from_configured_limits PASSED [ 61%]
tests/test_pod_tools.py::test_report_contains_rca_steps_and_previous_logs PASSED [ 66%]
tests/test_pod_tools.py::test_missing_pod_does_not_create_report PASSED  [ 71%]
tests/test_pod_tools.py::test_missing_api_key_gives_clear_message PASSED [ 76%]
tests/test_pod_tools.py::test_prompt_asks_for_rca_sections PASSED        [ 80%]
tests/test_pod_tools.py::test_tool_definitions_describe_every_tool PASSED [ 85%]
tests/test_pod_tools.py::test_agent_runs_the_tools_claude_chooses PASSED [ 90%]
tests/test_pod_tools.py::test_agent_rejects_unsafe_tool_input PASSED     [ 95%]
tests/test_pod_tools.py::test_agent_stops_at_step_limit PASSED           [100%]

============================== 21 passed in 3.91s ==============================
```

All 21 tests must pass. The time will be different on your machine.

### Part B — Real investigation on the cluster

#### Step 8.1 — Make sure the cluster is running

```bash
k3d cluster list
kubectl get nodes
```

If the cluster is stopped (for example after a reboot), start it:

```bash
k3d cluster start pod-lab
```

Both nodes must be `Ready`.

#### Step 8.2 — Investigate the healthy HTTPD Pod

The HTTPD app from Phase 2 must be running:

```bash
kubectl get pods -n ai-sre-lab -l app=demo-web
```

Copy the Pod name (it starts with `demo-web-`) and run:

```bash
cd ~/agent
source .venv/bin/activate
python main.py --pod <DEMO_WEB_POD_NAME> --namespace ai-sre-lab
```

Recorded output:

```text
=== LW-RCA-analyzer ===
Investigating pod demo-web-665f97df4c-mj54n in namespace ai-sre-lab (read-only).

[1/3] Checking that the pod exists...
Pod found: phase=Running, node=k3d-pod-lab-agent-0

[2/3] LW-RCA-analyzer is investigating (Claude chooses the read-only tools)...
  Step 1: inspect_pod {"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}
  Step 1: read_pod_events {"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}
  Step 1: read_pod_logs {"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}
  Step 1: read_pod_cpu_ram {"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}
  Step 2: describe_pod {"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}
  Step 2: describe_node {"node_name": "k3d-pod-lab-agent-0"}

[3/3] Collecting evidence and writing the RCA report...

Report created successfully:
reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_045410.md

Open it with:
cat reports/incident_ai-sre-lab_demo-web-665f97df4c-mj54n_20261031_045410.md
```

**What happened:**

- `[1/3]` confirmed that the Pod exists.
- `[2/3]` In step 1, Claude asked for four tools at once. After reading the results, it decided in step 2 to look at the Pod details **and the node** (`describe_node`). Nobody told it to check the node; it decided that from the evidence.
- `[3/3]` saved the report.

The `[2/3]` stage takes about 1–2 minutes, because Claude thinks between rounds. The tools it chooses can be a little different on every run.

**Open the report** (use the path printed on your screen):

```bash
cat reports/incident_ai-sre-lab_<POD_NAME>_<TIMESTAMP>.md
```

Key parts of the recorded report:

```markdown
# LW-RCA-analyzer: Kubernetes Pod Incident and Root Cause Analysis (RCA) Report

- **Generated at (local time):** 2026-10-31T04:54:10
- **Evidence collected at (UTC):** 2026-10-30T23:24:06.519997+00:00
- **Pod name:** demo-web-665f97df4c-mj54n
- **Namespace:** ai-sre-lab
- **Status:** Running
- **Node:** k3d-pod-lab-agent-0
- **Pod IP:** 10.42.1.4
- **Created:** 2026-10-30T21:15:54Z

[...]

## AI agent investigation steps

LW-RCA-analyzer chose these read-only tools itself. Tools with the same step number were called together.

- Step 1: `inspect_pod` with `{"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_events` with `{"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_logs` with `{"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_cpu_ram` with `{"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}`
- Step 2: `describe_pod` with `{"pod_name": "demo-web-665f97df4c-mj54n", "namespace": "ai-sre-lab"}`
- Step 2: `describe_node` with `{"node_name": "k3d-pod-lab-agent-0"}`

## Root cause analysis (AI-generated, advisory)

### 1. Executive summary
**No incident detected.** Pod `demo-web-665f97df4c-mj54n` in namespace `ai-sre-lab` is healthy. It is `Running`, its single `httpd` container is Ready with 0 restarts, and all pod conditions are True. It has no events and is serving HTTP 200 responses. Live usage is very low (1m CPU, 6Mi memory). Its node, `k3d-pod-lab-agent-0`, is Ready with no pressure conditions and no taints. I found no root cause because there is no failure to explain.

[...]

### 6. Root cause
**No incident detected.** The evidence shows no failure, so I am not stating a root cause.

[...]

### 12. Confidence level and evidence gaps
**Confidence: High** that the pod is healthy right now.

Gaps:
- Events from pod startup have expired, so I can't confirm why the container took about 70s to start (likely an image pull).
- Metrics are a single live reading. I had no historical CPU or memory data.
- I didn't check the Service, Endpoints or Ingress, so I haven't confirmed that the pod can be reached from outside.
- I didn't check the Deployment or ReplicaSet (for example, how many replicas are available).
- I don't know why the node's conditions changed at 21:58:54 UTC, because node events from that time are not shown.

[...]
```

**Check that:**

- [ ] The title starts with `LW-RCA-analyzer`.
- [ ] Status is `Running`, and the `httpd` container is ready with 0 restarts.
- [ ] Live CPU/RAM shows real numbers.
- [ ] Configured requests/limits are `50m`/`250m` CPU and `64Mi`/`128Mi` memory (from `demo.yaml`).
- [ ] The **AI agent investigation steps** section lists the tools the agent chose.
- [ ] The RCA says **"No incident detected"**. It does not invent a problem.

**About the logs:** the HTTPD logs contain `AH00558: Could not reliably determine the server's fully qualified domain name`. This is a normal start-up message of the default `httpd` image, not an error. The RCA correctly treats it as harmless.

#### Step 8.3 — Create a Pod with a wrong image

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

- `image: httpd:tag-that-does-not-exist` — the `httpd` image exists, but this tag does not. The image download will fail.
- It is a bare Pod with a fixed name, so it is easy to investigate. It does not touch the healthy app.

```bash
kubectl apply -f ~/agent/k8s/broken-pod.yaml
kubectl get pod broken-image-demo -n ai-sre-lab -w
```

`-w` watches the status. Wait until it shows `ErrImagePull` or `ImagePullBackOff`, then press `Ctrl+C`.

Recorded output:

```text
NAME                READY   STATUS             RESTARTS   AGE
broken-image-demo   0/1     ImagePullBackOff   0          18s
```

| Status | Meaning |
|---|---|
| `ErrImagePull` | The image download just failed |
| `ImagePullBackOff` | Kubernetes waits before trying again; the wait gets longer each time |

Check it by hand:

```bash
kubectl logs broken-image-demo -n ai-sre-lab
kubectl top pod broken-image-demo -n ai-sre-lab
```

Recorded output:

```text
Error from server (BadRequest): container "web" in pod "broken-image-demo" is waiting to start: trying and failing to pull image
Error from server (NotFound): pods "broken-image-demo" not found
```

**There are no logs and no CPU/RAM numbers**, because the container never started. This is normal.

#### Step 8.4 — Investigate the wrong-image Pod

```bash
python main.py --pod broken-image-demo --namespace ai-sre-lab
```

Recorded output:

```text
=== LW-RCA-analyzer ===
Investigating pod broken-image-demo in namespace ai-sre-lab (read-only).

[1/3] Checking that the pod exists...
Pod found: phase=Pending, node=k3d-pod-lab-agent-0

[2/3] LW-RCA-analyzer is investigating (Claude chooses the read-only tools)...
  Step 1: inspect_pod {"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}
  Step 1: read_pod_events {"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}
  Step 1: describe_pod {"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}

[3/3] Collecting evidence and writing the RCA report...

Report created successfully:
reports/incident_ai-sre-lab_broken-image-demo_20261031_045452.md

Open it with:
cat reports/incident_ai-sre-lab_broken-image-demo_20261031_045452.md
```

**What happened:** Claude read the status, events, and Pod details. It **did not read the logs**, because the container never started, so there are no logs.

Key parts of the recorded RCA:

```markdown
## AI agent investigation steps

LW-RCA-analyzer chose these read-only tools itself. Tools with the same step number were called together.

- Step 1: `inspect_pod` with `{"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_events` with `{"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}`
- Step 1: `describe_pod` with `{"pod_name": "broken-image-demo", "namespace": "ai-sre-lab"}`

## Root cause analysis (AI-generated, advisory)

### 1. Executive summary
Pod `broken-image-demo` in namespace `ai-sre-lab` has never started. Its only container, `web`, uses the image `httpd:tag-that-does-not-exist`. The registry says that tag does not exist (`NotFound`), so the kubelet can't pull the image and keeps retrying with backoff (`ImagePullBackOff`). The pod has been stuck in `Pending` for about 2 hours. The cluster, node and scheduling look fine; the problem is in the pod spec.

[...]

### 6. Root cause
**Confirmed root cause:** The pod spec points to an image tag that does not exist, `httpd:tag-that-does-not-exist`. The registry (`docker.io/library/httpd`) answered `NotFound` when asked for that tag. Without an image, the kubelet can't create the container and keeps retrying with backoff.

[...]

### 12. Confidence level and evidence gaps
**Confidence: High.** The kubelet's error message names the exact cause (`NotFound` for that image reference), and the pod condition and events match it.

Gaps:
- I didn't collect live CPU or RAM metrics. They wouldn't mean much anyway, because the container never ran.
- I didn't read any logs, because there was never a running container to produce them.
- I didn't describe the node. The pod was scheduled and the error comes from the registry, not the node, so I don't think node health is involved, but I didn't check it.
- I can't tell who applied the manifest or why (deliberate demo or mistake). I didn't check for a Service that selects `app=broken-image-demo`.

[...]
```

**Check that:**

- [ ] Status is `Pending`; the container state shows `ImagePullBackOff`.
- [ ] Live CPU/RAM is `Unavailable` with the real Kubernetes error.
- [ ] The RCA says **"Confirmed root cause"**: the image tag does not exist. Confidence: High.
- [ ] The RCA explains which tools it did not use and why.

#### Step 8.5 — Create a crashing Pod and investigate it

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

- `image: busybox:1.36` — a tiny image with a shell, used to simulate an application.
- `command:` — a small script. It prints start-up messages, prints a configuration error, and **always** exits with code `1` (failure).
- Kubernetes restarts the container after every exit, with a longer wait each time. This is `CrashLoopBackOff`.
- The script never really checks for the file; it always fails. This tests whether the agent reads the evidence carefully.

```bash
kubectl apply -f ~/agent/k8s/crashloop-pod.yaml
kubectl get pod crashloop-demo -n ai-sre-lab -w
```

Wait until `RESTARTS` is 3 or more (about one minute), then press `Ctrl+C`.

Recorded output:

```text
NAME             READY   STATUS   RESTARTS      AGE
crashloop-demo   0/1     Error    3 (30s ago)   52s
```

The status changes between `Error`, `CrashLoopBackOff`, and briefly `Running`. Check the logs by hand:

```bash
kubectl logs crashloop-demo -n ai-sre-lab
```

Recorded output:

```text
Starting payment-api v1.4.2
Loading configuration from /etc/app/config.yaml
ERROR: configuration file /etc/app/config.yaml not found
```

Now run the agent:

```bash
python main.py --pod crashloop-demo --namespace ai-sre-lab
```

Recorded output:

```text
=== LW-RCA-analyzer ===
Investigating pod crashloop-demo in namespace ai-sre-lab (read-only).

[1/3] Checking that the pod exists...
Pod found: phase=Running, node=k3d-pod-lab-agent-0

[2/3] LW-RCA-analyzer is investigating (Claude chooses the read-only tools)...
  Step 1: describe_pod {"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}
  Step 1: read_pod_events {"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}
  Step 1: read_previous_pod_logs {"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}
  Step 1: read_pod_logs {"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}
  Step 1: read_pod_cpu_ram {"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}

[3/3] Collecting evidence and writing the RCA report...

Report created successfully:
reports/incident_ai-sre-lab_crashloop-demo_20261031_045543.md

Open it with:
cat reports/incident_ai-sre-lab_crashloop-demo_20261031_045543.md
```

**What happened:** Claude chose five tools in one round, including **`read_previous_pod_logs`**, because the error of a crashing container is in the previous run.

**The full recorded report** (`reports/incident_ai-sre-lab_crashloop-demo_20261031_045543.md`, with the long `Pod description` section removed):

````markdown
# LW-RCA-analyzer: Kubernetes Pod Incident and Root Cause Analysis (RCA) Report

- **Generated at (local time):** 2026-10-31T04:55:43
- **Evidence collected at (UTC):** 2026-10-30T23:25:40.457070+00:00
- **Pod name:** crashloop-demo
- **Namespace:** ai-sre-lab
- **Status:** Running
- **Node:** k3d-pod-lab-agent-0
- **Pod IP:** 10.42.1.10
- **Created:** 2026-10-30T22:38:27Z

## Actual CPU and RAM usage (live, from kubectl top)

```text
Unavailable
```

**Live metrics could not be retrieved.** kubectl top failed. Metrics Server may not be installed, may not be ready, or the pod may not have metrics yet.

Kubernetes said: `Error from server (NotFound): podmetrics.metrics.k8s.io "ai-sre-lab/crashloop-demo" not found`

> CPU/RAM above is live usage from Kubernetes Metrics Server when available. It is not the pod's configured limit. If marked unavailable, no usage number was invented.

## Configured CPU and RAM (requests and limits from the pod spec)

| Container | CPU request | CPU limit | Memory request | Memory limit |
|---|---|---|---|---|
| app | 10m | 100m | 16Mi | 32Mi |

> Requests and limits are configuration settings, not measurements.

## Container state

```json
[
  {
    "name": "app",
    "ready": false,
    "restart_count": 13,
    "waiting_reason": "CrashLoopBackOff",
    "state": {
      "waiting": {
        "message": "back-off 5m0s restarting failed container=app pod=crashloop-demo_ai-sre-lab(79bc46a7-536c-42de-9fdb-dc92a2284e21)",
        "reason": "CrashLoopBackOff"
      }
    },
    "last_state": {
      "terminated": {
        "containerID": "containerd://253599b2c92aa2b4544196393100ccce636fd5757b7adcc833db6965f11e9402",
        "exitCode": 1,
        "finishedAt": "2026-10-30T23:21:09Z",
        "reason": "Error",
        "startedAt": "2026-10-30T23:21:09Z"
      }
    }
  }
]
```

## Kubernetes events

```text
FIRST_SEEN             LAST_SEEN              COUNT    TYPE      REASON      SOURCE    MESSAGE
<nil>                  <nil>                  <none>   Normal    Scheduled   <none>    Successfully assigned ai-sre-lab/crashloop-demo to k3d-pod-lab-agent-0
2026-10-30T22:38:32Z   2026-10-30T22:54:54Z   9        Normal    Started     kubelet   Container started
2026-10-30T22:38:31Z   2026-10-30T23:00:01Z   10       Normal    Created     kubelet   Container created
2026-10-30T22:38:31Z   2026-10-30T23:21:08Z   14       Normal    Pulled      kubelet   Container image "busybox:1.36" already present on machine and can be accessed by the pod
2026-10-30T22:38:35Z   2026-10-30T23:23:54Z   40       Warning   BackOff     kubelet   Back-off restarting failed container app in pod crashloop-demo_ai-sre-lab(79bc46a7-536c-42de-9fdb-dc92a2284e21)
```

## Recent logs

```text
ERROR: configuration file /etc/app/config.yaml not found
Starting payment-api v1.4.2
Loading configuration from /etc/app/config.yaml
```

## Previous container logs (before the last restart)

```text
ERROR: configuration file /etc/app/config.yaml not found
Starting payment-api v1.4.2
Loading configuration from /etc/app/config.yaml
```

## Pod description

[... removed here to keep the README short ...]

## AI agent investigation steps

LW-RCA-analyzer chose these read-only tools itself. Tools with the same step number were called together.

- Step 1: `describe_pod` with `{"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_events` with `{"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}`
- Step 1: `read_previous_pod_logs` with `{"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_logs` with `{"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}`
- Step 1: `read_pod_cpu_ram` with `{"pod_name": "crashloop-demo", "namespace": "ai-sre-lab"}`

## Root cause analysis (AI-generated, advisory)

### 1. Executive summary
Pod `crashloop-demo` in namespace `ai-sre-lab` is in **CrashLoopBackOff**. It has restarted 13 times in about 46 minutes. Each time, the only container (`app`, image `busybox:1.36`) exits with code 1 immediately after starting. It logs `ERROR: configuration file /etc/app/config.yaml not found`. The pod spec shows why: the container command is a hard-coded shell script that prints this error and then runs `exit 1` every time. No volume is mounted at `/etc/app` either. The failure comes from the pod's own configuration, not from the node, resources or the image.

### 2. Problem statement
Container `app` keeps exiting with code 1 (`Reason: Error`). The kubelet keeps restarting it with increasing back-off delays. The pod never becomes Ready (`Ready=False`, `ContainersReady=False`).

### 3. Impact
- The workload, which logs itself as "payment-api v1.4.2", has not served anything since it was scheduled. It has never been Ready.
- Any Service routing to label `app=crashloop-demo` would have no ready endpoints. I did not check whether such a Service exists.
- Impact on other parts of the cluster is low. Each run is very short, ending in the same second it starts (`Started`/`Finished` both 04:51:09 +0530).

### 4. Timeline (UTC)
| Time (UTC) | Event |
|---|---|
| 2026-10-30 22:38:27 | Pod start time (04:08:27 +0530). It was scheduled to `k3d-pod-lab-agent-0`. |
| 22:38:31 | First `Pulled` and `Created` events. The image `busybox:1.36` was already on the node. |
| 22:38:32 | First `Started` event |
| 22:38:35 | First `BackOff` warning, 3 seconds after the first start |
| 22:54:54 | Last recorded `Started` event (9 in total) |
| 23:00:01 | Last recorded `Created` event (10 in total) |
| 23:21:08–23:21:09 | Last `Pulled` event (14 in total). The latest run started and finished at 23:21:09 (04:51:09 +0530) with exit code 1. |
| 23:23:54 | Last recorded `BackOff` warning (40 in total). Restart count is 13. |

### 5. Confirmed observations
- **State:** `Waiting / CrashLoopBackOff`. Last state was `Terminated`, `Reason: Error`, `Exit Code: 1`. Restart count is 13.
- **Container command** (from the pod spec):
  ```sh
  echo "Starting payment-api v1.4.2"
  echo "Loading configuration from /etc/app/config.yaml"
  echo "ERROR: configuration file /etc/app/config.yaml not found" >&2
  exit 1
  ```
- **Logs:** the current and previous logs are the same: the two startup lines plus the error line. The error line appears first, probably because stdout and stderr were collected in a different order.
- **Mounts:** the only mount is the service-account token at `/var/run/secrets/kubernetes.io/serviceaccount`. There is no ConfigMap, Secret or other volume at `/etc/app`.
- **Image:** `busybox:1.36` was already present on the node. There are no pull errors.
- **Scheduling and node:** `PodScheduled=True` on `k3d-pod-lab-agent-0`. The events show no node problems, evictions or OOMKilled.
- **Resources:** limits are cpu 100m / memory 32Mi and requests are cpu 10m / memory 16Mi. These are settings, not measured usage. The termination reason is `Error`, not `OOMKilled`.
- **Live CPU/RAM:** not available. `kubectl top` returned `podmetrics ... not found`. Metrics Server may be missing, or the pod lives too briefly to be measured.

### 6. Root cause
**Confirmed root cause:** the container's startup command always fails. It prints the "config not found" error and then runs `exit 1` without condition, so every start exits with code 1. Kubernetes restarts the container and applies exponential back-off, which produces CrashLoopBackOff.

There is also a secondary, matching gap: no volume is mounted at `/etc/app`, so `/etc/app/config.yaml` would not exist even if a real application were checking for it. However, the script never actually checks for the file. It exits regardless. Adding the config file alone would not fix this pod.

### 7. Contributing factors
- The configuration file the application message refers to is not delivered by any ConfigMap or Secret volume.
- There is no startup validation or pre-deployment check that would catch a spec that always fails.
- The image is a placeholder (`busybox` running an inline script) rather than a real application image.
- Metrics Server data is missing, which limits resource observability. It did not cause this incident.

### 8. Five whys
1. **Why is the pod not Ready?** Container `app` is in CrashLoopBackOff.
2. **Why CrashLoopBackOff?** The container exits with code 1 every time it starts (13 restarts, 40 BackOff events).
3. **Why does it exit with code 1?** The command logs "configuration file /etc/app/config.yaml not found" and then runs `exit 1`.
4. **Why does the command do that?** The pod spec hard-codes this failing script. It looks like it is meant to simulate an app that cannot find its config. And no config volume is mounted at `/etc/app`.
5. **Why did this reach the cluster?** Most likely there was no review or validation of the pod spec and its config dependencies before deployment. This is not confirmed; there is no evidence about the deployment process.

### 9. Corrective actions
All of these are **not performed by the agent; requires human approval**.
1. Replace the container command or image with the real application entrypoint, or remove the unconditional `exit 1`.
2. Create a ConfigMap or Secret that holds `config.yaml` and mount it at `/etc/app`.
3. Pods are immutable, so delete and recreate the pod (or update the controller that owns it) with the corrected spec.
4. If this pod is only a lab or demo artifact that is no longer needed, delete it to stop the restart loop.

### 10. Preventive actions
All of these are **not performed by the agent; requires human approval**.
- Make the application check for required config at startup and give a clear message, and declare config dependencies in the manifest (volume plus `volumeMounts`).
- Add CI checks on manifests, such as kubeconform, policy checks with OPA/Kyverno, or a dry-run, to catch missing config mounts.
- Add a readiness probe, plus alerts on `kube_pod_container_status_restarts_total` and on CrashLoopBackOff.
- Install Metrics Server, or fix it if it is broken, so live CPU/RAM data is available in future investigations.

### 11. Verification steps
After a fix is applied:
- `kubectl get pod crashloop-demo -n ai-sre-lab -w`: the pod should be `Running`, `READY 1/1`, and the restart count should stop rising.
- `kubectl describe pod crashloop-demo -n ai-sre-lab`: there should be a mount at `/etc/app` and no new `BackOff` events.
- `kubectl logs crashloop-demo -n ai-sre-lab`: the "configuration file ... not found" error should be gone.
- `kubectl exec crashloop-demo -n ai-sre-lab -- ls /etc/app/config.yaml`: the file should exist.
- `kubectl top pod crashloop-demo -n ai-sre-lab` (once Metrics Server works): usage should be within the limits.

### 12. Confidence level and evidence gaps
**Confidence: high.** The pod spec, the exit code, and the current and previous logs all directly show that the container is scripted to fail.

Evidence gaps:
- Live CPU/RAM metrics were not available (`kubectl top` failed).
- I did not identify the owning controller (Deployment, Job, etc.), if there is one. `describe` shows no "Controlled By" field, which suggests this is a standalone pod.
- I did not check for a Service or anything else that depends on this pod, so the downstream impact is unknown.
- I did not describe the node `k3d-pod-lab-agent-0`. Nothing in the events pointed to a node problem.
- There is no information about how or why this spec was deployed, or whether the failure is intentional (for example, a fault-injection lab).

## Verification and limitations

- This report is based on evidence collected from the current Kubernetes cluster.
- The AI analysis is advisory; verify recommendations before making changes.
- LW-RCA-analyzer did not restart, delete, or modify the pod.
- Missing metrics or unavailable logs are reported as unavailable, not guessed.
````

**Things to notice:**

- **Status is `Running`**, even though the container keeps crashing. Kubernetes keeps the Pod phase `Running` while it restarts the container. The real story is in **Container state**: `CrashLoopBackOff`, `restart_count: 13`, and `last_state` with `exitCode: 1`.
- **Events have exact times.** `BackOff` happened 40 times between `22:38:35Z` and `23:23:54Z`.
- **The RCA looked deeper than the log message.** The log says "configuration file not found", but the agent read the container command and found that the script **always** runs `exit 1`. So adding the config file alone would not fix it.
- **Honest about gaps:** It says what it did not check (Service, node, owner) and that CPU/RAM metrics were unavailable.
- **Read-only:** every fix is marked "not performed by the agent; requires human approval".

**Check that:**

- [ ] Container state shows restarts, `CrashLoopBackOff` (or `terminated`), and `last_state` with exit code 1.
- [ ] The agent steps include `read_previous_pod_logs` or `read_pod_logs`.
- [ ] The RCA names the unconditional `exit 1` as the **confirmed root cause**.

#### Step 8.6 — Compare the three investigations

All values are from the recorded reports.

| | Healthy HTTPD | Wrong image | Crashing Pod |
|---|---|---|---|
| Status | `Running` | `Pending` | `Running` (restarting) |
| Container | ready, 0 restarts | not ready, 0 restarts | not ready, 13 restarts |
| Waiting reason | — | `ImagePullBackOff` | `CrashLoopBackOff` |
| Live CPU/RAM | `1m` / `6Mi` | Unavailable | Unavailable |
| Logs | Apache start-up + HTTP 200 lines | "waiting to start" error | the configuration error |
| **Tools the agent chose** | status, events, logs, CPU/RAM, then `describe_pod`, **`describe_node`** | status, events, `describe_pod` | `describe_pod`, events, logs, **previous logs**, CPU/RAM |
| **Root cause** | **No incident detected** | **Confirmed:** image tag does not exist | **Confirmed:** command always runs `exit 1` |
| **Confidence** | High | High | High |

#### Step 8.7 — Test the error handling

```bash
python main.py --pod ghost --namespace ai-sre-lab
python main.py --pod Bad_Name
```

Recorded output:

```text
=== LW-RCA-analyzer ===
Investigating pod ghost in namespace ai-sre-lab (read-only).

[1/3] Checking that the pod exists...
Could not find the pod: Error from server (NotFound): pods "ghost" not found
Check the pod name and namespace with: kubectl get pods -n ai-sre-lab
```

```text
Invalid pod name: 'Bad_Name'
Names may only use lowercase letters, numbers, '-' and '.'.
```

Both stop with exit code 1. **Claude is not called and no report is created.**

#### Step 8.8 — Clean up the test Pods

The agent never deletes anything. You do this yourself:

```bash
kubectl delete pod broken-image-demo -n ai-sre-lab
kubectl delete pod crashloop-demo -n ai-sre-lab
```

This deletes only the two test Pods; the HTTPD app keeps running. To delete the whole lab cluster:

```bash
k3d cluster delete pod-lab
```

---

## Troubleshooting

For each problem: what it means, how to see it, how to fix it, and how to check the fix.

### 1. Docker service not running

- **Meaning:** Docker is stopped, so k3d cannot start the cluster.
- **You see:** `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`.
- **Fix:**

  ```bash
  sudo systemctl enable --now docker
  sudo systemctl status docker --no-pager
  ```

  If you see `permission denied` on `/var/run/docker.sock`, add your user to the `docker` group (Phase 1) and log in again.
- **Check:** `docker ps` works without errors.

### 2. k3d cluster creation fails

- **You see:** `k3d cluster create` stops with an error, such as "cluster already exists" or "port is already allocated".
- **Fix:**
  - Make sure Docker runs (problem 1).
  - If the cluster already exists: `k3d cluster start pod-lab`, or delete it with `k3d cluster delete pod-lab` and create it again.
  - Check disk space: `df -h /var/lib/docker`.
- **Check:** `kubectl get nodes` shows two `Ready` nodes.

### 3. kubectl connection errors

- **You see:** `The connection to the server 0.0.0.0:<port> was refused`. The agent prints `Could not find the pod: ...` with the same error.
- **Fix:**

  ```bash
  k3d cluster list
  k3d cluster start pod-lab
  kubectl config use-context k3d-pod-lab
  ```

  If it still fails: `k3d kubeconfig merge pod-lab --kubeconfig-switch-context`.
- **Check:** `kubectl get nodes` shows both nodes `Ready`.

### 4. Pod stuck in Pending

- **Meaning:** The Pod exists, but no container is running yet.
- **You see:** `kubectl get pod` shows `Pending`. In the report, **Node** may say `Not scheduled`.
- **Fix:** run `kubectl describe pod <pod> -n ai-sre-lab` and read the events:
  - `FailedScheduling ... Insufficient cpu/memory`: the Pod asks for more than the nodes have.
  - `ErrImagePull` / `ImagePullBackOff`: see problem 5.
- **Check:** after a human fixes the cause, the Pod becomes `Running`.

### 5. ImagePullBackOff / ErrImagePull

- **Meaning:** Kubernetes cannot download the container image.
- **You see:** events with `Failed to pull image`; the report shows `waiting_reason: "ImagePullBackOff"`.
- **Fix:** check the image name and tag:

  ```bash
  kubectl get pod <pod> -n ai-sre-lab -o jsonpath='{.spec.containers[*].image}'
  ```

  Also check that the node has internet access. (For `broken-image-demo` the failure is on purpose.)
- **Check:** after a corrected Pod is created, the events show `Pulled` and `Started`.

### 6. CrashLoopBackOff

- **Meaning:** The container starts, exits, and Kubernetes keeps restarting it.
- **You see:** `CrashLoopBackOff` or `Error`, and a growing restart count. The report's `last_state` shows the exit code and reason.
- **Fix:** run LW-RCA-analyzer; it reads the previous logs and `last_state`. By hand:

  ```bash
  kubectl logs <pod> -n ai-sre-lab --previous
  kubectl describe pod <pod> -n ai-sre-lab | grep -A5 "Last State"
  ```

  `OOMKilled` means the container used more memory than its limit. `Error` with exit code 1 means the application itself failed. If `--previous` says `unable to retrieve container logs`, wait a few seconds and try again.
- **Check:** after the fix, the restart count stops growing.

### 7. Missing Kubernetes metrics

- **Meaning:** `kubectl top` has no data, so the report shows CPU/RAM as `Unavailable`.
- **You see:** `Live metrics could not be retrieved.` and an error like `metrics not available yet`.
- **Fix:**

  ```bash
  kubectl -n kube-system get deployment metrics-server
  kubectl top nodes
  ```

  - Right after the cluster or Pod starts, wait about a minute.
  - If the container is not running (wrong image, crash loop), there is nothing to measure. That is normal.
  - If `metrics-server` does not exist, install it from the official manifest:

    ```bash
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
    kubectl -n kube-system rollout status deployment/metrics-server --timeout=120s
    ```

- **Check:** `kubectl top pod -n ai-sre-lab` shows numbers.

### 8. Python package errors

- **You see:** `ModuleNotFoundError: No module named 'anthropic'` (or `langchain_core`, `dotenv`).
- **Fix:**

  ```bash
  cd ~/agent
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

- **Check:** `python -c "import anthropic, langchain_core, dotenv; print('imports OK')"`.

### 9. Missing settings in `.env`

- **You see:** the RCA section says `AI explanation unavailable: set a valid ANTHROPIC_API_KEY in .env.` or `set ANTHROPIC_MODEL in .env.`, and the steps section says `No tools were called by the AI agent.`
- **Fix:**
  - `.env` must be in `~/agent`, and you must run the program from `~/agent`.
  - Check the variable names (without showing the values): `grep -o '^[A-Z_]*=' .env`
  - No spaces around `=` and no quotes.
  - A variable already set in your terminal wins over `.env`. Check with `env | grep -o '^ANTHROPIC_[A-Z_]*'` and remove an old one with `unset ANTHROPIC_API_KEY`.
- **Check:** a new run prints `Step 1: ...` lines in `[2/3]`.

### 10. Invalid API key

- **You see:** `AI explanation unavailable: the API key was rejected.`
- **Fix:** create a new key in the Anthropic Console, paste it into `.env`, and check that your account has billing set up.
- **Check:** a new run shows agent steps and an RCA.

### 11. Other Claude API errors

| Message in the report | Meaning | Fix |
|---|---|---|
| `model '...' was not found.` | The model ID is wrong or not in your account | Set `ANTHROPIC_MODEL` to a model ID from your Anthropic Console |
| `rate limit or quota reached.` | Too many requests, or no credit left | Wait and try again; check your usage and billing |
| `could not connect to the Claude API.` | No internet, DNS, proxy, or firewall problem | Test with `curl -I https://api.anthropic.com` |
| `API error <code>.` | Another API error (for example 500 or 529) | Try again later |
| `Claude declined this request.` | Claude refused | Try again |

### 12. The report is missing or cannot be written

- **You see:** a `PermissionError`, or no report in `~/agent/reports`.
- **Fix:**
  - Run the program from `~/agent`.
  - Check write permission: `touch reports/test && rm reports/test`.
  - Check disk space: `df -h .`.
- **Check:** `ls -lt reports/` shows a new `incident_...md` file.

### 13. pytest fails

- **You see:** `FAILED`, or `ModuleNotFoundError: No module named 'pod_tools'`.
- **Fix:**
  - Run `pytest` from `~/agent`, where `pytest.ini` is.
  - Turn on the virtual environment.
  - A typing mistake while copying code is the most common cause. Compare your file with the README, and read the first error line that names one of your files.
  - Run one test: `pytest -v tests/test_pod_tools.py::<test_name>`.
- **Check:** `pytest -q` shows `21 passed`.

### 14. The agent takes long or uses different tools each time

- **Meaning:** This is normal. Claude thinks between rounds (about 1–2 minutes in total) and decides each time which tools to use.
- **If it never finishes:** the loop always stops after 10 rounds. Check your internet connection and problem 11.

---

## Security and Limitations

### Keep secrets safe

- The API key is only in `~/agent/.env`, which is in `.gitignore`.
- `chmod 600 .env` makes it readable only by you.
- The code never prints or saves the key.
- Commit `.env.example`, **never** `.env`. Before your first commit, check with `git status --ignored` that `.env` is listed as ignored.
- If a key is ever leaked, revoke it in the Anthropic Console at once.

### Reports and data

Reports contain logs, IP addresses, and node names, so they are ignored by Git. **The evidence the agent reads is also sent to the Claude API.** Do not run the agent on Pods whose logs contain data that your company does not allow to send to an external service.

### Why the agent is safe

- It only runs `kubectl get`, `logs`, `top`, and `describe`. None of these change the cluster.
- Claude chooses tools, but **only from the 7 read-only tools** in `ALL_TOOLS`. It has no shell and no write access. A tool that changes the cluster does not exist in this project.
- Every name Claude sends is checked by `validate_name()` before `kubectl` runs. Unknown tools are refused.
- The agent loop stops after at most 10 rounds.
- **If you add tools later, add only read-only tools.** An AI agent with a delete or restart tool would remove the human check.
- For extra safety, run the agent with a Kubernetes account that can only read (`get`, `list`, `watch`) Pods, logs, events, nodes, and metrics.

### Why a human must decide

An AI can be wrong and still sound confident. Changing a cluster can cause outages. So LW-RCA-analyzer only **recommends**; a human checks the evidence and makes the change.

### What LW-RCA-analyzer can do

- Investigate one Pod per run, choosing its own read-only checks, including the node.
- Read Pod status, container states, restarts, `last_state`, logs, previous logs, events, CPU/RAM, requests/limits, and the Pod and node descriptions.
- Write a 12-section RCA that separates confirmed facts from guesses.
- Say "No incident detected" for a healthy Pod.
- Save a report every time, even when the AI is not available.
- Refuse unsafe names and missing Pods.

### What LW-RCA-analyzer cannot do

- It does **not** restart, delete, scale, or repair anything. It is **not** self-healing.
- It does **not** look at Deployments, Services, other Pods, or k3s/kubelet logs (there are no tools for these).
- It does **not** watch the cluster all the time or send alerts. It runs once when you start it.
- It does **not** guess CPU/RAM when metrics are missing.
- Claude's wording and tool choices change from run to run.

---

## Quick Reference

```bash
# Start the lab
k3d cluster start pod-lab            # or: k3d cluster create pod-lab --agents 1 --servers 1
kubectl get nodes

# Deploy the demo Pods
kubectl apply -f ~/agent/k8s/demo.yaml
kubectl apply -f ~/agent/k8s/broken-pod.yaml
kubectl apply -f ~/agent/k8s/crashloop-pod.yaml
kubectl get pods -n ai-sre-lab

# Run LW-RCA-analyzer
cd ~/agent && source .venv/bin/activate
python main.py --pod <POD_NAME> --namespace ai-sre-lab
python main.py --namespace ai-sre-lab          # choose from a list
ls -lt reports/

# Tests
pytest -v

# Clean up
kubectl delete pod broken-image-demo crashloop-demo -n ai-sre-lab
k3d cluster delete pod-lab
```

---

## Appendix — Differences from manual.docs

`manual.docs` is the original course manual. The project has grown beyond it. This README follows the **current code**:

| Topic | `manual.docs` | This project |
|---|---|---|
| Name | Pod investigation agent | **LW-RCA-analyzer** |
| Demo app | NGINX Deployment | Apache **HTTPD** Deployment **and** a Service |
| How the AI is used | Python collects evidence; Claude explains it once | **AI agent:** Claude chooses read-only tools in a loop, then writes the RCA |
| AI output | Short explanation | 12-section **Root Cause Analysis** |
| Tools | 4 tools, called by Python | 7 tools chosen by Claude, including `describe_node` and previous logs |
| Files | `claude_client.py` | `agent.py` (the agent loop) |
| Events | Relative ages ("5m") | Exact UTC times, for a timeline |
| Test Pods | Broken image only | Broken image **and** a crash-looping Pod |
| Tests | 3 tests | 21 tests, including the agent with a fake Claude |
| Model in `.env` | `claude-3-5-sonnet-latest` | Set your own available model ID (`.env.example` uses `claude-opus-5-5`) |
| `K8S_NAMESPACE` setting | In `.env` | Removed; use `--namespace` |
| Project folder | `~/pod-investigation-agent` | `~/agent` |
| Restart "safety checkpoint" | Mentioned | Not needed: the agent has no restart ability at all |
