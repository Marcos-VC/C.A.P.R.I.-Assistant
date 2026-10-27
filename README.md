<div align="center">

# 🤖 C.A.P.R.I. Assistant
### **C**ybernetic **A**utonomously **P**rogrammed **R**esponse **I**nterface

![Ubuntu](https://img.shields.io/badge/OS-Ubuntu-orange?style=for-the-badge&logo=ubuntu)
![Python](https://img.shields.io/badge/Backend-Python_3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688?style=for-the-badge&logo=fastapi)
![Gemini](https://img.shields.io/badge/LLM-Gemini_3.5_Flash-4285F4?style=for-the-badge&logo=google)
![PyQt6](https://img.shields.io/badge/Desktop-PyQt6-41CD52?style=for-the-badge&logo=qt)
![Architecture](https://img.shields.io/badge/Design-Local--First-purple?style=for-the-badge)

*Asistente modular de escritorio de estética cyberpunk, autónoma, segura y optimizada para entornos Linux.*

---

</div>

## 👁️ Visión del Proyecto

**C.A.P.R.I.** es una interfaz de respuesta autónoma diseñada bajo el paradigma **Local-First**. Su objetivo es proporcionar una asistencia de escritorio privada, extensible mediante habilidades (*skills*) dinámicas y con un consumo de recursos ultraoptimizado, aislando la lógica y los datos sensibles del usuario en su propia máquina local.

El procesamiento LLM se delega a **APIs en la nube** (Google Gemini / Groq) para garantizar respuestas inteligentes de alta calidad sin saturar los recursos locales del equipo.

---

## 🛠️ Arquitectura del Sistema

```text
capri-assistant/
├── src/
│   ├── backend/                    # Servidor REST con FastAPI
│   │   ├── core/
│   │   │   ├── llm.py              # Motor LLM: Gemini Flash + cascada de fallback
│   │   │   └── schemas.py          # Modelos Pydantic
│   │   ├── memory/
│   │   │   ├── database.py         # SQLite init
│   │   │   └── repository.py       # Persistencia de historial por sesión
│   │   ├── skills/
│   │   │   ├── base.py             # BaseSkill con SecurityLevel y Function Calling
│   │   │   ├── registry.py         # SkillRegistry: validación y ejecución segura
│   │   │   └── system_skills.py    # SystemMonitorSkill y AudioControlSkill
│   │   └── main.py                 # Endpoints FastAPI (REST + HUD)
│   ├── desktop/
│   │   ├── shimeji.py              # Mascota de escritorio animada (PyQt6)
│   │   └── assets/                 # Spritesheets multi-frame de Capri (RGBA)
│   └── frontend/
│       └── index.html              # HUD Web Cyberpunk en http://127.0.0.1:8000
├── tests/
│   ├── backend/
│   │   ├── test_api.py             # Tests de endpoints FastAPI
│   │   └── test_skills.py          # Tests del SkillRegistry y seguridad
│   └── desktop/
│       └── test_shimeji.py         # Tests del motor de animación y estados
└── docs/                           # Documentación técnica de arquitectura
```

---

## ⚙️ Stack Tecnológico

| Capa | Tecnología | Descripción |
|:---|:---|:---|
| **Backend** | FastAPI + Uvicorn | API REST asíncrona en el puerto 8000 |
| **LLM Cloud** | `google-genai` SDK | `gemini-3.5-flash-lite` (principal) con fallback a `gemini-3.6-flash` y `gemini-3.5-flash` |
| **Memoria** | SQLite | Historial de conversaciones por `session_id` |
| **Skills** | SkillRegistry | Ejecución segura con matrix SAFE / CONFIRM_REQUIRED / PROHIBITED |
| **Function Calling** | `types.Tool` nativo de Gemini | El modelo invoca skills locales de forma autónoma |
| **HUD Web** | HTML5 + CSS3 + JS | Dashboard cyberpunk servido desde FastAPI |
| **Desktop** | PyQt6 | Ventana 100% transparente, siempre-al-frente, sin bordes |
| **Sprites** | PNG RGBA spritesheets | Animaciones multi-frame de Capri (Edgerunners S2) |
| **Tests** | pytest + anyio | 10 tests automatizados < 0.7s |

---

## 🧠 Integración LLM y Function Calling

C.A.P.R.I. implementa un ciclo de **Function Calling autónomo** con Gemini:

1. El usuario envía un mensaje al chat.
2. Gemini detecta si necesita información del sistema (`system_monitor`) para responder.
3. Si es necesario, genera un `function_call` → el backend ejecuta la skill localmente via `asyncio.create_subprocess_exec`.
4. El resultado (RAM, disco, uptime) se inyecta de vuelta a Gemini como `function_response`.
5. Gemini genera la respuesta final con los datos reales del sistema, en tono cyberpunk.

```
Usuario → /api/v1/chat → [Gemini genera function_call] 
       → SkillRegistry.execute("system_monitor") 
       → [Gemini recibe datos y genera respuesta final]
       → C.A.P.R.I. responde con datos reales del sistema
```

---

## 👾 Desktop Shimeji — Capri (Edgerunners S2)

La mascota de escritorio es una implementación ligera (<20 MB RAM) con:

- **Transparencia 100% real** — Sin caja de fondo, solo el personaje sobre el escritorio.
- **Always-on-top** — Visible por encima de todas las ventanas (VSCode, Firefox, terminal...).
- **Motor de animación** — `AnimationPlayer` reproduce spritesheets RGBA frame a frame.
- **Estados animados**: `IDLE` · `WALK` · `FALLING` · `DRAGGED` · `SCANNING` · `SLEEPING` · `WAKING` · `GRINNING`
- **Interacción**: arrastre con ratón · doble clic para abrir el HUD · menú clic derecho · gravedad al soltar en el aire.
- **Enlace con el backend**: detecta si el servidor está online y reacciona visualmente (LED verde = online, cyan = offline).

### Lanzar el Shimeji:
```bash
./venv/bin/python src/desktop/shimeji.py
```

---

## 🔐 Seguridad de Skills

Todas las habilidades se clasifican con un nivel de seguridad antes de ejecutarse:

| Nivel | Descripción | Ejemplo |
|:---|:---|:---|
| `SAFE` | Lectura del sistema, auto-aprobado | `system_monitor` (RAM, disco, uptime) |
| `CONFIRM_REQUIRED` | Requiere confirmación del usuario | Gestión de procesos, apertura de apps |
| `PROHIBITED` | Bloqueado por diseño | Comandos destructivos (`rm -rf`, `mkfs`...) |

---

## 🚀 Inicio Rápido

```bash
# 1. Clonar el repositorio
git clone git@github.com:Marcos-VC/C.A.P.R.I.-Assistant.git
cd C.A.P.R.I.-Assistant

# 2. Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate
pip install -r src/backend/requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# → Editar .env y añadir tu GEMINI_API_KEY

# 4. Iniciar el servidor backend
uvicorn src.backend.main:app --reload --port 8000

# 5. (Opcional) Lanzar el Shimeji de escritorio en paralelo
./venv/bin/python src/desktop/shimeji.py &
```

El HUD Web estará disponible en **http://127.0.0.1:8000**

---

## 🧪 Tests

```bash
pytest
# → 19 passed in <1.1s (backend API, skills matrix, audio control, desktop animation engine, mini-console)
```

---

## 🗺️ Roadmap

### ✅ v0.1 — Core Architecture (COMPLETADO)
- [x] Estructura del repositorio, entorno virtual, endpoints base `/health` y `/api/v1/chat`.
- [x] Modelos Pydantic, servidor ASGI con Uvicorn.

### ✅ v0.2 — Memoria y Skills Engine (COMPLETADO)
- [x] Persistencia con SQLite por `session_id`.
- [x] `BaseSkill`, `SkillRegistry` con matriz de seguridad de 3 niveles.
- [x] `SystemMonitorSkill` con `asyncio.create_subprocess_exec` (RAM, disco, uptime).

### ✅ v0.3 — Integración LLM + HUD (COMPLETADO)
- [x] `google-genai` SDK con `gemini-3.5-flash-lite` + cascada de fallback automática.
- [x] Fix crítico `async def` + `await` en el endpoint de chat.
- [x] **Function Calling autónomo**: Gemini invoca skills locales cuando necesita datos del sistema.
- [x] HUD Web cyberpunk servido desde FastAPI (`http://127.0.0.1:8000`).
- [x] Caché de cliente `_gemini_client` para reutilización de sockets HTTP/TLS.
- [x] Soporte de fallback a Groq Cloud API (`GROQ_API_KEY` en `.env`).

### ✅ v0.4 — Desktop Shimeji Animado (COMPLETADO)
- [x] Mascota de escritorio **100% transparente** con PyQt6 + XWayland.
- [x] Motor de animación `AnimationPlayer` con spritesheets RGBA multi-frame.
- [x] Sprites oficiales de Capri (Cyberpunk: Edgerunners S2): `idle`, `dangle`, `glitch`, `grin`, `sleep`, `wake`.
- [x] Máquina de estados completa con física (gravedad, arrastre, patrulla autónoma).
- [x] Enlace en vivo con el backend: LED verde = online, cyan = offline.

### 🟢 v0.6 — Mini-Consola Táctica Flotante en el Escritorio
- [x] Mini-consola `CyberCommandConsole` estilizada Cyberpunk (borde cian `#00e5ff`, texto verde `#00ff66`, fondo oscuro `#0d0f12`).
- [x] Activación inmediata mediante clic simple sobre Capri, clic central (rueda) o menú contextual ("💬 Enviar directiva...").
- [x] Despacho no bloqueante al backend (`/api/v1/chat`), animación táctica `SCANNING` y respuesta directa en bocadillo multi-línea con reacción `grin`.
- [x] Cancelación rápida con tecla `Escape` o clic fuera del campo.

### 🟡 v0.5 — Control del Sistema y Automatización en Ubuntu (EN PROGRESO)
- [x] `AudioControlSkill` para control de volumen, silencio y reactivación mediante PipeWire/PulseAudio (`wpctl`/`pactl`).
- [ ] `ProcessManagerSkill`: Monitoreo y gestión de procesos que consumen recursos (con confirmación `CONFIRM_REQUIRED`).
- [ ] `AppLauncherSkill`: Lanzador de aplicaciones en Ubuntu (`gtk-launch`/`gio`).

### 🔴 v0.7 — WebSocket Streaming
- [ ] Endpoint `@app.websocket("/ws/chat")` para streaming de tokens en tiempo real.
- [ ] Efecto máquina de escribir en el HUD (respuesta carácter a carácter).
- [ ] Animación `mouth.png` de Capri sincronizada con el streaming de la respuesta.

### 🔴 v0.8 — Empaquetado Nativo
- [ ] `.desktop` launcher para Ubuntu (lanzar todo con un icono en el dock).
- [ ] Script de instalación único `install.sh`.

---

<div align="center">

*Desarrollado con precisión, ingeniería modular y espíritu cyberpunk.*

</div>
