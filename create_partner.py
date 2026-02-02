from sqlalchemy.orm import Session
from database import SessionLocal, Base, engine
from models import Partner
from security import hash_api_key
import secrets

Base.metadata.create_all(bind=engine)

def main():
    db: Session = SessionLocal()

    api_key = secrets.token_urlsafe(32)
    p = Partner(
        name="Test Partner",
        api_key_hash=hash_api_key(api_key),
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    db.close()

    print("Partner ID:", p.id)
    print("API Key (save this, cannot be recovered):", api_key)

if __name__ == "__main__":
    main()
