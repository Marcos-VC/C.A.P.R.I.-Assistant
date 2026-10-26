from fastapi import FastAPI
from src.backend.core.schemas import (
    SystemStatusResponse,
    AssistantMessageRequest,
    AssistantMessageResponse
)

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
    # Respuesta simulada por ahora mientras integramos los módulos de memoria y skills
    reply = f"C.A.P.R.I. ha recibido tu mensaje: '{payload.message}'"
    return AssistantMessageResponse(response=reply)
