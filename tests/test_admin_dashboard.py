"""Dashboard authentication, safe read adapters and exact monetary responses."""
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

import backend_core as c
from test_existing_backend import pg, setup, submit, payload
from test_existing_http import client


def sign_in(http, main, setup, index=0):
    from browser_security import create
    with main.SessionLocal.begin() as db:
        token, csrf = create(db, setup['admins'][index]['id'], main.settings.secret_key)
    http.cookies.set('session', token)
    http.cookies.set('csrf_token', csrf)
    return {'X-CSRF-Token': csrf}


def test_dashboard_adapters_are_admin_only_and_session_scoped(pg, setup, client):
    http, main = client
    paths = ['/admin', '/api/preview/admin', '/admin/api/session', '/admin/api/partnerships', '/admin/api/payouts/' + str(uuid4())]
    for path in paths:
        assert http.get(path).status_code == 401
    sign_in(http, main, setup)
    session = http.get('/admin/api/session')
    assert session.json()['role'] == 'admin'
    assert session.json()['scope'] == 'All partners'
    assert session.headers['Cache-Control'] == 'no-store'
    page = http.get('/admin')
    assert page.status_code == 200
    assert '/static/admin_dashboard.css' in page.text
    assert 'fonts.googleapis.com' not in page.text
    assert 'Executor token' not in page.text
    preview = http.get('/api/preview/admin', follow_redirects=False)
    assert preview.status_code == 303 and preview.headers['Location'] == '/admin'
    with pg.begin() as db:
        c.run(db, "UPDATE users SET role='partner' WHERE id=:id", id=setup['admins'][0]['id'])
    for path in paths:
        assert http.get(path).status_code == 403


def test_details_return_recorded_history_without_credentials_or_raw_instructions(pg, setup, client):
    http, main = client
    payout = submit(pg, setup, payload(amount='123.45', request_payload={'secret': 'DO-NOT-EXPOSE'}))
    sign_in(http, main, setup)
    response = http.get('/admin/api/payouts/' + payout['id'])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['id'] == payout['id'] and data['amount'] == '123.45'
    assert data['reservation']['amount'] == '123.45'
    assert data['partner_id'] == setup['partner']
    assert 'events' in data and 'attempts' in data
    assert 'request_payload' not in data and 'DO-NOT-EXPOSE' not in response.text
    assert 'ussd_text' not in data and 'instructions' not in response.text
    assert http.get('/admin/api/payouts/' + str(uuid4())).status_code == 404
    assert http.get('/admin/api/payouts/not-a-uuid').status_code == 422


def test_enquiry_search_is_literal_bounded_paginated_and_safe(pg, setup, client):
    http, main = client
    sign_in(http, main, setup)
    with pg.begin() as db:
        for name in ['<img src=x onerror=alert(1)>', 'Company 100%_match', 'Third company']:
            identifier = uuid4()
            c.run(db, '''INSERT INTO public_partnership_enquiries
                (id,reference,payload_hash,company_name,country,contact_name,email,monthly_volume,channels)
                VALUES(:id,:reference,:hash,:company,'Somalia','Contact','contact@example.test',
                'Under $10k / month','Wallets + banks')''', id=identifier, reference='HB-P-' + identifier.hex[:12],
                hash='x' * 64, company=name)
    before = http.get('/admin/api/partnerships?limit=2').json()
    after = http.get('/admin/api/partnerships?limit=2&offset=2').json()
    assert before['total'] == 3 and len(before['items']) == 2 and len(after['items']) == 1
    assert len({row['reference'] for row in before['items'] + after['items']}) == 3
    literal = http.get('/admin/api/partnerships', params={'q': '%_'}).json()
    assert literal['total'] == 1 and literal['items'][0]['company_name'] == 'Company 100%_match'
    assert http.get('/admin/api/partnerships?q=absent').json()['items'] == []
    assert http.get('/admin/api/partnerships?limit=201').status_code == 422
    assert http.get('/admin/api/partnerships?offset=-1').status_code == 422
    assert http.get('/admin/api/partnerships', params={'q': 'a' * 161}).status_code == 422


def test_funds_use_recorded_currency_and_exact_decimal_strings(pg, setup, client):
    http, main = client
    sign_in(http, main, setup)
    result = http.get('/admin/api/funds/partners').json()
    row = next(item for item in result['partners'] if item['id'] == setup['partner'])
    assert row['funding_currency'] == 'USD'
    assert row['ledger_enabled'] is True
    assert isinstance(row['balance_available'], str) and isinstance(row['balance_total'], str)
    assert Decimal(row['balance_total']) == Decimal(row['balance_available']) + Decimal(row['balance_reserved'])
    history = http.get('/admin/api/funds/history/' + str(setup['partner']))
    assert history.status_code == 200 and history.json()['funding_currency'] == 'USD'
    assert http.get('/admin/api/funds/history/' + str(setup['partner']) + '?limit=201').status_code == 422
    assert http.get('/admin/api/funds/history/2147483647').status_code == 404
    for query in ('page=0', 'limit=101', 'search=' + 'x' * 161):
        assert http.get('/admin/api/funds/partners?' + query).status_code == 422


def test_dashboard_funding_uses_csrf_and_backend_reference_idempotency(pg, setup, client):
    http, main = client
    headers = sign_in(http, main, setup)
    body = dict(partner_id=setup['partner'], amount='123.45', reference='DASHBOARD-FUNDING', note='bank://test-receipt')
    assert http.post('/admin/api/funds/deposit', json=body).status_code == 403
    accepted = http.post('/admin/api/funds/deposit', json=body, headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['journal_id']
    replay = http.post('/admin/api/funds/deposit', json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()['journal_id'] == accepted.json()['journal_id']
    assert replay.json() == accepted.json()
    assert http.post('/admin/api/funds/deposit', json={**body, 'amount': '124.45'}, headers=headers).status_code == 409
    history = http.get('/admin/api/funds/history/' + str(setup['partner'])).json()['history']
    entry = next(item for item in history if item['reference'] == body['reference'])
    assert entry['amount'] == '123.45'
    assert sum(item['reference'] == body['reference'] for item in history) == 1


def test_summary_counts_uncertain_cancelled_rejected_and_held_jobs(pg, setup, client):
    http, main = client
    submit(pg, setup)
    with pg.begin() as db:
        payout = c.row(db, 'SELECT * FROM payouts')
        c.change(db, payout, 'UNKNOWN', 'Dashboard test', 'Uncertain result')
        c.run(db, "UPDATE payout_queue SET status='HELD'")
    sign_in(http, main, setup)
    summary = http.get('/admin/api/summary')
    assert summary.status_code == 200 and summary.headers['Cache-Control'] == 'no-store'
    assert summary.json()['payouts']['unknown'] == 1
    assert summary.json()['queue']['held'] == 1
    assert summary.json()['payouts']['cancelled'] == summary.json()['payouts']['rejected'] == 0
    queue = http.get('/admin/api/queue')
    assert queue.status_code == 200 and queue.json()['items'][0]['queue_status'] == 'HELD'
    assert isinstance(queue.json()['items'][0]['amount'], str)
    payouts = http.get('/admin/api/payouts')
    assert payouts.status_code == 200 and isinstance(payouts.json()['items'][0]['amount'], str)
