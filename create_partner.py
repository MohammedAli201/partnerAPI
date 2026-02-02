# createpartner.py
import sys
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Partner
from security import generate_api_key
from database import SessionLocal
from models import Partner
from security import generate_api_key
def main():
    if len(sys.argv) < 2:
        print("Usage: python createpartner.py 'Partner Name'")
        sys.exit(1)

    name = sys.argv[1].strip()
    display_key, prefix, stored_hash = generate_api_key()

    db: Session = SessionLocal()
    try:
        p = Partner(
            name=name,
            api_key_prefix=prefix,
            api_key_hash=stored_hash,
            is_active=True,
        )
        db.add(p)
        db.commit()
        db.refresh(p)

        print("Partner created:")
        print("  id:", p.id)
        print("  name:", p.name)
        print("\nAPI Key (give to partner, store once):")
        print(display_key)
        print("\nIMPORTANT: You will not be able to show this key again.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
