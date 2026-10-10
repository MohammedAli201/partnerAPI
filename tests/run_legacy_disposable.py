"""Run legacy PostgreSQL regressions without touching an existing database.

Set CENTRAL_TEST_CLUSTER_URL to an explicitly disposable cluster, then run this
script using the established simulator Python environment.
"""
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def main():
    url=make_url(os.environ['CENTRAL_TEST_CLUSTER_URL'])
    engine=create_engine(url,isolation_level='AUTOCOMMIT')
    name='legacy_test_'+uuid4().hex
    with engine.connect() as db:
        db.exec_driver_sql(f'CREATE DATABASE {name}')
    try:
        environment={**os.environ,'TEST_DATABASE_URL':url.set(database=name).render_as_string(hide_password=False)}
        return subprocess.run([sys.executable,'-B','-m','pytest','tests/test_postgres_integration.py','-q','--tb=short'],
            cwd=Path(__file__).resolve().parents[1],env=environment).returncode
    finally:
        with engine.connect() as db:
            db.exec_driver_sql(f'DROP DATABASE {name} WITH (FORCE)')
        engine.dispose()


if __name__=='__main__':
    raise SystemExit(main())
