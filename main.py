"""
main.py — LevelUp FastAPI application
Runs on port 3000, single worker.
SQLite database replaces PocketBase.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.db import init_db
from services.queue import process_queue, resume_interrupted_jobs, cleanup_old_jobs
from routers import auth, dashboard, admin, coach

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")

    # Check Ollama connectivity and warm up model
    from services.ollama import client as ollama_client
    import os
    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
    try:
        resp = await ollama_client.get(f"{ollama_url}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            models = [m['name'] for m in resp.json().get("models", [])]
            logger.info(f"Ollama reachable. Models: {models}")
            if any(m.startswith('llava') for m in models):
                # Start background warmup
                logger.info("Starting Ollama model warmup (llava)...")
                # We don't await this, let it run in background
                asyncio.create_task(ollama_client.post(
                    f"{ollama_url}/api/generate",
                    json={"model": "llava", "prompt": "hi", "stream": False},
                    timeout=300.0
                ))
            else:
                logger.warning("Model 'llava' NOT FOUND in Ollama tags!")
        else:
            logger.warning(f"Ollama returned {resp.status_code} on tags check")
    except Exception as e:
        logger.error(f"Could not reach Ollama at {ollama_url} during startup: {e}")

    resume_interrupted_jobs()
    cleanup_old_jobs(days=7)

    # Start background queue worker
    worker_task = asyncio.create_task(process_queue())
    logger.info("Queue worker started.")

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutdown complete.")


app = FastAPI(lifespan=lifespan, title="LevelUp")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(coach.router)
