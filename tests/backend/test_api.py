import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src.backend.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}

def test_root_hud():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "C.A.P.R.I." in response.text

def test_skill_execution_system_monitor():
    response = client.post("/api/v1/skills/execute", json={"skill_name": "system_monitor"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "result" in data
    assert data["result"]["status"] == "success"
    assert "memory_info" in data["result"]
    assert "disk_info" in data["result"]

def test_skill_execution_not_found():
    response = client.post("/api/v1/skills/execute", json={"skill_name": "non_existent_skill"})
    assert response.status_code == 404

@pytest.mark.anyio
@patch("src.backend.main.generate_llm_response", new_callable=AsyncMock)
def test_chat_endpoint_mocked(mock_generate):
    mock_generate.return_value = "C.A.P.R.I. respondiendo con éxito."
    
    response = client.post("/api/v1/chat", json={
        "session_id": "test_pytest_session",
        "message": "Hola Capri"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test_pytest_session"
    assert data["response"] == "C.A.P.R.I. respondiendo con éxito."
    assert data["status"] == "success"
    assert data["history_count"] >= 1

