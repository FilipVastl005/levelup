import sys
import os
from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Ensure we can import from the parent directory's services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import db

app = FastAPI(title="Eggman Studio Home")
templates = Jinja2Templates(directory="home_app/templates")
app.mount("/static", StaticFiles(directory="home_app/static"), name="static")

def _is_alpine(request: Request) -> bool:
    return request.headers.get("X-Alpine-Request") == "true"

@app.get("/")
async def home(request: Request):
    token = request.cookies.get("session_token")
    user = None
    if token:
        user = db.get_session_user(token)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    user = db.authenticate_user(email, password)
    if not user:
        if _is_alpine(request):
            return JSONResponse({"status": "error", "message": "Nesprávný email nebo heslo"})
        return templates.TemplateResponse("login.html", {"request": request, "error": "Nesprávný email nebo heslo"})

    token = db.create_session(user["id"])
    
    # Check if there is a 'next' parameter to redirect back to the app the user came from
    next_url = request.query_params.get("next", "/")
    
    if _is_alpine(request):
        resp = JSONResponse({"status": "success", "redirect": next_url})
        resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
        return resp

    resp = RedirectResponse(next_url, status_code=302)
    resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
    return resp

@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})

@app.post("/signup")
async def signup(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if len(username) < 3:
        msg = "Uživatelské jméno musí mít alespoň 3 znaky"
        if _is_alpine(request): return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    if len(password) < 6:
        msg = "Heslo musí mít alespoň 6 znaků"
        if _is_alpine(request): return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    user = db.create_user(username, email, password)
    if not user:
        msg = "Email nebo uživatelské jméno již existuje"
        if _is_alpine(request): return JSONResponse({"status": "error", "message": msg})
        return templates.TemplateResponse("signup.html", {"request": request, "error": msg})

    token = db.create_session(user["id"])
    
    if _is_alpine(request):
        resp = JSONResponse({"status": "success", "redirect": "/"})
        resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
        return resp

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session_token", token, httponly=True, max_age=7 * 86400, samesite="lax")
    return resp

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        db.delete_session(token)
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("session_token")
    return resp
