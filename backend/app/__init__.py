"""场馆临时封路无障碍通行指引 —— Flask API。

版本模型：
  - 运营维护公告草稿（可撤回）；POST /api/publish 生成一条不可变版本快照；
  - 访客查询在单事务内先固定最新已发布版本，再按出行时刻过滤该版本中生效的公告；
  - 公告区间左闭右开 [start, end)，多条重叠公告对边集取并集；
  - 撤回仅影响之后的发布与查询，既有版本/指引不变。
"""
from __future__ import annotations

import heapq
import json
import math
import sqlite3

from flask import Flask, jsonify, request

from .db import connect, init_schema, tx
from .errors import ApiError
from .timeutil import parse_tz, to_utc_iso, validate_window

app = Flask(__name__)


# --------------------------------------------------------------------------- 基础

@app.errorhandler(ApiError)
def handle_api_error(err: ApiError):
    return jsonify(err.to_dict()), err.status


@app.errorhandler(404)
def handle_404(_):
    return jsonify({"error": {"code": "not_found", "message": "资源不存在"}}), 404


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "请求体必须是 JSON 对象")
    return data


def require_str(data: dict, key: str, label: str) -> str:
    val = data.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ApiError(400, f"{label} 必填")
    return val.strip()


def parse_bool(data: dict, key: str, label: str, default: bool | None = None) -> int:
    val = data.get(key, default)
    if val is None:
        raise ApiError(400, f"{label} 必填")
    if isinstance(val, bool):
        return int(val)
    raise ApiError(400, f"{label} 必须为布尔值 true/false")


# --------------------------------------------------------------------------- 序列化

def loc_json(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "code": r["code"], "name": r["name"]}


def edge_json(conn, r: sqlite3.Row) -> dict:
    fr = conn.execute("SELECT code, name FROM location WHERE id=?", (r["from_loc"],)).fetchone()
    to = conn.execute("SELECT code, name FROM location WHERE id=?", (r["to_loc"],)).fetchone()
    return {
        "id": r["id"],
        "code": r["code"],
        "from": {"id": r["from_loc"], "code": fr["code"], "name": fr["name"]},
        "to": {"id": r["to_loc"], "code": to["code"], "name": to["name"]},
        "length_m": r["length_m"],
        "wheelchair": bool(r["wheelchair"]),
        "note": r["note"],
    }


def ann_json(r: sqlite3.Row, edge: sqlite3.Row | None = None) -> dict:
    return {
        "id": r["id"],
        "title": r["title"],
        "edge_id": r["edge_id"],
        "edge_code": edge["ecode"] if edge is not None else None,
        "from_code": edge["fr_code"] if edge is not None else None,
        "to_code": edge["to_code"] if edge is not None else None,
        "start_ts": r["start_ts"],
        "end_ts": r["end_ts"],
        "withdrawn": bool(r["withdrawn"]),
        "created_at": r["created_at"],
    }


# --------------------------------------------------------------------------- 只读资源

@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/locations")
def list_locations():
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM location ORDER BY id").fetchall()
        return jsonify([loc_json(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/edges")
def list_edges():
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM edge ORDER BY id").fetchall()
        return jsonify([edge_json(conn, r) for r in rows])
    finally:
        conn.close()


@app.get("/api/announcements")
def list_announcements():
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT a.*, e.code AS ecode, lf.code AS fr_code, lt.code AS to_code
                 FROM announcement a
                 JOIN edge e ON e.id = a.edge_id
                 JOIN location lf ON lf.id = e.from_loc
                 JOIN location lt ON lt.id = e.to_loc
             ORDER BY a.id DESC"""
        ).fetchall()
        return jsonify([ann_json(r, r) for r in rows])
    finally:
        conn.close()


@app.get("/api/versions")
def list_versions():
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM version ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            vc = conn.execute(
                "SELECT COUNT(*) c FROM version_closure WHERE version_id=?", (r["id"],)
            ).fetchone()["c"]
            va = conn.execute(
                "SELECT COUNT(*) c FROM version_announcement WHERE version_id=?", (r["id"],)
            ).fetchone()["c"]
            guides = conn.execute(
                "SELECT COUNT(*) c FROM guidance WHERE version_id=?", (r["id"],)
            ).fetchone()["c"]
            out.append({
                "version": r["id"],
                "published_at": r["published_at"],
                "note": r["note"],
                "announcement_count": va,
                "closed_edge_count": vc,
                "guidance_count": guides,
            })
        return jsonify(out)
    finally:
        conn.close()


# --------------------------------------------------------------------------- 运营维护

@app.post("/api/locations")
def create_location():
    data = body()
    code = require_str(data, "code", "地点编号")
    name = require_str(data, "name", "地点名称")
    with tx(immediate=True) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO location(code, name) VALUES(?, ?)", (code, name)
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, f"地点编号 {code} 已存在")
        row = conn.execute("SELECT * FROM location WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(loc_json(row)), 201


@app.post("/api/edges")
def create_edge():
    data = body()
    code = require_str(data, "code", "通道编号")
    from_code = require_str(data, "from_code", "起点编号")
    to_code = require_str(data, "to_code", "终点编号")
    wheelchair = parse_bool(data, "wheelchair", "轮椅通行属性")
    note = str(data.get("note") or "").strip()

    length = data.get("length_m")
    if isinstance(length, bool) or not isinstance(length, (int, float)):
        raise ApiError(400, "通道长度 length_m 必填且必须为数字")
    length = float(length)
    if not math.isfinite(length) or length <= 0:
        raise ApiError(422, "通道长度必须为正数")

    with tx(immediate=True) as conn:
        fr = conn.execute("SELECT * FROM location WHERE code=?", (from_code,)).fetchone()
        if not fr:
            raise ApiError(404, f"未知起点：{from_code}")
        to = conn.execute("SELECT * FROM location WHERE code=?", (to_code,)).fetchone()
        if not to:
            raise ApiError(404, f"未知终点：{to_code}")
        if fr["id"] == to["id"]:
            raise ApiError(422, "定向通道的起点与终点不能相同")
        dup = conn.execute(
            "SELECT id FROM edge WHERE from_loc=? AND to_loc=?", (fr["id"], to["id"])
        ).fetchone()
        if dup:
            raise ApiError(409, f"{from_code} → {to_code} 的定向通道已存在")
        try:
            cur = conn.execute(
                "INSERT INTO edge(code, from_loc, to_loc, length_m, wheelchair, note) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (code, fr["id"], to["id"], length, wheelchair, note),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, f"通道编号 {code} 已存在")
        row = conn.execute("SELECT * FROM edge WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(edge_json(conn, row)), 201


@app.post("/api/announcements")
def create_announcement():
    data = body()
    title = require_str(data, "title", "公告标题")
    edge_id = data.get("edge_id")
    if not isinstance(edge_id, int) or isinstance(edge_id, bool):
        raise ApiError(400, "edge_id 必填且必须为整数")
    start = parse_tz(data.get("start_ts"), "起始时刻")
    end = parse_tz(data.get("end_ts"), "结束时刻")
    validate_window(start, end)
    start_iso, end_iso = to_utc_iso(start), to_utc_iso(end)

    with tx(immediate=True) as conn:
        edge = conn.execute("SELECT id FROM edge WHERE id=?", (edge_id,)).fetchone()
        if not edge:
            raise ApiError(404, f"未知通道：edge_id={edge_id}")
        cur = conn.execute(
            "INSERT INTO announcement(title, edge_id, start_ts, end_ts) VALUES(?, ?, ?, ?)",
            (title, edge_id, start_iso, end_iso),
        )
        row = conn.execute("SELECT * FROM announcement WHERE id=?", (cur.lastrowid,)).fetchone()
        joined = conn.execute(
            """SELECT a.*, e.code AS ecode, lf.code AS fr_code, lt.code AS to_code
                 FROM announcement a
                 JOIN edge e ON e.id = a.edge_id
                 JOIN location lf ON lf.id = e.from_loc
                 JOIN location lt ON lt.id = e.to_loc
                WHERE a.id=?""",
            (cur.lastrowid,),
        ).fetchone()
        return jsonify(ann_json(row, joined)), 201


@app.post("/api/announcements/<int:aid>/withdraw")
def withdraw_announcement(aid: int):
    """撤回公告：仅影响之后的发布/查询，历史版本快照与既有指引不变。"""
    with tx(immediate=True) as conn:
        row = conn.execute("SELECT * FROM announcement WHERE id=?", (aid,)).fetchone()
        if not row:
            raise ApiError(404, f"公告不存在：id={aid}")
        if row["withdrawn"]:
            raise ApiError(409, "该公告已撤回，无需重复操作")
        conn.execute("UPDATE announcement SET withdrawn=1 WHERE id=?", (aid,))
        return jsonify({"id": aid, "withdrawn": True})


# --------------------------------------------------------------------------- 发布

@app.post("/api/publish")
def publish():
    """把当前全部未撤回公告快照为一条不可变版本。

    BEGIN IMMEDIATE 串行化发布；查询在各自事务内固定 version_id，
    因此发布瞬间进行中的查询不会混用新旧版本。
    """
    note = str(body().get("note") or "").strip()
    with tx(immediate=True) as conn:
        anns = conn.execute(
            "SELECT * FROM announcement WHERE withdrawn=0"
        ).fetchall()
        cur = conn.execute("INSERT INTO version(note) VALUES(?)", (note,))
        version_id = cur.lastrowid
        for a in anns:
            conn.execute(
                "INSERT INTO version_announcement"
                "(version_id, announcement_id, title, edge_id, start_ts, end_ts) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (version_id, a["id"], a["title"], a["edge_id"], a["start_ts"], a["end_ts"]),
            )
        if anns:
            conn.execute(
                "INSERT OR IGNORE INTO version_closure(version_id, edge_id) "
                "SELECT ?, edge_id FROM announcement WHERE withdrawn=0",
                (version_id,),
            )
        closed = conn.execute(
            "SELECT COUNT(*) c FROM version_closure WHERE version_id=?", (version_id,)
        ).fetchone()["c"]
        return jsonify({
            "version": version_id,
            "note": note,
            "announcement_count": len(anns),
            "closed_edge_count": closed,
        }), 201


# --------------------------------------------------------------------------- 路线计算

def _active_blocked_edges(conn, version_id: int, travel_iso: str) -> set[int]:
    """该版本中、出行时刻落入某条公告左闭右开区间的边（重叠自动并集去重）。"""
    rows = conn.execute(
        "SELECT DISTINCT edge_id FROM version_announcement "
        "WHERE version_id=? AND start_ts <= ? AND ? < end_ts",
        (version_id, travel_iso, travel_iso),
    ).fetchall()
    return {r["edge_id"] for r in rows}


def _dijkstra(conn, origin_id: int, dest_id: int, blocked: set[int], wheelchair: bool):
    rows = conn.execute("SELECT * FROM edge").fetchall()
    adj: dict[int, list] = {}
    for e in rows:
        if e["id"] in blocked:
            continue
        if wheelchair and not e["wheelchair"]:
            continue
        adj.setdefault(e["from_loc"], []).append(e)

    dist = {origin_id: 0.0}
    prev: dict[int, tuple] = {}
    pq = [(0.0, origin_id)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue
        if u == dest_id:
            break
        for e in adj.get(u, []):
            nd = d + e["length_m"]
            if nd < dist.get(e["to_loc"], math.inf):
                dist[e["to_loc"]] = nd
                prev[e["to_loc"]] = (u, e)
                heapq.heappush(pq, (nd, e["to_loc"]))

    if dest_id not in dist:
        return None, None
    edges = []
    node = dest_id
    while node != origin_id:
        pnode, edge = prev[node]
        edges.append(edge)
        node = pnode
    edges.reverse()
    return edges, dist[dest_id]


@app.post("/api/route")
def compute_route():
    data = body()
    origin_code = require_str(data, "origin", "起点")
    dest_code = require_str(data, "destination", "终点")
    travel = parse_tz(data.get("travel_ts"), "出行时刻")
    wheelchair = parse_bool(data, "wheelchair", "是否使用轮椅")
    travel_iso = to_utc_iso(travel)

    # 单一事务：固定版本 → 过滤生效公告 → 寻路 → 落指引，全程不混用版本。
    # IMMEDIATE 立即取保留锁：与并发发布串行化，同时保证指引编号唯一连续。
    with tx(immediate=True) as conn:
        origin = conn.execute("SELECT * FROM location WHERE code=?", (origin_code,)).fetchone()
        if not origin:
            raise ApiError(404, f"未知起点：{origin_code}")
        dest = conn.execute("SELECT * FROM location WHERE code=?", (dest_code,)).fetchone()
        if not dest:
            raise ApiError(404, f"未知终点：{dest_code}")
        if origin["id"] == dest["id"]:
            raise ApiError(422, "起点与终点不能相同，无需路线指引")

        ver = conn.execute(
            "SELECT * FROM version ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if ver is None:
            raise ApiError(422, "尚无已发布版本，请运营人员先发布封闭公告版本")
        version_id = ver["id"]

        blocked = _active_blocked_edges(conn, version_id, travel_iso)
        edges, total = _dijkstra(conn, origin["id"], dest["id"], blocked, bool(wheelchair))
        if edges is None:
            scope = "（轮椅可达子图）" if wheelchair else ""
            raise ApiError(
                422,
                f"不可达：版本 v{version_id} 在该出行时刻，"
                f"{origin_code} → {dest_code} 无可行路径{scope}",
                code="unreachable",
            )

        loc_cache: dict[int, sqlite3.Row] = {}

        def loc(lid):
            if lid not in loc_cache:
                loc_cache[lid] = conn.execute(
                    "SELECT * FROM location WHERE id=?", (lid,)
                ).fetchone()
            return loc_cache[lid]

        path_nodes = [loc(origin["id"])]
        steps = []
        for i, e in enumerate(edges, 1):
            t = loc(e["to_loc"])
            path_nodes.append(t)
            steps.append({
                "seq": i,
                "edge_id": e["id"],
                "edge_code": e["code"],
                "from": {"code": loc(e["from_loc"])["code"], "name": loc(e["from_loc"])["name"]},
                "to": {"code": t["code"], "name": t["name"]},
                "length_m": round(e["length_m"], 3),
                "wheelchair": bool(e["wheelchair"]),
                "instruction": f"沿通道 {e['code']} 由「{loc(e['from_loc'])['name']}」"
                               f"前往「{t['name']}」，约 {e['length_m']:g} 米",
            })

        total = round(total, 3)
        path_json = json.dumps({
            "origin": {"code": origin["code"], "name": origin["name"]},
            "destination": {"code": dest["code"], "name": dest["name"]},
            "nodes": [{"code": n["code"], "name": n["name"]} for n in path_nodes],
            "steps": steps,
            "distance_m": total,
        }, ensure_ascii=False)

        next_id = (conn.execute("SELECT COALESCE(MAX(id), 0) + 1 n FROM guidance")
                   .fetchone()["n"])
        guidance_no = f"G-{next_id:06d}"
        conn.execute(
            "INSERT INTO guidance(guidance_no, version_id, origin_id, dest_id, travel_ts, "
            "wheelchair, distance_m, path_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (guidance_no, version_id, origin["id"], dest["id"], travel_iso,
             wheelchair, total, path_json),
        )

        active = conn.execute(
            "SELECT * FROM version_announcement "
            "WHERE version_id=? AND start_ts <= ? AND ? < end_ts ORDER BY edge_id, start_ts",
            (version_id, travel_iso, travel_iso),
        ).fetchall()

        return jsonify({
            "guidance_no": guidance_no,
            "version": version_id,
            "published_at": ver["published_at"],
            "origin": {"code": origin["code"], "name": origin["name"]},
            "destination": {"code": dest["code"], "name": dest["name"]},
            "travel_ts": travel_iso,
            "wheelchair": bool(wheelchair),
            "distance_m": total,
            "path": [n["code"] for n in path_nodes],
            "steps": steps,
            "closed_edges_at_travel_time": sorted(blocked),
            "active_announcements": [
                {"id": a["announcement_id"], "title": a["title"],
                 "edge_id": a["edge_id"], "start_ts": a["start_ts"], "end_ts": a["end_ts"]}
                for a in active
            ],
        }), 201


@app.get("/api/guidance/<guidance_no>")
def get_guidance(guidance_no: str):
    """凭指引编号查看原路线——按当时绑定的版本重放，不受后续发布/撤回影响。"""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM guidance WHERE guidance_no=?", (guidance_no.strip().upper(),)
        ).fetchone()
        if not row:
            raise ApiError(404, f"指引编号不存在：{guidance_no}")
        ver = conn.execute("SELECT * FROM version WHERE id=?", (row["version_id"],)).fetchone()
        data = json.loads(row["path_json"])
        return jsonify({
            "guidance_no": row["guidance_no"],
            "version": row["version_id"],
            "published_at": ver["published_at"],
            "origin": data["origin"],
            "destination": data["destination"],
            "travel_ts": row["travel_ts"],
            "wheelchair": bool(row["wheelchair"]),
            "distance_m": row["distance_m"],
            "path": [n["code"] for n in data["nodes"]],
            "steps": data["steps"],
            "archived": True,
        })
    finally:
        conn.close()


# --------------------------------------------------------------------------- 启动初始化

init_schema()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
