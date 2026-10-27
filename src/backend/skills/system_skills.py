import asyncio
from typing import Dict, Any
from google.genai import types
from src.backend.skills.base import BaseSkill, SecurityLevel

class SystemMonitorSkill(BaseSkill):
    """
    Habilidad para monitorizar el estado del sistema en Ubuntu (RAM, Disco y Carga).
    Nivel de seguridad: SAFE (Solo lectura, ejecución no bloqueante).
    """
    name = "system_monitor"
    description = "Obtiene información técnica en tiempo real del sistema Ubuntu: memoria RAM disponible, espacio en disco y carga de CPU."
    security_level = SecurityLevel.SAFE

    async def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            # 1. Obtener uso de memoria RAM
            mem_proc = await asyncio.create_subprocess_exec(
                "free", "-h",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            mem_stdout, mem_stderr = await mem_proc.communicate()
            if mem_proc.returncode != 0:
                raise RuntimeError(f"Fallo al consultar memoria: {mem_stderr.decode().strip()}")

            # 2. Obtener uso de disco raíz
            disk_proc = await asyncio.create_subprocess_exec(
                "df", "-h", "/",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            disk_stdout, disk_stderr = await disk_proc.communicate()
            if disk_proc.returncode != 0:
                raise RuntimeError(f"Fallo al consultar disco: {disk_stderr.decode().strip()}")

            # 3. Obtener uptime y carga media del sistema
            uptime_proc = await asyncio.create_subprocess_exec(
                "uptime",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            uptime_stdout, uptime_stderr = await uptime_proc.communicate()
            uptime_str = uptime_stdout.decode().strip() if uptime_proc.returncode == 0 else "No disponible"

            return {
                "status": "success",
                "memory_info": mem_stdout.decode().strip(),
                "disk_info": disk_stdout.decode().strip(),
                "uptime_info": uptime_str,
                "security_level": self.security_level.value
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en la telemetría del sistema -> {str(e)}",
                "security_level": self.security_level.value
            }


class AudioControlSkill(BaseSkill):
    """
    Habilidad táctica para gestionar el audio en Ubuntu (PipeWire / PulseAudio).
    Permite consultar volumen, ajustarlo (0-100%) y silenciar o activar el sonido.
    Nivel de seguridad: SAFE.
    """
    name = "audio_control"
    description = (
        "Controla el volumen y estado de silenciamiento del sistema de sonido en Ubuntu. "
        "Permite consultar el nivel actual ('get'), establecer un nuevo volumen de 0 a 100% ('set'), "
        "silenciar el audio ('mute') o reactivarlo ('unmute')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción a realizar: 'get' para consultar volumen, 'set' para ajustarlo, 'mute' para silenciar, 'unmute' para reactivar sonido, 'toggle_mute' para alternar.",
                    enum=["get", "set", "mute", "unmute", "toggle_mute"]
                ),
                "level": types.Schema(
                    type=types.Type.INTEGER,
                    description="Nivel de volumen en porcentaje del 0 al 100 (requerido solo para action='set')."
                )
            },
            required=["action"]
        )

    async def _run_command(self, *args) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "get").lower()
        level = kwargs.get("level")

        try:
            # 1. CONSULTAR VOLUMEN
            if action == "get":
                code, out, err = await self._run_command("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
                if code == 0:
                    is_muted = "[MUTED]" in out
                    clean = out.replace("[MUTED]", "").replace("Volume:", "").strip()
                    try:
                        vol_percent = int(float(clean) * 100)
                    except ValueError:
                        vol_percent = clean
                    return {
                        "status": "success",
                        "action": "get",
                        "volume_percent": vol_percent,
                        "muted": is_muted,
                        "security_level": self.security_level.value
                    }
                # Fallback con pactl
                code, out, err = await self._run_command("pactl", "get-sink-volume", "@DEFAULT_SINK@")
                if code == 0:
                    return {
                        "status": "success",
                        "action": "get",
                        "raw_info": out,
                        "security_level": self.security_level.value
                    }
                raise RuntimeError(f"Fallo al consultar volumen: {err}")

            # 2. ESTABLECER VOLUMEN
            elif action == "set":
                if level is None:
                    return {
                        "status": "error",
                        "message": "Debes especificar el parámetro 'level' (0-100) para fijar el volumen."
                    }
                level = max(0, min(100, int(level)))
                vol_str = f"{level / 100.0:.2f}"

                # Si sube volumen, desilenciar automáticamente
                if level > 0:
                    await self._run_command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0")

                code, out, err = await self._run_command("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", vol_str)
                if code != 0:
                    # Fallback pactl
                    code, out, err = await self._run_command("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%")
                    if code != 0:
                        raise RuntimeError(f"Fallo al ajustar volumen: {err}")

                return {
                    "status": "success",
                    "action": "set",
                    "volume_percent": level,
                    "message": f"Volumen del sistema establecido en {level}%.",
                    "security_level": self.security_level.value
                }

            # 3. SILENCIAR
            elif action == "mute":
                code, out, err = await self._run_command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1")
                if code != 0:
                    await self._run_command("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1")
                return {
                    "status": "success",
                    "action": "mute",
                    "muted": True,
                    "message": "Audio silenciado.",
                    "security_level": self.security_level.value
                }

            # 4. REACTIVAR SONIDO
            elif action == "unmute":
                code, out, err = await self._run_command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0")
                if code != 0:
                    await self._run_command("pactl", "set-sink-mute", "@DEFAULT_SINK@", "0")
                return {
                    "status": "success",
                    "action": "unmute",
                    "muted": False,
                    "message": "Audio reactivado.",
                    "security_level": self.security_level.value
                }

            # 5. ALTERNAR SILENCIO
            elif action == "toggle_mute":
                code, out, err = await self._run_command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
                if code != 0:
                    await self._run_command("pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle")
                return {
                    "status": "success",
                    "action": "toggle_mute",
                    "message": "Estado de silencio alternado.",
                    "security_level": self.security_level.value
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción desconocida '{action}'. Usa 'get', 'set', 'mute', 'unmute' o 'toggle_mute'."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en AudioControlSkill -> {str(e)}",
                "security_level": self.security_level.value
            }
