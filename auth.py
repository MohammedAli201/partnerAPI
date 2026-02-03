import os
import bcrypt
from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

serializer = URLSafeSerializer(SECRET_KEY, salt="session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def make_session(data: dict) -> str:
    # data example: {"uid": 1, "role": "admin"}
    return serializer.dumps(data)


def read_session(token: str) -> dict | None:
    try:
        return serializer.loads(token)
    except BadSignature:
        return None


def set_session_cookie(resp, token: str):
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        secure=COOKIE_SECURE,       # true in production HTTPS
        samesite="lax",
        max_age=60 * 60 * 12,       # 12 hours
        path="/",
    )


def clear_session_cookie(resp):
    resp.delete_cookie("session", path="/")


def get_current_user_session(request: Request) -> dict:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401)
    data = read_session(token)
    if not data:
        raise HTTPException(status_code=401)
    return data


def require_role(role: str):
    """
    Dependency: require_role('admin') or require_role('partner')
    """
    def _inner(request: Request):
        sess = get_current_user_session(request)
        if sess.get("role") != role:
            raise HTTPException(status_code=403)
        return sess
    return _inner


def redirect_if_not_logged_in(request: Request, to="/login"):
    token = request.cookies.get("session")
    if not token or not read_session(token):
        return RedirectResponse(to, status_code=303)
    return None
