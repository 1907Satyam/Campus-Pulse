from app.database import SessionLocal
from app.models import models

def set_admin(email):
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        user.is_admin = True
        db.commit()
        print(f"Success: {email} is now an Admin!")
    else:
        print("User not found. Sign up in the browser first.")
    db.close()

if __name__ == "__main__":
    email_to_promote = input("Enter the email you signed up with: ")
    set_admin(email_to_promote)