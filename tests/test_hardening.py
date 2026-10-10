from __future__ import annotations

import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi import APIRouter
from sqlalchemy import exc as sa_exc
from starlette.requests import Request


def load_main_module(monkeypatch):
    monkeypatch.setenv("SKIP_DB_BOOTSTRAP", "true")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/test_db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("EXECUTOR_TOKEN", "executor-token")
    monkeypatch.setenv("API_KEY_HASH_SECRET", "hash-secret")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("PARTNER_FEE", "0.60")

    for module_name in ["main", "database", "config", "auth_session", "routes_ui_auth", "middleware"]:
        sys.modules.pop(module_name, None)

    class LimiterStub:
        def limit(self, _rule):
            def decorator(func):
                return func
            return decorator

    sys.modules["middleware"] = types.SimpleNamespace(
        limiter=LimiterStub(),
        setup_middleware=lambda app: None,
    )
    sys.modules["auth_session"] = types.SimpleNamespace(
        require_role=lambda role: (lambda request=None: {"role": role, "username": "tester"}),
        hash_password=lambda password: f"hashed:{password}",
        get_session=lambda request=None: {"role": "admin", "username": "tester"},
    )
    sys.modules["routes_ui_auth"] = types.SimpleNamespace(router=APIRouter())

    return importlib.import_module("main")


def make_request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def endpoint_fn(func):
    return getattr(func, "__wrapped__", func)


def test_retired_executor_cannot_be_reenabled(monkeypatch):
    main=load_main_module(monkeypatch)
    for enabled in ('false','true'):
        monkeypatch.setenv('ENABLE_LEGACY_SIMULATOR_EXECUTOR',enabled)
        with pytest.raises(HTTPException) as caught:
            main.require_executor_token('executor-token')
        assert caught.value.status_code==410


def test_uuid_reference_is_stable(monkeypatch):
    main=load_main_module(monkeypatch)
    reference=str(uuid4())
    assert main.normalize_partner_tx_id(reference,{})==reference


def test_old_result_never_authorizes_money(monkeypatch):
    main=load_main_module(monkeypatch)
    with pytest.raises(HTTPException) as caught:
        main.executor_report(request=make_request(),body=None,db=None)
    assert caught.value.status_code==410
