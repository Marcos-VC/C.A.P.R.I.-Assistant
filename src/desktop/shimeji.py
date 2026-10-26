"""
C.A.P.R.I. Desktop Shimeji (Cyberpunk: Edgerunners Style)
Mascota de escritorio interactiva, autónoma y liviana para Ubuntu Linux.
100% Transparente (sin caja de fondo) mediante PyQt6 y aceleración nativa.
"""
import os
import sys
import math
import random
import json
import urllib.request
import webbrowser
import threading

# Evita el bug de incompatibilidad de GNOME 46 xsettings con GLib en Ubuntu 24.04
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["XDG_CURRENT_DESKTOP"] = "Generic"

from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QAction

# Directorio de assets gráficos
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

class CapriShimeji(QWidget):
    def __init__(self):
        super().__init__()

        # Ventana transparente sin marcos y siempre al frente (Always on Top)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # Cargar sprites oficiales de Capri (derecha / izquierda)
        path_right = os.path.join(ASSETS_DIR, "capri_right.png")
        path_left = os.path.join(ASSETS_DIR, "capri_left.png")

        self.pixmap_right = QPixmap(path_right) if os.path.exists(path_right) else QPixmap()
        self.pixmap_left = QPixmap(path_left) if os.path.exists(path_left) else QPixmap()
        self.current_pixmap = self.pixmap_right

        # Dimensiones de la ventana (con margen superior para el bocadillo de diálogo)
        self.sprite_w = self.current_pixmap.width() if not self.current_pixmap.isNull() else 104
        self.sprite_h = self.current_pixmap.height() if not self.current_pixmap.isNull() else 220
        self.win_w = max(130, self.sprite_w + 20)
        self.win_h = self.sprite_h + 35  # Espacio superior para bocadillos
        self.resize(self.win_w, self.win_h)

        # Dimensiones de la pantalla física
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.screen_width = screen_geo.width()
        self.screen_height = screen_geo.height()

        # Posición inicial: suelo de la pantalla (justo sobre el panel de tareas de Ubuntu)
        self.x = self.screen_width // 2 - self.win_w // 2
        self.floor_y = self.screen_height - self.win_h - 44
        self.y = self.floor_y

        # Física y comportamiento autónomo
        self.vx = 2
        self.vy = 0.0
        self.gravity = 1.3
        self.state = "WALK_RIGHT"  # IDLE, WALK_LEFT, WALK_RIGHT, FALLING, SCANNING, DRAGGED, PAUSED
        self.state_timer = 0
        self.anim_tick = 0
        self.backend_online = False
        self.dialog_text = None
        self.dialog_timer = 0
        self.is_running = True

        # Control de arrastre con ratón
        self.drag_position = QPoint()
        self.is_dragging = False

        # Posicionamiento inicial
        self.move(int(self.x), int(self.y))

        # Menú contextual cyberpunk
        self.setup_context_menu()

        # Bucle de juego a 40 FPS (25ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.game_loop)
        self.timer.start(25)

        # Chequeo periódico de salud del backend
        self.check_backend_health()

    def setup_context_menu(self):
        """Crea el menú contextual cyberpunk para el clic derecho."""
        self.menu = QMenu(self)
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #161920;
                color: #c5d1de;
                border: 1px solid #00e5ff;
                font-family: monospace;
                font-size: 11px;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #00e5ff;
                color: #0d0f12;
            }
        """)

        act_hud = QAction("⚡ Abrir C.A.P.R.I. HUD", self)
        act_hud.triggered.connect(self.open_hud)
        self.menu.addAction(act_hud)

        act_ram = QAction("📊 Telemetría del Sistema", self)
        act_ram.triggered.connect(self.query_system_status)
        self.menu.addAction(act_ram)

        self.menu.addSeparator()

        self.act_pause = QAction("⏸ Pausar / Reanudar", self)
        self.act_pause.triggered.connect(self.toggle_pause)
        self.menu.addAction(self.act_pause)

        act_quit = QAction("❌ Desactivar Shimeji", self)
        act_quit.triggered.connect(self.close)
        self.menu.addAction(act_quit)

    # ==========================================
    # INTERACCIÓN DEL RATÓN
    # ==========================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.state = "DRAGGED"
            self.vy = 0.0
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.x = new_pos.x()
            self.y = new_pos.y()
            self.move(int(self.x), int(self.y))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            if self.y < self.floor_y:
                self.state = "FALLING"
            else:
                self.y = self.floor_y
                self.state = "IDLE"
                self.state_timer = 50
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_hud()

    def open_hud(self):
        self.show_dialog("Enlace Neural...")
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_pause(self):
        if self.state == "PAUSED":
            self.state = "IDLE"
            self.show_dialog("Reanudando")
        else:
            self.state = "PAUSED"
            self.show_dialog("Modo centinela")

    def show_dialog(self, text: str, duration: int = 140):
        self.dialog_text = text
        self.dialog_timer = duration
        self.update()

    # ==========================================
    # ENLACE CON EL BACKEND DE C.A.P.R.I.
    # ==========================================
    def check_backend_health(self):
        def _check():
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/health", headers={"User-Agent": "Capri-Shimeji"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        self.backend_online = True
            except Exception:
                self.backend_online = False
            
            if self.is_running:
                QTimer.singleShot(5000, self.check_backend_health)

        threading.Thread(target=_check, daemon=True).start()

    def query_system_status(self):
        def _query():
            try:
                payload = json.dumps({"skill_name": "system_monitor"}).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/v1/skills/execute",
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Capri-Shimeji"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    result = data.get("result", {})
                    mem_info = result.get("memory_info", "")
                    lines = mem_info.split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        free_mem = parts[6] if len(parts) > 6 else parts[3]
                        self.show_dialog(f"RAM libre: {free_mem}")
                    else:
                        self.show_dialog("Sistemas OK")
            except Exception:
                self.show_dialog("Error enlace")

        threading.Thread(target=_query, daemon=True).start()

    # ==========================================
    # BUCLE FÍSICO Y COMPORTAMIENTO AUTÓNOMO
    # ==========================================
    def game_loop(self):
        if not self.is_running or self.state == "PAUSED":
            return

        self.anim_tick += 1

        # Temporizador de diálogo
        if self.dialog_timer > 0:
            self.dialog_timer -= 1
            if self.dialog_timer <= 0:
                self.dialog_text = None

        # Gravedad en caída
        if self.state == "FALLING":
            self.vy += self.gravity
            self.y += self.vy
            if self.y >= self.floor_y:
                self.y = self.floor_y
                self.vy = 0.0
                self.state = "IDLE"
                self.state_timer = 40
            self.move(int(self.x), int(self.y))

        # Patrulla autónoma
        elif self.state == "WALK_RIGHT":
            self.current_pixmap = self.pixmap_right
            self.x += self.vx
            if self.x >= self.screen_width - self.win_w - 20:
                self.state = "WALK_LEFT"
            elif random.random() < 0.008:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 120)
            self.move(int(self.x), int(self.y))

        elif self.state == "WALK_LEFT":
            self.current_pixmap = self.pixmap_left
            self.x -= self.vx
            if self.x <= 20:
                self.state = "WALK_RIGHT"
            elif random.random() < 0.008:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 120)
            self.move(int(self.x), int(self.y))

        elif self.state == "IDLE":
            self.state_timer -= 1
            if self.state_timer <= 0:
                decision = random.random()
                if decision < 0.48:
                    self.state = "WALK_RIGHT"
                elif decision < 0.96:
                    self.state = "WALK_LEFT"
                else:
                    self.state = "SCANNING"
                    self.state_timer = 60

        elif self.state == "SCANNING":
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "IDLE"
                self.state_timer = 40

        # Redibujar fotograma
        self.update()

    # ==========================================
    # PINTADO 100% TRANSPARENTE EN PANTALLA
    # ==========================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Flotación suave y orgánica
        float_y = int(math.sin(self.anim_tick * 0.1) * 3) if self.state in ("IDLE", "SCANNING", "DRAGGED") else 0

        # Micro-glitch digital aleatorio característico de Capri
        glitch_x = 0
        if random.random() < 0.04:
            glitch_x = random.choice([-3, 3])

        # 1. Dibujar Sprite 100% transparente de Capri
        draw_x = (self.win_w - self.sprite_w) // 2 + glitch_x
        draw_y = 35 + float_y  # Dejar 35px arriba para el bocadillo

        if not self.current_pixmap.isNull():
            painter.drawPixmap(draw_x, draw_y, self.current_pixmap)

            # Efecto sutil de línea de escaneo si hay glitch
            if glitch_x != 0:
                pen = QPen(QColor(0, 229, 255, 180), 1)
                painter.setPen(pen)
                line_y = draw_y + random.randint(20, self.sprite_h - 20)
                painter.drawLine(draw_x - 10, line_y, draw_x + self.sprite_w + 10, line_y)

        # 2. Indicador LED holográfico de enlace con el backend
        led_color = QColor(0, 255, 102, 220) if self.backend_online else QColor(0, 229, 255, 180)
        painter.setBrush(led_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.win_w // 2 - 3, self.win_h - 6, 6, 6)

        # 3. Globo de texto cyberpunk flotando sobre su pelo
        if self.dialog_text:
            painter.setFont(QFont("monospace", 8, QFont.Weight.Bold))
            text = self.dialog_text
            text_w = min(self.win_w - 4, max(65, len(text) * 7 + 10))
            bubble_x = (self.win_w - text_w) // 2
            bubble_y = 6

            # Caja del bocadillo
            painter.setBrush(QColor(5, 7, 10, 230))
            painter.setPen(QPen(QColor(0, 255, 102), 1))
            painter.drawRect(bubble_x, bubble_y, text_w, 20)

            # Texto
            painter.setPen(QColor(0, 255, 102))
            painter.drawText(QRect(bubble_x, bubble_y, text_w, 20), Qt.AlignmentFlag.AlignCenter, text)

    def close(self):
        """Cierre ordenado y limpio."""
        self.is_running = False
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        super().close()

def run():
    app = QApplication(sys.argv)
    shimeji = CapriShimeji()
    shimeji.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run()
