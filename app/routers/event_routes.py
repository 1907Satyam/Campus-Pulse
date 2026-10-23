from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import models
import shutil
import os
from datetime import datetime

router = APIRouter(prefix="/events", tags=["Events"])

# Route to handle the poster image upload
@router.post("/upload-poster")
async def upload_poster(file: UploadFile = File(...)):
    # Define where to save the image
    upload_dir = "app/static/uploads"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    file_path = os.path.join(upload_dir, file.filename)
    
    # Save the file locally
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Return the URL that the frontend can use
    return {"image_url": f"/static/uploads/{file.filename}"}

# Create Event Route
@router.post("/")
def create_event(event: dict, db: Session = Depends(get_db)):
    # The frontend sends date as a String (e.g., "2026-01-02T10:00"), 
    # but SQLite needs a Python datetime Object.
    if "date_time" in event and isinstance(event["date_time"], str):
        try:
            event["date_time"] = datetime.fromisoformat(event["date_time"])
        except ValueError:
            pass

    new_event = models.Event(**event)
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event

# Get All Events Route
@router.get("/")
def get_all_events(db: Session = Depends(get_db)):
    return db.query(models.Event).filter(models.Event.is_active == True).all()

# --- NEW ROUTE ADDED HERE ---
# Get Single Event by ID (Required for "View Details" page)
@router.get("/{id}")
def get_event(id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event
# ----------------------------

# Delete Route
@router.delete("/{id}")
def delete_event(id: int, db: Session = Depends(get_db)):
    event_query = db.query(models.Event).filter(models.Event.id == id)
    event = event_query.first()
    
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    event_query.delete(synchronize_session=False)
    db.commit()
    return {"message": "Event deleted successfully"}