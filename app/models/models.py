from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    
    # Matches your existing auth system
    hashed_password = Column(String) 
    
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    mobile_number = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    
    registrations = relationship("Registration", back_populates="student")

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    category = Column(String)
    location = Column(String)
    image_url = Column(String)
    date_time = Column(DateTime)
    
    # Required for event visibility logic
    is_active = Column(Boolean, default=True) 
    
    registrations = relationship("Registration", back_populates="event")

class Registration(Base):
    __tablename__ = "registrations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))
    
    # Team Registration Fields
    participation_type = Column(String, default="Solo") 
    participation_category = Column(String, nullable=True)
    team_name = Column(String, nullable=True)
    team_members = Column(String, nullable=True)

    # --- NEW: Stores the specific count for this ticket ---
    scan_count = Column(Integer, default=0) 

    student = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")