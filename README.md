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
│   └── frontend/         # Interfaz nativa de escritorio (Tauri + Rust)
├── tests/                # Baterías de pruebas unitarias e integración
└── docs/                 # Documentación técnica de arquitectura

* **Backend Core:** FastAPI + Pydantic para una validación estricta de tipos y baja latencia.
* **Seguridad:** Aislamiento de credenciales locales (`.env` bajo `.gitignore`), integración nativa mediante SSH y ejecución aislada en entorno virtual (`venv`).
* **Frontend:** (En desarrollo) Interfaz ligera sobre Tauri/Rust.

---

## 🗺️ Roadmap de Desarrollo

- [x] **Fase 1: Infraestructura y Core**
  - [x] Estructuración del repositorio Git e integración SSH segura.
  - [x] Entorno virtual e instalación de dependencias base.
  - [x] Endpoint de salud (`/health`) y servidor ASGI con Uvicorn.
  - [x] Modelos de validación con Pydantic y endpoint `/api/v1/chat`.
  - [x] Documentación inicial del repositorio.

- [x] **Fase 2: Sistema de Memoria Local (Local-First Memory)**
  - [x] Implementación de persistencia ligera con SQLite.
  - [x] Historial de chat guardado por sesión (`session_id`).

- [x] **Fase 3: Motor de Habilidades (Skills Engine)**
  - [x] Módulo base para habilidades y endpoint de ejecución `/api/v1/skills/execute`.
  - [x] Habilidad `system_monitor` integrada (lectura de RAM y disco).

- [ ] **Fase 4: Frontend y UI Cyberpunk**
  - [ ] Setup del cliente nativo en Tauri/Rust.
  - [ ] Dashboard HUD con estética Cyberpunk/Terminal.

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
