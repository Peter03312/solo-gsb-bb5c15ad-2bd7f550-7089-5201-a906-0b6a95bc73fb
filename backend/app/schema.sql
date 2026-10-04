-- 场馆临时封路无障碍通行指引 数据库结构
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 地点
CREATE TABLE IF NOT EXISTS location (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 定向通道：length_m > 0；wheelchair 表示轮椅是否可通行
CREATE TABLE IF NOT EXISTS edge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    from_loc    INTEGER NOT NULL REFERENCES location(id),
    to_loc      INTEGER NOT NULL REFERENCES location(id),
    length_m    REAL NOT NULL CHECK (length_m > 0),
    wheelchair  INTEGER NOT NULL CHECK (wheelchair IN (0, 1)),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (from_loc <> to_loc)
);

-- 封闭公告草稿（运营维护，可撤回；发布后被快照进 version_announcement）
CREATE TABLE IF NOT EXISTS announcement (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    edge_id     INTEGER NOT NULL REFERENCES edge(id),
    start_ts    TEXT NOT NULL,              -- UTC ISO8601，含时区偏移，区间 [start, end)
    end_ts      TEXT NOT NULL,
    withdrawn   INTEGER NOT NULL DEFAULT 0 CHECK (withdrawn IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 发布版本：每次发布生成一条不可变快照
CREATE TABLE IF NOT EXISTS version (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    published_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    note        TEXT NOT NULL DEFAULT ''
);

-- 版本内当时生效（未撤回）的公告快照
CREATE TABLE IF NOT EXISTS version_announcement (
    version_id     INTEGER NOT NULL REFERENCES version(id),
    announcement_id INTEGER NOT NULL REFERENCES announcement(id),
    title          TEXT NOT NULL,
    edge_id        INTEGER NOT NULL,
    start_ts       TEXT NOT NULL,
    end_ts         TEXT NOT NULL,
    PRIMARY KEY (version_id, announcement_id)
);

-- 版本内被封闭边（并集去重）的快照，查询时再按出行时刻过滤
CREATE TABLE IF NOT EXISTS version_closure (
    version_id  INTEGER NOT NULL REFERENCES version(id),
    edge_id     INTEGER NOT NULL REFERENCES edge(id),
    PRIMARY KEY (version_id, edge_id)
);

-- 访客指引：与计算时所用发布版本永久绑定
CREATE TABLE IF NOT EXISTS guidance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guidance_no TEXT NOT NULL UNIQUE,       -- G-000001
    version_id  INTEGER NOT NULL REFERENCES version(id),
    origin_id   INTEGER NOT NULL,
    dest_id     INTEGER NOT NULL,
    travel_ts   TEXT NOT NULL,
    wheelchair  INTEGER NOT NULL,
    distance_m  REAL NOT NULL,
    path_json   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edge_from ON edge(from_loc);
CREATE INDEX IF NOT EXISTS idx_ann_edge ON announcement(edge_id);
CREATE INDEX IF NOT EXISTS idx_va_version ON version_announcement(version_id);
CREATE INDEX IF NOT EXISTS idx_vc_version ON version_closure(version_id);
CREATE INDEX IF NOT EXISTS idx_guidance_version ON guidance(version_id);
