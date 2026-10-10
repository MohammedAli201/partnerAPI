"""DB-backed session expiry/revocation and cookie-request CSRF protection."""
import hashlib
import hmac
import secrets
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4

from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from sqlalchemy import text

ABSOLUTE_SECONDS=12*3600
IDLE_SECONDS=30*60


def create(db,user_id,secret):
    sid=uuid4()
    csrf=secrets.token_urlsafe(32)
    db.execute(text('''INSERT INTO browser_sessions(id,user_id,csrf_hash,expires_at)
        VALUES(:id,:user,:csrf,:expires)'''),dict(id=sid,user=user_id,csrf=hashlib.sha256(csrf.encode()).hexdigest(),expires=datetime.now(timezone.utc)+timedelta(seconds=ABSOLUTE_SECONDS)))
    token=URLSafeTimedSerializer(secret,salt='ui-session-v2').dumps(dict(sid=str(sid),csrf=csrf))
    return token,csrf


def verify(db,token,secret,csrf=None):
    try:
        data=URLSafeTimedSerializer(secret,salt='ui-session-v2').loads(token,max_age=ABSOLUTE_SECONDS)
        sid=UUID(data['sid'])
    except (BadSignature,SignatureExpired,ValueError,KeyError,TypeError):
        raise HTTPException(401,'Session expired or invalid') from None
    session=db.execute(text('''UPDATE browser_sessions s SET last_seen_at=now() FROM users u
        WHERE s.id=:sid AND u.id=s.user_id AND u.is_active AND s.revoked_at IS NULL
          AND s.expires_at>now() AND s.last_seen_at>now()-make_interval(secs=>:idle)
        RETURNING s.*,u.username,u.role,u.partner_id'''),dict(sid=sid,idle=IDLE_SECONDS)).mappings().first()
    if not session:
        raise HTTPException(401,'Session expired or revoked')
    if csrf is not None and not hmac.compare_digest(hashlib.sha256(csrf.encode()).hexdigest(),session['csrf_hash']):
        raise HTTPException(403,'CSRF token invalid')
    return dict(uid=session['user_id'],role=session['role'],username=session['username'],partner_id=session['partner_id'],sid=sid)


def revoke(db,token,secret):
    try:
        data=URLSafeTimedSerializer(secret,salt='ui-session-v2').loads(token)
        sid=UUID(data['sid'])
    except (BadSignature,ValueError,KeyError,TypeError):
        return
    db.execute(text('UPDATE browser_sessions SET revoked_at=now() WHERE id=:id'),dict(id=sid))


def install(app,settings,session_factory):
    from starlette.responses import JSONResponse
    origins=set(settings.cors_origins)
    if settings.environment=='production' and '*' in origins:
        raise RuntimeError('Production CORS must list approved origins')
    if settings.environment=='production' and len(settings.secret_key)<32:
        raise RuntimeError('Production SECRET_KEY must have at least 32 characters')
    @app.middleware('http')
    async def csrf_guard(request,call_next):
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            same=str(request.base_url).rstrip('/')
            if origin and origin!=same and origin not in origins:
                return JSONResponse({'detail':'Origin not approved'},status_code=403)
            if request.headers.get('sec-fetch-site')=='cross-site' and origin not in origins:
                return JSONResponse({'detail':'Cross-site request denied'},status_code=403)
            token=request.cookies.get('session')
            if token and request.url.path!='/login':
                csrf=request.headers.get('x-csrf-token')
                if not csrf:
                    return JSONResponse({'detail':'X-CSRF-Token required'},status_code=403)
                import asyncio
                def check():
                    with session_factory.begin() as db:
                        verify(db,token,settings.secret_key,csrf)
                try:
                    await asyncio.to_thread(check)
                except HTTPException as error:
                    return JSONResponse({'detail':error.detail},status_code=error.status_code)
        response = await call_next(request)
        if request.url.path.startswith('/admin'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
