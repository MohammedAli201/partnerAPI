import os
import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from config import get_settings
settings = get_settings()

SECRET_KEY = settings.secret_key
COOKIE_SECURE = settings.cookie_secure

# SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_LONG_RANDOM")
# COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

serializer = URLSafeSerializer(SECRET_KEY, salt="ui-session")


# ---- password helpers ----
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


# ---- session helpers ----
def make_session(uid: int, role: str) -> str:
    return serializer.dumps({"uid": uid, "role": role})


def read_session(token: str) -> dict | None:
    try:
        return serializer.loads(token)
    except BadSignature:
        return None


def set_session_cookie(resp, token: str):
    resp.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,   # True on HTTPS
        samesite="lax",
        max_age=60 * 60 * 12,   # 12 hours
        path="/",
    )


def clear_session_cookie(resp):
    resp.delete_cookie("session", path="/")


def get_session(request: Request) -> dict:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    data = read_session(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")
    return data


def require_role(role: str):
    def _dep(request: Request):
        sess = get_session(request)
        if sess.get("role") != role:
            raise HTTPException(status_code=403, detail="Forbidden")
        return sess
    return _dep


def require_login(request: Request):
    return get_session(request)


def redirect_to_login():
    return RedirectResponse("/login", status_code=303)
