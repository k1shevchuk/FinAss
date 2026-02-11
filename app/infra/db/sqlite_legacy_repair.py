from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote

REV_0001 = "20260211_0001"
REV_0002 = "20260211_0002"


def _sqlite_path_from_dsn(dsn: str) -> Path | None:
    if not dsn.startswith("sqlite"):
        return None
    marker = ":///"
    if marker not in dsn:
        return None
    raw_path = dsn.split(marker, maxsplit=1)[1]
    if not raw_path or raw_path == ":memory:":
        return None
    path = Path(unquote(raw_path))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _get_tables(cursor: sqlite3.Cursor) -> set[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def _get_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _set_alembic_version(cursor: sqlite3.Cursor, revision: str) -> None:
    cursor.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    cursor.execute("DELETE FROM alembic_version")
    cursor.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (revision,))


def _read_alembic_version(cursor: sqlite3.Cursor) -> str | None:
    if not _table_exists(cursor, "alembic_version"):
        return None
    cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return ""
    return str(row[0] or "")


def _ensure_family_balance_columns(cursor: sqlite3.Cursor) -> None:
    if not _table_exists(cursor, "families"):
        return
    columns = _get_columns(cursor, "families")
    if "main_balance" not in columns:
        cursor.execute(
            "ALTER TABLE families ADD COLUMN main_balance NUMERIC(14,2) NOT NULL DEFAULT 0"
        )
    if "savings_balance" not in columns:
        cursor.execute(
            "ALTER TABLE families ADD COLUMN savings_balance NUMERIC(14,2) NOT NULL DEFAULT 0"
        )
    if "balances_updated_at_utc" not in columns:
        cursor.execute("ALTER TABLE families ADD COLUMN balances_updated_at_utc DATETIME")


def repair_sqlite_legacy_schema() -> None:
    db_dsn = os.getenv("DB_DSN", "")
    db_path = _sqlite_path_from_dsn(db_dsn)
    if db_path is None:
        return
    if not db_path.exists():
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        tables = _get_tables(cursor)
        core_tables = {"telegram_users", "families"}
        if not (tables & core_tables):
            return

        has_sql_primary_tables = {"expense_entries", "ledger_entries"}.issubset(tables)
        version = _read_alembic_version(cursor)

        if version in (None, ""):
            target_revision = REV_0002 if has_sql_primary_tables else REV_0001
            _set_alembic_version(cursor, target_revision)
            version = target_revision

        if version == REV_0001 and has_sql_primary_tables:
            _set_alembic_version(cursor, REV_0002)
            version = REV_0002

        if version == REV_0002:
            _ensure_family_balance_columns(cursor)

        conn.commit()


if __name__ == "__main__":
    repair_sqlite_legacy_schema()
