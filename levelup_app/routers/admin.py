"""
routers/admin.py — Hidden admin panel
Protected by ADMIN_PASSWORD env var. Rate-limited login.
"""

import os
import time
import logging
from collections import defaultdict
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from services import db
from services.queue import enqueue_log

router = APIRouter()
templates = Jinja2Templates(directory="levelup_app/templates")
logger = logging.getLogger(__name__)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Rate limiting: {ip: [timestamps]}
_failed_attempts: dict[str, list] = defaultdict(list)
LOCKOUT_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes

SESSION_COOKIE = "admin_session"
_admin_sessions: set = set()


def _is_locked(ip: str) -> bool:
    now = time.time()
    attempts = _failed_attempts.get(ip, [])
    recent = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    _failed_attempts[ip] = recent
    return len(recent) >= LOCKOUT_ATTEMPTS


def _record_failure(ip: str):
    _failed_attempts[ip].append(time.time())


def _clear_failures(ip: str):
    _failed_attempts.pop(ip, None)


def _is_admin(request: Request) -> bool:
    return request.cookies.get(SESSION_COOKIE) in _admin_sessions


@router.get("/admin")
async def admin_get(request: Request):
    if not _is_admin(request):
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})

    stats = db.get_admin_stats()
    active_jobs = db.get_active_jobs()
    failed_jobs = db.get_failed_jobs()
    feedback = db.get_feedback_inbox()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "stats": stats,
        "active_jobs": active_jobs,
        "failed_jobs": failed_jobs,
        "feedback": feedback,
        "error": None,
    })


@router.post("/admin")
async def admin_post(request: Request):
    ip = request.client.host

    if _is_locked(ip):
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Příliš mnoho pokusů. Zkus to za 15 minut."
        })

    form = await request.form()
    password = str(form.get("password", ""))

    if password != ADMIN_PASSWORD:
        _record_failure(ip)
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Nesprávné heslo"
        })

    _clear_failures(ip)
    import secrets
    token = secrets.token_hex(16)
    _admin_sessions.add(token)

    resp = RedirectResponse("/admin", status_code=302)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=3600, samesite="strict")
    return resp


@router.post("/admin/retry/{queue_id}")
async def admin_retry(request: Request, queue_id: str):
    if not _is_admin(request):
        return RedirectResponse("/admin", status_code=302)
    db.retry_job(queue_id)
    return RedirectResponse("/admin", status_code=302)


@router.post("/admin/feedback/{feedback_id}/reviewed")
async def admin_feedback_reviewed(request: Request, feedback_id: str):
    if not _is_admin(request):
        return RedirectResponse("/admin", status_code=302)
    db.mark_feedback_reviewed(feedback_id)
    return RedirectResponse("/admin", status_code=302)


@router.get("/admin/logout")
async def admin_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        _admin_sessions.discard(token)
    resp = RedirectResponse("/admin", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
