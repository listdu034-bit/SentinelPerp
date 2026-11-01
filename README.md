# SentinelPerp

OKX USDT 永续合约采集基础服务（M1 第一阶段），Python 3.12。

## 启动

```bash
cp .env.example .env
# 修改 POSTGRES_PASSWORD，同时更新 DATABASE_URL 中的密码（URL 特殊字符需编码）
docker compose up -d --build
docker compose logs -f backend
```

TimescaleDB 使用 PostgreSQL 15，首次空数据卷启动时执行
`scripts/init_db.sql`。已有数据卷不会再次运行初始化脚本；升级 schema 应通过显式迁移完成。
Redis 和数据库端口仅绑定本机。后端当前运行 collector，API/UI 留待后续阶段。
停止服务使用 `docker compose down`，不带 `-v` 以保留数据库。

本地开发：

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
# Cryptofeed/yapic.json 可能需要 C/C++ 编译器；Docker 构建已包含。
docker compose up -d timescaledb redis
# 将 .env 的 DATABASE_URL / REDIS_URL 主机改为 localhost
python -m backend.collector
```

## 数据与可靠性

- CCXT 每 300 秒发现活跃、线性、USDT 结算的 `*-USDT-SWAP` 合约；变更自动替换订阅。
- Cryptofeed 订阅 trades、L2 book、funding、OI、liquidations，以及 1m candles。
  public/business 端点分流。清算由 Cryptofeed REST 轮询提供，不是逐条 WS 推送；
  只保存交易所确认收盘的 K 线，不将中途更新误当作最终 K 线。
- `symbol` 始终使用 OKX 原始 ID，例如 `BTC-USDT-SWAP`。价格/数量使用 Decimal，
  时间使用带时区 UTC。衍生品 quantity/volume/OI 是**合约张数**，不能直接作为币量或美元量；
  当前阶段不输出未经合约面值换算的美元成交额。
- 每 100 条或 1 秒事务批量写入。队列与待确认事件有界；瞬时 I/O 错误指数退避重试。
  超出重试次数会使服务失败，由 Compose 重启，日志明确报告失败。
- 默认 dual 去重（内存 + Redis），按事件时间分 60 分钟桶、标记 TTL 24 小时；
  提交数据库后才确认去重。数据库带时间列的唯一键作为跨实例和缓存淘汰后的兜底。
  进程崩溃前未提交的内存缓冲不具备持久性；WS 断线缺口只检测/记录，本阶段不自动回补。
- Redis 保存 `latest:trade:{symbol}` 等最新状态，拒绝旧事件覆盖新状态；订单簿历史每分钟
  采样一次，Redis 仍处理实时更新。质量计数保存于 `quality:{symbol}`。
- 延迟、乱序、数据陈旧、交易 ID 不连续和验证失败写入 `quality_logs`。
  `trade_count` 保存 OKX 消息聚合成交笔数，缺口检查先扣除聚合覆盖的 ID。
  ID 不连续属于观测告警，不能证明丢单；可用 `TRADE_ID_GAP_DETECTION=false` 关闭。
  trades/book 独立每 5 秒检查静默，即使没有新回调也能触发 15 秒告警。
  稀疏 funding/OI/liquidations 不应用无消息 15 秒规则。
- SIGINT/SIGTERM 停止源、取消刷新任务、等待已接收写入提交，再释放连接池。

## 保留与聚合（方案 C）

七张 P0 超表：`trades`、`candles`、`funding_rates`、`open_interest`、
`liquidations`、`orderbook_snapshots`、`quality_logs`。明细保留 7 天。
`candles_5m/1h/1d`、`trades_hourly`、`orderbook_hourly`、`oi_daily`、
`funding_daily`、`liquidations_daily` 保留 60 天（形成第 8–60 天压缩汇总层）。
这些视图独立从明细聚合，刷新最近 6 天，避免刷新已删除源区间导致历史聚合消失。

L4 的 `market_features_1m`（60 天）及永久特征聚合属于后续特征阶段，当前没有占位特征表
或计算器。不要把 P0 的 7 天明细策略直接应用到将来的 L4 表。
保留天数是 SQL schema 策略，修改需显式数据库迁移；其余运行参数参见 `.env.example`。

## 验证

```bash
python -m pytest -q
ruff check backend tests
ruff format --check backend tests
```

默认测试离线运行，覆盖真实 Cryptofeed 类型转换、去重、重试、批量提交、失败传播、质量检查和订阅。
集成验证需要独立测试数据库（先执行 `scripts/init_db.sql`）和 Redis：

```bash
TEST_DATABASE_URL=postgresql://... TEST_REDIS_URL=redis://localhost:6379/15 \
  python -m pytest tests/test_integration.py -v
```

实网验收运行 Compose 后，检查 `collector_status` 的连接数和各类 `last_message`、
`SELECT count(*) FROM trades;`、`SELECT * FROM quality_logs ORDER BY time DESC LIMIT 10;`
以及 `redis-cli GET latest:trade:BTC-USDT-SWAP`。数据库初始化/依赖测试不能代替此实网验收。

## React Web 控制台

```bash
cd frontend
npm ci
npm run dev                 # http://localhost:5173
npm run build
npm test
```

使用 React 18、Ant Design 5、TanStack Query 5、React Router 6、axios、date-fns、
Ant Design Charts 和 Lightweight Charts 4。HTTP 查询共享缓存，10 秒内视为新鲜，
每 30 秒自动刷新，失败最多重试 2 次（除 429 外的 4xx 不重试）。切回窗口自动校验。

页面：`/status` 系统统计与采集表；`/rankings` 24h 榜单；
`/markets/BTC-USDT-SWAP` K 线（1m/5m/1h/1d）；`/quality` 事件统计和服务端分页日志。
时间标签使用浏览器本地时间，K 线使用 UTC。统计图使用全部历史质量日志，
系统质量评分使用后端 24h 窗口；两者口径不同。

API 契约对照第二阶段后端 `backend/api/schemas.py`：
`GET /api/v1/status`、`GET /api/v1/candles/{symbol}?interval=1m&size=500`、
`GET /api/v1/quality/summary`、`GET /api/v1/quality/logs?page=1&size=20`。
分页格式为 `{items,total,page,size,pages}`。榜单使用 `WS /ws/market` 的
`{type:"market",time,gainers,losers,status}`；`react-use-websocket` 管理指数退避重连，
收到 `ping` 回复 `pong`，市场快照写入 Query 缓存。断线保留缓存并显示连接告警。
无真实数据时显示空态或接口错误。

开发默认由 Vite 将 `/api`、`/ws` 代理到 `http://127.0.0.1:8000`。
可复制 `frontend/.env.example` 为 `frontend/.env.local`，设置 `API_PROXY_TARGET`。
直接跨域连接可设置 `VITE_API_BASE_URL` 和 `VITE_WS_BASE_URL`；后端必须允许页面的
Origin（包含协议、主机、端口），生产 WebSocket 连接也会校验 Origin。

```bash
docker compose up --build frontend
# http://localhost:8080
```

`docker/frontend.Dockerfile` 使用 Node multi-stage 构建和 nginx:alpine 提供静态文件，
支持 SPA 深链接以及 HTTP/WebSocket 同源反向代理。nginx 的运行时环境变量
`API_UPSTREAM` 默认是 `api:8000`，Compose 可用 `FRONTEND_API_UPSTREAM` 覆盖。
**需先集成并启动第二阶段 A 的 API 服务**；第一阶段的 `backend` 服务仅是采集器。
API 与 frontend 应位于相同 Docker 网络，并在 API 的 CORS/Origin 配置中加入
`http://localhost:8080`（或实际访问源）。外部 API 的 upstream 只填 `主机:端口`。

第二阶段 API 默认 Origin 与 Vite 端口不同，启动 API 前设置：

```dotenv
API_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://localhost:8080","http://127.0.0.1:8080"]
```

若修改开发或容器端口，请同步该列表。Vite HTTP 代理不需要浏览器 CORS，
但 WebSocket 握手保留原始 Origin，因此必须配置。

依赖审计：React Router 6 当前仍有中等级上游告警，npm 建议升级到 v7；本阶段按
指定技术栈保留 v6。控制台使用静态路由、编码后的合约路径和 BrowserRouter，
未使用 SSR hydration。后续升级路由主版本时需重新验证导航行为。
