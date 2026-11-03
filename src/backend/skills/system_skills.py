import asyncio
import os
import glob
import shutil
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

