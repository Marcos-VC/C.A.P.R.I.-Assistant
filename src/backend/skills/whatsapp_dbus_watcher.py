"""
Interceptor de notificaciones DBus para WhatsApp Web — C.A.P.R.I.

Monitoriza el bus de sesión de GNOME para capturar notificaciones entrantes
de WhatsApp Web (org.freedesktop.Notifications) y las guarda en la bandeja
local (~/.local/share/capri/whatsapp_inbox.json).

PRIVACIDAD: solo se guardan remitente y fragmento de mensaje tal como
llegan en la notificación del escritorio. No se accede a WhatsApp Web
ni a ningún servidor externo.
"""

import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime

logger = logging.getLogger("capri.whatsapp.watcher")

# ── Rutas de almacenamiento ────────────────────────────────────────────────────
CAPRI_DATA_DIR = os.path.expanduser("~/.local/share/capri")
INBOX_FILE = os.path.join(CAPRI_DATA_DIR, "whatsapp_inbox.json")
MAX_INBOX = 50  # Máximo de notificaciones en memoria

# Palabras clave que identifican notificaciones de WhatsApp Web
WHATSAPP_KEYWORDS = ("whatsapp", "web.whatsapp.com", "wapp")


def _ensure_data_dir() -> None:
    """Crea el directorio de datos de Capri si no existe."""
    os.makedirs(CAPRI_DATA_DIR, exist_ok=True)


def _load_inbox() -> list:
    """Carga la bandeja actual desde disco."""
    _ensure_data_dir()
    if not os.path.exists(INBOX_FILE):
        return []
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_to_inbox(entry: dict) -> None:
    """Añade una nueva entrada a la bandeja, respetando el límite MAX_INBOX."""
    _ensure_data_dir()
    inbox = _load_inbox()
    inbox.append(entry)
    # Mantener solo los últimos MAX_INBOX mensajes
    if len(inbox) > MAX_INBOX:
        inbox = inbox[-MAX_INBOX:]
    try:
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(inbox, f, indent=2, ensure_ascii=False)
        logger.debug("Notificación WhatsApp guardada en bandeja: %s", entry.get("sender", "?"))
    except OSError as exc:
        logger.warning("No se pudo guardar en bandeja WhatsApp: %s", exc)


def _is_whatsapp_notification(app_name: str) -> bool:
    """Detecta si el nombre de la aplicación corresponde a WhatsApp Web."""
    app_lower = (app_name or "").lower()
    return any(kw in app_lower for kw in WHATSAPP_KEYWORDS)


def _extract_string_values(block: list[str]) -> list[str]:
    """
    Extrae los valores de las líneas con formato 'string "..."' de dbus-monitor.
    Maneja valores multi-línea básicos.
    """
    values = []
    for line in block:
        # Buscar líneas del tipo:   string "valor"
        match = re.match(r'\s*string\s+"(.*)"', line)
        if match:
            values.append(match.group(1))
    return values


class _DbusNotificationParser:
    """
    Máquina de estados que procesa la salida de dbus-monitor línea a línea
    y extrae notificaciones completas del método Notify.

    Formato esperado de dbus-monitor para una llamada Notify:
        method call time=... sender=... -> destination=... serial=... path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify
           string "app_name"       ← índice 0
           uint32 N                ← replaces_id (ignorar)
           string "app_icon"       ← índice 1
           string "summary"        ← índice 2  → remitente
           string "body"           ← índice 3  → texto del mensaje
           ... (hints, etc.)
    """

    def __init__(self):
        self._in_notify = False
        self._buffer: list[str] = []

    def feed(self, line: str) -> dict | None:
        """
        Alimenta una línea de dbus-monitor al parser.
        Devuelve un dict con la notificación si está completa, None en caso contrario.
        """
        stripped = line.strip()

        # Detectar inicio de llamada Notify
        if "member=Notify" in stripped and "interface=org.freedesktop.Notifications" in stripped:
            self._in_notify = True
            self._buffer = []
            return None

        if not self._in_notify:
            return None

        # Fin de bloque: nueva llamada de método o señal
        if stripped.startswith("method call") or stripped.startswith("method return") or stripped.startswith("signal "):
            result = self._try_parse()
            self._in_notify = False
            self._buffer = []
            # Puede que el nuevo bloque también sea Notify
            if "member=Notify" in stripped and "interface=org.freedesktop.Notifications" in stripped:
                self._in_notify = True
            return result

        self._buffer.append(line)
        return None

    def _try_parse(self) -> dict | None:
        """Intenta extraer los campos de la notificación del buffer acumulado."""
        strings = _extract_string_values(self._buffer)
        # Necesitamos al menos: app_name, app_icon, summary, body → 4 strings
        if len(strings) < 4:
            return None

        app_name = strings[0]
        # summary = strings[2], body = strings[3]
        summary = strings[2]
        body = strings[3]

        if not _is_whatsapp_notification(app_name):
            return None

        return {
            "sender": summary,
            "message": body,
            "app": app_name,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def flush(self) -> dict | None:
        """Intenta parsear el buffer restante al final del stream."""
        if self._in_notify and self._buffer:
            return self._try_parse()
        return None


def _watch_loop() -> None:
    """
    Bucle principal del watcher: lanza dbus-monitor y procesa su salida en tiempo real.
    Se reinicia automáticamente si dbus-monitor termina de forma inesperada.
    """
    parser = _DbusNotificationParser()
    logger.info("Iniciando watcher de notificaciones DBus para WhatsApp Web...")

    try:
        proc = subprocess.Popen(
            [
                "dbus-monitor",
                "--session",
                "interface='org.freedesktop.Notifications',member='Notify'",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            notification = parser.feed(line)
            if notification:
                logger.info(
                    "WhatsApp recibido de '%s': %s",
                    notification.get("sender", "?"),
                    notification.get("message", "")[:40],
                )
                _save_to_inbox(notification)

        # Stream cerrado — intentar parsear buffer final
        final = parser.flush()
        if final:
            _save_to_inbox(final)

    except FileNotFoundError:
        logger.warning(
            "dbus-monitor no encontrado. El watcher de WhatsApp no estará activo. "
            "Instálalo con: sudo apt install dbus"
        )
    except Exception as exc:
        logger.error("Error en el watcher de notificaciones DBus: %s", exc)


def start_notification_watcher() -> threading.Thread:
    """
    Inicia el watcher de notificaciones en un hilo demonio en segundo plano.
    Llama a esta función UNA sola vez en el arranque del backend de C.A.P.R.I.

    Returns:
        El hilo demonio en ejecución.
    """
    t = threading.Thread(target=_watch_loop, name="capri-whatsapp-watcher", daemon=True)
    t.start()
    logger.info("Hilo watcher WhatsApp iniciado (daemon=True).")
    return t
