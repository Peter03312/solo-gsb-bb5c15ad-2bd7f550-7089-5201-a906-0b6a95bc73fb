import json
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from .db import db, get_conn
from .errors import ApiError
from .routing import blocked_announcements, load_version, shortest_path
from .schema import _publish, init_db
from .timeutil import COMMON_TIMEZONES, parse_dt, utc_str

app = FastAPI(title="场馆临时封路无障碍通行指引")


@app.exception_handler(ApiError)
def _api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail()})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


@contextmanager
def immediate_tx():
    """立即事务：确保 版本选择→计算→指引落库 串行化，避免查询混用版本。"""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------- 模型

class LocationIn(BaseModel):
    code: str
    name: str

    @field_validator("code", "name")
    @classmethod
    def _nonempty(cls, v):
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()


class PassageIn(BaseModel):
    code: str
    name: str
    from_location: str
    to_location: str
    length_m: float
    wheelchair: bool

    @field_validator("code", "name", "from_location", "to_location")
    @classmethod
    def _nonempty(cls, v):
        if not v or not v.strip():
            raise ValueError("不能为空")
        return v.strip()

    @field_validator("length_m")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("通道长度必须为正数")
        return v


class AnnouncementIn(BaseModel):
    title: str
    start_time: str
    end_time: str
    passage_codes: list[str]

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        if not v or not v.strip():
            raise ValueError("公告标题不能为空")
        return v.strip()


class PublishIn(BaseModel):
    note: str | None = None


class RouteIn(BaseModel):
    origin: str
    destination: str
    travel_time: str
    wheelchair: bool

    @field_validator("origin", "destination")
    @classmethod
    def _nonempty(cls, v):
        if not v or not v.strip():
            raise ValueError("地点不能为空")
        return v.strip()


# ---------------------------------------------------------------- 基础

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/timezones")
def timezones():
    return COMMON_TIMEZONES


# ---------------------------------------------------------------- 运营：地点

@app.get("/api/locations")
def list_locations():
    with db() as conn:
        rows = conn.execute("SELECT code, name, created_at FROM locations ORDER BY code").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/locations", status_code=201)
def create_location(body: LocationIn):
    with db() as conn:
        exists = conn.execute("SELECT 1 FROM locations WHERE code = ?", (body.code,)).fetchone()
        if exists:
            raise HTTPException(409, detail={"code": "LOCATION_EXISTS", "message": f"地点编号 {body.code} 已存在"})
        now = utc_str(datetime.now(timezone.utc))
        conn.execute("INSERT INTO locations(code, name, created_at) VALUES (?,?,?)", (body.code, body.name, now))
    return {"code": body.code, "name": body.name, "message": "地点已保存（发布后对访客生效）"}


@app.delete("/api/locations/{code}", status_code=200)
def delete_location(code: str):
    with db() as conn:
        loc = conn.execute("SELECT 1 FROM locations WHERE code = ?", (code,)).fetchone()
        if not loc:
            raise HTTPException(404, detail={"code": "LOCATION_NOT_FOUND", "message": f"未知地点：{code}"})
        used = conn.execute(
            "SELECT 1 FROM passages WHERE from_location = ? OR to_location = ? LIMIT 1", (code, code)
        ).fetchone()
        if used:
            raise HTTPException(409, detail={"code": "LOCATION_IN_USE", "message": f"地点 {code} 仍被通道引用，请先调整通道"})
        conn.execute("DELETE FROM locations WHERE code = ?", (code,))
    return {"message": "地点已删除（发布后对访客生效）"}


# ---------------------------------------------------------------- 运营：通道

@app.get("/api/passages")
def list_passages():
    with db() as conn:
        rows = conn.execute(
            "SELECT code, name, from_location, to_location, length_m, wheelchair, created_at"
            " FROM passages ORDER BY code"
        ).fetchall()
    return [
        {"code": r["code"], "name": r["name"], "from_location": r["from_location"],
         "to_location": r["to_location"], "length_m": r["length_m"], "wheelchair": bool(r["wheelchair"])}
        for r in rows
    ]


@app.post("/api/passages", status_code=201)
def create_passage(body: PassageIn):
    with db() as conn:
        for code in (body.from_location, body.to_location):
            if not conn.execute("SELECT 1 FROM locations WHERE code = ?", (code,)).fetchone():
                raise HTTPException(400, detail={"code": "LOCATION_NOT_FOUND", "message": f"未知地点：{code}"})
        if conn.execute("SELECT 1 FROM passages WHERE code = ?", (body.code,)).fetchone():
            raise HTTPException(409, detail={"code": "PASSAGE_EXISTS", "message": f"通道编号 {body.code} 已存在"})
        now = utc_str(datetime.now(timezone.utc))
        conn.execute(
            "INSERT INTO passages(code, name, from_location, to_location, length_m, wheelchair, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (body.code, body.name, body.from_location, body.to_location, body.length_m, int(body.wheelchair), now),
        )
    return {"code": body.code, "message": "通道已保存（发布后对访客生效）"}


@app.delete("/api/passages/{code}")
def delete_passage(code: str):
    with db() as conn:
        row = conn.execute("SELECT id FROM passages WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "PASSAGE_NOT_FOUND", "message": f"未知通道：{code}"})
        used = conn.execute(
            "SELECT 1 FROM announcement_passages WHERE passage_id = ? LIMIT 1", (row["id"],)
        ).fetchone()
        if used:
            raise HTTPException(409, detail={"code": "PASSAGE_IN_USE", "message": f"通道 {code} 仍被公告引用，请先处理相关公告"})
        conn.execute("DELETE FROM passages WHERE id = ?", (row["id"],))
    return {"message": "通道已删除（发布后对访客生效）"}


# ---------------------------------------------------------------- 运营：公告

def _announcement_dicts(rows, conn):
    result = []
    for r in rows:
        pids = conn.execute(
            "SELECT passage_id FROM announcement_passages WHERE announcement_id = ?", (r["id"],)
        ).fetchall()
        codes = [
            conn.execute("SELECT code FROM passages WHERE id = ?", (p["passage_id"],)).fetchone()["code"]
            for p in pids
        ]
        result.append({
            "id": r["id"], "title": r["title"],
            "start_time_utc": r["start_utc"], "end_time_utc": r["end_utc"],
            "revoked": bool(r["revoked"]), "passage_codes": codes,
            "created_at": r["created_at"],
        })
    return result


@app.get("/api/announcements")
def list_announcements():
    with db() as conn:
        rows = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
        return _announcement_dicts(rows, conn)


@app.post("/api/announcements", status_code=201)
def create_announcement(body: AnnouncementIn):
    start = parse_dt(body.start_time, "封闭开始时间")
    end = parse_dt(body.end_time, "封闭结束时间")
    if end <= start:
        raise HTTPException(400, detail={"code": "INVALID_INTERVAL", "message": "封闭区间无效：结束时间必须晚于开始时间（区间左闭右开 [开始, 结束)）"})
    if not body.passage_codes:
        raise HTTPException(400, detail={"code": "EMPTY_PASSAGES", "message": "公告至少需要封闭一条通道"})

    with db() as conn:
        pids = []
        for code in body.passage_codes:
            row = conn.execute("SELECT id FROM passages WHERE code = ?", (code,)).fetchone()
            if not row:
                raise HTTPException(400, detail={"code": "PASSAGE_NOT_FOUND", "message": f"未知通道：{code}"})
            pids.append(row["id"])
        now = utc_str(datetime.now(timezone.utc))
        aid = conn.execute(
            "INSERT INTO announcements(title, start_utc, end_utc, revoked, created_at) VALUES (?,?,?,0,?)",
            (body.title, utc_str(start), utc_str(end), now),
        ).lastrowid
        for pid in set(pids):
            conn.execute(
                "INSERT INTO announcement_passages(announcement_id, passage_id) VALUES (?,?)", (aid, pid)
            )
    return {"id": aid, "message": "公告已保存（发布后对访客生效；多条重叠公告封闭区间自动取并集）"}


@app.post("/api/announcements/{aid}/revoke")
def revoke_announcement(aid: int):
    """撤回公告：立即整体快照发布新版本，只影响后续查询。"""
    with immediate_tx() as conn:
        row = conn.execute("SELECT * FROM announcements WHERE id = ?", (aid,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "ANNOUNCEMENT_NOT_FOUND", "message": f"未知公告：{aid}"})
        if row["revoked"]:
            raise HTTPException(409, detail={"code": "ALREADY_REVOKED", "message": f"公告 {aid} 已撤回"})
        conn.execute("UPDATE announcements SET revoked = 1 WHERE id = ?", (aid,))
        version_id = _publish(conn, note=f"撤回公告 #{aid}：{row['title']}")
    return {"id": aid, "version_id": version_id, "message": "公告已撤回并发布新版本；已生成的指引可凭编号查看原路线"}


# ---------------------------------------------------------------- 运营：发布与版本

@app.post("/api/publish")
def publish(body: PublishIn):
    note = (body.note or "").strip() or "运营发布"
    with immediate_tx() as conn:
        version_id = _publish(conn, note=note)
        n_a = conn.execute(
            "SELECT COUNT(*) AS c FROM version_announcements WHERE version_id = ?", (version_id,)
        ).fetchone()["c"]
    return {"version_id": version_id, "active_announcements": n_a, "message": f"已发布版本 #{version_id}"}


@app.get("/api/versions")
def list_versions():
    with db() as conn:
        rows = conn.execute(
            "SELECT v.id, v.note, v.published_at,"
            " (SELECT COUNT(*) FROM version_announcements va WHERE va.version_id = v.id) AS ann_count"
            " FROM versions v ORDER BY v.id"
        ).fetchall()
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM versions").fetchone()["m"]
    return [
        {"id": r["id"], "note": r["note"], "published_at": r["published_at"],
         "announcement_count": r["ann_count"], "is_latest": r["id"] == latest}
        for r in rows
    ]


@app.get("/api/versions/latest")
def latest_version():
    with db() as conn:
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM versions").fetchone()["m"]
        if not latest:
            raise HTTPException(409, detail={"code": "NO_PUBLISHED_VERSION", "message": "尚未发布任何版本，请运营人员先发布公告"})
    return version_detail(latest)


@app.get("/api/versions/{vid}")
def version_detail(vid: int):
    with db() as conn:
        version = load_version(conn, vid)
        if version is None:
            raise HTTPException(404, detail={"code": "VERSION_NOT_FOUND", "message": f"未知版本：{vid}"})
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM versions").fetchone()["m"]

    titles = {a["aid"]: a["title"] for a in version["announcements"]}
    pmap = {p["pid"]: p for p in version["passages"]}
    closures = []
    for pid, segs in version["closure_details"].items():
        p = pmap[pid]
        closures.append({
            "passage_code": p["code"],
            "passage_name": p["name"],
            "segments": [
                {
                    "start_utc": datetime.fromtimestamp(seg["start"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_utc": datetime.fromtimestamp(seg["end"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "announcement_ids": seg["announcement_ids"],
                    "announcement_titles": [titles[i] for i in seg["announcement_ids"] if i in titles],
                }
                for seg in segs
            ],
        })
    return {
        "id": version["id"],
        "note": version["note"],
        "published_at": version["published_at"],
        "is_latest": version["id"] == latest,
        "locations": [{"code": r["code"], "name": r["name"]} for r in version["locations"]],
        "passages": [
            {"pid": p["pid"], "code": p["code"], "name": p["name"], "from_location": p["from_location"],
             "to_location": p["to_location"], "length_m": p["length_m"], "wheelchair": bool(p["wheelchair"])}
            for p in version["passages"]
        ],
        "announcements": [
            {"id": a["aid"], "title": a["title"], "start_time_utc": a["start_utc"], "end_time_utc": a["end_utc"]}
            for a in version["announcements"]
        ],
        "closures": closures,
    }


# ---------------------------------------------------------------- 访客：路线查询

def _name_map(version):
    return {r["code"]: r["name"] for r in version["locations"]}


def _enrich_path(result, names):
    for step in result["path"]:
        step["from_name"] = names.get(step["from"], step["from"])
        step["to_name"] = names.get(step["to"], step["to"])
    result["node_names"] = [names.get(c, c) for c in result["nodes"]]
    return result


@app.post("/api/routes")
def query_route(body: RouteIn):
    travel = parse_dt(body.travel_time, "出行时刻")

    # 一次查询全程使用同一个版本快照（BEGIN IMMEDIATE 与发布事务互斥）
    with immediate_tx() as conn:
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM versions").fetchone()["m"]
        if not latest:
            raise HTTPException(409, detail={"code": "NO_PUBLISHED_VERSION", "message": "尚未发布任何版本，请运营人员先发布公告"})
        version = load_version(conn, latest)
        names = _name_map(version)

        if body.origin not in names:
            raise HTTPException(404, detail={"code": "UNKNOWN_ORIGIN", "message": f"未知起点地点：{body.origin}"})
        if body.destination not in names:
            raise HTTPException(404, detail={"code": "UNKNOWN_DESTINATION", "message": f"未知终点地点：{body.destination}"})

        result = shortest_path(version, body.origin, body.destination, body.wheelchair, travel)
        if result is None:
            reason = "当前时刻生效的封闭公告" if not body.wheelchair else "当前时刻生效的封闭公告或轮椅通行属性限制"
            raise HTTPException(404, detail={"code": "ROUTE_UNREACHABLE",
                                             "message": f"在版本 #{latest}、{utc_str(travel)} 时刻，{reason}导致无可达路线"})

        # 命中封闭的公告（用于提示，非路径组成部分）
        travel_ts = travel.timestamp()
        affected = []
        for p in version["passages"]:
            aids = blocked_announcements(version, p["pid"], travel_ts)
            for aid in aids:
                affected.append({"passage_code": p["code"], "announcement_id": aid})

        _enrich_path(result, names)
        now = utc_str(datetime.now(timezone.utc))
        gid = conn.execute(
            "INSERT INTO guidance(version_id, origin, destination, travel_utc, wheelchair, distance_m, path_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (latest, body.origin, body.destination, utc_str(travel), int(body.wheelchair),
             result["distance_m"], json.dumps(result, ensure_ascii=False), now),
        ).lastrowid

    return {
        "guidance_number": gid,
        "version_id": latest,
        "origin": body.origin, "origin_name": names[body.origin],
        "destination": body.destination, "destination_name": names[body.destination],
        "travel_time_utc": utc_str(travel),
        "wheelchair": body.wheelchair,
        "distance_m": result["distance_m"],
        "path": result["path"],
        "nodes": result["nodes"],
        "node_names": result["node_names"],
        "blocked_now": affected,
        "created_at": now,
    }


@app.get("/api/guidance/{gid}")
def get_guidance(gid: int):
    """凭指引编号查看原路线——始终返回当时计算并存储的快照。"""
    with db() as conn:
        row = conn.execute("SELECT * FROM guidance WHERE id = ?", (gid,)).fetchone()
        if not row:
            raise HTTPException(404, detail={"code": "GUIDANCE_NOT_FOUND", "message": f"未知指引编号：{gid}"})
        version = load_version(conn, row["version_id"])
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM versions").fetchone()["m"]

    path = json.loads(row["path_json"])
    return {
        "guidance_number": row["id"],
        "version_id": row["version_id"],
        "version_exists": version is not None,
        "is_latest_version": row["version_id"] == latest,
        "origin": row["origin"],
        "destination": row["destination"],
        "travel_time_utc": row["travel_utc"],
        "wheelchair": bool(row["wheelchair"]),
        "distance_m": row["distance_m"],
        "path": path.get("path", []),
        "nodes": path.get("nodes", []),
        "node_names": path.get("node_names", path.get("nodes", [])),
        "created_at": row["created_at"],
        "snapshot": True,
        "message": "此为该指引生成时的原始路线快照，不受后续公告撤回或新版本影响",
    }
