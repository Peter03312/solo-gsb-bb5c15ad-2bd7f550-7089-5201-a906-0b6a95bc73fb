"""SQLite 连接与事务工具。

所有查询在一次事务内固定 version_id，保证并发发布不会让一次查询混用版本。
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "venue.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

MAX_LOCK_RETRIES = 50
LOCK_RETRY_INTERVAL = 0.05


def get_db_path() -> Path:
    import os

    return Path(os.environ.get("DB_PATH", DB_PATH))


def connect() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def tx(immediate: bool = False):
    """事务上下文，对写-写锁冲突做有限次重试。

    isolation_level=None 时 SQL 层的 BEGIN 才真正生效；
    immediate=True 使用 BEGIN IMMEDIATE 立刻取得保留锁，
    用于发布、路线查询等写事务，串行化版本与指引编号，
    使并发发布不可能让一次查询读到混用的版本。
    """
    attempt = 0
    while True:
        conn = connect()
        try:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            break
        except sqlite3.OperationalError as exc:
            conn.close()
            if "database is locked" in str(exc) and attempt < MAX_LOCK_RETRIES:
                attempt += 1
                time.sleep(LOCK_RETRY_INTERVAL)
                continue
            raise
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # 持久属性，仅需设置一次
    finally:
        conn.close()
    with tx(immediate=True) as c:
        c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
