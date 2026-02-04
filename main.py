
# # main.py - PRODUCTION READY (UPDATED)
# import os
# import json
# import logging
# import structlog
# from datetime import datetime, timezone, timedelta
# from decimal import Decimal
# from uuid import UUID as PyUUID
# from typing import Dict, Any

# from pydantic import BaseModel
# from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
# from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates
# from fastapi.staticfiles import StaticFiles

# from sqlalchemy import text, bindparam, exc
# from sqlalchemy.orm import Session

# from config import get_settings
# from database import engine, get_db
# from middleware import limiter, setup_middleware

# # SQLAlchemy models
# from models import Base, Partner, Payout, PayoutQueue, User

# # Pydantic schemas you already have
# from schemas import PayoutCreate, ExecutorClaimRequest, ExecutorReport

# # Partner API-key auth helpers (already in your project)
# from security import verify_api_key, validate_api_key_format, extract_prefix, generate_api_key

# # UI session auth + role
# from auth_session import require_role, hash_password

# # Login router (/login, /logout)
# from routes_ui_auth import router as ui_auth_router


# # -------------------------
# # Logging
# # -------------------------
# logging.basicConfig(level=logging.INFO)
# structlog.configure(
#     processors=[
#         structlog.stdlib.filter_by_level,
#         structlog.stdlib.add_logger_name,
#         structlog.stdlib.add_log_level,
#         structlog.stdlib.PositionalArgumentsFormatter(),
#         structlog.processors.TimeStamper(fmt="iso"),
#         structlog.processors.JSONRenderer(),
#     ],
#     context_class=dict,
#     logger_factory=structlog.stdlib.LoggerFactory(),
#     wrapper_class=structlog.stdlib.BoundLogger,
#     cache_logger_on_first_use=True,
# )
# logger = structlog.get_logger(__name__)
# settings = get_settings()


# # -------------------------
# # App
# # -------------------------
# app = FastAPI(
#     title=settings.api_title,
#     version=settings.api_version,
#     docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
#     redoc_url=None,
# )

# # DB tables (dev). In production use migrations.
# Base.metadata.create_all(bind=engine)

# templates = Jinja2Templates(directory="templates")
# app.mount("/static", StaticFiles(directory="static"), name="static")
# @app.get("/", response_class=HTMLResponse, include_in_schema=False)
# def landing(request: Request):
#     return templates.TemplateResponse("home.html", {"request": request})
# # middleware
# setup_middleware(app)
# app.state.limiter = limiter

# # add login router
# app.include_router(ui_auth_router)


# # -------------------------
# # Executor token (internal)
# # -------------------------
# EXECUTOR_TOKEN = settings.executor_token

# def require_executor_token(x_executor_token: str | None = Header(None, alias="X-Executor-Token")):
#     if not x_executor_token:
#         raise HTTPException(status_code=401, detail="Missing X-Executor-Token")
#     if x_executor_token != EXECUTOR_TOKEN:
#         raise HTTPException(status_code=401, detail="Invalid executor token")
#     return True


# # -------------------------
# # Partner API key auth (external partner integration)
# # -------------------------
# def get_partner_from_api_key(
#     x_api_key: str = Header(..., alias="X-API-Key"),
#     db: Session = Depends(get_db),
# ) -> Partner:
#     if not validate_api_key_format(x_api_key):
#         logger.warning("Invalid API key format", api_key_prefix=x_api_key[:8])
#         raise HTTPException(status_code=401, detail="Invalid API key format")

#     prefix = extract_prefix(x_api_key)
#     partner = (
#         db.query(Partner)
#         .filter(Partner.is_active == True, Partner.api_key_prefix == prefix)
#         .first()
#     )

#     if not partner or not verify_api_key(x_api_key, partner.api_key_hash):
#         logger.warning("Invalid API key attempt", partner_id=partner.id if partner else None)
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

#     return partner


# # -------------------------
# # Business status decision
# # -------------------------
# def is_plausible_balance(x: Decimal | None) -> bool:
#     if x is None:
#         return False
#     return Decimal("0") <= x <= Decimal(str(settings.max_amount))


# def decide_status(amount: Decimal, bb: Decimal | None, ba: Decimal | None, ussd_text: str):
#     """
#     SAFE BY DEFAULT:
#     Mark SENT only with strong evidence.
#     """
#     t = (ussd_text or "").lower()

#     if "kuguma filna" in t or "haraaga" in t or "insufficient" in t:
#         return ("FAILED", "INSUFFICIENT_BALANCE")

#     wrong_menu_indicators = ["sunrise", "settings", "°", "weather", "clock", "calendar"]
#     if any(indicator in t for indicator in wrong_menu_indicators):
#         return ("FAILED", "WRONG_SCREEN")

#     strong_success = ["success", "successful", "completed", "reference", "tixraac",
#                       "trx", "txid", "ref:", "lacag", "diray"]
#     if any(k in t for k in strong_success):
#         return ("SENT", "USSD_STRONG_OK")

#     if is_plausible_balance(bb) and is_plausible_balance(ba):
#         diff = bb - ba
#         if diff >= amount and diff <= (amount * Decimal("1.25")):
#             return ("SENT", "BALANCE_DIFF_OK")

#     return ("FAILED", "AMBIGUOUS")


# # -------------------------
# # Home + Health
# # -------------------------
# @app.get("/", include_in_schema=False)
# def home():
#     return RedirectResponse("/login", status_code=303)


# @app.get("/health")
# def health_check(db: Session = Depends(get_db)):
#     try:
#         db.execute(text("SELECT 1"))
#         queue_stats = db.execute(text("""
#             SELECT
#                 COUNT(*) as total_queued,
#                 SUM(CASE WHEN status = 'IN_PROGRESS' AND lease_until < now() THEN 1 ELSE 0 END) as expired_tasks
#             FROM payout_queue
#         """)).first()

#         return {
#             "status": "healthy",
#             "timestamp": datetime.now(timezone.utc).isoformat(),
#             "database": "connected",
#             "queue_health": {
#                 "total_queued": queue_stats[0] or 0,
#                 "expired_tasks": queue_stats[1] or 0
#             }
#         }
#     except Exception as e:
#         logger.error("Health check failed", error=str(e))
#         raise HTTPException(status_code=503, detail="Service unhealthy")


# # ============================================================
# # Partner API endpoints (auth = X-API-Key)
# # ============================================================
# @app.post("/payouts-create", status_code=201)
# @limiter.limit("100/minute")
# def create_payout(
#     request: Request,
#     payload: PayoutCreate,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     existing = db.query(Payout).filter(
#         Payout.partner_id == partner.id,
#         Payout.partner_tx_id == payload.partner_tx_id
#     ).first()

#     if existing:
#         return {
#             "id": str(existing.id),
#             "status": existing.status,
#             "created_at": existing.created_at,
#             "duplicate": True,
#             "message": "Transaction already exists"
#         }

#     if payload.amount <= 0:
#         raise HTTPException(status_code=400, detail="Amount must be positive")
#     if payload.amount > settings.max_amount:
#         raise HTTPException(status_code=400, detail=f"Amount exceeds maximum limit of {settings.max_amount}")
#     if not payload.recipient.startswith("+"):
#         raise HTTPException(status_code=400, detail="Recipient phone must start with +")

#     recent_duplicate = db.query(Payout).filter(
#         Payout.partner_id == partner.id,
#         Payout.recipient == payload.recipient,
#         Payout.amount == payload.amount,
#         Payout.status.in_(["RECEIVED", "PROCESSING", "PENDING"]),
#         Payout.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5)
#     ).first()

#     if recent_duplicate:
#         raise HTTPException(
#             status_code=409,
#             detail=f"Similar payment to {payload.recipient} for {payload.amount} was recently created. "
#                    f"If intentional, wait 5 minutes or change partner_tx_id."
#         )

#     payout = Payout(
#         partner_id=partner.id,
#         partner_tx_id=payload.partner_tx_id,
#         amount=payload.amount,
#         currency=payload.currency,
#         recipient=payload.recipient,
#         provider=payload.provider,
#         request_payload=json.dumps(payload.request_payload),
#         status="RECEIVED",
#         created_at=datetime.now(timezone.utc),
#         updated_at=datetime.now(timezone.utc),
#     )

#     db.add(payout)
#     db.flush()

#     db.add(PayoutQueue(
#         payout_id=payout.id,
#         status="PENDING",
#         created_at=datetime.now(timezone.utc)
#     ))

#     try:
#         db.commit()
#     except exc.IntegrityError as e:
#         db.rollback()
#         logger.error("Integrity error", error=str(e))
#         raise HTTPException(status_code=500, detail="Database error")
#     except Exception as e:
#         db.rollback()
#         logger.error("Create payout failed", error=str(e))
#         raise HTTPException(status_code=500, detail="Internal server error")

#     return {"id": str(payout.id), "status": payout.status, "created_at": payout.created_at, "duplicate": False}


# @app.get("/payouts/{payout_id}")
# @limiter.limit("60/minute")
# def get_payout(
#     request: Request,
#     payout_id: PyUUID,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     payout = db.query(Payout).filter(Payout.id == payout_id, Payout.partner_id == partner.id).first()
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     evidence = db.execute(text("""
#         SELECT executor_id, balance_before, balance_after, ussd_text, provider_ref, captured_at
#         FROM payout_evidence
#         WHERE payout_id = :payout_id
#     """), {"payout_id": str(payout_id)}).first()

#     return {
#         "id": str(payout.id),
#         "partner_tx_id": payout.partner_tx_id,
#         "amount": str(payout.amount),
#         "currency": payout.currency,
#         "recipient": payout.recipient,
#         "provider": payout.provider,
#         "status": payout.status,
#         "request_payload": json.loads(payout.request_payload) if payout.request_payload else None,
#         "created_at": payout.created_at,
#         "updated_at": payout.updated_at,
#         "evidence": {
#             "executor_id": evidence[0] if evidence else None,
#             "balance_before": str(evidence[1]) if evidence and evidence[1] else None,
#             "balance_after": str(evidence[2]) if evidence and evidence[2] else None,
#             "ussd_text": evidence[3] if evidence else None,
#             "provider_ref": evidence[4] if evidence else None,
#             "captured_at": evidence[5] if evidence else None,
#         } if evidence else None
#     }


# @app.get("/stats/summary")
# @limiter.limit("30/minute")
# def summary_stats(
#     request: Request,
#     partner: Partner = Depends(get_partner_from_api_key),
#     db: Session = Depends(get_db),
# ):
#     today = datetime.now(timezone.utc).date()

#     today_amount = db.execute(text("""
#         SELECT COALESCE(SUM(amount), 0)
#         FROM payouts
#         WHERE partner_id = :partner_id
#           AND status = 'SENT'
#           AND DATE(created_at) = :today
#     """), {"partner_id": partner.id, "today": today}).scalar() or 0

#     result = db.execute(text("""
#         SELECT
#             COUNT(*) FILTER (WHERE p.status = 'RECEIVED')   as received,
#             COUNT(*) FILTER (WHERE p.status = 'PROCESSING') as processing,
#             COUNT(*) FILTER (WHERE p.status = 'SENT')       as sent,
#             COUNT(*) FILTER (WHERE p.status = 'FAILED')     as failed
#         FROM payouts p
#         WHERE p.partner_id = :partner_id
#     """), {"partner_id": partner.id}).first()

#     return {
#         "received": result[0] or 0,
#         "processing": result[1] or 0,
#         "sent": result[2] or 0,
#         "failed": result[3] or 0,
#         "daily_sent_amount": float(today_amount),
#         "partner_since": partner.created_at.date() if partner.created_at else None
#     }


# # ============================================================
# # Admin UI pages (auth = session role)
# # ============================================================
# @app.get("/admin", response_class=HTMLResponse)
# def admin_dashboard(request: Request, _sess=Depends(require_role("admin"))):
#     return templates.TemplateResponse("admin.html", {"request": request})


# @app.get("/partner", response_class=HTMLResponse)
# def partner_dashboard(request: Request, _sess=Depends(require_role("partner"))):
#     return templates.TemplateResponse("partner.html", {"request": request})


# # ============================================================
# # Admin UI APIs (auth = session role admin)
# # ============================================================
# @app.get("/admin/api/summary")
# def admin_summary(
#     request: Request,
#     _auth=Depends(require_role("admin")),
#     db: Session = Depends(get_db),
# ):
#     row = db.execute(text("""
#         SELECT
#             COUNT(*) FILTER (WHERE status = 'RECEIVED')   AS received,
#             COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
#             COUNT(*) FILTER (WHERE status = 'SENT')       AS sent,
#             COUNT(*) FILTER (WHERE status = 'FAILED')     AS failed
#         FROM payouts
#     """)).first()

#     qrow = db.execute(text("""
#         SELECT
#             COUNT(*) FILTER (WHERE status = 'PENDING')     AS pending,
#             COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress,
#             SUM(CASE WHEN status='IN_PROGRESS' AND lease_until < now() THEN 1 ELSE 0 END) AS expired
#         FROM payout_queue
#     """)).first()

#     return {
#         "payouts": {
#             "received": row[0] or 0,
#             "processing": row[1] or 0,
#             "sent": row[2] or 0,
#             "failed": row[3] or 0,
#         },
#         "queue": {
#             "pending": qrow[0] or 0,
#             "in_progress": qrow[1] or 0,
#             "expired": qrow[2] or 0,
#         },
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#     }


# @app.get("/admin/api/payouts")
# def admin_list_payouts(
#     request: Request,
#     _auth=Depends(require_role("admin")),
#     db: Session = Depends(get_db),
#     q: str | None = None,
#     status: str | None = None,
#     limit: int = 50,
#     offset: int = 0,
# ):
#     limit = max(1, min(limit, 200))
#     offset = max(0, offset)

#     params: Dict[str, Any] = {"limit": limit, "offset": offset}
#     where = ["1=1"]

#     if status:
#         where.append("p.status = :status")
#         params["status"] = status

#     if q:
#         where.append("""
#             (
#               p.recipient ILIKE :q
#               OR p.partner_tx_id ILIKE :q
#               OR EXISTS (
#                 SELECT 1 FROM payout_evidence e
#                 WHERE e.payout_id = p.id AND e.provider_ref ILIKE :q
#               )
#             )
#         """)
#         params["q"] = f"%{q}%"

#     total = db.execute(text(f"""
#         SELECT COUNT(*)
#         FROM payouts p
#         WHERE {" AND ".join(where)}
#     """), params).scalar() or 0

#     rows = db.execute(text(f"""
#         SELECT
#             p.id,
#             p.partner_id,
#             p.partner_tx_id,
#             p.amount,
#             p.currency,
#             p.recipient,
#             p.provider,
#             p.status,
#             p.created_at,
#             p.updated_at,
#             pq.status AS queue_status,
#             pq.worker_id,
#             pq.lease_until
#         FROM payouts p
#         LEFT JOIN payout_queue pq ON pq.payout_id = p.id
#         WHERE {" AND ".join(where)}
#         ORDER BY p.created_at DESC
#         LIMIT :limit OFFSET :offset
#     """), params).mappings().all()

#     return {"total": int(total), "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


# @app.get("/admin/api/queue")
# def admin_queue(
#     request: Request,
#     _auth=Depends(require_role("admin")),
#     db: Session = Depends(get_db),
#     limit: int = 100,
# ):
#     limit = max(1, min(limit, 500))
#     rows = db.execute(text("""
#         SELECT
#             pq.payout_id,
#             pq.status as queue_status,
#             pq.lease_until,
#             pq.worker_id,
#             pq.created_at as queue_created,
#             p.status as payout_status,
#             p.amount,
#             p.currency,
#             p.recipient,
#             p.partner_tx_id
#         FROM payout_queue pq
#         LEFT JOIN payouts p ON p.id = pq.payout_id
#         ORDER BY pq.created_at DESC
#         LIMIT :limit
#     """), {"limit": limit}).mappings().all()

#     return {"items": [dict(r) for r in rows]}


# @app.post("/admin/reset-stuck-tasks")
# @limiter.limit("10/minute")
# def reset_stuck_tasks(
#     request: Request,
#     hours_old: int = 1,
#     _auth=Depends(require_role("admin")),
#     db: Session = Depends(get_db),
# ):
#     stuck_tasks = db.execute(text("""
#         SELECT pq.payout_id, pq.worker_id, pq.lease_until
#         FROM payout_queue pq
#         WHERE pq.status = 'IN_PROGRESS'
#           AND pq.lease_until < now() - interval :hours_old hour
#         ORDER BY pq.lease_until
#     """), {"hours_old": hours_old}).mappings().all()

#     if not stuck_tasks:
#         return {"message": "No stuck tasks found", "reset_count": 0}

#     result = db.execute(text("""
#         UPDATE payout_queue
#         SET status = 'PENDING',
#             lease_until = NULL,
#             worker_id = NULL
#         WHERE status = 'IN_PROGRESS'
#           AND lease_until < now() - interval :hours_old hour
#         RETURNING payout_id
#     """), {"hours_old": hours_old})

#     reset_ids = [str(row[0]) for row in result]
#     db.commit()

#     logger.warning("Stuck tasks reset by admin", count=len(reset_ids), hours_old=hours_old)
#     return {"message": f"Reset {len(reset_ids)} stuck tasks", "reset_count": len(reset_ids), "reset_ids": reset_ids[:50]}




# def get_current_user(
#     sess: dict,
#     db: Session,
# ) -> User:
#     u = db.query(User).filter(User.id == sess["uid"], User.is_active == True).first()
#     if not u:
#         raise HTTPException(status_code=401, detail="User not found")
#     return u


# @app.get("/partner/api/summary")
# def partner_summary(
#     request: Request,
#     sess=Depends(require_role("partner")),
#     db: Session = Depends(get_db),
# ):
#     u = get_current_user(sess, db)
#     if not u.partner_id:
#         raise HTTPException(status_code=403, detail="Partner not linked to user")

#     row = db.execute(text("""
#         SELECT
#             COUNT(*) FILTER (WHERE status = 'RECEIVED')   AS received,
#             COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
#             COUNT(*) FILTER (WHERE status = 'SENT')       AS sent,
#             COUNT(*) FILTER (WHERE status = 'FAILED')     AS failed
#         FROM payouts
#         WHERE partner_id = :partner_id
#     """), {"partner_id": u.partner_id}).first()

#     return {
#         "partner_id": u.partner_id,
#         "payouts": {
#             "received": row[0] or 0,
#             "processing": row[1] or 0,
#             "sent": row[2] or 0,
#             "failed": row[3] or 0,
#         },
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#     }


# @app.get("/partner/api/payouts")
# def partner_list_payouts(
#     request: Request,
#     sess=Depends(require_role("partner")),
#     db: Session = Depends(get_db),
#     status: str | None = None,
#     q: str | None = None,
#     limit: int = 50,
#     offset: int = 0,
# ):
#     u = get_current_user(sess, db)
#     if not u.partner_id:
#         raise HTTPException(status_code=403, detail="Partner not linked to user")

#     limit = max(1, min(limit, 200))
#     offset = max(0, offset)

#     params: Dict[str, Any] = {
#         "partner_id": u.partner_id,
#         "limit": limit,
#         "offset": offset,
#     }

#     where = ["p.partner_id = :partner_id"]

#     if status:
#         where.append("p.status = :status")
#         params["status"] = status

#     if q:
#         where.append("(p.recipient ILIKE :q OR p.partner_tx_id ILIKE :q)")
#         params["q"] = f"%{q}%"

#     total = db.execute(text(f"""
#         SELECT COUNT(*)
#         FROM payouts p
#         WHERE {" AND ".join(where)}
#     """), params).scalar() or 0

#     rows = db.execute(text(f"""
#         SELECT
#             p.id,
#             p.partner_tx_id,
#             p.amount,
#             p.currency,
#             p.recipient,
#             p.provider,
#             p.status,
#             p.created_at,
#             p.updated_at
#         FROM payouts p
#         WHERE {" AND ".join(where)}
#         ORDER BY p.created_at DESC
#         LIMIT :limit OFFSET :offset
#     """), params).mappings().all()

#     return {
#         "total": int(total),
#         "limit": limit,
#         "offset": offset,
#         "items": [dict(r) for r in rows],
#     }

# # ============================================================
# # Admin: Create Partner + Partner Login (admin-only)
# # ============================================================
# class PartnerSignup(BaseModel):
#     partner_name: str
#     username: str
#     password: str


# @app.post("/admin/create-partner")
# def admin_create_partner(
#     body: PartnerSignup,
#     _auth=Depends(require_role("admin")),
#     db: Session = Depends(get_db),
# ):
#     # username must be unique
#     if db.query(User).filter(User.username == body.username).first():
#         raise HTTPException(status_code=400, detail="Username already exists")

#     # create partner + API key
#     api_key, prefix, key_hash = generate_api_key()

#     partner = Partner(
#         name=body.partner_name,
#         api_key_prefix=prefix,
#         api_key_hash=key_hash,
#         is_active=True,
#         created_at=datetime.now(timezone.utc),
#     )
#     db.add(partner)
#     db.flush()

#     # create login user linked to partner
#     user = User(
#         username=body.username,
#         password_hash=hash_password(body.password),
#         role="partner",
#         is_active=True,
#         partner_id=partner.id,  # IMPORTANT: requires users.partner_id column in DB + model
#     )
#     db.add(user)
#     db.commit()

#     return {
#         "partner_id": partner.id,
#         "username": user.username,
#         "api_key": api_key,  # show once
#         "message": "Partner created",
#     }


# # ============================================================
# # Executor endpoints (auth = X-Executor-Token)
# # ============================================================
# @app.post("/internal/executor/report")
# @limiter.limit("60/minute")
# def executor_report(
#     request: Request,
#     body: ExecutorReport,
#     _auth=Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
#     if not payout:
#         raise HTTPException(status_code=404, detail="Payout not found")

#     # upsert evidence
#     db.execute(text("""
#         INSERT INTO payout_evidence (
#             payout_id, executor_id, balance_before, balance_after,
#             ussd_text, provider_ref, captured_at
#         )
#         VALUES (
#             :payout_id, :executor_id, :bb, :ba,
#             :ussd, :ref, now()
#         )
#         ON CONFLICT (payout_id)
#         DO UPDATE SET
#             executor_id = EXCLUDED.executor_id,
#             balance_before = EXCLUDED.balance_before,
#             balance_after = EXCLUDED.balance_after,
#             ussd_text = EXCLUDED.ussd_text,
#             provider_ref = EXCLUDED.provider_ref,
#             captured_at = now()
#     """), {
#         "payout_id": str(body.payout_id),
#         "executor_id": body.executor_id,
#         "bb": body.balance_before,
#         "ba": body.balance_after,
#         "ussd": body.ussd_text,
#         "ref": body.provider_ref,
#     })

#     final_status, reason = decide_status(
#         payout.amount,
#         body.balance_before,
#         body.balance_after,
#         body.ussd_text or "",
#     )

#     payout.status = final_status
#     payout.updated_at = datetime.now(timezone.utc)

#     if final_status in ("SENT", "FAILED"):
#         db.execute(text("DELETE FROM payout_queue WHERE payout_id = :id"), {"id": str(body.payout_id)})

#     db.commit()

#     return {"ok": True, "status": final_status, "reason": reason}


# @app.post("/internal/executor/claim")
# @limiter.limit("30/minute")
# def executor_claim(
#     request: Request,
#     body: ExecutorClaimRequest,
#     _auth=Depends(require_executor_token),
#     db: Session = Depends(get_db),
# ):
#     if body.lease_secs > 600:
#         raise HTTPException(status_code=400, detail="Lease time too long (max 600 seconds)")
#     if body.batch_size > 20:
#         raise HTTPException(status_code=400, detail="Batch size too large (max 20)")

#     lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)

#     claimed = db.execute(text("""
#         WITH candidates AS (
#             SELECT pq.payout_id
#             FROM payout_queue pq
#             JOIN payouts p ON p.id = pq.payout_id
#             WHERE (
#                 pq.status = 'PENDING'
#                 OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
#             )
#             AND p.status = 'RECEIVED'
#             ORDER BY pq.created_at
#             FOR UPDATE SKIP LOCKED
#             LIMIT :limit
#         )
#         UPDATE payout_queue pq
#         SET status = 'IN_PROGRESS',
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

#     payout_ids = [r["payout_id"] for r in claimed]
#     if not payout_ids:
#         db.commit()
#         return {"jobs": [], "message": "No jobs available"}

#     upd = text("""
#         UPDATE payouts
#         SET status = 'PROCESSING',
#             updated_at = now()
#         WHERE id IN :ids
#           AND status = 'RECEIVED'
#     """).bindparams(bindparam("ids", expanding=True))

#     db.execute(upd, {"ids": payout_ids})

#     sel = text("""
#         SELECT p.id, p.amount, p.currency, p.recipient, p.provider, p.request_payload
#         FROM payouts p
#         WHERE p.id IN :ids
#         ORDER BY p.created_at
#     """).bindparams(bindparam("ids", expanding=True))

#     jobs = db.execute(sel, {"ids": payout_ids}).mappings().all()
#     db.commit()

#     return {"jobs": [dict(j) for j in jobs], "lease_until": lease_until.isoformat(), "count": len(jobs)}


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=int(os.getenv("PORT", 8000)),
#         workers=int(os.getenv("WORKERS", 4)),
#         log_level="info",
#         access_log=True,
#     )



# main.py — PRODUCTION READY (with Partner Prepaid Balance + Reserve/Capture/Release)
import os
import json
import logging
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID as PyUUID
from typing import Dict, Any

from pydantic import BaseModel
from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text, bindparam, exc
from sqlalchemy.orm import Session

from config import get_settings
from database import engine, get_db
from middleware import limiter, setup_middleware

# SQLAlchemy models
from models import Base, Partner, Payout, PayoutQueue, User  # + ensure you added PayoutReservation + partner balance columns in models/db
# Pydantic schemas you already have
from schemas import PayoutCreate, ExecutorClaimRequest, ExecutorReport

# Partner API-key auth helpers (already in your project)
from security import verify_api_key, validate_api_key_format, extract_prefix, generate_api_key

# UI session auth + role
from auth_session import require_role, hash_password

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

# Fee charged to partner per payout (fixed)
# Put this in config/settings, e.g. PARTNER_FEE=0.60
PARTNER_FEE = Decimal(str(getattr(settings, "partner_fee", "0.60")))


# -------------------------
# App
# -------------------------
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url=None,
)

# DB tables (dev). In production use migrations.
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


# middleware
setup_middleware(app)
app.state.limiter = limiter

# add login router
app.include_router(ui_auth_router)


# -------------------------
# Executor token (internal)
# -------------------------
EXECUTOR_TOKEN = settings.executor_token


def require_executor_token(x_executor_token: str | None = Header(None, alias="X-Executor-Token")):
    if not x_executor_token:
        raise HTTPException(status_code=401, detail="Missing X-Executor-Token")
    if x_executor_token != EXECUTOR_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid executor token")
    return True


# -------------------------
# Partner API key auth (external partner integration)
# -------------------------
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

    return partner


# -------------------------
# Business status decision
# -------------------------
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

    if "kuguma filna" in t or "haraaga" in t or "insufficient" in t:
        return ("FAILED", "INSUFFICIENT_BALANCE")

    wrong_menu_indicators = ["sunrise", "settings", "°", "weather", "clock", "calendar"]
    if any(indicator in t for indicator in wrong_menu_indicators):
        return ("FAILED", "WRONG_SCREEN")

    strong_success = ["success", "successful", "completed", "reference", "tixraac",
                      "trx", "txid", "ref:", "lacag", "diray"]
    if any(k in t for k in strong_success):
        return ("SENT", "USSD_STRONG_OK")

    if is_plausible_balance(bb) and is_plausible_balance(ba):
        diff = bb - ba
        if diff >= amount and diff <= (amount * Decimal("1.25")):
            return ("SENT", "BALANCE_DIFF_OK")

    return ("FAILED", "AMBIGUOUS")


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
@limiter.limit("100/minute")
def create_payout(
    request: Request,
    payload: PayoutCreate,
    partner: Partner = Depends(get_partner_from_api_key),
    db: Session = Depends(get_db),
):
    # -------------------------
    # Idempotency (must have)
    # -------------------------
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
            "message": "Transaction already exists"
        }

    # -------------------------
    # Validation
    # -------------------------
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if payload.amount > settings.max_amount:
        raise HTTPException(status_code=400, detail=f"Amount exceeds maximum limit of {settings.max_amount}")
    if not payload.recipient.startswith("+"):
        raise HTTPException(status_code=400, detail="Recipient phone must start with +")

    recent_duplicate = db.query(Payout).filter(
        Payout.partner_id == partner.id,
        Payout.recipient == payload.recipient,
        Payout.amount == payload.amount,
        Payout.status.in_(["RECEIVED", "PROCESSING", "PENDING"]),
        Payout.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5)
    ).first()

    if recent_duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"Similar payment to {payload.recipient} for {payload.amount} was recently created. "
                   f"If intentional, wait 5 minutes or change partner_tx_id."
        )

    fee = PARTNER_FEE
    total = Decimal(payload.amount) + fee

    # -------------------------
    # Reserve partner funds ATOMICALLY
    # -------------------------
    try:
        # Lock partner row so two requests can't spend same balance
        prow = db.execute(
            text("SELECT id, balance_available, balance_reserved FROM partners WHERE id=:id FOR UPDATE"),
            {"id": partner.id}
        ).mappings().first()

        if not prow:
            raise HTTPException(status_code=401, detail="Partner not found")

        available = Decimal(str(prow["balance_available"]))

        if available < total:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_partner_balance",
                    "available": str(available),
                    "required": str(total),
                },
            )

        # Create payout
        payout = Payout(
            partner_id=partner.id,
            partner_tx_id=payload.partner_tx_id,
            amount=payload.amount,
            currency=payload.currency,
            recipient=payload.recipient,
            provider=payload.provider,
            request_payload=json.dumps(payload.request_payload),
            status="RECEIVED",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(payout)
        db.flush()

        # Create reservation record
        db.execute(text("""
            INSERT INTO payout_reservations (payout_id, partner_id, amount, fee, total, status, created_at)
            VALUES (:payout_id, :partner_id, :amount, :fee, :total, 'ACTIVE', now())
        """), {
            "payout_id": str(payout.id),
            "partner_id": partner.id,
            "amount": str(payload.amount),
            "fee": str(fee),
            "total": str(total),
        })

        # Move available -> reserved
        db.execute(text("""
            UPDATE partners
            SET balance_available = balance_available - :total,
                balance_reserved  = balance_reserved + :total
            WHERE id = :partner_id
        """), {"total": str(total), "partner_id": partner.id})

        # Enqueue job
        db.add(PayoutQueue(
            payout_id=payout.id,
            status="PENDING",
            created_at=datetime.now(timezone.utc)
        ))

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except exc.IntegrityError as e:
        db.rollback()
        logger.error("Integrity error", error=str(e))
        # If you added UNIQUE(partner_id, partner_tx_id), you could return idempotent response here too.
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        db.rollback()
        logger.error("Create payout failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

    bal = db.execute(text("""
        SELECT balance_available, balance_reserved FROM partners WHERE id=:id
    """), {"id": partner.id}).first()

    return {
        "id": str(payout.id),
        "status": payout.status,
        "created_at": payout.created_at,
        "duplicate": False,
        "fee": str(fee),
        "charged_total": str(total),
        "balances": {
            "available": str(bal[0] or 0),
            "reserved": str(bal[1] or 0),
            "total": str((bal[0] or 0) + (bal[1] or 0)),
        }
    }


@app.get("/payouts/{payout_id}")
@limiter.limit("60/minute")
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
@limiter.limit("30/minute")
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
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/partner", response_class=HTMLResponse)
def partner_dashboard(request: Request, _sess=Depends(require_role("partner"))):
    return templates.TemplateResponse("partner.html", {"request": request})


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
            "received": int(row[0] or 0),
            "processing": int(row[1] or 0),
            "sent": int(row[2] or 0),
            "failed": int(row[3] or 0),
        },
        "queue": {
            "pending": int(qrow[0] or 0),
            "in_progress": int(qrow[1] or 0),
            "expired": int(qrow[2] or 0),
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
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {"total": int(total), "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


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
        ORDER BY pq.created_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return {"items": [dict(r) for r in rows]}


@app.post("/admin/reset-stuck-tasks")
@limiter.limit("10/minute")
def reset_stuck_tasks(
    request: Request,
    hours_old: int = 1,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    stuck_tasks = db.execute(text("""
        SELECT pq.payout_id, pq.worker_id, pq.lease_until
        FROM payout_queue pq
        WHERE pq.status = 'IN_PROGRESS'
          AND pq.lease_until < now() - interval '1 hour' * :hours_old
        ORDER BY pq.lease_until
    """), {"hours_old": hours_old}).mappings().all()

    if not stuck_tasks:
        return {"message": "No stuck tasks found", "reset_count": 0}

    result = db.execute(text("""
        UPDATE payout_queue
        SET status = 'PENDING',
            lease_until = NULL,
            worker_id = NULL
        WHERE status = 'IN_PROGRESS'
          AND lease_until < now() - interval '1 hour' * :hours_old
        RETURNING payout_id
    """), {"hours_old": hours_old})

    reset_ids = [str(row[0]) for row in result]
    db.commit()

    logger.warning("Stuck tasks reset by admin", count=len(reset_ids), hours_old=hours_old)
    return {"message": f"Reset {len(reset_ids)} stuck tasks", "reset_count": len(reset_ids), "reset_ids": reset_ids[:50]}


# -------------------------
# Admin: Partner deposit/top-up (prepaid float)
# -------------------------
class PartnerDeposit(BaseModel):
    amount: Decimal
    reference: str | None = None
    note: str | None = None


# ============================================================
# Admin: List all partners
# ============================================================
@app.get("/admin/api/partners")
@limiter.limit("30/minute")
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
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    sort: str = "balance_desc",
    active_only: bool = False,
):
    page = max(1, page)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit
    
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
            balance_available, balance_reserved,
            created_at, updated_at
        FROM partners 
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """)
    
    partners = db.execute(query, params).mappings().all()
    
    return {
        "partners": list(partners),
        "total": total,
        "page": page,
        "total_pages": (total + limit - 1) // limit,
        "limit": limit,
    }

# Enhanced deposit endpoint with audit trail
@app.post("/admin/api/funds/deposit")
@limiter.limit("30/minute")
def admin_deposit_funds(
    request: Request,
    body: PartnerDeposit,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    try:
        # Lock partner row for update
        partner = db.execute(
            text("""
                SELECT id, name, balance_available, balance_reserved 
                FROM partners 
                WHERE id = :partner_id 
                FOR UPDATE
            """),
            {"partner_id": body.partner_id}
        ).mappings().first()
        
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        # Calculate new balance
        new_balance = Decimal(str(partner["balance_available"])) + body.amount
        
        # Update partner balance
        db.execute(text("""
            UPDATE partners 
            SET balance_available = balance_available + :amount,
                updated_at = now()
            WHERE id = :partner_id
        """), {
            "amount": str(body.amount),
            "partner_id": body.partner_id
        })
        
        # Record in audit table (create if doesn't exist)
        try:
            db.execute(text("""
                INSERT INTO balance_transactions (
                    partner_id, type, amount, previous_balance, 
                    new_balance, reference, admin_user, created_at
                ) VALUES (
                    :partner_id, 'deposit', :amount, :prev_balance,
                    :new_balance, :reference, :admin_user, now()
                )
            """), {
                "partner_id": body.partner_id,
                "amount": str(body.amount),
                "prev_balance": str(partner["balance_available"]),
                "new_balance": str(new_balance),
                "reference": body.reference,
                "admin_user": _auth.get("username", "admin")  # Assuming _auth contains user info
            })
        except Exception as e:
            logger.warning("Could not record transaction audit", error=str(e))
            # Continue even if audit fails
        
        db.commit()
        
        # Get updated balances
        updated = db.execute(text("""
            SELECT balance_available, balance_reserved 
            FROM partners 
            WHERE id = :partner_id
        """), {"partner_id": body.partner_id}).first()
        
        return {
            "success": True,
            "message": f"Successfully deposited ${body.amount} to partner",
            "partner_id": body.partner_id,
            "balances": {
                "available": str(updated[0] or 0),
                "reserved": str(updated[1] or 0),
                "total": str((updated[0] or 0) + (updated[1] or 0)),
            }
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("Deposit failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# New: Adjust balance (add, subtract, or set)
@app.post("/admin/api/funds/adjust")
@limiter.limit("20/minute")
def admin_adjust_funds(
    request: Request,
    body: FundAdjustment,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    valid_types = ['add', 'subtract', 'set']
    if body.adjustment_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid adjustment type. Must be one of: {valid_types}")
    
    valid_balances = ['available', 'reserved', 'both']
    if body.balance_type not in valid_balances:
        raise HTTPException(status_code=400, detail=f"Invalid balance type. Must be one of: {valid_balances}")
    
    try:
        # Lock partner row
        partner = db.execute(
            text("""
                SELECT id, name, balance_available, balance_reserved 
                FROM partners 
                WHERE id = :partner_id 
                FOR UPDATE
            """),
            {"partner_id": body.partner_id}
        ).mappings().first()
        
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        # Calculate new balances
        prev_available = Decimal(str(partner["balance_available"]))
        prev_reserved = Decimal(str(partner["balance_reserved"]))
        
        if body.adjustment_type == 'set':
            if body.balance_type == 'available':
                new_available = body.amount
                new_reserved = prev_reserved
            elif body.balance_type == 'reserved':
                new_available = prev_available
                new_reserved = body.amount
            else:  # both
                new_available = body.amount / Decimal('2')
                new_reserved = body.amount / Decimal('2')
        elif body.adjustment_type == 'add':
            if body.balance_type == 'available':
                new_available = prev_available + body.amount
                new_reserved = prev_reserved
            elif body.balance_type == 'reserved':
                new_available = prev_available
                new_reserved = prev_reserved + body.amount
            else:  # both
                new_available = prev_available + body.amount / Decimal('2')
                new_reserved = prev_reserved + body.amount / Decimal('2')
        else:  # subtract
            if body.balance_type == 'available':
                if prev_available < body.amount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient available balance: {prev_available}"
                    )
                new_available = prev_available - body.amount
                new_reserved = prev_reserved
            elif body.balance_type == 'reserved':
                if prev_reserved < body.amount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient reserved balance: {prev_reserved}"
                    )
                new_available = prev_available
                new_reserved = prev_reserved - body.amount
            else:  # both
                if (prev_available + prev_reserved) < body.amount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient total balance: {prev_available + prev_reserved}"
                    )
                # Distribute subtraction proportionally
                total = prev_available + prev_reserved
                if total > 0:
                    available_ratio = prev_available / total
                    reserved_ratio = prev_reserved / total
                    new_available = prev_available - (body.amount * available_ratio)
                    new_reserved = prev_reserved - (body.amount * reserved_ratio)
                else:
                    new_available = Decimal('0')
                    new_reserved = Decimal('0')
        
        # Update balances
        update_query = text("""
            UPDATE partners 
            SET balance_available = :available,
                balance_reserved = :reserved,
                updated_at = now()
            WHERE id = :partner_id
        """)
        
        db.execute(update_query, {
            "available": str(new_available),
            "reserved": str(new_reserved),
            "partner_id": body.partner_id
        })
        
        # Record audit trail
        try:
            db.execute(text("""
                INSERT INTO balance_transactions (
                    partner_id, type, amount, previous_balance, 
                    new_balance, reference, admin_user, created_at,
                    adjustment_type, balance_type, notes
                ) VALUES (
                    :partner_id, :tx_type, :amount, :prev_balance,
                    :new_balance, :reference, :admin_user, now(),
                    :adj_type, :bal_type, :notes
                )
            """), {
                "partner_id": body.partner_id,
                "tx_type": 'adjustment',
                "amount": str(body.amount),
                "prev_balance": str(prev_available),
                "new_balance": str(new_available),
                "reference": f"Balance adjustment: {body.adjustment_type} {body.balance_type}",
                "admin_user": _auth.get("username", "admin"),
                "adj_type": body.adjustment_type,
                "bal_type": body.balance_type,
                "notes": body.reason
            })
        except Exception as e:
            logger.warning("Could not record adjustment audit", error=str(e))
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Balance adjusted successfully",
            "partner_id": body.partner_id,
            "previous": {
                "available": str(prev_available),
                "reserved": str(prev_reserved),
                "total": str(prev_available + prev_reserved),
            },
            "new": {
                "available": str(new_available),
                "reserved": str(new_reserved),
                "total": str(new_available + new_reserved),
            }
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("Adjustment failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

# Get transaction history for a partner
@app.get("/admin/api/funds/history/{partner_id}")
def admin_get_funds_history(
    request: Request,
    partner_id: int,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    # Check if partner exists
    partner = db.execute(
        text("SELECT id, name FROM partners WHERE id = :partner_id"),
        {"partner_id": partner_id}
    ).first()
    
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    # Try to get from balance_transactions table
    try:
        history = db.execute(text("""
            SELECT 
                id, type, amount, previous_balance, new_balance,
                reference, admin_user, created_at, adjustment_type, notes
            FROM balance_transactions
            WHERE partner_id = :partner_id
            ORDER BY created_at DESC
            LIMIT :limit
        """), {
            "partner_id": partner_id,
            "limit": limit
        }).mappings().all()
        
        return {
            "partner_id": partner_id,
            "partner_name": partner[1],
            "history": list(history)
        }
        
    except Exception:
        # If table doesn't exist, return empty
        return {
            "partner_id": partner_id,
            "partner_name": partner[1],
            "history": []
        }

# Create balance_transactions table if it doesn't exist
def create_balance_transactions_table(db: Session):
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id SERIAL PRIMARY KEY,
                partner_id INTEGER NOT NULL REFERENCES partners(id),
                type TEXT NOT NULL CHECK (type IN ('deposit', 'withdrawal', 'adjustment', 'initial')),
                amount NUMERIC(18,2) NOT NULL,
                previous_balance NUMERIC(18,2) NOT NULL,
                new_balance NUMERIC(18,2) NOT NULL,
                reference TEXT,
                admin_user TEXT,
                adjustment_type TEXT,
                balance_type TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_balance_tx_partner ON balance_transactions(partner_id);
            CREATE INDEX IF NOT EXISTS idx_balance_tx_created ON balance_transactions(created_at DESC);
        """))
        db.commit()
        logger.info("Created balance_transactions table")
    except Exception as e:
        logger.warning("Could not create balance_transactions table", error=str(e))

@app.get("/admin/funds", response_class=HTMLResponse)
def admin_funds_page(
    request: Request,
    _auth=Depends(require_role("admin")),
):
    return templates.TemplateResponse("admin_funds.html", {"request": request})

@app.post("/admin/partner/{partner_id}/deposit")
@limiter.limit("30/minute")
def admin_partner_deposit(
    request: Request,
    partner_id: int,
    body: PartnerDeposit,
    _auth=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    # Lock partner row
    prow = db.execute(
        text("SELECT id FROM partners WHERE id=:id FOR UPDATE"),
        {"id": partner_id}
    ).first()
    if not prow:
        raise HTTPException(status_code=404, detail="Partner not found")

    db.execute(text("""
        UPDATE partners
        SET balance_available = balance_available + :amt
        WHERE id = :pid
    """), {"amt": str(body.amount), "pid": partner_id})

    # Optional: record a deposit table/ledger later (recommended)
    db.commit()

    bal = db.execute(text("""
        SELECT balance_available, balance_reserved
        FROM partners
        WHERE id = :pid
    """), {"pid": partner_id}).first()

    return {
        "ok": True,
        "partner_id": partner_id,
        "balances": {
            "available": str(bal[0] or 0),
            "reserved": str(bal[1] or 0),
            "total": str((bal[0] or 0) + (bal[1] or 0)),
        }
    }


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
@limiter.limit("60/minute")
def executor_report(
    request: Request,
    body: ExecutorReport,
    _auth=Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    payout = db.query(Payout).filter(Payout.id == body.payout_id).first()
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    # upsert evidence
    db.execute(text("""
        INSERT INTO payout_evidence (
            payout_id, executor_id, balance_before, balance_after,
            ussd_text, provider_ref, captured_at
        )
        VALUES (
            :payout_id, :executor_id, :bb, :ba,
            :ussd, :ref, now()
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

    final_status, reason = decide_status(
        payout.amount,
        body.balance_before,
        body.balance_after,
        body.ussd_text or "",
    )

    payout.status = final_status
    payout.updated_at = datetime.now(timezone.utc)

    # ---- Reserve settlement: CAPTURE or RELEASE ----
    res = db.execute(text("""
        SELECT r.partner_id, r.total, r.status
        FROM payout_reservations r
        WHERE r.payout_id = :payout_id
        FOR UPDATE
    """), {"payout_id": str(body.payout_id)}).mappings().first()

    if not res:
        logger.warning("Missing reservation for payout", payout_id=str(body.payout_id))
    else:
        if res["status"] == "ACTIVE":
            if final_status == "SENT":
                db.execute(text("""
                    UPDATE payout_reservations
                    SET status = 'CAPTURED'
                    WHERE payout_id = :payout_id
                """), {"payout_id": str(body.payout_id)})

                db.execute(text("""
                    UPDATE partners
                    SET balance_reserved = balance_reserved - :total
                    WHERE id = :partner_id
                """), {"total": str(res["total"]), "partner_id": res["partner_id"]})

            elif final_status == "FAILED":
                db.execute(text("""
                    UPDATE payout_reservations
                    SET status = 'RELEASED'
                    WHERE payout_id = :payout_id
                """), {"payout_id": str(body.payout_id)})

                db.execute(text("""
                    UPDATE partners
                    SET balance_reserved  = balance_reserved - :total,
                        balance_available = balance_available + :total
                    WHERE id = :partner_id
                """), {"total": str(res["total"]), "partner_id": res["partner_id"]})

    # If finalized, remove from queue
    if final_status in ("SENT", "FAILED"):
        db.execute(text("DELETE FROM payout_queue WHERE payout_id = :id"), {"id": str(body.payout_id)})

    db.commit()

    return {"ok": True, "status": final_status, "reason": reason}


@app.post("/internal/executor/claim")
@limiter.limit("30/minute")
def executor_claim(
    request: Request,
    body: ExecutorClaimRequest,
    _auth=Depends(require_executor_token),
    db: Session = Depends(get_db),
):
    if body.lease_secs > 600:
        raise HTTPException(status_code=400, detail="Lease time too long (max 600 seconds)")
    if body.batch_size > 20:
        raise HTTPException(status_code=400, detail="Batch size too large (max 20)")

    lease_until = datetime.now(timezone.utc) + timedelta(seconds=body.lease_secs)

    claimed = db.execute(text("""
        WITH candidates AS (
            SELECT pq.payout_id
            FROM payout_queue pq
            JOIN payouts p ON p.id = pq.payout_id
            WHERE (
                pq.status = 'PENDING'
                OR (pq.status = 'IN_PROGRESS' AND pq.lease_until < now())
            )
            AND p.status = 'RECEIVED'
            ORDER BY pq.created_at
            FOR UPDATE SKIP LOCKED
            LIMIT :limit
        )
        UPDATE payout_queue pq
        SET status = 'IN_PROGRESS',
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

    payout_ids = [r["payout_id"] for r in claimed]
    if not payout_ids:
        db.commit()
        return {"jobs": [], "message": "No jobs available"}

    upd = text("""
        UPDATE payouts
        SET status = 'PROCESSING',
            updated_at = now()
        WHERE id IN :ids
          AND status = 'RECEIVED'
    """).bindparams(bindparam("ids", expanding=True))

    db.execute(upd, {"ids": payout_ids})

    sel = text("""
        SELECT p.id, p.amount, p.currency, p.recipient, p.provider, p.request_payload
        FROM payouts p
        WHERE p.id IN :ids
        ORDER BY p.created_at
    """).bindparams(bindparam("ids", expanding=True))

    jobs = db.execute(sel, {"ids": payout_ids}).mappings().all()
    db.commit()

    return {"jobs": [dict(j) for j in jobs], "lease_until": lease_until.isoformat(), "count": len(jobs)}


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
