import os
import logging
from typing import Dict, Any, Optional
from src.backend.voice.tts import CapriTTS
from src.backend.voice.stt import CapriSTT, extract_wake_word

logger = logging.getLogger("capri.voice.manager")

class VoiceManager:
    """
    Gestor centralizado del subsistema de voz de C.A.P.R.I.
    Controla el estado de silencio (Mute/Unmute), la detección del comando
    'Oye Capri', la síntesis vocal y la coordinación entre audio y LLM.
    """
    def __init__(self):
        self.tts = CapriTTS()
        self.stt = CapriSTT()
        # Por defecto inicia muteado por seguridad y privacidad del usuario
        self._is_muted: bool = True
        self._is_listening: bool = False

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    def toggle_mute(self) -> bool:
        """Alterna el estado de mute. Devuelve el nuevo estado de is_muted."""
        self._is_muted = not self._is_muted
        state_str = "MUTED (Silenciado)" if self._is_muted else "ACTIVO (Escuchando 'Oye Capri')"
        logger.info("Estado del micrófono de C.A.P.R.I. cambiado a: %s", state_str)
        return self._is_muted

    def set_muted(self, muted: bool):
        self._is_muted = muted
        logger.info("Micrófono establecido en: %s", "MUTED" if muted else "ACTIVO")

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_muted": self._is_muted,
            "is_listening": self._is_listening,
            "voice_es": self.tts.voice_es,
            "voice_en": self.tts.voice_en,
            "rate": self.tts.rate,
            "pitch": self.tts.pitch,
            "wake_words": ["Oye Capri", "Hey Capri", "Hola Capri"]
        }

    async def speak(self, text: str, lang: Optional[str] = None) -> bool:
        """Sintetiza la respuesta y la reproduce en los altavoces."""
        return await self.tts.speak(text, lang=lang)

    async def process_audio_file(self, file_path: str, require_wake_word: bool = True) -> Dict[str, Any]:
        """
        Procesa una pista de audio entrante:
        1. Si está muteado, descarta la orden.
        2. Transcribe con Groq Whisper / Gemini Audio.
        3. Evalúa si contiene la palabra de activación 'Oye Capri' (si require_wake_word=True).
        4. Devuelve el comando extraído listo para el LLM.
        """
        if self._is_muted:
            return {
                "triggered": False,
                "status": "muted",
                "message": "El micrófono de C.A.P.R.I. está actualmente silenciado (Mute)."
            }

        self._is_listening = True
        try:
            transcription = await self.stt.transcribe_file(file_path)
            if not transcription:
                return {
                    "triggered": False,
                    "status": "empty",
                    "message": "No se detectó habla inteligible en la grabación."
                }

            has_wake, command = extract_wake_word(transcription)

            if require_wake_word and not has_wake:
                return {
                    "triggered": False,
                    "status": "no_wake_word",
                    "raw_transcription": transcription,
                    "message": "No se detectó el comando de activación 'Oye Capri' / 'Hey Capri'."
                }

            target_cmd = command if has_wake else transcription
            if not target_cmd:
                target_cmd = "Hola Capri"

            return {
                "triggered": True,
                "status": "success",
                "wake_word_detected": has_wake,
                "raw_transcription": transcription,
                "command": target_cmd,
                "message": f"Directiva detectada: '{target_cmd}'"
            }
        finally:
            self._is_listening = False


# Singleton del VoiceManager
_default_voice_manager: Optional[VoiceManager] = None

def get_voice_manager() -> VoiceManager:
    global _default_voice_manager
    if _default_voice_manager is None:
        _default_voice_manager = VoiceManager()
    return _default_voice_manager
