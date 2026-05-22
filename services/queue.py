"""
services/queue.py — Disk-based job queue for LevelUp
Works identically to the original but writes results to SQLite instead of PocketBase.
"""

import os
import json
import shutil
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from services.ollama import evaluate_activity
from services import db
from services.xp import (
    calculate_level, apply_streak_bonus, calculate_total_level,
    update_streak, xp_progress
)

logger = logging.getLogger(__name__)

QUEUE_BASE = os.getenv("QUEUE_PATH", "/mnt/storage/queue")
PENDING_DIR    = os.path.join(QUEUE_BASE, "pending")
PROCESSING_DIR = os.path.join(QUEUE_BASE, "processing")
COMPLETED_DIR  = os.path.join(QUEUE_BASE, "completed")
FAILED_DIR     = os.path.join(QUEUE_BASE, "failed")
SCREENSHOTS_DIR = os.path.join(QUEUE_BASE, "screenshots")

_worker_running = False


def ensure_queue_dirs():
    for d in [PENDING_DIR, PROCESSING_DIR, COMPLETED_DIR, FAILED_DIR, SCREENSHOTS_DIR]:
        Path(d).mkdir(parents=True, exist_ok=True)


def _job_filename(job_id: str) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}_{job_id}.json"


def enqueue_log(job_id: str, user_id: str, category: str,
                description: str, screenshot_path: str | None = None,
                duration: int | None = None):
    """Save job to disk queue and add a pending record to DB."""
    ensure_queue_dirs()

    # Move screenshot to queue screenshots dir
    screenshot_queue_path = None
    if screenshot_path and os.path.exists(screenshot_path):
        dest = os.path.join(SCREENSHOTS_DIR, f"{job_id}_{os.path.basename(screenshot_path)}")
        shutil.move(screenshot_path, dest)
        screenshot_queue_path = dest

    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "category": category,
        "description": description,
        "screenshot": screenshot_queue_path,
        "duration": duration,
        "created": datetime.utcnow().isoformat(),
    }

    filename = _job_filename(job_id)
    job_path = os.path.join(PENDING_DIR, filename)
    with open(job_path, "w") as f:
        json.dump(job_data, f)

    # Record in DB
    db.create_queue_entry(job_id, user_id, category, description)
    logger.info(f"Enqueued job {job_id} for user {user_id}")


async def process_queue():
    """Background worker — runs forever, processes one job at a time."""
    global _worker_running
    _worker_running = True
    logger.info("Queue worker started")

    while True:
        try:
            await _process_one()
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
        await asyncio.sleep(5)


async def _process_one():
    """Pick one pending job, process it, update DB."""
    ensure_queue_dirs()
    pending_files = sorted(Path(PENDING_DIR).glob("*.json"))
    if not pending_files:
        return

    job_file = pending_files[0]
    proc_path = Path(PROCESSING_DIR) / job_file.name

    try:
        shutil.move(str(job_file), str(proc_path))
    except Exception:
        return  # Another worker grabbed it (shouldn't happen with single worker)

    try:
        with open(proc_path) as f:
            job = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read job file {proc_path}: {e}")
        shutil.move(str(proc_path), str(Path(FAILED_DIR) / job_file.name))
        return

    job_id = job["job_id"]
    user_id = job["user_id"]
    logger.info(f"Processing job {job_id}")

    # Mark as processing in DB
    db.update_queue_status_by_job(job_id, "processing")

    try:
        result = await evaluate_activity(
            category=job["category"],
            description=job["description"],
            screenshot_path=job.get("screenshot"),
            duration=job.get("duration"),
        )

        # Clean up screenshot
        if job.get("screenshot") and os.path.exists(job["screenshot"]):
            os.remove(job["screenshot"])

        # Get user and apply XP
        user = db.get_user_by_id(user_id)
        if not user:
            raise Exception(f"User {user_id} not found")

        xp = result["xp_awarded"]
        verified = result["verified"]
        message = result["message"]

        if verified and xp > 0:
            # Apply streak bonus
            new_streak, new_last_date = update_streak(
                user["last_log_date"], user["current_streak"]
            )
            xp = apply_streak_bonus(xp, new_streak)

            # Update category XP
            cat = job["category"]
            new_physical_xp = user["physical_xp"] + (xp if cat == "physical" else 0)
            new_sharpness_xp = user["sharpness_xp"] + (xp if cat == "sharpness" else 0)
            new_wellbeing_xp = user["wellbeing_xp"] + (xp if cat == "wellbeing" else 0)
            new_total_xp = user["total_xp"] + xp

            new_physical_level = calculate_level(new_physical_xp)
            new_sharpness_level = calculate_level(new_sharpness_xp)
            new_wellbeing_level = calculate_level(new_wellbeing_xp)
            new_total_level = calculate_total_level(
                new_physical_level, new_sharpness_level, new_wellbeing_level
            )

            db.update_user_xp(
                user_id,
                new_physical_xp, new_sharpness_xp, new_wellbeing_xp, new_total_xp,
                new_physical_level, new_sharpness_level, new_wellbeing_level, new_total_level,
                new_streak, new_last_date
            )
        else:
            new_streak = user["current_streak"]
            new_last_date = user["last_log_date"]

        # Create log entry
        db.create_log(
            user_id=user_id,
            category=job["category"],
            description=job["description"],
            xp_awarded=xp if verified else 0,
            ai_response=message,
            verified=verified,
        )

        # Update queue record
        db.update_queue_status_by_job(
            job_id, "completed",
            xp_awarded=xp if verified else 0,
            ai_response=message,
            verified=verified
        )

        # Move job file to completed
        shutil.move(str(proc_path), str(Path(COMPLETED_DIR) / job_file.name))
        logger.info(f"Job {job_id} completed. XP={xp}, verified={verified}")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        db.update_queue_status_by_job(job_id, "failed", ai_response=str(e))
        shutil.move(str(proc_path), str(Path(FAILED_DIR) / job_file.name))


def resume_interrupted_jobs():
    """On startup, move any processing/ jobs back to pending/ (they were interrupted)."""
    ensure_queue_dirs()
    moved = 0
    for f in Path(PROCESSING_DIR).glob("*.json"):
        shutil.move(str(f), str(Path(PENDING_DIR) / f.name))
        moved += 1
    if moved:
        logger.info(f"Resumed {moved} interrupted jobs")


def cleanup_old_jobs(days: int = 7):
    """Delete completed/failed job files older than `days` days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    removed = 0
    for d in [COMPLETED_DIR, FAILED_DIR]:
        for f in Path(d).glob("*.json"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
    if removed:
        logger.info(f"Cleaned up {removed} old job files")
