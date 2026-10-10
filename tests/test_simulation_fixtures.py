from collections import Counter
from simulation.fixtures import generate,PARTNERS

def test_repeatable_exact_manifest_and_initial_burst():
    run='26010900-0000-4000-8000-000000000001'
    records=generate(run,260109,120,'mixed')
    assert records==generate(run,260109,120,'mixed')
    assert len(records)==10000
    assert Counter(r['partner'] for r in records)=={a:n for a,_,_,n,_ in PARTNERS}
    assert Counter(r['initial_outcome'] for r in records)==dict(SUCCESS=8500,FAILURE=500,RETRY=500,UNKNOWN=300,DELAYED=200)
    assert sum(r['scheduled']==0 for r in records)==6000
    for alias,_,_,count,burst in PARTNERS:
        own=[r for r in records if r['partner']==alias]
        assert sum(r['scheduled']==0 for r in own)==burst
    assert len({(r['partner'],r['body']['partner_tx_id']) for r in records})==10000
    assert len({r['body']['partner_tx_id'] for r in records})<10000
    assert all(isinstance(r['amount_minor'],int) for r in records)

def test_other_profiles_and_separate_run_identity():
    run='26010900-0000-4000-8000-000000000001'
    assert all(r['scheduled']==0 for r in generate(run,1,120,'burst'))
    assert all(r['scheduled']>0 for r in generate(run,1,120,'spread'))
    other=generate('26010900-0000-4000-8000-000000000002',1,120,'spread')
    assert other[0]['key']!=generate(run,1,120,'spread')[0]['key']
