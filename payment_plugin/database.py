"""Payment storage. Default = stdlib sqlite3 file store; Postgres is an
opt-in path (import psycopg2 lazily) selected when cfg.db_url starts with
"postgres". Call init_db(cfg) once at startup.

ponytail: the sqlite file store uses naive single-file locking — fine for one
bot process. For multi-process / high concurrency, point DATABASE_URL at
Postgres (same schema, utr UNIQUE enforces the reuse guard there too).
"""

import logging
from contextlib import contextmanager

log = logging.getLogger(__name__)

_backend = _dsn = None  # set by init_db


@contextmanager
def _conn():
    if _backend == "postgres":
        import psycopg2  # lazy: only imported when Postgres is actually selected
        c = psycopg2.connect(_dsn)
    else:
        import sqlite3
        c = sqlite3.connect(_dsn)
        c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()


def _q(sql):
    return sql if _backend == "postgres" else sql.replace("%s", "?")


def init_db(cfg):
    global _backend, _dsn
    if cfg.db_url.startswith("postgres"):
        _backend, _dsn = "postgres", cfg.db_url
    else:
        _backend, _dsn = "sqlite", cfg.db_path
    ddl = ("CREATE TABLE IF NOT EXISTS payments ("
           "order_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, amount REAL NOT NULL, "
           "status TEXT NOT NULL DEFAULT 'PENDING', utr TEXT UNIQUE, "
           "created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    if _backend == "postgres":
        ddl = ddl.replace("(datetime('now'))", "(now()::text)")
    with _conn() as c:
        c.cursor().execute(ddl)
    log.info(f"Storage initialized ({_backend})")


def insert_payment(order_id, user_id, amount):
    with _conn() as c:
        c.cursor().execute(_q("INSERT INTO payments (order_id, user_id, amount) VALUES (%s,%s,%s)"),
                           (order_id, user_id, amount))


def get_payment(order_id):
    with _conn() as c:
        cur = c.cursor(); cur.execute(_q("SELECT * FROM payments WHERE order_id=%s"), (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def claim_utr(order_id, utr):
    """Guard #4: bind utr to this PENDING order. Returns True only if a row was
    updated; the utr UNIQUE constraint rejects a utr already claimed elsewhere."""
    try:
        with _conn() as c:
            cur = c.cursor()
            cur.execute(_q("UPDATE payments SET status='SUCCESS', utr=%s "
                           "WHERE order_id=%s AND status='PENDING'"), (utr, order_id))
            return cur.rowcount > 0
    except Exception as e:  # IntegrityError (sqlite3 or psycopg2) = utr reused
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return False
        raise


def fail_payment(order_id):
    with _conn() as c:
        c.cursor().execute(_q("UPDATE payments SET status='FAILURE' "
                              "WHERE order_id=%s AND status='PENDING'"), (order_id,))


def admin_search(q):
    with _conn() as c:
        cur = c.cursor(); cur.execute(_q("SELECT * FROM payments WHERE order_id=%s OR utr=%s LIMIT 1"), (q, q))
        row = cur.fetchone()
        return dict(row) if row else None


def admin_recent(limit=10):
    with _conn() as c:
        cur = c.cursor(); cur.execute(_q("SELECT * FROM payments ORDER BY created_at DESC LIMIT %s"), (limit,))
        return [dict(r) for r in cur.fetchall()]
