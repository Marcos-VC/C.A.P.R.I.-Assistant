import asyncio
from typing import Dict, Any
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
