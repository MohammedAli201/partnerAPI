"""Test-only durable journal fixture. No HTTP client or worker entry point."""
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import backend_core as s
from payment_worker import proof


class Journal:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS executions(
            attempt_id TEXT PRIMARY KEY,command TEXT NOT NULL,phase TEXT NOT NULL,
            result TEXT,acknowledged INTEGER NOT NULL DEFAULT 0)''')
        self.db.commit()

    def record(self,command):
        aid=command['attempt_id']
        encoded=s.canonical(command)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO executions(attempt_id,command,phase) VALUES(?,?,'RECEIVED')",(aid,encoded))
        current=self.db.execute('SELECT command,phase,result FROM executions WHERE attempt_id=?',(aid,)).fetchone()
        if current[0]!=encoded:
            raise ValueError('Repeated command instructions changed')
        return current[1],current[2]

    def mark(self,aid,phase):
        with self.db:
            self.db.execute('UPDATE executions SET phase=? WHERE attempt_id=?',(phase,aid))

    def result(self,command,outcome,stage,reference=None,secret=''):
        aid=command['attempt_id']
        import json
        existing=self.db.execute('SELECT result FROM executions WHERE attempt_id=?',(aid,)).fetchone()[0]
        if existing:
            return json.loads(existing)
        result=dict(event_id=str(uuid4()),attempt_id=aid,lease_generation=command['lease_generation'],
            instruction_hash=command['instruction_hash'],outcome=outcome,stage=stage,
            evidence_ref=f'simulator://journal/{aid}',provider_reference=reference,
            proof=proof(command,reference,secret) if reference else None,
            occurred_at=datetime.now(timezone.utc).isoformat())
        with self.db:
            self.db.execute("UPDATE executions SET phase='RESULT',result=? WHERE attempt_id=? AND result IS NULL",(s.canonical(result),aid))
        return json.loads(self.db.execute('SELECT result FROM executions WHERE attempt_id=?',(aid,)).fetchone()[0])

    def execute(self,command,arm,send,secret,crash=None):
        phase,result=self.record(command)
        if result:
            import json
            return json.loads(result)
        # A prior ARM_REQUESTED or MAY_HAVE_SUBMITTED never executes again, even
        # if the crash occurred before the server armed or before the fake send.
        if phase!='RECEIVED':
            return self.result(command,'UNKNOWN','UNKNOWN')
        with self.db:
            acquired=self.db.execute("UPDATE executions SET phase='ARM_REQUESTED' WHERE attempt_id=? AND phase='RECEIVED' AND result IS NULL",(command['attempt_id'],)).rowcount
        if not acquired:
            return self.result(command,'UNKNOWN','UNKNOWN')
        arm(command)
        self.mark(command['attempt_id'],'MAY_HAVE_SUBMITTED')
        if crash=='before_send':
            raise RuntimeError('injected crash after durable boundary')
        reference=send(command)
        if crash=='after_send':
            raise RuntimeError('injected crash after external payment')
        return self.result(command,'SUCCESS','AFTER_SEND',reference,secret)

    def pending(self):
        import json
        # Recover uncertain commands locally without touching the phone again.
        for (encoded,) in self.db.execute("SELECT command FROM executions WHERE result IS NULL AND phase<>'RECEIVED'").fetchall():
            self.result(json.loads(encoded),'UNKNOWN','UNKNOWN')
        return [(aid,json.loads(result)) for aid,result in self.db.execute('SELECT attempt_id,result FROM executions WHERE acknowledged=0 AND result IS NOT NULL')]
