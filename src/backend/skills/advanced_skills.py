import asyncio
import os
import re
import json
import shutil
import datetime
from typing import Dict, Any, Optional, List
from google.genai import types
from src.backend.skills.base import BaseSkill, SecurityLevel

# ──────────────────────────────────────────────────────────────────────────────
# 1. BASH EXECUTION SKILL
# ──────────────────────────────────────────────────────────────────────────────
class BashExecutionSkill(BaseSkill):
    """
    Motor de ejecución de terminal Bash en Ubuntu.
    Permite a C.A.P.R.I. ejecutar comandos de inspección, git, docker, consultas,
    compilación o scripts con verificación estricta de seguridad.
    """
    name = "bash_runner"
    description = (
        "Ejecuta comandos en la terminal Bash de Ubuntu para inspección de sistema, diagnósticos, "
        "git, docker, consultas de archivos, compilaciones o scripts de forma segura."
    )
    security_level = SecurityLevel.SAFE

    # Patrones estrictamente prohibidos (riesgo crítico de destrucción)
    PROHIBITED_PATTERNS = [
        r"\brm\s+-[a-zA-Z0-9]*[rfRF][a-zA-Z0-9]*\s+(?:/|\*|~|\$)",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r">\s*/dev/sd[a-z]",
        r">\s*/dev/nvme",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
        r"\bchmod\s+-[rR]\s+000\s+",
        r"\binit\s+0\b",
        r"\bshutdown\b",
        r"\breboot\b",
    ]

    # Prefijos de comandos seguros de inspección y lectura (SAFE)
    SAFE_PREFIXES = [
        "git", "ls", "grep", "cat", "head", "tail", "wc", "find", "du", "df", "ps", "top",
        "which", "whereis", "uname", "whoami", "hostname", "date", "uptime", "curl", "wget",
        "file", "stat", "awk", "sed", "echo", "diff", "tree", "dpkg", "apt-cache", "free",
        "lscpu", "lsusb", "lspci", "ip", "ifconfig", "ping", "netstat", "ss", "env", "printenv",
        "sort", "uniq", "cut", "tr", "tar -tf", "zipinfo", "md5sum", "sha256sum", "journalctl"
    ]

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "command": types.Schema(
                    type=types.Type.STRING,
                    description="Comando bash a ejecutar en el sistema (ej: 'git status', 'df -h', 'ls -la ~/Descargas', 'uptime')."
                ),
                "confirmed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Confirmación explícita para comandos de modificación o escritura."
                )
            },
            required=["command"]
        )

    def _is_prohibited(self, cmd: str) -> bool:
        for pattern in self.PROHIBITED_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def _is_safe(self, cmd: str) -> bool:
        cmd_clean = cmd.strip()
        # Verificar si comienza con algún prefijo seguro
        for prefix in self.SAFE_PREFIXES:
            if cmd_clean == prefix or cmd_clean.startswith(prefix + " ") or cmd_clean.startswith(prefix + "\t"):
                return True
        return False

    async def execute(self, **kwargs) -> Dict[str, Any]:
        command = kwargs.get("command", "").strip()
        confirmed = kwargs.get("confirmed", False)

        if not command:
            return {
                "status": "error",
                "message": "[SYSTEM ERROR]: No se proporcionó ningún comando para bash_runner.",
                "security_level": self.security_level.value
            }

        # 1. Comprobar comandos prohibidos
        if self._is_prohibited(command):
            return {
                "status": "blocked",
                "command": command,
                "message": f"[ICE BLOCKED]: Directiva rechazada. El comando contiene patrones prohibidos de alto riesgo.",
                "security_level": SecurityLevel.PROHIBITED.value
            }

        # 2. Comprobar si requiere confirmación
        if not self._is_safe(command) and not confirmed:
            return {
                "status": "confirmation_required",
                "command": command,
                "message": f"[AVISO TÁCTICO]: El comando '{command}' modifica el estado del sistema. Confirma con confirmed=True para ejecutar.",
                "security_level": SecurityLevel.CONFIRM_REQUIRED.value
            }

        # 3. Ejecutar comando en bash
        try:
            start_time = asyncio.get_event_loop().time()
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                executable="/bin/bash"
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "status": "error",
                    "command": command,
                    "message": f"[TIMEOUT]: El comando superó el límite de tiempo de 15 segundos y fue neutralizado.",
                    "security_level": self.security_level.value
                }

            elapsed = round(asyncio.get_event_loop().time() - start_time, 3)
            stdout = stdout_b.decode("utf-8", errors="replace").strip()
            stderr = stderr_b.decode("utf-8", errors="replace").strip()

            # Truncar salida si es masiva para no desbordar tokens
            max_chars = 3500
            if len(stdout) > max_chars:
                stdout = stdout[:max_chars] + f"\n... [Truncado a {max_chars} caracteres]"
            if len(stderr) > max_chars:
                stderr = stderr[:max_chars] + f"\n... [Truncado a {max_chars} caracteres]"

            output_summary = stdout if stdout else (stderr if stderr else "(Comando ejecutado sin salida en consola)")

            return {
                "status": "success" if proc.returncode == 0 else "error",
                "command": command,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "elapsed_seconds": elapsed,
                "message": f"Comando '{command}' finalizado (código {proc.returncode}, {elapsed}s):\n{output_summary}",
                "security_level": self.security_level.value
            }

        except Exception as e:
            return {
                "status": "error",
                "command": command,
                "message": f"[SYSTEM ERROR]: Fallo al ejecutar comando en bash -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 2. CLIPBOARD SKILL
# ──────────────────────────────────────────────────────────────────────────────
class ClipboardSkill(BaseSkill):
    """
    Habilidad para interactuar con el portapapeles del sistema Ubuntu.
    Soporta copiar texto o leer el contenido actual vía wl-clipboard, xclip o fallback.
    """
    name = "clipboard"
    description = (
        "Interactúa con el portapapeles de Ubuntu: 'copy' (copia texto al portapapeles), "
        "'paste' (lee el contenido actual copiado) o 'clear' (vacía el portapapeles)."
    )
    security_level = SecurityLevel.SAFE

    # Buffer de respaldo local en caso de ausencia de herramientas X11/Wayland
    _FALLBACK_FILE = os.path.expanduser("~/.local/share/capri/clipboard_fallback.txt")

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción a realizar en el portapapeles: 'copy', 'paste' o 'clear'.",
                    enum=["copy", "paste", "clear"]
                ),
                "text": types.Schema(
                    type=types.Type.STRING,
                    description="Texto a copiar en el portapapeles cuando action='copy'."
                )
            },
            required=["action"]
        )

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self._FALLBACK_FILE), exist_ok=True)

    async def _copy_text(self, text: str) -> bool:
        # 1. Intentar wl-copy (Wayland nativo)
        if shutil.which("wl-copy"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wl-copy",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate(input=text.encode("utf-8"))
                if proc.returncode == 0:
                    return True
            except Exception:
                pass

        # 2. Intentar xclip (X11 / XWayland)
        if shutil.which("xclip"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xclip", "-selection", "clipboard",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate(input=text.encode("utf-8"))
                if proc.returncode == 0:
                    return True
            except Exception:
                pass

        # 3. Fallback en archivo de sesión
        self._ensure_dir()
        with open(self._FALLBACK_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        return True

    async def _paste_text(self) -> str:
        # 1. Intentar wl-paste
        if shutil.which("wl-paste"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wl-paste", "--no-newline",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    return stdout.decode("utf-8", errors="replace")
            except Exception:
                pass

        # 2. Intentar xclip
        if shutil.which("xclip"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xclip", "-selection", "clipboard", "-o",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    return stdout.decode("utf-8", errors="replace")
            except Exception:
                pass

        # 3. Fallback en archivo
        if os.path.exists(self._FALLBACK_FILE):
            with open(self._FALLBACK_FILE, "r", encoding="utf-8") as f:
                return f.read()

        return ""

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "paste").lower().strip()
        text = kwargs.get("text", "")

        try:
            if action == "copy":
                if not text:
                    return {
                        "status": "error",
                        "message": "Debes especificar el parámetro 'text' para copiar al portapapeles.",
                        "security_level": self.security_level.value
                    }
                await self._copy_text(text)
                preview = text[:80] + "…" if len(text) > 80 else text
                return {
                    "status": "success",
                    "action": "copy",
                    "copied_chars": len(text),
                    "message": f"Contenido copiado al portapapeles con éxito ({len(text)} caracteres): '{preview}'",
                    "security_level": self.security_level.value
                }

            elif action == "paste":
                content = await self._paste_text()
                if not content:
                    return {
                        "status": "success",
                        "action": "paste",
                        "text": "",
                        "message": "El portapapeles está actualmente vacío.",
                        "security_level": self.security_level.value
                    }
                preview = content[:100] + "…" if len(content) > 100 else content
                return {
                    "status": "success",
                    "action": "paste",
                    "text": content,
                    "length": len(content),
                    "message": f"Contenido recuperado del portapapeles ({len(content)} caracteres):\n{content}",
                    "security_level": self.security_level.value
                }

            elif action == "clear":
                await self._copy_text("")
                return {
                    "status": "success",
                    "action": "clear",
                    "message": "Portapapeles vaciado correctamente.",
                    "security_level": self.security_level.value
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción '{action}' no válida. Usa 'copy', 'paste' o 'clear'.",
                    "security_level": self.security_level.value
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo en ClipboardSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 3. GIT ASSISTANT SKILL
# ──────────────────────────────────────────────────────────────────────────────
class GitAssistantSkill(BaseSkill):
    """
    Asistente táctico para repositorios Git en Ubuntu.
    Revisa estado, historial, ramas, diffs y crea commits de forma ágil.
    """
    name = "git_assistant"
    description = (
        "Operaciones y consultas en repositorios Git: estado ('status'), historial ('log'), "
        "ramas ('branch'), diferencias ('diff'), preparación de archivos ('add') y commits rápidos ('commit')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción de git: 'status', 'log', 'branch', 'diff', 'add' o 'commit'.",
                    enum=["status", "log", "branch", "diff", "add", "commit"]
                ),
                "repo_path": types.Schema(
                    type=types.Type.STRING,
                    description="Ruta al repositorio git local (por defecto el directorio actual del proyecto)."
                ),
                "message": types.Schema(
                    type=types.Type.STRING,
                    description="Mensaje del commit si action='commit'."
                ),
                "files": types.Schema(
                    type=types.Type.STRING,
                    description="Archivos específicos para git add o git diff (ej: '.' o 'src/backend/main.py')."
                )
            },
            required=["action"]
        )

    async def _run_git(self, args: List[str], cwd: str) -> Dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout_b, stderr_b = await proc.communicate()
        return {
            "code": proc.returncode,
            "stdout": stdout_b.decode("utf-8", errors="replace").strip(),
            "stderr": stderr_b.decode("utf-8", errors="replace").strip()
        }

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "status").lower().strip()
        repo_path = os.path.abspath(os.path.expanduser(kwargs.get("repo_path") or os.getcwd()))
        message = kwargs.get("message", "").strip()
        files = kwargs.get("files", ".").strip()

        if not shutil.which("git"):
            return {
                "status": "error",
                "message": "El ejecutable 'git' no se encuentra instalado en el sistema.",
                "security_level": self.security_level.value
            }

        if not os.path.exists(os.path.join(repo_path, ".git")):
            return {
                "status": "error",
                "message": f"La ruta '{repo_path}' no contiene un repositorio Git inicializado (.git no encontrado).",
                "security_level": self.security_level.value
            }

        try:
            if action == "status":
                res = await self._run_git(["status", "-s", "-b"], cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "status",
                    "repo_path": repo_path,
                    "output": res["stdout"] or res["stderr"],
                    "message": f"Estado de Git en {os.path.basename(repo_path)}:\n{res['stdout'] or 'Árbol de trabajo limpio (sin cambios).'}",
                    "security_level": self.security_level.value
                }

            elif action == "log":
                res = await self._run_git(["log", "-n", "6", "--pretty=format:%h - %an (%cr): %s"], cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "log",
                    "repo_path": repo_path,
                    "output": res["stdout"],
                    "message": f"Últimos commits en {os.path.basename(repo_path)}:\n{res['stdout'] or 'Sin historial de commits.'}",
                    "security_level": self.security_level.value
                }

            elif action == "branch":
                res = await self._run_git(["branch", "-a"], cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "branch",
                    "repo_path": repo_path,
                    "output": res["stdout"],
                    "message": f"Ramas en {os.path.basename(repo_path)}:\n{res['stdout']}",
                    "security_level": self.security_level.value
                }

            elif action == "diff":
                args = ["diff", "--stat"] if files == "." else ["diff", files]
                res = await self._run_git(args, cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "diff",
                    "repo_path": repo_path,
                    "output": res["stdout"] or "(No hay diferencias detectadas)",
                    "message": f"Diferencias en {os.path.basename(repo_path)}:\n{res['stdout'] or 'Sin diferencias en cambios no preparados.'}",
                    "security_level": self.security_level.value
                }

            elif action == "add":
                res = await self._run_git(["add", files], cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "add",
                    "repo_path": repo_path,
                    "message": f"Archivos ('{files}') añadidos al área de preparación (stage) en {os.path.basename(repo_path)}.",
                    "security_level": self.security_level.value
                }

            elif action == "commit":
                if not message:
                    return {
                        "status": "error",
                        "message": "Debes especificar un 'message' descriptivo para el commit.",
                        "security_level": self.security_level.value
                    }
                res = await self._run_git(["commit", "-m", message], cwd=repo_path)
                return {
                    "status": "success" if res["code"] == 0 else "error",
                    "action": "commit",
                    "repo_path": repo_path,
                    "output": res["stdout"] or res["stderr"],
                    "message": f"Commit generado en {os.path.basename(repo_path)}:\n{res['stdout'] or res['stderr']}",
                    "security_level": self.security_level.value
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción '{action}' no válida en git_assistant. Usa status, log, branch, diff, add o commit.",
                    "security_level": self.security_level.value
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo en GitAssistantSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 4. QUICK NOTES & SCRATCHPAD SKILL
# ──────────────────────────────────────────────────────────────────────────────
class QuickNotesSkill(BaseSkill):
    """
    Bloc de notas y tareas tácticas rápidas persistentes de C.A.P.R.I.
    Permite registrar ideas, tareas, recordatorios rápidos y organizarlos localmente.
    """
    name = "quick_notes"
    description = (
        "Bloc de notas y tareas persistente de C.A.P.R.I.: 'add' (guardar nota/tarea), "
        "'list' (ver notas), 'search' (buscar), 'done' (marcar completada), 'delete' (eliminar) o 'clear' (limpiar completadas)."
    )
    security_level = SecurityLevel.SAFE

    NOTES_FILE = os.path.expanduser("~/.local/share/capri/notes.json")

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción: 'add', 'list', 'search', 'done', 'delete' o 'clear'.",
                    enum=["add", "list", "search", "done", "delete", "clear"]
                ),
                "text": types.Schema(
                    type=types.Type.STRING,
                    description="Contenido de la nota o tarea a añadir o término a buscar."
                ),
                "note_id": types.Schema(
                    type=types.Type.INTEGER,
                    description="Identificador numérico de la nota a marcar como completada o eliminar."
                ),
                "category": types.Schema(
                    type=types.Type.STRING,
                    description="Etiqueta opcional de categoría (ej: 'tarea', 'idea', 'urgente', 'contacto')."
                )
            },
            required=["action"]
        )

    def _load_notes(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.NOTES_FILE):
            return []
        try:
            with open(self.NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_notes(self, notes: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(self.NOTES_FILE), exist_ok=True)
        with open(self.NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "list").lower().strip()
        text = kwargs.get("text", "").strip()
        note_id = kwargs.get("note_id")
        category = kwargs.get("category", "general").strip()

        notes = self._load_notes()

        try:
            if action == "add":
                if not text:
                    return {"status": "error", "message": "Debes especificar 'text' con el contenido de la nota."}

                next_id = max([n.get("id", 0) for n in notes], default=0) + 1
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                new_note = {
                    "id": next_id,
                    "text": text,
                    "category": category,
                    "status": "pending",
                    "created_at": now_str
                }
                notes.append(new_note)
                self._save_notes(notes)
                return {
                    "status": "success",
                    "action": "add",
                    "note": new_note,
                    "message": f"Nota #{next_id} guardada [{category}]: '{text}'",
                    "security_level": self.security_level.value
                }

            elif action == "list":
                if not notes:
                    return {
                        "status": "success",
                        "action": "list",
                        "count": 0,
                        "notes": [],
                        "message": "El bloc de notas táctico está vacío. Añade una con action='add'.",
                        "security_level": self.security_level.value
                    }

                lines = []
                for n in notes:
                    status_icon = "✓" if n.get("status") == "done" else " "
                    lines.append(f"[{status_icon}] #{n.get('id')} [{n.get('category', 'general')}]: {n.get('text')} ({n.get('created_at')})")

                return {
                    "status": "success",
                    "action": "list",
                    "count": len(notes),
                    "notes": notes,
                    "message": f"Notas registradas en C.A.P.R.I. ({len(notes)}):\n" + "\n".join(lines),
                    "security_level": self.security_level.value
                }

            elif action == "search":
                if not text:
                    return {"status": "error", "message": "Debes especificar 'text' para buscar en las notas."}

                matches = [n for n in notes if text.lower() in n.get("text", "").lower() or text.lower() in n.get("category", "").lower()]
                if not matches:
                    return {
                        "status": "success",
                        "action": "search",
                        "query": text,
                        "matches": [],
                        "message": f"No se encontró ninguna nota que coincida con '{text}'.",
                        "security_level": self.security_level.value
                    }

                lines = [f"#{n.get('id')} [{n.get('category')}]: {n.get('text')}" for n in matches]
                return {
                    "status": "success",
                    "action": "search",
                    "query": text,
                    "matches": matches,
                    "message": f"Coincidencias encontradas ({len(matches)}):\n" + "\n".join(lines),
                    "security_level": self.security_level.value
                }

            elif action == "done":
                if note_id is None:
                    return {"status": "error", "message": "Debes especificar 'note_id' para marcar como completada."}

                found = False
                for n in notes:
                    if n.get("id") == note_id:
                        n["status"] = "done"
                        found = True
                        break

                if not found:
                    return {"status": "error", "message": f"No se encontró ninguna nota con ID #{note_id}."}

                self._save_notes(notes)
                return {
                    "status": "success",
                    "action": "done",
                    "note_id": note_id,
                    "message": f"Nota #{note_id} marcada como completada [✓].",
                    "security_level": self.security_level.value
                }

            elif action == "delete":
                if note_id is None:
                    return {"status": "error", "message": "Debes especificar 'note_id' para eliminar."}

                new_notes = [n for n in notes if n.get("id") != note_id]
                if len(new_notes) == len(notes):
                    return {"status": "error", "message": f"No se encontró la nota con ID #{note_id}."}

                self._save_notes(new_notes)
                return {
                    "status": "success",
                    "action": "delete",
                    "note_id": note_id,
                    "message": f"Nota #{note_id} eliminada permanentemente.",
                    "security_level": self.security_level.value
                }

            elif action == "clear":
                remaining = [n for n in notes if n.get("status") != "done"]
                cleared_count = len(notes) - len(remaining)
                self._save_notes(remaining)
                return {
                    "status": "success",
                    "action": "clear",
                    "cleared_count": cleared_count,
                    "message": f"Se eliminaron {cleared_count} notas completadas del bloc.",
                    "security_level": self.security_level.value
                }

            else:
                return {"status": "error", "message": f"Acción '{action}' no válida en quick_notes."}

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en QuickNotesSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 5. PACKAGE MANAGER SKILL
# ──────────────────────────────────────────────────────────────────────────────
class PackageManagerSkill(BaseSkill):
    """
    Consultas de paquetes y software del sistema Ubuntu APT.
    Permite buscar paquetes, verificar si están instalados y comprobar actualizaciones.
    """
    name = "package_manager"
    description = (
        "Consulta paquetes del sistema APT en Ubuntu: buscar paquetes ('search'), verificar si están "
        "instalados ('check'), detalles técnicos ('info') o comprobar actualizaciones disponibles ('updates')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción: 'search' (buscar), 'check' (ver si está instalado), 'info' (detalles) o 'updates' (actualizaciones pendientes).",
                    enum=["search", "check", "info", "updates"]
                ),
                "package_name": types.Schema(
                    type=types.Type.STRING,
                    description="Nombre del paquete a consultar o término de búsqueda (ej: 'ffmpeg', 'git', 'docker', 'neovim')."
                )
            },
            required=["action"]
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "check").lower().strip()
        package_name = kwargs.get("package_name", "").strip()

        try:
            if action == "search":
                if not package_name:
                    return {"status": "error", "message": "Debes especificar 'package_name' para buscar en APT."}

                proc = await asyncio.create_subprocess_exec(
                    "apt-cache", "search", package_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_b, _ = await proc.communicate()
                lines = stdout_b.decode("utf-8", errors="replace").strip().split("\n")
                filtered = [l.strip() for l in lines if l.strip()][:10]

                if not filtered:
                    return {
                        "status": "success",
                        "action": "search",
                        "query": package_name,
                        "results": [],
                        "message": f"No se encontraron paquetes para '{package_name}' en los repositorios de APT.",
                        "security_level": self.security_level.value
                    }

                return {
                    "status": "success",
                    "action": "search",
                    "query": package_name,
                    "results": filtered,
                    "message": f"Paquetes encontrados en APT para '{package_name}' (primeros 10):\n" + "\n".join(filtered),
                    "security_level": self.security_level.value
                }

            elif action == "check":
                if not package_name:
                    return {"status": "error", "message": "Debes especificar 'package_name' a verificar."}

                # 1. Comprobar si existe como binario ejecutable
                which_path = shutil.which(package_name)

                # 2. Comprobar estado con dpkg
                proc = await asyncio.create_subprocess_exec(
                    "dpkg", "-s", package_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_b, _ = await proc.communicate()
                dpkg_out = stdout_b.decode("utf-8", errors="replace")
                is_installed = "Status: install ok installed" in dpkg_out or (which_path is not None)

                version = "Desconocida"
                for line in dpkg_out.split("\n"):
                    if line.startswith("Version:"):
                        version = line.split(":", 1)[1].strip()
                        break

                if is_installed:
                    msg = f"✓ El paquete/herramienta '{package_name}' está instalado en el sistema."
                    if which_path:
                        msg += f"\n  ↳ Binario: {which_path}"
                    if version != "Desconocida":
                        msg += f"\n  ↳ Versión: {version}"
                else:
                    msg = f"✗ El paquete '{package_name}' no está instalado en el sistema."

                return {
                    "status": "success",
                    "action": "check",
                    "package_name": package_name,
                    "is_installed": is_installed,
                    "binary_path": which_path,
                    "version": version if is_installed else None,
                    "message": msg,
                    "security_level": self.security_level.value
                }

            elif action == "info":
                if not package_name:
                    return {"status": "error", "message": "Debes especificar 'package_name' para ver sus detalles."}

                proc = await asyncio.create_subprocess_exec(
                    "apt-cache", "show", package_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_b, _ = await proc.communicate()
                raw_info = stdout_b.decode("utf-8", errors="replace").strip()
                if not raw_info:
                    return {
                        "status": "error",
                        "message": f"No se encontró información técnica para el paquete '{package_name}'.",
                        "security_level": self.security_level.value
                    }

                # Extraer campos clave
                info_lines = []
                for line in raw_info.split("\n"):
                    if any(line.startswith(k) for k in ["Package:", "Version:", "Section:", "Installed-Size:", "Description:"]):
                        info_lines.append(line)

                return {
                    "status": "success",
                    "action": "info",
                    "package_name": package_name,
                    "details": "\n".join(info_lines[:8]),
                    "message": f"Ficha técnica de '{package_name}':\n" + "\n".join(info_lines[:8]),
                    "security_level": self.security_level.value
                }

            elif action == "updates":
                proc = await asyncio.create_subprocess_shell(
                    "apt list --upgradable 2>/dev/null",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    executable="/bin/bash"
                )
                stdout_b, _ = await proc.communicate()
                lines = [l.strip() for l in stdout_b.decode("utf-8", errors="replace").split("\n") if "/" in l]

                count = len(lines)
                if count == 0:
                    msg = "El sistema está completamente actualizado. No hay paquetes pendientes de upgrade."
                else:
                    preview = "\n".join(lines[:8])
                    msg = f"Hay {count} paquete(s) con actualizaciones disponibles:\n{preview}"
                    if count > 8:
                        msg += f"\n... y {count - 8} más."

                return {
                    "status": "success",
                    "action": "updates",
                    "upgradable_count": count,
                    "packages": lines[:12],
                    "message": msg,
                    "security_level": self.security_level.value
                }

            else:
                return {"status": "error", "message": f"Acción '{action}' no válida en package_manager."}

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo en PackageManagerSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 6. SCREENSHOT SKILL
# ──────────────────────────────────────────────────────────────────────────────
class ScreenshotSkill(BaseSkill):
    """
    Captura de pantalla en Ubuntu Linux.
    Guarda la captura en ~/Pictures/Screenshots o ~/Imágenes y devuelve ruta y tamaño.
    """
    name = "screenshot"
    description = (
        "Realiza capturas de pantalla del escritorio de Ubuntu y las guarda automáticamente "
        "en la carpeta de imágenes del usuario ('~/Pictures/Screenshots')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "delay_seconds": types.Schema(
                    type=types.Type.INTEGER,
                    description="Segundos opcionales de espera antes de capturar la pantalla (por defecto 0)."
                ),
                "filename": types.Schema(
                    type=types.Type.STRING,
                    description="Nombre de archivo personalizado para la imagen (por defecto con marca de tiempo)."
                )
            },
            required=[]
        )

    def _get_target_dir(self) -> str:
        candidates = [
            os.path.expanduser("~/Pictures/Screenshots"),
            os.path.expanduser("~/Imágenes/Capturas de pantalla"),
            os.path.expanduser("~/Pictures"),
            os.path.expanduser("~/Imágenes"),
            os.path.expanduser("~")
        ]
        for c in candidates:
            if os.path.isdir(c):
                return c
        target = os.path.expanduser("~/Pictures/Screenshots")
        os.makedirs(target, exist_ok=True)
        return target

    async def execute(self, **kwargs) -> Dict[str, Any]:
        delay = int(kwargs.get("delay_seconds") or 0)
        filename = kwargs.get("filename")

        if delay > 0:
            await asyncio.sleep(delay)

        target_dir = self._get_target_dir()
        if not filename:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capri_screenshot_{ts}.png"
        elif not filename.endswith(".png"):
            filename += ".png"

        target_path = os.path.join(target_dir, filename)

        try:
            captured = False

            # 1. Probar GNOME Shell Screenshot DBus
            if shutil.which("gdbus"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "gdbus", "call", "--session",
                        "--dest", "org.gnome.Shell.Screenshot",
                        "--object-path", "/org/gnome/Shell/Screenshot",
                        "--method", "org.gnome.Shell.Screenshot.Screenshot",
                        "true", "false", target_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                        captured = True
                except Exception:
                    pass

            # 2. Probar ImageMagick import
            if not captured and shutil.which("import"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "import", "-window", "root", target_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                        captured = True
                except Exception:
                    pass

            # 3. Probar gnome-screenshot
            if not captured and shutil.which("gnome-screenshot"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "gnome-screenshot", "-f", target_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                        captured = True
                except Exception:
                    pass

            # 4. Probar scrot o grim
            for tool in ["scrot", "grim"]:
                if not captured and shutil.which(tool):
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            tool, target_path,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await proc.communicate()
                        if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                            captured = True
                            break
                    except Exception:
                        pass

            if captured and os.path.exists(target_path):
                sz = os.path.getsize(target_path)
                sz_kb = max(0.1, round(sz / 1024, 1))
                return {
                    "status": "success",
                    "filepath": target_path,
                    "filename": filename,
                    "size_kb": sz_kb,
                    "message": f"Captura óptica Kiroshi guardada con éxito:\n  ↳ Archivo: {target_path} ({sz_kb} KB)",
                    "security_level": self.security_level.value
                }
            else:
                return {
                    "status": "error",
                    "message": "No se pudo realizar la captura. Comprueba permisos de pantalla o instala gnome-screenshot / imagemagick.",
                    "security_level": self.security_level.value
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo en ScreenshotSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


# ──────────────────────────────────────────────────────────────────────────────
# 7. MEDIA CONTROL SKILL (MPRIS / playerctl)
# ──────────────────────────────────────────────────────────────────────────────
class MediaControlSkill(BaseSkill):
    """
    Control de reproducción multimedia activa en Ubuntu (Spotify, navegadores, VLC, etc.).
    Soporta consultar qué está sonando, pausar, reproducir, avanzar o retroceder pista.
    """
    name = "media_control"
    description = (
        "Controla la reproducción multimedia activa en Ubuntu (Spotify, navegadores, VLC, etc.): "
        "ver qué está sonando ('status'), pausar/reanudar ('play_pause'), siguiente pista ('next'), pista anterior ('previous') y detener ('stop')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción multimedia: 'status', 'play_pause', 'next', 'previous' o 'stop'.",
                    enum=["status", "play_pause", "next", "previous", "stop"]
                )
            },
            required=["action"]
        )

    async def _execute_playerctl(self, action: str) -> Optional[Dict[str, Any]]:
        if not shutil.which("playerctl"):
            return None

        if action == "status":
            proc_stat = await asyncio.create_subprocess_exec(
                "playerctl", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_s, _ = await proc_stat.communicate()
            status_text = stdout_s.decode("utf-8", errors="replace").strip()

            proc_meta = await asyncio.create_subprocess_exec(
                "playerctl", "metadata", "--format", "{{ artist }} - {{ title }} [{{ album }}]",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_m, _ = await proc_meta.communicate()
            meta_text = stdout_m.decode("utf-8", errors="replace").strip()

            if not status_text and not meta_text:
                return {
                    "status": "success",
                    "action": "status",
                    "is_playing": False,
                    "message": "No se detectó ningún reproductor multimedia activo en este momento."
                }

            return {
                "status": "success",
                "action": "status",
                "playback_status": status_text,
                "track_info": meta_text,
                "message": f"Estado multimedia: [{status_text}]\n  ↳ Pista: {meta_text or 'Sin metadatos'}"
            }

        cmd_map = {
            "play_pause": ["play-pause"],
            "next": ["next"],
            "previous": ["previous"],
            "stop": ["stop"]
        }
        subcmd = cmd_map.get(action)
        if subcmd:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", *subcmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return {
                "status": "success",
                "action": action,
                "message": f"Directiva multimedia '{action}' enviada a los reproductores activos."
            }
        return None

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "status").lower().strip()

        try:
            # 1. Intentar con playerctl
            res = await self._execute_playerctl(action)
            if res:
                res["security_level"] = self.security_level.value
                return res

            # 2. Si no hay playerctl, intentar vía gdbus MPRIS
            if shutil.which("gdbus"):
                # Buscar reproductores registrados en DBus
                list_proc = await asyncio.create_subprocess_exec(
                    "gdbus", "call", "--session",
                    "--dest", "org.freedesktop.DBus",
                    "--object-path", "/org/freedesktop/DBus",
                    "--method", "org.freedesktop.DBus.ListNames",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_b, _ = await list_proc.communicate()
                names_raw = stdout_b.decode("utf-8", errors="replace")
                mpris_players = [w.strip("' ") for w in re.findall(r"'org\.mpris\.MediaPlayer2\.[^']+'", names_raw)]

                if not mpris_players:
                    return {
                        "status": "success",
                        "action": action,
                        "message": "No se detectó ningún reproductor multimedia activo (DBus/MPRIS).",
                        "security_level": self.security_level.value
                    }

                target_dest = mpris_players[0]
                action_methods = {
                    "play_pause": "PlayPause",
                    "next": "Next",
                    "previous": "Previous",
                    "stop": "Stop"
                }

                if action in action_methods:
                    method_name = action_methods[action]
                    call_proc = await asyncio.create_subprocess_exec(
                        "gdbus", "call", "--session",
                        "--dest", target_dest,
                        "--object-path", "/org/mpris/MediaPlayer2",
                        "--method", f"org.mpris.MediaPlayer2.Player.{method_name}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await call_proc.communicate()
                    return {
                        "status": "success",
                        "action": action,
                        "player": target_dest,
                        "message": f"Comando '{action}' ejecutado en {target_dest.split('.')[-1]}.",
                        "security_level": self.security_level.value
                    }
                elif action == "status":
                    return {
                        "status": "success",
                        "action": "status",
                        "active_players": mpris_players,
                        "message": f"Reproductores multimedia detectados: {', '.join(p.split('.')[-1] for p in mpris_players)}",
                        "security_level": self.security_level.value
                    }

            return {
                "status": "error",
                "message": "No se pudo comunicar con el subsistema multimedia. Instala 'playerctl' para control total.",
                "security_level": self.security_level.value
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo en MediaControlSkill -> {str(e)}",
                "security_level": self.security_level.value
            }
