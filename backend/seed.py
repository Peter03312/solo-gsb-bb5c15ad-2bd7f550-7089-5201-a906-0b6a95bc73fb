"""一键初始化：建表 + 演示数据 + 发布 v1。幂等：已有地点数据时跳过种子。

演示公告时间以「今天 08:00–20:00（+08:00）」为基准生成，
便于在任意日期启动后立即验证「出行时刻落在封闭区间内」的行为。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import init_schema, tx
from app.timeutil import to_utc_iso

CST = timezone(timedelta(hours=8))


def at(hour: int, minute: int = 0, day_offset: int = 0) -> str:
    """返回归一化的 UTC ISO8601（与 API 写入路径一致，保证可按字符串比较）。"""
    today = datetime.now(CST).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc_iso(today + timedelta(days=day_offset, hours=hour, minutes=minute))


def seed() -> bool:
    init_schema()
    with tx() as conn:
        if conn.execute("SELECT COUNT(*) c FROM location").fetchone()["c"]:
            return False

        locations = [
            ("EAST", "东门"),
            ("NORTH", "北门"),
            ("ATR", "中庭"),
            ("HALL", "多功能厅"),
            ("STAIR", "台阶入口"),
            ("RAMP", "西侧无障碍坡道"),
        ]
        ids: dict[str, int] = {}
        for code, name in locations:
            cur = conn.execute("INSERT INTO location(code, name) VALUES(?, ?)", (code, name))
            ids[code] = cur.lastrowid

        # (编号, 起, 终, 长度米, 轮椅可通行, 备注)
        edges = [
            ("E-A", "EAST", "ATR", 120, 1, "东门平路至中庭"),
            ("A-E", "ATR", "EAST", 120, 1, "中庭返东门"),
            ("N-A", "NORTH", "ATR", 80, 1, "北门至中庭"),
            ("A-N", "ATR", "NORTH", 80, 1, "中庭返北门"),
            ("A-H", "ATR", "HALL", 60, 1, "中庭至多功能厅（平层通道）"),
            ("H-A", "HALL", "ATR", 60, 1, "多功能厅返中庭"),
            ("A-S", "ATR", "STAIR", 50, 0, "中庭至台阶入口（有台阶，轮椅不可通行）"),
            ("S-H", "STAIR", "HALL", 30, 0, "台阶入口至多功能厅（轮椅不可通行）"),
            ("H-S", "HALL", "STAIR", 30, 0, "多功能厅返台阶（轮椅不可通行）"),
            ("R-H", "RAMP", "HALL", 90, 1, "西侧无障碍坡道直达多功能厅"),
            ("H-R", "HALL", "RAMP", 90, 1, "多功能厅返坡道"),
            ("E-N", "EAST", "NORTH", 150, 1, "东门外环至北门"),
            ("N-R", "NORTH", "RAMP", 110, 1, "北门至西侧坡道"),
            ("R-N", "RAMP", "NORTH", 110, 1, "坡道返北门"),
        ]
        eids: dict[str, int] = {}
        for code, fr, to, length, wc, note in edges:
            cur = conn.execute(
                "INSERT INTO edge(code, from_loc, to_loc, length_m, wheelchair, note) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (code, ids[fr], ids[to], length, wc, note),
            )
            eids[code] = cur.lastrowid

        # 公告：左闭右开；前两条同边重叠演示并集；
        # 白天效果：步行可经台阶绕行，轮椅必须绕外环（北门→坡道→多功能厅）
        announcements = [
            ("中庭平层通道临时封闭（设备进场）", "A-H", at(9), at(13)),
            ("多功能厅通道封闭（布展延时，与上一条重叠取并集）", "A-H", at(12), at(20)),
            ("中庭东门方向临时封闭（上午）", "E-A", at(8, 30), at(12)),
            ("西侧无障碍坡道封闭（坡道检修，下午恢复）", "R-H", at(12), at(18)),
        ]
        for title, ecode, s, e in announcements:
            conn.execute(
                "INSERT INTO announcement(title, edge_id, start_ts, end_ts) VALUES(?, ?, ?, ?)",
                (title, eids[ecode], s, e),
            )

        # 发布 v1 快照
        cur = conn.execute("INSERT INTO version(note) VALUES(?)", ("初始化发布",))
        vid = cur.lastrowid
        anns = conn.execute("SELECT id, edge_id FROM announcement WHERE withdrawn=0").fetchall()
        for a in anns:
            row = conn.execute("SELECT * FROM announcement WHERE id=?", (a["id"],)).fetchone()
            conn.execute(
                "INSERT INTO version_announcement"
                "(version_id, announcement_id, title, edge_id, start_ts, end_ts) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (vid, row["id"], row["title"], row["edge_id"], row["start_ts"], row["end_ts"]),
            )
        conn.execute(
            "INSERT OR IGNORE INTO version_closure(version_id, edge_id) "
            "SELECT ?, edge_id FROM announcement WHERE withdrawn=0",
            (vid,),
        )
        return True


if __name__ == "__main__":
    created = seed()
    if created:
        print("✅ 已初始化数据库并写入演示数据，发布版本 v1")
    else:
        print("ℹ️  数据库已有地点数据，跳过种子")
