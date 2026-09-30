# Partner Payout API

A FastAPI backend prototype for accepting partner payout requests, reserving balances and assigning work to external executors. PostgreSQL stores payout state, reservations and processing queues.

## Explore the implementation

| Area | Implementation |
| --- | --- |
| Partner authentication | `security.py` generates salted API-key hashes; `main.py` authenticates incoming requests |
| Payout creation | `/payouts-create` checks transaction identifiers and reserves partner funds |
| Concurrent work | `/internal/executor/claim` uses PostgreSQL row locks and `SKIP LOCKED` |
| Result reporting | `/internal/executor/report` accepts executor evidence |
| Operator interface | Admin and partner HTML views under `templates/` |

These are implemented mechanisms, not a claim of validated end-to-end payment safety. In particular, concurrency, crash recovery and duplicate-callback behaviour need integration testing before any operational use.

## Local setup

Use Python 3.12 and an isolated PostgreSQL database.

```bash
python -m venv .venv
# Activate .venv using the command for your shell.
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` to your local test database and generate separate random values for `SECRET_KEY`, `EXECUTOR_TOKEN` and `API_KEY_HASH_SECRET`. For example, `python -c "import secrets; print(secrets.token_urlsafe(48))"` creates one value; run it separately for each setting. Keep `.env` local.

`python init_db.py` creates the ORM-defined tables. The SQL in `main.py` also references database structures that are not fully represented by a versioned migration set, so this is not yet a one-command reproducible deployment. Review the schema before attempting the payout routes.

After configuring a compatible local schema, `uvicorn main:app --reload --host 127.0.0.1 --port 8000` starts the development server. Use synthetic records and a simulated executor only.

## Tests

```bash
python -m unittest discover -s tests -v
```

The offline suite checks API-key verification, tampering and malformed input. It requires only the Python standard library and does not contact a database or payment service. `test_connection.py` is a separate, explicitly invoked database connectivity check, not a business-rule test.

## Deployment and configuration

`Dockerfile` and `.github/workflows/fly-deploy.yml` describe the existing Fly deployment. Runtime secrets belong in the hosting environment. `COOKIE_SECURE` must be true for an HTTPS deployment. Removing local credentials from source does not rotate values already exposed in Git history; operators must replace and revoke those values separately.

## Project status

Integration prototype. The repository does not establish regulatory approval, live service availability, complete migrations, or production readiness. Legacy commented copies of code and generated Python environments are excluded from the maintained source tree.
