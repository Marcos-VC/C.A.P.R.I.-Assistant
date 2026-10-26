import pytest
from unittest.mock import patch, MagicMock

@patch("tkinter.Tk")
def test_shimeji_initialization_and_states(mock_tk_class):
    mock_root = MagicMock()
    mock_root.winfo_screenwidth.return_value = 1920
    mock_root.winfo_screenheight.return_value = 1080
    mock_tk_class.return_value = mock_root

    from src.desktop.shimeji import CapriShimeji

    shimeji = CapriShimeji()

    assert shimeji.screen_width == 1920
    assert shimeji.screen_height == 1080
    assert shimeji.x == 960
    assert shimeji.state in ("WALK_RIGHT", "IDLE", "WALK_LEFT")
    assert shimeji.is_running is True

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

