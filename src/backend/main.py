import json
import asyncio
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
from src.backend.voice import get_voice_manager

app = FastAPI(
    title="C.A.P.R.I. Assistant API",
    version="0.5.0",
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
                vm = get_voice_manager()
                if not vm.is_muted or payload.get("speak", False):
                    asyncio.create_task(vm.speak(full_reply))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

@app.get("/api/v1/voice/status")
def get_voice_status():
    """Estado actual del subsistema de voz (Mute/Unmute, config y palabras clave)."""
    return get_voice_manager().get_status()

@app.post("/api/v1/voice/toggle_mute")
def toggle_voice_mute():
    """Alterna el estado de silencio del micrófono de C.A.P.R.I."""
    vm = get_voice_manager()
    new_state = vm.toggle_mute()
    return {
        "status": "success",
        "is_muted": new_state,
        "message": "Micrófono silenciado [MUTED]." if new_state else "Micrófono activo [UNMUTED]. Escuchando 'Oye Capri'..."
    }

@app.post("/api/v1/voice/speak")
async def trigger_speech(payload: dict):
    """Sintetiza texto con la voz de Capri y lo reproduce en el sistema."""
    text = payload.get("text", "").strip()
    lang = payload.get("lang")
    if not text:
        raise HTTPException(status_code=400, detail="El campo 'text' es obligatorio.")
    vm = get_voice_manager()
    success = await vm.speak(text, lang=lang)
    return {"status": "success" if success else "error", "spoken": success}

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
