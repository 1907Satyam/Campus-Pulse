import os
import shutil
import datetime
from typing import List
from io import BytesIO

from fastapi import FastAPI, Request, Depends, Form, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from jose import jwt, JWTError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
import qrcode

# 1. IMPORTS
from app.database import engine, get_db
from app.models import models 
from app.routers import auth_routes, event_routes
from app.auth import SECRET_KEY, ALGORITHM

# 2. CREATE TABLES
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Campus Pulse")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# 3. ROUTERS
app.include_router(auth_routes.router)
app.include_router(event_routes.router)

# --- HELPER: GET USER ---
def get_current_user(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token: return None
    if token.startswith("Bearer "): token = token[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    except JWTError: return None

# --- ERROR HANDLER ---
@app.exception_handler(StarletteHTTPException)
async def custom_404(request, exc):
    if exc.status_code == 404: 
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ==========================
#      WEBSITE ROUTES
# ==========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): 
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request): 
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

@app.get("/event-details", response_class=HTMLResponse)
async def event_details_page(request: Request): 
    return templates.TemplateResponse("event_details.html", {"request": request})

# --- PROFILE COMPLETION ---
@app.get("/complete-profile", response_class=HTMLResponse)
async def complete_profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    if user.mobile_number and user.branch: return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("register_details.html", {"request": request, "user": user})

@app.post("/complete-profile")
async def save_profile(request: Request, mobile: str = Form(...), branch: str = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        user.mobile_number = mobile
        user.branch = branch
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)

# --- NEW EVENT REGISTRATION ---
@app.get("/register-event/{event_id}", response_class=HTMLResponse)
async def show_event_registration_form(event_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    
    # Check if Basic Profile is done
    if not user.mobile_number or not user.branch:
        return RedirectResponse(url="/complete-profile")
        
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    return templates.TemplateResponse("event_register.html", {"request": request, "user": user, "event": event})

@app.post("/register-event/{event_id}")
async def process_event_registration(
    event_id: int, request: Request,
    participation_type: str = Form(...),
    participation_category: str = Form(...),
    team_name: str = Form(None),
    team_members: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")

    existing = db.query(models.Registration).filter(
        models.Registration.user_id == user.id, 
        models.Registration.event_id == event_id
    ).first()

    if existing:
        return templates.TemplateResponse("event_register.html", {
            "request": request, "user": user, "event": existing.event, "error": "You are already registered!"
        })

    # Save new details
    new_reg = models.Registration(
        user_id=user.id,
        event_id=event_id,
        participation_type=participation_type,
        participation_category=participation_category,
        team_name=team_name,
        team_members=team_members,
        scan_count=0 
    )
    db.add(new_reg)
    db.commit()

    return RedirectResponse(url="/dashboard?success=1", status_code=302)

# --- USER PROFILE EDIT ---
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@app.post("/profile")
async def update_profile(
    request: Request, 
    full_name: str = Form(...), 
    mobile: str = Form(...), 
    branch: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    
    user.full_name = full_name
    user.mobile_number = mobile
    user.branch = branch
    db.commit()
    
    return templates.TemplateResponse("profile.html", {
        "request": request, 
        "user": user, 
        "message": "Profile Updated Successfully!"
    })

# ===============================
#   ADMIN & API ROUTES
# ===============================

@app.get("/admin-dashboard", response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin: return RedirectResponse(url="/login")
    events = db.query(models.Event).all()
    return templates.TemplateResponse("admin.html", {"request": request, "events": events})

# --- CREATE EVENT (HANDLES FILE UPLOADS) ---
@app.post("/admin/create-event")
async def create_event(
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    location: str = Form(...),
    date_time: str = Form(...),
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db)
):
    # 1. Handle File Uploads
    saved_filenames = []
    upload_dir = "app/static/uploads"
    os.makedirs(upload_dir, exist_ok=True) 

    for file in files:
        if file.filename:
            file_path = os.path.join(upload_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_filenames.append(f"/static/uploads/{file.filename}")

    # Use first image as main poster
    main_image = saved_filenames[0] if saved_filenames else "/static/default.jpg"

    try:
        dt_obj = datetime.datetime.strptime(date_time, "%Y-m-%dT%H:%M")
    except:
        dt_obj = datetime.datetime.now()

    new_event = models.Event(
        title=title,
        description=description,
        category=category,
        location=location,
        date_time=dt_obj,
        image_url=main_image, 
        is_active=True
    )
    db.add(new_event)
    db.commit()

    return RedirectResponse(url="/admin-dashboard", status_code=302)

# --- EDIT EVENT ROUTES ---
@app.get("/admin/edit-event/{event_id}", response_class=HTMLResponse)
async def edit_event_page(event_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin: return RedirectResponse(url="/login")
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    return templates.TemplateResponse("edit_event.html", {"request": request, "event": event})

@app.post("/admin/edit-event/{event_id}")
async def update_event(
    event_id: int, 
    title: str = Form(...), 
    description: str = Form(...),
    category: str = Form(...),
    location: str = Form(...),
    image_url: str = Form(...),
    date_time: str = Form(...),
    db: Session = Depends(get_db)
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if event:
        event.title = title
        event.description = description
        event.category = category
        event.location = location
        event.image_url = image_url
        try:
            event.date_time = datetime.datetime.strptime(date_time, "%Y-m-%dT%H:%M")
        except:
             pass 
        db.commit()
        
    return RedirectResponse(url="/admin-dashboard", status_code=302)

@app.get("/admin/event/{event_id}/users", response_class=HTMLResponse)
async def view_event_users(event_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin: return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    registrations = db.query(models.Registration).filter(models.Registration.event_id == event_id).all()
    
    return templates.TemplateResponse("event_users.html", {
        "request": request, "event": event, "registrations": registrations
    })

@app.get("/admin/toggle-block/{user_id}")
async def toggle_block_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user and user.is_admin:
        u = db.query(models.User).filter(models.User.id == user_id).first()
        if u:
            u.is_blocked = not u.is_blocked
            db.commit()
    return RedirectResponse(url=request.headers.get("referer"), status_code=302)

# --- QR & TICKETS ---

@app.get("/ticket/{event_id}", response_class=HTMLResponse)
async def generate_ticket(event_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse(url="/login")
    
    reg = db.query(models.Registration).filter(
        models.Registration.user_id == user.id, 
        models.Registration.event_id == event_id
    ).first()
    
    if not reg: return HTMLResponse("<h1>Access Denied</h1>")
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    return templates.TemplateResponse("ticket.html", {"request": request, "user": user, "event": event, "reg_id": f"CP-{event.id}-{user.id}"})

@app.get("/generate-qr/{ticket_id}")
async def generate_qr_code(ticket_id: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(ticket_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#d90429", back_color="#0a0a0a")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# --- ADMIN SCANNER (PROTECTED) ---

class TicketScan(BaseModel):
    ticket_id: str

@app.get("/scanner", response_class=HTMLResponse)
async def scanner_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("scanner.html", {"request": request})

@app.post("/api/scan-ticket")
async def scan_ticket(scan: TicketScan, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return JSONResponse(status_code=403, content={"message": "⛔ Admins Only"})

    try:
        parts = scan.ticket_id.split("-")
        if len(parts) != 3 or parts[0] != "CP":
            return JSONResponse(status_code=400, content={"message": "Invalid Ticket Format ❌"})
        
        event_id = int(parts[1])
        user_id = int(parts[2])
    except:
        return JSONResponse(status_code=400, content={"message": "Corrupt Data ⚠️"})

    reg = db.query(models.Registration).filter(
        models.Registration.event_id == event_id,
        models.Registration.user_id == user_id
    ).first()

    if not reg:
        return JSONResponse(status_code=404, content={"message": "Not Registered 🚫"})

    # INCREMENT COUNT
    reg.scan_count += 1
    db.commit()
    db.refresh(reg)

    status_msg = "Verified"
    if reg.scan_count > 1:
        status_msg = f"Already Scanned ({reg.scan_count} times)"

    return {
        "status": "success",
        "message": f"{status_msg}: {reg.student.full_name}",
        "category": reg.participation_category or "Attendee",
        "type": reg.participation_type,
        "scan_count": reg.scan_count
    }

# --- PUBLIC APIs ---

@app.get("/events/")
async def get_events(db: Session = Depends(get_db)): 
    return db.query(models.Event).all()

@app.get("/events/{event_id}")
async def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event: raise StarletteHTTPException(status_code=404, detail="Event not found")
    return event

@app.get("/api/my-registrations")
async def get_my_regs(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return []
    return db.query(models.Event).join(models.Registration).filter(models.Registration.user_id == user.id).all()

@app.get("/api/admin/stats")
async def get_admin_stats(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin: return []
    stats = db.query(models.Event.category, func.count(models.Registration.id)).join(models.Registration).group_by(models.Event.category).all()
    return [{"label": cat, "count": count} for cat, count in stats]