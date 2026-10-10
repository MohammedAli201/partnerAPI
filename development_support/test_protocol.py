import hashlib
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4
from protocol import Simulator, digest, encoded, mac


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.api_key, self.secret = secrets.token_hex(32), secrets.token_hex(32)
        self.wallet = {"provider": "EVC", "recipient": "+252611234567", "country": "SO", "currency": "USD", "name": "Synthetic Recipient"}
        self.sim = self.restart()

    def tearDown(self):
        self.directory.cleanup()

    def restart(self):
        return Simulator(Path(self.directory.name) / "test.sqlite", self.api_key, self.secret, "Test", [self.wallet])

    def request(self, method, path, data=None, key="", headers=None):
        raw = encoded(data) if data is not None else b""
        timestamp, nonce = str(int(time.time())), secrets.token_hex(32)
        canonical = "\n".join(["simulator-request-v1", method, path, timestamp, nonce, digest(raw), key])
        signed = {"X-API-Key": self.api_key, "X-Simulator-Timestamp": timestamp, "X-Simulator-Nonce": nonce,
            "X-Simulator-Body-SHA256": digest(raw), "X-Simulator-Signature": mac(self.secret, canonical), "Idempotency-Key": key}
        signed.update(headers or {})
        return method, path, signed, raw

    def instruction(self, amount=500):
        transaction = str(uuid4()); key = "payout:" + transaction.replace("-", "") + ":1"
        payload = encoded({"transactionId": transaction, "amount": amount, "currency": "USD", "recipient": self.wallet["recipient"],
            "name": self.wallet["name"], "provider": "EVC", "country": "SO", "method": "wallet"})
        return key, {"partner_tx_id": transaction, "amount": amount, "currency": "USD", "recipient": self.wallet["recipient"],
            "provider": "EVC", "payout_channel": "wallet", "request_payload": {"TransactionId": transaction, "RequestKey": key,
                "PayloadHash": digest(payload), "Payload": payload.decode()}}

    def test_wallet_account_is_authenticated_and_response_bound_to_request(self):
        request = self.request("POST", "/wallet-accounts/verify", self.wallet)
        status, headers, raw, _ = self.sim.handle(*request)
        self.assertEqual(200, status); self.assertEqual("Match", json.loads(raw)["result"])
        prefix = [request[0], request[1], request[2]["X-Simulator-Timestamp"], request[2]["X-Simulator-Nonce"], digest(request[3]), ""]
        canonical = "\n".join(["simulator-response-v1"] + prefix + [str(status), headers["X-Simulator-Timestamp"], digest(raw)])
        self.assertEqual(mac(self.secret, canonical), headers["X-Simulator-Signature"])

    def test_unknown_wallet_is_not_invented(self):
        status, _, raw, _ = self.sim.handle(*self.request("POST", "/wallet-accounts/verify", {**self.wallet, "recipient": "+252619999999"}))
        self.assertEqual(200, status); self.assertEqual("NoMatch", json.loads(raw)["result"])

    def test_optional_recipient_policy_accepts_unregistered_account_without_claiming_match(self):
        self.wallet = {**self.wallet, "recipient": "+252100000001", "name": "Unregistered Recipient"}
        key, data = self.instruction()
        self.assertEqual(409, self.sim.handle(*self.request("POST", "/payouts-create", data, key))[0])
        self.sim = Simulator(Path(self.directory.name) / "test.sqlite", self.api_key, self.secret, "Test", [], skip_recipient_verification=True)
        status, _, raw, _ = self.sim.handle(*self.request("POST", "/payouts-create", data, key))
        self.assertEqual(201, status)
        self.assertEqual("DevelopmentSkipped", json.loads(raw)["recipient_verification"])
        self.assertEqual("RECEIVED", json.loads(raw)["status"])
        # Explicit lookup still reports the truth, even when payout lookup is optional.
        status, _, raw, _ = self.sim.handle(*self.request("POST", "/wallet-accounts/verify", self.wallet))
        self.assertEqual("NoMatch", json.loads(raw)["result"])
        key, over = self.instruction(500.01)
        self.assertEqual(409, self.sim.handle(*self.request("POST", "/payouts-create", over, key))[0])
        self.assertEqual(401, self.sim.handle("GET", "/simulation/evidence", {"X-API-Key": self.api_key}, b"")[0])

    def test_optional_recipient_policy_cannot_enable_production_or_staging(self):
        for environment in ("Production", "Staging"):
            with self.subTest(environment=environment), self.assertRaisesRegex(ValueError, "SIMULATOR_ENVIRONMENT_REQUIRED"):
                Simulator(Path(self.directory.name) / "test.sqlite", self.api_key, self.secret, environment, [], skip_recipient_verification=True)

    def test_api_key_alone_is_rejected(self):
        self.assertEqual(401, self.sim.handle("GET", "/simulation/evidence", {"X-API-Key": self.api_key}, b"")[0])

    def test_wrong_key_and_tampered_request_components_are_rejected(self):
        for header, value in [("X-API-Key", "bad"), ("X-Simulator-Timestamp", "1"), ("X-Simulator-Nonce", "0" * 64),
                ("X-Simulator-Body-SHA256", "0" * 64), ("X-Simulator-Signature", "0" * 64), ("Idempotency-Key", "tampered")]:
            with self.subTest(header=header):
                self.assertEqual(401, self.sim.handle(*self.request("POST", "/wallet-accounts/verify", self.wallet, headers={header: value}))[0])
        request = self.request("POST", "/wallet-accounts/verify", self.wallet)
        self.assertEqual(401, self.sim.handle("GET", *request[1:])[0])
        self.assertEqual(401, self.sim.handle(request[0], "/different", *request[2:])[0])

    def test_replay_is_rejected_after_restart(self):
        request = self.request("POST", "/wallet-accounts/verify", self.wallet)
        self.assertEqual(200, self.sim.handle(*request)[0]); self.sim = self.restart()
        result = self.sim.handle(*request)
        self.assertEqual(401, result[0]); self.assertEqual("REPLAY_DETECTED", json.loads(result[2])["code"])

    def test_exact_limit_and_idempotent_submission_and_conflicting_reuse(self):
        key, data = self.instruction()
        first = self.sim.handle(*self.request("POST", "/payouts-create", data, key))
        self.assertEqual(201, first[0]); self.assertEqual("RECEIVED", json.loads(first[2])["status"])
        second = self.sim.handle(*self.request("POST", "/payouts-create", data, key))
        self.assertEqual(200, second[0]); self.assertEqual(json.loads(first[2])["id"], json.loads(second[2])["id"])
        self.assertEqual(409, self.sim.handle(*self.request("POST", "/payouts-create", {**data, "amount": 499}, key))[0])

    def test_500_01_rejected(self):
        key, data = self.instruction(500.01)
        result = self.sim.handle(*self.request("POST", "/payouts-create", data, key))
        self.assertEqual(409, result[0]); self.assertEqual("SOMALIA_WALLET_RECEIVE_LIMIT_EXCEEDED", json.loads(result[2])["code"])

    def test_lost_response_recovers_by_key_after_restart_without_another_submission(self):
        self.sim.handle(*self.request("POST", "/simulation/fault", {"drop_next_submission": True}))
        key, data = self.instruction()
        result = self.sim.handle(*self.request("POST", "/payouts-create", data, key)); self.assertTrue(result[3])
        self.sim = self.restart()
        result = self.sim.handle(*self.request("GET", "/payouts/by-request-key/" + key, key=key))
        self.assertEqual(200, result[0]); self.assertEqual("RECEIVED", json.loads(result[2])["status"])
        evidence = json.loads(self.sim.handle(*self.request("GET", "/simulation/evidence"))[2])
        self.assertEqual(1, evidence["submissions"]); self.assertEqual(0, evidence["callbacks"])

    def test_terminal_event_is_durable_and_separate_from_acceptance(self):
        key, data = self.instruction(); self.sim.handle(*self.request("POST", "/payouts-create", data, key))
        result = self.sim.handle(*self.request("POST", "/simulation/terminal", {"request_key": key, "status": "SENT"}))
        self.assertEqual(200, result[0]); self.assertEqual("Paid", json.loads(result[2])["status"])
        self.sim = self.restart()
        with self.sim.connect() as db:
            self.assertEqual(1, db.execute("SELECT count(*) FROM callbacks WHERE accepted=0").fetchone()[0])
        self.assertEqual(409, self.sim.handle(*self.request("POST", "/simulation/terminal", {"request_key": key, "status": "SENT"}))[0])

    def test_production_and_staging_are_rejected(self):
        for environment in ["Production", "Staging", "", "development"]:
            with self.assertRaisesRegex(ValueError, "SIMULATOR_ENVIRONMENT_REQUIRED"):
                Simulator(Path(self.directory.name) / "forbidden.sqlite", self.api_key, self.secret, environment, [])

    def test_mount_is_bound_in_signature(self):
        result = self.sim.handle(*self.request("POST", "/development/v1/wallet-accounts/verify", self.wallet))
        self.assertEqual(200, result[0])


if __name__ == "__main__":
    unittest.main()
