import importlib
import json
import sqlite3
import sys
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from payout_webhooks import signed_headers

@pytest.fixture
def receiver(tmp_path,monkeypatch):
    secrets={'atlas':'a'*64,'britannia':'b'*64,'liberty':'c'*64,'nordic':'d'*64}
    (tmp_path/'credentials.json').write_text(json.dumps({'webhook_secrets':secrets}))
    monkeypatch.setenv('SIMULATION_RUN_DIR',str(tmp_path))
    sys.modules.pop('simulation.receiver',None)
    app=importlib.import_module('simulation.receiver').app
    return TestClient(app),tmp_path,secrets

def body(payout,status,timestamp):
    return json.dumps(dict(event_id=str(uuid4()),provider_reference=payout,status=status,recipient='+252610000000',timestamp=timestamp)).encode()

def test_receiver_durable_dedup_exact_hmac_and_no_regression(receiver):
    http,root,secrets=receiver
    payout=str(uuid4())
    paid=body(payout,'Paid','2026-10-09T12:00:02Z')
    processing=body(payout,'Processing','2026-10-09T12:00:01Z')
    for raw in (paid,processing,paid):
        assert http.post('/atlas',content=raw,headers=signed_headers(secrets['atlas'],raw)).status_code==202
    assert http.post('/atlas',content=paid,headers=signed_headers(secrets['britannia'],paid)).status_code==401
    with sqlite3.connect(root/'atlas-events.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==4
        assert db.execute('SELECT status FROM current WHERE payout_id=?',(payout,)).fetchone()[0]=='Paid'
    with sqlite3.connect(root/'britannia-events.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==0

def test_receiver_unknown_can_be_reconciled_but_cannot_regress(receiver):
    http,root,secrets=receiver
    payout=str(uuid4())
    for status,timestamp in [('Unknown','2026-10-09T12:00:00Z'),('Processing','2026-10-09T12:00:01Z'),('Paid','2026-10-09T12:00:02Z')]:
        raw=body(payout,status,timestamp)
        assert http.post('/atlas',content=raw,headers=signed_headers(secrets['atlas'],raw)).status_code==202
    with sqlite3.connect(root/'atlas-events.sqlite3') as db:
        assert db.execute('SELECT status FROM current WHERE payout_id=?',(payout,)).fetchone()[0]=='Paid'
