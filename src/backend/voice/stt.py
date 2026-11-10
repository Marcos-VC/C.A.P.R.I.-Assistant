import os
import re
import shutil
import asyncio
import logging
import tempfile
from typing import Tuple, Optional, Union
import httpx
from src.backend.core.llm import get_gemini_client

logger = logging.getLogger("capri.voice.stt")

# Palabras de activación reconocidas en español e inglés
WAKE_WORDS = [
    r"\boye\s+capri\b",
    r"\bhey\s+capri\b",
    r"\bhola\s+capri\b",
    r"\bhi\s+capri\b",
    r"\bok\s+capri\b",
    r"\bhello\s+capri\b",
    r"\bey\s+capri\b",
    r"\bcapri\b",
]

def extract_wake_word(text: str) -> Tuple[bool, str]:
    """
    Analiza si el texto transcrito contiene la palabra clave 'Oye Capri' / 'Hey Capri'.
    Devuelve (activado: bool, comando_limpio: str).
    """
    clean = text.strip()
    for pattern in WAKE_WORDS:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            # Extraer la orden que sigue a la palabra de activación
            start, end = match.span()
            command = (clean[:start] + " " + clean[end:]).strip()
            # Limpiar comas o signos de puntuación iniciales
            command = re.sub(r"^[\s,;:\.¿\?!]+", "", command).strip()
            return True, command
    return False, clean


class CapriSTT:
    """
    Motor de reconocimiento de voz (Speech-to-Text) y detección de Wake Word.
    Transcribe audio de micrófono utilizando Groq Whisper API o Gemini Audio Multimodal.
    """
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")

    async def record_audio_clip(self, duration_seconds: float = 4.0, output_path: Optional[str] = None) -> Optional[str]:
        """
        Graba un fragmento de audio desde el micrófono usando arecord (ALSA/PipeWire).
        """
        if not shutil.which("arecord"):
            logger.warning("El comando 'arecord' no está disponible para grabación en el sistema.")
            return None

        target = output_path or os.path.join(
            tempfile.gettempdir(),
            f"capri_mic_{os.getpid()}_{int(asyncio.get_event_loop().time() * 1000)}.wav"
        )

        try:
            dur_int = max(1, int(round(duration_seconds)))
            proc = await asyncio.create_subprocess_exec(
                "arecord", "-q", "-d", str(dur_int), "-r", "16000", "-c", "1", "-f", "S16_LE", target,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            if proc.returncode == 0 and os.path.exists(target) and os.path.getsize(target) > 0:
                return target
            return None
        except Exception as e:
            logger.error("Error grabando audio con arecord: %s", str(e))
            return None

    async def transcribe_with_groq(self, file_path: str, lang: Optional[str] = None) -> Optional[str]:
        """Transcribe archivo de audio con Groq Whisper API (latencia <150ms)."""
        api_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            return None

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, "audio/wav")}
                    data = {
                        "model": "whisper-large-v3-turbo",
                        "response_format": "json",
                        "temperature": "0.0"
                    }
                    if lang:
                        data["language"] = lang

                    resp = await client.post(url, headers=headers, files=files, data=data)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        text = res_json.get("text", "").strip()
                        logger.info("Transcripción Groq Whisper exitosa: '%s'", text)
                        return text
                    else:
                        logger.warning("Groq Whisper devolvió %d: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.warning("Error conectando con Groq Whisper: %s", str(e))
        return None

    async def transcribe_with_gemini(self, file_path: str) -> Optional[str]:
        """Transcribe archivo de audio usando Gemini Multimodal Audio."""
        client = get_gemini_client()
        if not client:
            return None

        try:
            from google.genai import types
            with open(file_path, "rb") as f:
                audio_bytes = f.read()

            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
            prompt_part = types.Part.from_text(
                text="Transcribe de forma literal y exacta lo que se dice en este audio, ya sea en español o en inglés. "
                     "Devuelve únicamente la transcripción sin comentarios ni explicaciones adicionales."
            )

            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=[audio_part, prompt_part]
                ),
                timeout=10.0
            )
            if resp and resp.text:
                text = resp.text.strip()
                logger.info("Transcripción Gemini Audio exitosa: '%s'", text)
                return text
        except Exception as e:
            logger.warning("Error transcribiendo con Gemini Audio: %s", str(e))
        return None

    async def transcribe_file(self, file_path: str, lang: Optional[str] = None) -> str:
        """
        Transcribe un archivo de audio con cascada de fallback (Groq Whisper -> Gemini Audio).
        """
        # 1. Intentar Groq Whisper (ultra-rápido)
        text = await self.transcribe_with_groq(file_path, lang=lang)
        if text:
            return text

        # 2. Intentar Gemini Multimodal
        text = await self.transcribe_with_gemini(file_path)
        if text:
            return text

        return ""
