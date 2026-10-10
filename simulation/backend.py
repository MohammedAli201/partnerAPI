"""Actual main:app with a narrowly scoped local callback transport adapter."""
import os
import threading
from urllib.parse import urlsplit
import httpx
from sqlalchemy import create_engine,text

if os.getenv('ENVIRONMENT')!='simulation' or not os.getenv('SIMULATION_RUN_ID'):
    raise RuntimeError('This entry point is for disposable simulation only')
engine=create_engine(os.environ['DATABASE_URL'])
if not engine.url.database.startswith('payout_e2e_') or engine.url.host!='127.0.0.1':
    raise RuntimeError('Simulation requires an isolated local database')
with engine.connect() as db:
    if db.execute(text('SELECT run_id FROM simulation_marker')).scalar()!=os.environ['SIMULATION_RUN_ID']:
        raise RuntimeError('Disposable database ownership marker mismatch')
engine.dispose()
import registered_webhooks as hooks
NAMES=('atlas','britannia','liberty','nordic')
URLS={f'https://{name}.simulation.invalid/events':name for name in NAMES}
original_resolve=hooks.resolve
local=threading.local()
def resolve(url):
    if url not in URLS: raise ValueError('Simulation endpoint not allowlisted')
    return ['93.184.216.34']
def send(url,approved,body,headers):
    if url not in URLS or approved!=['93.184.216.34']: raise ValueError('Simulation destination mismatch')
    # No arbitrary URLs/proxies: actual signed HTTP goes only to owned loopback
    # receiver. Production's TLS/DNS/IP-pinning implementation is not modified.
    receiver=os.environ['SIMULATION_RECEIVER']
    parsed=urlsplit(receiver)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1': raise RuntimeError('Local receiver only')
    if not hasattr(local,'client'):
        local.client=httpx.Client(timeout=5,trust_env=False,follow_redirects=False)
    return local.client.post(receiver+'/'+URLS[url],content=body,headers=headers).status_code
hooks.resolve=resolve
hooks.send=send
from main import app
