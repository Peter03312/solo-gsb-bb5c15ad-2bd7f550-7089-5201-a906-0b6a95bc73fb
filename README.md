# 场馆临时封路 · 无障碍通行指引

运营人员维护场馆地点、**有向**的临时通道（正长度、标注轮椅是否可通行），编排
**带时区起止时刻**的封闭公告并发布；访客输入起点、终点、带时区的出行时刻及是否使用
轮椅，系统在**同一发布版本**的快照上、按该时刻生效的封闭公告计算可行**最短路线**，
返回指引编号、分段路径、总距离与版本号。

## 核心规则

- **有向通道**：通道 A→B 与 B→A 需分别建立；长度必须为正数。
- **轮椅属性**：访客勾选轮椅后，仅经过 `wheelchair = true` 的通道。
- **封闭区间左闭右开 `[start, end)`**：恰好等于开始时刻算封闭，恰好等于结束时刻算开放。
- **重叠公告取并集**：同一通道若有多条公告（含相互重叠），封闭时间轴先合并为并集再判断。
- **发布版本不可变（快照）**：每次「发布」把当前地点、通道、未撤回公告整体冻结为一个版本。
  访客查询永远基于当时最新版本；发布与查询用 SQLite `BEGIN IMMEDIATE` 互斥，
  **一次查询绝不会混用两个版本**。
- **撤回只影响后续查询**：撤回公告会立即生成新版本；已生成的指引把路径快照入库，
  凭指引编号随时查看原路线（并标明当时版本号）。
- 明确错误提示：未知地点（`UNKNOWN_ORIGIN/DESTINATION`）、无效区间（`INVALID_INTERVAL`）、
  时刻缺时区（`INVALID_TIME`）、不可达（`ROUTE_UNREACHABLE`）、未知指引编号（`GUIDANCE_NOT_FOUND`）等。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · FastAPI · SQLite3（标准库，WAL）· Dijkstra 最短路 |
| 前端 | React 18 · Vite 5 · 原生 CSS（Nginx 托管静态页并反代 `/api`） |
| 部署 | Docker + Docker Compose，命名卷持久化数据库 |

## 一键启动

前置：已安装 Docker 与 Docker Compose 插件。

```bash
docker compose up -d --build
```

启动后：

- **网页地址（访客 & 运营同一页面，页内切换）**：<http://localhost:8080>
- 后端健康检查：<http://localhost:8000/api/health>
- 后端接口文档（FastAPI Swagger）：<http://localhost:8000/docs>

停止：

```bash
docker compose down          # 保留数据
docker compose down -v       # 同时删除数据库卷
```

首次启动会自动建表并写入一套演示数据（东/西门、中心广场、体育馆、3 号无障碍门及
14 条有向通道），并发布**版本 #1**：演示两条重叠公告将「东门主道（E-P / P-E）」在
**容器当天 08:00–18:00（Asia/Shanghai）**合并封闭。可直接用「东门→体育馆、
当天 10:00」查询，得到经 3 号门的绕行路线（250 米）；用 20:00 查询则恢复主道（200 米）。

## 配置（docker-compose.yml 中 backend.environment）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_PATH` | `/data/venue.db` | SQLite 数据库文件路径，已挂载命名卷 `venue-data` |
| `SEED_DEMO` | `1` | 数据库为空时是否写入演示数据；设为 `0` 则初始化空库（需运营自行发布版本后访客才能查询） |

端口修改：编辑 `docker-compose.yml` 中 frontend 的 `"8080:80"`（宿主机:容器）。

## 本地开发（不用 Docker）

```bash
# 后端（需要 Python 3.11+）
cd backend
python -m pip install -r requirements.txt
DB_PATH=./venue.db SEED_DEMO=1 uvicorn app.main:app --reload --port 8000

# 前端（需要 Node 18+）
cd frontend
npm install
npm run dev      # http://localhost:5173 ，/api 自动代理到 8000
```

## 主要 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/versions/latest` | 访客页用：最新发布版本（含地点、通道、并集封闭区间） |
| POST | `/api/routes` | 访客查询：`{origin, destination, travel_time(ISO8601带时区), wheelchair}` |
| GET | `/api/guidance/{id}` | 凭指引编号查看**原始路线快照** |
| GET/POST/DELETE | `/api/locations[...]` | 地点维护（草稿态） |
| GET/POST/DELETE | `/api/passages[...]` | 有向通道维护（长度须为正，草稿态） |
| GET/POST | `/api/announcements` | 公告编排（校验结束晚于开始；保存为草稿） |
| POST | `/api/announcements/{id}/revoke` | 撤回公告并自动发布新版本 |
| POST | `/api/publish` | 发布新不可变版本 |
| GET | `/api/versions`、`/api/versions/{id}` | 版本列表与版本快照详情 |

时间示例（请求体均接受 ISO 8601 带偏移时间，如 `2026-10-04T09:00+08:00`），
服务端统一转 UTC 存储与比较。
