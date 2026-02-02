# security.py
import bcrypt

def hash_api_key(api_key: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(api_key.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    return bcrypt.checkpw(api_key.encode("utf-8"), api_key_hash.encode("utf-8"))
