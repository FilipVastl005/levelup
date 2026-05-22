"""
routers/dashboard.py — Dashboard, logging, friends, groups, settings, feedback
"""

import os
import uuid
import logging
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services import db
from services.xp import xp_progress, calculate_level
from services.queue import enqueue_log

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/app/uploads")
MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB
DAILY_LOG_LIMIT = 3
ALLOWED_CATEGORIES = {"physical", "sharpness", "wellbeing"}


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session_token")
    if not token:
        return None
    return db.get_session_user(token)


def _is_alpine(request: Request) -> bool:
    return request.headers.get("X-Alpine-Request") == "true"


def _build_dashboard_context(user: dict) -> dict:
    """Fetch everything needed to render the dashboard."""
    physical_logs = db.get_logs_for_user(user["id"], "physical")
    sharpness_logs = db.get_logs_for_user(user["id"], "sharpness")
    wellbeing_logs = db.get_logs_for_user(user["id"], "wellbeing")
    leaderboard = db.get_leaderboard()
    friends = db.get_friends(user["id"])
    groups = db.get_groups_for_user(user["id"])
    queue = db.get_queue_for_user(user["id"])

    physical_progress = xp_progress(user["physical_xp"], user["physical_level"])
    sharpness_progress = xp_progress(user["sharpness_xp"], user["sharpness_level"])
    wellbeing_progress = xp_progress(user["wellbeing_xp"], user["wellbeing_level"])

    return {
        "user": user,
        "physical_logs": physical_logs,
        "sharpness_logs": sharpness_logs,
        "wellbeing_logs": wellbeing_logs,
        "leaderboard": leaderboard,
        "friends": friends,
        "groups": groups,
        "queue": queue,
        "physical_progress": physical_progress,
        "sharpness_progress": sharpness_progress,
        "wellbeing_progress": wellbeing_progress,
    }


@router.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/dashboard")
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ctx = _build_dashboard_context(user)
    ctx["request"] = request
    ctx["error"] = None
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/requests")
async def requests_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    queue = db.get_queue_for_user(user["id"])
    return templates.TemplateResponse("requests.html", {
        "request": request,
        "user": user,
        "queue": queue,
    })


@router.post("/log/{category}")
async def log_activity(
    request: Request,
    category: str,
    activity: str = Form(...),
    duration: int | None = Form(None),
    proof: UploadFile | None = File(None),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Nepřihlášen"}, status_code=401)

    if category not in ALLOWED_CATEGORIES:
        return JSONResponse({"status": "error", "message": "Neplatná kategorie"})

    if len(activity) < 10 or len(activity) > 500:
        return JSONResponse({"status": "error", "message": "Popis musí mít 10–500 znaků"})

    # Rate limit
    count_today = db.count_logs_today(user["id"], category)
    if count_today >= DAILY_LOG_LIMIT:
        return JSONResponse({"status": "error", "message": f"Denní limit {DAILY_LOG_LIMIT} záznamy/kategorii dosažen"})

    # Handle file upload
    screenshot_path = None
    if proof and proof.filename:
        content = await proof.read()
        if len(content) > MAX_FILE_SIZE:
            return JSONResponse({"status": "error", "message": "Soubor je příliš velký (max 4MB)"})

        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(proof.filename)[1] or ".jpg"
        filename = f"{uuid.uuid4()}{ext}"
        screenshot_path = os.path.join(UPLOADS_DIR, filename)
        with open(screenshot_path, "wb") as f:
            f.write(content)

    job_id = str(uuid.uuid4()).replace("-", "")[:14]
    enqueue_log(job_id, user["id"], category, activity, screenshot_path, duration)

    if _is_alpine(request):
        # Return fresh data
        fresh_user = db.get_user_by_id(user["id"])
        ctx = _build_dashboard_context(fresh_user)
        ctx.pop("request", None)
        ctx.pop("error", None)
        return JSONResponse({"status": "success", **ctx})

    return RedirectResponse("/dashboard", status_code=302)


@router.post("/friends/add")
async def add_friend(request: Request, friend: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Nepřihlášen"}, status_code=401)

    target = db.get_user_by_username(friend.strip())
    if not target:
        return JSONResponse({"status": "error", "message": "Uživatel nenalezen"})
    if target["id"] == user["id"]:
        return JSONResponse({"status": "error", "message": "Nemůžeš přidat sebe"})

    db.add_friend(user["id"], target["id"])
    friends = db.get_friends(user["id"])

    if _is_alpine(request):
        return JSONResponse({"status": "success", "friends": friends})
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/groups/create")
async def create_group(
    request: Request,
    groupname: str = Form(...),
    members: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Nepřihlášen"}, status_code=401)

    member_ids = [user["id"]]
    for username in members.split(","):
        username = username.strip()
        if username:
            u = db.get_user_by_username(username)
            if u:
                member_ids.append(u["id"])

    db.create_group(groupname.strip(), user["id"], member_ids)
    groups = db.get_groups_for_user(user["id"])

    if _is_alpine(request):
        return JSONResponse({"status": "success", "groups": groups})
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/settings/theme")
async def set_theme(request: Request, theme: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error"}, status_code=401)

    if theme not in ("light", "dark"):
        return JSONResponse({"status": "error", "message": "Neplatné téma"})

    db.update_user_theme(user["id"], theme)
    return JSONResponse({"status": "success"})


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    queue_id: str = Form(...),
    message: str = Form(...),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error"}, status_code=401)

    if len(message.strip()) < 5:
        return JSONResponse({"status": "error", "message": "Zpráva je příliš krátká"})

    db.create_feedback(user["id"], queue_id, message.strip())

    if _is_alpine(request):
        return JSONResponse({"status": "success"})
    return RedirectResponse("/requests", status_code=302)
