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
