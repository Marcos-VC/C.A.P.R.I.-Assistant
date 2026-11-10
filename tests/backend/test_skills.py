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


@pytest.mark.anyio
async def test_call_gemini_model_multiple_simultaneous_function_calls():
    mock_client = MagicMock()
    mock_aio = MagicMock()
    mock_models = MagicMock()
    mock_client.aio = mock_aio
    mock_aio.models = mock_models

    fc1 = MagicMock()
    fc1.name = "system_monitor"
    fc1.args = {}

    fc2 = MagicMock()
    fc2.name = "clipboard"
    fc2.args = {"action": "paste"}

    first_resp = MagicMock()
    first_resp.function_calls = [fc1, fc2]
    mock_candidate = MagicMock()
    mock_candidate.content = types.Content(
        role="model",
        parts=[
            types.Part.from_function_call(name="system_monitor", args={}),
            types.Part.from_function_call(name="clipboard", args={"action": "paste"})
        ]
    )
    first_resp.candidates = [mock_candidate]
    first_resp.text = None

    second_resp = MagicMock()
    second_resp.function_calls = None
    second_resp.text = "Sistema y portapapeles procesados simultáneamente con éxito."

    mock_models.generate_content = AsyncMock(side_effect=[first_resp, second_resp])
    contents = [types.Content(role="user", parts=[types.Part.from_text(text="Dime la RAM y el portapapeles")])]

    reply = await _call_gemini_model(mock_client, "gemini-3.5-flash-lite", contents)
    assert reply == "Sistema y portapapeles procesados simultáneamente con éxito."
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


from src.backend.skills.system_skills import NetworkInfoSkill, FileManagerSkill
from src.backend.core.llm import SYSTEM_PROMPT

def test_cyberpunk_persona_prompt():
    # Verificar que el prompt contenga los términos clave solicitados por el usuario
    assert "choom" in SYSTEM_PROMPT.lower()
    assert "nova" in SYSTEM_PROMPT.lower()
    assert "preem" in SYSTEM_PROMPT.lower()
    assert "kiroshi" in SYSTEM_PROMPT.lower()
    assert "flatline" in SYSTEM_PROMPT.lower()
    assert "ciberpsicosis" in SYSTEM_PROMPT.lower()
    assert "ciberware" in SYSTEM_PROMPT.lower() or "chrome" in SYSTEM_PROMPT.lower()

def test_network_info_gemini_declaration():
    skill = NetworkInfoSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "network_info"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_network_info_execution():
    skill = NetworkInfoSkill()
    # 1. IP
    ip_res = await skill.execute(action="ip")
    assert ip_res["status"] in ("success", "error")

    # 2. Ping real o fallback
    from unittest.mock import patch
    with patch.object(skill, "_socket_ping", return_value=15.4):
        ping_res = await skill.execute(action="ping", host="1.1.1.1")
        assert ping_res["status"] == "success"
        assert "latency_ms" in ping_res or "raw" in ping_res

    # 3. Wi-Fi
    wifi_res = await skill.execute(action="wifi")
    assert wifi_res["status"] in ("success", "error")

@pytest.mark.anyio
async def test_network_info_ping_socket_fallback():
    skill = NetworkInfoSkill()
    from unittest.mock import patch
    with patch("shutil.which", return_value=None):
        with patch.object(skill, "_socket_ping", return_value=15.4):
            ping_res = await skill.execute(action="ping", host="1.1.1.1")
            assert ping_res["status"] == "success"
            assert ping_res.get("latency_ms") == 15.4


def test_file_manager_gemini_declaration():
    skill = FileManagerSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "file_manager"
    assert "action" in decl.parameters.properties

@pytest.mark.anyio
async def test_file_manager_list():
    skill = FileManagerSkill()
    # List current workspace
    res = await skill.execute(action="list", folder=".")
    assert res["status"] == "success"
    assert "items" in res
    assert len(res["items"]) > 0

@pytest.mark.anyio
async def test_file_manager_search():
    skill = FileManagerSkill()
    # Search for pytest.ini
    res = await skill.execute(action="search", folder=".", query="pytest.ini")
    assert res["status"] == "success"
    assert len(res["matches"]) >= 1

@pytest.mark.anyio
async def test_file_manager_recent():
    skill = FileManagerSkill()
    res = await skill.execute(action="recent", folder=".")
    assert res["status"] == "success"
    assert "recent_files" in res


# ──────────────────────────────────────────────────────────────────────────────
# TESTS: NUEVAS HABILIDADES AVANZADAS (v0.9 REAL POWER)
# ──────────────────────────────────────────────────────────────────────────────
from src.backend.skills.advanced_skills import (
    BashExecutionSkill,
    ClipboardSkill,
    GitAssistantSkill,
    QuickNotesSkill,
    PackageManagerSkill,
    ScreenshotSkill,
    MediaControlSkill,
)
from src.backend.skills.registry import get_skill_registry

def test_registry_contains_all_16_skills():
    registry = get_skill_registry()
    all_skills = registry.list_skills()
    assert len(all_skills) >= 16
    names = [s.name for s in all_skills]
    expected = [
        "system_monitor", "audio_control", "app_launcher", "power_control",
        "process_manager", "timer_reminder", "web_lookup", "network_info",
        "file_manager", "bash_runner", "clipboard", "git_assistant",
        "quick_notes", "package_manager", "screenshot", "media_control"
    ]
    for exp in expected:
        assert exp in names, f"La skill '{exp}' debe estar registrada"


# 1. BASH RUNNER
def test_bash_runner_declaration():
    skill = BashExecutionSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "bash_runner"
    assert "command" in decl.parameters.properties


@pytest.mark.anyio
async def test_bash_runner_safe_command():
    skill = BashExecutionSkill()
    res = await skill.execute(command="echo 'preem edgerunner'")
    assert res["status"] == "success"
    assert "preem edgerunner" in res["stdout"]
    assert res["returncode"] == 0


@pytest.mark.anyio
async def test_bash_runner_prohibited():
    skill = BashExecutionSkill()
    res = await skill.execute(command="rm -rf /")
    assert res["status"] == "blocked"
    assert res["security_level"] == "prohibited"


@pytest.mark.anyio
async def test_bash_runner_unconfirmed():
    skill = BashExecutionSkill()
    res = await skill.execute(command="systemctl restart dummy_service", confirmed=False)
    assert res["status"] == "confirmation_required"


# 2. CLIPBOARD
def test_clipboard_declaration():
    skill = ClipboardSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "clipboard"
    assert "action" in decl.parameters.properties


@pytest.mark.anyio
async def test_clipboard_copy_and_paste(tmp_path):
    skill = ClipboardSkill()
    skill._FALLBACK_FILE = str(tmp_path / "clip.txt")
    from unittest.mock import patch
    # Forzar fallback para reproducibilidad en CI/headless
    with patch("shutil.which", return_value=None):
        copy_res = await skill.execute(action="copy", text="Night City 2077")
        assert copy_res["status"] == "success"

        paste_res = await skill.execute(action="paste")
        assert paste_res["status"] == "success"
        assert paste_res["text"] == "Night City 2077"

        clear_res = await skill.execute(action="clear")
        assert clear_res["status"] == "success"

        paste_res2 = await skill.execute(action="paste")
        assert paste_res2["text"] == ""


# 3. GIT ASSISTANT
def test_git_assistant_declaration():
    skill = GitAssistantSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "git_assistant"
    assert "action" in decl.parameters.properties


@pytest.mark.anyio
async def test_git_assistant_status_and_log():
    skill = GitAssistantSkill()
    status_res = await skill.execute(action="status")
    assert status_res["status"] == "success"
    assert "output" in status_res

    log_res = await skill.execute(action="log")
    assert log_res["status"] == "success"
    assert "output" in log_res

    branch_res = await skill.execute(action="branch")
    assert branch_res["status"] == "success"
    assert "main" in branch_res["output"]


# 4. QUICK NOTES
def test_quick_notes_declaration():
    skill = QuickNotesSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "quick_notes"


@pytest.mark.anyio
async def test_quick_notes_lifecycle(tmp_path):
    skill = QuickNotesSkill()
    skill.NOTES_FILE = str(tmp_path / "notes.json")

    # Add
    add_res = await skill.execute(action="add", text="Comprar cromo Kiroshi", category="tarea")
    assert add_res["status"] == "success"
    note_id = add_res["note"]["id"]

    # List
    list_res = await skill.execute(action="list")
    assert list_res["status"] == "success"
    assert list_res["count"] == 1

    # Search
    search_res = await skill.execute(action="search", text="Kiroshi")
    assert search_res["status"] == "success"
    assert len(search_res["matches"]) == 1

    # Mark done
    done_res = await skill.execute(action="done", note_id=note_id)
    assert done_res["status"] == "success"

    # Clear completed
    clear_res = await skill.execute(action="clear")
    assert clear_res["status"] == "success"
    assert clear_res["cleared_count"] == 1

    list_res2 = await skill.execute(action="list")
    assert list_res2["count"] == 0


# 5. PACKAGE MANAGER
def test_package_manager_declaration():
    skill = PackageManagerSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "package_manager"


@pytest.mark.anyio
async def test_package_manager_check_installed():
    skill = PackageManagerSkill()
    # git está instalado
    res_git = await skill.execute(action="check", package_name="git")
    assert res_git["status"] == "success"
    assert res_git["is_installed"] is True

    # paquete ficticio
    res_fake = await skill.execute(action="check", package_name="paquete_inexistente_cyberpunk_xyz")
    assert res_fake["status"] == "success"
    assert res_fake["is_installed"] is False


@pytest.mark.anyio
async def test_package_manager_search():
    skill = PackageManagerSkill()
    res = await skill.execute(action="search", package_name="python3")
    assert res["status"] == "success"
    assert len(res["results"]) > 0


# 6. SCREENSHOT
def test_screenshot_declaration():
    skill = ScreenshotSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "screenshot"


@pytest.mark.anyio
async def test_screenshot_execution_mocked(tmp_path):
    skill = ScreenshotSkill()
    from unittest.mock import patch, AsyncMock
    fake_img = tmp_path / "test_shot.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")

    with patch.object(skill, "_get_target_dir", return_value=str(tmp_path)):
        with patch("shutil.which", side_effect=lambda bin: "/usr/bin/" + bin if bin == "gdbus" else None):
            with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate.return_value = (b"", b"")
                mock_exec.return_value = mock_proc

                res = await skill.execute(filename="test_shot.png")
                assert res["status"] == "success"
                assert "test_shot.png" in res["filepath"]
                assert res["size_kb"] > 0


# 7. MEDIA CONTROL
def test_media_control_declaration():
    skill = MediaControlSkill()
    decl = skill.to_gemini_declaration()
    assert decl.name == "media_control"


@pytest.mark.anyio
async def test_media_control_status_fallback():
    skill = MediaControlSkill()
    res = await skill.execute(action="status")
    assert res["status"] in ("success", "error")
    assert "message" in res






