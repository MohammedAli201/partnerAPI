"""Repeatable synthetic instructions in the existing PayoutCreate schema."""
import random
from uuid import UUID,uuid5
from schemas import PayoutCreate
from backend_core import immutable,digest

PARTNERS=(('atlas','Atlas EU','EU',6000,4500),('britannia','Britannia UK','GB',2500,1000),('liberty','Liberty USA','US',1000,400),('nordic','Nordic EU','EU',500,100))

def money(n): return f'{n//100}.{n%100:02d}'

def generate(run_id,seed,period,profile,settings=None):
    rng=random.Random(seed)
    outcomes=['SUCCESS']*8500+['FAILURE']*500+['RETRY']*500+['UNKNOWN']*300+['DELAYED']*200
    rng.shuffle(outcomes)
    records=[]
    for partner_index,(alias,name,origin,count,burst) in enumerate(PARTNERS):
        options=(settings or {}).get(alias,{})
        partner_period=float(options.get('period_seconds',period))
        jitter=float(options.get('jitter_seconds',.5))
        if partner_period<=0 or jitter<0: raise ValueError('Positive partner periods and nonnegative jitter required')
        for i in range(count):
            reference=str(uuid5(UUID(run_id),f'common-reference-{i}'))
            amount=1 if i==0 else 1000000 if i==1 else rng.randint(100,50000)
            network,provider=('evc','Hormuud') if i%2==0 else ('edahab','Somtel')
            scheduled=0 if profile=='burst' or (profile=='mixed' and i<burst) else max(.001,min(partner_period,(i-(burst if profile=='mixed' else 0)+1)/max(1,count-(burst if profile=='mixed' else 0))*partner_period+rng.uniform(-jitter,jitter)))
            if i%200<10 and scheduled>0: scheduled=max(.001,int(scheduled/5)*5)
            body=dict(partner_tx_id=reference,amount=money(amount),currency='USD',recipient=f'+25261{partner_index}{i:06d}',provider=provider,payout_channel=network,request_payload=dict(corridor='SO',simulation_correlation=f'{alias}-{i}',synthetic_recipient_name=f'Test Recipient {i}',synthetic_sender_name=f'Test Sender {i}',origin_country=origin,destination_country='SO',purpose='Family support',relationship='Family'))
            parsed=PayoutCreate(**body)
            records.append(dict(partner=alias,index=i,body=body,key=f'{run_id}:{alias}:{i}',amount_minor=amount,fee_minor=60,scheduled=scheduled,initial_outcome=outcomes[len(records)],instruction_hash=digest(immutable(parsed,reference))))
    assert len(records)==10000
    return records
