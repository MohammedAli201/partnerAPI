import copy
import json
import unittest
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import test_protocol
from original_admin_api import install, install_partner
from partner_dashboard import install as install_dashboard


class OriginalReader:
    def __init__(self):
        self.rows = [{'id': str(uuid4()), 'partner_id': owner, 'partner_tx_id': 'native-' + str(i),
            'status': status, 'recipient': 'native-recipient', 'amount': '12.00', 'currency': 'USD'}
            for i, (owner, status) in enumerate([(5, 'RECEIVED'), (5, 'SENT'), (4, 'SENT')])]

    def page(self, rows, q, status, limit, offset):
        rows = [row for row in rows if (not status or row['status'] == status) and
            (not q or q.casefold() in (row['recipient'] + row['partner_tx_id'] + row['id']).casefold())]
        limit, offset = max(1, min(limit, 200)), max(0, offset)
        return {'total': len(rows), 'limit': limit, 'offset': offset, 'items': copy.deepcopy(rows[offset:offset + limit])}

    def payouts(self, request, q, status, limit, offset):
        return self.page(self.rows, q, status, limit, offset)

    def summary(self, request):
        return {'payouts': {'received': 1, 'processing': 0, 'sent': 2, 'failed': 0},
            'queue': {'pending': 1, 'in_progress': 0, 'expired': 0}}

    def detail(self, payout_id):
        return next((copy.deepcopy(row) for row in self.rows if row['id'] == str(payout_id)), None)

    def partner_payouts(self, request, session, q, status, limit, offset):
        return self.page([row for row in self.rows if row['partner_id'] == session['partner_id']], q, status, limit, offset)

    def partner_summary(self, request, session):
        rows = [row for row in self.rows if row['partner_id'] == session['partner_id']]
        return {'partner_id': session['partner_id'], 'payouts': {status.lower(): sum(row['status'] == status for row in rows)
            for status in ['RECEIVED', 'PROCESSING', 'SENT', 'FAILED']}, 'balances': {'available': '100', 'reserved': '12'}}


class OriginalAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_protocol.ProtocolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.sim = self.fixture.sim
        self.synthetic = []
        for amount in [10, 20, 30]:
            key, data = self.fixture.instruction(amount)
            result = self.sim.handle(*self.fixture.request('POST', '/payouts-create', data, key))
            self.synthetic.insert(0, json.loads(result[2]))
        self.original = OriginalReader()
        self.app = FastAPI()

        @self.app.get('/admin/api/payouts')
        def original_list():
            return {'incorrect': 'Original first-match route must be replaced'}

        def require_admin(request: Request):
            if request.headers.get('authorization') != 'admin':
                raise HTTPException(403)
            return 'active-admin'

        def require_partner(request: Request):
            header = request.headers.get('authorization')
            if header not in {'partner-5', 'partner-4'}:
                raise HTTPException(403)
            return {'uid': 3, 'role': 'partner', 'partner_id': int(header[-1])}

        self.require_partner = require_partner
        install_dashboard(self.app, self.sim, require_admin)
        install(self.app, self.sim, require_admin, self.original, 5)
        install_partner(self.app, self.sim, require_partner, self.original, 5)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.admin = {'Authorization': 'admin'}

    def get(self, path, role='admin'):
        return self.client.get(path, headers={'Authorization': role})

    def test_exact_original_endpoint_includes_existing_signed_payout_ids(self):
        response = self.get('/admin/api/payouts')
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(6, data['total'])
        self.assertEqual([row['id'] for row in self.synthetic], [row['id'] for row in data['items'][:3]])
        self.assertTrue(all(row['partner_id'] == 5 and row['is_development_simulation'] for row in data['items'][:3]))
        self.assertEqual(self.original.rows, data['items'][3:])
        self.assertNotIn(self.fixture.api_key, response.text)
        self.assertNotIn('request_payload', response.text)
        self.assertNotIn(self.fixture.wallet['recipient'], response.text)
        with self.sim.connect() as db:
            self.assertEqual(3, db.execute('SELECT count(*) FROM payouts').fetchone()[0])
            self.assertEqual(0, db.execute('SELECT count(*) FROM callbacks').fetchone()[0])

    def test_pagination_crosses_store_boundary_without_omitting_or_duplicating_rows(self):
        ids = []
        for offset in [0, 2, 4]:
            page = self.get('/admin/api/payouts?limit=2&offset=' + str(offset)).json()
            self.assertEqual(6, page['total'])
            self.assertEqual(2, len(page['items']))
            ids.extend(row['id'] for row in page['items'])
        self.assertEqual(6, len(set(ids)))
        self.assertEqual([row['id'] for row in self.synthetic + self.original.rows], ids)
        self.assertEqual([], self.get('/admin/api/payouts?offset=100').json()['items'])
        bounded = self.get('/admin/api/payouts?limit=1000&offset=-1').json()
        self.assertEqual(200, bounded['limit'])
        self.assertEqual(0, bounded['offset'])

    def test_filters_and_counts_apply_before_pagination(self):
        for search in [self.synthetic[0]['partner_tx_id'], self.synthetic[0]['id']]:
            result = self.get('/admin/api/payouts?q=' + search.upper()).json()
            self.assertEqual(1, result['total'])
            self.assertEqual(self.synthetic[0]['id'], result['items'][0]['id'])
        result = self.get('/admin/api/payouts?status=RECEIVED&limit=2&offset=2').json()
        self.assertEqual(4, result['total'])
        self.assertEqual(2, len(result['items']))
        self.assertEqual(2, self.get('/admin/api/payouts?status=SENT').json()['total'])
        self.assertEqual(0, self.get('/admin/api/payouts?q=%27%20OR%201%3D1--').json()['total'])

    def test_summary_counts_payouts_without_creating_queue_or_funds_entries(self):
        result = self.get('/admin/api/summary').json()
        self.assertEqual(4, result['payouts']['received'])
        self.assertEqual(self.original.summary(None)['queue'], result['queue'])
        partner = self.get('/partner/api/summary', 'partner-5').json()
        self.assertEqual(4, partner['payouts']['received'])
        self.assertEqual({'available': '100', 'reserved': '12'}, partner['balances'])

    def test_partner_view_includes_only_its_bound_test_records(self):
        result = self.get('/partner/api/payouts?limit=2&offset=2', 'partner-5').json()
        self.assertEqual(5, result['total'])
        self.assertEqual([self.synthetic[2]['id'], self.original.rows[0]['id']], [row['id'] for row in result['items']])
        other = self.get('/partner/api/payouts', 'partner-4').json()
        self.assertEqual(1, other['total'])
        self.assertEqual([self.original.rows[2]], other['items'])
        self.assertEqual(0, self.get('/partner/api/summary', 'partner-4').json()['payouts']['received'])
        self.assertEqual(0, self.get('/partner/api/payouts?q=' + self.synthetic[0]['id'], 'partner-4').json()['total'])

    def test_roles_and_missing_partner_binding_fail_closed(self):
        for path in ['/admin/api/payouts', '/admin/api/summary', '/admin/api/payouts/' + self.synthetic[0]['id']]:
            self.assertEqual(403, self.client.get(path).status_code)
            self.assertEqual(403, self.get(path, 'partner-5').status_code)
        for role in ['admin', 'inactive-partner', '']:
            self.assertEqual(403, self.get('/partner/api/payouts', role).status_code)
        with self.assertRaisesRegex(ValueError, 'SIMULATOR_PARTNER_BINDING_REQUIRED'):
            install_partner(FastAPI(), self.sim, self.require_partner, self.original, None)

    def test_detail_and_terminal_action_share_the_original_payout_identity(self):
        payout_id = self.synthetic[0]['id']
        before = self.get('/admin/api/payouts/' + payout_id).json()
        self.assertEqual({'queued': 0, 'accepted': 0}, before['callback'])
        action = self.client.post('/admin/api/development-payouts/' + payout_id + '/terminal',
            json={'status': 'SENT', 'reason': 'Disposable original-view test'},
            headers={**self.admin, 'Origin': 'http://testserver', 'X-Simulator-Action': 'terminal'})
        self.assertEqual(200, action.status_code)
        detail = self.get('/admin/api/payouts/' + payout_id).json()
        self.assertEqual('SENT', detail['status'])
        self.assertEqual({'queued': 1, 'accepted': 0}, detail['callback'])
        self.assertEqual(3, self.get('/admin/api/payouts?status=SENT').json()['total'])
        native = self.get('/admin/api/payouts/' + self.original.rows[0]['id']).json()
        self.assertEqual(self.original.rows[0], native)
        self.assertEqual(404, self.get('/admin/api/payouts/' + str(uuid4())).status_code)
