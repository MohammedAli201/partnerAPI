# # # middleware.py
# # import time
# # import logging

# # from fastapi import FastAPI, Request
# # from fastapi.middleware.cors import CORSMiddleware

# # from slowapi import Limiter, _rate_limit_exceeded_handler
# # from slowapi.util import get_remote_address
# # from slowapi.errors import RateLimitExceeded

# # from config import get_settings

# # logger = logging.getLogger(__name__)
# # settings = get_settings()

# # # Rate limiter (per IP by default)
# # limiter = Limiter(
# #     key_func=get_remote_address,
# #     default_limits=[f"{settings.rate_limit_per_minute}/minute"],
# # )

# # def setup_middleware(app: FastAPI):
# #     """
# #     Setup all middleware for the application
# #     """
# #     # CORS
# #     app.add_middleware(
# #         CORSMiddleware,
# #         allow_origins=settings.cors_origins,
# #         allow_credentials=True,
# #         allow_methods=["*"],
# #         allow_headers=["*"],
# #     )

# #     # Rate limiting error handler
# #     app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# #     # Request logging middleware
# #     @app.middleware("http")
# #     async def log_requests(request: Request, call_next):
# #         start = time.perf_counter()
# #         try:
# #             response = await call_next(request)
# #             return response
# #         finally:
# #             duration_ms = (time.perf_counter() - start) * 1000.0

# #             # response may not exist if call_next raised an exception
# #             status_code = getattr(locals().get("response", None), "status_code", 500)

# #             logger.info(
# #                 "request",
# #                 extra={
# #                     "path": request.url.path,
# #                     "method": request.method,
# #                     "status_code": status_code,
# #                     "duration_ms": round(duration_ms, 2),
# #                     "client_ip": request.client.host if request.client else None,
# #                 },
# #             )


# from models import Partner
# from security import validate_api_key_format, extract_prefix
# from database import SessionLocal  # adjust if your session name is different
# from fastapi import FastAPI, Request

# # small cache to reduce DB hits
# _partner_cache: dict[str, tuple[int, float]] = {}  # prefix -> (partner_id, expires_at)
# CACHE_TTL = 60  # seconds

# def partner_key_func(request: Request) -> str:
#     api_key = request.headers.get("X-API-Key")

#     # No API key => fallback to IP
#     if not api_key or not validate_api_key_format(api_key):
#         return f"ip:{get_remote_address(request)}"

#     prefix = extract_prefix(api_key)

#     # Cache hit
#     now = time.time()
#     cached = _partner_cache.get(prefix)
#     if cached and cached[1] > now:
#         return f"partner:{cached[0]}"

#     # DB lookup by prefix
#     db = SessionLocal()
#     try:
#         partner = (
#             db.query(Partner)
#             .filter(Partner.is_active == True, Partner.api_key_prefix == prefix)
#             .first()
#         )
#         if not partner:
#             return f"ip:{get_remote_address(request)}"

#         _partner_cache[prefix] = (partner.id, now + CACHE_TTL)
#         return f"partner:{partner.id}"
#     finally:
#         db.close()
# middleware.py
import time
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ✅ Define limiter at module level
limiter = Limiter(
    key_func=get_remote_address,  # or partner_key_func if you added it
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)

def setup_middleware(app: FastAPI):
    # ✅ Attach limiter to app here
    app.state.limiter = limiter

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting error handler
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            status_code = getattr(locals().get("response", None), "status_code", 500)

            logger.info(
                "request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": request.client.host if request.client else None,
                },
            )
