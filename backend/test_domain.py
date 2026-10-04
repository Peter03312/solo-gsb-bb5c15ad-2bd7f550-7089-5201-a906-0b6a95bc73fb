"""端到端领域逻辑验证（标准库 + Flask test client）。"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ["DB_PATH"] = os.path.join(os.path.dirname(__file__), "data", "test.db")
DB = os.environ["DB_PATH"]
for suffix in ("", "-wal", "-shm"):
    p = DB + suffix
    if os.path.exists(p):
        os.remove(p)

sys.path.insert(0, os.path.dirname(__file__))
from app import app  # noqa: E402

CST = timezone(timedelta(hours=8))
client = app.test_client()
passed = []


def check(name, cond, detail=""):
    assert cond, f"FAIL {name}: {detail}"
    passed.append(name)


def at(h, m=0, d=0):
    today = datetime.now(CST).replace(hour=0, minute=0, second=0, microsecond=0)
    return (today + timedelta(days=d, hours=h, minutes=m)).isoformat()


# 重新初始化独立测试库
from app.db import init_schema  # noqa: E402
init_schema()

# --- 运营：建地点/通道/公告/发布 ---
r = client.post("/api/locations", json={"code": "A", "name": "甲"})
check("create loc", r.status_code == 201, r.status_code)
r = client.post("/api/locations", json={"code": "B", "name": "乙"})
r = client.post("/api/locations", json={"code": "C", "name": "丙"})
r = client.post("/api/locations", json={"code": "D", "name": "丁"})

# 重复地点编号 -> 409
r = client.post("/api/locations", json={"code": "A", "name": "重复"})
check("dup location 409", r.status_code == 409, r.status_code)

# 长度必须为正
r = client.post("/api/edges", json={
    "code": "AB", "from_code": "A", "to_code": "B", "length_m": 0, "wheelchair": True})
check("zero length 422", r.status_code == 422, r.json)
r = client.post("/api/edges", json={
    "code": "AB", "from_code": "A", "to_code": "B", "length_m": -5, "wheelchair": True})
check("negative length 422", r.status_code == 422, r.status_code)
r = client.post("/api/edges", json={
    "code": "AB", "from_code": "A", "to_code": "A", "length_m": 10, "wheelchair": True})
check("self loop 422", r.status_code == 422, r.status_code)

# 未知地点
r = client.post("/api/edges", json={
    "code": "AB", "from_code": "A", "to_code": "ZZ", "length_m": 10, "wheelchair": True})
check("unknown endpoint 404", r.status_code == 404, r.status_code)

client.post("/api/edges", json={"code": "AB", "from_code": "A", "to_code": "B",
                                "length_m": 10, "wheelchair": True})
client.post("/api/edges", json={"code": "BC", "from_code": "B", "to_code": "C",
                                "length_m": 10, "wheelchair": False})  # 台阶
client.post("/api/edges", json={"code": "AD", "from_code": "A", "to_code": "D",
                                "length_m": 100, "wheelchair": True})
client.post("/api/edges", json={"code": "DC", "from_code": "D", "to_code": "C",
                                "length_m": 100, "wheelchair": True})

# 重复同方向通道 -> 409
r = client.post("/api/edges", json={"code": "AB2", "from_code": "A", "to_code": "B",
                                    "length_m": 12, "wheelchair": True})
check("dup directed edge 409", r.status_code == 409, r.status_code)

edges = {e["code"]: e for e in client.get("/api/edges").json}
ab_id, bc_id, ad_id, dc_id = (edges[c]["id"] for c in ("AB", "BC", "AD", "DC"))

# 无效区间 start >= end
r = client.post("/api/announcements", json={
    "title": "坏区间", "edge_id": ab_id, "start_ts": at(12), "end_ts": at(12)})
check("invalid window equal 422", r.status_code == 422, r.json)
r = client.post("/api/announcements", json={
    "title": "坏区间", "edge_id": ab_id, "start_ts": at(13), "end_ts": at(12)})
check("invalid window reversed 422", r.status_code == 422, r.status_code)
# 无时区
r = client.post("/api/announcements", json={
    "title": "无时区", "edge_id": ab_id, "start_ts": "2026-10-04T09:00", "end_ts": at(12)})
check("naive ts 400", r.status_code == 400, r.status_code)
# 未知通道
r = client.post("/api/announcements", json={
    "title": "x", "edge_id": 99999, "start_ts": at(9), "end_ts": at(18)})
check("unknown edge ann 404", r.status_code == 404, r.status_code)

# AB 在 [09:00, 18:00) 封闭；两条重叠公告验证并集（同边相邻时段）
client.post("/api/announcements", json={
    "title": "AB 上午封闭", "edge_id": ab_id, "start_ts": at(9), "end_ts": at(13)})
client.post("/api/announcements", json={
    "title": "AB 下午封闭（与上午重叠）", "edge_id": ab_id, "start_ts": at(12), "end_ts": at(18)})
# DC 仅午间封闭：轮椅唯一通道被封时不可达（台阶 BC 不能用）
client.post("/api/announcements", json={
    "title": "DC 午间封闭", "edge_id": dc_id, "start_ts": at(13), "end_ts": at(15)})

r = client.post("/api/publish", json={"note": "v1"})
check("publish v1", r.status_code == 201 and r.json["version"] == 1, r.json)
check("union closed edges v1", r.json["closed_edge_count"] == 2, r.json)

# --- 访客：封闭时刻，步行最短 A->C 被封，绕行 A->D->C = 200 ---
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(10), "wheelchair": False})
check("walker blocked AB reroute", r.status_code == 201, r.json)
check("walker distance via D", abs(r.json["distance_m"] - 200) < 1e-9, r.json["distance_m"])
gno1 = r.json["guidance_no"]
check("guidance bound v1", r.json["version"] == 1, r.json["version"])
check("blocked list", r.json["closed_edges_at_travel_time"] == [ab_id],
      r.json["closed_edges_at_travel_time"])

# 左闭：09:00 整 AB 已封闭
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(9), "wheelchair": False})
check("left closed 09:00", r.json["distance_m"] == 200, r.json["distance_m"])
# 右开：18:00 整 AB 已开放；DC 也已开放 -> 步行最短 AB+BC = 20，无封闭边
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(18), "wheelchair": False})
check("right open 18:00", r.json["distance_m"] == 20, r.json["distance_m"])
check("nothing blocked at 18:00", r.json["closed_edges_at_travel_time"] == [],
      r.json["closed_edges_at_travel_time"])

# 非封闭时刻 07:00：步行 20
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(7), "wheelchair": False})
check("open hours shortest 20", r.json["distance_m"] == 20, r.json["distance_m"])

# 轮椅：平时只能 A->D->C（200），BC 台阶不可用
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(7), "wheelchair": True})
check("wheelchair avoids stairs", r.json["distance_m"] == 200,
      [(s["edge_code"], s["wheelchair"]) for s in r.json["steps"]])
# 轮椅 + 14:00：AB、DC 同时封闭，台阶又不能用 -> 不可达
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(14), "wheelchair": True})
check("wheelchair unreachable 422", r.status_code == 422 and
      r.json["error"]["code"] == "unreachable", r.json)
# 步行 14:00 同样两条路径都被封
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(14), "wheelchair": False})
check("walker also unreachable 14:00", r.status_code == 422, r.json)

# 未知起终点
r = client.post("/api/route", json={
    "origin": "NOPE", "destination": "C", "travel_ts": at(10), "wheelchair": False})
check("unknown origin 404", r.status_code == 404, r.json)
r = client.post("/api/route", json={
    "origin": "A", "destination": "NOPE", "travel_ts": at(10), "wheelchair": False})
check("unknown dest 404", r.status_code == 404, r.json)
# 起终点相同
r = client.post("/api/route", json={
    "origin": "A", "destination": "A", "travel_ts": at(10), "wheelchair": False})
check("same origin dest 422", r.status_code == 422, r.json)
# 缺字段 / 布尔类型
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(10)})
check("missing wheelchair 400", r.status_code == 400, r.json)
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": "garbage", "wheelchair": False})
check("bad travel ts 400", r.status_code == 400, r.json)
# 尚无已发布版本时的提示（切到一个只建表、有地点无版本的空库）
import tempfile
tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmpdir, "empty.db")
init_schema()
client.post("/api/locations", json={"code": "A", "name": "甲"})
client.post("/api/locations", json={"code": "C", "name": "丙"})
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(10), "wheelchair": False})
check("no version explicit msg", r.status_code == 422 and "发布版本" in r.json["error"]["message"],
      r.json)
os.environ["DB_PATH"] = DB  # 恢复主测试库

# 时区等价：今天 02:00Z == 10:00+08:00，AB/DC 均封闭
utc_0200 = at(2).replace("+08:00", "+00:00")
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": utc_0200, "wheelchair": False})
check("timezone equivalence", r.json["distance_m"] == 200, r.json["distance_m"])

# --- 撤回 + 发布 v2：指引仍可凭号查看原路线 ---
anns = client.get("/api/announcements").json
dc_ann = [a for a in anns if a["edge_id"] == dc_id and not a["withdrawn"]][0]
r = client.post(f"/api/announcements/{dc_ann['id']}/withdraw")
check("withdraw ok", r.status_code == 200, r.json)
r = client.post(f"/api/announcements/{dc_ann['id']}/withdraw")
check("double withdraw 409", r.status_code == 409, r.status_code)
r = client.post("/api/announcements/99999/withdraw")
check("withdraw missing 404", r.status_code == 404, r.status_code)

r = client.post("/api/publish", json={"note": "v2 撤回 DC"})
check("publish v2", r.json["version"] == 2 and r.json["closed_edge_count"] == 1, r.json)

# v2 下轮椅 10:00：AB 封、DC 已撤 -> 经 D-C，200
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(10), "wheelchair": True})
check("v2 wheelchair reachable", r.status_code == 201 and r.json["distance_m"] == 200,
      r.json)
check("v2 bound", r.json["version"] == 2, r.json)

# 旧指引（v1 步行绕行 D 的 200 米）保持原样
r = client.get(f"/api/guidance/{gno1}")
check("guidance replay", r.status_code == 200, r.status_code)
check("guidance frozen v1", r.json["version"] == 1 and r.json["distance_m"] == 200,
      r.json)
check("guidance steps intact", len(r.json["steps"]) == 2 and
      r.json["path"] == ["A", "D", "C"], r.json["path"])
check("archived flag", r.json["archived"] is True, r.json)

# 不存在的指引号
r = client.get("/api/guidance/G-999999")
check("bad guidance 404", r.status_code == 404, r.json)

# --- 并集：两条 AB 公告 13:00 同时生效，但去重后只出现一条边 ---
r = client.post("/api/route", json={
    "origin": "A", "destination": "C", "travel_ts": at(12, 30), "wheelchair": False})
check("overlap union dedup", r.json["closed_edges_at_travel_time"].count(ab_id) == 1,
      r.json["closed_edges_at_travel_time"])
check("2 active ann at overlap",
      len([a for a in r.json["active_announcements"] if a["edge_id"] == ab_id]) == 2,
      r.json["active_announcements"])

print(f"\n✅ 全部 {len(passed)} 项断言通过：")
for n in passed:
    print("  -", n)
