import sys
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User
from auth import hash_password

def main(username: str, password: str, role: str, partner_name: str = ""):
    db: Session = SessionLocal()
    try:
        if role not in ("admin", "partner"):
            raise SystemExit("role must be admin or partner")

        if db.query(User).filter(User.username == username).first():
            print("User already exists")
            return

        u = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            partner_name=partner_name if role == "partner" else None,
        )
        db.add(u)
        db.commit()
        print("Created:", username, "role:", role)
    finally:
        db.close()

if __name__ == "__main__":
    # admin: python create_user.py admin Pass123 admin
    # partner: python create_user.py partner1 Pass123 partner "Partner Company"
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
