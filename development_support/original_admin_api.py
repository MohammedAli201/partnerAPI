"""Read projection of signed test payouts into the original administrator API.

No payout is copied into the original executor queue or funds ledger. Test rows
come first, newest first within that group, then the original app's ordered rows.
"""
import json
from uuid import UUID
from fastapi import Depends, HTTPException, Request


def payout_view(row, partner_id=None):
    body = json.loads(row['body'])
    return {
        'id': row['id'], 'partner_id': partner_id, 'partner_tx_id': body['partner_tx_id'],
        'amount': body['amount'], 'currency': body['currency'],
        'recipient': '***' + body.get('recipient', '')[-2:], 'provider': body['provider'],
        'status': row['status'], 'created_at': None, 'updated_at': None,
        'queue_status': None, 'worker_id': None, 'lease_until': None,
        'is_development_simulation': True,
    }


def combined_page(simulator, original_page, q, status, limit, offset, partner_id):
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    where, params = ['1=1'], []
    if status:
        where.append('status = ?')
        params.append(status)
    if q:
        where.append("(json_extract(body,'$.recipient') LIKE ? OR json_extract(body,'$.partner_tx_id') LIKE ? OR id LIKE ?)")
        params.extend(['%' + q + '%'] * 3)
    predicate = ' AND '.join(where)
    with simulator.connect() as db:
        count = db.execute('SELECT count(*) FROM payouts WHERE ' + predicate, params).fetchone()[0]
        rows = db.execute('SELECT id,status,body FROM payouts WHERE ' + predicate +
            ' ORDER BY rowid DESC LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
    items = [payout_view(row, partner_id) for row in rows]
    remaining = limit - len(items)
    legacy = original_page(q, status, max(1, remaining), max(0, offset - count))
    if remaining:
        items.extend(legacy['items'][:remaining])
    return {'total': count + legacy['total'], 'limit': limit, 'offset': offset, 'items': items}


def combined_summary(simulator, result):
    with simulator.connect() as db:
        counts = db.execute('SELECT status,count(*) AS total FROM payouts GROUP BY status').fetchall()
    for row in counts:
        status = row['status'].lower()
        if status in result['payouts']:
            result['payouts'][status] += row['total']
    return result


def replace_reads(app, paths):
    app.router.routes[:] = [route for route in app.router.routes
        if not (getattr(route, 'path', '') in paths and getattr(route, 'methods', set()) == {'GET'})]
    app.openapi_schema = None


def install(app, simulator, require_admin, original, partner_id=None):
    # Replace the two read routes so FastAPI's original first-match routing cannot
    # hide the projection. Original write and executor routes stay registered.
    replace_reads(app, {'/admin/api/payouts', '/admin/api/summary'})

    @app.get('/admin/api/payouts')
    def payouts(request: Request, q: str | None = None, status: str | None = None,
                limit: int = 50, offset: int = 0, actor=Depends(require_admin)):
        return combined_page(simulator, lambda *args: original.payouts(request, *args),
            q, status, limit, offset, partner_id)

    @app.get('/admin/api/summary')
    def summary(request: Request, actor=Depends(require_admin)):
        return combined_summary(simulator, original.summary(request))

    @app.get('/admin/api/payouts/{payout_id}')
    def detail(payout_id: UUID, actor=Depends(require_admin)):
        with simulator.connect() as db:
            row = db.execute('SELECT id,status,body FROM payouts WHERE id=?', (str(payout_id),)).fetchone()
            if row:
                result = payout_view(row, partner_id)
                body = json.loads(row['body'])
                # Counts only; signed callback bodies and credentials are private.
                callbacks = db.execute("SELECT count(*) AS total,coalesce(sum(accepted),0) AS accepted FROM callbacks WHERE json_extract(raw,'$.provider_reference')=?",
                    (str(payout_id),)).fetchone()
                result['callback'] = {'queued': callbacks['total'], 'accepted': callbacks['accepted']}
                result['recipient_verification'] = body.get('recipient_verification')
                return result
        result = original.detail(payout_id)
        if result is None:
            raise HTTPException(404, detail='PAYOUT_NOT_FOUND')
        return result

    app.openapi_schema = None


def install_partner(app, simulator, require_partner, original, partner_id):
    if type(partner_id) is not int or partner_id <= 0:
        raise ValueError('SIMULATOR_PARTNER_BINDING_REQUIRED')
    replace_reads(app, {'/partner/api/payouts', '/partner/api/summary'})

    @app.get('/partner/api/payouts')
    def payouts(request: Request, q: str | None = None, status: str | None = None,
                limit: int = 50, offset: int = 0, session=Depends(require_partner)):
        read = lambda *args: original.partner_payouts(request, session, *args)
        if session['partner_id'] != partner_id:
            return read(q, status, limit, offset)
        return combined_page(simulator, read, q, status, limit, offset, partner_id)

    @app.get('/partner/api/summary')
    def summary(request: Request, session=Depends(require_partner)):
        result = original.partner_summary(request, session)
        if session['partner_id'] == partner_id:
            return combined_summary(simulator, result)
        return result
