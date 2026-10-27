"""
C.A.P.R.I. Desktop Shimeji — Cyberpunk: Edgerunners Edition
============================================================
Mascota de escritorio animada, 100% transparente y siempre-al-frente.
Motor de sprites con spritesheets multi-frame para animaciones fluidas.
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

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QAction

# Directorio de assets gráficos
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

FRAME_SIZE = 220      # Tamaño de cada frame en los scaled spritesheets
DIALOG_MARGIN = 38    # Espacio sobre el sprite para el bocadillo de diálogo


# ──────────────────────────────────────────────────────────────────────────────
# MOTOR DE ANIMACIÓN
# ──────────────────────────────────────────────────────────────────────────────
class AnimationPlayer:
    """
    Reproduce animaciones frame-a-frame desde un spritesheet pre-escalado.
    Cada hoja tiene frames de FRAME_SIZE×FRAME_SIZE px dispuestos en horizontal.
    """
    def __init__(self, sheet: QPixmap, n_frames: int, fps: float = 8.0, loop: bool = True):
        self.sheet = sheet
        self.n_frames = n_frames
        self.frame_duration = int(1000 / fps)   # ms por frame
        self.loop = loop
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
        x = self._frame_idx * FRAME_SIZE
        return self.sheet.copy(x, 0, FRAME_SIZE, FRAME_SIZE)


def load_animation(name: str, n_frames: int, fps: float = 8.0,
                   loop: bool = True, facing: str = "right") -> Optional[AnimationPlayer]:
    """Carga un spritesheet escalado desde assets/ y devuelve un AnimationPlayer."""
    suffix = "_left_scaled" if facing == "left" else "_scaled"
    path = os.path.join(ASSETS_DIR, f"{name}{suffix}.png")
    if not os.path.exists(path):
        # Fallback: sheet sin sufijo
        path = os.path.join(ASSETS_DIR, f"{name}.png")
    if not os.path.exists(path):
        return None
    sheet = QPixmap(path)
    if sheet.isNull():
        return None
    return AnimationPlayer(sheet, n_frames, fps, loop)


# ──────────────────────────────────────────────────────────────────────────────
# SHIMEJI PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
class CapriShimeji(QWidget):
    # Definición de animaciones: (sheet_name, n_frames, fps, loop)
    ANIM_DEF = {
        "idle":    ("idle",         10, 8.0,  True),
        "dangle":  ("dangle",       15, 12.0, True),
        "glitch":  ("glitch",        6, 10.0, True),
        "grin":    ("grin",         10, 10.0, False),
        "sleep":   ("sleep",        10, 5.0,  True),
        "wake":    ("wake",          8, 10.0, False),
        "blink":   ("blink",         2, 4.0,  False),
    }

    # FPS lógico del bucle de juego
    TICK_MS = 25   # 40 FPS

    # Tiempo (ticks) sin actividad antes de dormir
    SLEEP_AFTER = 40 * 60 * 3   # ~3 minutos

    def __init__(self):
        super().__init__()

        # ── Ventana sin marcos, transparente, siempre encima ──────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool          # Sin botón en la barra de tareas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # ── Dimensiones ───────────────────────────────────────────────────────
        self.win_w = FRAME_SIZE + 20
        self.win_h = FRAME_SIZE + DIALOG_MARGIN
        self.resize(self.win_w, self.win_h)

        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.screen_width = geo.width()
        self.screen_height = geo.height()

        # ── Física y posición ─────────────────────────────────────────────────
        self.floor_y = self.screen_height - self.win_h - 44
        self.pos_x: float = float(self.screen_width // 2)
        self.pos_y: float = float(self.floor_y)
        self.vx: float = 2.0
        self.vy: float = 0.0
        self.gravity: float = 1.4

        # ── Estado de la máquina ──────────────────────────────────────────────
        self.state: str = "IDLE"
        self.facing: str = "right"          # "left" | "right"
        self.state_timer: int = 0
        self.idle_ticks: int = 0            # Para detectar inactividad → sleep
        self.is_running: bool = True

        # ── Diálogos ──────────────────────────────────────────────────────────
        self.dialog_text: Optional[str] = None
        self.dialog_timer: int = 0

        # ── Backend ───────────────────────────────────────────────────────────
        self.backend_online: bool = False

        # ── Arrastre con ratón ────────────────────────────────────────────────
        self.drag_offset = QPoint()
        self.is_dragging: bool = False

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
        for key, (sheet, n, fps, loop) in self.ANIM_DEF.items():
            self.anims[key] = {
                "right": load_animation(sheet, n, fps, loop, "right"),
                "left":  load_animation(sheet, n, fps, loop, "left"),
            }

    def _get_anim(self, key: str) -> Optional[AnimationPlayer]:
        """Devuelve el AnimationPlayer para el estado y facing actuales."""
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

        act("⚡ Abrir C.A.P.R.I. HUD", self.open_hud)
        act("📊 Telemetría del Sistema", self.query_system_status)
        self.menu.addSeparator()
        act("⏸ Pausar / Reanudar", self.toggle_pause)
        act("😴 Dormir ahora", lambda: self._transition("SLEEPING"))
        act("❌ Desactivar Shimeji", self.close)

    # ── Transiciones de estado ────────────────────────────────────────────────
    def _transition(self, new_state: str, timer: int = 0):
        """Cambia al nuevo estado y rearma la animación correspondiente."""
        self.state = new_state
        self.state_timer = timer
        self.idle_ticks = 0

        state_to_anim = {
            "IDLE":      "idle",
            "WALK_RIGHT":"idle",
            "WALK_LEFT": "idle",
            "FALLING":   "dangle",
            "DRAGGED":   "dangle",
            "SCANNING":  "glitch",
            "SLEEPING":  "sleep",
            "WAKING":    "wake",
            "GRINNING":  "grin",
        }
        anim_key = state_to_anim.get(new_state, "idle")
        self.current_anim = self._get_anim(anim_key)

    # ── Interacción del ratón ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.state != "DRAGGED":
                self.facing = "right"
                self._transition("DRAGGED")
            self.vy = 0.0
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
            self.is_dragging = False
            if self.pos_y < self.floor_y:
                self._transition("FALLING")
            else:
                self.pos_y = self.floor_y
                self._transition("IDLE", timer=60)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_hud()

    # ── Acciones del menú ─────────────────────────────────────────────────────
    def open_hud(self):
        self.show_dialog("Enlace Neural...")
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_pause(self):
        if self.state == "PAUSED":
            self._transition("IDLE", timer=40)
            self.show_dialog("Sistema reactivado")
        else:
            self.state = "PAUSED"
            self.show_dialog("Modo centinela")

    def show_dialog(self, text: str, duration: int = 150):
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
            # Reacción visual cuando el backend vuelve a estar online
            if self.backend_online and not was_online:
                self.show_dialog("Neural link established")
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
            # Parpadeo ocasional durante IDLE
            if random.random() < 0.003:
                self.show_dialog("...")
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
            # Despertar si el usuario hace clic (manejado en mouse events)

        elif s == "WAKING":
            if self.current_anim and self.current_anim.finished:
                self._transition("IDLE", timer=60)

        elif s == "GRINNING":
            if self.current_anim and self.current_anim.finished:
                self._transition("IDLE", timer=60)

        self.update()

    def _sync_position(self):
        """Aplica pos_x/pos_y a la posición real de la ventana con clamp."""
        self.pos_x = max(0.0, min(float(self.screen_width - self.win_w), self.pos_x))
        self.pos_y = max(0.0, min(float(self.screen_height - self.win_h), self.pos_y))
        self.move(int(self.pos_x), int(self.pos_y))

    # ── Despertar al hacer clic durante el sueño ──────────────────────────────
    def _wake_if_sleeping(self):
        if self.state == "SLEEPING":
            self.idle_ticks = 0
            self._transition("WAKING")

    def mousePressEvent(self, event):
        self._wake_if_sleeping()
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.state not in ("SLEEPING", "WAKING"):
                self.facing = "right"
                self._transition("DRAGGED")
            self.vy = 0.0
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.exec(event.globalPosition().toPoint())

    # ── Pintado ───────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Frame actual de la animación
        frame = self.current_anim.current_frame() if self.current_anim else QPixmap()

        # Flotación suave en estados tranquilos
        float_y = 0
        if self.state in ("IDLE", "SCANNING", "SLEEPING"):
            import math as _m
            tick = self.game_timer.remainingTime()  # reuse for wave
            float_y = int(_m.sin(self.game_timer.interval() * 0.001 + id(self) * 0.001) * 2)

        # Micro-glitch característica de Capri
        gx = 0
        if self.state in ("SCANNING", "GRINNING") and random.random() < 0.06:
            gx = random.choice([-4, 4])

        draw_x = (self.win_w - FRAME_SIZE) // 2 + gx
        draw_y = DIALOG_MARGIN + float_y

        # Dibujar sprite
        if not frame.isNull():
            painter.drawPixmap(draw_x, draw_y, frame)
            # Línea de glitch
            if gx != 0:
                pen = QPen(QColor(0, 229, 255, 160), 1)
                painter.setPen(pen)
                ly = draw_y + random.randint(10, FRAME_SIZE - 10)
                painter.drawLine(draw_x, ly, draw_x + FRAME_SIZE, ly)

        # LED de estado del backend
        led = QColor(0, 255, 102, 220) if self.backend_online else QColor(0, 229, 255, 140)
        painter.setBrush(led)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.win_w // 2 - 4, self.win_h - 8, 8, 8)

        # Bocadillo de diálogo
        if self.dialog_text:
            font = QFont("Courier New", 8, QFont.Weight.Bold)
            painter.setFont(font)
            text = self.dialog_text
            text_w = min(self.win_w - 6, max(70, len(text) * 7 + 14))
            bx = (self.win_w - text_w) // 2
            by = 4
            painter.setBrush(QColor(5, 7, 10, 235))
            painter.setPen(QPen(QColor(0, 255, 102), 1))
            painter.drawRoundedRect(bx, by, text_w, 22, 3, 3)
            painter.setPen(QColor(0, 255, 102))
            painter.drawText(QRect(bx, by, text_w, 22), Qt.AlignmentFlag.AlignCenter, text)

    # ── Cierre ordenado ───────────────────────────────────────────────────────
    def close(self):
        self.is_running = False
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
