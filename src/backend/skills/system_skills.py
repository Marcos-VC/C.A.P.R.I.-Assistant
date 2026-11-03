import asyncio
import os
import glob
import shutil
import time
import json
import socket
import datetime
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List
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


class AppLauncherSkill(BaseSkill):
    """
    Habilidad táctica para abrir y lanzar aplicaciones en Ubuntu Linux (GNOME).
    Permite abrir navegadores (Firefox, Chrome), editores (VS Code), terminales,
    utilidades (calculadora, explorador de archivos, ajustes) o cualquier app instalada.
    Nivel de seguridad: SAFE.
    """
    name = "app_launcher"
    description = (
        "Lanza o abre una aplicación instalada en el sistema operativo Ubuntu "
        "(ejemplos: 'firefox', 'code' / 'vscode', 'terminal', 'calculadora', 'spotify', 'archivos' / 'nautilus', 'ajustes', etc.)."
    )
    security_level = SecurityLevel.SAFE

    # Mapeo de alias comunes a identificadores de escritorio y ejecutables
    ALIAS_MAP = {
        "firefox": ["firefox_firefox.desktop", "firefox.desktop"],
        "navegador": ["firefox_firefox.desktop", "firefox.desktop", "google-chrome.desktop"],
        "browser": ["firefox_firefox.desktop", "firefox.desktop", "google-chrome.desktop"],
        "chrome": ["google-chrome.desktop", "chromium.desktop"],
        "code": ["code_code.desktop", "code.desktop"],
        "vscode": ["code_code.desktop", "code.desktop"],
        "vs code": ["code_code.desktop", "code.desktop"],
        "terminal": ["org.gnome.Terminal.desktop", "gnome-terminal.desktop"],
        "consola": ["org.gnome.Terminal.desktop", "gnome-terminal.desktop"],
        "calculadora": ["org.gnome.Calculator.desktop", "gnome-calculator.desktop"],
        "calculator": ["org.gnome.Calculator.desktop", "gnome-calculator.desktop"],
        "archivos": ["org.gnome.Nautilus.desktop", "nautilus.desktop"],
        "files": ["org.gnome.Nautilus.desktop", "nautilus.desktop"],
        "carpetas": ["org.gnome.Nautilus.desktop", "nautilus.desktop"],
        "nautilus": ["org.gnome.Nautilus.desktop", "nautilus.desktop"],
        "ajustes": ["org.gnome.Settings.desktop", "gnome-control-center.desktop"],
        "configuracion": ["org.gnome.Settings.desktop", "gnome-control-center.desktop"],
        "settings": ["org.gnome.Settings.desktop", "gnome-control-center.desktop"],
        "spotify": ["spotify_spotify.desktop", "spotify.desktop"],
        "editor": ["org.gnome.TextEditor.desktop", "gedit_gedit.desktop", "gedit.desktop"],
        "texto": ["org.gnome.TextEditor.desktop", "gedit_gedit.desktop", "gedit.desktop"],
    }

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "app_name": types.Schema(
                    type=types.Type.STRING,
                    description="Nombre o alias de la aplicación que se desea abrir (ej: 'firefox', 'code', 'terminal', 'calculadora', 'archivos', 'spotify')."
                )
            },
            required=["app_name"]
        )

    def _find_desktop_file(self, query: str) -> Optional[tuple[str, str]]:
        """
        Busca un archivo .desktop que coincida con la consulta en los directorios estándar de Ubuntu.
        Devuelve una tupla (desktop_id, absolute_path) o None.
        """
        clean = query.lower().strip()
        desktop_dirs = [
            "/usr/share/applications",
            "/var/lib/snapd/desktop/applications",
            os.path.expanduser("~/.local/share/applications")
        ]

        # 1. Comprobar tabla de alias
        candidates = self.ALIAS_MAP.get(clean, [clean if clean.endswith(".desktop") else f"{clean}.desktop"])

        for cand in candidates:
            for d in desktop_dirs:
                path = os.path.join(d, cand)
                if os.path.exists(path):
                    desktop_id = cand[:-8] if cand.endswith(".desktop") else cand
                    return desktop_id, path

        # 2. Búsqueda por subcadena en nombres de archivo .desktop
        for d in desktop_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if fname.endswith(".desktop") and clean in fname.lower():
                    path = os.path.join(d, fname)
                    desktop_id = fname[:-8]
                    return desktop_id, path

        return None

    async def execute(self, **kwargs) -> Dict[str, Any]:
        app_name = kwargs.get("app_name", "").strip()
        if not app_name:
            return {
                "status": "error",
                "message": "Debes especificar el parámetro 'app_name' para lanzar una aplicación."
            }

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
        if "WAYLAND_DISPLAY" not in env and os.path.exists(f"/run/user/{os.getuid()}/wayland-0"):
            env["WAYLAND_DISPLAY"] = "wayland-0"

        # 1. Intentar localizar archivo .desktop
        match = self._find_desktop_file(app_name)
        if match:
            desktop_id, desktop_path = match

            # Intentar con gtk-launch
            if shutil.which("gtk-launch"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "gtk-launch", desktop_id,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        return {
                            "status": "success",
                            "app_name": app_name,
                            "launcher": "gtk-launch",
                            "desktop_id": desktop_id,
                            "message": f"Aplicación '{app_name}' iniciada correctamente con gtk-launch ({desktop_id}).",
                            "security_level": self.security_level.value
                        }
                except Exception:
                    pass

            # Fallback: gio launch
            if shutil.which("gio"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "gio", "launch", desktop_path,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        return {
                            "status": "success",
                            "app_name": app_name,
                            "launcher": "gio launch",
                            "desktop_path": desktop_path,
                            "message": f"Aplicación '{app_name}' iniciada correctamente con gio launch.",
                            "security_level": self.security_level.value
                        }
                except Exception:
                    pass

        # 2. Fallback por ejecutable directo (PATH)
        bin_path = shutil.which(app_name.lower())
        if bin_path:
            try:
                # Lanzar en segundo plano sin esperar a que termine la app GUI
                await asyncio.create_subprocess_exec(
                    bin_path,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                return {
                    "status": "success",
                    "app_name": app_name,
                    "launcher": "direct_binary",
                    "binary_path": bin_path,
                    "message": f"Aplicación '{app_name}' ejecutada desde binario ({bin_path}).",
                    "security_level": self.security_level.value
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Fallo al ejecutar binario '{bin_path}': {str(e)}"
                }

        return {
            "status": "error",
            "message": f"No se encontró la aplicación '{app_name}' en los registros de escritorio (.desktop) ni en el PATH del sistema."
        }


class PowerControlSkill(BaseSkill):
    """
    Habilidad táctica para gestionar energía, batería, brillo de pantalla y bloqueo de sesión en Ubuntu.
    Permite consultar batería ('battery'), consultar o ajustar brillo ('get_brightness', 'set_brightness')
    y bloquear la pantalla del escritorio ('lock').
    Nivel de seguridad: SAFE.
    """
    name = "power_control"
    description = (
        "Gestiona la energía, batería, brillo de pantalla y bloqueo de sesión en Ubuntu Linux. "
        "Permite consultar el estado y porcentaje de batería ('battery'), "
        "consultar el brillo actual ('get_brightness'), ajustar el nivel de brillo de 0 a 100% ('set_brightness') "
        "y bloquear la pantalla del escritorio ('lock')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción a realizar: 'battery' (estado batería), 'get_brightness' (consultar brillo), 'set_brightness' (ajustar brillo 0-100%), 'lock' (bloquear pantalla).",
                    enum=["battery", "get_brightness", "set_brightness", "lock"]
                ),
                "level": types.Schema(
                    type=types.Type.INTEGER,
                    description="Nivel de brillo en porcentaje de 0 a 100 (requerido únicamente para action='set_brightness')."
                )
            },
            required=["action"]
        )

    def _read_battery_sysfs(self) -> Optional[Dict[str, Any]]:
        base_dir = "/sys/class/power_supply"
        if not os.path.isdir(base_dir):
            return None
        bats = [d for d in os.listdir(base_dir) if d.startswith("BAT")]
        if not bats:
            return None
        bat_path = os.path.join(base_dir, bats[0])
        cap_file = os.path.join(bat_path, "capacity")
        stat_file = os.path.join(bat_path, "status")
        if os.path.exists(cap_file):
            try:
                with open(cap_file, "r") as f:
                    cap = int(f.read().strip())
                status = "Desconocido"
                if os.path.exists(stat_file):
                    with open(stat_file, "r") as f:
                        status = f.read().strip()
                return {"percent": cap, "status": status, "device": bats[0]}
            except Exception:
                pass
        return None

    def _read_brightness_sysfs(self) -> Optional[int]:
        base_dir = "/sys/class/backlight"
        if not os.path.isdir(base_dir):
            return None
        controllers = os.listdir(base_dir)
        if not controllers:
            return None
        ctrl_path = os.path.join(base_dir, controllers[0])
        b_file = os.path.join(ctrl_path, "brightness")
        mb_file = os.path.join(ctrl_path, "max_brightness")
        if os.path.exists(b_file) and os.path.exists(mb_file):
            try:
                with open(b_file, "r") as f:
                    curr = float(f.read().strip())
                with open(mb_file, "r") as f:
                    mx = float(f.read().strip())
                if mx > 0:
                    return int(round((curr / mx) * 100))
            except Exception:
                pass
        return None

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "battery").lower().strip()
        level = kwargs.get("level")

        try:
            # 1. ESTADO DE BATERÍA
            if action == "battery":
                data = self._read_battery_sysfs()
                if data:
                    pct = data["percent"]
                    st = data["status"]
                    icon = "🔌" if "charg" in st.lower() else "🔋"
                    return {
                        "status": "success",
                        "action": "battery",
                        "battery_percent": pct,
                        "charging_status": st,
                        "message": f"{icon} Batería al {pct}% [{st}].",
                        "security_level": self.security_level.value
                    }
                # Fallback con upower
                if shutil.which("upower"):
                    proc = await asyncio.create_subprocess_exec(
                        "upower", "-e",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    out, _ = await proc.communicate()
                    devices = [line.strip() for line in out.decode().splitlines() if "battery" in line]
                    if devices:
                        iproc = await asyncio.create_subprocess_exec(
                            "upower", "-i", devices[0],
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        iout, _ = await iproc.communicate()
                        return {
                            "status": "success",
                            "action": "battery",
                            "raw_info": iout.decode().strip(),
                            "message": "Información de energía recuperada vía UPower.",
                            "security_level": self.security_level.value
                        }

                return {
                    "status": "success",
                    "action": "battery",
                    "message": "No se detectó batería conectada (sistema sobre alimentación directa AC).",
                    "security_level": self.security_level.value
                }

            # 2. CONSULTAR BRILLO
            elif action == "get_brightness":
                val = self._read_brightness_sysfs()
                if val is not None:
                    return {
                        "status": "success",
                        "action": "get_brightness",
                        "brightness_percent": val,
                        "message": f"Nivel de brillo actual: {val}%.",
                        "security_level": self.security_level.value
                    }
                return {
                    "status": "error",
                    "message": "No se pudo leer el sensor de brillo de pantalla en /sys/class/backlight."
                }

            # 3. AJUSTAR BRILLO
            elif action == "set_brightness":
                if level is None:
                    return {
                        "status": "error",
                        "message": "Debes especificar el parámetro 'level' (0-100) para ajustar el brillo."
                    }
                target_level = max(5, min(100, int(level)))

                # 1) Probar gdbus con org.gnome.SettingsDaemon.Power
                gdbus_bin = shutil.which("gdbus")
                if gdbus_bin:
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "gdbus", "call", "--session",
                            "--dest", "org.gnome.SettingsDaemon.Power",
                            "--object-path", "/org/gnome/SettingsDaemon/Power",
                            "--method", "org.freedesktop.DBus.Properties.Set",
                            "org.gnome.SettingsDaemon.Power.Screen", "Brightness",
                            f"<int32 {target_level}>",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await proc.communicate()
                        if proc.returncode == 0:
                            return {
                                "status": "success",
                                "action": "set_brightness",
                                "brightness_percent": target_level,
                                "message": f"Brillo ajustado al {target_level}% vía GNOME Power.",
                                "security_level": self.security_level.value
                            }
                    except Exception:
                        pass

                # 2) Fallback con brightnessctl
                if shutil.which("brightnessctl"):
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "brightnessctl", "set", f"{target_level}%",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await proc.communicate()
                        if proc.returncode == 0:
                            return {
                                "status": "success",
                                "action": "set_brightness",
                                "brightness_percent": target_level,
                                "message": f"Brillo ajustado al {target_level}% vía brightnessctl.",
                                "security_level": self.security_level.value
                            }
                    except Exception:
                        pass

                return {
                    "status": "error",
                    "message": f"No se pudo modificar el brillo al {target_level}%. Instala 'brightnessctl' o verifica la sesión GNOME."
                }

            # 4. BLOQUEAR PANTALLA
            elif action == "lock":
                lock_bin = shutil.which("loginctl")
                if lock_bin:
                    proc = await asyncio.create_subprocess_exec(
                        "loginctl", "lock-session",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    return {
                        "status": "success",
                        "action": "lock",
                        "message": "🔒 Pantalla de escritorio bloqueada.",
                        "security_level": self.security_level.value
                    }
                return {
                    "status": "error",
                    "message": "No se encontró el comando 'loginctl' para bloquear la sesión."
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción desconocida '{action}'. Usa 'battery', 'get_brightness', 'set_brightness' o 'lock'."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en PowerControlSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


class ProcessManagerSkill(BaseSkill):
    """
    Habilidad táctica para supervisar y gestionar procesos en ejecución en Ubuntu Linux.
    Permite consultar los procesos que más CPU ('top_cpu') o memoria RAM ('top_ram') consumen,
    buscar procesos por nombre ('find') y finalizar procesos ('kill').
    Nivel de seguridad: SAFE para lectura, con confirmación requerida internamente para 'kill'.
    """
    name = "process_manager"
    description = (
        "Supervisa y administra procesos del sistema en Ubuntu. "
        "Permite listar los procesos con mayor uso de CPU ('top_cpu') o memoria ('top_ram'), "
        "buscar procesos por nombre ('find') y terminar un proceso por PID ('kill')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción a realizar: 'top_cpu' (procesos con más CPU), 'top_ram' (procesos con más RAM), 'find' (buscar por nombre), 'kill' (terminar proceso).",
                    enum=["top_cpu", "top_ram", "find", "kill"]
                ),
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Término o nombre de proceso a buscar (para action='find' o 'kill')."
                ),
                "pid": types.Schema(
                    type=types.Type.INTEGER,
                    description="PID numérico del proceso a terminar (para action='kill')."
                ),
                "confirmed": types.Schema(
                    type=types.Type.BOOLEAN,
                    description="Confirmación obligatoria del usuario para matar procesos (action='kill'). Debe ser true si el usuario ha pedido expresamente cerrar o matar la aplicación."
                )
            },
            required=["action"]
        )

    async def _run_ps(self, sort_by: str, limit: int = 7) -> List[Dict[str, Any]]:
        proc = await asyncio.create_subprocess_exec(
            "ps", "-eo", "pid,comm,%cpu,%mem", f"--sort=-{sort_by}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, _ = await proc.communicate()
        lines = out.decode().strip().splitlines()
        results = []
        if len(lines) > 1:
            for line in lines[1:limit + 1]:
                parts = line.split()
                if len(parts) >= 4:
                    results.append({
                        "pid": int(parts[0]),
                        "command": parts[1],
                        "cpu_percent": parts[2],
                        "mem_percent": parts[3]
                    })
        return results

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "top_cpu").lower().strip()
        query = kwargs.get("query", "").strip()
        pid = kwargs.get("pid")
        confirmed = kwargs.get("confirmed", False)

        try:
            # 1. TOP CPU
            if action == "top_cpu":
                processes = await self._run_ps("%cpu")
                summary_lines = [f"• PID {p['pid']} ({p['command']}): CPU {p['cpu_percent']}% | RAM {p['mem_percent']}%" for p in processes]
                msg = "Procesos con mayor uso de CPU:\n" + "\n".join(summary_lines)
                return {
                    "status": "success",
                    "action": "top_cpu",
                    "processes": processes,
                    "message": msg,
                    "security_level": self.security_level.value
                }

            # 2. TOP RAM
            elif action == "top_ram":
                processes = await self._run_ps("%mem")
                summary_lines = [f"• PID {p['pid']} ({p['command']}): RAM {p['mem_percent']}% | CPU {p['cpu_percent']}%" for p in processes]
                msg = "Procesos con mayor uso de Memoria RAM:\n" + "\n".join(summary_lines)
                return {
                    "status": "success",
                    "action": "top_ram",
                    "processes": processes,
                    "message": msg,
                    "security_level": self.security_level.value
                }

            # 3. BUSCAR PROCESOS
            elif action == "find":
                if not query:
                    return {"status": "error", "message": "Debes especificar 'query' con el nombre del proceso a buscar."}
                proc = await asyncio.create_subprocess_exec(
                    "ps", "-eo", "pid,comm,%cpu,%mem",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                out, _ = await proc.communicate()
                matches = []
                for line in out.decode().strip().splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4 and query.lower() in parts[1].lower():
                        matches.append({
                            "pid": int(parts[0]),
                            "command": parts[1],
                            "cpu_percent": parts[2],
                            "mem_percent": parts[3]
                        })
                if matches:
                    summary_lines = [f"• PID {p['pid']} ({p['command']}): CPU {p['cpu_percent']}% | RAM {p['mem_percent']}%" for p in matches[:8]]
                    msg = f"Se encontraron {len(matches)} proceso(s) para '{query}':\n" + "\n".join(summary_lines)
                    return {"status": "success", "action": "find", "query": query, "matches": matches, "message": msg}
                return {"status": "success", "action": "find", "query": query, "matches": [], "message": f"No se encontró ningún proceso activo que coincida con '{query}'."}

            # 4. TERMINAR PROCESO (KILL)
            elif action == "kill":
                # Si no se pasó PID pero sí query, intentar resolverlo
                target_pid = pid
                target_name = query
                if not target_pid and query:
                    # Buscar el PID de ese proceso
                    proc = await asyncio.create_subprocess_exec("pgrep", "-f", query, stdout=asyncio.subprocess.PIPE)
                    pout, _ = await proc.communicate()
                    pids = [int(p) for p in pout.decode().split() if p.isdigit()]
                    if pids:
                        target_pid = pids[0]
                    else:
                        return {"status": "error", "message": f"No se encontró ningún proceso activo con nombre '{query}'."}

                if not target_pid:
                    return {"status": "error", "message": "Debes especificar el 'pid' numérico o el nombre 'query' del proceso a terminar."}

                # Protección: evitar matar PID 1 o procesos del sistema crítico
                if target_pid <= 1:
                    return {"status": "blocked", "message": f"[SEGURIDAD]: Prohibido terminar el proceso crítico PID {target_pid}."}

                # Verificación de confirmación de seguridad
                if not confirmed:
                    return {
                        "status": "confirmation_required",
                        "security_level": SecurityLevel.CONFIRM_REQUIRED.value,
                        "pid": target_pid,
                        "query": target_name,
                        "message": f"⚠️ [CONFIRMACIÓN REQUERIDA]: ¿Confirmas terminar el proceso PID {target_pid} ({target_name or 'proceso'})? Responde afirmativamente para proceder."
                    }

                # Ejecutar SIGTERM primero
                kproc = await asyncio.create_subprocess_exec(
                    "kill", "-15", str(target_pid),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, kerr = await kproc.communicate()
                if kproc.returncode == 0:
                    return {
                        "status": "success",
                        "action": "kill",
                        "pid": target_pid,
                        "message": f"Proceso PID {target_pid} finalizado correctamente.",
                        "security_level": self.security_level.value
                    }
                return {
                    "status": "error",
                    "message": f"Fallo al terminar PID {target_pid}: {kerr.decode().strip() or 'Permiso denegado o proceso inexistente'}"
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción desconocida '{action}'. Usa 'top_cpu', 'top_ram', 'find' o 'kill'."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en ProcessManagerSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


class TimerReminderSkill(BaseSkill):
    """
    Habilidad táctica para gestionar temporizadores, Pomodoro y alertas en Ubuntu.
    Al concluir el tiempo, emite una notificación nativa en el escritorio.
    Nivel de seguridad: SAFE.
    """
    name = "timer_reminder"
    description = (
        "Configura temporizadores, avisos de productividad (Pomodoro) y recordatorios en el escritorio Ubuntu. "
        "Permite iniciar un temporizador ('set_timer' con minutos o segundos), "
        "listar los temporizadores activos ('list') y cancelar un temporizador ('cancel' con timer_id)."
    )
    security_level = SecurityLevel.SAFE

    # Almacén en memoria de temporizadores activos en la sesión
    _active_timers: Dict[str, Dict[str, Any]] = {}
    _counter: int = 0

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción a realizar: 'set_timer' (crear cuenta atrás), 'list' (ver activos), 'cancel' (cancelar temporizador).",
                    enum=["set_timer", "list", "cancel"]
                ),
                "minutes": types.Schema(
                    type=types.Type.NUMBER,
                    description="Duración del temporizador en minutos (ej: 0.5 para 30s, 15 para 15 minutos, 25 para Pomodoro)."
                ),
                "seconds": types.Schema(
                    type=types.Type.INTEGER,
                    description="Duración adicional o exacta en segundos."
                ),
                "label": types.Schema(
                    type=types.Type.STRING,
                    description="Motivo o etiqueta del temporizador (ej: 'Descanso Pomodoro', 'Pizza en el horno', 'Revisar servidor')."
                ),
                "timer_id": types.Schema(
                    type=types.Type.STRING,
                    description="Identificador del temporizador para cancelar (para action='cancel')."
                )
            },
            required=["action"]
        )

    @classmethod
    async def _timer_worker(cls, timer_id: str, total_seconds: float, label: str):
        try:
            await asyncio.sleep(total_seconds)
            # Emitir notificación nativa en escritorio Ubuntu si sigue activo
            if timer_id in cls._active_timers:
                cls._active_timers.pop(timer_id, None)
                if shutil.which("notify-send"):
                    env = os.environ.copy()
                    if "DISPLAY" not in env:
                        env["DISPLAY"] = ":0"
                    try:
                        await asyncio.create_subprocess_exec(
                            "notify-send",
                            "✦ C.A.P.R.I. // ALERTA TÁCTICA",
                            f"⏰ ¡Tiempo cumplido!: {label}",
                            "-u", "critical",
                            "-t", "8000",
                            env=env
                        )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "set_timer").lower().strip()
        minutes = kwargs.get("minutes")
        seconds = kwargs.get("seconds")
        label = kwargs.get("label", "Alerta táctica de C.A.P.R.I.").strip()
        timer_id = kwargs.get("timer_id", "").strip()

        try:
            # 1. CREAR TEMPORIZADOR
            if action == "set_timer":
                total_sec = 0.0
                if minutes is not None:
                    total_sec += float(minutes) * 60.0
                if seconds is not None:
                    total_sec += float(seconds)

                if total_sec <= 0:
                    return {
                        "status": "error",
                        "message": "Debes especificar una duración positiva en 'minutes' o 'seconds'."
                    }

                TimerReminderSkill._counter += 1
                t_id = f"T-{TimerReminderSkill._counter}"
                ends_at = time.time() + total_sec

                task = asyncio.create_task(self._timer_worker(t_id, total_sec, label))

                TimerReminderSkill._active_timers[t_id] = {
                    "id": t_id,
                    "label": label,
                    "duration_sec": total_sec,
                    "ends_at": ends_at,
                    "task": task
                }

                readable_dur = f"{minutes} min" if minutes and not seconds else f"{int(total_sec)} seg"
                return {
                    "status": "success",
                    "action": "set_timer",
                    "timer_id": t_id,
                    "duration_sec": total_sec,
                    "label": label,
                    "message": f"⏳ Temporizador {t_id} iniciado ({readable_dur}) para: '{label}'. Te avisaré al completarse.",
                    "security_level": self.security_level.value
                }

            # 2. LISTAR TEMPORIZADORES
            elif action == "list":
                now = time.time()
                active_list = []
                for tid, item in list(TimerReminderSkill._active_timers.items()):
                    rem = max(0, int(item["ends_at"] - now))
                    active_list.append({
                        "id": tid,
                        "label": item["label"],
                        "remaining_seconds": rem
                    })

                if not active_list:
                    return {
                        "status": "success",
                        "action": "list",
                        "timers": [],
                        "message": "No hay ningún temporizador activo en este momento.",
                        "security_level": self.security_level.value
                    }

                lines = [f"• [{t['id']}] {t['label']} (quedan {t['remaining_seconds']}s)" for t in active_list]
                return {
                    "status": "success",
                    "action": "list",
                    "timers": active_list,
                    "message": "Temporizadores activos:\n" + "\n".join(lines),
                    "security_level": self.security_level.value
                }

            # 3. CANCELAR TEMPORIZADOR
            elif action == "cancel":
                if not timer_id:
                    return {"status": "error", "message": "Debes especificar el 'timer_id' a cancelar (ej: 'T-1')."}

                timer_entry = TimerReminderSkill._active_timers.pop(timer_id, None)
                if timer_entry:
                    task = timer_entry.get("task")
                    if task and not task.done():
                        task.cancel()
                    return {
                        "status": "success",
                        "action": "cancel",
                        "timer_id": timer_id,
                        "message": f"Temporizador {timer_id} cancelado correctamente.",
                        "security_level": self.security_level.value
                    }
                return {
                    "status": "error",
                    "message": f"No se encontró ningún temporizador activo con ID '{timer_id}'."
                }

            else:
                return {
                    "status": "error",
                    "message": f"Acción desconocida '{action}'. Usa 'set_timer', 'list' o 'cancel'."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en TimerReminderSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


class WebLookupSkill(BaseSkill):
    """
    Habilidad para consultas meteorológicas en tiempo real y resúmenes web concisos.
    Nivel de seguridad: SAFE.
    """
    name = "web_lookup"
    description = (
        "Consulta información en tiempo real desde la web: "
        "clima meteorológico actual de cualquier ciudad ('weather') o resúmenes enciclopédicos rápidos ('search')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción: 'weather' (pronóstico del tiempo), 'search' (resumen de conocimiento o definición).",
                    enum=["weather", "search"]
                ),
                "location": types.Schema(
                    type=types.Type.STRING,
                    description="Nombre de la ciudad o localidad (para action='weather', ej: 'Madrid', 'Barcelona', 'Buenos Aires')."
                ),
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Término o concepto a consultar (para action='search', ej: 'Kernel Linux', 'Wayland vs X11')."
                )
            },
            required=["action"]
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "weather").lower().strip()
        location = kwargs.get("location", "Madrid").strip()
        query = kwargs.get("query", "").strip()

        try:
            # 1. CONSULTA DE CLIMA METEOROLÓGICO
            if action == "weather":
                loc_encoded = urllib.parse.quote(location)
                url = f"https://wttr.in/{loc_encoded}?format=%C:+%t+(sensaci%C3%B3n+%f),+humedad+%h,+viento+%w"

                def _fetch_weather():
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "curl/7.88.1"}  # wttr.in detecta curl y devuelve texto limpio
                    )
                    with urllib.request.urlopen(req, timeout=3.5) as r:
                        return r.read().decode("utf-8").strip()

                try:
                    report = await asyncio.to_thread(_fetch_weather)
                    return {
                        "status": "success",
                        "action": "weather",
                        "location": location,
                        "report": report,
                        "message": f"Clima actual en {location}:\n🌦️ {report}",
                        "security_level": self.security_level.value
                    }
                except Exception as net_err:
                    return {
                        "status": "error",
                        "message": f"No se pudo contactar con el servicio meteorológico para '{location}': {str(net_err)}"
                    }

            # 2. BÚSQUEDA RÁPIDA / WIKIPEDIA
            elif action == "search":
                if not query:
                    return {"status": "error", "message": "Debes especificar 'query' para realizar una búsqueda."}

                def _fetch_summary():
                    q_enc = urllib.parse.quote(query)
                    # Consultar API REST de Wikipedia en español
                    url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{q_enc}"
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "CapriAssistant/2.0 (linux; x86_64)"}
                    )
                    with urllib.request.urlopen(req, timeout=3.5) as r:
                        data = json.loads(r.read().decode("utf-8"))
                        title = data.get("title", query)
                        extract = data.get("extract", "")
                        return title, extract

                try:
                    title, extract = await asyncio.to_thread(_fetch_summary)
                    if extract:
                        return {
                            "status": "success",
                            "action": "search",
                            "title": title,
                            "summary": extract,
                            "message": f"Información sobre '{title}':\n{extract}",
                            "security_level": self.security_level.value
                        }
                    return {
                        "status": "success",
                        "action": "search",
                        "message": f"No se encontró un artículo directo para '{query}'."
                    }
                except Exception as net_err:
                    return {
                        "status": "error",
                        "message": f"Fallo al conectar con la base de conocimiento para '{query}': {str(net_err)}"
                    }

            else:
                return {
                    "status": "error",
                    "message": f"Acción desconocida '{action}'. Usa 'weather' o 'search'."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en WebLookupSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


class NetworkInfoSkill(BaseSkill):
    """
    Habilidad táctica para diagnosticar conectividad de red, latencia, interfaces IP y Wi-Fi en Ubuntu.
    Nivel de seguridad: SAFE.
    """
    name = "network_info"
    description = (
        "Diagnostica la red y enlace neural en Ubuntu. "
        "Permite medir latencia ('ping' a un host como 1.1.1.1 o google.com), "
        "consultar las direcciones IP locales ('ip') "
        "y revisar la red Wi-Fi activa y potencia de señal ('wifi')."
    )
    security_level = SecurityLevel.SAFE

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción de diagnóstico: 'ping' (medir latencia), 'ip' (direcciones IP locales), 'wifi' (estado Wi-Fi).",
                    enum=["ping", "ip", "wifi"]
                ),
                "host": types.Schema(
                    type=types.Type.STRING,
                    description="Host o servidor a verificar con ping (por defecto '1.1.1.1' o '8.8.8.8')."
                )
            },
            required=["action"]
        )

    def _socket_ping(self, host: str, port: int = 53, timeout: float = 2.0) -> Optional[float]:
        """Calcula el RTT en milisegundos mediante socket TCP/DNS sin requerir privilegios raw."""
        try:
            start = time.time()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return round((time.time() - start) * 1000.0, 1)
        except Exception:
            return None

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "ping").lower().strip()
        host = kwargs.get("host", "1.1.1.1").strip()

        try:
            # 1. PING / LATENCIA
            if action == "ping":
                # Intentar primero con ping ICMP si está permitido
                ping_bin = shutil.which("ping")
                if ping_bin:
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            ping_bin, "-c", "2", "-W", "2", host,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        out, _ = await proc.communicate()
                        if proc.returncode == 0:
                            lines = out.decode().strip().splitlines()
                            stat_line = [l for l in lines if "avg" in l or "min/avg" in l]
                            summary = stat_line[0] if stat_line else lines[-1]
                            return {
                                "status": "success",
                                "action": "ping",
                                "host": host,
                                "raw": summary,
                                "message": f"Conexión con {host} activa: {summary}",
                                "security_level": self.security_level.value
                            }
                    except Exception:
                        pass

                # Fallback con socket TCP handshake (100% no privilegiado)
                target_ip = host if host.replace(".", "").isdigit() else "1.1.1.1"
                rtt = await asyncio.to_thread(self._socket_ping, target_ip, 53, 2.0)
                if rtt is not None:
                    return {
                        "status": "success",
                        "action": "ping",
                        "host": host,
                        "latency_ms": rtt,
                        "message": f"Enlace con {host} verificado: latencia de {rtt} ms (nova).",
                        "security_level": self.security_level.value
                    }

                return {
                    "status": "error",
                    "message": f"Fallo al medir enlace con {host}: sin respuesta de red o paquete bloqueado por ICE."
                }

            # 2. DIRECCIÓN IP LOCAL
            elif action == "ip":
                ip_bin = shutil.which("ip")
                if ip_bin:
                    proc = await asyncio.create_subprocess_exec(
                        ip_bin, "-brief", "addr", "show",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    out, _ = await proc.communicate()
                    lines = [l.strip() for l in out.decode().splitlines() if l.strip()]
                    clean_lines = [l for l in lines if not l.startswith("lo ")]
                    summary = "\n".join(clean_lines) if clean_lines else "\n".join(lines)
                    return {
                        "status": "success",
                        "action": "ip",
                        "interfaces": summary,
                        "message": f"Interfaces de red activas en el equipo:\n{summary}",
                        "security_level": self.security_level.value
                    }

                # Fallback vía hostname
                hn_bin = shutil.which("hostname")
                if hn_bin:
                    proc = await asyncio.create_subprocess_exec(hn_bin, "-I", stdout=asyncio.subprocess.PIPE)
                    out, _ = await proc.communicate()
                    return {
                        "status": "success",
                        "action": "ip",
                        "ips": out.decode().strip(),
                        "message": f"IPs locales detectadas: {out.decode().strip()}",
                        "security_level": self.security_level.value
                    }

                return {"status": "error", "message": "No se encontraron herramientas 'ip' ni 'hostname'."}

            # 3. ESTADO WI-FI
            elif action == "wifi":
                nmcli_bin = shutil.which("nmcli")
                if nmcli_bin:
                    proc = await asyncio.create_subprocess_exec(
                        nmcli_bin, "-t", "-f", "active,ssid,signal,bars", "dev", "wifi",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    out, _ = await proc.communicate()
                    lines = out.decode().splitlines()
                    active = [l for l in lines if l.startswith("yes:")]
                    if active:
                        parts = active[0].split(":")
                        ssid = parts[1] if len(parts) > 1 else "Conectado"
                        signal = parts[2] if len(parts) > 2 else "100"
                        return {
                            "status": "success",
                            "action": "wifi",
                            "ssid": ssid,
                            "signal_percent": signal,
                            "message": f"📶 Wi-Fi conectada a '{ssid}' con señal al {signal}% (enlace preem).",
                            "security_level": self.security_level.value
                        }
                    return {
                        "status": "success",
                        "action": "wifi",
                        "message": "No hay ninguna red Wi-Fi activa (posible conexión por cable Ethernet o interfaz en reposo).",
                        "security_level": self.security_level.value
                    }

                return {"status": "error", "message": "Herramienta 'nmcli' no disponible en el sistema."}

            else:
                return {"status": "error", "message": f"Acción desconocida '{action}'. Usa 'ping', 'ip' o 'wifi'."}

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en NetworkInfoSkill -> {str(e)}",
                "security_level": self.security_level.value
            }


class FileManagerSkill(BaseSkill):
    """
    Habilidad táctica para inspeccionar archivos, listar descargas y buscar documentos en Ubuntu.
    Nivel de seguridad: SAFE.
    """
    name = "file_manager"
    description = (
        "Explora y busca archivos en el almacenamiento de Ubuntu. "
        "Permite listar archivos de carpetas clave como Descargas o Documentos ('list'), "
        "buscar archivos por nombre o extensión ('search') "
        "y consultar los archivos más recientes o recién descargados ('recent')."
    )
    security_level = SecurityLevel.SAFE

    # Carpetas conocidas en el home del usuario
    KNOWN_FOLDERS = {
        "descargas": "~/Downloads",
        "downloads": "~/Downloads",
        "documentos": "~/Documents",
        "documents": "~/Documents",
        "escritorio": "~/Desktop",
        "desktop": "~/Desktop",
        "musica": "~/Music",
        "videos": "~/Videos",
        "imagenes": "~/Pictures",
        "workspace": ".",
        "proyecto": "."
    }

    def get_parameters_schema(self) -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "action": types.Schema(
                    type=types.Type.STRING,
                    description="Acción: 'list' (listar directorio), 'search' (buscar archivos por patrón), 'recent' (archivos recientes).",
                    enum=["list", "search", "recent"]
                ),
                "folder": types.Schema(
                    type=types.Type.STRING,
                    description="Carpeta a consultar (ej: 'Descargas', 'Documentos', 'Escritorio', '.' o una ruta absoluta/relativa)."
                ),
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Término o extensión a buscar (ej: '.pdf', 'informe', '.png', 'shimeji')."
                )
            },
            required=["action"]
        )

    def _resolve_path(self, folder: Optional[str]) -> str:
        if not folder:
            return os.path.expanduser("~")
        clean = folder.lower().strip()
        mapped = self.KNOWN_FOLDERS.get(clean)
        if mapped:
            return os.path.abspath(os.path.expanduser(mapped))
        return os.path.abspath(os.path.expanduser(folder))

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024.0:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024.0 * 1024.0):.1f} MB"
        return f"{size_bytes / (1024.0 * 1024.0 * 1024.0):.1f} GB"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "list").lower().strip()
        folder = kwargs.get("folder", "")
        query = kwargs.get("query", "").strip()

        target_dir = self._resolve_path(folder)

        if not os.path.exists(target_dir):
            return {"status": "error", "message": f"La ruta '{target_dir}' no existe en el sistema de archivos."}

        try:
            # 1. LISTAR DIRECTORIO
            if action == "list":
                items = os.listdir(target_dir)
                items.sort()
                entries = []
                for item in items[:15]:
                    p = os.path.join(target_dir, item)
                    is_dir = os.path.isdir(p)
                    icon = "📁" if is_dir else "📄"
                    sz = "" if is_dir else f" ({self._format_size(os.path.getsize(p))})"
                    entries.append(f"{icon} {item}{sz}")

                total_count = len(items)
                shown_count = min(15, total_count)
                lines = "\n".join(entries) if entries else "Carpeta vacía."
                msg = f"Contenido de '{target_dir}' ({shown_count}/{total_count} elementos):\n{lines}"
                return {
                    "status": "success",
                    "action": "list",
                    "path": target_dir,
                    "total_items": total_count,
                    "items": items[:15],
                    "message": msg,
                    "security_level": self.security_level.value
                }

            # 2. ARCHIVOS RECIENTES
            elif action == "recent":
                files_with_mtime = []
                for root, _, fnames in os.walk(target_dir):
                    for fn in fnames:
                        fp = os.path.join(root, fn)
                        try:
                            mtime = os.path.getmtime(fp)
                            files_with_mtime.append((mtime, fp, os.path.getsize(fp)))
                        except Exception:
                            continue
                    # Limitar profundidad
                    if root.count(os.sep) - target_dir.count(os.sep) >= 2:
                        break

                files_with_mtime.sort(key=lambda x: x[0], reverse=True)
                recent = files_with_mtime[:8]

                if not recent:
                    return {"status": "success", "action": "recent", "message": f"No se encontraron archivos en '{target_dir}'."}

                lines = []
                for mtime, fp, sz in recent:
                    dt = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
                    rel = os.path.relpath(fp, target_dir)
                    lines.append(f"• 📄 {rel} ({self._format_size(sz)}) — [{dt}]")

                msg = f"Archivos recientes en '{target_dir}':\n" + "\n".join(lines)
                return {
                    "status": "success",
                    "action": "recent",
                    "path": target_dir,
                    "recent_files": [f[1] for f in recent],
                    "message": msg,
                    "security_level": self.security_level.value
                }

            # 3. BUSCAR ARCHIVOS
            elif action == "search":
                if not query:
                    return {"status": "error", "message": "Debes especificar 'query' para buscar archivos."}

                matches = []
                for root, _, fnames in os.walk(target_dir):
                    for fn in fnames:
                        if query.lower() in fn.lower():
                            fp = os.path.join(root, fn)
                            try:
                                sz = os.path.getsize(fp)
                                matches.append((fp, sz))
                            except Exception:
                                continue
                            if len(matches) >= 12:
                                break
                    if len(matches) >= 12 or (root.count(os.sep) - target_dir.count(os.sep) >= 3):
                        break

                if not matches:
                    return {
                        "status": "success",
                        "action": "search",
                        "query": query,
                        "matches": [],
                        "message": f"No se encontró ningún archivo que coincida con '{query}' en '{target_dir}'."
                    }

                lines = [f"• 📄 {os.path.basename(m[0])} ({self._format_size(m[1])})\n   ↳ {m[0]}" for m in matches]
                msg = f"Resultados para '{query}' ({len(matches)} encontrados):\n" + "\n".join(lines)
                return {
                    "status": "success",
                    "action": "search",
                    "query": query,
                    "matches": [m[0] for m in matches],
                    "message": msg,
                    "security_level": self.security_level.value
                }

            else:
                return {"status": "error", "message": f"Acción desconocida '{action}'. Usa 'list', 'recent' o 'search'."}

        except Exception as e:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Error en FileManagerSkill -> {str(e)}",
                "security_level": self.security_level.value
            }

