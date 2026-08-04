from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import runs, uploads
from app.config import get_settings
from app.services.worker import get_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    worker = get_worker()
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="XHS Content Workflow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(runs.router)
app.include_router(uploads.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
