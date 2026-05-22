"""
routers/auth.py — Login, signup, logout
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from services import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _is_alpine(request: Request) -> bool:
    return request.headers.get("X-Alpine-Request") == "true"


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(request: Request, response: Response):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", "")).strip()

    user = db.authenticate_user(email, password)
    if not user:
        if _is_alpine(request):
            return JSONResponse({"status": "error", "message": "Nesprávný email nebo heslo"})
        return templates.TemplateResponse("login.html", {"request": request, "error": "Nesprávný email nebo heslo"})

    token = db.create_session(user["id"])

    if _is_alpine(request):
        resp = JSONResponse({"status": "success", "redirect": "/dashboard"})
        resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
        return resp

    resp = RedirectResponse("/dashboard", status_code=302)
    resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
    return resp


@router.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@router.post("/signup")
async def signup(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", "")).strip()

    if len(username) < 3:
        msg = "Uživatelské jméno musí mít alespoň 3 znaky"
        if _is_alpine(request):
            return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    if len(password) < 6:
        msg = "Heslo musí mít alespoň 6 znaků"
        if _is_alpine(request):
            return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    user = db.create_user(username, email, password)
    if not user:
        msg = "Email nebo uživatelské jméno již existuje"
        if _is_alpine(request):
            return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    token = db.create_session(user["id"])

    if _is_alpine(request):
        resp = JSONResponse({"status": "success", "redirect": "/dashboard"})
        resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
        return resp

    resp = RedirectResponse("/dashboard", status_code=302)
    resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
    return resp


@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        db.delete_session(token)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_token")
    return resp
