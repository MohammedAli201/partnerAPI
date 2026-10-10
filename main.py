import os
import json
import re
import logging
import structlog
import asyncio
from contextlib import asynccontextmanager
from threading import Event, Thread
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID as PyUUID
from typing import Dict, Any

from pydantic import BaseModel
from fastapi import FastAPI, Depends, Header, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text, bindparam, exc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import get_settings
from database import engine, get_db, SessionLocal
from payout_webhooks import callback_url, enqueue_event, payout_channel, run_worker
from middleware import limiter, setup_middleware

# SQLAlchemy models
from models import Base, Partner, Payout, PayoutQueue, User  # + ensure you added PayoutReservation + partner balance columns in models/db
# Pydantic schemas you already have
from schemas import PayoutCreate, PayoutStatusUpdate, ExecutorClaimRequest, ExecutorReport

# Partner API-key auth helpers (already in your project)
from security import verify_api_key, validate_api_key_format, extract_prefix, generate_api_key

# UI session auth + role
from auth_session import require_role, hash_password, get_session

# Login router (/login, /logout)
from routes_ui_auth import router as ui_auth_router


# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger(__name__)
settings = get_settings()
SKIP_DB_BOOTSTRAP = os.getenv("SKIP_DB_BOOTSTRAP", "").lower() in {"1", "true", "yes"}

# Fee charged to partner per payout (fixed)
# Put this in config/settings, e.g. PARTNER_FEE=0.60
PARTNER_FEE = Decimal(str(getattr(settings, "partner_fee", "0.60")))
PAYOUT_STATUS_WEBHOOK_URL = None  # Global/per-payout callback destinations are retired

UUID_V4_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)
PARTNER_TX_FULL_RE = re.compile(
    r"^pm_(?P<date>\d{6})-(?P<code>[A-Za-z0-9]{3,32})_(?P<tx_uuid>[0-9a-fA-F-]{36})$"
)
PARTNER_TX_LEGACY_RE = re.compile(
    r"^pm_(?P<date>\d{6})-(?P<code>[A-Za-z0-9]{3,32})_(?P<tx_short>[0-9a-fA-F]{8})$"
)
RUNTIME_GUARD_STATEMENTS = (
    """
    ALTER TABLE partners
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_payouts_partner_partner_tx_id
    ON payouts (partner_id, partner_tx_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_payouts_partner_status_created_at
    ON payouts (partner_id, status, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_payouts_partner_recipient_amount_created_at
    ON payouts (partner_id, recipient, amount, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_payout_queue_status_lease_created_at
    ON payout_queue (status, lease_until, created_at)
    """,
)


# -------------------------
# App
# -------------------------
@asynccontextmanager
async def lifespan(app):
    with engine.connect() as connection:
        connection.execute(text("SELECT ledger_enabled FROM partners LIMIT 1"))
        connection.execute(text("SELECT 1 FROM ledger_journals LIMIT 1"))
        connection.execute(text("SELECT execution_closed_at FROM payout_attempts LIMIT 1"))
        connection.execute(text("SELECT 1 FROM execution_containment_reviews LIMIT 1"))
        connection.execute(text("SELECT 1 FROM payout_fee_snapshots LIMIT 1"))
        connection.execute(text("SELECT 1 FROM fee_financial_events LIMIT 1"))
        connection.execute(text("SELECT 'financial_fee_guard()'::regprocedure"))
    if settings.environment=="production" and len(settings.api_key_verifier_secret.get_secret_value())<32:
        raise RuntimeError("API_KEY_VERIFIER_SECRET of at least 32 characters is required in production")
    if settings.environment=='production' and os.getenv('PAYOUT_SIMULATOR_ENABLED')=='true':
        raise RuntimeError('Simulated financial confirmations are forbidden in production')
    stop=Event()
    worker=None
    if settings.embedded_payment_workers:
        worker=Thread(target=run_worker,args=(stop,SessionLocal),daemon=True)
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            await asyncio.to_thread(worker.join,6)


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

@app.exception_handler(SQLAlchemyError)
async def database_failure(request: Request,error: SQLAlchemyError):
    from fastapi.responses import JSONResponse
    logger.error('Database operation failed',failure_type=type(error).__name__)
    return JSONResponse({'detail':'Database operation unavailable; retry with the same reference'},status_code=503)


def ensure_runtime_db_guards():
    # Schema changes are performed by Alembic, never API workers.
    return



if SKIP_DB_BOOTSTRAP:
    logger.warning("Skipping DB bootstrap because SKIP_DB_BOOTSTRAP is enabled")
else:
    if settings.environment != "production":
        logger.info("Use alembic upgrade head before startup; runtime DDL is disabled")
    else:
        logger.warning("Skipping create_all in production; use migrations for schema changes")

    ensure_runtime_db_guards()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request, lang: str = 'en'):
    from public_site.routes import render
    return render(request, '/', lang)


# middleware
setup_middleware(app)
app.state.limiter = limiter
from browser_security import install as install_browser_security
from quotas import install as install_quotas
install_browser_security(app,settings,SessionLocal)
install_quotas(app,SessionLocal)

# add login router
app.include_router(ui_auth_router)


# -------------------------
# Executor token (internal)
# -------------------------
EXECUTOR_TOKEN = settings.executor_token


def require_executor_token(x_executor_token: str | None=Header(None,alias="X-Executor-Token")):
    raise HTTPException(410,"Legacy shared-token execution retired; use /internal/workers/v2 with an independent worker credential")



def require_admin_or_executor(request: Request,x_executor_token: str | None=Header(None,alias="X-Executor-Token")):
    return require_role("admin")(request)



# -------------------------
# Partner API key auth (external partner integration)
# -------------------------
def get_partner_from_api_key(request: Request,x_api_key: str=Header(...,alias="X-API-Key"),db: Session=Depends(get_db)) -> Partner:
    if not validate_api_key_format(x_api_key):
        raise HTTPException(401,"Invalid API credential")
    prefix=extract_prefix(x_api_key)
    credential=db.execute(text("SELECT * FROM api_credentials WHERE prefix=:prefix AND revoked_at IS NULL"),{"prefix":prefix}).mappings().first()
    if credential:
        partner=db.query(Partner).filter(Partner.id==credential["partner_id"],Partner.is_active==True).first()
        verifier=credential["verifier"]
    else:
        partner=db.query(Partner).filter(Partner.api_key_prefix==prefix,Partner.is_active==True).first()
        verifier=partner.api_key_hash if partner else ""
    if not partner or not verify_api_key(x_api_key,verifier):
        db.rollback()
        raise HTTPException(401,"Invalid API credential")
    from quotas import partner_quota
    partner_quota(db,partner.id,request.url.path)
    db.commit()
    return partner



def extract_payload_transaction_id(payload: Dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None

    def pick_uuid(value: Any) -> str | None:
        if isinstance(value, str):
            candidate = value.strip()
            if UUID_V4_RE.fullmatch(candidate):
                return candidate.lower()
        return None

    # 1) direct keys on root payload
    for key in ("TransactionId", "transactionId", "transaction_id"):
        tx = pick_uuid(payload.get(key))
        if tx:
            return tx

    # 2) common nested object, e.g. {"data": {"TransactionId": "..."}}
    nested_data = payload.get("data")
    if isinstance(nested_data, dict):
        for key in ("TransactionId", "transactionId", "transaction_id"):
            tx = pick_uuid(nested_data.get(key))
            if tx:
                return tx

    # 3) shallow scan one level for any transaction id key
    for _, value in payload.items():
        if isinstance(value, dict):
            for key in ("TransactionId", "transactionId", "transaction_id"):
                tx = pick_uuid(value.get(key))
                if tx:
                    return tx
    return None


def normalize_partner_tx_id(raw_partner_tx_id: str, request_payload: Dict[str, Any]) -> str:
    partner_tx_id = (raw_partner_tx_id or "").strip()
    if not partner_tx_id:
        raise HTTPException(status_code=400, detail="partner_tx_id is required")

    payload_tx_id = extract_payload_transaction_id(request_payload)

    m_full = PARTNER_TX_FULL_RE.fullmatch(partner_tx_id)
    if m_full:
        tx_uuid = m_full.group("tx_uuid").lower()
        if not UUID_V4_RE.fullmatch(tx_uuid):
            raise HTTPException(status_code=400, detail="partner_tx_id must include a full GUID")
        if payload_tx_id and payload_tx_id != tx_uuid:
            raise HTTPException(status_code=400, detail="partner_tx_id and request_payload.TransactionId do not match")
        return f"pm_{m_full.group('date')}-{m_full.group('code')}_{tx_uuid}"

    m_legacy = PARTNER_TX_LEGACY_RE.fullmatch(partner_tx_id)
    if m_legacy:
        if not payload_tx_id:
            raise HTTPException(
                status_code=400,
                detail="Legacy truncated partner_tx_id detected. Send full request_payload.TransactionId to upgrade.",
            )
        tx_short = m_legacy.group("tx_short").lower()
        if not payload_tx_id.startswith(tx_short):
            raise HTTPException(status_code=400, detail="Legacy partner_tx_id does not match request_payload.TransactionId")
        return f"pm_{m_legacy.group('date')}-{m_legacy.group('code')}_{payload_tx_id}"

    if UUID_V4_RE.fullmatch(partner_tx_id):
        full_tx_id = partner_tx_id.lower()
        if payload_tx_id and payload_tx_id != full_tx_id:
            raise HTTPException(status_code=400, detail="partner_tx_id and request_payload.TransactionId do not match")
        date_code = datetime.now(timezone.utc).strftime("%y%m%d")
        partner_code = full_tx_id.replace("-", "")[:6].upper()
        return full_tx_id  # Stable across dates; aliases preserve earlier formatted references

    raise HTTPException(
        status_code=400,
        detail="partner_tx_id must be pm_[DATE]-[CODE]_[FULL_GUID] or a full GUID.",
    )


def serialize_existing_payout(existing: Payout) -> Dict[str, Any]:
    return {
        "id": str(existing.id),
        "partner_tx_id": existing.partner_tx_id,
        "status": existing.status,
        "created_at": existing.created_at,
        "duplicate": True,
        "message": "Transaction already exists",
    }


# -------------------------
# Business status decision
# -------------------------
def is_plausible_balance(x: Decimal | None) -> bool:
    if x is None:
        return False
    return Decimal("0") <= x <= Decimal(str(settings.max_amount))


def decide_status(amount: Decimal,bb: Decimal | None,ba: Decimal | None,ussd_text: str):
    return ("UNKNOWN","UNVERIFIED_USSD_EVIDENCE")



# -------------------------
# Home + Health
# -------------------------
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
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
                "total_queued": int(queue_stats[0] or 0),
                "expired_tasks": int(queue_stats[1] or 0)
            }
        }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")


# ============================================================
# Partner API endpoints (auth = X-API-Key)
# ============================================================
@app.post("/payouts-create", status_code=201)
def create_payout(request: Request,payload: PayoutCreate,partner: Partner=Depends(get_partner_from_api_key),db: Session=Depends(get_db),idempotency_key: str | None=Header(None,alias="Idempotency-Key")):
    from backend_core import admission
    if payload.amount>settings.max_amount:
        raise HTTPException(422,"Amount exceeds configured limit")
    reference=normalize_partner_tx_id(payload.partner_tx_id,payload.request_payload)
    try:
        response=admission(db,partner.id,payload,reference,idempotency_key if isinstance(idempotency_key,str) else None,PARTNER_FEE)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise



@app.get("/payouts/{payout_id}")
def get_payout(
    request: Request,
    payout_id: PyUUID,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    payout = db.query(Payout).filter(Payout.id == payout_id, Payout.partner_id == partner.id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    evidence = db.execute(text("""
        SELECT executor_id, balance_before, balance_after, ussd_text, provider_ref, captured_at
        FROM payout_evidence
        WHERE payout_id = :payout_id
    """), {"payout_id": str(payout_id)}).first()

    res = db.execute(text("""
        SELECT amount, fee, total, status
        FROM payout_reservations
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
        "reservation": {
            "amount": str(res[0]),
            "fee": str(res[1]),
            "total": str(res[2]),
            "status": res[3],
        } if res else None,
        "evidence": {
            "executor_id": evidence[0] if evidence else None,
            "balance_before": str(evidence[1]) if evidence and evidence[1] is not None else None,
            "balance_after": str(evidence[2]) if evidence and evidence[2] is not None else None,
            "ussd_text": evidence[3] if evidence else None,
            "provider_ref": evidence[4] if evidence else None,
            "captured_at": evidence[5] if evidence else None,
        } if evidence else None
    }


@app.get("/stats/summary")
def summary_stats(
    request: Request,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()

    today_amount = db.execute(text("""
        SELECT COALESCE(SUM(amount), 0)
        FROM payouts
        WHERE partner_id = :partner_id
          AND status = 'SENT'
          AND DATE(created_at) = :today
    """), {"partner_id": partner.id, "today": today}).scalar() or 0

    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE p.status = 'RECEIVED')   as received,
            COUNT(*) FILTER (WHERE p.status = 'PROCESSING') as processing,
            COUNT(*) FILTER (WHERE p.status = 'SENT')       as sent,
            COUNT(*) FILTER (WHERE p.status = 'FAILED')     as failed
        FROM payouts p
        WHERE p.partner_id = :partner_id
    """), {"partner_id": partner.id}).first()

    bal = db.execute(text("""
        SELECT balance_available, balance_reserved
        FROM partners
        WHERE id = :partner_id
    """), {"partner_id": partner.id}).first()

    return {
        "received": int(result[0] or 0),
        "processing": int(result[1] or 0),
        "sent": int(result[2] or 0),
        "failed": int(result[3] or 0),
        "daily_sent_amount": float(today_amount),
        "partner_since": partner.created_at.date() if partner.created_at else None,
        "balances": {
            "available": str(bal[0] or 0),
            "reserved": str(bal[1] or 0),
            "total": str((bal[0] or 0) + (bal[1] or 0)),
        }
    }


# ============================================================
# Admin UI pages (auth = session role)
# ============================================================
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, _sess=Depends(require_role("admin"))):
    return templates.TemplateResponse(request=request, name="admin.html", context={"request": request})


@app.get("/partner", response_class=HTMLResponse)
def partner_dashboard(request: Request, _sess=Depends(require_role("partner"))):
    return templates.TemplateResponse(request=request, name="partner.html", context={"request": request})


# ============================================================
# Admin UI APIs (auth = session role admin)
# ============================================================
@app.get("/admin/api/summary")
def admin_summary(
    request: Request,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'RECEIVED')   AS received,
            COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
            COUNT(*) FILTER (WHERE status = 'SENT')       AS sent,
            COUNT(*) FILTER (WHERE status = 'FAILED')     AS failed,
            COUNT(*) FILTER (WHERE status = 'UNKNOWN')    AS unknown,
            COUNT(*) FILTER (WHERE status = 'CANCELLED')  AS cancelled,
            COUNT(*) FILTER (WHERE status = 'REJECTED')   AS rejected
        FROM payouts
    """)).first()

    qrow = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'PENDING')     AS pending,
            COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress,
            SUM(CASE WHEN status='IN_PROGRESS' AND lease_until < now() THEN 1 ELSE 0 END) AS expired,
            COUNT(*) FILTER (WHERE status = 'HELD') AS held
        FROM payout_queue
    """)).first()

    return {
        "payouts": {
            "received": int(row[0] or 0),
            "processing": int(row[1] or 0),
            "sent": int(row[2] or 0),
            "failed": int(row[3] or 0),
            "unknown": int(row[4] or 0),
            "cancelled": int(row[5] or 0),
            "rejected": int(row[6] or 0),
        },
        "queue": {
            "pending": int(qrow[0] or 0),
            "in_progress": int(qrow[1] or 0),
            "expired": int(qrow[2] or 0),
            "held": int(qrow[3] or 0),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/admin/api/payouts")
def admin_list_payouts(
    request: Request,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    q: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    where = ["1=1"]

    if status:
        where.append("p.status = :status")
        params["status"] = status

    if q:
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
        ORDER BY p.created_at DESC,p.id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {"total": int(total), "limit": limit, "offset": offset,
            "items": [{**dict(r), "amount": str(r["amount"])} for r in rows]}


def queue_payout_status_webhook(db, payout, final_status, event_time):
    try:
        return enqueue_event(db, payout, final_status, event_time, PAYOUT_STATUS_WEBHOOK_URL)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def settle_payout_reservation(db: Session,payout_id: str,final_status: str):
    raise HTTPException(409,"Settlement requires verified execution evidence and atomic ledger posting")



@app.patch("/admin/api/payouts/{payout_id}/status")
def admin_update_payout_status(request: Request,payout_id: PyUUID,body: PayoutStatusUpdate,_auth=Depends(require_role("admin")),db: Session=Depends(get_db)):
    raise HTTPException(409,"Direct financial status changes retired; use verified worker results or independent reconciliation")



@app.get("/admin/api/queue")
def admin_queue(
    request: Request,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = 100,
):
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
        ORDER BY pq.created_at DESC,pq.payout_id DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {"items": [{**dict(r), "amount": str(r["amount"]) if r["amount"] is not None else None} for r in rows]}


@app.post("/admin/reset-stuck-tasks")
def reset_stuck_tasks(request: Request,hours_old: int=1,_auth=Depends(require_role("admin")),db: Session=Depends(get_db)):
    from payment_worker import reap
    try:
        count=reap(db)
        db.commit()
        return {"processed_count":count,"message":"Only provably unarmed claims recover; armed/legacy work stays held"}
    except Exception:
        db.rollback()
        raise



# -------------------------
# Admin: Partner deposit/top-up (prepaid float)
# -------------------------
class PartnerDeposit(BaseModel):
    partner_id: int | None = None
    amount: Decimal
    reference: str | None = None
    note: str | None = None


# ============================================================
# Admin: List all partners
# ============================================================
@app.get("/admin/api/partners")
def admin_list_partners(
    request: Request,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    total = db.execute(text("""
        SELECT COUNT(*) FROM partners
    """)).scalar() or 0

    rows = db.execute(text("""
        SELECT
            id,
            name,
            is_active,
            api_key_prefix,
            created_at,
            balance_available,
            balance_reserved
        FROM partners
        ORDER BY id
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()

    items = []
    for r in rows:
        available = r["balance_available"] or 0
        reserved = r["balance_reserved"] or 0

        items.append({
            "partner_id": r["id"],
            "name": r["name"],
            "is_active": r["is_active"],
            "api_key_prefix": r["api_key_prefix"],  # safe to show prefix only
            "created_at": r["created_at"],
            "balances": {
                "available": str(available),
                "reserved": str(reserved),
                "total": str(available + reserved),
            }
        })

    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": items,
    }



# ============================================================
# Admin Funds Management APIs
# ============================================================

# Pydantic models for fund management
class FundAdjustment(BaseModel):
    partner_id: int
    amount: Decimal
    adjustment_type: str  # 'add', 'subtract', 'set'
    balance_type: str    # 'available', 'reserved', 'both'
    reason: str

# New endpoint to get partners with pagination and filtering
@app.get("/admin/api/funds/partners")
def admin_get_partners_for_funds(
    request: Request,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, le=2000000),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=160),
    status: str | None = None,
    sort: str = "balance_desc",
    active_only: bool = False,
    earnings_period: str = 'month',
    earnings_activity: str = 'live',
    earnings_currency: str = 'USD',
):
    page = max(1, page)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    
    params = {"limit": limit, "offset": offset}
    where_clauses = []
    
    if active_only or status == "active":
        where_clauses.append("is_active = TRUE")
    elif status == "inactive":
        where_clauses.append("is_active = FALSE")
    
    if search:
        where_clauses.append("(name ILIKE :search OR CAST(id AS TEXT) LIKE :search)")
        params["search"] = f"%{search}%"
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Sorting
    order_by = {
        "balance_desc": "balance_available DESC",
        "balance_asc": "balance_available ASC",
        "name_asc": "name ASC",
        "name_desc": "name DESC",
        "id_desc": "id DESC",
        "id_asc": "id ASC",
    }.get(sort, "balance_available DESC")
    
    # Get total count
    count_query = text(f"""
        SELECT COUNT(*) FROM partners WHERE {where_sql}
    """)
    total = db.execute(count_query, params).scalar() or 0
    
    # Get paginated partners
    query = text(f"""
        SELECT 
            id, name, is_active, 
            balance_available, balance_reserved,funding_currency,ledger_enabled,
            created_at, updated_at
        FROM partners 
        WHERE {where_sql}
        ORDER BY {order_by},id
        LIMIT :limit OFFSET :offset
    """)
    
    partners = db.execute(query, params).mappings().all()
    from earnings import period, money
    if earnings_activity not in ('live','simulation','unclassified') or earnings_currency not in ('USD','EUR','GBP'):
        raise HTTPException(422,'Invalid earnings activity or currency')
    reporting = period(earnings_period)
    earnings_by_partner = {}
    ids = [p['id'] for p in partners]
    if ids:
        earnings_by_partner = dict(db.execute(text('''SELECT partner_id,
          sum(CASE WHEN event_type='PAYOUT' THEN amount_minor ELSE -amount_minor END)
          FROM fee_financial_events WHERE partner_id=ANY(:ids) AND currency=:currency AND activity=:activity
          AND posted_at>=:start AND posted_at<:end GROUP BY partner_id'''),
          dict(ids=ids,currency=earnings_currency,activity=earnings_activity,start=reporting['start'],end=reporting['end'])).all())
    partners = [{**p,'balance_available':str(p['balance_available'] or 0),'balance_reserved':str(p['balance_reserved'] or 0),
                 'balance_total':str((p['balance_available'] or 0)+(p['balance_reserved'] or 0)),
                 'earned_fees':money(earnings_by_partner.get(p['id'],0)), 'earnings_currency':earnings_currency} for p in partners]
    
    return {
        "partners": list(partners),
        "earnings_period": {k:reporting[k] for k in ('start_date','end_date','timezone')},
        "total": total,
        "page": page,
        "total_pages": (total + limit - 1) // limit,
        "limit": limit,
    }

# Enhanced deposit endpoint with audit trail
@app.post("/admin/api/funds/deposit")
def admin_deposit_funds(request: Request,body: PartnerDeposit,_auth=Depends(require_role("admin")),db: Session=Depends(get_db)):
    from backend_core import deposit
    if body.partner_id is None:
        raise HTTPException(422,"partner_id required")
    try:
        response=deposit(db,body.partner_id,body.amount,body.reference,body.note or body.reference,_auth["uid"])
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


# New: Adjust balance (add, subtract, or set)
@app.post("/admin/api/funds/adjust")
def admin_adjust_funds(request: Request,body: FundAdjustment,_auth=Depends(require_role("admin")),db: Session=Depends(get_db)):
    raise HTTPException(409,"Direct balance edits retired; use independently approved correcting journals")


# Get transaction history for a partner
@app.get("/admin/api/funds/history/{partner_id}")
def admin_get_funds_history(
    request: Request,
    partner_id: int,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    # Check if partner exists
    partner = db.execute(
        text("SELECT id, name, funding_currency FROM partners WHERE id = :partner_id"),
        {"partner_id": partner_id}
    ).first()
    
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    history = db.execute(text("""SELECT id,type,amount,previous_balance,new_balance,
        reference,admin_user,created_at,adjustment_type,notes,ledger_journal_id
        FROM balance_transactions WHERE partner_id=:partner_id
        ORDER BY created_at DESC,id DESC LIMIT :limit"""),
        {"partner_id": partner_id, "limit": limit}).mappings().all()
    return {"partner_id": partner_id, "partner_name": partner[1], "funding_currency": partner[2],
            "history": [{**dict(row), **{key: str(row[key]) if row[key] is not None else None
                        for key in ("amount", "previous_balance", "new_balance")}} for row in history]}

# Create balance_transactions table if it doesn't exist

@app.get("/admin/funds", response_class=HTMLResponse)
def admin_funds_page(
    request: Request,
    _auth=Depends(require_role("admin")),
):
    return templates.TemplateResponse(request=request, name="admin_funds.html", context={"request": request})

@app.post("/admin/partner/{partner_id}/deposit")
def admin_partner_deposit(request: Request,partner_id: int,body: PartnerDeposit,_auth=Depends(require_role("admin")),db: Session=Depends(get_db)):
    if body.partner_id is not None and body.partner_id!=partner_id:
        raise HTTPException(409,"Funding target mismatch")
    return admin_deposit_funds(request,body.model_copy(update={"partner_id":partner_id}),_auth,db)



# ============================================================
# Partner UI APIs (auth = session role partner)
# ============================================================
def get_current_user(sess: dict, db: Session) -> User:
    u = db.query(User).filter(User.id == sess["uid"], User.is_active == True).first()
    if not u:
        raise HTTPException(status_code=401, detail="User not found")
    return u


@app.get("/partner/api/summary")
def partner_summary(
    request: Request,
    sess=Depends(require_role("partner")),
    db: Session = Depends(get_db),
):
    u = get_current_user(sess, db)
    if not u.partner_id:
        raise HTTPException(status_code=403, detail="Partner not linked to user")

    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'RECEIVED')   AS received,
            COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
            COUNT(*) FILTER (WHERE status = 'SENT')       AS sent,
            COUNT(*) FILTER (WHERE status = 'FAILED')     AS failed
        FROM payouts
        WHERE partner_id = :partner_id
    """), {"partner_id": u.partner_id}).first()

    bal = db.execute(text("""
        SELECT balance_available, balance_reserved
        FROM partners
        WHERE id = :pid
    """), {"pid": u.partner_id}).first()

    return {
        "partner_id": u.partner_id,
        "payouts": {
            "received": int(row[0] or 0),
            "processing": int(row[1] or 0),
            "sent": int(row[2] or 0),
            "failed": int(row[3] or 0),
        },
        "balances": {
            "available": str(bal[0] or 0),
            "reserved": str(bal[1] or 0),
            "total": str((bal[0] or 0) + (bal[1] or 0)),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/partner/api/payouts")
def partner_list_payouts(
    request: Request,
    sess=Depends(require_role("partner")),
    db: Session = Depends(get_db),
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    u = get_current_user(sess, db)
    if not u.partner_id:
        raise HTTPException(status_code=403, detail="Partner not linked to user")

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    params: Dict[str, Any] = {
        "partner_id": u.partner_id,
        "limit": limit,
        "offset": offset,
    }

    where = ["p.partner_id = :partner_id"]

    if status:
        where.append("p.status = :status")
        params["status"] = status

    if q:
        where.append("(p.recipient ILIKE :q OR p.partner_tx_id ILIKE :q)")
        params["q"] = f"%{q}%"

    total = db.execute(text(f"""
        SELECT COUNT(*)
        FROM payouts p
        WHERE {" AND ".join(where)}
    """), params).scalar() or 0

    rows = db.execute(text(f"""
        SELECT
            p.id,
            p.partner_tx_id,
            p.amount,
            p.currency,
            p.recipient,
            p.provider,
            p.status,
            p.created_at,
            p.updated_at
        FROM payouts p
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


# ============================================================
# Admin: Create Partner + Partner Login (admin-only)
# ============================================================
class PartnerSignup(BaseModel):
    partner_name: str
    username: str
    password: str


@app.post("/admin/create-partner")
def admin_create_partner(
    body: PartnerSignup,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    # username must be unique
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    # create partner + API key
    api_key, prefix, key_hash = generate_api_key()

    partner = Partner(
        name=body.partner_name,
        api_key_prefix=prefix,
        api_key_hash=key_hash,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        # balances start at 0
    )
    db.add(partner)
    db.flush()

    # create login user linked to partner
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="partner",
        is_active=True,
        partner_id=partner.id,
    )
    db.add(user)
    db.commit()

    return {
        "partner_id": partner.id,
        "username": user.username,
        "api_key": api_key,  # show once
        "message": "Partner created",
    }


# ============================================================
# Executor endpoints (auth = X-Executor-Token)
# ============================================================
@app.post("/internal/executor/report")
def executor_report(request: Request,body: ExecutorReport,_auth=Depends(require_executor_token),db: Session=Depends(get_db)):
    raise HTTPException(410,"Legacy result reports cannot safely authorize financial settlement")



@app.post("/internal/executor/claim")
def executor_claim(request: Request,body: ExecutorClaimRequest,_auth=Depends(require_executor_token),db: Session=Depends(get_db)):
    raise HTTPException(410,"Use /internal/workers/v2/claim with a device assignment")



from backend_routes import make_router
app.include_router(make_router(get_partner_from_api_key,require_role,get_db))
from earnings import make_router as earnings_router
app.include_router(earnings_router(require_role,get_db))
from admin_dashboard import make_router as admin_dashboard_router
app.include_router(admin_dashboard_router(require_role,get_db))
from public_site.routes import make_router as public_router
from public_site.partnerships import make_router as partnership_router
app.include_router(partnership_router(get_db,require_role))
app.include_router(public_router())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=int(os.getenv("WORKERS", 4)),
        log_level="info",
        access_log=True,
    )
