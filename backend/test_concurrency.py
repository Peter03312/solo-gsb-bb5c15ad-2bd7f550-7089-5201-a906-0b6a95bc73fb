"""并发测试：多个发布者持续发布 + 大量查询并发执行，
验证每次查询的结果与所声明版本严格一致（不混用版本）。
"""
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected
from urllib import error, request

sys.path.insert(0, os.path.dirname(__file__))

# 构造测试库
DB = os.path.join(os.path.dirname(__file__), "data", "concurrency.db")
os.environ["DB_PATH"] = DB
for suffix in ("", "-wal", "-shm"):
    p = DB + suffix
    if os.path.exists(p):
        os.remove(p)

from app import app  # noqa: E402
from app.db import tx  # noqa: E402

CST = timezone(timedelta(hours=8))

# 基础数据：两条 A->C 路径
with tx() as conn:
    for code, name in [("A", "甲"), ("B", "乙"), ("C", "丙"), ("D", "丁")]:
        conn.execute("INSERT INTO location(code, name) VALUES(?, ?)", (code, name))
    ids = {r["code"]: r["id"] for r in
           conn.execute("SELECT * FROM location").fetchall()}
    for code, fr, to, length in [("AB", "A", "B", 10), ("BC", "B", "C", 10),
                                 ("AD", "A", "D", 100), ("DC", "D", "C", 100)]:
        conn.execute(
            "INSERT INTO edge(code, from_loc, to_loc, length_m, wheelchair) VALUES(?,?,?,?,1)",
            (code, ids[fr], ids[to], length))
    conn.execute("INSERT INTO version(note) VALUES(?)", ("v0",))

import http.server  # noqa: E402
import socketserver  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

server = make_server("127.0.0.1", 8765, app, threaded=True)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()
time.sleep(0.3)

BASE = "http://127.0.0.1:8765"


def call(method, path, payload=None, retries=3):
    for i in range(retries):
        try:
            data = json.dumps(payload).encode() if payload is not None else None
            req = request.Request(BASE + path, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except error.HTTPError as e:
            return e.code, json.loads(e.read())
        except (RemoteDisconnected, ConnectionError, TimeoutError):
            time.sleep(0.1 * (i + 1))
    raise RuntimeError(f"call failed: {method} {path}")


def today_at(h):
    return (datetime.now(CST).replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(hours=h)).isoformat()


edges = {e["code"]: e for e in call("GET", "/api/edges")[1]}

stop = False
errors = []
versions_seen = set()
lock = threading.Lock()


def publisher(n):
    """每位发布者交替 封闭 AB / 封闭 DC：先撤回自己上一条公告再发布，
    使每个版本快照中恰好只有一条生效公告。"""
    time.sleep(0.05)
    seq = 0
    last_ann = None
    while not stop:
        if last_ann is not None:
            code, payload = call("POST", f"/api/announcements/{last_ann}/withdraw")
            if code != 200:
                errors.append(f"withdraw {code} {payload}")
                return
        edge = "AB" if (n + seq) % 2 == 0 else "DC"
        code, payload = call("POST", "/api/announcements", {
            "title": f"pub{n}-{seq}",
            "edge_id": edges[edge]["id"],
            "start_ts": today_at(0),
            "end_ts": today_at(23),
        })
        if code != 201:
            errors.append(f"ann create {code} {payload}")
            return
        last_ann = payload["id"]
        code, payload = call("POST", "/api/publish", {"note": f"p{n}-{seq}"})
        if code != 201:
            errors.append(f"publish {code} {payload}")
            return
        with lock:
            versions_seen.add(payload["version"])
        seq += 1
        time.sleep(0.02)


def querier(n):
    """查询时刻为 12:00（所有公告都生效），校验响应内部自洽且与版本快照一致。"""
    count = 0
    while not stop:
        code, payload = call("POST", "/api/route", {
            "origin": "A", "destination": "C",
            "travel_ts": today_at(12), "wheelchair": False})
        if code not in (201, 422):
            errors.append(f"unexpected {code} {payload}")
            return
        if code == 201:
            v = payload["version"]
            # 该版本封闭边数为 0（仅 v1 基线）或 1（后续发布）
            blocked = payload["closed_edges_at_travel_time"]
            dist = payload["distance_m"]
            if v == 1:
                if blocked != [] or dist != 20:
                    errors.append(f"基线 v1 应为空封闭/距离20: {payload}")
            else:
                if len(blocked) != 1:
                    errors.append(f"v{v} 生效封闭边数应为 1，实际 {blocked}")
                if blocked == [edges["DC"]["id"]] and dist != 20:
                    errors.append(f"v{v} 封 DC 但距离 {dist} != 20")
                if blocked == [edges["AB"]["id"]] and dist != 200:
                    errors.append(f"v{v} 封 AB 但距离 {dist} != 200")
            # 指引重放必须得到同版本同距离
            g = call("GET", f"/api/guidance/{payload['guidance_no']}")[1]
            if g["version"] != v or g["distance_m"] != dist:
                errors.append(f"指引重放与当场结果不一致: {g}")
            count += 1
        time.sleep(0.005)
    qcount[n] = count


qcount = [0] * 6
pubs = [threading.Thread(target=publisher, args=(0,))]
qs = [threading.Thread(target=querier, args=(i,)) for i in range(6)]
for x in pubs + qs:
    x.start()

time.sleep(6)
stop = True
for x in pubs + qs:
    x.join(timeout=10)
server.shutdown()

print(f"发布版本数: {len(versions_seen)}（{min(versions_seen)}..{max(versions_seen)}）")
print(f"成功查询数: {sum(qcount)}，各查询线程: {qcount}")
if errors:
    print(f"\n❌ 发现 {len(errors)} 个错误：")
    for e in errors[:10]:
        print(" -", e)
    sys.exit(1)
print("\n✅ 并发期间所有查询均与单一版本严格一致，指引重放不变，无版本混用")
