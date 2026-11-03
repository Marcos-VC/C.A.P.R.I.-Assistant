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


from src.backend.skills.system_skills import AppLauncherSkill

def test_app_launcher_gemini_declaration():
    skill = AppLauncherSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "app_launcher"
    assert "app_name" in decl.parameters.properties

def test_app_launcher_find_desktop_file():
    skill = AppLauncherSkill()
    # Debe encontrar aplicaciones reales instaladas en el sistema (ej. terminal o calculator o snap firefox)
    match_term = skill._find_desktop_file("terminal")
    assert match_term is not None
    desktop_id, path = match_term
    assert "terminal" in desktop_id.lower() or "terminal" in path.lower()

    match_calc = skill._find_desktop_file("calculadora")
    assert match_calc is not None

@pytest.mark.anyio
async def test_app_launcher_missing_arg():
    skill = AppLauncherSkill()
    res = await skill.execute(app_name="")
    assert res["status"] == "error"

@pytest.mark.anyio
async def test_app_launcher_mocked_success():
    skill = AppLauncherSkill()
    skill._find_desktop_file = MagicMock(return_value=("org.gnome.Calculator", "/usr/share/applications/org.gnome.Calculator.desktop"))
    # Mock subprocess exec
    from unittest.mock import patch
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc
        res = await skill.execute(app_name="calculadora")
        assert res["status"] == "success"
        assert res["desktop_id"] == "org.gnome.Calculator"


from src.backend.skills.system_skills import PowerControlSkill

def test_power_control_gemini_declaration():
    skill = PowerControlSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "power_control"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_power_control_battery():
    skill = PowerControlSkill()
    # Test real execution on HP laptop or mocked fallback
    res = await skill.execute(action="battery")
    assert res["status"] == "success"
    assert res["action"] == "battery"
    assert "message" in res

@pytest.mark.anyio
async def test_power_control_brightness():
    skill = PowerControlSkill()
    res = await skill.execute(action="get_brightness")
    # In Linux laptop with intel_backlight, this should return success and integer
    assert res["status"] in ("success", "error")

    # Test set_brightness missing level
    bad_res = await skill.execute(action="set_brightness")
    assert bad_res["status"] == "error"

@pytest.mark.anyio
async def test_power_control_lock_mock():
    skill = PowerControlSkill()
    from unittest.mock import patch
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc
        res = await skill.execute(action="lock")
        assert res["status"] == "success"
        assert "bloqueada" in res["message"]


from src.backend.skills.system_skills import ProcessManagerSkill

def test_process_manager_gemini_declaration():
    skill = ProcessManagerSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "process_manager"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_process_manager_top_cpu_and_ram():
    skill = ProcessManagerSkill()
    cpu_res = await skill.execute(action="top_cpu")
    assert cpu_res["status"] == "success"
    assert "processes" in cpu_res

    ram_res = await skill.execute(action="top_ram")
    assert ram_res["status"] == "success"
    assert "processes" in ram_res

@pytest.mark.anyio
async def test_process_manager_find():
    skill = ProcessManagerSkill()
    # Find bash or python or something that is running
    res = await skill.execute(action="find", query="python")
    assert res["status"] == "success"

@pytest.mark.anyio
async def test_process_manager_kill_confirmation_and_blocks():
    skill = ProcessManagerSkill()
    # Critical PID 1 blocked
    blocked = await skill.execute(action="kill", pid=1, confirmed=True)
    assert blocked["status"] == "blocked"

    # Kill without confirmed flag requires confirmation
    unconfirmed = await skill.execute(action="kill", pid=99999, confirmed=False)
    assert unconfirmed["status"] == "confirmation_required"

@pytest.mark.anyio
async def test_process_manager_kill_mocked_success():
    skill = ProcessManagerSkill()
    from unittest.mock import patch
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_exec.return_value = mock_proc

        res = await skill.execute(action="kill", pid=12345, confirmed=True)
        assert res["status"] == "success"
        assert "finalizado" in res["message"]


from src.backend.skills.system_skills import TimerReminderSkill, WebLookupSkill

def test_timer_reminder_gemini_declaration():
    skill = TimerReminderSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "timer_reminder"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_timer_reminder_workflow():
    skill = TimerReminderSkill()

    # 1. Invalid duration
    err = await skill.execute(action="set_timer", minutes=0, seconds=0)
    assert err["status"] == "error"

    # 2. Create timer for 10 seconds (Pomodoro)
    set_res = await skill.execute(action="set_timer", seconds=10, label="Pausa café")
    assert set_res["status"] == "success"
    timer_id = set_res["timer_id"]
    assert "T-" in timer_id

    # 3. List active timers
    list_res = await skill.execute(action="list")
    assert list_res["status"] == "success"
    assert len(list_res["timers"]) >= 1

    # 4. Cancel timer
    cancel_res = await skill.execute(action="cancel", timer_id=timer_id)
    assert cancel_res["status"] == "success"

    # Cancel nonexistent
    cancel_err = await skill.execute(action="cancel", timer_id="T-99999")
    assert cancel_err["status"] == "error"


def test_web_lookup_gemini_declaration():
    skill = WebLookupSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "web_lookup"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_web_lookup_weather_mocked():
    skill = WebLookupSkill()
    from unittest.mock import patch

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"Despejado: +21C (sensacion +21C), humedad 40%, viento 10km/h"
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res = await skill.execute(action="weather", location="Madrid")
        assert res["status"] == "success"
        assert "Despejado" in res["report"]
        assert "Madrid" in res["message"]

@pytest.mark.anyio
async def test_web_lookup_search_mocked():
    skill = WebLookupSkill()
    from unittest.mock import patch
    import json

    mock_wiki = json.dumps({
        "title": "Python (lenguaje de programación)",
        "extract": "Python es un lenguaje de programación de alto nivel multiparadigma."
    }).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_wiki
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        res = await skill.execute(action="search", query="Python")
        assert res["status"] == "success"
        assert "multiparadigma" in res["summary"]




