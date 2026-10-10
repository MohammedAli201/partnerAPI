"""Development fixture only, always leaves global execution paused."""
import hashlib
import json
import os
import secrets
from uuid import uuid4

from central.app import transaction
from central import service as s


def seed(db,unpause=False):
    s.money_lock(db)
    partner,worker,wallet,device=[uuid4() for _ in range(4)]
    s.run(db,"INSERT INTO central.partners(id,name,corridors) VALUES(:id,'Demo partner',ARRAY['EU-SO','GB-SO','US-SO'])",id=partner)
    s.run(db,"INSERT INTO central.workers(id,name,simulator) VALUES(:id,'Fake Pi',true)",id=worker)
    cash=s.account(db,'bank:USD','BANK','USD',spendable=True)
    funding=s.partner_account(db,partner,'USD')
    asset=s.account(db,f'wallet:{wallet}:USD','WALLET_ASSET','USD',spendable=True)
    s.post(db,f'prefund:{partner}','PREFUND',[(cash['id'],1_000_000),(funding['id'],-1_000_000)],'simulator://prefunding')
    s.post(db,f'topup:{wallet}','TOPUP',[(asset['id'],1_000_000),(cash['id'],-1_000_000)],'simulator://topup')
    s.run(db,"""INSERT INTO central.wallets(id,provider,provider_account_reference,currency,account_id,observed_minor,observed_at,daily_limit_minor,max_payout_minor)
        VALUES(:id,'fake',:reference,'USD',:account,1000000,now(),1000000,100000)""",id=wallet,reference=str(wallet),account=asset['id'])
    s.run(db,"INSERT INTO central.devices(id,sim_identity,worker_id,wallet_id,networks) VALUES(:id,:sim,:worker,:wallet,ARRAY['evc'])",id=device,sim=str(device),worker=worker,wallet=wallet)
    output=dict(partner_id=str(partner),worker_id=str(worker),wallet_id=str(wallet),device_id=str(device))
    for name,role in [('partner','partner'),('worker','worker'),('admin','admin'),('reviewer_a','reviewer'),('reviewer_b','reviewer')]:
        token=secrets.token_urlsafe(32)
        cid=uuid4()
        s.run(db,'INSERT INTO central.credentials(id,partner_id,worker_id,token_hash,role) VALUES(:id,:partner,:worker,:hash,:role)',
            id=cid,partner=partner if role=='partner' else None,worker=worker if role=='worker' else None,
            hash=hashlib.sha256(token.encode()).hexdigest(),role=role)
        output[f'{name}_token']=token
        output[f'{name}_credential_id']=str(cid)
    if unpause:
        s.run(db,"UPDATE central.controls SET paused=false WHERE scope='global' AND identity='all'")
    return output


def main():
    if os.getenv('CENTRAL_SIMULATOR_ENABLED')!='true':
        raise SystemExit('Bootstrap is development only: CENTRAL_SIMULATOR_ENABLED=true required')
    with transaction() as db:
        output=seed(db)
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    main()
