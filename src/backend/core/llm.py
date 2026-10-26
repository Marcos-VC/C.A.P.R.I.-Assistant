import os
import asyncio
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
import httpx
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger("capri.llm")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SYSTEM_PROMPT = (
    "Eres C.A.P.R.I. (Cybernetic Autonomously Programmed Response Interface), "
    "un asistente de escritorio cyberpunk, eficiente, conciso y táctico para Ubuntu. "
    "Responde siempre en español, con un tono técnico, útil, directo y con un ligero toque cyberpunk. "
    "Mantén las respuestas claras y orientadas a la acción sin rodeos innecesarios."
)

# Modelos en la nube para fallback progresivo (ordenados por velocidad y disponibilidad)
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

# Cliente Gemini en caché para reutilización de sockets HTTPX
_gemini_client: Optional[genai.Client] = None
_cached_gemini_key: Optional[str] = None

def get_gemini_client() -> Optional[genai.Client]:
    """Obtiene o inicializa el cliente del SDK google-genai de forma singleton."""
    global _gemini_client, _cached_gemini_key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    if _gemini_client is None or _cached_gemini_key != api_key:
        _gemini_client = genai.Client(api_key=api_key)
        _cached_gemini_key = api_key
    return _gemini_client

def _build_gemini_contents(history: List[Dict[str, str]]) -> List[types.Content]:
    """Convierte el historial de C.A.P.R.I. al formato de Content de google-genai."""
    contents: List[types.Content] = []
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        text = msg.get("content", "").strip()
        if text:
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    
    # Si por alguna razón el historial está vacío, agregar un prompt genérico
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Estado del sistema.")]))
    
    return contents

async def _call_gemini_model(client: genai.Client, model: str, contents: List[types.Content], timeout: float = 8.0) -> str:
    """Ejecuta una llamada asíncrona a un modelo específico de Gemini."""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.7,
        max_output_tokens=600,
    )
    
    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        ),
        timeout=timeout
    )
    
    if response and response.text:
        return response.text.strip()
    raise ValueError(f"El modelo {model} devolvió una respuesta vacía.")

async def _call_groq_fallback(history: List[Dict[str, str]], timeout: float = 8.0) -> Optional[str]:
    """Fallback secundario 100% en la nube vía Groq API si está configurada."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return None

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = "user" if msg.get("role") == "user" else "assistant"
        content = msg.get("content", "").strip()
        if content:
            messages.append({"role": role, "content": content})

    async with httpx.AsyncClient(timeout=timeout) as http_client:
        for model in GROQ_MODELS:
            try:
                logger.info("Intentando fallback en la nube con Groq (%s)...", model)
                resp = await http_client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {groq_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 600
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"]["content"].strip()
                else:
                    logger.warning("Groq (%s) devolvió status %d: %s", model, resp.status_code, resp.text)
            except Exception as e:
                logger.warning("Error conectando con Groq (%s): %s", model, str(e))
    return None

async def generate_llm_response(history: List[Dict[str, str]]) -> str:
    """
    Genera la respuesta del LLM con cascada de fallback resiliente.
    Prioridad: Gemini (3.5-flash-lite -> 3.6-flash -> 3.5-flash) -> Groq Cloud (si está configurado).
    No consume recursos locales (CPU/RAM).
    """
    client = get_gemini_client()
    errors_log = []

    if client:
        contents = _build_gemini_contents(history)
        
        for model in GEMINI_MODELS:
            try:
                logger.info("C.A.P.R.I. consultando Gemini [%s]...", model)
                reply = await _call_gemini_model(client, model, contents, timeout=8.0)
                logger.info("Respuesta recibida exitosamente de Gemini [%s].", model)
                return reply
            except asyncio.TimeoutError:
                err_msg = f"Timeout (8s) en {model}"
                logger.warning("Gemini [%s]: %s. Probando siguiente modelo...", model, err_msg)
                errors_log.append(err_msg)
            except Exception as e:
                err_msg = f"{model}: {str(e)}"
                logger.warning("Error en Gemini [%s]: %s. Probando siguiente modelo...", model, str(e))
                errors_log.append(err_msg)
    else:
        errors_log.append("GEMINI_API_KEY no encontrada.")

    # Si los modelos de Gemini fallaron o no hay clave, intentar Groq Cloud si existe
    groq_reply = await _call_groq_fallback(history)
    if groq_reply:
        logger.info("Respuesta generada exitosamente mediante fallback en Groq.")
        return groq_reply

    # Si todo falló, devolver mensaje de diagnóstico con estética C.A.P.R.I.
    diag = " | ".join(errors_log)
    return (
        f"[SYSTEM ERROR]: Interrupción en el enlace neural con los servicios de nube.\n"
        f"Diagnóstico de fallos: {diag}.\n"
        f"Comprueba tu conexión de red o el estado de cuota en Google AI Studio."
    )
