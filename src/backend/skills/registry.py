import logging
from typing import Dict, Optional, List, Any
from google.genai import types
from src.backend.skills.base import BaseSkill, SecurityLevel
from src.backend.skills.system_skills import SystemMonitorSkill

logger = logging.getLogger("capri.skills")

class SkillRegistry:
    """
    Registro centralizado y gestor de ejecución segura de habilidades para C.A.P.R.I.
    Asegura validación de permisos [REGLA 4] y asincronía obligatoria [REGLA 1].
    """
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill):
        """Registra una nueva habilidad en el catálogo."""
        self._skills[skill.name] = skill
        logger.info("Skill registrada: '%s' [Seguridad: %s]", skill.name, skill.security_level.value)

    def get(self, name: str) -> Optional[BaseSkill]:
        """Obtiene una habilidad por su nombre."""
        return self._skills.get(name)

    def list_skills(self) -> List[BaseSkill]:
        """Devuelve todas las habilidades registradas."""
        return list(self._skills.values())

    async def execute(self, name: str, params: Optional[Dict[str, Any]] = None, confirmed: bool = False) -> Dict[str, Any]:
        """
        Ejecuta una habilidad con verificación estricta de matriz de seguridad.
        """
        skill = self.get(name)
        if not skill:
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: La habilidad '{name}' no existe en el registro."
            }

        params = params or {}

        # 1. Validación de directiva PROHIBITED
        if skill.security_level == SecurityLevel.PROHIBITED:
            return {
                "status": "blocked",
                "message": f"[SYSTEM OVERLOAD]: Directiva rechazada. La habilidad '{name}' está catalogada como PROHIBIDA.",
                "security_level": skill.security_level.value
            }

        # 2. Validación de CONFIRM_REQUIRED
        if skill.security_level == SecurityLevel.CONFIRM_REQUIRED and not confirmed:
            return {
                "status": "confirmation_required",
                "message": f"[SYSTEM NOTICE]: La habilidad '{name}' requiere confirmación explícita del Operador para ejecutarse.",
                "security_level": skill.security_level.value,
                "skill_name": name,
                "params": params
            }

        # 3. Ejecución asíncrona segura
        try:
            return await skill.execute(**params)
        except Exception as e:
            logger.error("Error al ejecutar skill '%s': %s", name, str(e))
            return {
                "status": "error",
                "message": f"[SYSTEM ERROR]: Fallo interno en la ejecución de '{name}' -> {str(e)}"
            }

    def get_gemini_tools(self) -> Optional[types.Tool]:
        """
        Genera la estructura types.Tool para Gemini Function Calling
        a partir de todas las habilidades registradas.
        """
        declarations = [skill.to_gemini_declaration() for skill in self._skills.values()]
        if not declarations:
            return None
        return types.Tool(function_declarations=declarations)

# Instancia global del registro por defecto de C.A.P.R.I.
_default_registry: Optional[SkillRegistry] = None

def get_skill_registry() -> SkillRegistry:
    """Singleton para acceder al registro central de habilidades de C.A.P.R.I."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry()
        # Registrar habilidades base del sistema
        _default_registry.register(SystemMonitorSkill())
    return _default_registry

