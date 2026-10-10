"""Shared PostgreSQL fixed-window quotas, not per-process in-memory counters."""
import time
from fastapi import HTTPException
from sqlalchemy import text

POLICY={'submit':(600,20),'poll':(1800,60),'report':(120,10)}


def take(db,identity,operation,limit,seconds):
    bucket=int(time.time())//seconds
    result=db.execute(text('''INSERT INTO rate_buckets(identity,operation,bucket,requests,expires_at)
        VALUES(:identity,:operation,:bucket,1,now()+make_interval(secs=>:ttl))
        ON CONFLICT(identity,operation,bucket) DO UPDATE SET requests=rate_buckets.requests+1
        WHERE rate_buckets.requests<:limit RETURNING requests'''),dict(identity=identity,operation=operation,bucket=bucket,ttl=seconds*2,limit=limit)).first()
    if not result:
        raise HTTPException(429,'Quota exceeded',headers={'Retry-After':str(seconds)})


def partner_quota(db,partner,path):
    operation='submit' if path=='/payouts-create' else 'report' if 'summary' in path or 'report' in path else 'poll'
    minute,burst=POLICY[operation]
    take(db,f'partner:{partner}',operation+':minute',minute,60)
    take(db,f'partner:{partner}',operation+':burst',burst,1)


def install(app,session_factory):
    from starlette.responses import JSONResponse
    import asyncio
    @app.middleware('http')
    async def abuse_guard(request,call_next):
        if request.url.path=='/health' or request.url.path.startswith('/static'):
            return await call_next(request)
        # Use the actual trusted proxy's peer address unless the server is configured
        # to trust forwarding headers from known ingress addresses. Never parse XFF here.
        ip=request.client.host if request.client else 'unknown'
        def check():
            with session_factory.begin() as db:
                take(db,f'ip:{ip}','abuse',12000,60)
                if request.url.path=='/login' and request.method=='POST':
                    take(db,f'ip:{ip}','login',20,60)
        try:
            await asyncio.to_thread(check)
        except HTTPException as error:
            return JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
        return await call_next(request)
