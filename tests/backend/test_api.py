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

def test_websocket_chat_streaming():
    import json
    async def _mock_stream(history):
        yield {"type": "status", "stage": "connecting", "message": "Conectando..."}
        yield {"type": "token", "delta": "Hola "}
        yield {"type": "token", "delta": "choom!"}
        yield {"type": "done", "full_response": "Hola choom!"}

    with patch("src.backend.main.stream_llm_response", side_effect=_mock_stream):
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"session_id": "test_ws_session", "message": "Que pasa Capri"}))
            evt1 = ws.receive_json()
            assert evt1["type"] == "status"
            evt2 = ws.receive_json()
            assert evt2["type"] == "token"
            assert evt2["delta"] == "Hola "
            evt3 = ws.receive_json()
            assert evt3["type"] == "token"
            assert evt3["delta"] == "choom!"
            evt4 = ws.receive_json()
            assert evt4["type"] == "done"
            assert evt4["full_response"] == "Hola choom!"

def test_websocket_chat_invalid_payload():
    import json
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text("not a valid json")
        evt = ws.receive_json()
        assert evt["type"] == "error"
        assert "inválido" in evt["message"].lower()

        ws.send_text(json.dumps({"session_id": "s1", "message": "   "}))
        evt2 = ws.receive_json()
        assert evt2["type"] == "error"
        assert "vacío" in evt2["message"].lower()

@pytest.mark.anyio
async def test_freellmapi_fallback_disabled():
    from src.backend.core.llm import _call_freellmapi_fallback
    with patch.dict("os.environ", {"FREELLMAPI_BASE_URL": ""}):
        result = await _call_freellmapi_fallback([{"role": "user", "content": "hola"}])
        assert result is None

@pytest.mark.anyio
async def test_freellmapi_fallback_success():
    import httpx
    from src.backend.core.llm import _call_freellmapi_fallback
    mock_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "Respuesta desde FreeLLMAPI preem."}}]},
        request=httpx.Request("POST", "http://localhost:3000/v1/chat/completions")
    )
    with patch.dict("os.environ", {"FREELLMAPI_BASE_URL": "http://localhost:3000/v1"}):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            reply = await _call_freellmapi_fallback([{"role": "user", "content": "hola"}])
            assert reply == "Respuesta desde FreeLLMAPI preem."

@pytest.mark.anyio
async def test_stream_llm_response_fallback_all_down():
    from src.backend.core.llm import stream_llm_response
    with patch("src.backend.core.llm.get_gemini_client", return_value=None):
        with patch.dict("os.environ", {"FREELLMAPI_BASE_URL": "", "GROQ_API_KEY": ""}):
            events = []
            async for ev in stream_llm_response([{"role": "user", "content": "hola"}]):
                events.append(ev)
            types = [e["type"] for e in events]
            assert "token" in types
            assert "done" in types
            assert any("[SYSTEM ERROR]" in e.get("full_response", "") for e in events if e["type"] == "done")


