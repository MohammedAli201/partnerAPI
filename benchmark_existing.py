"""Local two-process HTTP benchmark; explicit disposable PostgreSQL only.

Run with requirements-payout.lock and CENTRAL_TEST_CLUSTER_URL. Synthetic
openings and callback faults never contact a phone or an external endpoint.
"""
import asyncio
import collections
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import psutil
import pytest
from sqlalchemy.orm import sessionmaker
import backend_core as c
import registered_webhooks as hooks
from security import generate_api_key,verify_api_key


def percentiles(values):
    values=sorted(values)
    return {str(p):round(values[min(len(values)-1,int((len(values)-1)*p/100))],2) for p in (50,95,99)} if values else {}


async def scenario(base,keys,rate,seconds,single=False):
    samples=collections.defaultdict(list)
    statuses=collections.Counter()
    semaphore=asyncio.Semaphore(160)
    async with httpx.AsyncClient(base_url=base,timeout=30,limits=httpx.Limits(max_connections=160)) as http:
        async def request(method,url,operation,**kwargs):
            started=time.perf_counter()
            try:
                response=await http.request(method,url,**kwargs)
                statuses[f'{operation}:{response.status_code}']+=1
                return response
            except httpx.HTTPError:
                statuses[f'{operation}:transport_error']+=1
            finally:
                samples[operation].append(1000*(time.perf_counter()-started))
        async def job(i):
            async with semaphore:
                headers={'X-API-Key':keys[0 if single else i%len(keys)]}
                body=dict(partner_tx_id=str(uuid4()),amount='1.00',currency='USD',recipient='+252611234567',provider='Hormuud',payout_channel='evc',request_payload={})
                accepted=await request('POST','/payouts-create','submit',headers=headers,json=body)
                if accepted is not None and accepted.status_code==201:
                    if i%10==0:
                        await request('POST','/payouts-create','duplicate',headers=headers,json=body)
                    await request('GET','/payouts/'+accepted.json()['id'],'poll',headers=headers)
                if i%10==0:
                    await request('POST','/payouts-create','invalid_auth',headers={'X-API-Key':'invalid'},json=body)
        started=time.perf_counter()
        jobs=[]
        for i in range(rate*seconds):
            await asyncio.sleep(max(0,started+i/rate-time.perf_counter()))
            jobs.append(asyncio.create_task(job(i)))
        await asyncio.gather(*jobs)
        duration=time.perf_counter()-started
    return dict(arrival_rate=rate,arrival_seconds=seconds,single_partner=single,duration_seconds=round(duration,3),
        submission_completions_per_second=round(len(samples['submit'])/duration,2),statuses=dict(statuses),latency_ms={k:percentiles(v) for k,v in samples.items()})


def main():
    sys.path.insert(0,str(Path('tests').resolve()))
    from test_existing_backend import pg,setup
    patch=pytest.MonkeyPatch()
    generator=pg.__wrapped__()
    engine=next(generator)
    process=None
    stop=threading.Event()
    threads=[]
    log=Path('.benchmark-http.log').open('w',encoding='utf-8')
    original_send=hooks.send
    try:
        data=setup.__wrapped__(engine,patch)
        keys=[data['key']]
        auth={}
        for legacy in (False,True):
            if legacy: patch.delenv('API_KEY_VERIFIER_SECRET',raising=False)
            else: patch.setenv('API_KEY_VERIFIER_SECRET','a'*48)
            key,prefix,verifier=generate_api_key()
            started=time.perf_counter()
            for _ in range(100): assert verify_api_key(key,verifier)
            auth['PBKDF2_120000' if legacy else 'HMAC_256bit_key']={'verification_ms':round((time.perf_counter()-started)*10,3),'samples':100}
        patch.setenv('API_KEY_VERIFIER_SECRET','a'*48)
        with engine.begin() as db:
            c.deposit(db,data['partner'],10000,'synthetic-benchmark-topup','synthetic://benchmark-only','benchmark')
            for i in range(9):
                if i<4 and os.getenv('BENCH_KEY_MODE')!='hmac': patch.delenv('API_KEY_VERIFIER_SECRET',raising=False)
                else: patch.setenv('API_KEY_VERIFIER_SECRET','a'*48)
                key,prefix,verifier=generate_api_key()
                keys.append(key)
                partner=c.row(db,'INSERT INTO partners(name,api_key_prefix,api_key_hash,balance_available) VALUES(:name,:prefix,:hash,10000) RETURNING id',name=f'Bench {i}',prefix=prefix,hash=verifier)['id']
                review=c.opening_propose(db,partner,data['admins'][0]['id'],10000,0,'synthetic://benchmark-only')
                c.opening_approve(db,review['review_id'],data['admins'][1]['id'])
            config={k:c.row(db,f'SHOW {k}')[k] for k in ('server_version','shared_buffers','max_connections')}
            # Generate callback work without granting execution permission.
            endpoint=uuid4()
            c.run(db,"INSERT INTO webhook_endpoints(id,partner_id,url,approved_addresses,signing_secret,version) VALUES(:id,:partner,'https://synthetic.example/callback',ARRAY['93.184.216.34'],:secret,1)",id=endpoint,partner=data['partner'],secret='synthetic-secret-'+'x'*32)
            from test_existing_backend import payload
            for _ in range(30):
                p=payload(amount='1.00')
                result=c.admission(db,data['partner'],p,p.partner_tx_id,None,Decimal('.60'))
                stored=c.row(db,'SELECT * FROM payouts WHERE id=:id',id=result['id'])
                c.change(db,stored,'PROCESSING','BENCH','SYNTHETIC_CALLBACK')
        patch.setenv('API_KEY_VERIFIER_SECRET','a'*48)
        callback_counts=collections.Counter()
        def injected_send(*args):
            callback_counts['attempts']+=1
            time.sleep(1)
            if callback_counts['attempts']%2:
                callback_counts['unavailable']+=1
                raise OSError('Injected unavailable endpoint')
            callback_counts['slow_202']+=1
            return 202
        hooks.send=injected_send
        factory=sessionmaker(bind=engine)
        def callbacks():
            while not stop.is_set():
                if not hooks.deliver_next(factory): stop.wait(.1)
        threads.append(threading.Thread(target=callbacks))
        threads[-1].start()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        environment=os.environ.copy()
        environment.update(DATABASE_URL=engine.url.render_as_string(hide_password=False),SECRET_KEY='bench-session-'+uuid4().hex,EXECUTOR_TOKEN='unused',API_KEY_HASH_SECRET='unused',API_KEY_VERIFIER_SECRET='a'*48,ENVIRONMENT='test',SKIP_DB_BOOTSTRAP='true',EMBEDDED_PAYMENT_WORKERS='false',POOL_SIZE='8',MAX_OVERFLOW='4')
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port),'--workers','2','--no-access-log'],env=environment,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        base=f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                if httpx.get(base+'/payouts/no-id',timeout=.5).status_code<500: break
            except httpx.HTTPError: pass
            if process.poll() is not None: raise RuntimeError('HTTP server exited; inspect .benchmark-http.log')
            time.sleep(.1)
        resources=[]
        def monitor():
            tracked={}
            while not stop.is_set():
                try:
                    procs=[psutil.Process(process.pid)]+psutil.Process(process.pid).children(recursive=True)
                    rss=cpu=0
                    for proc in procs:
                        if proc.pid not in tracked: tracked[proc.pid]=proc; proc.cpu_percent()
                        rss+=proc.memory_info().rss
                        cpu+=tracked[proc.pid].cpu_percent()
                    with engine.connect() as db:
                        activity=c.row(db,"SELECT count(*) FILTER(WHERE wait_event_type='Lock') AS locks,count(*) FILTER(WHERE state='active') AS active FROM pg_stat_activity WHERE datname=current_database()")
                    resources.append(dict(rss_mb=round(rss/1048576,2),cpu_percent=cpu,lock_wait_connections=activity['locks'],active_connections=activity['active']))
                except psutil.Error: pass
                stop.wait(.5)
        threads.append(threading.Thread(target=monitor)); threads[-1].start()
        results=[asyncio.run(scenario(base,keys,10,20)),asyncio.run(scenario(base,keys,100,10)),asyncio.run(scenario(base,keys,100,5,True))]
        report=dict(measured_at='2026-10-09',hardware=dict(os=platform.platform(),logical_cpus=os.cpu_count(),host_memory_mb=round(psutil.virtual_memory().total/1048576)),application=dict(workers=2,pool_per_worker=8,overflow_per_worker=4,python=platform.python_version()),database=config,dataset=dict(partners=10,legacy_pbkdf2_partners=0 if os.getenv('BENCH_KEY_MODE')=='hmac' else 4,synthetic_wallets=1,opening_evidence='Synthetic only; no actual funds'),authentication=auth,scenarios=results,callback_faults=dict(callback_counts),resources=dict(samples=len(resources),peak_rss_mb=max(x['rss_mb'] for x in resources),peak_process_cpu_percent=max(x['cpu_percent'] for x in resources),max_lock_wait_connections=max(x['lock_wait_connections'] for x in resources)),limitations=['Local host and PostgreSQL; not Fly hardware','20-second steady, 10-second burst, 5-second single-partner; no soak test','Client has 160 in-flight job cap; scheduled bursts may queue on client; duration includes drain','HTTP percentiles exclude client semaphore queue time; not arrival-to-completion latency','Callback transport faults injected; no external network latency measured','No physical USSD throughput measured; no production capacity claim'])
        Path('docs').mkdir(exist_ok=True)
        Path('docs/existing-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        stop.set()
        for thread in threads: thread.join(12)
        if process:
            for child in psutil.Process(process.pid).children(recursive=True): child.terminate()
            process.terminate(); process.wait(timeout=10)
        hooks.send=original_send
        log.close()
        patch.undo()
        try: next(generator)
        except StopIteration: pass


if __name__=='__main__': main()
