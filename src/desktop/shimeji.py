"""
C.A.P.R.I. Desktop Shimeji (Cyberpunk: Edgerunners Style)
Mascota de escritorio interactiva, autónoma y liviana (<20MB RAM) para Ubuntu Linux.
Diseño oficial del constructo digital Capri (Project Capricorn).
"""
import os
import math
import random
import time
import urllib.request
import json
import webbrowser
import threading
import tkinter as tk
from typing import Optional

# Directorio de assets gráficos
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Paleta de colores Cyberpunk
COLOR_BG = "#0d0f12"
COLOR_PANEL = "#161920"
COLOR_CYAN = "#00e5ff"
COLOR_GREEN = "#00ff66"
COLOR_MAGENTA = "#ff007f"
COLOR_RED = "#ff0055"
COLOR_YELLOW = "#ffcc00"
COLOR_TEXT = "#c5d1de"

class CapriShimeji:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("C.A.P.R.I. Shimeji")

        # Configuración de ventana flotante "Always on Top" y sin bordes
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.95)

        # Dimensiones del Shimeji adaptadas al sprite oficial de Capri
        self.width = 124
        self.height = 250
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        # Posición inicial: posada sobre el suelo de la pantalla (encima de la barra de tareas)
        self.x = self.screen_width // 2
        self.floor_y = self.screen_height - self.height - 42
        self.y = self.floor_y

        # Física y comportamiento autónomo
        self.vx = 2
        self.vy = 0
        self.gravity = 1.4
        self.state = "WALK_RIGHT"  # IDLE, WALK_LEFT, WALK_RIGHT, FALLING, SCANNING, DRAGGED, PAUSED
        self.state_timer = 0
        self.anim_tick = 0
        self.backend_online = False
        self.dialog_text: Optional[str] = None
        self.dialog_timer = 0
        self.is_running = True
        self.after_id = None

        # Cargar sprites oficiales de Capri (frente izquierda / derecha)
        self.sprite_right: Optional[tk.PhotoImage] = None
        self.sprite_left: Optional[tk.PhotoImage] = None
        self.load_sprites()

        # Control de arrastre con ratón
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_dragging = False

        # Canvas para renderizar el personaje y sus efectos digitales
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=COLOR_BG,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Eventos del ratón
        self.canvas.bind("<Button-1>", self.on_left_press)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Button-3>", self.show_context_menu)

        # Menú contextual
        self.menu = tk.Menu(self.root, tearoff=0, bg=COLOR_PANEL, fg=COLOR_TEXT, activebackground=COLOR_CYAN, activeforeground=COLOR_BG)
        self.menu.add_command(label="⚡ Abrir C.A.P.R.I. HUD", command=self.open_hud)
        self.menu.add_command(label="📊 Telemetría del Sistema", command=self.query_system_status)
        self.menu.add_separator()
        self.menu.add_command(label="⏸ Pausar / Reanudar", command=self.toggle_pause)
        self.menu.add_command(label="❌ Desactivar Shimeji", command=self.close)

        # Actualizar posición de la ventana
        self.update_geometry()

        # Iniciar chequeo periódico del backend en hilo secundario
        self.check_backend_health()

        # Bucle principal de animación y lógica física (40 FPS = 25ms)
        self.after_id = self.root.after(25, self.game_loop)

    def load_sprites(self):
        """Carga las imágenes PNG transparentes de Capri."""
        try:
            path_right = os.path.join(ASSETS_DIR, "capri_right.png")
            path_left = os.path.join(ASSETS_DIR, "capri_left.png")
            if os.path.exists(path_right):
                self.sprite_right = tk.PhotoImage(file=path_right)
            if os.path.exists(path_left):
                self.sprite_left = tk.PhotoImage(file=path_left)
        except Exception as e:
            print(f"[SHIMEJI]: Aviso al cargar sprites ({e}). Usando renderizado alternativo.")

    def close(self):
        """Cierre ordenado del Shimeji sin señales de error al sistema operativo."""
        self.is_running = False
        if self.after_id:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def update_geometry(self):
        """Posiciona la ventana en pantalla asegurando los límites."""
        self.x = max(0, min(self.screen_width - self.width, self.x))
        self.y = max(0, min(self.screen_height - self.height, self.y))
        self.root.geometry(f"{self.width}x{self.height}+{int(self.x)}+{int(self.y)}")

    # ==========================================
    # INTERACCIÓN DEL RATÓN
    # ==========================================
    def on_left_press(self, event):
        self.is_dragging = True
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.state = "DRAGGED"
        self.vy = 0

    def on_drag_motion(self, event):
        if self.is_dragging:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.x += dx
            self.y += dy
            self.update_geometry()

    def on_left_release(self, event):
        self.is_dragging = False
        if self.y < self.floor_y:
            self.state = "FALLING"
        else:
            self.y = self.floor_y
            self.state = "IDLE"
            self.state_timer = 50

    def on_double_click(self, event):
        """Doble clic abre el HUD Web en el navegador predeterminado."""
        self.open_hud()

    def show_context_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def open_hud(self):
        self.show_dialog("Enlace Neural HUD...")
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_pause(self):
        if self.state == "PAUSED":
            self.state = "IDLE"
            self.show_dialog("Patrulla reactivada")
        else:
            self.state = "PAUSED"
            self.show_dialog("Modo centinela")

    def show_dialog(self, text: str, duration: int = 140):
        """Muestra un globo de diálogo cyberpunk flotando sobre Capri."""
        self.dialog_text = text
        self.dialog_timer = duration

    # ==========================================
    # COMUNICACIÓN CON EL BACKEND DE C.A.P.R.I.
    # ==========================================
    def check_backend_health(self):
        """Verifica en segundo plano si el backend en el puerto 8000 está activo."""
        def _check():
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/health", headers={"User-Agent": "Capri-Shimeji"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        self.backend_online = True
            except Exception:
                self.backend_online = False
            
            if self.is_running:
                try:
                    self.root.after(5000, self.check_backend_health)
                except Exception:
                    pass

        threading.Thread(target=_check, daemon=True).start()

    def query_system_status(self):
        """Solicita la telemetría del sistema al backend y la muestra en pantalla."""
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
                        self.root.after(0, lambda: self.show_dialog(f"RAM libre: {free_mem}"))
                    else:
                        self.root.after(0, lambda: self.show_dialog("Sistemas estables"))
            except Exception:
                self.root.after(0, lambda: self.show_dialog("Error enlace"))

        threading.Thread(target=_query, daemon=True).start()

    # ==========================================
    # MÁQUINA DE ESTADOS Y FÍSICA
    # ==========================================
    def game_loop(self):
        if not self.is_running:
            return
        self.anim_tick += 1

        # 1. Temporizador de globos de diálogo
        if self.dialog_timer > 0:
            self.dialog_timer -= 1
            if self.dialog_timer <= 0:
                self.dialog_text = None

        # 2. Física de caída con gravedad
        if self.state == "FALLING":
            self.vy += self.gravity
            self.y += self.vy
            if self.y >= self.floor_y:
                self.y = self.floor_y
                self.vy = 0
                self.state = "IDLE"
                self.state_timer = 40
            self.update_geometry()

        # 3. Comportamientos autónomos
        elif self.state == "WALK_RIGHT":
            self.x += self.vx
            if self.x >= self.screen_width - self.width - 20:
                self.state = "WALK_LEFT"
            elif random.random() < 0.008:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 120)
            self.update_geometry()

        elif self.state == "WALK_LEFT":
            self.x -= self.vx
            if self.x <= 20:
                self.state = "WALK_RIGHT"
            elif random.random() < 0.008:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 120)
            self.update_geometry()

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

        # 4. Renderizar gráfico
        self.render()

        # Siguiente fotograma a ~40 FPS (25ms)
        if self.is_running:
            self.after_id = self.root.after(25, self.game_loop)

    # ==========================================
    # RENDERIZADO VISUAL DE CAPRI
    # ==========================================
    def render(self):
        self.canvas.delete("all")
        cx = self.width // 2
        cy = self.height // 2 + 10

        # Flotación suave y orgánica (efecto constructo digital / engrama)
        float_offset = math.sin(self.anim_tick * 0.1) * 3 if self.state in ("IDLE", "SCANNING", "DRAGGED") else 0
        cy += float_offset

        # Micro-glitch digital aleatorio característico de Capri
        glitch_x = 0
        glitch_y = 0
        if random.random() < 0.035:
            glitch_x = random.choice([-3, 3])
            glitch_y = random.choice([-2, 2])

        # Selección de sprite según dirección de movimiento
        sprite_to_draw = self.sprite_left if self.state == "WALK_LEFT" else self.sprite_right

        if sprite_to_draw:
            # Dibujar sprite real de Capri
            self.canvas.create_image(cx + glitch_x, cy + glitch_y, anchor="center", image=sprite_to_draw)
            
            # Efecto sutil de anomalía / línea de escaneo digital si hay glitch
            if glitch_x != 0:
                line_y = cy + random.randint(-40, 40)
                self.canvas.create_line(cx - 35, line_y, cx + 35, line_y, fill=COLOR_CYAN, width=1)
        else:
            # Fallback procedural de seguridad en caso de no encontrar la imagen
            self.canvas.create_oval(cx - 20, cy - 40, cx + 20, cy, fill=COLOR_MAGENTA, outline=COLOR_CYAN)
            self.canvas.create_rectangle(cx - 15, cy, cx + 15, cy + 40, fill=COLOR_PANEL, outline=COLOR_GREEN)

        # Indicador de estado del enlace neuronal (LED holográfico debajo de los pies)
        led_color = COLOR_GREEN if self.backend_online else COLOR_CYAN
        self.canvas.create_oval(cx - 3, self.height - 8, cx + 3, self.height - 2, fill=led_color, outline="")

        # Globo de diálogo flotando elegantemente por encima de su pelo rosa
        if self.dialog_text:
            text_w = min(118, max(70, len(self.dialog_text) * 7 + 10))
            bubble_y = 16
            self.canvas.create_rectangle(cx - text_w // 2, bubble_y - 12, cx + text_w // 2, bubble_y + 10, fill="#05070a", outline=COLOR_GREEN, width=1)
            self.canvas.create_text(cx, bubble_y - 1, text=self.dialog_text, fill=COLOR_GREEN, font=("Courier", 8, "bold"))

def run():
    app = CapriShimeji()
    app.root.mainloop()

if __name__ == "__main__":
    run()
