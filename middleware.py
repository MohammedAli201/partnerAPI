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
    default_limits=[], # Shared DB quotas enforce IP abuse and partner business limits
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
