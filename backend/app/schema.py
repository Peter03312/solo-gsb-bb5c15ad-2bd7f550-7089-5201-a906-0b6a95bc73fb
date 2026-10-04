import json
import os
from datetime import datetime, timedelta, timezone

from .db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS passages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    from_location  TEXT NOT NULL REFERENCES locations(code),
    to_location    TEXT NOT NULL REFERENCES locations(code),
    length_m       REAL NOT NULL CHECK(length_m > 0),
    wheelchair     INTEGER NOT NULL CHECK(wheelchair IN (0, 1)),
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    start_utc   TEXT NOT NULL,
    end_utc     TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1)),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcement_passages (
    announcement_id INTEGER NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    passage_id      INTEGER NOT NULL REFERENCES passages(id),
    PRIMARY KEY (announcement_id, passage_id)
);

CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    note        TEXT NOT NULL,
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_locations (
    version_id INTEGER NOT NULL REFERENCES versions(id),
    code       TEXT NOT NULL,
    name       TEXT NOT NULL,
    PRIMARY KEY (version_id, code)
);

CREATE TABLE IF NOT EXISTS version_passages (
    version_id     INTEGER NOT NULL REFERENCES versions(id),
    pid            INTEGER NOT NULL,
    code           TEXT NOT NULL,
    name           TEXT NOT NULL,
    from_location  TEXT NOT NULL,
    to_location    TEXT NOT NULL,
    length_m       REAL NOT NULL,
    wheelchair     INTEGER NOT NULL,
    PRIMARY KEY (version_id, pid)
);

CREATE TABLE IF NOT EXISTS version_announcements (
    version_id INTEGER NOT NULL REFERENCES versions(id),
    aid        INTEGER NOT NULL,
    title      TEXT NOT NULL,
    start_utc  TEXT NOT NULL,
    end_utc    TEXT NOT NULL,
    PRIMARY KEY (version_id, aid)
);

CREATE TABLE IF NOT EXISTS version_announcement_passages (
    version_id      INTEGER NOT NULL,
    aid             INTEGER NOT NULL,
    passage_pid     INTEGER NOT NULL,
    PRIMARY KEY (version_id, aid, passage_pid)
);

CREATE TABLE IF NOT EXISTS guidance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id   INTEGER NOT NULL,
    origin       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    travel_utc   TEXT NOT NULL,
    wheelchair   INTEGER NOT NULL,
    distance_m   REAL NOT NULL,
    path_json    TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
"""


def init_db(path: str | None = None) -> None:
    conn = get_conn(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        empty = conn.execute("SELECT COUNT(*) AS c FROM locations").fetchone()["c"] == 0
        if empty and os.environ.get("SEED_DEMO", "1") != "0":
            _seed_demo(conn)
            conn.commit()
    finally:
        conn.close()


def _seed_demo(conn) -> None:
    """写入演示场馆数据并立即发布版本 1。

    以"今天"为封闭日（运行容器当天的 08:00-18:00，Asia/Shanghai），
    两条重叠公告演示左闭右开区间取并集：[08:00,12:00) ∪ [11:30,18:00)。
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tz = timezone(timedelta(hours=8))
    day = datetime.now(tz).date()
    s1 = datetime(day.year, day.month, day.day, 8, 0, tzinfo=tz).astimezone(timezone.utc)
    e1 = s1 + timedelta(hours=4)          # 12:00
    s2 = s1 + timedelta(hours=3, minutes=30)  # 11:30
    e2 = s1 + timedelta(hours=10)         # 18:00

    locations = [
        ("EAST", "东门"),
        ("WEST", "西门"),
        ("PLAZA", "中心广场"),
        ("HALL", "体育馆"),
        ("GATE3", "3号无障碍门"),
    ]
    for code, name in locations:
        conn.execute(
            "INSERT INTO locations(code, name, created_at) VALUES (?,?,?)",
            (code, name, now),
        )

    # (code, 名称, 起点, 终点, 米, 轮椅)
    passages = [
        ("E-P", "东门主道", "EAST", "PLAZA", 120, 1),
        ("P-E", "东门主道反向", "PLAZA", "EAST", 120, 1),
        ("W-P", "西门步道", "WEST", "PLAZA", 200, 0),
        ("P-W", "西门步道反向", "PLAZA", "WEST", 200, 0),
        ("W-P-A", "西门无障碍坡道", "WEST", "PLAZA", 240, 1),
        ("P-W-A", "西门无障碍坡道反向", "PLAZA", "WEST", 240, 1),
        ("P-H", "广场至体育馆", "PLAZA", "HALL", 80, 1),
        ("H-P", "体育馆至广场", "HALL", "PLAZA", 80, 1),
        ("E-G3", "东门至3号门连廊", "EAST", "GATE3", 150, 1),
        ("G3-E", "3号门至东门连廊", "GATE3", "EAST", 150, 1),
        ("G3-H", "3号门至体育馆直梯", "GATE3", "HALL", 100, 1),
        ("H-G3", "体育馆至3号门直梯", "HALL", "GATE3", 100, 1),
        ("W-H", "西门至体育馆小路", "WEST", "HALL", 170, 0),
        ("H-W", "体育馆至西门小路", "HALL", "WEST", 170, 0),
    ]
    pid = {}
    for code, name, a, b, length, wc in passages:
        cur = conn.execute(
            "INSERT INTO passages(code, name, from_location, to_location, length_m, wheelchair, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (code, name, a, b, length, wc, now),
        )
        pid[code] = cur.lastrowid

    a1 = conn.execute(
        "INSERT INTO announcements(title, start_utc, end_utc, revoked, created_at) VALUES (?,?,?,?,?)",
        ("东门主道上午临时封闭", s1.strftime("%Y-%m-%dT%H:%M:%SZ"), e1.strftime("%Y-%m-%dT%H:%M:%SZ"), 0, now),
    ).lastrowid
    a2 = conn.execute(
        "INSERT INTO announcements(title, start_utc, end_utc, revoked, created_at) VALUES (?,?,?,?,?)",
        ("东门主道下午施工封闭", s2.strftime("%Y-%m-%dT%H:%M:%SZ"), e2.strftime("%Y-%m-%dT%H:%M:%SZ"), 0, now),
    ).lastrowid
    for aid in (a1, a2):
        for code in ("E-P", "P-E"):
            conn.execute(
                "INSERT INTO announcement_passages(announcement_id, passage_id) VALUES (?,?)",
                (aid, pid[code]),
            )

    _publish(conn, note="初始演示数据（含东门主道 08:00-18:00 并集封闭）")


def _publish(conn, note: str) -> int:
    """把当前草稿整体快照为一个新版本（同一事务内调用）。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    vid = conn.execute(
        "INSERT INTO versions(note, published_at) VALUES (?,?)", (note, now)
    ).lastrowid
    conn.execute(
        "INSERT INTO version_locations(version_id, code, name) SELECT ?, code, name FROM locations",
        (vid,),
    )
    conn.execute(
        "INSERT INTO version_passages(version_id, pid, code, name, from_location, to_location, length_m, wheelchair)"
        " SELECT ?, id, code, name, from_location, to_location, length_m, wheelchair FROM passages",
        (vid,),
    )
    conn.execute(
        "INSERT INTO version_announcements(version_id, aid, title, start_utc, end_utc)"
        " SELECT ?, id, title, start_utc, end_utc FROM announcements WHERE revoked = 0",
        (vid,),
    )
    conn.execute(
        "INSERT INTO version_announcement_passages(version_id, aid, passage_pid)"
        " SELECT ?, ap.announcement_id, ap.passage_id"
        " FROM announcement_passages ap JOIN announcements a ON a.id = ap.announcement_id"
        " WHERE a.revoked = 0",
        (vid,),
    )
    return vid
