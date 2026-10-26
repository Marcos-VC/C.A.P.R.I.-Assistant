import sys
import pytest
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    """Inicializa una instancia headless de QApplication para tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest", "-platform", "offscreen"])
    return app

def test_shimeji_initialization_and_states(qapp):
    from src.desktop.shimeji import CapriShimeji

    shimeji = CapriShimeji()

    assert shimeji.state in ("WALK_RIGHT", "IDLE", "WALK_LEFT")
    assert shimeji.is_running is True
    assert shimeji.win_w > 100
    assert shimeji.win_h > 200

    # Comprobar activación de diálogo
    shimeji.show_dialog("Test Cyberpunk", duration=10)
    assert shimeji.dialog_text == "Test Cyberpunk"
    assert shimeji.dialog_timer == 10

    # Comprobar toggle de pausa
    shimeji.toggle_pause()
    assert shimeji.state == "PAUSED"
    shimeji.toggle_pause()
    assert shimeji.state == "IDLE"

    # Comprobar cierre ordenado
    shimeji.close()
    assert shimeji.is_running is False
