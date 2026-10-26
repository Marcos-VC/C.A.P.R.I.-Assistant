from fastapi import FastAPI

app = FastAPI(
    title="Capri Desktop Assistant API",
    version="0.1.0",
    description="Backend modular para la asistente de escritorio Capri"
)

@app.get("/")
def read_root():
    return {"status": "online", "system": "Capri Core Framework"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "backend"}
