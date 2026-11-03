from urllib.request import urlopen
from urllib.error import URLError

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.projects import router as projects_router

app = FastAPI(
    title="Project Auditor API",
    description="Universal AI-powered project analysis and testing platform",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)


@app.get("/")
def root():
    return {
        "name": "Project Auditor",
        "version": "0.2.0",
        "status": "running",
    }


@app.get("/api/health")
def health():
    ollama_status = "offline"

    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            if response.status == 200:
                ollama_status = "online"
    except (URLError, TimeoutError, OSError):
        pass

    return {
        "backend": "online",
        "ollama": ollama_status,
        "version": "0.2.0",
    }

