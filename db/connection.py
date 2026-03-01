"""SQLite connection and database initialization."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from db.schema import (
    ALL_CREATE,
    CUSTOMER_ADD_ADDRESS,
    CUSTOMER_ADD_DELIVERY_TYPE,
    CUSTOMER_ADD_TOTAL_PRICE,
)
from db.seed import MENU_ROWS, PLATFORM_ROWS

# Default DB path: project root / data / coffeepho.db
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "coffeepho.db"


def get_db_path() -> str:
    """Return the database file path (from env or default)."""
    return os.environ.get("DATABASE_PATH", str(_DEFAULT_DB_PATH))


@contextmanager
def get_connection(db_path: str | None = None):
    """Context manager yielding a SQLite connection (auto-commits, closes)."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Create tables and seed platform + menu if empty. Safe to call repeatedly."""
    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as conn:
        cur = conn.cursor()
        for sql in ALL_CREATE:
            cur.execute(sql)

        cur.execute("SELECT COUNT(*) FROM platform")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO platform (id, name, phone_number) VALUES (?, ?, ?)",
                PLATFORM_ROWS,
            )

        cur.execute("SELECT COUNT(*) FROM menu")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO menu (id, item_name, price) VALUES (?, ?, ?)",
                MENU_ROWS,
            )

        # Migration: add new customer columns if missing (existing DBs)
        for alter_sql in (
            CUSTOMER_ADD_DELIVERY_TYPE,
            CUSTOMER_ADD_ADDRESS,
            CUSTOMER_ADD_TOTAL_PRICE,
        ):
            try:
                cur.execute(alter_sql)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise
