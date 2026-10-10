"""Admission benchmark only; never measures physical phone capacity.

Example: python -m central.loadtest --rate 10 --seconds 1800 --out load-10.json
Requires a dedicated funded simulator partner and CENTRAL_PARTNER_TOKEN.
"""
import argparse
import asyncio
import json
import os
import platform
import time
from collections import Counter
from uuid import uuid4

import httpx


async def benchmark(args):
    latencies=[]
    codes=Counter()
    semaphore=asyncio.Semaphore(100)
    headers={'Authorization':f"Bearer {os.environ['CENTRAL_PARTNER_TOKEN']}"}
    started=time.perf_counter()
    async with httpx.AsyncClient(base_url=args.url,timeout=30,headers=headers,follow_redirects=False) as client:
        async def send(reference):
            async with semaphore:
                t=time.perf_counter()
                try:
                    response=await client.post('/v1/payouts',headers={'Idempotency-Key':reference},json=dict(
                        external_reference=reference,amount_minor=100,currency='USD',recipient='+252611234567',network='evc',corridor='EU-SO'))
                    codes[str(response.status_code)]+=1
                except httpx.HTTPError:
                    codes['transport_error']+=1
                latencies.append((time.perf_counter()-t)*1000)
        tasks=[]
        previous=None
        for index in range(args.rate*args.seconds):
            # 10% exact duplicates, without deduplicating amount/recipient.
            reference=previous if index%10==9 else str(uuid4())
            previous=reference
            tasks.append(asyncio.create_task(send(reference)))
            delay=started+(index+1)/args.rate-time.perf_counter()
            if delay>0:
                await asyncio.sleep(delay)
        await asyncio.gather(*tasks)
    latencies.sort()
    def percentile(q):
        return latencies[min(len(latencies)-1,int(q*len(latencies)))] if latencies else None
    return dict(kind='API admission only',rate=args.rate,seconds=args.seconds,duplicate_fraction=0.1,
        amount_minor=100,currency='USD',elapsed_seconds=time.perf_counter()-started,
        requests=len(latencies),responses=dict(codes),latency_ms=dict(p50=percentile(.5),p95=percentile(.95),p99=percentile(.99)),
        client_hardware=dict(platform=platform.platform(),processor=platform.processor(),cpu_count=os.cpu_count()),
        server_configuration='Record server hardware, API workers, pool and PostgreSQL settings separately')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8001')
    parser.add_argument('--rate',type=int,default=10)
    parser.add_argument('--seconds',type=int,default=1800)
    parser.add_argument('--out',default='load-result.json')
    args=parser.parse_args()
    if args.rate<1 or args.seconds<1:
        parser.error('rate and seconds must be positive')
    result=asyncio.run(benchmark(args))
    with open(args.out,'w',encoding='utf-8') as file:
        json.dump(result,file,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
