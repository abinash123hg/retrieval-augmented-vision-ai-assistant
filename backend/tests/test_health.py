from fastapi.testclient import TestClient

from app.api import health as health_route
from app.main import app
from app.services import ollama_service

client = TestClient(app)


def test_health_reports_ok(monkeypatch):
    monkeypatch.setattr(ollama_service, "check_ollama_connection", lambda: True)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ollama"] is True
    assert body["chat_model"] == "qwen2.5:1.5b"
    assert body["embedding_model"] == "nomic-embed-text:latest"


def test_health_reports_ollama_down(monkeypatch):
    monkeypatch.setattr(ollama_service, "check_ollama_connection", lambda: False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ollama"] is False


def test_health_route_module_exists():
    assert health_route.router is not None
