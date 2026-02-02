# # main.py
# from sqlalchemy import func
# # main.py
# from fastapi import Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from sqlalchemy import text
# from uuid import UUID as PyUUID
# from decimal import Decimal
# from schemas import (
#     PayoutCreate,
#     PayoutStatusUpdate,
#     PayoutStatus,
#     ExecutorReport
# )

# from fastapi import FastAPI, Depends, Header, HTTPException, status
# from sqlalchemy.orm import Session

# from database import engine, Base, get_db
# from models import Partner, Payout
# from schemas import PayoutCreate
# from security import verify_api_key
# from models import PayoutQueue
# LEASE_SECS = 120  # Default lease time in seconds
# BATCH_SIZE = 10   # Default batch size
# EXECUTOR_ID = "pi-01" # Default executor ID

# app = FastAPI(title="Partner Payout API")

# # # Create tables (dev only). In production use migrations.
# # Base.metadata.create_all(bind=engine)

# def get_partner_from_api_key(
#     x_api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db),
# ) -> Partner:
#     # Find active partner whose hash matches this key
#     partners = db.query(Partner).filter(Partner.is_active == True).all()
#     for p in partners:
#         if verify_api_key(x_api_key, p.api_key_hash):
#             return p

#     raise HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Invalid API key",
#     )
# from uuid import UUID as PyUUID
# @app.patch("/payouts/{payout_id}/status")
# def update_payout_status(
#     payout_id: PyUUID,
#     body: PayoutStatusUpdate,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     payout = (
#         db.query(Payout)
#         .filter(Payout.id == payout_id, Payout.partner_id == partner.id)
#         .first()
#     )
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     payout.status = body.status.value
#     db.commit()
#     db.refresh(payout)

#     return {"id": str(payout.id), "status": payout.status}
# from sqlalchemy import func

# @app.get("/payouts/stats")
# def payout_stats(
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     rows = (
#         db.query(Payout.status, func.count())
#         .filter(Payout.partner_id == partner.id)
#         .group_by(Payout.status)
#         .all()
#     )

#     stats = {status: count for status, count in rows}

#     return {
#         "payouts": stats,
#         "total": sum(stats.values())
#     }

# @app.get("/queue/stats")
# def queue_stats(
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     rows = (
#         db.query(PayoutQueue.status, func.count())
#         .group_by(PayoutQueue.status)
#         .all()
#     )

#     stats = {status: count for status, count in rows}

#     return {
#         "queue": stats,
#         "total": sum(stats.values())
#     }

# @app.get("/queue/stats/me")
# def my_queue_stats(
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     rows = (
#         db.query(PayoutQueue.status, func.count())
#         .join(Payout, Payout.id == PayoutQueue.payout_id)
#         .filter(Payout.partner_id == partner.id)
#         .group_by(PayoutQueue.status)
#         .all()
#     )

#     stats = {status: count for status, count in rows}

#     return {
#         "queue": stats,
#         "total": sum(stats.values())
#     }

# @app.get("/payouts/{payout_id}")
# def get_payout(
#     payout_id: PyUUID,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     payout = (
#         db.query(Payout)
#         .filter(Payout.id == payout_id, Payout.partner_id == partner.id)
#         .first()
#     )
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     return {
#         "id": str(payout.id),
#         "partner_tx_id": payout.partner_tx_id,
#         "amount": str(payout.amount),
#         "currency": payout.currency,
#         "recipient": payout.recipient,
#         "provider": payout.provider,
#         "status": payout.status,
#         "request_payload": payout.request_payload,
#         "created_at": payout.created_at,
#     }

# @app.post("/payouts", status_code=201)
# def create_payout(
#     payload: PayoutCreate,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     # enforce unique (partner_id, partner_tx_id)
#     exists = (
#         db.query(Payout)
#         .filter(Payout.partner_id == partner.id, Payout.partner_tx_id == payload.partner_tx_id)
#         .first()
#     )
#     if exists:
#         raise HTTPException(
#             status_code=409,
#             detail="Duplicate partner_tx_id for this partner",
#         )

#     payout = Payout(
#         partner_id=partner.id,
#         partner_tx_id=payload.partner_tx_id,
#         amount=payload.amount,
#         currency=payload.currency,
#         recipient=payload.recipient,
#         provider=payload.provider,
#         request_payload=payload.request_payload,
#     )
#     db.add(payout)
#     db.flush()  # makes payout.id available before commit
#     db.add(PayoutQueue(payout_id=payout.id))  
#     db.commit()
#     db.refresh(payout)

#     return {
#         "id": str(payout.id),
#         "status": payout.status,
#         "created_at": payout.created_at,
#     }






# # ---- VERY SIMPLE executor auth (MVP) ----
# # Put this in .env on the API machine: EXECUTOR_TOKEN=supersecret
# import os
# EXECUTOR_TOKEN = os.getenv("EXECUTOR_TOKEN", "change-me")

# from fastapi import Header
# def require_executor_token(x_executor_token: str = Header(..., alias="X-Executor-Token")):
#     if x_executor_token != EXECUTOR_TOKEN:
#         raise HTTPException(status_code=401, detail="Invalid executor token")

# def decide_status(amount: Decimal, bb: Decimal | None, ba: Decimal | None, ussd_text: str):
#     """
#     Server decides business truth.
#     Returns: (new_status, reason_code)
#     """
#     t = (ussd_text or "").lower()

#     # Hard-fail phrases (Somali examples)
#     if "kuguma filna" in t or "haraaga" in t:
#         return ("FAILED", "INSUFFICIENT_BALANCE")

#     # Balance-diff success
#     if bb is not None and ba is not None:
#         diff = bb - ba
#         if diff >= amount:
#             return ("SENT", "BALANCE_DIFF_OK")

#     # Provider success words
#     if any(k in t for k in ["success", "completed", "approved", "reference", "trx", "txid"]):
#         return ("SENT", "USSD_TEXT_OK")

#     return ("FAILED", "AMBIGUOUS")

# @app.post("/internal/executor/report")
# def executor_report(
#     body: ExecutorReport,
#     _auth=Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     # 1) Load payout
#     payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     # 2) Ensure it is currently in queue (optional but recommended)
#     q = db.query(PayoutQueue).filter(PayoutQueue.payout_id == payout.id).first()
#     if not q:
#         # Could be already finalized; still allow evidence insert, but don’t double-finish
#         # For safety, return 409
#         raise HTTPException(status_code=409, detail="Payout not in queue (already finalized?)")

#     # 3) Upsert evidence (SQL approach, no ORM needed)
#     db.execute(text("""
#       INSERT INTO payout_evidence (
#         payout_id, executor_id, balance_before, balance_after, ussd_text, provider_ref
#       )
#       VALUES (:pid, :eid, :bb, :ba, :txt, :pref)
#       ON CONFLICT (payout_id) DO UPDATE SET
#         executor_id = EXCLUDED.executor_id,
#         balance_before = EXCLUDED.balance_before,
#         balance_after  = EXCLUDED.balance_after,
#         ussd_text = EXCLUDED.ussd_text,
#         provider_ref = EXCLUDED.provider_ref,
#         captured_at = now();
#     """), {
#         "pid": str(payout.id),
#         "eid": body.executor_id,
#         "bb": body.balance_before,
#         "ba": body.balance_after,
#         "txt": body.ussd_text,
#         "pref": body.provider_ref,
#     })

#     # 4) Decide final status on server
#     new_status, reason = decide_status(
#         amount=payout.amount,
#         bb=body.balance_before,
#         ba=body.balance_after,
#         ussd_text=body.ussd_text
#     )

#     payout.status = new_status

#     # 5) Remove from queue if final (SENT/FAILED)
#     db.execute(text("DELETE FROM payout_queue WHERE payout_id=:pid"), {"pid": str(payout.id)})

#     db.commit()

#     # 6) TODO: enqueue webhook delivery here (next step)
#     # enqueue_webhook(...)

#     return {
#         "payout_id": str(payout.id),
#         "new_status": new_status,
#         "reason": reason,
#     }
# from sqlalchemy import text
# from datetime import datetime, timezone, timedelta

# from datetime import datetime, timezone, timedelta
# from sqlalchemy import text
# from fastapi import Depends
# from sqlalchemy.orm import Session

# from database import get_db
# from schemas import ExecutorClaimRequest
# from security import require_executor_token  # wherever you put it

# @app.post("/internal/executor/claim")
# def executor_claim(
#     body: ExecutorClaimRequest,
#     _auth=Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)

#     claimed = db.execute(text("""
#     WITH candidates AS (
#       SELECT pq.payout_id
#       FROM payout_queue pq
#       WHERE
#         pq.status = 'PENDING'
#         OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
#       ORDER BY pq.created_at
#       FOR UPDATE SKIP LOCKED
#       LIMIT :limit
#     )
#     UPDATE payout_queue pq
#     SET
#       status = 'IN_PROGRESS',
#       lease_until = :lease_until,
#       worker_id = :worker_id
#     FROM candidates c
#     WHERE pq.payout_id = c.payout_id
#     RETURNING pq.payout_id;
#     """), {
#         "limit": body.batch_size,
#         "lease_until": lease_until,
#         "worker_id": body.executor_id,
#     }).mappings().all()

#     if not claimed:
#         db.commit()
#         return {"jobs": []}

#     payout_ids = [r["payout_id"] for r in claimed]

#     db.execute(text("""
#       UPDATE payouts
#       SET status='PROCESSING'
#       WHERE id = ANY(:ids)
#     """), {"ids": payout_ids})

#     jobs = db.execute(text("""
#       SELECT
#         p.id, p.amount, p.currency, p.recipient, p.provider, p.request_payload
#       FROM payouts p
#       WHERE p.id = ANY(:ids)
#       ORDER BY p.created_at
#     """), {"ids": payout_ids}).mappings().all()

#     db.commit()
#     return {"jobs": [dict(j) for j in jobs]}



# from decimal import Decimal
# from schemas import ExecutorReport
# from sqlalchemy import text
# from fastapi import HTTPException

# def decide_status(amount: Decimal, bb: Decimal | None, ba: Decimal | None, ussd_text: str):
#     t = (ussd_text or "").lower()

#     # Hard fail phrases (Somali + generic)
#     if "kuguma filna" in t or "haraaga" in t:
#         return ("FAILED", "INSUFFICIENT_BALANCE")

#     # Balance diff success (if you can parse balances)
#     if bb is not None and ba is not None:
#         try:
#             diff = bb - ba
#             if diff >= amount:
#                 return ("SENT", "BALANCE_DIFF_OK")
#         except Exception:
#             pass

#     # Text success patterns
#     if any(k in t for k in ["success", "completed", "approved", "reference", "trx", "txid", "ref"]):
#         return ("SENT", "USSD_TEXT_OK")

#     return ("FAILED", "AMBIGUOUS")

# @app.post("/internal/executor/report")
# def executor_report(
#     body: ExecutorReport,
#     _auth=Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     # Ensure payout exists
#     payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     # Ensure still in queue (prevents double finalize)
#     q = db.query(PayoutQueue).filter(PayoutQueue.payout_id == payout.id).first()
#     if not q:
#         raise HTTPException(status_code=409, detail="Payout not in queue (already finalized?)")

#     # Upsert evidence
#     db.execute(text("""
#       INSERT INTO payout_evidence (
#         payout_id, executor_id, balance_before, balance_after, ussd_text, provider_ref
#       )
#       VALUES (:pid, :eid, :bb, :ba, :txt, :pref)
#       ON CONFLICT (payout_id) DO UPDATE SET
#         executor_id = EXCLUDED.executor_id,
#         balance_before = EXCLUDED.balance_before,
#         balance_after  = EXCLUDED.balance_after,
#         ussd_text = EXCLUDED.ussd_text,
#         provider_ref = EXCLUDED.provider_ref,
#         captured_at = now();
#     """), {
#         "pid": str(payout.id),
#         "eid": body.executor_id,
#         "bb": body.balance_before,
#         "ba": body.balance_after,
#         "txt": body.ussd_text or "",
#         "pref": body.provider_ref,
#     })

#     # Decide business status
#     new_status, reason = decide_status(
#         amount=payout.amount,
#         bb=body.balance_before,
#         ba=body.balance_after,
#         ussd_text=body.ussd_text or "",
#     )

#     payout.status = new_status

#     # Remove from queue
#     db.execute(text("DELETE FROM payout_queue WHERE payout_id=:pid"), {"pid": str(payout.id)})

#     db.commit()
#     db.refresh(payout)

#     # TODO: enqueue webhook here (next step)
#     # enqueue_webhook(db, payout, reason)

#     return {"payout_id": str(payout.id), "status": payout.status, "reason": reason}






# main.py
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID as PyUUID

from fastapi import FastAPI, Depends, Header, HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import get_db  # engine/Base not needed here
from models import Partner, Payout, PayoutQueue
from schemas import (
    PayoutCreate,
    PayoutStatusUpdate,
    ExecutorClaimRequest,
    ExecutorReport,
)
from security import verify_api_key

app = FastAPI(title="Partner Payout API")

# =========================================================
# Partner auth (X-API-Key)
# =========================================================

def get_partner_from_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Partner:
    partners = db.query(Partner).filter(Partner.is_active == True).all()
    for p in partners:
        if verify_api_key(x_api_key, p.api_key_hash):
            return p
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


# =========================================================
# Executor auth (X-Executor-Token)
# =========================================================

EXECUTOR_TOKEN = os.getenv("EXECUTOR_TOKEN", "change-me")

def require_executor_token(
    x_executor_token: str = Header(..., alias="X-Executor-Token")
):
    if x_executor_token != EXECUTOR_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid executor token")
    return True


# =========================================================
# Public partner endpoints
# =========================================================

@app.post("/payouts", status_code=201)
def create_payout(
    payload: PayoutCreate,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    # enforce unique (partner_id, partner_tx_id)
    exists = (
        db.query(Payout)
        .filter(
            Payout.partner_id == partner.id,
            Payout.partner_tx_id == payload.partner_tx_id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Duplicate partner_tx_id for this partner")

    payout = Payout(
        partner_id=partner.id,
        partner_tx_id=payload.partner_tx_id,
        amount=payload.amount,
        currency=payload.currency,
        recipient=payload.recipient,
        provider=payload.provider,
        request_payload=payload.request_payload,
    )

    db.add(payout)
    db.flush()  # payout.id available

    # Add to queue
    db.add(PayoutQueue(payout_id=payout.id))

    db.commit()
    db.refresh(payout)

    return {
        "id": str(payout.id),
        "status": payout.status,
        "created_at": payout.created_at,
    }


@app.get("/payouts/{payout_id}")
def get_payout(
    payout_id: PyUUID,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    payout = (
        db.query(Payout)
        .filter(Payout.id == payout_id, Payout.partner_id == partner.id)
        .first()
    )
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    return {
        "id": str(payout.id),
        "partner_tx_id": payout.partner_tx_id,
        "amount": str(payout.amount),
        "currency": payout.currency,
        "recipient": payout.recipient,
        "provider": payout.provider,
        "status": payout.status,
        "request_payload": payout.request_payload,
        "created_at": payout.created_at,
    }


@app.patch("/payouts/{payout_id}/status")
def update_payout_status(
    payout_id: PyUUID,
    body: PayoutStatusUpdate,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    payout = (
        db.query(Payout)
        .filter(Payout.id == payout_id, Payout.partner_id == partner.id)
        .first()
    )
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    payout.status = body.status.value
    db.commit()
    db.refresh(payout)
    return {"id": str(payout.id), "status": payout.status}


@app.get("/payouts/stats")
def payout_stats(
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Payout.status, func.count())
        .filter(Payout.partner_id == partner.id)
        .group_by(Payout.status)
        .all()
    )
    stats = {st: cnt for st, cnt in rows}
    return {"payouts": stats, "total": sum(stats.values())}


@app.get("/queue/stats")
def queue_stats_global(
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    # Global queue view (optional). If you want partner-only, remove this endpoint.
    rows = db.query(PayoutQueue.status, func.count()).group_by(PayoutQueue.status).all()
    stats = {st: cnt for st, cnt in rows}
    return {"queue": stats, "total": sum(stats.values())}


@app.get("/queue/stats/me")
def queue_stats_me(
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PayoutQueue.status, func.count())
        .join(Payout, Payout.id == PayoutQueue.payout_id)
        .filter(Payout.partner_id == partner.id)
        .group_by(PayoutQueue.status)
        .all()
    )
    stats = {st: cnt for st, cnt in rows}
    return {"queue": stats, "total": sum(stats.values())}



@app.post("/admin/reset-stuck-tasks")
def reset_stuck_tasks(db: Session = Depends(get_db)):
    """Reset all IN_PROGRESS tasks back to PENDING"""
   
    
    # Reset queue
    result = db.execute(text("""
        UPDATE payout_queue 
        SET status = 'PENDING', 
            lease_until = NULL,
            worker_id = NULL
        WHERE status = 'IN_PROGRESS'
    """))
    
    reset_count = result.rowcount
    
    # Reset payouts
    if reset_count > 0:
        db.execute(text("""
            UPDATE payouts 
            SET status = 'PENDING'
            WHERE status = 'PROCESSING'
        """))
    
    db.commit()
    
    return {
        "message": f"Reset {reset_count} stuck tasks",
        "reset_count": reset_count
    }

@app.get("/admin/debug/queue")
def debug_queue(db: Session = Depends(get_db)):
    """Debug endpoint to see queue contents"""
    from sqlalchemy import text
    
    queue_items = db.execute(text("""
        SELECT 
            pq.payout_id,
            pq.status as queue_status,
            pq.lease_until,
            pq.worker_id,
            pq.created_at as queue_created,
            p.status as payout_status,
            p.amount,
            p.recipient
        FROM payout_queue pq
        LEFT JOIN payouts p ON p.id = pq.payout_id
        ORDER BY pq.created_at
    """)).mappings().all()
    
    return {"queue": [dict(item) for item in queue_items]}

# =========================================================
# Then continue with your existing routes...
# =========================================================

# =========================================================
# Internal executor endpoints (worker uses these)
# =========================================================

@app.get("/payouts-audit")
def payouts_audit(
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
      SELECT
        p.id,
        p.partner_tx_id,
        p.amount,
        p.recipient,
        p.provider,
        p.status,

        pq.status       AS queue_status,
        pq.worker_id    AS queue_worker_id,
        pq.lease_until,

        pe.executor_id,
        pe.balance_before,
        pe.balance_after,
        pe.ussd_text,
        pe.provider_ref,
        pe.captured_at

      FROM payouts p
      LEFT JOIN payout_queue pq ON pq.payout_id = p.id
      LEFT JOIN payout_evidence pe ON pe.payout_id = p.id
      WHERE p.partner_id = :partner_id
      ORDER BY p.created_at DESC
      LIMIT 100
    """), {"partner_id": partner.id}).mappings().all()

    return {"items": [dict(r) for r in rows]}


@app.get("/stats/summary")
def summary_stats(
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    # Pending in queue (only this partner)
    pending = (
        db.query(func.count())
        .select_from(PayoutQueue)
        .join(Payout, Payout.id == PayoutQueue.payout_id)
        .filter(Payout.partner_id == partner.id, PayoutQueue.status == "PENDING")
        .scalar()
    )

    # In progress in queue (optional)
    in_progress = (
        db.query(func.count())
        .select_from(PayoutQueue)
        .join(Payout, Payout.id == PayoutQueue.payout_id)
        .filter(Payout.partner_id == partner.id, PayoutQueue.status == "IN_PROGRESS")
        .scalar()
    )

    # Failed (business truth) from payouts table
    failing = (
        db.query(func.count())
        .select_from(Payout)
        .filter(Payout.partner_id == partner.id, Payout.status == "FAILED")
        .scalar()
    )

    return {
        "pending": int(pending or 0),
        "in_progress": int(in_progress or 0),
        "failing": int(failing or 0),
        "queue_total": int((pending or 0) + (in_progress or 0)),
    }

@app.post("/internal/executor/claim")
def executor_claim(
    body: ExecutorClaimRequest,
    _auth=Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    """
    Atomically claim jobs from payout_queue.
    Uses SKIP LOCKED so multiple executors can run safely.
    """
    lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)

    claimed = db.execute(text("""
    WITH candidates AS (
      SELECT pq.payout_id
      FROM payout_queue pq
      WHERE
        pq.status = 'PENDING'
        OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
      ORDER BY pq.created_at
      FOR UPDATE SKIP LOCKED
      LIMIT :limit
    )
    UPDATE payout_queue pq
    SET
      status = 'IN_PROGRESS',
      lease_until = :lease_until,
      worker_id = :worker_id
    FROM candidates c
    WHERE pq.payout_id = c.payout_id
    RETURNING pq.payout_id;
    """), {
        "limit": body.batch_size,
        "lease_until": lease_until,
        "worker_id": body.executor_id,
    }).mappings().all()

    if not claimed:
        db.commit()
        return {"jobs": []}

    payout_ids = [r["payout_id"] for r in claimed]

    # Mark business status as PROCESSING (so partner can see it)
    db.execute(text("""
      UPDATE payouts
      SET status='PROCESSING'
      WHERE id = ANY(:ids)
    """), {"ids": payout_ids})

    jobs = db.execute(text("""
      SELECT
        p.id, p.amount, p.currency, p.recipient, p.provider, p.request_payload
      FROM payouts p
      WHERE p.id = ANY(:ids)
      ORDER BY p.created_at
    """), {"ids": payout_ids}).mappings().all()

    db.commit()
    return {"jobs": [dict(j) for j in jobs]}


def decide_status(amount: Decimal, bb: Decimal | None, ba: Decimal | None, ussd_text: str):
    """
    Server decides final status (business truth).
    Returns: (new_status, reason_code)
    """
    t = (ussd_text or "").lower()

    # Somali phrase examples: insufficient balance
    if "kuguma filna" in t or "haraaga" in t:
        return ("FAILED", "INSUFFICIENT_BALANCE")

    # Balance difference check (if we have balances)
    if bb is not None and ba is not None:
        try:
            diff = bb - ba
            if diff >= amount:
                return ("SENT", "BALANCE_DIFF_OK")
        except Exception:
            pass

    # Generic success signals
    if any(k in t for k in ["success", "completed", "approved", "reference", "trx", "txid", "ref"]):
        return ("SENT", "USSD_TEXT_OK")

    return ("FAILED", "AMBIGUOUS")


@app.post("/internal/executor/report")
def executor_report(
    body: ExecutorReport,
    _auth=Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    """
    Worker reports proof. Server:
    - stores proof in payout_evidence
    - decides SENT/FAILED
    - deletes from payout_queue
    """
    payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    q = db.query(PayoutQueue).filter(PayoutQueue.payout_id == payout.id).first()
    if not q:
        raise HTTPException(status_code=409, detail="Payout not in queue (already finalized?)")

    # Upsert evidence (requires payout_evidence table)
    db.execute(text("""
      INSERT INTO payout_evidence (
        payout_id, executor_id, balance_before, balance_after, ussd_text, provider_ref
      )
      VALUES (:pid, :eid, :bb, :ba, :txt, :pref)
      ON CONFLICT (payout_id) DO UPDATE SET
        executor_id = EXCLUDED.executor_id,
        balance_before = EXCLUDED.balance_before,
        balance_after  = EXCLUDED.balance_after,
        ussd_text = EXCLUDED.ussd_text,
        provider_ref = EXCLUDED.provider_ref,
        captured_at = now();
    """), {
        "pid": str(payout.id),
        "eid": body.executor_id,
        "bb": body.balance_before,
        "ba": body.balance_after,
        "txt": body.ussd_text or "",
        "pref": body.provider_ref,
    })

    new_status, reason = decide_status(
        amount=payout.amount,
        bb=body.balance_before,
        ba=body.balance_after,
        ussd_text=body.ussd_text or "",
    )

    payout.status = new_status

    # finalize: remove from queue
    db.execute(text("DELETE FROM payout_queue WHERE payout_id=:pid"), {"pid": str(payout.id)})

    db.commit()
    db.refresh(payout)

    return {"payout_id": str(payout.id), "status": payout.status, "reason": reason}
