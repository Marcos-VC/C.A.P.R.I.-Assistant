from fastapi import FastAPI
from src.backend.core.schemas import (
    SystemStatusResponse,
    AssistantMessageRequest,
    AssistantMessageResponse
)
from src.backend.memory.repository import save_message, get_recent_history

app = FastAPI(
    title="C.A.P.R.I. Assistant API",
    version="0.1.0",
    description="Cybernetic Autonomously Programmed Response Interface - Backend API"
)

@app.get("/", response_model=SystemStatusResponse)
def read_root():
    return SystemStatusResponse(
        status="online",
        system="C.A.P.R.I. Core Framework",
        version="0.1.0"
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "backend"}

@app.post("/api/v1/chat", response_model=AssistantMessageResponse)
def process_message(payload: AssistantMessageRequest):
    # 1. Guardar mensaje entrante del usuario
    save_message(session_id=payload.session_id, role="user", content=payload.message)
    
    # 2. Obtener historial reciente de la sesion
    history = get_recent_history(session_id=payload.session_id, limit=10)
    
    # 3. Generar respuesta con formato de comillas correcto
    reply = f"C.A.P.R.I. [Sesion {payload.session_id}]: Recibido -> '{payload.message}'. Memoria activa: {len(history)} mensajes."
    
    # 4. Guardar la respuesta del asistente
    save_message(session_id=payload.session_id, role="assistant", content=reply)
    
    return AssistantMessageResponse(
        session_id=payload.session_id,
        response=reply,
        history_count=len(history) + 1
    )
