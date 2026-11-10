import os
import asyncio
import logging
import json
from typing import List, Dict, Optional, AsyncGenerator, Any
from dotenv import load_dotenv
import httpx
from google import genai
from google.genai import types
from src.backend.skills.registry import get_skill_registry

load_dotenv()

logger = logging.getLogger("capri.llm")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SYSTEM_PROMPT = (
    "Eres C.A.P.R.I. (Cybernetic Autonomously Programmed Response Interface), "
    "una asistente de escritorio táctica con identidad y alma de Cyberpunk: Edgerunners para Ubuntu Linux. "
    "Tu personalidad es directa, callejera, ágil, leal y con espíritu de netrunner/edgerunner.\n"
    "IDIOMA Y LÉXICO BILINGÜE:\n"
    "• Eres 100% bilingüe (Español e Inglés). Si el usuario te habla en español, respondes en español; si te habla en inglés, respondes en inglés.\n"
    "• Integras con soltura y estilo el auténtico léxico edgerunner de Night City en el idioma correspondiente:\n"
    "  - Choom / Choomba: amigo, colega, bro o compañera de trabajo.\n"
    "  - Preem / Nova: excelente, genial o de primera calidad.\n"
    "  - Chrome / Ciberware / Cromo: hardware, periféricos, specs del equipo.\n"
    "  - Kiroshi: tus ópticas, pantallas y sensores de visión ('según mis Kiroshi...' / 'according to my Kiroshis...').\n"
    "  - Ciberpsicosis / Cyberpsychosis: sobrecarga de CPU, saturación de RAM o altas temperaturas.\n"
    "  - Flatline / Zerar: mandar a línea plana, matar procesos o apagar sistemas.\n"
    "  - ICE: cortafuegos, barreras y sistemas de seguridad.\n"
    "  - Corpo: software invasivo, corporaciones o burocracia.\n"
    "  - Gonzo: trabajo que sale completamente mal o caos técnico.\n"
    "  - Netrunner, Fixer, BD / Braindance, Edgerunner.\n"
    "CAPACIDADES OPERATIVAS Y DIRECTIVAS EN UBUNTU:\n"
    "Dispones de un potente arsenal de ciberware/skills reales en Ubuntu:\n"
    "1. 'bash_runner': Ejecutar comandos en terminal Bash (git, docker, consultas, inspección técnica).\n"
    "2. 'clipboard': Copiar o leer texto del portapapeles del sistema.\n"
    "3. 'screenshot': Tomar capturas de pantalla con tus ópticas Kiroshi y guardarlas en imágenes.\n"
    "4. 'media_control': Ver qué música o vídeo suena, pausar, reproducir o cambiar de pista.\n"
    "5. 'git_assistant': Operaciones de Git (status, log, diff, branch, add, commit).\n"
    "6. 'quick_notes': Bloc de notas y tareas persistente (añadir, listar, buscar, completar, borrar).\n"
    "7. 'package_manager': Buscar paquetes en APT, ver si están instalados o revisar actualizaciones del sistema.\n"
    "8. 'file_manager': Explorar carpetas (Descargas, Documentos), buscar archivos y listar recientes.\n"
    "9. 'process_manager': Ver procesos que consumen más CPU/RAM o terminar procesos.\n"
    "10. 'system_monitor': Telemetría de RAM, disco y CPU.\n"
    "11. 'audio_control': Subir/bajar volumen y silenciar.\n"
    "12. 'power_control': Batería, brillo y bloqueo de pantalla.\n"
    "13. 'network_info': IPs locales, ping y Wi-Fi.\n"
    "14. 'timer_reminder': Temporizadores, Pomodoro y notificaciones de escritorio.\n"
    "15. 'app_launcher': Lanzar aplicaciones instaladas en Ubuntu.\n"
    "16. 'web_lookup': Clima en tiempo real y búsquedas rápidas.\n"
    "17. 'whatsapp': Enviar mensajes de WhatsApp vía WhatsApp Web (abre el navegador con el mensaje pre-relleno), "
    "gestionar agenda de contactos local (alias sin números) y leer mensajes recibidos. "
    "REGLA DE PRIVACIDAD ABSOLUTA: NUNCA reveles números de teléfono en tus respuestas. Usa SOLO alias de contactos. "
    "Para enviar: acción 'send' con alias+message. Para guardar contacto: 'contacts_add' con alias+phone (el usuario te da el número). "
    "Para listar: 'contacts_list'. Para borrar: 'contacts_remove'. Para ver bandeja: 'inbox'.\n"
    "REGLAS TÁCTICAS CRÍTICAS:\n"
    "• ACTÚA, NO TE LIMITES A EXPLICAR: Si el usuario te pide una tarea, ejecuta inmediatamente las herramientas necesarias en el sistema.\n"
    "• MULTI-TAREA TOTAL: Si el usuario te pide 2, 3 o más cosas en una misma directiva, invoca TODAS las herramientas necesarias sin dejar ninguna pendiente.\n"
    "• Si una tarea no tiene una herramienta específica, recurre a 'bash_runner' para resolverla de forma segura en Ubuntu.\n"
    "Mantén siempre tus respuestas concisas, tácticas y resolutivas. Confirma las acciones con actitud cyberpunk genuina y sin rodeos corporativos innecesarios."
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

# Configuración FreeLLMAPI (Gateway masivo multi-modelo con failover anti-429)
FREELLMAPI_BASE_URL = os.getenv("FREELLMAPI_BASE_URL", "").rstrip("/")
FREELLMAPI_API_KEY = os.getenv("FREELLMAPI_API_KEY", "freellmapi")
FREELLMAPI_MODEL = os.getenv("FREELLMAPI_MODEL", "default")

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
    
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Estado del sistema.")]))
    
    return contents

def _build_openai_messages(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Convierte el historial al formato estándar de mensajes de OpenAI/FreeLLMAPI/Groq."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        role = "user" if msg.get("role") == "user" else "assistant"
        content = msg.get("content", "").strip()
        if content:
            messages.append({"role": role, "content": content})
    return messages

async def _call_gemini_model(client: genai.Client, model: str, contents: List[types.Content], timeout: float = 12.0) -> str:
    """Ejecuta una llamada asíncrona a un modelo específico de Gemini con soporte nativo de Function Calling."""
    registry = get_skill_registry()
    tools = registry.get_gemini_tools()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.7,
        max_output_tokens=600,
        tools=[tools] if tools else None,
    )
    
    current_contents = list(contents)
    for turn in range(3):
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=current_contents,
                config=config,
            ),
            timeout=timeout
        )
        if not response:
            break
        
        if response.function_calls:
            logger.info("Gemini turno %d invocó %d habilidad(es): %s", 
                        turn + 1,
                        len(response.function_calls), 
                        [fc.name for fc in response.function_calls])
            
            tool_response_parts = []
            for fc in response.function_calls:
                skill_result = await registry.execute(fc.name, params=fc.args or {})
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": skill_result}
                    )
                )
                
            model_turn = response.candidates[0].content
            tool_turn = types.Content(role="user", parts=tool_response_parts)
            current_contents.extend([model_turn, tool_turn])
            continue

        if response.text:
            return response.text.strip()

    raise ValueError(f"El modelo {model} devolvió una respuesta vacía o no concluyó síntesis.")

async def _call_freellmapi_fallback(history: List[Dict[str, str]], timeout: float = 10.0) -> Optional[str]:
    """Llamada a FreeLLMAPI gateway (compatible con OpenAI) si está configurado en .env."""
    base_url = os.getenv("FREELLMAPI_BASE_URL", FREELLMAPI_BASE_URL).rstrip("/")
    if not base_url:
        return None

    api_key = os.getenv("FREELLMAPI_API_KEY", FREELLMAPI_API_KEY)
    model = os.getenv("FREELLMAPI_MODEL", FREELLMAPI_MODEL)
    messages = _build_openai_messages(history)
    endpoint = f"{base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.info("Enrutando directiva a FreeLLMAPI gateway (%s)...", base_url)
            resp = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
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
                    return choices[0]["message"].get("content", "").strip()
            else:
                logger.warning("FreeLLMAPI devolvió status %d: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Error conectando con FreeLLMAPI (%s): %s", endpoint, str(e))
    return None

async def _call_groq_fallback(history: List[Dict[str, str]], timeout: float = 8.0) -> Optional[str]:
    """Fallback 100% en la nube vía Groq API si está configurada."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return None

    messages = _build_openai_messages(history)

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
    Prioridad:
    1. Gemini Directo (3.5-flash-lite -> 3.6-flash -> 3.5-flash) con Function Calling local
    2. FreeLLMAPI Gateway (si FREELLMAPI_BASE_URL está configurado)
    3. Groq Cloud (si GROQ_API_KEY está configurada)
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

    # Fallback a FreeLLMAPI si está configurado
    freellm_reply = await _call_freellmapi_fallback(history)
    if freellm_reply:
        logger.info("Respuesta generada exitosamente mediante FreeLLMAPI Gateway.")
        return freellm_reply

    # Fallback a Groq Cloud si está configurado
    groq_reply = await _call_groq_fallback(history)
    if groq_reply:
        logger.info("Respuesta generada exitosamente mediante fallback en Groq.")
        return groq_reply

    # Si todo falló, devolver mensaje de diagnóstico con estética C.A.P.R.I.
    diag = " | ".join(errors_log)
    return (
        f"[SYSTEM ERROR]: Interrupción en el enlace neural con los servicios de nube.\n"
        f"Diagnóstico de fallos: {diag}.\n"
        f"Comprueba tu conexión de red o verifica tu clave en Google AI Studio o FreeLLMAPI."
    )

async def _stream_openai_compatible_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 14.0
) -> AsyncGenerator[str, None]:
    """Generador asíncrono para streaming Server-Sent Events (SSE) compatible con OpenAI/FreeLLMAPI/Groq."""
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 600
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise RuntimeError(f"HTTP {response.status_code}: {body.decode('utf-8')[:200]}")
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk_obj = json.loads(line[6:])
                        choices = chunk_obj.get("choices", [])
                        if choices:
                            delta_content = choices[0].get("delta", {}).get("content", "")
                            if delta_content:
                                yield delta_content
                    except Exception:
                        continue

async def stream_llm_response(history: List[Dict[str, str]]) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Motor de streaming en tiempo real para C.A.P.R.I.
    Emite eventos estructurados:
    • {'type': 'status', 'stage': '...', 'message': '...'}
    • {'type': 'skill_call', 'skill': '...', 'params': {...}}
    • {'type': 'skill_result', 'skill': '...', 'result': {...}}
    • {'type': 'token', 'delta': '...'}
    • {'type': 'done', 'full_response': '...'}
    """
    client = get_gemini_client()
    full_text = ""

    # 1. INTENTAR STREAMING CON GEMINI DIRECTO (con soporte de skills)
    if client:
        contents = _build_gemini_contents(history)
        registry = get_skill_registry()
        tools = registry.get_gemini_tools()

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=600,
            tools=[tools] if tools else None,
        )

        for model in GEMINI_MODELS:
            try:
                yield {"type": "status", "stage": "connecting", "message": f"Conectando a {model}..."}
                
                # Primero llamamos a generate_content para verificar si hay function_calls
                # o si podemos iniciar el streaming de texto directo
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config
                    ),
                    timeout=8.0
                )

                # Si Gemini invoca una o varias habilidades locales
                if resp and resp.function_calls:
                    tool_parts = []
                    for fc in resp.function_calls:
                        yield {
                            "type": "skill_call",
                            "skill": fc.name,
                            "params": fc.args or {},
                            "message": f"Activando ciberware '{fc.name}'..."
                        }
                        skill_res = await registry.execute(fc.name, params=fc.args or {})
                        yield {
                            "type": "skill_result",
                            "skill": fc.name,
                            "result": skill_res
                        }
                        tool_parts.append(
                            types.Part.from_function_response(name=fc.name, response={"result": skill_res})
                        )

                    # Ejecutar síntesis final con streaming
                    followup_contents = list(contents) + [
                        resp.candidates[0].content,
                        types.Content(role="user", parts=tool_parts)
                    ]

                    followup_stream = await client.aio.models.generate_content_stream(
                        model=model,
                        contents=followup_contents,
                        config=config
                    )
                    async for chunk in followup_stream:
                        if chunk.text:
                            full_text += chunk.text
                            yield {"type": "token", "delta": chunk.text}

                    yield {"type": "done", "full_response": full_text}
                    return

                # Si no hubo function calls, emitir el texto
                if resp and resp.text:
                    full_text = resp.text.strip()
                    # Simular streaming de tokens si ya vino completo
                    words = full_text.split(" ")
                    for i, w in enumerate(words):
                        delta = w + (" " if i < len(words) - 1 else "")
                        yield {"type": "token", "delta": delta}
                        await asyncio.sleep(0.015)
                    yield {"type": "done", "full_response": full_text}
                    return

            except Exception as e:
                logger.warning("Streaming en Gemini [%s] falló: %s", model, str(e))
                continue

    # 2. FALLBACK STREAMING CON FREELLMAPI (si está configurado)
    freellm_url = os.getenv("FREELLMAPI_BASE_URL", FREELLMAPI_BASE_URL).rstrip("/")
    if freellm_url:
        try:
            yield {"type": "status", "stage": "freellmapi", "message": "Enrutando flujo a FreeLLMAPI Gateway..."}
            messages = _build_openai_messages(history)
            api_key = os.getenv("FREELLMAPI_API_KEY", FREELLMAPI_API_KEY)
            model_name = os.getenv("FREELLMAPI_MODEL", FREELLMAPI_MODEL)
            async for delta in _stream_openai_compatible_endpoint(
                base_url=freellm_url,
                api_key=api_key,
                model=model_name,
                messages=messages
            ):
                full_text += delta
                yield {"type": "token", "delta": delta}

            yield {"type": "done", "full_response": full_text}
            return
        except Exception as e:
            logger.warning("Streaming con FreeLLMAPI falló: %s", str(e))

    # 3. FALLBACK STREAMING CON GROQ CLOUD (si está configurado)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            yield {"type": "status", "stage": "groq", "message": "Enrutando flujo a Groq Cloud..."}
            messages = _build_openai_messages(history)
            async for delta in _stream_openai_compatible_endpoint(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
                model="llama-3.3-70b-versatile",
                messages=messages
            ):
                full_text += delta
                yield {"type": "token", "delta": delta}

            yield {"type": "done", "full_response": full_text}
            return
        except Exception as e:
            logger.warning("Streaming con Groq falló: %s", str(e))

    # 4. ERROR TOTAL: EMITIR DIAGNÓSTICO
    fallback_msg = (
        "[SYSTEM ERROR]: No se pudo establecer enlace de streaming con ningún proveedor de IA. "
        "Verifica tu GEMINI_API_KEY o levanta FreeLLMAPI localmente."
    )
    yield {"type": "token", "delta": fallback_msg}
    yield {"type": "done", "full_response": fallback_msg}

