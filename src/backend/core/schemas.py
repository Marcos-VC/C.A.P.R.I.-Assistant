from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SystemStatusResponse(BaseModel):
    status: str = Field(..., example="online")
    system: str = Field(..., example="C.A.P.R.I. Core Framework")
    version: str = Field(..., example="0.1.0")
    disk_available_gb: Optional[float] = Field(None, example=16.0)

class AssistantMessageRequest(BaseModel):
    session_id: str = Field(default="default_session", example="session_123")
    message: str = Field(..., min_length=1, example="Hola Capri, ¿cuál es tu estado?")
    context: Optional[dict] = Field(default_factory=dict)

class AssistantMessageResponse(BaseModel):
    session_id: str
    response: str
    history_count: int
    status: str = "success"

class SkillExecuteRequest(BaseModel):
    skill_name: str = Field(..., example="system_monitor")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class SkillExecuteResponse(BaseModel):
    skill_name: str
    result: Dict[str, Any]
    status: str = "success"
