"""基于不可变发布版本快照的封闭计算与最短路径（Dijkstra）。"""
import heapq
from datetime import datetime

from .timeutil import union_intervals


def load_version(conn, version_id: int) -> dict | None:
    """读取一个发布版本的完整快照。"""
    version = conn.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
    if version is None:
        return None
    locations = conn.execute(
        "SELECT * FROM version_locations WHERE version_id = ?", (version_id,)
    ).fetchall()
    passages = conn.execute(
        "SELECT * FROM version_passages WHERE version_id = ?", (version_id,)
    ).fetchall()
    announcements = conn.execute(
        "SELECT * FROM version_announcements WHERE version_id = ?", (version_id,)
    ).fetchall()
    ap_rows = conn.execute(
        "SELECT aid, passage_pid FROM version_announcement_passages WHERE version_id = ?",
        (version_id,),
    ).fetchall()

    # 每条通道在该版本下的生效公告时间轴（重叠区间先取并集）
    a_by_id = {a["aid"]: a for a in announcements}
    raw: dict[int, list[tuple[float, float, int]]] = {}
    for row in ap_rows:
        a = a_by_id.get(row["aid"])
        if a is None:
            continue
        raw.setdefault(row["passage_pid"], []).append((
            datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")).timestamp(),
            datetime.fromisoformat(a["end_utc"].replace("Z", "+00:00")).timestamp(),
            row["aid"],
        ))

    closure_details: dict[int, list[dict]] = {}
    for pid, entries in raw.items():
        merged = union_intervals([(s, e) for s, e, _ in entries])
        closure_details[pid] = [
            {
                "start": s,
                "end": e,
                "announcement_ids": sorted({
                    aid for s2, e2, aid in entries if s2 < e and e2 > s
                }),
            }
            for s, e in merged
        ]

    return {
        "id": version["id"],
        "note": version["note"],
        "published_at": version["published_at"],
        "locations": locations,
        "passages": passages,
        "announcements": announcements,
        "closure_details": closure_details,
    }


def blocked_announcements(version: dict, pid: int, travel_ts: float) -> list[int]:
    """travel_ts 命中该通道并集封闭区间时返回生效公告 id（左闭右开）。"""
    for seg in version["closure_details"].get(pid, []):
        if seg["start"] <= travel_ts < seg["end"]:
            return seg["announcement_ids"]
    return []


def shortest_path(version: dict, origin: str, destination: str,
                  wheelchair: bool, travel_dt: datetime) -> dict | None:
    """在版本快照上计算可行最短路径；不可达返回 None。"""
    nodes = {r["code"] for r in version["locations"]}
    if origin not in nodes or destination not in nodes:
        return None

    travel_ts = travel_dt.timestamp()
    usable = []
    for p in version["passages"]:
        if wheelchair and not p["wheelchair"]:
            continue
        if blocked_announcements(version, p["pid"], travel_ts):
            continue
        usable.append(p)

    if origin == destination:
        return {"distance_m": 0.0, "path": [], "nodes": [origin]}

    adj: dict[str, list] = {}
    for p in usable:
        adj.setdefault(p["from_location"], []).append(p)

    dist = {origin: 0.0}
    prev: dict[str, object] = {}
    heap = [(0.0, origin)]
    done = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == destination:
            break
        for p in adj.get(u, []):
            v = p["to_location"]
            nd = d + p["length_m"]
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = p
                heapq.heappush(heap, (nd, v))

    if destination not in dist:
        return None

    edge_chain = []
    cur = destination
    while cur != origin:
        p = prev[cur]
        edge_chain.append(p)
        cur = p["from_location"]
    edge_chain.reverse()
    return {
        "distance_m": dist[destination],
        "path": [
            {
                "seq": i + 1,
                "passage_code": p["code"],
                "passage_name": p["name"],
                "from": p["from_location"],
                "to": p["to_location"],
                "length_m": p["length_m"],
                "wheelchair": bool(p["wheelchair"]),
            }
            for i, p in enumerate(edge_chain)
        ],
        "nodes": [origin] + [p["to_location"] for p in edge_chain],
    }
