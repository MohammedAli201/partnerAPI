"""Authenticated view of synthetic payouts inside the original partner admin app."""
import json
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from protocol import Rejection, encoded


def install(app, simulator, require_admin):
    @app.get('/development/admin-payouts.js')
    def original_dashboard_script(actor=Depends(require_admin)):
        return Response(Path(__file__).with_name('original_admin_payouts.js').read_text(encoding='utf-8'),
            media_type='application/javascript', headers={'Cache-Control': 'no-store'})

    @app.get('/admin/api/development-payouts')
    def payouts(actor=Depends(require_admin)):
        with simulator.connect() as db:
            rows = db.execute('SELECT id,status,body FROM payouts ORDER BY rowid DESC LIMIT 200').fetchall()
            result = []
            for row in rows:
                body = json.loads(row['body'])
                recipient = body.get('recipient', '')
                result.append({'id': row['id'], 'transactionId': body['partner_tx_id'],
                    'status': row['status'], 'amount': body['amount'], 'currency': body['currency'],
                    'provider': body['provider'], 'recipient': '***' + recipient[-2:]})
            return {'payouts': result, 'submissions': db.execute('SELECT count(*) FROM payouts').fetchone()[0]}

    @app.post('/admin/api/development-payouts/{payout_id}/terminal')
    async def terminal(payout_id: UUID, request: Request, actor=Depends(require_admin)):
        origin = urlsplit(request.headers.get('origin', ''))
        if (origin.scheme, origin.netloc) != (request.url.scheme, request.url.netloc) or request.headers.get('x-simulator-action') != 'terminal':
            raise HTTPException(403, detail='SAME_ORIGIN_ACTION_REQUIRED')
        if not request.headers.get('content-type', '').startswith('application/json'):
            raise HTTPException(415, detail='JSON_REQUIRED')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096: raise HTTPException(413, detail='REQUEST_TOO_LARGE')
        try:
            data = json.loads(raw)
            if not isinstance(data.get('reason'), str) or not data['reason'].strip():
                raise HTTPException(400, detail='TERMINAL_REASON_REQUIRED')
            with simulator.connect() as db:
                row = db.execute('SELECT request_key FROM payouts WHERE id=?', (str(payout_id),)).fetchone()
            if not row: raise HTTPException(404, detail='PAYOUT_NOT_FOUND')
            status, event, _ = simulator.dispatch('POST', '/simulation/terminal', '',
                encoded({'request_key': row['request_key'], 'status': data.get('status'), 'reason': data['reason']}),
                operator='original_partner_admin:' + str(actor))
            return Response(encoded({'eventId': event['event_id'], 'status': event['status'], 'callbackQueued': True}),
                status_code=status, media_type='application/json')
        except Rejection as error:
            raise HTTPException(error.status, detail=error.code) from None
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, detail='INVALID_REQUEST') from None

    @app.get('/admin/development-payouts', response_class=HTMLResponse)
    def page(actor=Depends(require_admin)):
        return Path(__file__).with_name('partner_dashboard.html').read_text(encoding='utf-8')

    # Add the entry point to the existing admin page without altering its repo,
    # authentication, funds ledger, executor routes or templates.
    @app.middleware('http')
    async def dashboard_link(request, call_next):
        response = await call_next(request)
        if request.method != 'GET' or request.url.path != '/admin' or response.status_code != 200 or 'text/html' not in response.headers.get('content-type', ''):
            return response
        body = b''.join([chunk async for chunk in response.body_iterator])
        link = b'<section class="panel"><p>JubaTech test payouts appear in Transactions below. Select a terminal status and enter a reason to send a test result.</p><p><a href="/admin/development-payouts">View accepted test payouts and send a terminal test result</a></p></section>'
        body = body.replace(b'</header>', b'</header>' + link, 1)
        body = body.replace(b'</body>', b'<script src="/development/admin-payouts.js"></script></body>', 1)
        headers = dict(response.headers)
        headers.pop('content-length', None)
        return Response(body, status_code=response.status_code, headers=headers, background=response.background)
