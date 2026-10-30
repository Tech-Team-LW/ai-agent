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
