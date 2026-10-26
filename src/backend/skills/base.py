from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
from google.genai import types

class SecurityLevel(str, Enum):
    """
    Niveles de seguridad para la ejecución de habilidades en el sistema operativo.
    [REGLA 4]: C.A.P.R.I. no debe ejecutar acciones críticas sin validación.
    """
    SAFE = "safe"                          # Lecturas del sistema, telemetría y diagnósticos (auto-aprobado)
    CONFIRM_REQUIRED = "confirm_required"  # Modificaciones de entorno, procesos o archivos
    PROHIBITED = "prohibited"              # Operaciones destructivas o comandos de alto riesgo (bloqueo total)

class BaseSkill(ABC):
    """Clase base abstracta para todas las habilidades del ecosistema C.A.P.R.I."""
    name: str
    description: str
    security_level: SecurityLevel = SecurityLevel.SAFE

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Ejecuta la lógica de la habilidad de forma 100% asíncrona."""
        pass

    def get_parameters_schema(self) -> types.Schema:
        """Define el esquema de parámetros para Gemini Function Calling (por defecto sin parámetros)."""
        return types.Schema(
            type=types.Type.OBJECT,
            properties={},
            required=[]
        )

    def to_gemini_declaration(self) -> types.FunctionDeclaration:
        """Convierte la habilidad en una declaración de función nativa de Gemini."""
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=self.get_parameters_schema()
        )
