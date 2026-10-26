from fastapi import FastAPI, HTTPException
from src.backend.core.schemas import (
    SystemStatusResponse,
    AssistantMessageRequest,
    AssistantMessageResponse,
    SkillExecuteRequest,
    SkillExecuteResponse
)
from src.backend.memory.repository import save_message, get_recent_history
from src.backend.skills.system_skills import SystemMonitorSkill

app = FastAPI(
    title="C.A.P.R.I. Assistant API",
    version="0.1.0",
    description="Cybernetic Autonomously Programmed Response Interface - Backend API"
)

# Registro de habilidades disponibles
AVAILABLE_SKILLS = {
    SystemMonitorSkill.name: SystemMonitorSkill()
}

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
    save_message(session_id=payload.session_id, role="user", content=payload.message)
    history = get_recent_history(session_id=payload.session_id, limit=10)
    
    reply = f"C.A.P.R.I. [Sesion {payload.session_id}]: Recibido -> '{payload.message}'. Memoria activa: {len(history)} mensajes."
    save_message(session_id=payload.session_id, role="assistant", content=reply)
    
    return AssistantMessageResponse(
        session_id=payload.session_id,
        response=reply,
        history_count=len(history) + 1
    )

@app.post("/api/v1/skills/execute", response_model=SkillExecuteResponse)
def execute_skill(payload: SkillExecuteRequest):
    skill = AVAILABLE_SKILLS.get(payload.skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Habilidad '{payload.skill_name}' no encontrada.")
    
    result = skill.execute(**payload.params)
    return SkillExecuteResponse(
        skill_name=payload.skill_name,
        result=result
    )
