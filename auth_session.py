import os
import bcrypt
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from config import get_settings
from database import SessionLocal
from browser_security import create,verify,revoke
settings = get_settings()

SECRET_KEY = settings.secret_key
COOKIE_SECURE = settings.cookie_secure or settings.environment=='production'

# SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_LONG_RANDOM")
# COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"



# ---- password helpers ----
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


# ---- session helpers ----
def make_session(uid: int, role: str, db=None) -> str:
    if db is not None:
        token,_=create(db,uid,SECRET_KEY)
        return token
    with SessionLocal.begin() as session:
        token,_=create(session,uid,SECRET_KEY)
        return token


def read_session(token: str) -> dict | None:
    try:
        with SessionLocal.begin() as db:
            return verify(db,token,SECRET_KEY)
    except HTTPException:
        return None


def set_session_cookie(resp, token: str):
    from itsdangerous import URLSafeTimedSerializer
    csrf=URLSafeTimedSerializer(SECRET_KEY,salt='ui-session-v2').loads(token)['csrf']
    resp.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,   # True on HTTPS
        samesite="lax",
        max_age=60 * 60 * 12,   # 12 hours
        path="/",
    )
    resp.set_cookie('csrf_token',csrf,secure=COOKIE_SECURE,httponly=False,samesite='lax',max_age=60*60*12,path='/')


def clear_session_cookie(resp):
    resp.delete_cookie("session", path="/")
    resp.delete_cookie('csrf_token',path='/')


def revoke_session(token):
    with SessionLocal.begin() as db:
        revoke(db,token,SECRET_KEY)


def get_session(request: Request) -> dict:
    cached=getattr(request.state,'payout_session',None)
    if cached:
        return cached
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    data = read_session(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")
    from quotas import take
    with SessionLocal.begin() as db:
        operation='browser-write' if request.method in ('POST','PUT','PATCH','DELETE') else 'browser-read'
        take(db,f"user:{data['uid']}",operation,240 if operation=='browser-write' else 1800,60)
    request.state.payout_session=data
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
