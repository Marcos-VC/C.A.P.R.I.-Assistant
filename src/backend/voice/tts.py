import os
import re
import shutil
import asyncio
import logging
import tempfile
from typing import Optional, Dict, Any

logger = logging.getLogger("capri.voice.tts")

class CapriTTS:
    """
    Motor de síntesis de voz (Text-to-Speech) para C.A.P.R.I.
    Utiliza Microsoft Edge Neural TTS para una voz ultra-natural, expresiva y de alta calidad.
    Configurada para imitar el tono enérgico, juvenil y callejero de Capri (Cyberpunk: Edgerunners).
    """
    def __init__(
        self,
        voice_es: Optional[str] = None,
        voice_en: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        volume: Optional[str] = None,
    ):
        # Voces por defecto: juveniles, ágiles y con personalidad
        self.voice_es = voice_es or os.getenv("CAPRI_VOICE_ES", "es-ES-ElviraNeural")
        self.voice_en = voice_en or os.getenv("CAPRI_VOICE_EN", "en-US-AnaNeural")
        
        # Moduladores para el timbre característico de Capri (Edgerunner)
        # Pitch ligeramente elevado (+8Hz) y velocidad dinámica (+5%)
        self.rate = rate or os.getenv("CAPRI_VOICE_RATE", "+5%")
        self.pitch = pitch or os.getenv("CAPRI_VOICE_PITCH", "+8Hz")
        self.volume = volume or os.getenv("CAPRI_VOICE_VOLUME", "+0%")

    def detect_language(self, text: str) -> str:
        """
        Detecta si el texto está principalmente en inglés o español
        mediante heurística de palabras clave comunes.
        """
        clean = text.lower()
        en_words = {"the", "is", "are", "you", "and", "this", "that", "what", "with", "from", "system", "offline", "online"}
        es_words = {"el", "la", "los", "las", "es", "está", "que", "para", "por", "sistema", "choom", "ciberware", "cromo"}
        
        tokens = set(re.findall(r"\b[a-záéíóúñ]+\b", clean))
        en_score = len(tokens.intersection(en_words))
        es_score = len(tokens.intersection(es_words))
        
        return "en" if en_score > es_score else "es"

    def clean_text_for_speech(self, text: str) -> str:
        """
        Limpia marcado Markdown, código, URLs y emojis para una locución fluida.
        """
        # Eliminar bloques de código ```...```
        cleaned = re.sub(r"```[\s\S]*?```", " [código ejecutado] ", text)
        # Eliminar código en línea `...`
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        # Eliminar asteriscos de negrita/cursiva **texto** o *texto*
        cleaned = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", cleaned)
        # Eliminar enlaces markdown [texto](url)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        # Eliminar URLs directas
        cleaned = re.sub(r"https?://\S+", " enlace ", cleaned)
        # Eliminar encabezados # ## ###
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
        # Eliminar viñetas
        cleaned = re.sub(r"^[\*\-•]\s+", "", cleaned, flags=re.MULTILINE)
        # Normalizar espacios
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def get_voice_for_text(self, text: str, lang: Optional[str] = None) -> str:
        target_lang = lang or self.detect_language(text)
        return self.voice_en if target_lang == "en" else self.voice_es

    async def generate_speech_file(self, text: str, output_path: str, lang: Optional[str] = None) -> str:
        """
        Genera un archivo de audio MP3 con la voz de Capri usando edge-tts.
        """
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("El paquete 'edge-tts' no está instalado en el entorno.")

        spoken_text = self.clean_text_for_speech(text)
        if not spoken_text:
            spoken_text = "Afirmativo, choom."

        voice = self.get_voice_for_text(spoken_text, lang=lang)
        logger.info("Sintetizando voz de Capri [%s] (pitch=%s, rate=%s): '%s...'", 
                    voice, self.pitch, self.rate, spoken_text[:40])

        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume
        )
        await communicate.save(output_path)
        return output_path

    async def speak(self, text: str, lang: Optional[str] = None) -> bool:
        """
        Sintetiza y reproduce el audio directamente a través del subsistema PipeWire/GStreamer.
        """
        spoken_text = self.clean_text_for_speech(text)
        if not spoken_text:
            return False

        temp_audio = os.path.join(tempfile.gettempdir(), f"capri_tts_{os.getpid()}_{asyncio.get_event_loop().time():.0f}.mp3")
        try:
            await self.generate_speech_file(spoken_text, temp_audio, lang=lang)
            if not os.path.exists(temp_audio) or os.path.getsize(temp_audio) == 0:
                return False

            # Reproducir audio con reproductor nativo
            # 1. Probar gst-play-1.0 (GStreamer nativo en GNOME/Ubuntu)
            if shutil.which("gst-play-1.0"):
                proc = await asyncio.create_subprocess_exec(
                    "gst-play-1.0", "--no-interactive", temp_audio,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.communicate()
                return proc.returncode == 0

            # 2. Probar pw-play o paplay
            for player in ["pw-play", "paplay", "mpv", "ffplay"]:
                if shutil.which(player):
                    proc = await asyncio.create_subprocess_exec(
                        player, temp_audio,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await proc.communicate()
                    return proc.returncode == 0

            logger.warning("No se encontró reproductor de audio compatible en el sistema.")
            return False

        except Exception as e:
            logger.error("Error al sintetizar o reproducir voz de Capri: %s", str(e))
            return False
        finally:
            if os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass
