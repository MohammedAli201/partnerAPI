import json
import hashlib
import hmac
import sqlite3
import threading
import unittest
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
import test_protocol
from fastapi_extension import install
from partner_dashboard import install as install_dashboard
from protocol import digest, mac


class FastApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_protocol.ProtocolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.sim = self.fixture.sim
        self.original_started = self.original_stopped = False

        @asynccontextmanager
        async def lifespan(app):
            self.original_started = True
            yield
            self.original_stopped = True

        self.app = FastAPI(lifespan=lifespan)

        def admin(request: Request):
            if request.headers.get('authorization') != 'test-admin':
                raise HTTPException(403)
            return 'synthetic-operator'

        @self.app.get('/admin', response_class=HTMLResponse)
        def original_admin():
            return '<header>Original dashboard</header><main>Original queue</main>'

        install(self.app, self.sim)
        install_dashboard(self.app, self.sim, admin)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.admin_headers = {'Authorization': 'test-admin', 'Origin': 'http://testserver',
            'X-Simulator-Action': 'terminal'}

    def signed(self, method, path, data=None, key=''):
        request = self.fixture.request(method, path, data, key)
        response = self.client.request(method, path, content=request[3], headers=request[2])
        return request, response

    def submit(self):
        key, data = self.fixture.instruction()
        _, response = self.signed('POST', '/development/v1/payouts-create', data, key)
        self.assertEqual(201, response.status_code)
        return key, response.json()

    def test_mount_preserves_escaped_request_key_and_signed_response(self):
        key, payout = self.submit()
        path = '/development/v1/payouts/by-request-key/' + quote(key, safe='')
        request, response = self.signed('GET', path, key=key)
        self.assertEqual(200, response.status_code)
        self.assertEqual(payout['id'], response.json()['id'])
        self.assertEqual('RECEIVED', response.json()['status'])
        prefix = ['GET', path, request[2]['X-Simulator-Timestamp'], request[2]['X-Simulator-Nonce'], digest(b''), key]
        canonical = '\n'.join(['simulator-response-v1'] + prefix + ['200', response.headers['X-Simulator-Timestamp'], digest(response.content)])
        self.assertEqual(mac(self.fixture.secret, canonical), response.headers['X-Simulator-Signature'])
        replay = self.client.get(path, headers=request[2])
        self.assertEqual(401, replay.status_code)
        self.assertEqual('REPLAY_DETECTED', replay.json()['code'])
        _, wrong_path = self.signed('GET', path.replace('payouts/', 'wrong/'), key=key)
        self.assertEqual(404, wrong_path.status_code)
        self.assertEqual(401, self.client.get(path).status_code)

    def test_custom_original_lifespan_also_starts_and_stops_callback_worker(self):
        started = threading.Event()
        stopped = threading.Event()

        def worker(simulator, stop):
            started.set()
            stop.wait(3)
            stopped.set()

        with patch('server.callback_worker', worker):
            # install captures the worker, so install into a fresh app for this assertion.
            original = self.app.router.lifespan_context
            fresh = FastAPI(lifespan=original)
            install(fresh, self.sim)
            with TestClient(fresh):
                self.assertTrue(started.wait(1))
                self.assertTrue(self.original_started)
            self.assertTrue(stopped.is_set())
            self.assertTrue(self.original_stopped)

    def test_admin_view_masks_recipient_and_keeps_original_dashboard(self):
        _, payout = self.submit()
        for path in ['/admin/development-payouts', '/admin/api/development-payouts']:
            self.assertEqual(403, self.client.get(path).status_code)
        response = self.client.get('/admin/api/development-payouts', headers=self.admin_headers)
        self.assertEqual(1, response.json()['submissions'])
        self.assertEqual(payout['id'], response.json()['payouts'][0]['id'])
        self.assertNotIn(self.fixture.wallet['recipient'], response.text)
        self.assertNotIn('request_payload', response.text)
        self.assertNotIn(self.fixture.api_key, response.text)
        page = self.client.get('/admin')
        self.assertIn('Original queue', page.text)
        self.assertIn('/admin/development-payouts', page.text)

    def test_terminal_action_requires_admin_same_origin_and_reason(self):
        _, payout = self.submit()
        path = '/admin/api/development-payouts/' + payout['id'] + '/terminal'
        body = {'status': 'SENT', 'reason': 'Synthetic completion'}
        self.assertEqual(403, self.client.post(path, json=body).status_code)
        self.assertEqual(403, self.client.post(path, json=body, headers={'Authorization': 'test-admin'}).status_code)
        self.assertEqual(403, self.client.post(path, json=body,
            headers={**self.admin_headers, 'Origin': 'http://attacker.example'}).status_code)
        self.assertEqual(400, self.client.post(path, json={'status': 'SENT'}, headers=self.admin_headers).status_code)
        self.assertEqual(400, self.client.post(path, json={'status': 'SENT', 'reason': 'x'*501}, headers=self.admin_headers).status_code)
        with self.sim.connect() as db:
            self.assertEqual('RECEIVED', db.execute('SELECT status FROM payouts').fetchone()[0])
            self.assertEqual(0, db.execute('SELECT count(*) FROM callbacks').fetchone()[0])

    def test_explicit_terminal_action_queues_one_callback_and_append_only_audit(self):
        key, payout = self.submit()
        path = '/admin/api/development-payouts/' + payout['id'] + '/terminal'
        body = {'status': 'SENT', 'reason': 'Synthetic completion'}
        first = self.client.post(path, json=body, headers=self.admin_headers)
        self.assertEqual(200, first.status_code)
        self.assertTrue(first.json()['callbackQueued'])
        self.assertEqual(409, self.client.post(path, json=body, headers=self.admin_headers).status_code)
        with self.sim.connect() as db:
            self.assertEqual(1, db.execute('SELECT count(*) FROM payouts').fetchone()[0])
            self.assertEqual(1, db.execute('SELECT count(*) FROM callbacks WHERE accepted=0').fetchone()[0])
            action = db.execute('SELECT * FROM terminal_actions').fetchone()
            self.assertEqual('original_partner_admin:synthetic-operator', action['actor'])
            self.assertEqual(body['reason'], action['reason'])
            self.assertEqual(first.json()['eventId'], action['event_id'])
            for sql in ['DELETE FROM terminal_actions', "UPDATE terminal_actions SET actor='other'"]:
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'AUDIT_APPEND_ONLY'):
                    db.execute(sql)
        _, lookup = self.signed('GET', '/development/v1/payouts/by-request-key/' + quote(key, safe=''), key=key)
        self.assertEqual('SENT', lookup.json()['status'])

    def test_body_size_limits_apply_before_dispatch(self):
        self.assertEqual(413, self.client.post('/development/v1/payouts-create', content=b'x'*65537).status_code)
        _, payout = self.submit()
        response = self.client.post('/admin/api/development-payouts/' + payout['id'] + '/terminal',
            content=b'x'*4097, headers={**self.admin_headers, 'Content-Type': 'application/json'})
        self.assertEqual(413, response.status_code)

    def test_mounted_lifespan_delivers_authenticated_terminal_callback(self):
        received = threading.Event()
        verified = []
        fixture = self.fixture

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                canonical = (self.headers['X-JubaTech-Timestamp'] + '.' + self.headers['X-JubaTech-Nonce'] + '.').encode() + raw
                signature = hmac.new(fixture.secret.encode(), canonical, hashlib.sha256).hexdigest()
                valid = self.headers['X-API-Key'] == fixture.api_key and hmac.compare_digest(signature, self.headers['X-JubaTech-Signature'])
                verified.append(valid and json.loads(raw)['status'] == 'Paid')
                self.send_response(202 if valid else 401)
                self.end_headers()
                received.set()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Callback)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.sim.callback_url = 'http://127.0.0.1:' + str(server.server_port) + '/callback'
        self.sim.callback_secret = fixture.secret
        _, payout = self.submit()
        try:
            with TestClient(self.app) as client:
                response = client.post('/admin/api/development-payouts/' + payout['id'] + '/terminal',
                    json={'status': 'SENT', 'reason': 'Explicit disposable test completion'}, headers=self.admin_headers)
                self.assertEqual(200, response.status_code)
                self.assertTrue(received.wait(3))
            self.assertEqual([True], verified)
            with self.sim.connect() as db:
                self.assertEqual(1, db.execute('SELECT count(*) FROM callbacks WHERE accepted=1').fetchone()[0])
            self.assertTrue(self.original_started)
            self.assertTrue(self.original_stopped)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
