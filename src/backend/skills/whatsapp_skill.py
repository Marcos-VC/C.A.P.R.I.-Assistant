"""
WhatsApp Skill para C.A.P.R.I. — Arquitectura Privacy-First.

PRIVACIDAD (NO NEGOCIABLE):
- Los números de teléfono NUNCA salen de este proceso local.
- El LLM solo conoce alias de contactos, JAMÁS números.
- El fichero de contactos vive en ~/.local/share/capri/contacts.json (fuera del repo).
- La acción 'send' requiere confirmación explícita del Operador (CONFIRM_REQUIRED).
- La función de envío usa xdg-open con URL scheme de WhatsApp Web (sin tokens, sin API).
"""

import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime
from typing import Any, Dict, Optional
from google.genai import types

from src.backend.skills.base import BaseSkill, SecurityLevel

# ── Rutas de almacenamiento local (fuera del repositorio git) ──────────────────
CAPRI_DATA_DIR = os.path.expanduser("~/.local/share/capri")
CONTACTS_FILE = os.path.join(CAPRI_DATA_DIR, "contacts.json")
INBOX_FILE = os.path.join(CAPRI_DATA_DIR, "whatsapp_inbox.json")
MAX_INBOX = 50  # máximo de notificaciones guardadas en bandeja


def _ensure_data_dir() -> None:
    """Crea el directorio de datos de Capri si no existe."""
    os.makedirs(CAPRI_DATA_DIR, exist_ok=True)


def _load_contacts() -> Dict[str, str]:
    """Carga el diccionario alias→teléfono desde el fichero local."""
    _ensure_data_dir()
    if not os.path.exists(CONTACTS_FILE):
        return {}
    try:
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_contacts(contacts: Dict[str, str]) -> None:
    """Persiste el diccionario alias→teléfono en el fichero local."""
    _ensure_data_dir()
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)


def _load_inbox() -> list:
    """Carga la bandeja de notificaciones WhatsApp interceptadas."""
    _ensure_data_dir()
    if not os.path.exists(INBOX_FILE):
        return []
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _validate_phone(phone: str) -> bool:
    """
    Valida formato básico de teléfono internacional.
    Debe empezar con '+' seguido solo de dígitos (mínimo 7, máximo 15).
    """
    return bool(re.match(r"^\+\d{7,15}$", phone.strip()))


class WhatsAppSkill(BaseSkill):
    """
    Skill de mensajería WhatsApp para C.A.P.R.I.

    Acciones disponibles:
    - send:            Abrir WhatsApp Web con mensaje pre-relleno (CONFIRM_REQUIRED)
    - contacts_add:    Guardar un nuevo contacto alias→teléfono localmente
    - contacts_list:   Listar alias guardados (NUNCA expone números)
    - contacts_remove: Eliminar un contacto por alias
    - inbox:           Ver últimos mensajes recibidos (notificaciones interceptadas)
    """

    name = "whatsapp"
    description = (
        "Gestión de mensajería WhatsApp: enviar mensajes, gestionar contactos locales "
        "y leer la bandeja de mensajes recibidos. "
        "PRIVACIDAD: los números de teléfono NUNCA se exponen al LLM."
    )
    # El nivel CONFIRM_REQUIRED aplica al skill globalmente; la lógica interna
    # permite ejecutar acciones de lectura sin confirmación adicional.
    security_level = SecurityLevel.CONFIRM_REQUIRED

    def to_gemini_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=(
                "Skill de WhatsApp. Acciones: "
                "'send' (enviar mensaje a un contacto guardado por alias), "
                "'contacts_add' (guardar nuevo contacto con alias), "
                "'contacts_list' (listar alias de contactos guardados), "
                "'contacts_remove' (eliminar contacto por alias), "
                "'inbox' (ver últimos mensajes recibidos de WhatsApp). "
                "IMPORTANTE: nunca uses ni muestres números de teléfono, solo alias."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Acción a ejecutar: 'send', 'contacts_add', "
                            "'contacts_list', 'contacts_remove', 'inbox'."
                        ),
                        enum=["send", "contacts_add", "contacts_list", "contacts_remove", "inbox"],
                    ),
                    "alias": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Alias del contacto (nombre amigable). "
                            "Requerido para 'send', 'contacts_add', 'contacts_remove'."
                        ),
                    ),
                    "phone": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Número de teléfono en formato internacional (ej: +34612345678). "
                            "Solo requerido en 'contacts_add'. NUNCA lo expongas en respuestas."
                        ),
                    ),
                    "message": types.Schema(
                        type=types.Type.STRING,
                        description="Texto del mensaje a enviar. Requerido para la acción 'send'.",
                    ),
                    "limit": types.Schema(
                        type=types.Type.INTEGER,
                        description=(
                            "Número máximo de mensajes a devolver en la acción 'inbox'. "
                            "Por defecto 10."
                        ),
                    ),
                },
                required=["action"],
            ),
        )

    # ── Métodos de acción ──────────────────────────────────────────────────────

    async def _action_send(self, alias: Optional[str], message: Optional[str]) -> Dict[str, Any]:
        """Resuelve alias→teléfono localmente y abre WhatsApp Web con el mensaje pre-relleno."""
        if not alias or not alias.strip():
            return {"status": "error", "message": "Se requiere el alias del contacto para enviar un mensaje."}
        if not message or not message.strip():
            return {"status": "error", "message": "Se requiere el texto del mensaje."}

        contacts = _load_contacts()
        alias_lower = alias.strip().lower()

        # Búsqueda insensible a mayúsculas
        phone = None
        for key, val in contacts.items():
            if key.lower() == alias_lower:
                phone = val
                break

        if phone is None:
            alias_list = list(contacts.keys()) if contacts else []
            hint = f" Contactos guardados: {alias_list}" if alias_list else " No hay contactos guardados aún."
            return {
                "status": "error",
                "message": f"Contacto '{alias}' no encontrado en la agenda local.{hint}",
            }

        # Construir URL de WhatsApp Web con mensaje codificado
        encoded_msg = urllib.parse.quote(message.strip())
        url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"

        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Vista previa del mensaje (máx 60 chars) para confirmación sin exponer teléfono
            preview = message[:60] + ("..." if len(message) > 60 else "")
            return {
                "status": "success",
                "action": "send",
                "to": alias,
                "message_preview": preview,
                "info": (
                    f"WhatsApp Web abierto en el navegador para '{alias}'. "
                    "El mensaje está pre-relleno. Solo tienes que pulsar Enviar."
                ),
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": "No se encontró 'xdg-open'. ¿Estás en un entorno de escritorio Linux?",
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error al abrir WhatsApp Web: {exc}"}

    async def _action_contacts_add(self, alias: Optional[str], phone: Optional[str]) -> Dict[str, Any]:
        """Guarda un nuevo contacto alias→teléfono en la agenda local."""
        if not alias or not alias.strip():
            return {"status": "error", "message": "Se requiere el alias del contacto."}
        if not phone or not phone.strip():
            return {"status": "error", "message": "Se requiere el número de teléfono en formato internacional (+34...)."}

        phone = phone.strip()
        if not _validate_phone(phone):
            return {
                "status": "error",
                "message": (
                    f"Formato de teléfono inválido: '{phone}'. "
                    "Usa formato internacional: +34612345678"
                ),
            }

        contacts = _load_contacts()
        alias_key = alias.strip().lower()
        existed = alias_key in contacts
        contacts[alias_key] = phone
        _save_contacts(contacts)

        action_word = "actualizado" if existed else "guardado"
        return {
            "status": "success",
            "action": "contacts_add",
            "alias": alias_key,
            "message": f"Contacto '{alias_key}' {action_word} en la agenda local. ✓",
        }

    async def _action_contacts_list(self) -> Dict[str, Any]:
        """Lista solo los alias de los contactos guardados (NUNCA expone teléfonos)."""
        contacts = _load_contacts()
        aliases = sorted(contacts.keys())
        if not aliases:
            return {
                "status": "success",
                "action": "contacts_list",
                "aliases": [],
                "count": 0,
                "message": "No hay contactos guardados en la agenda local de C.A.P.R.I. aún.",
            }
        return {
            "status": "success",
            "action": "contacts_list",
            "aliases": aliases,
            "count": len(aliases),
        }

    async def _action_contacts_remove(self, alias: Optional[str]) -> Dict[str, Any]:
        """Elimina un contacto de la agenda local por su alias."""
        if not alias or not alias.strip():
            return {"status": "error", "message": "Se requiere el alias del contacto a eliminar."}

        contacts = _load_contacts()
        alias_key = alias.strip().lower()

        if alias_key not in contacts:
            return {
                "status": "error",
                "message": f"El contacto '{alias_key}' no existe en la agenda local.",
            }

        del contacts[alias_key]
        _save_contacts(contacts)
        return {
            "status": "success",
            "action": "contacts_remove",
            "alias": alias_key,
            "message": f"Contacto '{alias_key}' eliminado de la agenda local. ✓",
        }

    async def _action_inbox(self, limit: Optional[int] = 10) -> Dict[str, Any]:
        """Devuelve los últimos N mensajes de WhatsApp interceptados vía DBus."""
        try:
            limit = int(limit) if limit else 10
            limit = max(1, min(limit, MAX_INBOX))
        except (ValueError, TypeError):
            limit = 10

        inbox = _load_inbox()
        recent = inbox[-limit:] if len(inbox) > limit else inbox
        # Ordenar más reciente primero
        recent = list(reversed(recent))

        if not recent:
            return {
                "status": "success",
                "action": "inbox",
                "messages": [],
                "count": 0,
                "message": (
                    "Bandeja de WhatsApp vacía. "
                    "Las notificaciones de WhatsApp Web se capturan automáticamente cuando llegan."
                ),
            }

        return {
            "status": "success",
            "action": "inbox",
            "messages": recent,
            "count": len(recent),
            "total_stored": len(inbox),
        }

    # ── Punto de entrada principal ─────────────────────────────────────────────

    async def execute(self, action: str = "inbox", **kwargs) -> Dict[str, Any]:
        """
        Despacha la acción solicitada al método interno correspondiente.
        Las acciones de lectura (inbox, contacts_list) no requieren confirmación adicional.
        """
        action = (action or "inbox").strip().lower()

        # Acciones de solo lectura — siempre disponibles
        if action == "inbox":
            return await self._action_inbox(limit=kwargs.get("limit"))
        if action == "contacts_list":
            return await self._action_contacts_list()

        # Acciones de escritura/modificación
        if action == "contacts_add":
            return await self._action_contacts_add(
                alias=kwargs.get("alias"),
                phone=kwargs.get("phone"),
            )
        if action == "contacts_remove":
            return await self._action_contacts_remove(alias=kwargs.get("alias"))

        # Acción de envío (requiere resolución local de alias→teléfono)
        if action == "send":
            return await self._action_send(
                alias=kwargs.get("alias"),
                message=kwargs.get("message"),
            )

        return {
            "status": "error",
            "message": (
                f"Acción desconocida: '{action}'. "
                "Acciones válidas: send, contacts_add, contacts_list, contacts_remove, inbox."
            ),
        }
