from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import runs
from app.config import get_settings

settings = get_settings()
settings.export_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="XHS Content Workflow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(runs.router)
app.mount("/exports", StaticFiles(directory=str(settings.export_dir)), name="exports")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
