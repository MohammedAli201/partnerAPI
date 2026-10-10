"""Development/Test-only protocol extension; all accounts and payouts are synthetic.

The durable store is separate from any executor queue: this module cannot send money.
It can be mounted in the existing FastAPI simulator or run by server.py for CI.
"""
import hashlib
import hmac
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote
from uuid import UUID, uuid4


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def mac(secret, value):
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


class Rejection(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


class Simulator:
    def __init__(self, path, api_key, secret, environment, wallets, callback_url="", callback_secret="", skip_recipient_verification=False):
        if environment not in {"Development", "Test"}:
            raise ValueError("SIMULATOR_ENVIRONMENT_REQUIRED")
        if len(api_key) < 32 or len(secret) < 32:
            raise ValueError("SIMULATOR_SIGNED_CREDENTIALS_REQUIRED")
        self.path, self.api_key, self.secret = str(path), api_key, secret
        self.environment, self.callback_url, self.callback_secret = environment, callback_url, callback_secret
        self.skip_recipient_verification = skip_recipient_verification is True
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY, seen INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS wallets(provider TEXT, recipient TEXT, country TEXT, currency TEXT,
                    name TEXT NOT NULL, PRIMARY KEY(provider,recipient,country,currency));
                CREATE TABLE IF NOT EXISTS payouts(request_key TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                    request_hash TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS callbacks(event_id TEXT PRIMARY KEY, raw BLOB NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS faults(name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metrics(name TEXT PRIMARY KEY, count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS terminal_actions(event_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                    reason TEXT NOT NULL, occurred_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS terminal_action_no_update BEFORE UPDATE ON terminal_actions
                    BEGIN SELECT RAISE(ABORT, 'AUDIT_APPEND_ONLY'); END;
                CREATE TRIGGER IF NOT EXISTS terminal_action_no_delete BEFORE DELETE ON terminal_actions
                    BEGIN SELECT RAISE(ABORT, 'AUDIT_APPEND_ONLY'); END;
            ''')
            for wallet in wallets:
                db.execute("INSERT OR REPLACE INTO wallets VALUES(?,?,?,?,?)", (
                    wallet["provider"], wallet["recipient"], wallet["country"], wallet["currency"], wallet["name"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def handle(self, method, path, headers, raw):
        headers = {k.lower(): v for k, v in headers.items()}
        nonce = headers.get("x-simulator-nonce", "")
        timestamp = headers.get("x-simulator-timestamp", "")
        request_key = headers.get("idempotency-key", "")
        request_digest = digest(raw)
        prefix = [method, path, timestamp, nonce, request_digest, request_key]
        try:
            if len(raw) > 65536 or len(request_key) > 200:
                raise Rejection("REQUEST_TOO_LARGE", 413)
            if not hmac.compare_digest(headers.get("x-api-key", ""), self.api_key):
                raise Rejection("INVALID_API_KEY", 401)
            if not timestamp.isdecimal() or abs(int(time.time()) - int(timestamp)) > 300:
                raise Rejection("TIMESTAMP_OUTSIDE_TOLERANCE", 401)
            if len(nonce) != 64 or any(c not in "0123456789abcdef" for c in nonce):
                raise Rejection("INVALID_NONCE", 401)
            canonical = "\n".join(["simulator-request-v1"] + prefix)
            if headers.get("x-simulator-body-sha256") != request_digest or not hmac.compare_digest(
                    headers.get("x-simulator-signature", ""), mac(self.secret, canonical)):
                raise Rejection("INVALID_SIGNATURE", 401)
            # The nonce commit precedes the business transaction. Replays remain rejected
            # after failures and process restarts. Only verified requests consume nonces.
            with self.connect() as db:
                db.execute("DELETE FROM nonces WHERE seen < ?", (int(time.time()) - 601,))
                try:
                    db.execute("INSERT INTO nonces VALUES(?,?)", (nonce, int(time.time())))
                except sqlite3.IntegrityError:
                    raise Rejection("REPLAY_DETECTED", 401)
                if method == "POST" and path in {"/payouts-create", "/development/v1/payouts-create"}:
                    db.execute("INSERT INTO metrics VALUES('payout_posts',1) ON CONFLICT(name) DO UPDATE SET count=count+1")
            business_path = path.removeprefix("/development/v1") if path.startswith("/development/v1/") else path
            status, payload, drop = self.dispatch(method, business_path, request_key, raw)
        except Rejection as error:
            status, payload, drop = error.status, {"code": error.code}, False
        except (ValueError, KeyError, TypeError, ArithmeticError):
            status, payload, drop = 400, {"code": "INVALID_REQUEST"}, False
        body = encoded(payload)
        response_time = str(int(time.time()))
        signature = mac(self.secret, "\n".join(["simulator-response-v1"] + prefix + [str(status), response_time, digest(body)]))
        response_headers = {"Content-Type": "application/json", "X-Simulator-Timestamp": response_time,
            "X-Simulator-Request-Nonce": nonce, "X-Simulator-Body-SHA256": digest(body), "X-Simulator-Signature": signature}
        return status, response_headers, body, drop

    def dispatch(self, method, path, request_key, raw, operator=None):
        data = json.loads(raw) if raw else {}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if method == "POST" and path == "/wallet-accounts/verify":
                db.execute("INSERT INTO metrics VALUES('wallet_lookups',1) ON CONFLICT(name) DO UPDATE SET count=count+1")
                wallet = db.execute("SELECT * FROM wallets WHERE provider=? AND recipient=? AND country=? AND currency=?",
                    (data["provider"], data["recipient"], data["country"], data["currency"])).fetchone()
                return 200, {**data, "result": "Match" if wallet else "NoMatch",
                    "registered_name": wallet["name"] if wallet else None,
                    "evidence_reference": "synthetic-wallet:" + digest(raw)}, False
            if method == "POST" and path == "/payouts-create":
                if not request_key or request_key != data["request_payload"]["RequestKey"]:
                    raise Rejection("REQUEST_KEY_MISMATCH", 409)
                original = db.execute("SELECT * FROM payouts WHERE request_key=?", (request_key,)).fetchone()
                if original:
                    if original["request_hash"] != digest(raw):
                        raise Rejection("IDEMPOTENCY_PAYLOAD_CONFLICT", 409)
                    # Even a repeated POST only acknowledges acceptance.
                    result = json.loads(original["body"]); result["status"] = "RECEIVED"
                    return 200, result, False
                payload = data["request_payload"]
                if digest(payload["Payload"].encode()) != payload["PayloadHash"]:
                    raise Rejection("PAYOUT_DIGEST_MISMATCH", 409)
                intent = json.loads(payload["Payload"], parse_float=Decimal)
                if str(UUID(data["partner_tx_id"])) != payload["TransactionId"] or intent["transactionId"] != payload["TransactionId"]:
                    raise Rejection("TRANSACTION_BINDING_MISMATCH", 409)
                amount = Decimal(str(data["amount"]))
                if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
                    raise Rejection("INVALID_AMOUNT", 409)
                if data["currency"] != "USD" or intent["country"] != "SO" or data["payout_channel"] != "wallet":
                    raise Rejection("SYNTHETIC_CORRIDOR_NOT_SUPPORTED", 409)
                if amount > 500:
                    raise Rejection("SOMALIA_WALLET_RECEIVE_LIMIT_EXCEEDED", 409)
                if any(intent[k] != data[v] for k, v in [("currency", "currency"), ("provider", "provider"),
                        ("recipient", "recipient"), ("method", "payout_channel")]) or Decimal(str(intent["amount"])) != amount:
                    raise Rejection("PAYOUT_BUSINESS_BINDING_MISMATCH", 409)
                if not self.skip_recipient_verification:
                    wallet = db.execute("SELECT * FROM wallets WHERE provider=? AND recipient=? AND country='SO' AND currency='USD'",
                        (data["provider"], data["recipient"])).fetchone()
                    if not wallet or wallet["name"].casefold() != intent["name"].casefold():
                        raise Rejection("SYNTHETIC_WALLET_NOT_VERIFIED", 409)
                result = {**data, "id": str(uuid4()), "amount": str(amount), "status": "RECEIVED",
                    "recipient_verification": "DevelopmentSkipped" if self.skip_recipient_verification else "Match"}
                result["request_payload"] = {k: payload[k] for k in ["TransactionId", "RequestKey", "PayloadHash"]}
                db.execute("INSERT INTO payouts VALUES(?,?,?,?,?)", (request_key, result["id"], digest(raw), encoded(result).decode(), "RECEIVED"))
                fault = db.execute("SELECT value FROM faults WHERE name='drop_next_submission'").fetchone()
                db.execute("DELETE FROM faults WHERE name='drop_next_submission'")
                return 201, result, bool(fault)
            if method == "GET" and path.startswith("/payouts/by-request-key/"):
                key = unquote(path[len("/payouts/by-request-key/"):])
                if key != request_key:
                    raise Rejection("REQUEST_KEY_MISMATCH", 409)
                payout = db.execute("SELECT * FROM payouts WHERE request_key=?", (key,)).fetchone()
                if not payout:
                    raise Rejection("PAYOUT_NOT_FOUND", 404)
                result = json.loads(payout["body"]); result["status"] = payout["status"]
                return 200, result, False
            # Signed, explicit test controls; never automatic settlement on submission.
            if method == "POST" and path == "/simulation/terminal":
                reason = data.get("reason", "Explicit synthetic terminal event")
                if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
                    raise Rejection("TERMINAL_REASON_REQUIRED", 400)
                payout = db.execute("SELECT * FROM payouts WHERE request_key=?", (data["request_key"],)).fetchone()
                if not payout:
                    raise Rejection("PAYOUT_NOT_FOUND", 404)
                if data["status"] not in {"SENT", "FAILED", "REJECTED"}:
                    raise Rejection("TERMINAL_STATUS_REQUIRED", 409)
                if payout["status"] not in {"RECEIVED", "PROCESSING"}:
                    raise Rejection("PAYOUT_ALREADY_TERMINAL", 409)
                db.execute("UPDATE payouts SET status=? WHERE request_key=?", (data["status"], data["request_key"]))
                stored = json.loads(payout["body"])
                event = {"event_id": str(uuid4()), "partner_tx_id": stored["partner_tx_id"],
                    "request_key": stored["request_payload"]["RequestKey"], "request_payload_hash": stored["request_payload"]["PayloadHash"],
                    "status": {"SENT": "Paid", "FAILED": "Failed", "REJECTED": "Rejected"}[data["status"]],
                    "provider": stored["provider"], "provider_reference": stored["id"],
                    "amount": float(stored["amount"]), "currency": stored["currency"], "recipient": stored["recipient"],
                    "payout_channel": stored["payout_channel"], "timestamp": datetime.now(timezone.utc).isoformat()}
                db.execute("INSERT INTO callbacks(event_id,raw) VALUES(?,?)", (event["event_id"], encoded(event)))
                db.execute("INSERT INTO terminal_actions VALUES(?,?,?,?)", (event["event_id"],
                    operator or "authenticated_simulator_api", reason.strip(), event["timestamp"]))
                return 200, event, False
            if method == "GET" and path == "/simulation/evidence":
                posts = db.execute("SELECT count FROM metrics WHERE name='payout_posts'").fetchone()
                lookups = db.execute("SELECT count FROM metrics WHERE name='wallet_lookups'").fetchone()
                return 200, {"submissions": db.execute("SELECT count(*) FROM payouts").fetchone()[0],
                    "payout_posts": posts[0] if posts else 0,
                    "wallet_lookups": lookups[0] if lookups else 0,
                    "callbacks": db.execute("SELECT count(*) FROM callbacks").fetchone()[0],
                    "accepted_callbacks": db.execute("SELECT count(*) FROM callbacks WHERE accepted=1").fetchone()[0]}, False
            if method == "POST" and path == "/simulation/fault" and self.environment == "Test":
                if data != {"drop_next_submission": True}:
                    raise Rejection("INVALID_FAULT")
                db.execute("INSERT OR REPLACE INTO faults VALUES('drop_next_submission','true')")
                return 200, {"configured": True}, False
            raise Rejection("ENDPOINT_NOT_FOUND", 404)

    def callback_headers(self, raw):
        if len(self.callback_secret) < 32:
            raise ValueError("CALLBACK_SECRET_REQUIRED")
        timestamp, nonce = str(int(time.time())), str(uuid4())
        signature = hmac.new(self.callback_secret.encode(), f"{timestamp}.{nonce}.".encode() + raw, hashlib.sha256).hexdigest()
        return {"Content-Type": "application/json", "X-API-Key": self.api_key, "X-JubaTech-Timestamp": timestamp,
            "X-JubaTech-Nonce": nonce, "X-JubaTech-Signature": signature}
