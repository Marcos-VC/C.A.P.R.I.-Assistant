"""
Tests del WhatsApp Skill de C.A.P.R.I.
Verifican funcionalidad de contactos, envío (mocked), bandeja e integración con el registro.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

# ── Importaciones del proyecto ─────────────────────────────────────────────────
from src.backend.skills.whatsapp_skill import (
    WhatsAppSkill,
    _load_contacts,
    _save_contacts,
    _load_inbox,
    _validate_phone,
    CONTACTS_FILE,
    INBOX_FILE,
)
from src.backend.skills.whatsapp_dbus_watcher import (
    start_notification_watcher,
    _is_whatsapp_notification,
    _DbusNotificationParser,
)
from src.backend.skills.registry import get_skill_registry
from src.backend.skills.base import SecurityLevel


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def skill(tmp_path, monkeypatch):
    """Instancia del skill con rutas de ficheros redirigidas a tmp_path."""
    contacts_path = str(tmp_path / "contacts.json")
    inbox_path = str(tmp_path / "whatsapp_inbox.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.INBOX_FILE", inbox_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))
    return WhatsAppSkill(), contacts_path, inbox_path


# ── Tests de declaración Gemini ────────────────────────────────────────────────

def test_whatsapp_declaration():
    """La declaración Gemini tiene nombre, descripción y parámetros correctos."""
    sk = WhatsAppSkill()
    decl = sk.to_gemini_declaration()
    assert decl.name == "whatsapp"
    assert "action" in decl.description.lower() or "action" in str(decl.parameters)
    # Verificar que 'action' está en los parámetros required
    required = decl.parameters.required
    assert "action" in required


def test_whatsapp_security_level():
    """El skill tiene nivel CONFIRM_REQUIRED."""
    sk = WhatsAppSkill()
    assert sk.security_level == SecurityLevel.CONFIRM_REQUIRED


# ── Tests de validación de teléfono ───────────────────────────────────────────

@pytest.mark.parametrize("phone,expected", [
    ("+34612345678", True),
    ("+1234567890", True),
    ("+447911123456", True),
    ("34612345678", False),   # sin +
    ("+34abc12345", False),   # letras
    ("+1", False),            # demasiado corto
    ("", False),              # vacío
    ("+12345678901234567", False),  # demasiado largo
])
def test_validate_phone(phone, expected):
    assert _validate_phone(phone) == expected


# ── Tests de gestión de contactos ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_contacts_add_and_list(tmp_path, monkeypatch):
    """Añadir un contacto y listarlo (solo alias, sin número)."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()

    # Añadir
    result = await sk.execute(action="contacts_add", alias="David", phone="+34612345678")
    assert result["status"] == "success"
    assert "david" in result["alias"]

    # Listar — verificar que el número NO aparece
    result_list = await sk.execute(action="contacts_list")
    assert result_list["status"] == "success"
    assert "david" in result_list["aliases"]
    assert result_list["count"] == 1
    # El número NUNCA debe aparecer en la respuesta
    assert "+34612345678" not in str(result_list)


@pytest.mark.anyio
async def test_contacts_add_invalid_phone(tmp_path, monkeypatch):
    """Añadir con teléfono inválido devuelve error."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="contacts_add", alias="Alguien", phone="600123456")
    assert result["status"] == "error"
    assert "formato" in result["message"].lower() or "inválido" in result["message"].lower()


@pytest.mark.anyio
async def test_contacts_remove(tmp_path, monkeypatch):
    """Añadir y eliminar un contacto."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    await sk.execute(action="contacts_add", alias="Mama", phone="+34600000001")
    result = await sk.execute(action="contacts_remove", alias="Mama")
    assert result["status"] == "success"
    assert "mama" in result["alias"]

    # Verificar que ya no existe
    contacts_data = json.loads(open(contacts_path).read())
    assert "mama" not in contacts_data


@pytest.mark.anyio
async def test_contacts_remove_nonexistent(tmp_path, monkeypatch):
    """Eliminar un contacto que no existe devuelve error."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="contacts_remove", alias="Fantasma")
    assert result["status"] == "error"


@pytest.mark.anyio
async def test_contacts_list_empty(tmp_path, monkeypatch):
    """Listar contactos vacíos devuelve lista vacía."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="contacts_list")
    assert result["status"] == "success"
    assert result["aliases"] == []
    assert result["count"] == 0


@pytest.mark.anyio
async def test_contacts_add_multiple_case_insensitive(tmp_path, monkeypatch):
    """Los alias se guardan en minúsculas; se pueden listar independientemente del case."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    await sk.execute(action="contacts_add", alias="PAPA", phone="+34611111111")
    await sk.execute(action="contacts_add", alias="Novia", phone="+34622222222")
    result = await sk.execute(action="contacts_list")
    assert "papa" in result["aliases"]
    assert "novia" in result["aliases"]
    assert result["count"] == 2


# ── Tests de envío ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_send_mocked(tmp_path, monkeypatch):
    """
    Enviar mensaje a contacto existente: verifica que xdg-open se llama con la URL correcta
    y que el número de teléfono NO aparece en la respuesta devuelta al LLM.
    """
    contacts_path = str(tmp_path / "contacts.json")
    inbox_path = str(tmp_path / "whatsapp_inbox.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.INBOX_FILE", inbox_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()

    # Guardar contacto de prueba
    _save_contacts.__module__  # just to reference import
    with open(contacts_path, "w") as f:
        json.dump({"david": "+34699887766"}, f)

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        result = await sk.execute(action="send", alias="David", message="Hola tío, ¿quedamos?")

    assert result["status"] == "success"
    assert result["to"] == "David"
    # El número de teléfono NUNCA debe aparecer en la respuesta
    assert "+34699887766" not in str(result)
    # Verificar que xdg-open fue llamado con la URL correcta
    call_args = mock_popen.call_args[0][0]
    assert "xdg-open" in call_args
    assert "web.whatsapp.com/send" in call_args[1]
    assert "+34699887766" in call_args[1]  # El número SÍ va en la URL (local), no en la respuesta
    assert "Hola" in call_args[1]


@pytest.mark.anyio
async def test_send_unknown_contact(tmp_path, monkeypatch):
    """Enviar a contacto desconocido devuelve error descriptivo."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="send", alias="Desconocido", message="Hola")
    assert result["status"] == "error"
    assert "desconocido" in result["message"].lower() or "no encontrado" in result["message"].lower()


@pytest.mark.anyio
async def test_send_missing_alias(tmp_path, monkeypatch):
    """Enviar sin alias devuelve error."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="send", message="Texto sin destinatario")
    assert result["status"] == "error"


@pytest.mark.anyio
async def test_send_missing_message(tmp_path, monkeypatch):
    """Enviar sin mensaje devuelve error."""
    contacts_path = str(tmp_path / "contacts.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CONTACTS_FILE", contacts_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    # Crear contacto
    with open(contacts_path, "w") as f:
        json.dump({"juan": "+34611111111"}, f)

    result = await sk.execute(action="send", alias="Juan")
    assert result["status"] == "error"


# ── Tests de bandeja (inbox) ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_inbox_empty(tmp_path, monkeypatch):
    """Bandeja vacía devuelve lista vacía correctamente."""
    inbox_path = str(tmp_path / "whatsapp_inbox.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.INBOX_FILE", inbox_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    sk = WhatsAppSkill()
    result = await sk.execute(action="inbox")
    assert result["status"] == "success"
    assert result["messages"] == []
    assert result["count"] == 0


@pytest.mark.anyio
async def test_inbox_with_data(tmp_path, monkeypatch):
    """Bandeja con datos devuelve los mensajes más recientes primero."""
    inbox_path = str(tmp_path / "whatsapp_inbox.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.INBOX_FILE", inbox_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    # Crear bandeja de prueba
    test_inbox = [
        {"sender": "Ana", "message": "Hola", "timestamp": "2024-01-01T10:00:00"},
        {"sender": "Luis", "message": "¿Vienes?", "timestamp": "2024-01-01T10:05:00"},
        {"sender": "Ana", "message": "Espera", "timestamp": "2024-01-01T10:10:00"},
    ]
    with open(inbox_path, "w") as f:
        json.dump(test_inbox, f)

    sk = WhatsAppSkill()
    result = await sk.execute(action="inbox", limit=2)
    assert result["status"] == "success"
    assert result["count"] == 2
    # El más reciente debe estar primero
    assert result["messages"][0]["sender"] == "Ana"
    assert result["messages"][0]["message"] == "Espera"


@pytest.mark.anyio
async def test_inbox_limit_default(tmp_path, monkeypatch):
    """La bandeja usa límite por defecto de 10."""
    inbox_path = str(tmp_path / "whatsapp_inbox.json")
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.INBOX_FILE", inbox_path)
    monkeypatch.setattr("src.backend.skills.whatsapp_skill.CAPRI_DATA_DIR", str(tmp_path))

    # Crear 15 mensajes de prueba
    test_inbox = [
        {"sender": f"User{i}", "message": f"Msg {i}", "timestamp": f"2024-01-01T10:{i:02d}:00"}
        for i in range(15)
    ]
    with open(inbox_path, "w") as f:
        json.dump(test_inbox, f)

    sk = WhatsAppSkill()
    result = await sk.execute(action="inbox")
    assert result["count"] == 10
    assert result["total_stored"] == 15


# ── Tests de acción inválida ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_unknown_action():
    """Acción desconocida devuelve error."""
    sk = WhatsAppSkill()
    result = await sk.execute(action="hackear_matriz")
    assert result["status"] == "error"
    assert "desconocida" in result["message"].lower() or "válidas" in result["message"].lower()


# ── Tests del watcher DBus ────────────────────────────────────────────────────

def test_is_whatsapp_notification():
    """Detecta correctamente notificaciones de WhatsApp Web."""
    assert _is_whatsapp_notification("WhatsApp Web") is True
    assert _is_whatsapp_notification("web.whatsapp.com") is True
    assert _is_whatsapp_notification("WHATSAPP") is True
    assert _is_whatsapp_notification("Telegram") is False
    assert _is_whatsapp_notification("") is False
    assert _is_whatsapp_notification("wapp_notifier") is True


def test_watcher_import():
    """El watcher importa sin errores (no lanza excepciones al importar)."""
    from src.backend.skills.whatsapp_dbus_watcher import start_notification_watcher
    assert callable(start_notification_watcher)


def test_dbus_parser_whatsapp_notification():
    """El parser detecta una notificación de WhatsApp correctamente."""
    parser = _DbusNotificationParser()

    lines = [
        "   method call time=12345.678 sender=:1.23 -> destination=org.freedesktop.Notifications serial=42 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify\n",
        '   string "WhatsApp Web"\n',
        "   uint32 0\n",
        '   string ""\n',
        '   string "David García"\n',
        '   string "Hola, ¿quedamos a las 8?"\n',
        "   array [\n",
        "   ]\n",
        "   array [\n",
        "   ]\n",
        "   int32 5000\n",
    ]

    result = None
    for line in lines[:-1]:
        result = parser.feed(line)

    # Forzar el flush al final
    final = parser.flush()
    if final:
        result = final

    assert result is not None
    assert result["sender"] == "David García"
    assert "quedamos" in result["message"]
    assert "timestamp" in result


def test_dbus_parser_non_whatsapp():
    """El parser ignora notificaciones que no son de WhatsApp."""
    parser = _DbusNotificationParser()

    lines = [
        "   method call time=12345.678 sender=:1.23 -> destination=org.freedesktop.Notifications serial=42 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify\n",
        '   string "GNOME Terminal"\n',
        "   uint32 0\n",
        '   string ""\n',
        '   string "Job finished"\n',
        '   string "Process completed successfully."\n',
    ]

    result = None
    for line in lines:
        result = parser.feed(line)

    final = parser.flush()
    # No debe devolver nada para Telegram/Terminal
    assert result is None
    assert final is None


def test_start_notification_watcher_runs():
    """
    El watcher se inicia como hilo demonio sin lanzar excepciones.
    dbus-monitor puede no estar disponible en CI, pero el hilo debe arrancar.
    """
    import threading
    with patch("subprocess.Popen") as mock_popen:
        # Simular que dbus-monitor no produce output y termina
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_popen.return_value = mock_proc

        t = start_notification_watcher()
        assert isinstance(t, threading.Thread)
        assert t.daemon is True


# ── Tests de integración con el registro ──────────────────────────────────────

def test_registry_has_whatsapp():
    """
    El skill 'whatsapp' está registrado en el registro central de C.A.P.R.I.
    (Resetea el singleton para incluir WhatsApp si ya se instanció antes.)
    """
    import src.backend.skills.registry as reg_module
    # Reset del singleton para test limpio
    reg_module._default_registry = None
    registry = get_skill_registry()
    skill = registry.get("whatsapp")
    assert skill is not None
    assert skill.name == "whatsapp"
    assert isinstance(skill, WhatsAppSkill)


def test_registry_skill_count_includes_whatsapp():
    """El registro tiene al menos 17 skills (16 anteriores + WhatsApp)."""
    import src.backend.skills.registry as reg_module
    reg_module._default_registry = None
    registry = get_skill_registry()
    skills = registry.list_skills()
    assert len(skills) >= 17


def test_whatsapp_in_gemini_tools():
    """El skill WhatsApp aparece en las tools generadas para Gemini."""
    import src.backend.skills.registry as reg_module
    reg_module._default_registry = None
    registry = get_skill_registry()
    tools = registry.get_gemini_tools()
    assert tools is not None
    names = [d.name for d in tools.function_declarations]
    assert "whatsapp" in names
