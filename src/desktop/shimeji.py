"""
C.A.P.R.I. Desktop Shimeji (Cybernetic Desktop Companion)
Mascota de escritorio interactiva, autónoma y liviana (<20MB RAM) para Ubuntu Linux.
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

# Paleta de colores Cyberpunk
COLOR_BG = "#0d0f12"
COLOR_PANEL = "#161920"
COLOR_CYAN = "#00e5ff"
COLOR_GREEN = "#00ff66"
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
        self.root.wm_attributes("-alpha", 0.94)

        # Dimensiones del Shimeji
        self.width = 110
        self.height = 110
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        # Posición inicial: suelo de la pantalla (justo sobre el panel de tareas)
        self.x = self.screen_width // 2
        self.floor_y = self.screen_height - self.height - 48
        self.y = self.floor_y

        # Física y comportamiento autónomo
        self.vx = 2
        self.vy = 0
        self.gravity = 1.2
        self.state = "WALK_RIGHT"  # IDLE, WALK_LEFT, WALK_RIGHT, FALLING, SCANNING, DRAGGED
        self.state_timer = 0
        self.anim_tick = 0
        self.backend_online = False
        self.dialog_text: Optional[str] = None
        self.dialog_timer = 0
        self.is_running = True
        self.after_id = None

        # Control de arrastre con ratón
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_dragging = False

        # Canvas para renderizar el personaje
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=COLOR_BG,
            highlightthickness=1,
            highlightbackground=COLOR_CYAN
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

    def close(self):
        """Cierre ordenado del Shimeji."""
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
            self.state_timer = 40

    def on_double_click(self, event):
        """Doble clic abre el HUD Web en el navegador predeterminado."""
        self.open_hud()

    def show_context_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def open_hud(self):
        self.show_dialog("Abriendo HUD Web...")
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_pause(self):
        if self.state == "PAUSED":
            self.state = "IDLE"
            self.show_dialog("Reanudando patrulla")
        else:
            self.state = "PAUSED"
            self.show_dialog("Modo centinela activo")

    def show_dialog(self, text: str, duration: int = 120):
        """Muestra un globo de texto cyberpunk encima del Shimeji."""
        self.dialog_text = text
        self.dialog_timer = duration

    # ==========================================
    # COMUNICACIÓN CON EL BACKEND DE C.A.P.R.I.
    # ==========================================
    def check_backend_health(self):
        """Verifica en segundo plano si el servidor FastAPI en el puerto 8000 está activo."""
        def _check():
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/health", headers={"User-Agent": "Capri-Shimeji"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        self.backend_online = True
            except Exception:
                self.backend_online = False
            # Reintentar cada 5 segundos
            if self.is_running:
                try:
                    self.root.after(5000, self.check_backend_health)
                except Exception:
                    pass

        threading.Thread(target=_check, daemon=True).start()

    def query_system_status(self):
        """Pide información al backend de C.A.P.R.I. y la muestra en el Shimeji."""
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
                    # Extraer línea de memoria
                    mem_info = result.get("memory_info", "")
                    lines = mem_info.split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        free_mem = parts[6] if len(parts) > 6 else parts[3]
                        self.root.after(0, lambda: self.show_dialog(f"RAM Disp: {free_mem}"))
                    else:
                        self.root.after(0, lambda: self.show_dialog("Sistemas estables"))
            except Exception as e:
                self.root.after(0, lambda: self.show_dialog("Error enlace backend"))

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

        # 2. Física de caída (Gravedad)
        if self.state == "FALLING":
            self.vy += self.gravity
            self.y += self.vy
            if self.y >= self.floor_y:
                self.y = self.floor_y
                self.vy = 0
                self.state = "IDLE"
                self.state_timer = 30
            self.update_geometry()

        # 3. Comportamientos autónomos
        elif self.state == "WALK_RIGHT":
            self.x += self.vx
            if self.x >= self.screen_width - self.width - 20:
                self.state = "WALK_LEFT"
            elif random.random() < 0.01:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 100)
            self.update_geometry()

        elif self.state == "WALK_LEFT":
            self.x -= self.vx
            if self.x <= 20:
                self.state = "WALK_RIGHT"
            elif random.random() < 0.01:
                self.state = "IDLE"
                self.state_timer = random.randint(40, 100)
            self.update_geometry()

        elif self.state == "IDLE":
            self.state_timer -= 1
            if self.state_timer <= 0:
                # Transición a caminar o escanear
                decision = random.random()
                if decision < 0.45:
                    self.state = "WALK_RIGHT"
                elif decision < 0.90:
                    self.state = "WALK_LEFT"
                else:
                    self.state = "SCANNING"
                    self.state_timer = 50

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
    # RENDERIZADO GRÁFICO CYBERPUNK (CANVAS)
    # ==========================================
    def render(self):
        self.canvas.delete("all")
        cx = self.width // 2
        cy = self.height // 2 + 5

        # Flotación suave sinusoidal en estados IDLE y SCANNING
        float_offset = math.sin(self.anim_tick * 0.12) * 3 if self.state in ("IDLE", "SCANNING", "DRAGGED") else 0
        cy += float_offset

        # Color del visor según estado del backend
        visor_color = COLOR_GREEN if self.backend_online else COLOR_CYAN

        # 1. Antenas / Orejas cibernéticas
        self.canvas.create_polygon(cx - 24, cy - 22, cx - 30, cy - 36, cx - 18, cy - 24, fill=COLOR_CYAN, outline=COLOR_CYAN)
        self.canvas.create_polygon(cx + 24, cy - 22, cx + 30, cy - 36, cx + 18, cy - 24, fill=COLOR_CYAN, outline=COLOR_CYAN)

        # 2. Cabeza del androide (Chasis oscuro con bisel)
        self.canvas.create_rectangle(cx - 28, cy - 25, cx + 28, cy + 18, fill=COLOR_PANEL, outline=COLOR_CYAN, width=2)
        
        # Puntos de remache / LEDs esquinas
        self.canvas.create_oval(cx - 26, cy - 23, cx - 22, cy - 19, fill=COLOR_CYAN, outline="")
        self.canvas.create_oval(cx + 22, cy - 23, cx + 26, cy - 19, fill=COLOR_CYAN, outline="")

        # 3. Visor Cibernético Táctico
        self.canvas.create_rectangle(cx - 22, cy - 10, cx + 22, cy + 4, fill="#05070a", outline=COLOR_CYAN, width=1)
        
        # Efecto de escaneo / brillo dinámico en el visor
        scan_x = math.sin(self.anim_tick * 0.18) * 14
        self.canvas.create_rectangle(cx + scan_x - 5, cy - 8, cx + scan_x + 5, cy + 2, fill=visor_color, outline="")

        # 4. Cuello y Cuerpo
        self.canvas.create_rectangle(cx - 16, cy + 20, cx + 16, cy + 32, fill=COLOR_PANEL, outline=COLOR_CYAN, width=1)
        # Núcleo de energía central
        core_color = COLOR_GREEN if (self.anim_tick % 20 < 10 and self.backend_online) else COLOR_CYAN
        self.canvas.create_oval(cx - 5, cy + 22, cx + 5, cy + 30, fill=core_color, outline="")

        # 5. Extremidades / Piernas animadas
        leg_step = math.sin(self.anim_tick * 0.3) * 6 if self.state in ("WALK_LEFT", "WALK_RIGHT") else 0
        if self.state == "FALLING" or self.state == "DRAGGED":
            # Efecto propulsor en caída o arrastre
            self.canvas.create_polygon(cx - 10, cy + 34, cx - 4, cy + 45, cx - 1, cy + 34, fill=COLOR_CYAN, outline="")
            self.canvas.create_polygon(cx + 1, cy + 34, cx + 4, cy + 45, cx + 10, cy + 34, fill=COLOR_CYAN, outline="")
        else:
            # Pierna izquierda y derecha
            self.canvas.create_line(cx - 10, cy + 32, cx - 10 + leg_step, cy + 42, fill=COLOR_CYAN, width=3)
            self.canvas.create_line(cx + 10, cy + 32, cx + 10 - leg_step, cy + 42, fill=COLOR_CYAN, width=3)

        # 6. Globo de texto / Diálogo si está activo
        if self.dialog_text:
            text_w = min(100, max(60, len(self.dialog_text) * 7))
            self.canvas.create_rectangle(cx - text_w // 2, cy - 45, cx + text_w // 2, cy - 28, fill="#000000", outline=COLOR_GREEN, width=1)
            self.canvas.create_text(cx, cy - 36, text=self.dialog_text, fill=COLOR_GREEN, font=("Courier", 8, "bold"))

def run():
    app = CapriShimeji()
    app.root.mainloop()

if __name__ == "__main__":
    run()
