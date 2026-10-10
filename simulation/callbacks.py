"""Several real callback workers plus the normal lease reaper on test DB only."""
import logging
import threading
import time
from simulation.backend import app  # verifies isolation and installs local relay
from database import SessionLocal
import registered_webhooks as hooks
import payment_worker as workers
import backend_core as core

for _ in range(8):
    threading.Thread(target=hooks.run_worker,args=(threading.Event(),SessionLocal),daemon=True).start()
while True:
    try:
        with SessionLocal.begin() as db:
            workers.reap(db)
            core.run(db,'DELETE FROM rate_buckets WHERE expires_at<now()')
    except Exception as error:
        logging.error('Simulation reaper failure type=%s',type(error).__name__)
    time.sleep(3)
