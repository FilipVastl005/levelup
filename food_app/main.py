import sys
import os
import json
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Ensure we can import from the parent directory's services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import db, off

app = FastAPI(title="Víte, co jíte?", root_path="/food")
templates = Jinja2Templates(directory="food_app/templates")
app.mount("/static", StaticFiles(directory="food_app/static"), name="static")

async def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token: return None
    return db.get_session_user(token)

@app.get("/")
async def index(request: Request):
    user = await get_current_user(request)
    if not user:
        # Redirect to the main login page with a next parameter
        return RedirectResponse("/login?next=/food/")
    
    scans = db.get_user_scans(user["id"])
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": user,
        "scans": scans
    })

@app.get("/scan")
async def scan_page(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/food/scan")
    
    shops = db.get_all_shops()
    return templates.TemplateResponse("scan.html", {
        "request": request,
        "user": user,
        "shops": shops
    })

@app.get("/lookup/{ean}")
async def lookup(ean: str):
    # 1. Local Cache
    product = db.get_product_by_ean(ean)
    if product:
        # If it was returned from DB, parse nutrition JSON
        product = dict(product)
        if product.get("nutrition"):
            try:
                product["nutrition"] = json.loads(product["nutrition"])
            except:
                product["nutrition"] = {}
        return {"status": "success", "product": product, "source": "local"}
    
    # 2. Open Food Facts
    off_data = await off.get_off_product(ean)
    if off_data:
        # Save to local cache
        db.create_product(
            ean=ean,
            name=off_data["name"],
            brand=off_data["brand"],
            ingredients=off_data["ingredients"],
            allergens=off_data["allergens"],
            nutrition=json.dumps(off_data["nutrition"]),
            nutrition_score=off_data["nutrition_score"]
        )
        return {"status": "success", "product": off_data, "source": "OFF"}
    
    # 3. Not found - in a real app, we'd trigger a background scraper here
    return {"status": "not_found", "message": "Produkt nebyl nalezen v lokální databázi ani v OFF."}

@app.post("/save-scan")
async def save_scan(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Nejste přihlášeni"}, status_code=401)
    
    data = await request.json()
    ean = data.get("ean")
    shop_id = data.get("shop_id")
    price = data.get("price")
    
    if not ean:
        return JSONResponse({"status": "error", "message": "Chybí EAN"}, status_code=400)
    
    db.record_scan(user["id"], ean, shop_id, price)
    return {"status": "success"}
