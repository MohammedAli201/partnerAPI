import psycopg

dsn = "postgresql://postgres:postgres123@127.0.0.1:5432/partner_api"

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
        print(cur.fetchone())
