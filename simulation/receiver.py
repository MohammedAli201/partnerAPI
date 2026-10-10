"""Real HTTP, exact-byte HMAC verification and durable per-partner event stores."""
import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import Response

root=Path(os.environ['SIMULATION_RUN_DIR'])
secrets=json.loads((root/'credentials.json').read_text())['webhook_secrets']
settings=json.loads(os.getenv('SIMULATION_PARTNER_SETTINGS','{}'))
app=FastAPI(docs_url=None,redoc_url=None)

def connect(name):
    db=sqlite3.connect(root/(name+'-events.sqlite3'),timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE IF NOT EXISTS receipts(event_id TEXT PRIMARY KEY,payout_id TEXT,status TEXT,raw BLOB,received_at REAL);
    CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,event_id TEXT,received_at REAL,valid INTEGER,response_code INTEGER);
    CREATE TABLE IF NOT EXISTS current(payout_id TEXT PRIMARY KEY,status TEXT,event_timestamp TEXT);''')
    return db
for name in secrets:
    connect(name).close()

@app.get('/health')
def health(): return {'ok':True}

@app.post('/{name}')
async def receive(name: str,request: Request):
    if name not in secrets: return Response(status_code=404)
    raw=await request.body()
    timestamp=request.headers.get('x-jubatech-timestamp','')
    nonce=request.headers.get('x-jubatech-nonce','')
    signed=(timestamp+'.'+nonce+'.').encode()+raw
    signature=hmac.new(secrets[name].encode(),signed,hashlib.sha256).hexdigest()
    try: fresh=abs(time.time()-int(timestamp))<=300
    except ValueError: fresh=False
    valid=fresh and bool(nonce) and hmac.compare_digest(signature,request.headers.get('x-jubatech-signature',''))
    try: event=json.loads(raw,parse_float=Decimal); eid=event['event_id']
    except (ValueError,KeyError): return Response(status_code=400)
    db=connect(name)
    with db:
        attempt=db.execute('SELECT count(*) FROM deliveries WHERE event_id=?',(eid,)).fetchone()[0]+1
        fault=int(hashlib.sha256((event.get('recipient','')+'|'+event.get('status','')).encode()).hexdigest()[:8],16)%20
        code=202
        if not valid: code=401
        elif attempt==1 and name=='britannia' and fault<int(settings.get(name,{}).get('failure_buckets',3)): code=500
        elif attempt==1 and name=='liberty' and fault<int(settings.get(name,{}).get('failure_buckets',3)): code=503
        elif attempt==1 and name=='liberty' and fault==int(settings.get(name,{}).get('lost_response_bucket',3)): code=0
        db.execute('INSERT INTO deliveries(event_id,received_at,valid,response_code) VALUES(?,?,?,?)',(eid,time.time(),int(valid),code))
        if valid and code not in (500,503):
            db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)',(eid,event['provider_reference'],event['status'],raw,time.time()))
            old=db.execute('SELECT status,event_timestamp FROM current WHERE payout_id=?',(event['provider_reference'],)).fetchone()
            final={'Paid','Failed','Rejected','Cancelled'}
            advance=not old or (old[0] not in final and event['timestamp']>=old[1] and (old[0]!='Unknown' or event['status'] in final))
            if advance:
                db.execute('INSERT INTO current VALUES(?,?,?) ON CONFLICT(payout_id) DO UPDATE SET status=excluded.status,event_timestamp=excluded.event_timestamp',(event['provider_reference'],event['status'],event['timestamp']))
    db.close()
    if code==0:
        # The receiver persisted this event, but its response exceeds the sender
        # deadline. Sender sees an actual timeout and retries the stable event ID.
        await asyncio.sleep(6)
    if name=='nordic': await asyncio.sleep(float(settings.get(name,{}).get('ack_delay_seconds',.02)))
    return Response(status_code=401 if not valid else code or 202)
