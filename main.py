




# main.py - PRODUCTION READY
import os
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text, bindparam
from database import engine
from models import Base
import json
import logging
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID as PyUUID
from typing import Dict, Any

from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from sqlalchemy import func, text, exc
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from middleware import limiter, setup_middleware
from models import Partner, Payout, PayoutQueue
from schemas import PayoutCreate, PayoutStatusUpdate, ExecutorClaimRequest, ExecutorReport
from security import verify_api_key, validate_api_key_format, extract_prefix

# Configure structured logging
logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url=None
)
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# Setup middleware
setup_middleware(app)
app.state.limiter = limiter

# =========================
# Auth
# =========================

EXECUTOR_TOKEN = settings.executor_token

# def require_executor_token(x_executor_token: str = Header(..., alias="X-Executor-Token")):
#     if x_executor_token != EXECUTOR_TOKEN:
#         logger.warning("Invalid executor token attempted")
#         raise HTTPException(status_code=401, detail="Invalid executor token")
#     return True
def require_executor_token(x_executor_token: str | None = Header(None, alias="X-Executor-Token")):
    if not x_executor_token:
        raise HTTPException(status_code=401, detail="Missing X-Executor-Token")
    if x_executor_token != EXECUTOR_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid executor token")
    return True

def get_partner_from_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Partner:
    if not validate_api_key_format(x_api_key):
        logger.warning("Invalid API key format", api_key_prefix=x_api_key[:8])
        raise HTTPException(status_code=401, detail="Invalid API key format")

    prefix = extract_prefix(x_api_key)
    partner = (
        db.query(Partner)
        .filter(Partner.is_active == True, Partner.api_key_prefix == prefix)
        .first()
    )
    if not partner or not verify_api_key(x_api_key, partner.api_key_hash):
        logger.warning("Invalid API key attempt", partner_id=partner.id if partner else None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    
    logger.info("API key validated", partner_id=partner.id)
    return partner

# =========================
# Business status decision
# =========================

def is_plausible_balance(x: Decimal | None) -> bool:
    if x is None:
        return False
    return Decimal("0") <= x <= Decimal(str(settings.max_amount))

def decide_status(amount: Decimal, bb: Decimal | None, ba: Decimal | None, ussd_text: str):
    """
    SAFE BY DEFAULT:
    Mark SENT only with strong evidence.
    """
    t = (ussd_text or "").lower()

    # Insufficient balance signals
    if "kuguma filna" in t or "haraaga" in t or "insufficient" in t:
        return ("FAILED", "INSUFFICIENT_BALANCE")

    # Wrong-menu signals (weather/settings etc.)
    wrong_menu_indicators = ["sunrise", "settings", "°", "weather", "clock", "calendar"]
    if any(indicator in t for indicator in wrong_menu_indicators):
        return ("FAILED", "WRONG_SCREEN")

    # Strong success signals
    strong_success = ["success", "successful", "completed", "reference", "tixraac", 
                     "trx", "txid", "ref:", "lacag", "diray"]
    if any(k in t for k in strong_success):
        return ("SENT", "USSD_STRONG_OK")

    # Balance diff only if balances are plausible
    if is_plausible_balance(bb) and is_plausible_balance(ba):
        diff = bb - ba
        # allow small overhead (fees), but block crazy diffs
        if diff >= amount and diff <= (amount * Decimal("1.25")):
            return ("SENT", "BALANCE_DIFF_OK")

    # Otherwise: ambiguous = FAILED
    return ("FAILED", "AMBIGUOUS")

# =========================
# Health & Monitoring
# =========================

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint for monitoring"""
    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        
        # Check queue health
        queue_stats = db.execute(text("""
            SELECT 
                COUNT(*) as total_queued,
                SUM(CASE WHEN status = 'IN_PROGRESS' AND lease_until < now() THEN 1 ELSE 0 END) as expired_tasks
            FROM payout_queue
        """)).first()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "connected",
            "queue_health": {
                "total_queued": queue_stats[0] or 0,
                "expired_tasks": queue_stats[1] or 0
            }
        }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")

# =========================
# Partner endpoints with DUPLICATE PREVENTION
# =========================

@app.post("/payouts-create", status_code=201)
@limiter.limit("100/minute")
def create_payout(
    request: Request,  # Required for rate limiting
    payload: PayoutCreate,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    """
    Create a payout with robust duplicate prevention.
    Checks multiple conditions before allowing creation.
    """
    # 1. Check if partner_tx_id already exists for this partner (IDEMPOTENCY)
    existing = db.query(Payout).filter(
        Payout.partner_id == partner.id,
        Payout.partner_tx_id == payload.partner_tx_id
    ).first()
    
    if existing:
        logger.info("Duplicate partner_tx_id detected", 
                   partner_id=partner.id, 
                   partner_tx_id=payload.partner_tx_id,
                   existing_status=existing.status)
        
        # Return the existing payout instead of error (idempotent)
        return {
            "id": str(existing.id),
            "status": existing.status,
            "created_at": existing.created_at,
            "duplicate": True,
            "message": "Transaction already exists"
        }
    
    # 2. Validate amount is positive and within limits
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    if payload.amount > settings.max_amount:
        raise HTTPException(status_code=400, 
                          detail=f"Amount exceeds maximum limit of {settings.max_amount}")
    
    # 3. Validate phone number format
    if not payload.recipient.startswith("+"):
        raise HTTPException(status_code=400, detail="Recipient phone must start with +")
    
    # 4. Check for recent duplicate recipient/amount combinations
    # (Prevents accidental double payments)
    recent_duplicate = db.query(Payout).filter(
        Payout.partner_id == partner.id,
        Payout.recipient == payload.recipient,
        Payout.amount == payload.amount,
        Payout.status.in_(["RECEIVED", "PROCESSING", "PENDING"]),
        Payout.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5)
    ).first()
    
    if recent_duplicate:
        logger.warning("Potential duplicate payment detected",
                      partner_id=partner.id,
                      recipient=payload.recipient,
                      amount=payload.amount)
        raise HTTPException(
            status_code=409,
            detail=f"Similar payment to {payload.recipient} for {payload.amount} was recently created. If this is intentional, wait 5 minutes or use a different amount."
        )
    
    # 5. Create the payout
    request_payload_str = json.dumps(payload.request_payload)
    
    payout = Payout(
        partner_id=partner.id,
        partner_tx_id=payload.partner_tx_id,
        amount=payload.amount,
        currency=payload.currency,
        recipient=payload.recipient,
        provider=payload.provider,
        request_payload=request_payload_str,
        status="RECEIVED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(payout)
    db.flush()  # payout.id available

    # 6. Enqueue (one row per payout)
    db.add(PayoutQueue(
        payout_id=payout.id,
        status="PENDING",
        created_at=datetime.now(timezone.utc)
    ))

    try:
        db.commit()
        logger.info("Payout created successfully",
                   partner_id=partner.id,
                   payout_id=str(payout.id),
                   amount=payload.amount,
                   recipient=payload.recipient)
    except exc.IntegrityError as e:
        db.rollback()
        # Check for duplicate partner_tx_id (race condition)
        if "ux_payout_partner_tx" in str(e):
            # Race condition - someone else just created it
            existing = db.query(Payout).filter(
                Payout.partner_id == partner.id,
                Payout.partner_tx_id == payload.partner_tx_id
            ).first()
            
            if existing:
                return {
                    "id": str(existing.id),
                    "status": existing.status,
                    "created_at": existing.created_at,
                    "duplicate": True,
                    "message": "Transaction created by concurrent request"
                }
        logger.error("Database integrity error", error=str(e), partner_id=partner.id)
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        db.rollback()
        logger.error("Payout creation failed", error=str(e), partner_id=partner.id)
        raise HTTPException(status_code=500, detail="Internal server error")

    db.refresh(payout)
    return {
        "id": str(payout.id),
        "status": payout.status,
        "created_at": payout.created_at,
        "duplicate": False
    }

@app.get("/payouts/check-duplicate/{partner_tx_id}")
@limiter.limit("60/minute")
def check_duplicate(
    request: Request,
    partner_tx_id: str,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    """
    Check if a transaction ID already exists before attempting to create.
    Useful for client-side duplicate prevention.
    """
    payout = db.query(Payout).filter(
        Payout.partner_id == partner.id,
        Payout.partner_tx_id == partner_tx_id
    ).first()
    
    if payout:
        return {
            "exists": True,
            "id": str(payout.id),
            "status": payout.status,
            "created_at": payout.created_at
        }
    
    return {"exists": False}

# =========================
# Enhanced Payout Retrieval with History
# =========================

@app.get("/payouts/{payout_id}")
@limiter.limit("60/minute")
def get_payout(
    request: Request,
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

    # Get evidence if available
    evidence = db.execute(text("""
        SELECT executor_id, balance_before, balance_after, ussd_text, provider_ref, captured_at
        FROM payout_evidence
        WHERE payout_id = :payout_id
    """), {"payout_id": str(payout_id)}).first()

    return {
        "id": str(payout.id),
        "partner_tx_id": payout.partner_tx_id,
        "amount": str(payout.amount),
        "currency": payout.currency,
        "recipient": payout.recipient,
        "provider": payout.provider,
        "status": payout.status,
        "request_payload": json.loads(payout.request_payload) if payout.request_payload else None,
        "created_at": payout.created_at,
        "updated_at": payout.updated_at,
        "evidence": {
            "executor_id": evidence[0] if evidence else None,
            "balance_before": str(evidence[1]) if evidence and evidence[1] else None,
            "balance_after": str(evidence[2]) if evidence and evidence[2] else None,
            "ussd_text": evidence[3] if evidence else None,
            "provider_ref": evidence[4] if evidence else None,
            "captured_at": evidence[5] if evidence else None,
        } if evidence else None
    }

# =========================
# Enhanced Statistics with Partner Limits
# =========================

@app.get("/stats/summary")
@limiter.limit("30/minute")
def summary_stats(
    request: Request,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    """
    Enhanced stats with daily limits and performance metrics
    """
    # Get today's total amount sent
    today = datetime.now(timezone.utc).date()
    today_amount = db.execute(text("""
        SELECT COALESCE(SUM(amount), 0)
        FROM payouts
        WHERE partner_id = :partner_id
          AND status = 'SENT'
          AND DATE(created_at) = :today
    """), {"partner_id": partner.id, "today": today}).scalar() or 0
    
    # Get basic stats
    stats_query = text("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'RECEIVED') as received,
            COUNT(*) FILTER (WHERE status = 'PROCESSING') as processing,
            COUNT(*) FILTER (WHERE status = 'SENT') as sent,
            COUNT(*) FILTER (WHERE status = 'FAILED') as failed,
            COUNT(*) FILTER (WHERE status = 'PENDING') as queue_pending,
            COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') as queue_in_progress
        FROM (
            SELECT p.status
            FROM payouts p
            WHERE p.partner_id = :partner_id
            
            UNION ALL
            
            SELECT pq.status
            FROM payout_queue pq
            JOIN payouts p2 ON p2.id = pq.payout_id
            WHERE p2.partner_id = :partner_id
        ) combined
    """)
    
    result = db.execute(stats_query, {"partner_id": partner.id}).first()
    
    return {
        "received": result[0] or 0,
        "processing": result[1] or 0,
        "sent": result[2] or 0,
        "failed": result[3] or 0,
        "queue_pending": result[4] or 0,
        "queue_in_progress": result[5] or 0,
        "daily_sent_amount": float(today_amount),
        "daily_limit": settings.max_amount * 10,  # Example: 10x max single transaction
        "partner_since": partner.created_at.date() if partner.created_at else None
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

# =========================
# Enhanced Admin Endpoints
# =========================
# =========================
# Admin Dashboard (UI + API)
# =========================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """
    Admin UI page (token is entered in the browser and used in JS via header).
    """
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/admin/api/summary")
def admin_summary(
    request: Request,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    """
    Global summary (all partners) for admin view.
    """
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'RECEIVED')   AS received,
            COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
            COUNT(*) FILTER (WHERE status = 'SENT')       AS sent,
            COUNT(*) FILTER (WHERE status = 'FAILED')     AS failed
        FROM payouts
    """)).first()

    qrow = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'PENDING')     AS pending,
            COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress,
            SUM(CASE WHEN status='IN_PROGRESS' AND lease_until < now() THEN 1 ELSE 0 END) AS expired
        FROM payout_queue
    """)).first()

    return {
        "payouts": {
            "received": row[0] or 0,
            "processing": row[1] or 0,
            "sent": row[2] or 0,
            "failed": row[3] or 0,
        },
        "queue": {
            "pending": qrow[0] or 0,
            "in_progress": qrow[1] or 0,
            "expired": qrow[2] or 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/admin/api/payouts")
def admin_list_payouts(
    request: Request,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
    q: str | None = None,              # search text (recipient / partner_tx_id / provider_ref)
    status: str | None = None,         # payout status filter
    limit: int = 50,
    offset: int = 0,
):
    """
    Paginated payouts list with simple filtering.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    where = ["1=1"]
    if status:
        where.append("p.status = :status")
        params["status"] = status

    if q:
        # Search recipient, partner_tx_id, provider_ref (from evidence)
        where.append("""
            (
              p.recipient ILIKE :q
              OR p.partner_tx_id ILIKE :q
              OR EXISTS (
                SELECT 1 FROM payout_evidence e
                WHERE e.payout_id = p.id AND e.provider_ref ILIKE :q
              )
            )
        """)
        params["q"] = f"%{q}%"

    total = db.execute(text(f"""
        SELECT COUNT(*)
        FROM payouts p
        WHERE {" AND ".join(where)}
    """), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT
            p.id,
            p.partner_id,
            p.partner_tx_id,
            p.amount,
            p.currency,
            p.recipient,
            p.provider,
            p.status,
            p.created_at,
            p.updated_at,
            pq.status AS queue_status,
            pq.worker_id,
            pq.lease_until
        FROM payouts p
        LEFT JOIN payout_queue pq ON pq.payout_id = p.id
        WHERE {" AND ".join(where)}
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@app.get("/admin/api/payouts/{payout_id}")
def admin_payout_details(
    request: Request,
    payout_id: str,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    """
    One payout + evidence + queue row.
    """
    payout = db.execute(text("""
        SELECT
            p.id, p.partner_id, p.partner_tx_id, p.amount, p.currency,
            p.recipient, p.provider, p.status, p.request_payload,
            p.created_at, p.updated_at,
            pq.status AS queue_status, pq.worker_id, pq.lease_until, pq.created_at AS queue_created
        FROM payouts p
        LEFT JOIN payout_queue pq ON pq.payout_id = p.id
        WHERE p.id = :id
    """), {"id": payout_id}).mappings().first()

    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    evidence = db.execute(text("""
        SELECT
            executor_id, balance_before, balance_after, ussd_text, provider_ref, captured_at
        FROM payout_evidence
        WHERE payout_id = :id
        ORDER BY captured_at DESC
        LIMIT 1
    """), {"id": payout_id}).mappings().first()

    out = dict(payout)
    out["request_payload"] = json.loads(out["request_payload"]) if out.get("request_payload") else None
    out["evidence"] = dict(evidence) if evidence else None
    return out


@app.get("/admin/api/queue")
def admin_queue(
    request: Request,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """
    Queue snapshot (most recent first).
    """
    limit = max(1, min(limit, 500))
    rows = db.execute(text("""
        SELECT
            pq.payout_id,
            pq.status as queue_status,
            pq.lease_until,
            pq.worker_id,
            pq.created_at as queue_created,
            p.status as payout_status,
            p.amount,
            p.currency,
            p.recipient,
            p.partner_tx_id
        FROM payout_queue pq
        LEFT JOIN payouts p ON p.id = pq.payout_id
        ORDER BY pq.created_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {"items": [dict(r) for r in rows]}

@app.post("/admin/reset-stuck-tasks")
@limiter.limit("10/minute")
def reset_stuck_tasks(
    request: Request,
    hours_old: int = 1,  # Only reset tasks older than X hours
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    """
    Safer reset: Only reset tasks that have been stuck for specified hours.
    Logs which tasks were reset for auditing.
    """
    # First, get the stuck tasks for logging
    stuck_tasks = db.execute(text("""
        SELECT pq.payout_id, pq.worker_id, pq.lease_until, p.recipient, p.amount
        FROM payout_queue pq
        JOIN payouts p ON p.id = pq.payout_id
        WHERE pq.status = 'IN_PROGRESS'
          AND pq.lease_until < now() - interval :hours_old hour
        ORDER BY pq.lease_until
    """), {"hours_old": hours_old}).mappings().all()
    
    if not stuck_tasks:
        return {"message": "No stuck tasks found", "reset_count": 0}
    
    # Reset them
    result = db.execute(text("""
        UPDATE payout_queue
        SET status = 'PENDING',
            lease_until = NULL,
            worker_id = NULL
        WHERE status = 'IN_PROGRESS'
          AND lease_until < now() - interval :hours_old hour
        RETURNING payout_id
    """), {"hours_old": hours_old})
    
    reset_ids = [str(row[0]) for row in result]
    db.commit()
    
    # Log the reset for auditing
    logger.warning("Stuck tasks reset by admin",
                  count=len(reset_ids),
                  hours_old=hours_old,
                  payout_ids=reset_ids[:10])  # Log first 10 IDs
    
    return {
        "message": f"Reset {len(reset_ids)} stuck tasks older than {hours_old} hour(s)",
        "reset_count": len(reset_ids),
        "reset_ids": reset_ids[:50]  # Return first 50 IDs
    }

# =========================
# Enhanced Executor Endpoints
# =========================

# @app.post("/internal/executor/claim")
# @limiter.limit("30/minute")
# def executor_claim(
#     request: Request,
#     body: ExecutorClaimRequest,
#     _auth = Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     """
#     Enhanced claim with better logging and validation
#     """
#     logger.info("Executor claim attempt",
#                executor_id=body.executor_id,
#                batch_size=body.batch_size,
#                lease_secs=body.lease_secs)
    
#     # Validate lease time
#     if body.lease_secs > 600:  # Max 10 minutes
#         raise HTTPException(status_code=400, detail="Lease time too long (max 600 seconds)")
    
#     if body.batch_size > 20:  # Max 20 tasks per claim
#         raise HTTPException(status_code=400, detail="Batch size too large (max 20)")
    
#     lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)
    
#     # Atomic claim
#     claimed = db.execute(text("""
#         WITH candidates AS (
#             SELECT pq.payout_id
#             FROM payout_queue pq
#             JOIN payouts p ON p.id = pq.payout_id
#             WHERE (
#                 pq.status = 'PENDING'
#                 OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
#             )
#             AND p.status = 'RECEIVED'  # Only claim RECEIVED payouts
#             ORDER BY pq.created_at
#             FOR UPDATE SKIP LOCKED
#             LIMIT :limit
#         )
#         UPDATE payout_queue pq
#         SET
#             status = 'IN_PROGRESS',
#             lease_until = :lease_until,
#             worker_id = :worker_id
#         FROM candidates c
#         WHERE pq.payout_id = c.payout_id
#         RETURNING pq.payout_id;
#     """), {
#         "limit": body.batch_size,
#         "lease_until": lease_until,
#         "worker_id": body.executor_id,
#     }).mappings().all()

#     payout_ids = [str(r["payout_id"]) for r in claimed]

#     if not payout_ids:
#         db.commit()
#         return {"jobs": [], "message": "No jobs available"}

#     # Update payout status
#     db.execute(text("""
#         UPDATE payouts
#         SET status = 'PROCESSING',
#             updated_at = now()
#         WHERE id = ANY(:ids::uuid[])
#           AND status = 'RECEIVED'
#     """), {"ids": payout_ids})

#     # Get job details
#     jobs = db.execute(text("""
#         SELECT
#             p.id,
#             p.amount,
#             p.currency,
#             p.recipient,
#             p.provider,
#             p.request_payload
#         FROM payouts p
#         WHERE p.id = ANY(:ids::uuid[])
#         ORDER BY p.created_at
#     """), {"ids": payout_ids}).mappings().all()
    
#     db.commit()
    
#     logger.info("Executor claimed jobs",
#                executor_id=body.executor_id,
#                job_count=len(jobs),
#                payout_ids=payout_ids)
    
#     return {
#         "jobs": [dict(j) for j in jobs],
#         "lease_until": lease_until.isoformat(),
#         "count": len(jobs)
#     }
@app.post("/internal/executor/report")
@limiter.limit("60/minute")
def executor_report(
    request: Request,
    body: ExecutorReport,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    logger.info(
        "Executor report received",
        payout_id=str(body.payout_id),
        executor_id=body.executor_id,
    )

    payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    # store / upsert evidence
    db.execute(text("""
        INSERT INTO payout_evidence (
            payout_id,
            executor_id,
            balance_before,
            balance_after,
            ussd_text,
            provider_ref,
            captured_at
        )
        VALUES (
            :payout_id,
            :executor_id,
            :bb,
            :ba,
            :ussd,
            :ref,
            now()
        )
        ON CONFLICT (payout_id)
        DO UPDATE SET
            executor_id = EXCLUDED.executor_id,
            balance_before = EXCLUDED.balance_before,
            balance_after = EXCLUDED.balance_after,
            ussd_text = EXCLUDED.ussd_text,
            provider_ref = EXCLUDED.provider_ref,
            captured_at = now()
    """), {
        "payout_id": str(body.payout_id),
        "executor_id": body.executor_id,
        "bb": body.balance_before,
        "ba": body.balance_after,
        "ussd": body.ussd_text,
        "ref": body.provider_ref,
    })

    # decide final status
    status, reason = decide_status(
        payout.amount,
        body.balance_before,
        body.balance_after,
        body.ussd_text or "",
    )

    payout.status = status
    payout.updated_at = datetime.now(timezone.utc)

    # remove from queue when finished
    if status in ("SENT", "FAILED"):
        db.execute(
            text("DELETE FROM payout_queue WHERE payout_id = :id"),
            {"id": str(body.payout_id)}
        )

    db.commit()

    logger.info(
        "Executor report processed",
        payout_id=str(body.payout_id),
        final_status=status,
        reason=reason,
    )

    return {
        "ok": True,
        "status": status,
        "reason": reason
    }

@app.post("/internal/executor/claim")
@limiter.limit("30/minute")
def executor_claim(
    request: Request,
    body: ExecutorClaimRequest,
    _auth = Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    logger.info(
        "Executor claim attempt",
        executor_id=body.executor_id,
        batch_size=body.batch_size,
        lease_secs=body.lease_secs
    )

    # Validate lease time
    if body.lease_secs > 600:
        raise HTTPException(status_code=400, detail="Lease time too long (max 600 seconds)")

    if body.batch_size > 20:
        raise HTTPException(status_code=400, detail="Batch size too large (max 20)")

    lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)

    # 1) Atomic claim
    claimed = db.execute(text("""
        WITH candidates AS (
            SELECT pq.payout_id
            FROM payout_queue pq
            JOIN payouts p ON p.id = pq.payout_id
            WHERE (
                pq.status = 'PENDING'
                OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
            )
            AND p.status = 'RECEIVED'  -- Only claim RECEIVED payouts
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

    payout_ids = [r["payout_id"] for r in claimed]  # keep UUID type if returned as UUID

    if not payout_ids:
        db.commit()
        return {"jobs": [], "message": "No jobs available"}

    # 2) Update payout status (use expanding bind for IN (...))
    upd = text("""
        UPDATE payouts
        SET status = 'PROCESSING',
            updated_at = now()
        WHERE id IN :ids
          AND status = 'RECEIVED'
    """).bindparams(bindparam("ids", expanding=True))

    db.execute(upd, {"ids": payout_ids})

    # 3) Get job details
    sel = text("""
        SELECT
            p.id,
            p.amount,
            p.currency,
            p.recipient,
            p.provider,
            p.request_payload
        FROM payouts p
        WHERE p.id IN :ids
        ORDER BY p.created_at
    """).bindparams(bindparam("ids", expanding=True))

    jobs = db.execute(sel, {"ids": payout_ids}).mappings().all()

    db.commit()

    logger.info(
        "Executor claimed jobs",
        executor_id=body.executor_id,
        job_count=len(jobs),
        payout_ids=[str(x) for x in payout_ids]
    )

    return {
        "jobs": [dict(j) for j in jobs],
        "lease_until": lease_until.isoformat(),
        "count": len(jobs),
    }

# Keep the rest of your endpoints as they are (executor_report, etc.)
# They're already production-ready

if __name__ == "__main__":
    import uvicorn
    
    # Production settings
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=int(os.getenv("WORKERS", 4)),  # Multiple workers for production
        log_level="info",
        access_log=True
    )