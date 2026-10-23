# File: superuser.py
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine 
from app.models import models
from passlib.context import CryptContext

# --- CONFIGURATION ---
ADMIN_EMAIL = "shrutisharma2308@gmail.com"
ADMIN_PASSWORD = "gungun1802"
ADMIN_NAME = "Master Admin"
# ---------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_super_user():
    db = SessionLocal()
    try:
        # 1. Check if admin exists
        existing_user = db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first()
        if existing_user:
            print(f"⚠️ User {ADMIN_EMAIL} already exists.")
            return

        # 2. Hash password
        print(f"Hashing password for {ADMIN_EMAIL}...")
        hashed_pw = pwd_context.hash(ADMIN_PASSWORD)

        # 3. Create User
        db_user = models.User(
            email=ADMIN_EMAIL,
            hashed_password=hashed_pw, # <--- CHANGED THIS NAME
            full_name=ADMIN_NAME,
            is_admin=True, 
            is_blocked=False,
            mobile_number="0000000000",
            branch="Admin Dept"
        )

        db.add(db_user)
        db.commit()
        print(f"✅ SUCCESS! Superuser created: {ADMIN_EMAIL}")

    except Exception as e:
        print(f"❌ ERROR Creating Superuser: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    create_super_user()