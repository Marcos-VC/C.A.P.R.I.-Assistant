from pydantic import BaseModel, Field
from typing import Optional

class SystemStatusResponse(BaseModel):
    status: str = Field(..., example="online")
    system: str = Field(..., example="C.A.P.R.I. Core Framework")
    version: str = Field(..., example="0.1.0")
    disk_available_gb: Optional[float] = Field(None, example=16.0)

class AssistantMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, example="Hola Capri, ¿cuál es tu estado?")
    context: Optional[dict] = Field(default_factory=dict)

class AssistantMessageResponse(BaseModel):
    response: str
    status: str = "success"
