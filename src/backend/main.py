import json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path
from src.backend.core.schemas import (
    SystemStatusResponse,
    AssistantMessageRequest,
    AssistantMessageResponse,
    SkillExecuteRequest,
    SkillExecuteResponse
)
from src.backend.memory.repository import save_message, get_recent_history
from src.backend.skills.registry import get_skill_registry
from src.backend.core.llm import generate_llm_response, stream_llm_response

app = FastAPI(
    title="C.A.P.R.I. Assistant API",
    version="0.4.0",
    description="Cybernetic Autonomously Programmed Response Interface - Backend API"
)

@app.get("/", response_class=HTMLResponse)
def read_root():
    html_path = Path("src/frontend/index.html")
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>C.A.P.R.I. API Online</h1>"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "backend"}

@app.post("/api/v1/chat", response_model=AssistantMessageResponse)
async def process_message(payload: AssistantMessageRequest):
    save_message(session_id=payload.session_id, role="user", content=payload.message)
    history = get_recent_history(session_id=payload.session_id, limit=8)
    
    reply = await generate_llm_response(history)
    save_message(session_id=payload.session_id, role="assistant", content=reply)
    
    return AssistantMessageResponse(
        session_id=payload.session_id,
        response=reply,
        history_count=len(history) + 1
    )

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket de alta velocidad para streaming de tokens en tiempo real,
    retroalimentación de ejecución de ciberware/skills y baja latencia percibida.
    """
    await websocket.accept()
    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
            except Exception:
                await websocket.send_json({"type": "error", "message": "Payload JSON inválido."})
                continue

            session_id = payload.get("session_id", "default_ws_session")
            message = payload.get("message", "").strip()

            if not message:
                await websocket.send_json({"type": "error", "message": "Mensaje vacío."})
                continue

            # 1. Registrar mensaje del usuario en SQLite
            save_message(session_id=session_id, role="user", content=message)
            history = get_recent_history(session_id=session_id, limit=8)

            # 2. Transmitir eventos de streaming en vivo
            full_reply = ""
            async for event in stream_llm_response(history):
                await websocket.send_json(event)
                if event.get("type") == "token":
                    full_reply += event.get("delta", "")
                elif event.get("type") == "done":
                    full_reply = event.get("full_response", full_reply)

            # 3. Persistir la respuesta completa en SQLite
            if full_reply:
                save_message(session_id=session_id, role="assistant", content=full_reply)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

@app.post("/api/v1/skills/execute", response_model=SkillExecuteResponse)
async def execute_skill(payload: SkillExecuteRequest):
    registry = get_skill_registry()
    skill = registry.get(payload.skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Habilidad '{payload.skill_name}' no encontrada en el registro de C.A.P.R.I.")
    
    result = await registry.execute(payload.skill_name, params=payload.params)
    return SkillExecuteResponse(
        skill_name=payload.skill_name,
        result=result
    )
