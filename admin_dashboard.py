"""Authenticated, read-only adapters for the supplied operations dashboard."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text


def make_router(require_role, get_db):
    admin = require_role("admin")
    router = APIRouter(dependencies=[Depends(admin)])

    @router.get("/api/preview/admin", include_in_schema=False)
    def supplied_preview_entry():
        # Compatibility with the React redirect included in the supplied src.zip.
        return RedirectResponse("/admin", status_code=303, headers={"Cache-Control": "no-store"})

    @router.get("/admin/api/session")
    def session(response: Response, user=Depends(admin)):
        response.headers["Cache-Control"] = "no-store"
        return {"username": user["username"], "role": "admin", "scope": "All partners"}

    @router.get("/admin/api/payouts/{payout_id}")
    def payout_detail(payout_id: UUID, response: Response, db=Depends(get_db)):
        response.headers["Cache-Control"] = "no-store"
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        payout = db.execute(text("""SELECT p.id,p.partner_id,partner.name partner_name,
            p.partner_tx_id,p.amount,p.currency,p.recipient,p.provider,p.status,
            p.status_version,p.hold_reason,p.created_at,p.updated_at,
            q.status queue_status,q.worker_id,q.lease_until,q.created_at queue_created,
            q.dispatch_count attempt_count,e.provider_ref,e.captured_at evidence_captured_at
            FROM payouts p JOIN partners partner ON partner.id=p.partner_id
            LEFT JOIN payout_queue q ON q.payout_id=p.id
            LEFT JOIN payout_evidence e ON e.payout_id=p.id WHERE p.id=:id"""),
            {"id": payout_id}).mappings().first()
        if not payout:
            raise HTTPException(404, "Payout not found")
        reservation = db.execute(text("""SELECT amount,fee,total,status
            FROM payout_reservations WHERE payout_id=:id"""), {"id": payout_id}).mappings().first()
        history = db.execute(text("""SELECT new_status status,old_status,reason message,created_at
            FROM payout_history WHERE payout_id=:id ORDER BY version"""), {"id": payout_id}).mappings().all()
        attempts = db.execute(text("""SELECT attempt_number,phase,worker_id,created_at,armed_at,
            resolved_at,provider_reference FROM payout_attempts WHERE payout_id=:id
            ORDER BY attempt_number"""), {"id": payout_id}).mappings().all()
        callback = db.execute(text("""SELECT state webhook_status,attempts webhook_attempts,
            accepted_at webhook_accepted_at,last_status_code webhook_last_response
            FROM payout_webhook_events WHERE payout_id=:id ORDER BY created_at DESC,event_id DESC LIMIT 1"""),
            {"id": payout_id}).mappings().first()
        funding = dict(reservation) if reservation else None
        if funding:
            for name in ("amount", "fee", "total"):
                funding[name] = str(funding[name])
        return {**dict(payout), "amount": str(payout["amount"]), "reservation": funding,
                "events": [dict(row) for row in history], "attempts": [dict(row) for row in attempts],
                **(dict(callback) if callback else {})}

    @router.get("/admin/api/partnerships")
    def enquiries(response: Response, q: str = Query("", max_length=160),
                  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db=Depends(get_db)):
        response.headers["Cache-Control"] = "no-store"
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        params = {"q": "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
                  "limit": limit, "offset": offset}
        where = """company_name ILIKE :q OR country ILIKE :q OR contact_name ILIKE :q
            OR email ILIKE :q OR reference ILIKE :q"""
        total = db.execute(text(f"SELECT count(*) FROM public_partnership_enquiries WHERE {where}"), params).scalar()
        rows = db.execute(text(f"""SELECT reference,company_name,country,contact_name,email,
            monthly_volume,channels,created_at FROM public_partnership_enquiries WHERE {where}
            ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"""), params).mappings().all()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    return router
