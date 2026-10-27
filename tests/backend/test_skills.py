import pytest
from src.backend.skills.base import BaseSkill, SecurityLevel
from src.backend.skills.system_skills import SystemMonitorSkill
from src.backend.skills.registry import SkillRegistry

class DummyConfirmSkill(BaseSkill):
    name = "dummy_confirm"
    description = "Skill que requiere confirmación previa"
    security_level = SecurityLevel.CONFIRM_REQUIRED

    async def execute(self, **kwargs):
        return {"status": "success", "executed": True}

class DummyProhibitedSkill(BaseSkill):
    name = "dummy_prohibited"
    description = "Skill prohibida por directiva de seguridad"
    security_level = SecurityLevel.PROHIBITED

    async def execute(self, **kwargs):
        return {"status": "success", "executed": True}

@pytest.mark.anyio
async def test_system_monitor_skill_execution():
    skill = SystemMonitorSkill()
    res = await skill.execute()
    assert res["status"] == "success"
    assert "memory_info" in res
    assert "disk_info" in res
    assert "uptime_info" in res
    assert res["security_level"] == "safe"

@pytest.mark.anyio
async def test_skill_registry_security_levels():
    registry = SkillRegistry()
    registry.register(SystemMonitorSkill())
    registry.register(DummyConfirmSkill())
    registry.register(DummyProhibitedSkill())

    # 1. SAFE se ejecuta directamente
    safe_res = await registry.execute("system_monitor")
    assert safe_res["status"] == "success"

    # 2. CONFIRM_REQUIRED sin confirmación es retenida
    confirm_res = await registry.execute("dummy_confirm")
    assert confirm_res["status"] == "confirmation_required"

    # 3. CONFIRM_REQUIRED con confirmación se ejecuta
    confirmed_res = await registry.execute("dummy_confirm", confirmed=True)
    assert confirmed_res["status"] == "success"
    assert confirmed_res["executed"] is True

    # 4. PROHIBITED es bloqueada incondicionalmente
    prohibited_res = await registry.execute("dummy_prohibited", confirmed=True)
    assert prohibited_res["status"] == "blocked"

def test_gemini_tool_declaration():
    registry = SkillRegistry()
    registry.register(SystemMonitorSkill())
    tools = registry.get_gemini_tools()
    assert tools is not None
    assert len(tools.function_declarations) == 1
    assert tools.function_declarations[0].name == "system_monitor"

from unittest.mock import AsyncMock, MagicMock
from google.genai import types
from src.backend.core.llm import _call_gemini_model

@pytest.mark.anyio
async def test_call_gemini_model_function_calling_flow():
    mock_client = MagicMock()
    mock_aio = MagicMock()
    mock_models = MagicMock()
    mock_client.aio = mock_aio
    mock_aio.models = mock_models

    # Simular primera respuesta de Gemini pidiendo invocar 'system_monitor'
    mock_fc = MagicMock()
    mock_fc.name = "system_monitor"
    mock_fc.args = {}

    first_response = MagicMock()
    first_response.function_calls = [mock_fc]
    mock_candidate = MagicMock()
    mock_candidate.content = types.Content(
        role="model",
        parts=[types.Part.from_function_call(name="system_monitor", args={})]
    )
    first_response.candidates = [mock_candidate]
    first_response.text = None

    # Simular segunda respuesta final de Gemini tras recibir la telemetría
    second_response = MagicMock()
    second_response.function_calls = None
    second_response.text = "Telemetría recibida: Tienes 10GB de RAM libre."

    mock_models.generate_content = AsyncMock(side_effect=[first_response, second_response])

    contents = [types.Content(role="user", parts=[types.Part.from_text(text="¿Cómo está el sistema?")])]
    reply = await _call_gemini_model(mock_client, "gemini-3.5-flash-lite", contents)

    assert "Telemetría recibida" in reply
    assert mock_models.generate_content.call_count == 2


from src.backend.skills.system_skills import AudioControlSkill

def test_audio_control_gemini_declaration():
    skill = AudioControlSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "audio_control"
    assert "action" in decl.parameters.properties
    assert "level" in decl.parameters.properties

@pytest.mark.anyio
async def test_audio_control_get_volume():
    skill = AudioControlSkill()
    skill._run_command = AsyncMock(return_value=(0, "Volume: 0.65", ""))
    res = await skill.execute(action="get")
    assert res["status"] == "success"
    assert res["volume_percent"] == 65
    assert res["muted"] is False

@pytest.mark.anyio
async def test_audio_control_set_volume():
    skill = AudioControlSkill()
    skill._run_command = AsyncMock(return_value=(0, "", ""))
    res = await skill.execute(action="set", level=80)
    assert res["status"] == "success"
    assert res["volume_percent"] == 80
    assert "80%" in res["message"]

@pytest.mark.anyio
async def test_audio_control_mute_and_unmute():
    skill = AudioControlSkill()
    skill._run_command = AsyncMock(return_value=(0, "", ""))
    
    mute_res = await skill.execute(action="mute")
    assert mute_res["status"] == "success"
    assert mute_res["muted"] is True

    unmute_res = await skill.execute(action="unmute")
    assert unmute_res["status"] == "success"
    assert unmute_res["muted"] is False
