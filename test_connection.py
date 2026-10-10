"""Explicit local database connectivity check; safe to import without connecting."""
import os


def main():
    import psycopg
    from dotenv import load_dotenv

    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL before running this check.")
    # SQLAlchemy driver suffixes are not part of a libpq connection URI.
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            print("Database connection OK" if cur.fetchone() == (1,) else "Unexpected result")


if __name__ == "__main__":
    main()
