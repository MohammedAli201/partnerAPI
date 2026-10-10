"""Run exactly 10,000 payouts against actual main:app and owned local PostgreSQL.

python -m simulation.run --profile mixed --period 120 --phones 10
"""
import argparse
import asyncio
import collections
import hashlib
import json
import os
import random
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

import bcrypt
import httpx
import psutil
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,text
import backend_core as core
from browser_security import create as create_session
from simulation.fixtures import PARTNERS,generate,money
from worker_simulator import Journal


def percentile(values):
    ordered=sorted(values)
    return {str(p):round(ordered[min(len(ordered)-1,int((len(ordered)-1)*p/100))],4) for p in (50,95,99,100)} if ordered else {}


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


class Scenario:
    def __init__(self,args,root,engine,records,environment):
        self.args,self.root,self.engine,self.records,self.env=args,root,engine,records,environment
        self.credentials={'label':'SIMULATION ONLY','webhook_secrets':{a:os.urandom(32).hex() for a,*_ in PARTNERS}}
        self.credentials['server_secrets']={key:environment[key] for key in ('SECRET_KEY','API_KEY_VERIFIER_SECRET','PAYOUT_SIMULATOR_SECRET')}
        self.processes=[]
        self.logs=[]
        self.partners={}
        self.phones=[]
        self.start=time.monotonic()
        self.http_stats=collections.Counter()
        self.http_times=[]
        self.http_evidence=[]
        self.admission_attempts=[]
        self.probes=collections.Counter()
        self.semaphore=asyncio.Semaphore(args.concurrency)
        self.partner_semaphores={a:asyncio.Semaphore(max(1,args.concurrency//4)) for a,*_ in PARTNERS}
        self.stop=asyncio.Event()
        self.hashes={r['instruction_hash']:r for r in records}
        assert len(self.hashes)==10000,'Synthetic execution hashes must identify manifest instructions uniquely'
        self.operator=sqlite3.connect(root/'operator.sqlite3')
        self.operator.execute('PRAGMA journal_mode=WAL')
        self.operator.execute('PRAGMA synchronous=FULL')
        self.operator.executescript('''CREATE TABLE effects(payout_key TEXT PRIMARY KEY,attempt_id TEXT UNIQUE,wallet_id TEXT,amount_minor INTEGER,receipt TEXT UNIQUE,paid_at REAL);
        CREATE TABLE sessions(attempt_id TEXT PRIMARY KEY,phone TEXT,started REAL,finished REAL,neutralized INTEGER DEFAULT 0);
        CREATE TABLE violations(reason TEXT);
        CREATE TABLE fault_events(kind TEXT,attempt_id TEXT,created_at REAL);''')
        self.workers_done=0
        self.executions=collections.Counter()
        self.failure=None
        self.faults={}
        unknown=[r for r in records if r['initial_outcome']=='UNKNOWN']
        for i,r in enumerate(unknown): r['operator_may_pay']=i<150
        self.fault_retry=next(r for r in records if r['initial_outcome']=='RETRY')['instruction_hash']
        self.fault_expiry=unknown[0]['instruction_hash']
        self.fault_restart=unknown[1]['instruction_hash']

    def persist_credentials(self):
        path=self.root/'credentials.json'
        path.write_text(json.dumps(self.credentials,indent=2),encoding='utf-8')
        os.chmod(path,0o600)

    def launch(self,module,port_number=None):
        log=(self.root/(module.replace('.','-')+'.log')).open('w',encoding='utf-8')
        self.logs.append(log)
        argv=[sys.executable,'-B','-m',module]
        if port_number is not None:
            argv=[sys.executable,'-B','-m','uvicorn',module+':app','--host','127.0.0.1','--port',str(port_number),'--no-access-log']
            if module=='simulation.backend': argv+=['--workers',str(self.args.app_workers)]
        child=subprocess.Popen(argv,env=self.env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.processes.append(child)

    async def request(self,http,method,path,kind,expected=None,**kwargs):
        deadline=time.monotonic()+self.args.drain_timeout
        tries=0
        while True:
            tries+=1
            began=time.monotonic()
            try:
                response=await http.request(method,path,**kwargs)
                self.http_stats[f'{kind}:{response.status_code}']+=1
                self.http_times.append((kind,time.monotonic()-began))
                self.http_evidence.append(dict(kind=kind,method=method,path=path,started=began-self.start,response_at=time.monotonic()-self.start,status=response.status_code,expected=expected,attempt=tries))
                if response.status_code in (429,503):
                    if time.monotonic()>deadline: raise RuntimeError(f'{kind} retry deadline expired')
                    delay=min(60,float(response.headers.get('retry-after',min(5,tries))))
                    await asyncio.sleep(delay+random.Random(tries+len(path)).random()*.2)
                    continue
                if expected is not None and response.status_code!=expected:
                    # Never log response bodies: provisioning may contain API keys.
                    raise AssertionError(f'{kind}: expected {expected}, received {response.status_code} at {path}')
                return response
            except httpx.TransportError as error:
                self.http_stats[f'{kind}:{type(error).__name__}']+=1
                self.http_evidence.append(dict(kind=kind,method=method,path=path,started=began-self.start,response_at=time.monotonic()-self.start,transport_failure=type(error).__name__,expected=expected,attempt=tries))
                if time.monotonic()>deadline: raise RuntimeError(f'{kind} transport retry deadline expired') from None
                await asyncio.sleep(min(5,tries))

    async def ready(self,url):
        async with httpx.AsyncClient(timeout=1,trust_env=False) as http:
            for _ in range(200):
                try:
                    if (await http.get(url+'/health')).status_code==200: return
                except httpx.HTTPError: pass
                if any(p.poll() is not None for p in self.processes): raise RuntimeError('Simulation component exited; inspect private run logs')
                await asyncio.sleep(.1)
        raise RuntimeError('Simulation service startup deadline expired')

    async def provision(self,base):
        secret=self.env['SECRET_KEY']
        with self.engine.begin() as db:
            admins=[]
            for i in range(2):
                uid=core.row(db,"INSERT INTO users(username,password_hash,role,is_active) VALUES(:name,:hash,'admin',true) RETURNING id",name=f'simulation-reviewer-{i}',hash=bcrypt.hashpw(os.urandom(32).hex().encode(),bcrypt.gensalt()).decode())['id']
                token,csrf=create_session(db,uid,secret)
                admins.append((token,csrf))
        self.admins=[httpx.AsyncClient(base_url=base,timeout=self.args.timeout,trust_env=False,cookies={'session':token},headers={'X-CSRF-Token':csrf}) for token,csrf in admins]
        for alias,name,origin,count,burst in PARTNERS:
            result=await self.request(self.admins[0],'POST','/admin/create-partner','provision',200,json=dict(partner_name=name,username='simulation-'+alias,password=os.urandom(24).hex()))
            details=result.json()
            self.partners[alias]={'id':details['partner_id'],'key':details['api_key']}
            review=await self.request(self.admins[0],'POST','/admin/api/funds/opening/propose','opening',200,json=dict(partner_id=details['partner_id'],available='0.00',reserved='0.00',evidence_ref='simulation://zero-new-account'))
            await self.request(self.admins[1],'POST','/admin/api/funds/opening/'+review.json()['review_id']+'/approve','opening',200)
            funding=sum(r['amount_minor']+r['fee_minor'] for r in self.records if r['partner']==alias)+100000
            self.partners[alias]['prefund_minor']=funding
            await self.request(self.admins[0],'POST','/admin/api/funds/deposit','prefund',200,json=dict(partner_id=details['partner_id'],amount=money(funding),reference='simulation-'+self.env['SIMULATION_RUN_ID']+'-'+alias,note='simulation://synthetic-prefunding'))
            await self.request(self.admins[0],'POST','/admin/api/webhooks/register','endpoint',200,json=dict(partner_id=details['partner_id'],url=f'https://{alias}.simulation.invalid/events',signing_secret=self.credentials['webhook_secrets'][alias]))
        total_float=sum(r['amount_minor'] for r in self.records)+1000000
        with self.engine.begin() as db:
            for i in range(self.args.phones):
                wid,wallet,did=uuid4(),uuid4(),uuid4()
                token=os.urandom(32).hex()
                core.run(db,"INSERT INTO payment_workers(id,name,token_hash,simulator) VALUES(:id,:name,:hash,true)",id=wid,name=f'Simulation phone {i}',hash=hashlib.sha256(token.encode()).hexdigest())
                asset=core.account(db,f'wallet:{wallet}','WALLET','USD')
                opening=core.account(db,f'simulation-wallet-opening:{wallet}','OPENING','USD')
                core.post(db,f'simulation-wallet-opening:{wallet}','OPENING','USD',[(asset['id'],total_float),(opening['id'],-total_float)],'simulation://independent-wallet-float')
                core.run(db,"INSERT INTO payout_wallets VALUES(:id,:reference,'USD',:account,true,:observed,now())",id=wallet,reference=f'simulation-wallet-{i}',account=asset['id'],observed=total_float)
                provider,network=('Hormuud','evc') if i%2==0 else ('Somtel','edahab')
                core.run(db,'INSERT INTO payout_devices VALUES(:id,:sim,:worker,:wallet,:provider,:network,false,true)',id=did,sim=f'simulation-sim-{self.env["SIMULATION_RUN_ID"]}-{i}',worker=wid,wallet=wallet,provider=provider,network=network)
                self.phones.append(dict(id=str(did),wallet=str(wallet),worker=str(wid),token=token,opening_minor=total_float,index=i))
        await self.request(self.admins[0],'POST','/admin/api/payment-controls','unpause',200,json=dict(scope='global',identity='all',paused=False,reason='simulation://reviewed-fixtures-only'))
        self.credentials['partners']=self.partners
        self.credentials['phones']=self.phones
        self.persist_credentials()

    async def load(self,http):
        gate=asyncio.Event()
        async def send_record(record,duplicate=False):
            await gate.wait()
            await asyncio.sleep(max(0,self.start+record['scheduled']-time.monotonic()))
            queued=time.monotonic()
            async with self.partner_semaphores[record['partner']],self.semaphore:
                began=time.monotonic()
                headers={'X-API-Key':self.partners[record['partner']]['key'],'Idempotency-Key':record['key']+('-new-key' if duplicate and record['index']%20 else '')}
                response=await self.request(http,'POST','/payouts-create','duplicate' if duplicate else 'unique',201,headers=headers,json=record['body'])
                finished=time.monotonic()
                if duplicate:
                    self.probes['identical']+=1
                    record['duplicate_started']=began-self.start
                else:
                    record.update(payout_id=response.json()['id'],started=began-self.start,completed=finished-self.start,scheduling_delay=began-(self.start+record['scheduled']),client_queue_delay=began-queued)
                    self.admission_attempts.append(record)
        jobs=[]
        for i,r in enumerate(self.records):
            jobs.append(asyncio.create_task(send_record(r)))
            if i%10==0: jobs.append(asyncio.create_task(send_record(r,True)))
        self.start=time.monotonic()
        gate.set()
        await asyncio.gather(*jobs)
        assert self.probes['identical']==1000
        # Further probes are additional to all 10,000 unique instructions.
        async def probe(i):
            r=self.records[i*17]
            alias=r['partner']
            other=next(a for a in self.partners if a!=alias)
            headers={'X-API-Key':self.partners[alias]['key'],'Idempotency-Key':r['key']}
            async with self.semaphore:
                changed={**r['body'],'recipient':'+25261999999999'}
                await self.request(http,'POST','/payouts-create','conflict',409,headers=headers,json=changed)
                self.probes['conflict']+=1
                await self.request(http,'POST','/payouts-create','invalid_credentials',401,headers={'X-API-Key':'abcdefgh.'+'x'*40},json=r['body'])
                self.probes['invalid_credentials']+=1
                await self.request(http,'GET','/payouts/'+r['payout_id'],'cross_partner',404,headers={'X-API-Key':self.partners[other]['key']})
                self.probes['cross_partner']+=1
                await self.request(http,'POST','/payouts-create','malformed',422,headers=headers,json={**r['body'],'amount':'-1.00'})
                self.probes['malformed']+=1
        await asyncio.gather(*(probe(i) for i in range(100)))

    def operator_pay(self,r,cmd,phone):
        key=r['partner']+':'+r['body']['partner_tx_id']
        receipt='simulation-receipt-'+cmd['attempt_id']
        try:
            with self.operator:
                self.operator.execute('INSERT INTO effects VALUES(?,?,?,?,?,?)',(key,cmd['attempt_id'],phone['wallet'],r['amount_minor'],receipt,time.time()))
        except sqlite3.IntegrityError:
            with self.operator: self.operator.execute("INSERT INTO violations VALUES('duplicate payment effect')")
            raise AssertionError('Simulated operator rejected duplicate physical payment') from None
        return receipt

    async def contain(self,cmd,phone):
        # Independent simulated operator journal proves there is no active session.
        with self.operator:
            self.operator.execute('UPDATE sessions SET finished=?,neutralized=1 WHERE attempt_id=?',(time.time(),cmd['attempt_id']))
        paid=self.operator.execute('SELECT coalesce(sum(amount_minor),0) FROM effects WHERE wallet_id=?',(phone['wallet'],)).fetchone()[0]
        review=await self.request(self.admins[0],'POST',f'/admin/api/attempts/{cmd["attempt_id"]}/containment/propose','containment',200,json=dict(observed_minor=phone['opening_minor']-paid,evidence_ref='simulation://operator-neutralized/'+cmd['attempt_id'],physical_worker_neutralized=True))
        await self.request(self.admins[1],'POST','/admin/api/containment/'+review.json()['review_id']+'/approve','containment',200)

    async def worker(self,phone,base):
        journal=Journal(self.root/f'phone-{phone["index"]}.sqlite3')
        async with httpx.AsyncClient(base_url=base,timeout=self.args.timeout,trust_env=False,headers={'Authorization':'Bearer '+phone['token']}) as http:
            while not self.stop.is_set():
                response=await self.request(http,'POST','/internal/workers/v2/claim','claim',200,json={'device_id':phone['id']})
                cmd=response.json()['command']
                if cmd is None:
                    await asyncio.sleep(.1)
                    continue
                r=self.hashes[cmd['instruction_hash']]
                if r.get('terminal'): raise AssertionError('Terminal/UNKNOWN manifest instruction was executed again')
                attempt=r.get('execution_count',0)+1
                r['execution_count']=attempt
                self.executions['claims']+=1
                journal.record(cmd)
                with self.operator:
                    if self.operator.execute('SELECT count(*) FROM sessions WHERE phone=? AND finished IS NULL',(phone['id'],)).fetchone()[0]:
                        raise AssertionError('Overlapping simulated USSD sessions on one phone')
                    self.operator.execute('INSERT INTO sessions(attempt_id,phone,started) VALUES(?,?,?)',(cmd['attempt_id'],phone['id'],time.time()))
                outcome=r['initial_outcome']
                if outcome=='RETRY' and attempt==1:
                    if cmd['instruction_hash']==self.fault_retry:
                        self.faults['lease_before_arm']=True
                        # Wait for the actual 120-second lease and normal reaper.
                        await asyncio.sleep(124)
                        stale=journal.result(cmd,'DEFINITE_FAILURE_BEFORE_SEND','BEFORE_ARM')
                        await self.request(http,'POST','/internal/workers/v2/results','prearm_stale',202,json=stale)
                    else:
                        result=journal.result(cmd,'RETRYABLE_FAILURE_BEFORE_SEND','BEFORE_ARM')
                        await self.request(http,'POST','/internal/workers/v2/results','retry_before_arm',202,json=result)
                    with self.operator: self.operator.execute('UPDATE sessions SET finished=? WHERE attempt_id=?',(time.time(),cmd['attempt_id']))
                    continue
                if outcome=='FAILURE':
                    result=journal.result(cmd,'DEFINITE_FAILURE_BEFORE_SEND','BEFORE_ARM')
                    await self.request(http,'POST','/internal/workers/v2/results','definitive_failure',202,json=result)
                    r['terminal']='FAILED'
                else:
                    journal.mark(cmd['attempt_id'],'ARM_REQUESTED')
                    await self.request(http,'POST',f'/internal/workers/v2/attempts/{cmd["attempt_id"]}/arm','arm',200,json={k:cmd[k] for k in ('lease_generation','instruction_hash')})
                    journal.mark(cmd['attempt_id'],'MAY_HAVE_SUBMITTED')
                    delay=(self.args.session_seconds if self.args.mode=='realistic' else self.args.accelerated_delay)*(3 if outcome=='DELAYED' else 1)
                    while delay>0:
                        step=min(delay,20)
                        await asyncio.sleep(step)
                        delay-=step
                        if delay>0 or outcome=='DELAYED':
                            await self.request(http,'POST',f'/internal/workers/v2/attempts/{cmd["attempt_id"]}/heartbeat','heartbeat',200,json={'lease_generation':cmd['lease_generation']})
                    reference=self.operator_pay(r,cmd,phone) if outcome!='UNKNOWN' or r['operator_may_pay'] else None
                    if outcome=='UNKNOWN':
                        if cmd['instruction_hash']==self.fault_expiry:
                            self.faults['lease_after_arm']=True
                            await asyncio.sleep(124)
                        if cmd['instruction_hash']==self.fault_restart:
                            self.faults['worker_restart_after_operator_payment']=True
                            journal.db.close()
                            journal=Journal(self.root/f'phone-{phone["index"]}.sqlite3')
                            result=dict(journal.pending())[cmd['attempt_id']]
                        else: result=journal.result(cmd,'UNKNOWN','UNKNOWN')
                        await self.request(http,'POST','/internal/workers/v2/results','unknown',202,json=result)
                        r['terminal']='UNKNOWN'
                        await self.contain(cmd,phone)
                    else:
                        result=journal.result(cmd,'SUCCESS','AFTER_SEND',reference,self.env['PAYOUT_SIMULATOR_SECRET'])
                        await self.request(http,'POST','/internal/workers/v2/results','success',202,json=result)
                        r['terminal']='SENT'
                        if r['index']%100==0:
                            await self.request(http,'POST','/internal/workers/v2/results','duplicate_worker_result',202,json=result)
                            self.faults['duplicate_worker_result']=True
                            late={**result,'event_id':str(uuid4()),'lease_generation':cmd['lease_generation']+100}
                            await self.request(http,'POST','/internal/workers/v2/results','stale_worker_result',202,json=late)
                            self.faults['stale_worker_result']=True
                with self.operator:
                    self.operator.execute('UPDATE sessions SET finished=? WHERE attempt_id=?',(time.time(),cmd['attempt_id']))
                r['finished']=time.monotonic()-self.start
                self.workers_done+=1
        journal.db.close()

    async def progress(self):
        while not self.stop.is_set():
            print(f'Progress: admitted={len(self.admission_attempts)}/10000, terminal={self.workers_done}/10000, elapsed={int(time.monotonic()-self.start)}s',flush=True)
            await asyncio.sleep(30)

    async def execute(self,base):
        async with httpx.AsyncClient(base_url=base,timeout=self.args.timeout,trust_env=False,limits=httpx.Limits(max_connections=self.args.connections,max_keepalive_connections=self.args.connections)) as http:
            workers=[asyncio.create_task(self.worker(p,base)) for p in self.phones]
            progress=asyncio.create_task(self.progress())
            load=asyncio.create_task(self.load(http))
            deadline=time.monotonic()+self.args.drain_timeout
            try:
                while not load.done() or self.workers_done<10000:
                    if load.done(): load.result()
                    for task in workers:
                        if task.done(): task.result(); raise RuntimeError('Worker exited unexpectedly')
                    if time.monotonic()>deadline: raise TimeoutError('Explicit payout drain deadline expired')
                    await asyncio.sleep(1)
                await load
                # Independent negative-signature probe goes directly to receiver.
                body=b'{"event_id":"invalid-signature-probe"}'
                async with httpx.AsyncClient(timeout=5,trust_env=False) as receiver:
                    response=await receiver.post(self.env['SIMULATION_RECEIVER']+'/atlas',content=body)
                    assert response.status_code==401
                while True:
                    with self.engine.connect() as db:
                        remaining=core.row(db,"SELECT count(*) AS n FROM payout_webhook_events WHERE state<>'DELIVERED'")['n']
                    if remaining==0: break
                    if time.monotonic()>deadline: raise TimeoutError(f'Webhook drain deadline expired with {remaining} outstanding events')
                    await asyncio.sleep(2)
            finally:
                self.stop.set()
                for task in workers+[progress,load]: task.cancel()
                await asyncio.gather(*workers,progress,load,return_exceptions=True)
                for admin in self.admins: await admin.aclose()

    def verify(self):
        checks={}
        def check(name,condition):
            checks[name]=bool(condition)
        with self.engine.connect() as db:
            payouts=core.run(db,'SELECT * FROM payouts').mappings().all()
            by_id={str(p['id']):p for p in payouts}
            statuses=collections.Counter(p['status'] for p in payouts)
            check('exactly_10000_unique_payouts',len(payouts)==10000)
            check('exact_scheduled_initial_burst',sum(r['scheduled']==0 for r in self.records)==(6000 if self.args.profile=='mixed' else 10000 if self.args.profile=='burst' else 0))
            check('final_distribution',dict(statuses)=={'SENT':9200,'FAILED':500,'UNKNOWN':300})
            check('partner_scoped_uniqueness',core.row(db,'SELECT count(*) AS n FROM (SELECT partner_id,partner_tx_id FROM payouts GROUP BY partner_id,partner_tx_id HAVING count(*)>1) duplicate')['n']==0)
            check('database_reference_unique_constraint',core.row(db,"SELECT count(*) AS n FROM pg_constraint WHERE conrelid='payouts'::regclass AND conname='uq_payouts_partner_partner_tx_id' AND contype='u'")['n']==1)
            check('one_reservation_per_payout',core.row(db,'SELECT count(*) AS n FROM payout_reservations')['n']==10000)
            check('no_duplicate_operator_effects',self.operator.execute('SELECT count(*) FROM violations').fetchone()[0]==0)
            effects={r[0]:r[1] for r in self.operator.execute('SELECT payout_key,amount_minor FROM effects')}
            check('operator_effects_match_manifest',all(effects.get(r['partner']+':'+r['body']['partner_tx_id'])==r['amount_minor'] if r['terminal']=='SENT' or r.get('operator_may_pay') else r['partner']+':'+r['body']['partner_tx_id'] not in effects for r in self.records))
            check('exact_operator_effects',len(effects)==9350)
            check('intended_outcome_mapping',all(r['terminal']==('FAILED' if r['initial_outcome']=='FAILURE' else 'UNKNOWN' if r['initial_outcome']=='UNKNOWN' else 'SENT') for r in self.records))
            check('no_duplicate_financial_effects',core.row(db,"SELECT count(*) AS n FROM ledger_journals WHERE event_type='PAYOUT'")['n']==9200)
            check('journals_balance',not core.run(db,'SELECT journal_id FROM ledger_entries GROUP BY journal_id HAVING sum(amount_minor)<>0').all())
            check('no_active_execution_permissions',core.row(db,"SELECT count(*) AS n FROM payout_attempts WHERE phase IN ('CLAIMED','ARMED')")['n']==0)
            check('unknown_never_reexecuted',all(r.get('execution_count')==1 for r in self.records if r['initial_outcome']=='UNKNOWN'))
            check('no_pending_or_in_progress_jobs',core.row(db,"SELECT count(*) AS n FROM payout_queue WHERE status IN ('PENDING','IN_PROGRESS')")['n']==0)
            check('unknown_reservations_held',core.row(db,"SELECT count(*) AS n FROM payout_reservations r JOIN payouts p ON p.id=r.payout_id WHERE p.status='UNKNOWN' AND r.status='ACTIVE'")['n']==300 and core.row(db,"SELECT count(*) AS n FROM wallet_reservations r JOIN payout_attempts a ON a.id=r.attempt_id WHERE a.phase='UNKNOWN' AND r.state='ACTIVE'")['n']==300)
            check('failed_reservations_released',core.row(db,"SELECT count(*) AS n FROM payout_reservations r JOIN payouts p ON p.id=r.payout_id WHERE p.status='FAILED' AND r.status='RELEASED'")['n']==500)
            check('successful_reservations_captured',core.row(db,"SELECT count(*) AS n FROM payout_reservations r JOIN payouts p ON p.id=r.payout_id WHERE p.status='SENT' AND r.status='CAPTURED'")['n']==9200)
            events=core.run(db,'SELECT * FROM payout_webhook_events').mappings().all()
            histories=core.row(db,"SELECT count(*) AS n FROM payout_history WHERE new_status IN ('PROCESSING','SENT','FAILED','UNKNOWN','CANCELLED','REJECTED')")['n']
            check('outbox_matches_status_history',len(events)==histories)
            check('all_outbox_delivered',all(e['state']=='DELIVERED' for e in events))
            expected=collections.defaultdict(set)
            for e in events:
                alias=next(a for a,p in self.partners.items() if p['id']==e['partner_id'])
                check('event_tenant_'+str(e['event_id']),by_id[str(e['payout_id'])]['partner_id']==e['partner_id'])
                expected[alias].add(str(e['event_id']))
            per_partner={}
            delivery_latencies=[]
            for alias,name,origin,count,burst in PARTNERS:
                records=[r for r in self.records if r['partner']==alias]
                actual=[p for p in payouts if p['partner_id']==self.partners[alias]['id']]
                check(alias+'_count',len(actual)==count)
                spent=sum(r['amount_minor']+r['fee_minor'] for r in records if r['terminal']=='SENT')
                held=sum(r['amount_minor']+r['fee_minor'] for r in records if r['terminal']=='UNKNOWN')
                balance=core.row(db,"SELECT balance_minor,reserved_minor FROM ledger_accounts WHERE partner_id=:id AND kind='PARTNER'",id=self.partners[alias]['id'])
                check(alias+'_funding',balance['balance_minor']==self.partners[alias]['prefund_minor']-spent and balance['reserved_minor']==held)
                receiver=sqlite3.connect(self.root/(alias+'-events.sqlite3'))
                receipts=receiver.execute('SELECT event_id,payout_id,status,received_at FROM receipts').fetchall()
                check(alias+'_exact_unique_receipts',{r[0] for r in receipts}==expected[alias])
                current=dict(receiver.execute('SELECT payout_id,status FROM current').fetchall())
                check(alias+'_callback_final_state',all(current.get(str(p['id']))=={'SENT':'Paid','FAILED':'Failed','UNKNOWN':'Unknown'}[p['status']] for p in actual))
                created={str(e['event_id']):e['created_at'].timestamp() for e in events if e['partner_id']==self.partners[alias]['id']}
                delivery_latencies.extend(r[3]-created[r[0]] for r in receipts)
                deliveries=receiver.execute('SELECT count(*),sum(valid=0) FROM deliveries').fetchone()
                per_partner[alias]=dict(unique_payouts=len(actual),outcomes=dict(collections.Counter(p['status'] for p in actual)),webhook_unique_receipts=len(receipts),webhook_attempts=deliveries[0],signature_rejections=deliveries[1],financial_balance_minor=balance['balance_minor'],financial_reserved_minor=balance['reserved_minor'])
                receiver.close()
            for phone in self.phones:
                paid=core.row(db,"SELECT coalesce(sum(p.amount),0) AS total FROM payout_attempts a JOIN payouts p ON p.id=a.payout_id WHERE a.wallet_id=:id AND a.phase='SUCCESS'",id=phone['wallet'])['total']
                paid=core.minor(paid,'USD')
                account=core.row(db,'SELECT a.balance_minor,a.reserved_minor FROM payout_wallets w JOIN ledger_accounts a ON a.id=w.account_id WHERE w.id=:id',id=phone['wallet'])
                unknown_amount=core.row(db,"SELECT coalesce(sum(amount_minor),0) AS n FROM wallet_reservations WHERE wallet_id=:id AND state='ACTIVE'",id=phone['wallet'])['n']
                check('wallet_'+str(phone['index']),account['balance_minor']==phone['opening_minor']-paid and account['reserved_minor']==unknown_amount)
            attempts=core.row(db,'SELECT count(*) AS n FROM payout_attempts')['n']
            check('exact_execution_attempts',attempts==10500)
            check('all_faults_exercised',all(self.faults.get(k) for k in ('lease_before_arm','lease_after_arm','worker_restart_after_operator_payment','duplicate_worker_result','stale_worker_result')))
            check('additional_probe_counts',dict(self.probes)==dict(identical=1000,conflict=100,invalid_credentials=100,cross_partner=100,malformed=100))
            check('manifest_matches_backend',all(str(by_id[r['payout_id']]['partner_tx_id'])==r['body']['partner_tx_id'] and core.minor(by_id[r['payout_id']]['amount'],'USD')==r['amount_minor'] and by_id[r['payout_id']]['status']==r['terminal'] for r in self.records))
            # Initial admitted epoch -> first claim epoch. Reports distinguish this
            # DB queue metric from the client-side scheduling/response timings.
            queue_wait=[float(x[0]) for x in core.run(db,'SELECT extract(epoch FROM min(a.created_at)-p.created_at) FROM payouts p JOIN payout_attempts a ON a.payout_id=p.id GROUP BY p.id').all()]
            config={k:core.row(db,'SHOW '+k)[k] for k in ('server_version','shared_buffers','max_connections')}
        report=dict(run_id=self.env['SIMULATION_RUN_ID'],profile=self.args.profile,mode=self.args.mode,configuration=vars(self.args),environment=dict(python=sys.version.split()[0],platform=sys.platform,logical_cpus=os.cpu_count(),database=config,app_processes=self.args.app_workers,pool_per_process=12,overflow_per_process=8,phone_count=self.args.phones,local_callback_transport='Actual HTTP loopback relay; TLS/DNS production path verified separately'),unique_instructions=10000,initial_burst=6000 if self.args.profile=='mixed' else 10000 if self.args.profile=='burst' else 0,staggered_scheduled_rate=4000/self.args.period if self.args.profile=='mixed' else 10000/self.args.period if self.args.profile=='spread' else None,achieved_new_admission_rate=10000/max(r['completed'] for r in self.records),additional_probes=dict(self.probes),http_status_and_failure_counts=dict(self.http_stats),http_attempts=sum(self.http_stats.values()),scheduling_delay_seconds=percentile([r['scheduling_delay'] for r in self.records]),client_queue_delay_seconds=percentile([r['client_queue_delay'] for r in self.records]),admission_response_latency_seconds=percentile([r['completed']-r['started'] for r in self.records]),scheduled_to_admission_seconds=percentile([r['completed']-r['scheduled'] for r in self.records]),queue_wait_seconds=percentile(queue_wait),end_to_end_seconds=percentile([r['finished']-r['scheduled'] for r in self.records]),admission_drain_seconds=max(r['completed'] for r in self.records),total_drain_seconds=time.monotonic()-self.start,outcomes=dict(statuses),execution_attempts=attempts,operator_effects=self.operator.execute('SELECT count(*) FROM effects').fetchone()[0],unknown_operator_effects=150,unknown_cases=300,expected_webhook_events=len(events),webhook_delivery_attempts=sum(e['attempts'] for e in events),webhook_delivery_latency_seconds=percentile(delivery_latencies),undelivered_events=sum(e['state']!='DELIVERED' for e in events),faults=self.faults,per_partner=per_partner,assertions_total=len(checks),failed_assertions=[k for k,v in checks.items() if not v],all_assertions_passed=all(checks.values()),limitations=['Accelerated software simulation is not physical USSD throughput','No real partner/operator or Android phone was connected','Documented quotas remain enabled; 429 retries are included in drain latency','No production database was touched'])
        (self.root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        (self.root/'manifest.json').write_text(json.dumps(self.records,indent=2),encoding='utf-8')
        (self.root/'http-attempts.json').write_text(json.dumps(self.http_evidence),encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('run_id','outcomes','total_drain_seconds','failed_assertions','all_assertions_passed')},indent=2),flush=True)
        if not report['all_assertions_passed']: raise AssertionError('End-to-end invariants failed; inspect report.json')
        return report

    def cleanup(self):
        for child in reversed(self.processes):
            if child.poll() is None:
                try:
                    parent=psutil.Process(child.pid)
                    for proc in parent.children(recursive=True): proc.terminate()
                    child.terminate(); child.wait(timeout=10)
                except (psutil.Error,subprocess.TimeoutExpired): child.kill()
        for log in self.logs: log.close()
        self.operator.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',choices=('mixed','burst','spread'),default='mixed')
    parser.add_argument('--period',type=float,default=120)
    parser.add_argument('--partner-config',help='JSON with per-partner timing and receiver behaviors; no credentials')
    parser.add_argument('--phones',type=int,choices=(5,10),default=10)
    parser.add_argument('--seed',type=int,default=260109)
    parser.add_argument('--concurrency',type=int,default=64)
    parser.add_argument('--connections',type=int,default=96)
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--drain-timeout',type=float,default=3600)
    parser.add_argument('--app-workers',type=int,default=2)
    parser.add_argument('--mode',choices=('accelerated','realistic'),default='accelerated')
    parser.add_argument('--session-seconds',type=float,default=30)
    parser.add_argument('--accelerated-delay',type=float,default=.002)
    args=parser.parse_args()
    if args.concurrency<1 or args.connections<1 or args.period<=0: parser.error('Positive timing and concurrency values required')
    run_id=str(uuid4())
    root=Path('.simulation-runs')/run_id
    root.mkdir(parents=True)
    pgroot=Path(tempfile.mkdtemp(prefix='payout-e2e-'))
    binaries=Path(os.getenv('SIMULATION_PG_BIN',r'C:\Program Files\PostgreSQL\18\bin'))
    pgport,apiport,receiverport=port(),port(),port()
    environment=os.environ.copy()
    dbname='payout_e2e_'+run_id.replace('-','')
    environment.update(DATABASE_URL=f'postgresql+psycopg://payout_sim@127.0.0.1:{pgport}/{dbname}',SECRET_KEY=os.urandom(32).hex(),API_KEY_VERIFIER_SECRET=os.urandom(32).hex(),EXECUTOR_TOKEN='simulation-unused',API_KEY_HASH_SECRET='simulation-unused',ENVIRONMENT='simulation',SKIP_DB_BOOTSTRAP='true',EMBEDDED_PAYMENT_WORKERS='false',PAYOUT_SIMULATOR_ENABLED='true',PAYOUT_SIMULATOR_SECRET=os.urandom(32).hex(),POOL_SIZE='12',MAX_OVERFLOW='8',SIMULATION_RUN_ID=run_id,SIMULATION_RUN_DIR=str(root.resolve()),SIMULATION_RECEIVER=f'http://127.0.0.1:{receiverport}',PYTHONDONTWRITEBYTECODE='1')
    for key in ('DATABASE_URL','TEST_DATABASE_URL','CENTRAL_TEST_CLUSTER_URL'): os.environ.pop(key,None)
    engine=scenario=None
    started=False
    try:
        subprocess.run([str(binaries/'initdb.exe' if os.name=='nt' else binaries/'initdb'),'-D',str(pgroot/'data'),'-U','payout_sim','-A','trust','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        with (pgroot/'data'/'postgresql.conf').open('a') as cfg: cfg.write(f"\nlisten_addresses='127.0.0.1'\nport={pgport}\n")
        subprocess.run([str(binaries/'pg_ctl.exe' if os.name=='nt' else binaries/'pg_ctl'),'-D',str(pgroot/'data'),'-l',str(pgroot/'postgres.log'),'-w','start'],check=True,stdout=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        started=True
        cluster=create_engine(f'postgresql+psycopg://payout_sim@127.0.0.1:{pgport}/postgres',isolation_level='AUTOCOMMIT')
        with cluster.connect() as db: db.exec_driver_sql('CREATE DATABASE '+dbname)
        cluster.dispose()
        os.environ['TEST_DATABASE_URL']=environment['DATABASE_URL']
        command.upgrade(Config('alembic.ini'),'head')
        os.environ.pop('TEST_DATABASE_URL',None)
        engine=create_engine(environment['DATABASE_URL'],pool_size=8,max_overflow=4)
        with engine.begin() as db:
            db.exec_driver_sql('CREATE TABLE simulation_marker(run_id text PRIMARY KEY)')
            core.run(db,'INSERT INTO simulation_marker VALUES(:id)',id=run_id)
        settings=json.loads(Path(args.partner_config).read_text()) if args.partner_config else {}
        if set(settings)-{a for a,*_ in PARTNERS}: raise ValueError('Unknown simulated partner alias')
        environment['SIMULATION_PARTNER_SETTINGS']=json.dumps(settings)
        records=generate(run_id,args.seed,args.period,args.profile,settings)
        scenario=Scenario(args,root,engine,records,environment)
        scenario.persist_credentials()
        scenario.launch('simulation.receiver',receiverport)
        scenario.launch('simulation.backend',apiport)
        async def run():
            await scenario.ready(environment['SIMULATION_RECEIVER'])
            await scenario.ready(f'http://127.0.0.1:{apiport}')
            await scenario.provision(f'http://127.0.0.1:{apiport}')
            scenario.launch('simulation.callbacks')
            await scenario.execute(f'http://127.0.0.1:{apiport}')
        print('SIMULATION ONLY run directory: '+str(root.resolve()),flush=True)
        asyncio.run(run())
        scenario.verify()
    except Exception as error:
        (root/'failure.json').write_text(json.dumps(dict(run_id=run_id,error_type=type(error).__name__,message=str(error))),encoding='utf-8')
        raise
    finally:
        if scenario: scenario.cleanup()
        if engine: engine.dispose()
        if started:
            # pgroot is generated here, never supplied by caller; no production
            # service or existing DB directory can be stopped/reset by this script.
            subprocess.run([str(binaries/'pg_ctl.exe' if os.name=='nt' else binaries/'pg_ctl'),'-D',str(pgroot/'data'),'-m','fast','-w','stop'],stdout=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        print('Owned PostgreSQL cluster stopped; evidence retained in '+str(root.resolve()),flush=True)


if __name__=='__main__': main()
