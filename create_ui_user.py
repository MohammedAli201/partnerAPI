import sys
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User
from auth_session import hash_password

def main(username: str, password: str, role: str):
    if role not in ("admin", "partner"):
        raise SystemExit("role must be admin or partner")

    db: Session = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            print("User exists")
            return

        u = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(u)
        db.commit()
        print("Created user:", username, "role:", role)
    finally:
        db.close()

if __name__ == "__main__":
    # python create_ui_user.py admin MyPass admin
    main(sys.argv[1], sys.argv[2], sys.argv[3])
