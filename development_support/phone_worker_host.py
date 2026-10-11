"""Persistent local phone backend host with bounded restart delay and lease reaping.

Configuration is an ignored local file; no credentials appear in process args.
Stop using stop_phone_worker.ps1 rather than killing just the supervised child.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.phone-worker-host.json'
STOP = ROOT / '.phone-worker-stop'
CONFIG = ROOT / '.phone-worker-local.json'


def stop_server(child):
    if child.poll() is not None:
        return
    if os.name == 'nt':
        # Windows venv python.exe can launch a second interpreter process. Stop
        # the owned process tree so that no orphan keeps the listening socket.
        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    else:
        child.terminate()
    try:
        child.wait(10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    os.environ.update(config['environment'])
    if os.environ.get('ENVIRONMENT') == 'production' or os.environ.get('PHONE_WORKER_ENABLED') != 'true':
        raise RuntimeError('This launcher requires an enabled non-production phone backend')
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())

    def reap():
        from database import SessionLocal
        import payment_worker
        while not stopped.wait(5):
            try:
                with SessionLocal.begin() as db:
                    payment_worker.reap(db)
            except Exception:
                # Restart naturally on the next tick, without emitting connection secrets.
                print('Lease reaper temporarily unavailable', flush=True)

    thread = threading.Thread(target=reap, daemon=True)
    thread.start()
    child = None
    try:
        with (ROOT / '.local-server.stdout.log').open('a', encoding='utf-8') as out, (ROOT / '.local-server.stderr.log').open('a', encoding='utf-8') as err:
            while not stopped.is_set() and not STOP.exists():
                child = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host',
                                          config.get('host', '127.0.0.1'), '--port', str(config.get('port', 8000)),
                                          '--no-access-log'], cwd=ROOT, stdout=out, stderr=err,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                STATE.write_text(json.dumps(dict(supervisor_pid=os.getpid(), server_pid=child.pid)), encoding='utf-8')
                while child.poll() is None and not stopped.is_set() and not STOP.exists():
                    stopped.wait(1)
                if child.poll() is None:
                    stop_server(child)
                if not stopped.is_set() and not STOP.exists():
                    print('Restarting local phone backend after exit', flush=True)
                    stopped.wait(5)
    finally:
        stopped.set()
        if child and child.poll() is None:
            stop_server(child)
        thread.join(6)
        STATE.unlink(missing_ok=True)
        STOP.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
