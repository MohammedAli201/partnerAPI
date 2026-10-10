"""Minimal FastAPI app that includes existing UI routes and the new webhook router.

Run with: `uvicorn partnerCodeApi.app:app --reload`
"""
from fastapi import FastAPI

from routes_ui_auth import router as ui_auth_router
from routes_webhooks_payout import router as webhooks_router

app = FastAPI(title="PartnerCodeApi (minimal)")

app.include_router(ui_auth_router)
app.include_router(webhooks_router)
