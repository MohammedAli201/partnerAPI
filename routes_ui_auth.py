from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import User
from auth_session import verify_password, make_session, set_session_cookie, clear_session_cookie

templates = Jinja2Templates(directory="templates")
router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    error = request.query_params.get("error")
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@router.post("/login")
def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()

    if (
        not user
        or not user.is_active
        or not user.password_hash
        or not verify_password(password, user.password_hash)
    ):
        return RedirectResponse("/login?error=1", status_code=303)

    token = make_session(user.id, user.role)
    next_url = "/admin" if user.role == "admin" else "/partner"

    resp = RedirectResponse(next_url, status_code=303)
    set_session_cookie(resp, token)
    return resp

@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    clear_session_cookie(resp)
    return resp
