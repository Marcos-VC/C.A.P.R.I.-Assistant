#!/usr/bin/env bash
# ==============================================================================
# C.A.P.R.I. — Lanzador Unificado del Sistema (Cyberpunk Desktop Assistant)
# ==============================================================================
# Inicia de forma limpia y orquestada:
# 1. Backend FastAPI ASGI (puerto 8000)
# 2. Mascota Shimeji Interactiva con Mini-Consola y Bocadillo Táctico
# 3. Limpieza automática de procesos en segundo plano al salir.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Activar entorno virtual
if [ -d "$DIR/venv" ]; then
    PYTHON="$DIR/venv/bin/python"
    UVICORN="$DIR/venv/bin/uvicorn"
else
    PYTHON="python3"
    UVICORN="uvicorn"
fi

PID_FILE="$DIR/.backend.pid"
BACKEND_STARTED=0

cleanup() {
    echo ""
    echo "✦ [C.A.P.R.I.]: Apagando subsistemas..."
    if [ "$BACKEND_STARTED" -eq 1 ] && [ -f "$PID_FILE" ]; then
        BACKEND_PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "✦ [C.A.P.R.I.]: Deteniendo backend FastAPI (PID $BACKEND_PID)..."
            kill "$BACKEND_PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
    echo "✦ [C.A.P.R.I.]: Sesión finalizada."
    exit 0
}

trap cleanup INT TERM EXIT

echo "=========================================================="
echo "    ✦ C.A.P.R.I. // INTERFAZ DE ENLACE NEURAL ✦"
echo "=========================================================="

# 1. Comprobar si el backend ya está corriendo
if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "✔ Backend activo y respondiendo en http://127.0.0.1:8000"
else
    echo "⚡ Iniciando backend FastAPI..."
    $UVICORN src.backend.main:app --host 127.0.0.1 --port 8000 --log-level warning >/dev/null 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$PID_FILE"
    BACKEND_STARTED=1

    # Esperar a que el backend esté listo (máximo 6 segundos)
    for i in {1..12}; do
        if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    echo "✔ Backend conectado correctamente (PID: $BACKEND_PID)"
fi

# 2. Lanzar Desktop Shimeji (interfaz gráfica)
echo "✦ Desplegando a Capri en el escritorio GNOME..."
$PYTHON src/desktop/shimeji.py
