import sys
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest", "-platform", "offscreen"])
    return app


def test_animation_player_frame_advance(qapp):
    from src.desktop.shimeji import AnimationPlayer
    sheet = QPixmap("src/desktop/assets/idle_scaled.png")
    assert not sheet.isNull(), "idle_scaled.png debe existir y cargarse"

    player = AnimationPlayer(sheet, n_frames=10, fps=8.0, loop=True)
    assert player._frame_idx == 0

    # A 8 FPS, cada frame dura 125ms
    player.tick(125)
    assert player._frame_idx == 1

    # Avanzar hasta el final y verificar que el loop vuelve a 0
    player.tick(125 * 9)
    assert player._frame_idx == 0  # wrapped
    assert not player.finished


def test_animation_player_no_loop(qapp):
    from src.desktop.shimeji import AnimationPlayer
    sheet = QPixmap("src/desktop/assets/idle_scaled.png")
    player = AnimationPlayer(sheet, n_frames=10, fps=8.0, loop=False)
    player.tick(125 * 11)   # Más allá del último frame
    assert player.finished
    assert player._frame_idx == 9   # Fijado en el último frame


def test_load_animation_right_and_left(qapp):
    from src.desktop.shimeji import load_animation
    anim_r = load_animation("idle", 10, 8.0, True, "right")
    anim_l = load_animation("idle", 10, 8.0, True, "left")
    assert anim_r is not None, "idle derecha debe cargarse"
    assert anim_l is not None, "idle izquierda debe cargarse"
    # Frames deben ser distintos (mirrored)
    frame_r = anim_r.current_frame()
    frame_l = anim_l.current_frame()
    assert not frame_r.isNull()
    assert not frame_l.isNull()


def test_shimeji_state_machine(qapp):
    from src.desktop.shimeji import CapriShimeji

    s = CapriShimeji()
    assert s.state == "IDLE"
    assert s.is_running is True

    # IDLE → SCANNING
    s._transition("SCANNING", timer=30)
    assert s.state == "SCANNING"
    assert s.state_timer == 30

    # SCANNING → SLEEPING
    s._transition("SLEEPING")
    assert s.state == "SLEEPING"

    # Despertar → WAKING
    s._wake_if_sleeping()
    assert s.state == "WAKING"

    # GRINNING
    s._transition("GRINNING")
    assert s.state == "GRINNING"

    # Diálogo
    s.show_dialog("Test dialog", 50)
    assert s.dialog_text == "Test dialog"
    assert s.dialog_timer == 50

    # Pausa / reanudación
    s.toggle_pause()
    assert s.state == "PAUSED"
    s.toggle_pause()
    assert s.state == "IDLE"

    # Cierre
    s.close()
    assert s.is_running is False


def test_shimeji_all_animations_load(qapp):
    from src.desktop.shimeji import CapriShimeji
    s = CapriShimeji()
    for key in ["idle", "dangle", "glitch", "grin", "sleep", "wake"]:
        assert key in s.anims, f"Animación '{key}' debe estar registrada"
        assert s.anims[key]["right"] is not None, f"'{key}' right debe cargarse"
        assert s.anims[key]["left"] is not None, f"'{key}' left debe cargarse"
    s.close()
