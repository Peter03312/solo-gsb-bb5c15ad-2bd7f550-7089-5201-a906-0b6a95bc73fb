# 场馆临时封路 · 无障碍通行指引

面向运营人员与访客的场馆通行指引网页：运营人员维护**地点**、**正长度的定向通道**及
**轮椅通行属性**，编排带时区起止时刻的封闭公告并**发布版本**；访客输入起点、终点、
带时区出行时刻与是否使用轮椅，系统在**同一发布版本**内按该时刻生效的公告计算
**最短可行路线**，返回指引编号、路径、距离与版本号。

## 核心规则

- **定向通道**：通道有方向，A→B 与 B→A 是两条通道；长度必须严格为正（米）。
- **轮椅属性**：通道标注「轮椅可通行/不可通行」；选择轮椅后寻路只走可通行通道。
- **封闭区间左闭右开 `[start, end)`**：时刻恰等起始时封闭，恰等结束时已恢复。
- **重叠取并集**：同一时刻多条公告（含同边重叠时段）对封闭边集取并集并自动去重。
- **发布版本不可变**：`POST /api/publish` 把当时全部未撤回公告快照为一个新版本。
- **撤回只影响后续**：撤回公告不改变历史版本；既有指引可凭编号查看**原路线**。
- **查询原子绑定版本**：一次查询在单个数据库事务内固定最新版本 → 过滤生效公告 →
  寻路 → 保存指引，并发发布不会使其混用新旧版本。
- **明确错误提示**：未知地点、未知通道、无效时间区间、不带时区、不可达均返回
  中文错误信息与合适的 HTTP 状态码（400 / 404 / 409 / 422）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React 18 + Vite（构建后由 nginx 托管，`/api` 反代后端） |
| 后端 | Python 3.11 + Flask，gunicorn（多 worker × 多线程） |
| 数据库 | SQLite（WAL 模式，`BEGIN IMMEDIATE` 串行化写事务与路线事务） |
| 寻路 | 有向正权图 Dijkstra（堆优化），封闭边与轮椅不可用边在内存中剔除 |

数据库文件默认位于容器卷 `/app/data/venue.db`，无需外部数据库服务。

## 一键启动（Docker Compose）

前置要求：安装 Docker 与 Docker Compose（`docker compose version` 可用）。

```bash
# 在本目录（docker-compose.yml 所在目录）执行
docker compose up -d --build
```

首次启动会自动：构建前端/后端镜像 → 建表 → 写入演示数据 → 发布版本 **v1**
→ 启动 gunicorn 与 nginx。

启动后访问：

> **http://localhost:8080**

页面分三个标签页：

1. **🧭 访客指引查询**：选起终点、出行时刻（可选时区，默认 UTC+8）、是否轮椅，
   计算路线；也可输入指引编号（如 `G-000001`）复核历史路线。
2. **🗺️ 地点与通道维护**：新增地点、正长度定向通道并标注轮椅属性。
3. **📢 封闭公告与发布**：编排带时区起止时刻的公告、撤回公告、发布版本、查看历史版本。

后端健康检查：`GET http://localhost:8080/api/health`。

停止 / 清理：

```bash
docker compose down            # 停止（数据保留在 volume 中）
docker compose down -v         # 停止并删除数据库卷（下次启动重新初始化演示数据）
docker compose logs -f backend # 查看后端日志
```

## 配置

| 配置项 | 位置 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 网页访问端口 | `.env` 中 `WEB_PORT`（或环境变量） | `8080` | 宿主机映射端口，容器内固定为 nginx 80 |
| SQLite 文件路径 | compose 环境变量 `DB_PATH` | `/app/data/venue.db` | 位于持久化卷 `venue-data` |
| gunicorn worker 数 | compose 环境变量 `GUNICORN_WORKERS` | `2` | 每 worker 4 线程；SQLite 写事务串行化，无需调大 |

修改端口示例：

```bash
echo "WEB_PORT=9000" > .env
docker compose up -d
# 访问 http://localhost:9000
```

## 本地开发（不使用 Docker）

```bash
# 后端（需要 Python 3.11，先 pip install -r backend/requirements.txt）
cd backend
python seed.py                 # 初始化 data/venue.db + 演示数据 + v1
python -m app                  # 或 gunicorn 'app:app'，监听 8000

# 前端（另开终端，需要 Node 20）
cd frontend
npm install
npm run dev                    # http://localhost:5173 ，/api 自动代理到 :8000
```

测试（仅标准库 + Flask test client，无需 Docker）：

```bash
cd backend
python test_domain.py          # 40 项端到端规则断言（区间/并集/版本/撤回/不可达…）
python test_concurrency.py     # 持续发布 + 6 线程并发查询，校验版本一致性与指引重放
```

## HTTP API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/locations` | 地点列表 |
| POST | `/api/locations` | 新增地点 `{code, name}` |
| GET | `/api/edges` | 定向通道列表（含轮椅属性） |
| POST | `/api/edges` | 新增通道 `{code, from_code, to_code, length_m>0, wheelchair, note?}` |
| GET | `/api/announcements` | 公告列表（含撤回状态） |
| POST | `/api/announcements` | 新增公告 `{title, edge_id, start_ts, end_ts}`（ISO8601 **必须带时区**） |
| POST | `/api/announcements/{id}/withdraw` | 撤回公告（只影响后续） |
| POST | `/api/publish` | 发布新版本快照 `{note?}` |
| GET | `/api/versions` | 已发布版本列表 |
| POST | `/api/route` | 计算路线 `{origin, destination, travel_ts, wheelchair}` |
| GET | `/api/guidance/{guidance_no}` | 凭编号查看原路线（历史快照重放） |

所有时间均接受带偏移的 ISO8601（如 `2026-10-04T09:00+08:00` 或
`2026-10-04T01:00Z`），后端统一归一化为 UTC 存储与比较。

### 路线响应示例

```json
{
  "guidance_no": "G-000001",
  "version": 1,
  "travel_ts": "2026-10-04T02:00:00Z",
  "wheelchair": true,
  "distance_m": 350.0,
  "path": ["EAST", "NORTH", "RAMP", "HALL"],
  "steps": [ { "seq": 1, "edge_code": "E-N", "instruction": "沿通道 E-N …",
               "length_m": 150, "wheelchair": true } ],
  "closed_edges_at_travel_time": [3, 1],
  "active_announcements": [ ]
}
```

## 演示数据（时间随初始化日期自动生成）

- 地点：东门 EAST、北门 NORTH、中庭 ATR、多功能厅 HALL、台阶入口 STAIR、西侧坡道 RAMP
- 14 条正长度定向通道，其中中庭↔台阶、台阶↔多功能厅为**轮椅不可通行**
- 4 条公告（同日，UTC+8）：中庭平层 09–18（两条重叠公告演示并集）、
  东门方向 08:30–12、无障碍坡道 12–18，已发布为 v1

白天试查 **东门 → 多功能厅**：步行走台阶绕行 310 米；轮椅绕外环经北门、坡道 350 米；
下午坡道封闭后轮椅**不可达**（明确提示）；20:00 后恢复直达 180 米。

## 目录结构

```
.
├── docker-compose.yml          # 一键编排（backend + frontend + 持久化卷）
├── .env.example                # WEB_PORT 配置示例
├── README.md
├── backend/
│   ├── Dockerfile              # pip 依赖 + seed 初始化 + gunicorn 启动
│   ├── requirements.txt
│   ├── seed.py                 # 建表/演示数据/幂等初始化
│   ├── test_domain.py          # 规则端到端测试
│   ├── test_concurrency.py     # 并发版本一致性测试
│   └── app/
│       ├── __init__.py         # Flask 路由 / 发布快照 / Dijkstra / 指引
│       ├── db.py               # SQLite WAL、BEGIN IMMEDIATE 事务与锁重试
│       ├── schema.sql          # 表结构与索引
│       ├── timeutil.py         # 带时区解析、UTC 归一化、区间校验
│       └── errors.py           # 统一错误结构
└── frontend/
    ├── Dockerfile              # Vite 多阶段构建 + nginx 托管
    ├── nginx.conf              # SPA 回退 + /api 反代 backend:8000
    ├── package.json
    └── src/                    # React：访客 / 数据维护 / 公告发布 三视图
```
