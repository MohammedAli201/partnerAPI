"""Loopback launcher for the versioned simulator protocol. No external packages required."""
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.parse import urlsplit
from protocol import Simulator


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def callback_worker(simulator, stop):
    target = urlsplit(simulator.callback_url)
    if not simulator.callback_url:
        return
    if target.hostname not in {"localhost", "127.0.0.1", "::1"} or target.scheme not in {"http", "https"} or target.username or target.password or target.query:
        raise ValueError("CALLBACK_LOOPBACK_REQUIRED")
    opener = build_opener(ProxyHandler({}), NoRedirects())
    while not stop.wait(0.5):
        # Durable callback body and event identity survive process restarts. Each
        # delivery gets a fresh nonce; the backend inbox owns event deduplication.
        with simulator.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = db.execute("SELECT * FROM callbacks WHERE accepted=0 ORDER BY rowid LIMIT 1").fetchone()
            if not event:
                continue
            db.execute("UPDATE callbacks SET attempts=attempts+1 WHERE event_id=?", (event["event_id"],))
            try:
                request = Request(simulator.callback_url, data=event["raw"], headers=simulator.callback_headers(event["raw"]), method="POST")
                with opener.open(request, timeout=5) as response:
                    if response.status == 202:
                        db.execute("UPDATE callbacks SET accepted=1 WHERE event_id=?", (event["event_id"],))
            except Exception:
                pass  # Do not log headers, URLs, exception text, credentials or bodies.


def main():
    settings = json.loads(Path(os.environ["JUBATECH_SIMULATOR_CONFIG"]).read_text(encoding="utf-8-sig"))
    simulator = Simulator(settings["database"], settings["apiKey"], settings["hmacSecret"],
        os.environ.get("JUBATECH_SIMULATOR_ENVIRONMENT", ""), settings["wallets"],
        settings.get("callbackUrl", ""), settings.get("callbackSecret", ""), settings.get("skipRecipientVerification", False))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def serve(self):
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 65536:
                self.send_error(413); return
            status, headers, body, drop = simulator.handle(self.command, self.path, dict(self.headers), self.rfile.read(size))
            if drop:
                self.connection.shutdown(socket.SHUT_RDWR); self.connection.close(); return
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        do_POST = do_GET = serve

    server = ThreadingHTTPServer(("127.0.0.1", settings.get("port", 0)), Handler)
    stop = threading.Event()
    threading.Thread(target=callback_worker, args=(simulator, stop), daemon=True).start()
    print(json.dumps({"port": server.server_port, "environment": os.environ["JUBATECH_SIMULATOR_ENVIRONMENT"]}), flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set(); server.server_close()


if __name__ == "__main__":
    main()
