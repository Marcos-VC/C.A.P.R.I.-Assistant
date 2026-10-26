<div align="center">

# 🤖 C.A.P.R.I. Assistant
### **C**ybernetic **A**utonomously **P**rogrammed **R**esponse **I**nterface

![Ubuntu](https://img.shields.io/badge/OS-Ubuntu-orange?style=for-the-badge&logo=ubuntu)
![Python](https://img.shields.io/badge/Backend-Python_3.12-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688?style=for-the-badge&logo=fastapi)
![Architecture](https://img.shields.io/badge/Design-Local--First-purple?style=for-the-badge)

*Asistente modular de escritorio de estética cyberpunk, autónoma, segura y optimizada para entornos Linux.*

---

</div>

## 👁️ Visión del Proyecto

**C.A.P.R.I.** es una interfaz de respuesta autónoma diseñada bajo el paradigma **Local-First**. Su objetivo es proporcionar una asistencia de escritorio privada, extensible mediante habilidades (*skills*) dinámicas y con un consumo de recursos ultraoptimizado, aislando la lógica y los datos sensibles del usuario en su propia máquina local.

---

## 🛠️ Arquitectura del Sistema

El proyecto sigue una arquitectura desacoplada en micro-módulos:

capri-assistant/
├── src/
│   ├── backend/          # Servidor REST / WebSockets con FastAPI
│   │   ├── core/         # Configuración, esquemas Pydantic y lógica base
│   │   ├── memory/       # Persistencia SQLite a corto/largo plazo
│   │   └── skills/       # Módulos de habilidades y comandos ejecutables
│   └── frontend/         # Interfaz nativa de escritorio y UI Web Cyberpunk
├── tests/                # Baterías de pruebas unitarias e integración
└── docs/                 # Documentación técnica de arquitectura

* **Backend Core:** FastAPI + Pydantic para una validación estricta de tipos y baja latencia.
* **Seguridad:** Aislamiento de credenciales locales (`.env` bajo `.gitignore`), integración nativa mediante SSH y ejecución aislada en entorno virtual (`venv`).
* **Frontend:** Dashboard HUD nativo sobre arquitectura ligera.

---

## 🗺️ Roadmap Extendido de Desarrollo

### 🟢 v0.1: Core Architecture & Systems Engine (COMPLETADO)
- [x] **Fase 1: Infraestructura Base**
  - [x] Estructuración del repositorio Git e integración SSH segura.
  - [x] Entorno virtual e instalación de dependencias base.
  - [x] Endpoint de salud (`/health`) y servidor ASGI con Uvicorn.
  - [x] Modelos de validación con Pydantic y endpoint `/api/v1/chat`.
- [x] **Fase 2: Memoria Local Relacional**
  - [x] Persistencia liviana con SQLite para historial de conversaciones.
  - [x] Contexto aislado por identificador de sesión (`session_id`).
- [x] **Fase 3: Motor de Habilidades (Skills Engine)**
  - [x] Arquitectura extensible de `BaseSkill` y endpoint `/api/v1/skills/execute`.
  - [x] Integración de la habilidad `system_monitor` (RAM y disco en Ubuntu).

---

### 🟡 v0.2: Interface MVP & Cyberpunk HUD (EN PROGRESO)
- [ ] **Fase 4: Frontend Web Cyberpunk / Terminal HUD**
  - [ ] Dashboard interactivo servido desde FastAPI con estética Cyberpunk.
  - [ ] Consola de comandos dinámicos y monitorización de recursos en tiempo real.
- [ ] **Fase 5: Extensión de Habilidades del Sistema**
  - [ ] Habilidades de control de volumen, brillo y gestión de procesos en Linux.
  - [ ] Ejecución condicional de scripts del sistema con confirmación de seguridad.

---

### 🔴 v0.3: Intelligence Integration & Voice Core (FUTURO)
- [ ] **Fase 6: Conexión con LLM Local / Ollama**
  - [ ] Integración de Llama3/Qwen/Mistral corriendo en local.
  - [ ] Módulo de razonamiento y clasificación automática de intenciones (*Intent Router*).
- [ ] **Fase 7: Motor de Voz (STT / TTS)**
  - [ ] Reconocimiento de voz local (Whisper) y síntesis de voz offline (Piper/Coqui).

---

### 🟣 v0.4: Native Desktop Integration (FUTURO)
- [ ] **Fase 8: Cliente Nativo Tauri / Rust**
  - [ ] Empaquetado como aplicación nativa de escritorio para Ubuntu (`.deb` / `.AppImage`).
  - [ ] Bandeja del sistema (*tray icon*), widgets flotantes y atajo de teclado global (`Super + Space`).

---

## 🚀 Inicio Rápido (Backend)

1. Clonar el repositorio:
   git clone git@github.com:Marcos-VC/C.A.P.R.I.-Assistant.git
   cd C.A.P.R.I.-Assistant

2. Crear y activar el entorno virtual:
   python3 -m venv venv
   source venv/bin/activate

3. Instalar dependencias:
   pip install -r src/backend/requirements.txt

4. Iniciar el servidor:
   uvicorn src.backend.main:app --reload --port 8000

---

<div align="center">

*Desarrollado con precisión e ingeniería modular.*

</div>
