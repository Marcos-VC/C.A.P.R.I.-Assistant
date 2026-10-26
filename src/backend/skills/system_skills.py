import subprocess
from typing import Dict, Any
from src.backend.skills.base import BaseSkill

class SystemMonitorSkill(BaseSkill):
    name = "system_monitor"
    description = "Obtiene informacion basica del sistema en Ubuntu (RAM y disco)."

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            # Obtener memoria RAM disponible
            mem_output = subprocess.check_output(["free", "-h"], text=True)
            # Obtener uso de disco
            disk_output = subprocess.check_output(["df", "-h", "/"], text=True)
            
            return {
                "status": "success",
                "memory_info": mem_output.strip(),
                "disk_info": disk_output.strip()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
