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
from routers import auth, dashboard, admin

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
