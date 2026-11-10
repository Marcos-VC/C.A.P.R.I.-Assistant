import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.voice import CapriTTS, CapriSTT, extract_wake_word, get_voice_manager

client = TestClient(app)

# ──────────────────────────────────────────────────────────────────────────────
# 1. WAKE WORD DETECTION
# ──────────────────────────────────────────────────────────────────────────────
def test_wake_word_extraction_spanish():
    triggered, cmd = extract_wake_word("Oye Capri, ¿cuánta batería me queda?")
    assert triggered is True
    assert "cuánta batería me queda" in cmd

    triggered2, cmd2 = extract_wake_word("Hola Capri, dime el estado del sistema")
    assert triggered2 is True
    assert cmd2 == "dime el estado del sistema"

    triggered3, cmd3 = extract_wake_word("capri status")
    assert triggered3 is True
    assert cmd3 == "status"


def test_wake_word_extraction_english():
    triggered, cmd = extract_wake_word("Hey Capri, what is my current CPU usage?")
    assert triggered is True
    assert cmd == "what is my current CPU usage?"

    triggered2, cmd2 = extract_wake_word("Hi Capri, show my git status")
    assert triggered2 is True
    assert cmd2 == "show my git status"


def test_wake_word_extraction_negative():
    triggered, cmd = extract_wake_word("Esto es una frase sin la palabra clave de activación.")
    assert triggered is False
    assert cmd == "Esto es una frase sin la palabra clave de activación."


# ──────────────────────────────────────────────────────────────────────────────
# 2. TTS TEXT PROCESSING & LANGUAGE DETECTION
# ──────────────────────────────────────────────────────────────────────────────
def test_tts_clean_text():
    tts = CapriTTS()
    raw = "**Hola choom!** Este es un `código` con [enlace](https://cyberpunk.net) y ```bloque de código```."
    clean = tts.clean_text_for_speech(raw)
    assert "**" not in clean
    assert "`" not in clean
    assert "https://" not in clean
    assert "Hola choom!" in clean


def test_tts_language_detection():
    tts = CapriTTS()
    assert tts.detect_language("Hola choom, el sistema está en estado nova.") == "es"
    assert tts.detect_language("Hey choom, what are the system specs today?") == "en"

    # Verificación de asignación de voz según idioma
    voice_es = tts.get_voice_for_text("Buenos días Night City", lang="es")
    voice_en = tts.get_voice_for_text("Good morning Night City", lang="en")
    assert "es-" in voice_es or "Elvira" in voice_es
    assert "en-" in voice_en or "Ana" in voice_en


# ──────────────────────────────────────────────────────────────────────────────
# 3. VOICE MANAGER MUTE STATE
# ──────────────────────────────────────────────────────────────────────────────
def test_voice_manager_mute_state():
    vm = get_voice_manager()
    vm.set_muted(True)
    assert vm.is_muted is True

    new_state = vm.toggle_mute()
    assert new_state is False
    assert vm.is_muted is False

    vm.set_muted(True)
    assert vm.is_muted is True


@pytest.mark.anyio
async def test_voice_manager_process_when_muted():
    vm = get_voice_manager()
    vm.set_muted(True)
    res = await vm.process_audio_file("fake_audio.wav")
    assert res["triggered"] is False
    assert res["status"] == "muted"


@pytest.mark.anyio
async def test_voice_manager_process_wake_word():
    vm = get_voice_manager()
    vm.set_muted(False)

    with patch.object(vm.stt, "transcribe_file", new_callable=AsyncMock) as mock_stt:
        mock_stt.return_value = "Oye Capri, revisa el portapapeles"
        res = await vm.process_audio_file("fake_audio.wav", require_wake_word=True)
        assert res["triggered"] is True
        assert res["wake_word_detected"] is True
        assert "portapapeles" in res["command"]

    vm.set_muted(True)


# ──────────────────────────────────────────────────────────────────────────────
# 4. REST API ENDPOINTS DE VOZ
# ──────────────────────────────────────────────────────────────────────────────
def test_voice_api_status_and_toggle():
    # 1. Status
    resp = client.get("/api/v1/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_muted" in data
    assert "wake_words" in data

    # 2. Toggle mute
    resp_toggle = client.post("/api/v1/voice/toggle_mute")
    assert resp_toggle.status_code == 200
    assert "is_muted" in resp_toggle.json()
    assert "message" in resp_toggle.json()


@pytest.mark.anyio
def test_voice_api_speak_mocked():
    with patch("src.backend.voice.voice_manager.VoiceManager.speak", new_callable=AsyncMock) as mock_spk:
        mock_spk.return_value = True
        resp = client.post("/api/v1/voice/speak", json={"text": "Directiva recibida, choomba."})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["spoken"] is True
