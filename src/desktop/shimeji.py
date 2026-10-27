"""
C.A.P.R.I. Desktop Shimeji — Cyberpunk: Edgerunners Edition
============================================================
Mascota de escritorio animada, 100% transparente y siempre-al-frente.
Incluye Mini-Consola Táctica Flotante para interactuar por texto directamente
desde el escritorio sin necesidad de abrir el navegador.
Física completa: gravedad, arrastre, patrulla autónoma y máquina de estados.
"""
import os
import sys
import math
import random
import json
import urllib.request
import webbrowser
import threading
from typing import Optional, Dict, List

# ── Fix Wayland: forzar XWayland para obtener posicionamiento global y topmost ──
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_QPA_PLATFORMTHEME"] = ""

from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QLineEdit
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QAction

# Directorio de assets gráficos
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

FRAME_H = 220         # Altura estándar escalada de los sprites
FRAME_W = 137         # Anchura estándar escalada (240 * 220 / 384 = 137.5 -> 137)
DIALOG_MARGIN = 48    # Espacio sobre el sprite para el bocadillo de diálogo multi-línea


# ──────────────────────────────────────────────────────────────────────────────
# MINI-CONSOLA TÁCTICA FLOTANTE
# ──────────────────────────────────────────────────────────────────────────────
class CyberCommandConsole(QLineEdit):
    """
    Mini-consola táctica flotante cyberpunk para enviar directivas a C.A.P.R.I.
    desde cualquier ventana del escritorio sin necesidad de abrir el navegador.
    """
    def __init__(self, submit_callback):
        super().__init__()
        self.submit_callback = submit_callback
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setStyleSheet("""
            QLineEdit {
                background-color: #0d0f12;
                color: #00ff66;
                border: 2px solid #00e5ff;
                border-radius: 4px;
                padding: 5px 10px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                selection-background-color: #00e5ff;
                selection-color: #0d0f12;
            }
            QLineEdit:focus {
                border: 2px solid #00ff66;
            }
        """)
        self.setPlaceholderText("[ > Directiva táctica a Capri... ]")
        self.resize(270, 34)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            txt = self.text().strip()
            self.hide()
            self.clear()
            if txt:
                self.submit_callback(txt)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # Auto-ocultar si el usuario pulsa en otra ventana
        self.hide()
        super().focusOutEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# MOTOR DE ANIMACIÓN
# ──────────────────────────────────────────────────────────────────────────────
class AnimationPlayer:
    """
    Reproduce animaciones frame-a-frame desde un spritesheet pre-escalado.
    Cada hoja contiene frames de ancho frame_w y alto frame_h dispuestos en horizontal.
    """
    def __init__(self, sheet: QPixmap, n_frames: int, fps: float = 8.0, loop: bool = True, frame_w: int = 137, frame_h: int = 220):
        self.sheet = sheet
        self.n_frames = n_frames
        self.frame_duration = int(1000 / fps)   # ms por frame
        self.loop = loop
        self.frame_w = frame_w
        self.frame_h = frame_h
        self._frame_idx = 0
        self._elapsed = 0
        self.finished = False

    def tick(self, delta_ms: int):
        """Avanza la animación según el tiempo transcurrido (ms)."""
        if self.finished:
            return
        self._elapsed += delta_ms
        while self._elapsed >= self.frame_duration:
            self._elapsed -= self.frame_duration
            self._frame_idx += 1
            if self._frame_idx >= self.n_frames:
                if self.loop:
                    self._frame_idx = 0
                else:
                    self._frame_idx = self.n_frames - 1
                    self.finished = True
                    return

    def reset(self):
        self._frame_idx = 0
        self._elapsed = 0
        self.finished = False

    def current_frame(self) -> QPixmap:
        if self.sheet.isNull():
            return self.sheet
        x = self._frame_idx * self.frame_w
        return self.sheet.copy(x, 0, self.frame_w, self.frame_h)


def load_animation(name: str, n_frames: int, fps: float = 8.0,
                   loop: bool = True, facing: str = "right",
                   frame_w: int = 137, frame_h: int = 220) -> Optional[AnimationPlayer]:
    """Carga un spritesheet escalado desde assets/ y devuelve un AnimationPlayer."""
    suffix = "_left_scaled" if facing == "left" else "_scaled"
    path = os.path.join(ASSETS_DIR, f"{name}{suffix}.png")
    if not os.path.exists(path):
        path = os.path.join(ASSETS_DIR, f"{name}.png")
    if not os.path.exists(path):
        return None
    sheet = QPixmap(path)
    if sheet.isNull():
        return None
    return AnimationPlayer(sheet, n_frames, fps, loop, frame_w, frame_h)


# ──────────────────────────────────────────────────────────────────────────────
# SHIMEJI PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
class CapriShimeji(QWidget):
    ANIM_DEF = {
        "idle":    ("idle",         16,  8.0, True,  137, 220),
        "dangle":  ("dangle",       24, 12.0, True,  137, 220),
        "glitch":  ("glitch",       10, 10.0, True,  137, 220),
        "grin":    ("grin",         16, 10.0, False, 137, 220),
        "sleep":   ("sleep",        16,  5.0, True,  137, 220),
        "wake":    ("wake",         13, 10.0, False, 137, 220),
        "blink":   ("blink",         4,  4.0, False, 137, 220),
        "perch":   ("perch",        16,  8.0, True,  220, 220),
    }

    TICK_MS = 25   # 40 FPS
    SLEEP_AFTER = 40 * 60 * 3   # 3 minutos de inactividad

    def __init__(self):
        super().__init__()

        # ── Ventana sin marcos, transparente, siempre encima ──────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # ── Dimensiones (anchura suficiente para bocadillos multi-línea) ──────
        self.win_w = 260
        self.win_h = FRAME_H + DIALOG_MARGIN
        self.resize(self.win_w, self.win_h)

        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.screen_width = geo.width()
        self.screen_height = geo.height()

        # ── Física y posición ─────────────────────────────────────────────────
        self.floor_y = self.screen_height - self.win_h - 44
        self.pos_x: float = float(self.screen_width // 2 - self.win_w // 2)
        self.pos_y: float = float(self.floor_y)
        self.vx: float = 2.0
        self.vy: float = 0.0
        self.gravity: float = 1.4

        # ── Estado de la máquina ──────────────────────────────────────────────
        self.state: str = "IDLE"
        self.facing: str = "right"
        self.state_timer: int = 0
        self.idle_ticks: int = 0
        self.is_running: bool = True

        # ── Diálogos ──────────────────────────────────────────────────────────
        self.dialog_text: Optional[str] = None
        self.dialog_timer: int = 0

        # ── Backend ───────────────────────────────────────────────────────────
        self.backend_online: bool = False

        # ── Arrastre con ratón ────────────────────────────────────────────────
        self.drag_offset = QPoint()
        self.press_pos = QPoint()
        self.is_dragging: bool = False

        # ── Consola de comandos ───────────────────────────────────────────────
        self.console: Optional[CyberCommandConsole] = None

        # ── Cargar animaciones ────────────────────────────────────────────────
        self.anims: Dict[str, Dict[str, Optional[AnimationPlayer]]] = {}
        self._load_all_animations()
        self.current_anim: Optional[AnimationPlayer] = self._get_anim("idle")

        # ── UI ────────────────────────────────────────────────────────────────
        self._setup_context_menu()
        self.move(int(self.pos_x), int(self.pos_y))

        # ── Timers ────────────────────────────────────────────────────────────
        self.game_timer = QTimer(self)
        self.game_timer.timeout.connect(self.game_loop)
        self.game_timer.start(self.TICK_MS)

        self.check_backend_health()

    # ── Carga de sprites ──────────────────────────────────────────────────────
    def _load_all_animations(self):
        for key, (sheet, n, fps, loop, fw, fh) in self.ANIM_DEF.items():
            self.anims[key] = {
                "right": load_animation(sheet, n, fps, loop, "right", fw, fh),
                "left":  load_animation(sheet, n, fps, loop, "left", fw, fh),
            }

    def _get_anim(self, key: str) -> Optional[AnimationPlayer]:
        group = self.anims.get(key, {})
        anim = group.get(self.facing) or group.get("right")
        if anim:
            anim.reset()
        return anim

    # ── Menú contextual ───────────────────────────────────────────────────────
    def _setup_context_menu(self):
        self.menu = QMenu(self)
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #161920;
                color: #c5d1de;
                border: 1px solid #00e5ff;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                padding: 4px;
            }
            QMenu::item:selected { background-color: #00e5ff; color: #0d0f12; }
        """)
        def act(label, slot):
            a = QAction(label, self)
            a.triggered.connect(slot)
            self.menu.addAction(a)

        act("💬 Enviar directiva...", self.open_console)
        act("⚡ Abrir C.A.P.R.I. HUD", self.open_hud)
        act("📊 Telemetría del Sistema", self.query_system_status)
        self.menu.addSeparator()
        act("⏸ Pausar / Reanudar", self.toggle_pause)
        act("😴 Dormir ahora", lambda: self._transition("SLEEPING"))
        act("❌ Desactivar Shimeji", self.close)

    # ── Transiciones de estado ────────────────────────────────────────────────
    def _transition(self, new_state: str, timer: int = 0):
        self.state = new_state
        self.state_timer = timer
        self.idle_ticks = 0

        state_to_anim = {
            "IDLE":       "idle",
            "WALK_RIGHT": "idle",
            "WALK_LEFT":  "idle",
            "FALLING":    "dangle",
            "DRAGGED":    "dangle",
            "SCANNING":   "glitch",
            "SLEEPING":   "sleep",
            "WAKING":     "wake",
            "GRINNING":   "grin",
        }
        anim_key = state_to_anim.get(new_state, "idle")
        self.current_anim = self._get_anim(anim_key)

    # ── Mini-Consola Táctica Flotante ─────────────────────────────────────────
    def open_console(self):
        """Abre la barra de entrada de comandos táctica en el escritorio."""
        if self.console is None:
            self.console = CyberCommandConsole(self.send_directive)

        # Posicionar la consola justo debajo de Capri o encima según espacio
        con_w = 270
        con_h = 34
        con_x = int(self.pos_x + (self.win_w - con_w) // 2)
        con_x = max(10, min(self.screen_width - con_w - 10, con_x))

        # Intentar situar encima del bocadillo; si no cabe, abajo
        con_y = int(self.pos_y - con_h - 6)
        if con_y < 30:
            con_y = int(self.pos_y + self.win_h + 4)

        self.console.move(con_x, con_y)
        self.console.show()
        self.console.raise_()
        self.console.activateWindow()
        self.console.setFocus()
        self._transition("IDLE", timer=999)  # Pausar patrulla mientras escribe

    def send_directive(self, text: str):
        """Envía la orden ingresada al endpoint /api/v1/chat del backend."""
        self.show_dialog("Procesando directiva...", duration=240)
        self._transition("SCANNING", timer=200)

        def _worker():
            try:
                payload = json.dumps({
                    "session_id": "desktop_shimeji_session",
                    "message": text
                }).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/v1/chat",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Capri-Shimeji/2.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=12.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw_reply = data.get("response", "").strip()

                    # Limpiar asteriscos y formatear resumen para el bocadillo
                    clean = raw_reply.replace("**", "").replace("*", "")
                    lines = [l.strip() for l in clean.split("\n") if l.strip()]
                    summary = " ".join(lines[:2]) if lines else "Directiva completada."
                    if len(summary) > 130:
                        summary = summary[:127] + "..."

                    def _success_ui():
                        self.show_dialog(summary, duration=320)
                        self._transition("GRINNING")

                    QTimer.singleShot(0, _success_ui)

            except Exception:
                def _fail_ui():
                    self.show_dialog("Error: Backend offline", duration=180)
                    self._transition("IDLE")
                QTimer.singleShot(0, _fail_ui)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Interacción del ratón ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        self._wake_if_sleeping()
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.press_pos = event.globalPosition().toPoint()
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.state not in ("SLEEPING", "WAKING"):
                self.facing = "right"
                self._transition("DRAGGED")
            self.vy = 0.0
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            # Clic central: abrir consola táctica
            self.open_console()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_offset
            self.pos_x = float(new_pos.x())
            self.pos_y = float(new_pos.y())
            self.move(int(self.pos_x), int(self.pos_y))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragged = (event.globalPosition().toPoint() - self.press_pos).manhattanLength() > 6
            self.is_dragging = False

            if not was_dragged:
                # Clic simple sobre Capri -> Abrir consola táctica
                self.open_console()
            elif self.pos_y < self.floor_y:
                self._transition("FALLING")
            else:
                self.pos_y = self.floor_y
                self._transition("IDLE", timer=60)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Doble clic abre el HUD web
            if self.console and self.console.isVisible():
                self.console.hide()
            self.open_hud()

    def open_hud(self):
        self.show_dialog("Enlace Neural HUD...")
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_pause(self):
        if self.state == "PAUSED":
            self._transition("IDLE", timer=40)
            self.show_dialog("Sistema reactivado")
        else:
            self.state = "PAUSED"
            self.show_dialog("Modo centinela")

    def show_dialog(self, text: str, duration: int = 180):
        self.dialog_text = text
        self.dialog_timer = duration
        self.update()

    # ── Backend ───────────────────────────────────────────────────────────────
    def check_backend_health(self):
        def _check():
            was_online = self.backend_online
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/health",
                    headers={"User-Agent": "Capri-Shimeji/2.0"}
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    self.backend_online = resp.status == 200
            except Exception:
                self.backend_online = False
            
            if self.backend_online and not was_online:
                self.show_dialog("Neural link OK")
                self._transition("GRINNING")
            if self.is_running:
                QTimer.singleShot(5000, self.check_backend_health)

        threading.Thread(target=_check, daemon=True).start()

    def query_system_status(self):
        def _query():
            try:
                payload = json.dumps({"skill_name": "system_monitor"}).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/v1/skills/execute",
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Capri-Shimeji/2.0"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    data = json.loads(resp.read())
                    result = data.get("result", {})
                    mem_info = result.get("memory_info", "")
                    lines = mem_info.split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        free = parts[6] if len(parts) > 6 else parts[3]
                        self.show_dialog(f"RAM libre: {free}")
                    else:
                        self.show_dialog("Sistemas nominales")
            except Exception:
                self.show_dialog("Error de enlace")

        threading.Thread(target=_query, daemon=True).start()

    # ── Bucle de juego ────────────────────────────────────────────────────────
    def game_loop(self):
        if not self.is_running or self.state == "PAUSED":
            return

        # Avanzar animación
        if self.current_anim:
            self.current_anim.tick(self.TICK_MS)

        # Temporizador de diálogo
        if self.dialog_timer > 0:
            self.dialog_timer -= 1
            if self.dialog_timer <= 0:
                self.dialog_text = None

        # ── Máquina de estados ────────────────────────────────────────────────
        s = self.state

        if s == "FALLING":
            self.vy += self.gravity
            self.pos_y += self.vy
            if self.pos_y >= self.floor_y:
                self.pos_y = self.floor_y
                self.vy = 0.0
                self._transition("IDLE", timer=50)
            self._sync_position()

        elif s == "WALK_RIGHT":
            self.facing = "right"
            self.pos_x += self.vx
            if self.pos_x >= self.screen_width - self.win_w - 20:
                self.facing = "left"
                self._transition("WALK_LEFT")
            elif random.random() < 0.007:
                self._transition("IDLE", timer=random.randint(40, 140))
            self._sync_position()
            self.idle_ticks = 0

        elif s == "WALK_LEFT":
            self.facing = "left"
            self.pos_x -= self.vx
            if self.pos_x <= 20:
                self.facing = "right"
                self._transition("WALK_RIGHT")
            elif random.random() < 0.007:
                self._transition("IDLE", timer=random.randint(40, 140))
            self._sync_position()
            self.idle_ticks = 0

        elif s == "IDLE":
            self.idle_ticks += 1
            self.state_timer -= 1
            if self.idle_ticks >= self.SLEEP_AFTER:
                self._transition("SLEEPING")
            elif self.state_timer <= 0:
                decision = random.random()
                if decision < 0.46:
                    self.facing = "right"
                    self._transition("WALK_RIGHT")
                elif decision < 0.92:
                    self.facing = "left"
                    self._transition("WALK_LEFT")
                elif decision < 0.97:
                    self._transition("SCANNING", timer=80)
                else:
                    self._transition("IDLE", timer=random.randint(60, 180))

        elif s == "SCANNING":
            self.state_timer -= 1
            if self.state_timer <= 0:
                self._transition("IDLE", timer=50)

        elif s == "SLEEPING":
            self.idle_ticks += 1

        elif s == "WAKING":
            if self.current_anim and self.current_anim.finished:
                self._transition("IDLE", timer=60)

        elif s == "GRINNING":
            if self.current_anim and self.current_anim.finished:
                self._transition("IDLE", timer=60)

        self.update()

    def _sync_position(self):
        self.pos_x = max(0.0, min(float(self.screen_width - self.win_w), self.pos_x))
        self.pos_y = max(0.0, min(float(self.screen_height - self.win_h), self.pos_y))
        self.move(int(self.pos_x), int(self.pos_y))

    def _wake_if_sleeping(self):
        if self.state == "SLEEPING":
            self.idle_ticks = 0
            self._transition("WAKING")

    # ── Pintado ───────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Frame actual de la animación
        frame = self.current_anim.current_frame() if self.current_anim else QPixmap()

        # Flotación suave en estados tranquilos
        float_y = 0
        if self.state in ("IDLE", "SCANNING", "SLEEPING"):
            float_y = int(math.sin(self.idle_ticks * 0.1) * 3)

        # Micro-glitch característico de Capri
        gx = 0
        if self.state in ("SCANNING", "GRINNING") and random.random() < 0.06:
            gx = random.choice([-4, 4])

        fw = frame.width() if not frame.isNull() else FRAME_W
        draw_x = (self.win_w - fw) // 2 + gx
        draw_y = DIALOG_MARGIN + float_y

        # Dibujar sprite único
        if not frame.isNull():
            painter.drawPixmap(draw_x, draw_y, frame)
            if gx != 0:
                pen = QPen(QColor(0, 229, 255, 160), 1)
                painter.setPen(pen)
                ly = draw_y + random.randint(10, FRAME_H - 10)
                painter.drawLine(draw_x - 10, ly, draw_x + fw + 10, ly)

        # LED de estado del backend
        led = QColor(0, 255, 102, 220) if self.backend_online else QColor(0, 229, 255, 140)
        painter.setBrush(led)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.win_w // 2 - 4, self.win_h - 8, 8, 8)

        # Bocadillo de diálogo multi-línea
        if self.dialog_text:
            font = QFont("Courier New", 8, QFont.Weight.Bold)
            painter.setFont(font)
            text = self.dialog_text
            text_w = min(self.win_w - 12, max(80, len(text) * 7 + 16))
            bubble_h = 36 if len(text) > 28 else 22
            bx = (self.win_w - text_w) // 2
            by = max(4, DIALOG_MARGIN - bubble_h - 4)

            painter.setBrush(QColor(5, 7, 10, 235))
            painter.setPen(QPen(QColor(0, 255, 102), 1))
            painter.drawRoundedRect(bx, by, text_w, bubble_h, 4, 4)
            painter.setPen(QColor(0, 255, 102))
            text_rect = QRect(bx + 4, by + 2, text_w - 8, bubble_h - 4)
            painter.drawText(text_rect, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter), text)

    # ── Cierre ordenado ───────────────────────────────────────────────────────
    def close(self):
        self.is_running = False
        if hasattr(self, "console") and self.console:
            self.console.close()
        if hasattr(self, "game_timer") and self.game_timer.isActive():
            self.game_timer.stop()
        super().close()


# ── Entry point ───────────────────────────────────────────────────────────────
def run():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    shimeji = CapriShimeji()
    shimeji.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
