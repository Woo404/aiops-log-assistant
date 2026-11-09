"""API tests with mocked LLM — no real Ollama required."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.llm import LLMError
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_metrics(client: TestClient):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "aiops_analyze_requests_total" in r.text or r.text.startswith("#")


def test_analyze_requires_payload(client: TestClient):
    r = client.post("/analyze", json={})
    assert r.status_code == 422


def test_analyze_force_fallback_oom(client: TestClient):
    payload = {
        "text": "kernel: Out of memory: Killed process 99 (python)",
        "force_fallback": True,
    }
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_source"] == "rule_fallback"
    assert body["matched_rule"] == "oom_killer"
    assert body["severity"] == "critical"
    assert len(body["troubleshooting_steps"]) >= 2


def test_analyze_redacts_before_fallback(client: TestClient):
    payload = {
        "text": "Connection timed out to 192.168.1.10 from admin@corp.example",
        "force_fallback": True,
    }
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200
    body = r.json()
    preview = body.get("redacted_preview") or ""
    assert "192.168.1.10" not in preview
    assert "admin@corp.example" not in preview
    assert body["redaction_counts"]["ipv4"] >= 1
    assert body["redaction_counts"]["email"] >= 1


def test_analyze_alert_json_fallback(client: TestClient):
    payload = {
        "alert": {
            "status": "firing",
            "labels": {"alertname": "DiskFull", "instance": "db-1"},
            "annotations": {"description": "No space left on device on /var"},
        },
        "force_fallback": True,
    }
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200
    assert r.json()["matched_rule"] == "disk_full"


def test_analyze_llm_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_llm(payload: str, *, input_kind: str = "logs", context: str = ""):
        assert "[REDACTED_IP]" in payload or "10.1.2.3" not in payload
        return {
            "summary": "Network timeout to backend",
            "probable_root_cause": "Firewall or service down",
            "severity": "high",
            "troubleshooting_steps": ["curl the target", "check SG rules"],
            "confidence": 0.82,
            "analysis_source": "llm",
        }

    monkeypatch.setattr("app.main.analyze_with_llm", fake_llm)
    r = client.post(
        "/analyze",
        json={"text": "dial tcp 10.1.2.3:443: i/o timeout", "context": "api-gateway"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_source"] == "llm"
    assert body["severity"] == "high"
    assert body["confidence"] == 0.82


def test_analyze_llm_failure_falls_back(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def boom(*_a, **_k):
        raise LLMError("simulated outage")

    monkeypatch.setattr("app.main.analyze_with_llm", boom)
    r = client.post(
        "/analyze",
        json={"text": "ERROR 1040 (HY000): Too many connections"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_source"] == "rule_fallback"
    assert body["matched_rule"] == "mysql_connection"


def test_llm_json_extract_helpers():
    from app.llm import _extract_json, _normalize

    raw = '```json\n{"summary":"x","probable_root_cause":"y","severity":"LOW",'
    raw += '"troubleshooting_steps":["a"],"confidence":1.5}\n```'
    data = _normalize(_extract_json(raw))
    assert data["severity"] == "low"
    assert data["confidence"] == 1.0
    assert data["analysis_source"] == "llm"
