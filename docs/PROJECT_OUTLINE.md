# SentinelPerp 项目开发大纲

## 目录

- [项目概述](#项目概述)
- [技术架构](#技术架构)
- [开源技术栈](#开源技术栈)
- [数据保留策略](#数据保留策略)
- [开发时间评估](#开发时间评估)
- [详细开发计划](#详细开发计划)
- [团队配置方案](#团队配置方案)
- [关键里程碑](#关键里程碑)
- [风险与对策](#风险与对策)

---

## 项目概述

SentinelPerp 是一个面向加密货币永续合约市场的智能观测系统，通过采集、清洗、特征提取和智能分析，帮助交易者识别市场机会。

### 核心价值

- **数据质量优先**：所有数据经过严格验证和清洗
- **分层架构**：原始数据 → 特征数据 → 智能分析
- **AI 驱动**：使用大模型提取市场特征模式
- **开源优先**：最大化利用成熟开源库，避免重复造轮子

### 核心功能

1. **P0 数据采集**：Trades、Candles、OI、Funding、OrderBook、Liquidations 等 8 类数据
2. **市场特征计算**：7 大类特征（价格、流动性、资金费率、清算等）
3. **涨跌幅榜单**：实时 TOP 10 涨跌幅监控
4. **特征识别**：AI 自动识别市场阶段（吸筹、拉升、派发等）
5. **机会发现**：基于历史相似案例发现交易机会

---

## 技术架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│  OKX Exchange                                                │
│  WebSocket + REST API                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  数据采集层（Cryptofeed + CCXT）                             │
│  - WebSocket 实时数据（Cryptofeed）                          │
│  - REST API 历史回填（CCXT）                                 │
│  - 自动重连、错误处理                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  数据清洗层                                                   │
│  - 格式验证、逻辑校验                                         │
│  - 去重（内存 + Redis）                                       │
│  - 质量评分（Coverage + Quality）                            │
│  - 异常值检测                                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  存储层（分层保留策略）                                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L1: Redis（实时缓存，1小时 TTL）                    │  │
│  │  - 最新价格、OBI、CVD                                 │  │
│  │  - 去重缓存                                           │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L2: TimescaleDB - 详细数据（10 天）                 │  │
│  │  - Trades（逐笔）                                     │  │
│  │  - Candles 1m                                         │  │
│  │  - OrderBook 快照（每分钟）                           │  │
│  │  - Liquidations                                       │  │
│  │  保留期: 10 天                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L3: TimescaleDB - 压缩数据（50 天）                 │  │
│  │  - Candles 5m/1h/1d（从 L2 聚合）                    │  │
│  │  - 每日 OI/Funding 汇总                               │  │
│  │  - 每日清算汇总                                       │  │
│  │  压缩比: 约 10:1                                      │  │
│  │  保留期: 50 天（总共 60 天）                          │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L4: 市场特征表（60 天）                              │  │
│  │  - market_features_1m（1 分钟聚合特征）              │  │
│  │  - 7 大类特征 + 质量评分                             │  │
│  │  保留期: 60 天完整 + 永久聚合（5m/1h）               │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L5: 特征案例库（永久）                               │  │
│  │  - 用户标注的特征案例                                 │  │
│  │  - 特征向量（pgvector）                               │  │
│  │  保留期: 永久                                         │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  特征计算层（APScheduler）                                    │
│  - 每分钟计算 market_features_1m                             │
│  - CVD、OBI、Squeeze 检测                                    │
│  - 质量评分                                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  应用层                                                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  FastAPI 后端                                         │  │
│  │  - RESTful API                                        │  │
│  │  - WebSocket（实时推送）                              │  │
│  │  - Swagger 文档                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  LangChain + LLM（特征识别）                          │  │
│  │  - OpenAI GPT-4 / Anthropic Claude                   │  │
│  │  - Prompt 模板管理                                    │  │
│  │  - 结构化输出解析                                     │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  前端展示层（React）                                          │
│  - 系统状态 Dashboard                                         │
│  - 涨跌幅榜单                                                 │
│  - 特征分析页面                                               │
│  - 机会发现页面                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 开源技术栈

### 核心原则：**不重复造轮子**

| 层级 | 开源方案 | 替代自研内容 | 节省时间 |
|------|---------|-------------|---------|
| **数据采集** | Cryptofeed + CCXT | WebSocket 客户端、REST API 封装 | **4-6 周** |
| **后端框架** | FastAPI | API 框架、参数验证、文档生成 | **2-3 周** |
| **数据库** | TimescaleDB | 时序数据库优化 | **不适用** |
| **向量搜索** | pgvector | 相似度搜索引擎 | **2-3 周** |
| **任务调度** | APScheduler | 定时任务框架 | **1-2 周** |
| **大模型集成** | LangChain | LLM 调用封装、Prompt 管理 | **1-2 周** |
| **数据处理** | Pandas + NumPy | 数据分析工具 | **1-2 周** |
| **前端框架** | React + Vite | 前端构建工具 | **不适用** |
| **UI 组件库** | Ant Design / Shadcn | UI 组件 | **3-4 周** |
| **状态管理** | TanStack Query | 数据获取和缓存 | **1 周** |
| **图表库** | TradingView Lightweight Charts | K 线图 | **2-3 周** |
| **通用图表** | Recharts / Chart.js | 统计图表 | **1 周** |

**总节省时间：约 22-31 周（5.5-7.5 个月）**

### 详细技术栈

#### 后端

```yaml
语言与框架:
  - Python 3.10+
  - FastAPI 0.100+（Web 框架）
  - Pydantic 2.0+（数据验证）
  - asyncio（异步 I/O）

数据采集:
  - Cryptofeed 2.4+（WebSocket 实时数据）
  - CCXT 4.0+（REST API、历史回填）

数据库:
  - TimescaleDB 2.11+（时序数据）
  - PostgreSQL 15+（关系数据）
  - pgvector 0.5+（向量搜索）
  - Redis 7+（缓存、去重）

数据处理:
  - Pandas 2.0+（数据分析）
  - NumPy 1.24+（数值计算）
  - asyncpg（异步 PostgreSQL 客户端）

任务调度:
  - APScheduler 3.10+（定时任务）
  - Celery（可选，异步任务队列）

大模型:
  - LangChain 0.1+（LLM 集成框架）
  - OpenAI Python SDK（GPT-4）
  - Anthropic SDK（Claude）

监控与日志:
  - structlog（结构化日志）
  - Prometheus（指标收集）
  - Grafana（可视化监控）

测试:
  - pytest（单元测试）
  - pytest-asyncio（异步测试）
  - httpx（HTTP 客户端测试）
```

#### 前端

```yaml
语言与框架:
  - TypeScript 5.0+
  - React 18+
  - Vite 4+（构建工具）

路由与状态:
  - React Router 6+
  - TanStack Query 4+（数据获取）
  - Zustand / Jotai（状态管理）

UI 组件:
  - Ant Design 5+ / Shadcn UI（组件库）
  - Tailwind CSS 3+（样式）
  - Framer Motion（动画）

图表:
  - TradingView Lightweight Charts（K 线图）
  - Recharts / Chart.js（统计图表）

工具:
  - Axios（HTTP 客户端）
  - date-fns（日期处理）
  - lodash（工具函数）
```

#### 基础设施

```yaml
容器化:
  - Docker 24+
  - Docker Compose 2+

CI/CD:
  - GitHub Actions（可选）
  - GitLab CI（可选）

部署:
  - Nginx（反向代理）
  - PM2 / Supervisor（进程管理）
```

---

## 数据保留策略

### 优化方案：7 天详细 + 53 天压缩（方案 C）

#### 设计目标

1. **平衡成本与功能**：节省 31% 存储，保留核心功能
2. **保留完整性**：60 天内的数据仍可查询
3. **满足 AI 需求**：7 天详细数据足够高精度特征提取
4. **支持新特征回填**：7 天窗口内可回填新特征
5. **支持长期分析**：53 天压缩数据支持趋势分析

#### 核心优化策略

**保留详细数据的**：
- ✅ Candles 1m（AI 特征提取必需）
- ✅ market_features_1m（核心特征，已聚合）
- ✅ Liquidations（Squeeze 检测必需）
- ✅ OI/Funding（市场情绪判断）

**压缩保存的**：
- ⚠️ Trades 逐笔 → 保留小时级汇总（7天原始 + 53天小时级）
- ⚠️ OrderBook 快照 → 保留小时级快照（7天分钟级 + 53天小时级）

#### 分层保留策略

```
┌─────────────────────────────────────────────────────────────┐
│  L1: Redis（实时层，1 小时 TTL）                             │
│  - 最新市场状态                                               │
│  - 去重缓存                                                   │
│  存储容量: 约 1 GB                                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  L2: 详细数据（7 天）                                         │
│  数据类型              | 粒度      | 每日容量 | 7天总容量     │
│  ─────────────────────|───────────|─────────|──────────── │
│  Candles 1m           | 1 分钟    | 80 MB   | 560 MB       │
│  market_features_1m   | 1 分钟    | 150 MB  | 1.05 GB      │
│  Trades（逐笔）        | 完整      | 8 GB    | 56 GB        │
│  Liquidations         | 完整      | 400 MB  | 2.8 GB       │
│  OI/Funding           | 每次更新   | 40 MB   | 280 MB       │
│  OrderBook 快照       | 每分钟    | 4 GB    | 28 GB        │
│  ─────────────────────|───────────|─────────|──────────── │
│  总计                  |           | ~12.7GB | **88 GB**    │
│                                                              │
│  保留策略: 超过 7 天自动删除                                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  L3: 压缩数据（53 天，总共 60 天）                            │
│  数据类型              | 粒度    | 每日容量  | 53天总容量    │
│  ─────────────────────|─────────|─────────|───────────── │
│  Candles 5m           | 5 分钟  | 16 MB   | 850 MB        │
│  Candles 1h           | 1 小时  | 1.5 MB  | 80 MB         │
│  Candles 1d           | 1 天    | 50 KB   | 2.6 MB        │
│  market_features 1h   | 1 小时  | 10 MB   | 530 MB        │
│  Trades 小时级汇总    | 1 小时  | 20 MB   | 1.06 GB       │
│  OrderBook 小时级快照 | 1 小时  | 10 MB   | 530 MB        │
│  OI 每日汇总          | 1 天    | 10 MB   | 530 MB        │
│  Funding 每日汇总     | 1 天    | 5 MB    | 265 MB        │
│  Liquidation 每日汇总 | 1 天    | 20 MB   | 1.06 GB       │
│  ─────────────────────|─────────|─────────|───────────── │
│  总计                  |         | ~52 MB  | **2.6 GB**    │
│                                                              │
│  压缩方式:                                                    │
│  - 从 L2 聚合生成                                            │
│  - TimescaleDB Continuous Aggregates                        │
│  - 保留期: 超过 60 天自动删除                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  L4: 市场特征表（60 天完整）                                  │
│  - market_features_1m（1 分钟聚合）                          │
│  - 7 大类特征 + 质量评分                                      │
│  每日容量: 150 MB | 60天: **9 GB**                           │
│                                                              │
│  保留策略:                                                    │
│  - 60 天完整保留                                             │
│  - 超过 60 天聚合为 5m/1h（永久保留）                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  L5: 特征案例库（永久）                                       │
│  - 用户标注的特征案例                                         │
│  - 特征向量（pgvector）                                       │
│  容量: 按案例增长，预计 **1-5 GB/年**                         │
└─────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总存储容量（100 个币种）:
  L1 (Redis):              1 GB
  L2 (7天详细):           88 GB
  L3 (53天压缩):          2.6 GB
  L4 (60天特征):          9 GB
  L5 (案例库):            5 GB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计:                    **~106 GB**  ✅ 方案 C

对比原方案（60天完整）: ~780 GB
节省比例: **86%**

对比 10+50 方案:        148 GB
额外节省:                **31%**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 数据聚合策略

##### 1. Candles 聚合（5m/1h/1d）

```sql
-- 使用 TimescaleDB Continuous Aggregates 自动聚合

-- 5 分钟 K 线（从 1 分钟聚合）
CREATE MATERIALIZED VIEW candles_5m
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('5 minutes', time) AS time,
    symbol,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(volume_usd) AS volume_usd
FROM candles
WHERE interval = '1m'
GROUP BY time_bucket('5 minutes', time), symbol;

-- 设置自动刷新策略
SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset => INTERVAL '10 minutes',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes');

-- 1 小时 K 线（从 5 分钟聚合）
CREATE MATERIALIZED VIEW candles_1h
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS time,
    symbol,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(volume_usd) AS volume_usd
FROM candles_5m
GROUP BY time_bucket('1 hour', time), symbol;

-- 1 天 K 线（从 1 小时聚合）
CREATE MATERIALIZED VIEW candles_1d
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS time,
    symbol,
    FIRST(open, time) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, time) AS close,
    SUM(volume) AS volume,
    SUM(volume_usd) AS volume_usd
FROM candles_1h
GROUP BY time_bucket('1 day', time), symbol;
```

##### 2. OI/Funding 每日汇总

```sql
-- OI 每日汇总
CREATE MATERIALIZED VIEW oi_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS time,
    symbol,
    FIRST(oi, time) AS open_oi,
    MAX(oi) AS high_oi,
    MIN(oi) AS low_oi,
    LAST(oi, time) AS close_oi,
    LAST(oi_usd, time) AS close_oi_usd,
    (LAST(oi, time) - FIRST(oi, time)) AS oi_change,
    ((LAST(oi, time) - FIRST(oi, time)) / FIRST(oi, time) * 100) AS oi_change_pct
FROM open_interest
GROUP BY time_bucket('1 day', time), symbol;

-- Funding Rate 每日汇总
CREATE MATERIALIZED VIEW funding_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS time,
    symbol,
    AVG(funding_rate) AS avg_funding_rate,
    MIN(funding_rate) AS min_funding_rate,
    MAX(funding_rate) AS max_funding_rate,
    STDDEV(funding_rate) AS funding_volatility
FROM funding_rates
GROUP BY time_bucket('1 day', time), symbol;
```

##### 3. Liquidation 每日汇总

```sql
-- 清算每日汇总
CREATE MATERIALIZED VIEW liquidations_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS time,
    symbol,
    COUNT(*) AS total_liquidations,
    SUM(CASE WHEN side = 'long' THEN quantity * price ELSE 0 END) AS long_liq_usd,
    SUM(CASE WHEN side = 'short' THEN quantity * price ELSE 0 END) AS short_liq_usd,
    SUM(quantity * price) AS total_liq_usd
FROM liquidations
GROUP BY time_bucket('1 day', time), symbol;
```

##### 4. Trades 小时级汇总（方案 C 新增）

```sql
-- 交易小时级汇总
CREATE MATERIALIZED VIEW trades_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS time,
    symbol,
    COUNT(*) AS trade_count,
    SUM(quantity) AS total_quantity,
    SUM(CASE WHEN side = 'buy' THEN quantity * price ELSE 0 END) AS buy_volume_usd,
    SUM(CASE WHEN side = 'sell' THEN quantity * price ELSE 0 END) AS sell_volume_usd,
    SUM(quantity * price) AS total_volume_usd,
    AVG(price) AS avg_price,
    FIRST(price, time) AS open_price,
    LAST(price, time) AS close_price
FROM trades
GROUP BY time_bucket('1 hour', time), symbol;

-- 设置自动刷新
SELECT add_continuous_aggregate_policy('trades_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

##### 5. OrderBook 小时级快照（方案 C 新增）

```sql
-- 订单簿小时级快照
CREATE MATERIALIZED VIEW orderbook_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS time,
    symbol,
    LAST(bid_price_1, time) AS bid_price_1,
    LAST(bid_quantity_1, time) AS bid_quantity_1,
    LAST(ask_price_1, time) AS ask_price_1,
    LAST(ask_quantity_1, time) AS ask_quantity_1,
    AVG(bid_depth_usd) AS avg_bid_depth_usd,
    AVG(ask_depth_usd) AS avg_ask_depth_usd,
    AVG((bid_depth_usd - ask_depth_usd) / (bid_depth_usd + ask_depth_usd)) AS avg_obi
FROM orderbook_snapshots
GROUP BY time_bucket('1 hour', time), symbol;
```

#### 数据保留策略配置（方案 C）

```sql
-- L2: 7 天详细数据保留
SELECT add_retention_policy('candles', INTERVAL '7 days');
SELECT add_retention_policy('market_features_1m', INTERVAL '7 days');
SELECT add_retention_policy('liquidations', INTERVAL '7 days');
SELECT add_retention_policy('open_interest', INTERVAL '7 days');
SELECT add_retention_policy('funding_rates', INTERVAL '7 days');

-- Trades 和 OrderBook：保留 7 天原始 + 小时级汇总
SELECT add_retention_policy('trades', INTERVAL '7 days');
SELECT add_retention_policy('orderbook_snapshots', INTERVAL '7 days');

-- L3: 53 天压缩数据保留（总共 60 天）
SELECT add_retention_policy('candles_5m', INTERVAL '60 days');
SELECT add_retention_policy('candles_1h', INTERVAL '60 days');
SELECT add_retention_policy('candles_1d', INTERVAL '60 days');
SELECT add_retention_policy('trades_hourly', INTERVAL '60 days');
SELECT add_retention_policy('orderbook_hourly', INTERVAL '60 days');
SELECT add_retention_policy('oi_daily', INTERVAL '60 days');
SELECT add_retention_policy('funding_daily', INTERVAL '60 days');
SELECT add_retention_policy('liquidations_daily', INTERVAL '60 days');

-- L4: 市场特征表
-- 1 分钟特征保留 60 天
SELECT add_retention_policy('market_features_1m', INTERVAL '60 days');

-- 5 分钟/1 小时特征永久保留（不设置保留策略）
-- market_features_5m, market_features_1h 无保留策略

-- L5: 特征案例库永久保留（不设置保留策略）
-- feature_cases 无保留策略
```

#### 查询示例

##### 查询最近 7 天的详细数据

```sql
-- 查询最近 7 天的逐笔交易
SELECT *
FROM trades
WHERE symbol = 'BTC-USDT-SWAP'
AND time > NOW() - INTERVAL '7 days'
ORDER BY time DESC;
```

##### 查询 7-60 天的压缩数据

```sql
-- 查询 30 天前的 5 分钟 K 线（压缩数据）
SELECT *
FROM candles_5m
WHERE symbol = 'BTC-USDT-SWAP'
AND time >= NOW() - INTERVAL '30 days'
AND time < NOW() - INTERVAL '7 days'
ORDER BY time DESC;

-- 查询 7-60 天的小时级交易汇总
SELECT *
FROM trades_hourly
WHERE symbol = 'BTC-USDT-SWAP'
AND time >= NOW() - INTERVAL '60 days'
AND time < NOW() - INTERVAL '7 days'
ORDER BY time DESC;
```

##### 联合查询（7 天详细 + 53 天压缩）

```sql
-- 查询最近 60 天的 5 分钟 K 线
-- 自动合并详细数据和压缩数据
WITH recent_detailed AS (
    SELECT 
        time_bucket('5 minutes', time) AS time,
        symbol,
        FIRST(open, time) AS open,
        MAX(high) AS high,
        MIN(low) AS low,
        LAST(close, time) AS close,
        SUM(volume) AS volume
    FROM candles
    WHERE symbol = 'BTC-USDT-SWAP'
    AND time > NOW() - INTERVAL '7 days'
    AND interval = '1m'
    GROUP BY time_bucket('5 minutes', time), symbol
),
compressed AS (
    SELECT *
    FROM candles_5m
    WHERE symbol = 'BTC-USDT-SWAP'
    AND time >= NOW() - INTERVAL '60 days'
    AND time <= NOW() - INTERVAL '7 days'
)
SELECT * FROM recent_detailed
UNION ALL
SELECT * FROM compressed
ORDER BY time DESC;
```

#### 存储成本分析

##### 云服务器成本（以阿里云为例）

**方案 C：7 天详细 + 53 天压缩（总 106 GB）**

```
配置:
  CPU: 4 核
  内存: 16 GB
  存储: 150 GB SSD（106 GB 数据 + 44 GB 系统/缓冲）

成本:
  ECS: ~¥400/月
  SSD 存储: ~¥200/月
  流量: ~¥100/月
━━━━━━━━━━━━━━━━━━━━
总计: ~¥700/月（约 $95/月）

对比原方案（60天完整，需 780 GB 存储）:
  原成本: ~¥2000/月
  节省: ~¥1300/月（65%）

对比 10+50 方案（148 GB 存储）:
  原成本: ~¥900/月
  节省: ~¥200/月（22%）
```

**成本优势**：
- ✅ 比完整保留方案节省 **65% 成本**
- ✅ 比 10+50 方案额外节省 **22% 成本**
- ✅ 存储需求降至 106 GB，单台服务器即可支撑
- ✅ 保留 7 天完整数据，满足 AI 特征提取需求
- ✅ 53 天压缩数据支持长期趋势分析

---

## 开发时间评估

### 单人全栈 + 开源库 + AI 辅助

| Phase | 内容 | 不用AI | 使用AI | AI节省 |
|-------|------|--------|--------|--------|
| Phase 1 | P0 数据采集（Cryptofeed + CCXT） | 12 天 | **6 天** | 50% |
| Phase 2 | 特征数据层 + 聚合策略 | 17 天 | **8 天** | 53% |
| Phase 3 | 前端基础（React + Ant Design） | 7 天 | **4 天** | 43% |
| Phase 4 | 特征识别（LangChain + LLM） | 14 天 | **7 天** | 50% |
| Phase 5 | 机会发现 | 7 天 | **4 天** | 43% |
| Phase 6 | 测试 + 优化 + 部署 | 7 天 | **4 天** | 43% |
| **总计** | | **64 天<br>(3.2 个月)** | **33 天<br>(1.6 个月)** | **48%** |

### 2 人团队 + 开源库 + AI 辅助

**团队配置**：1 后端 + 1 前端

**并行开发**：
```
Week 1-2:   后端: P0 数据采集          前端: 学习 + 框架搭建
Week 3-4:   后端: 特征数据层           前端: 系统状态 + 榜单
Week 5-6:   后端: 特征识别             前端: 特征分析页面
Week 7:     后端: 机会发现             前端: 机会发现页面
Week 8:     联调 + 测试 + 部署
```

**总时间：6-8 周（1.5-2 个月）**

### MVP 快速版本

**范围**：
- ✅ P0 数据采集（5-10 个主流币种）
- ✅ 市场特征计算
- ✅ 涨跌幅榜单
- ✅ 系统监控页面
- ❌ 特征识别（跳过）
- ❌ 机会发现（跳过）

**时间：3-4 周**

---

## 详细开发计划

### Phase 1: P0 数据采集（6 天，使用 AI）

#### Day 1-2: 环境搭建 + Cryptofeed 集成

**任务**：
- [ ] 项目初始化（FastAPI + Poetry/pip）
- [ ] Docker Compose 配置（TimescaleDB + Redis）
- [ ] Cryptofeed 安装和配置
- [ ] 基础日志系统（structlog）

**AI 辅助**：
```
Prompt 示例:
"帮我创建一个 FastAPI 项目，使用 Poetry 管理依赖，包含：
1. 项目结构（backend/collector, backend/api, backend/storage）
2. docker-compose.yml（TimescaleDB、Redis、Grafana）
3. .env.example 环境变量模板
4. Cryptofeed 的基础封装类（支持 OKX）"
```

**交付物**：
- ✅ 项目基础结构
- ✅ Docker 环境可运行
- ✅ Cryptofeed 可连接 OKX

---

#### Day 3-5: 8 类 P0 数据采集

**任务**：
- [ ] Instruments（CCXT REST）
- [ ] Candles（CCXT REST 历史 + Cryptofeed WS 实时）
- [ ] Trades（Cryptofeed WS）
- [ ] Open Interest（Cryptofeed WS）
- [ ] Funding Rate（Cryptofeed WS）
- [ ] Mark/Index Price（Cryptofeed WS）
- [ ] Order Book L2（Cryptofeed WS）
- [ ] Liquidations（Cryptofeed WS）

**AI 辅助**：
```
Prompt 示例:
"使用 Cryptofeed 编写一个数据采集管理器，支持：
1. 订阅 OKX 的 Trades、OrderBook、Funding 等数据
2. 数据标准化（转换为统一格式）
3. 数据验证（价格、数量非负，OHLC 逻辑正确）
4. 存储到 TimescaleDB
5. 错误处理和自动重连"
```

**交付物**：
- ✅ 8 类数据实时采集
- ✅ 数据存储到 TimescaleDB
- ✅ 基础数据验证

---

#### Day 6-7: 数据质量监控

**任务**：
- [ ] 质量指标收集（延迟、拒绝率、去重率）
- [ ] 告警规则（数据停止、质量下降）
- [ ] Grafana Dashboard

**AI 辅助**：
```
Prompt 示例:
"创建一个数据质量监控系统：
1. 定义质量指标类（DataQualityMetrics）
2. 实时收集指标（接收量、拒绝量、平均延迟）
3. 告警逻辑（数据停止 60 秒、拒绝率 > 10%）
4. Prometheus 指标导出
5. 提供 Grafana Dashboard JSON 配置"
```

**交付物**：
- ✅ 质量监控运行
- ✅ Grafana 可查看指标
- ✅ 告警可发送

---

### Phase 2: 特征数据层（8 天，使用 AI）

#### Day 1-2: 数据模型 + 数据库表

**任务**：
- [ ] MarketFeature1Min Pydantic 模型
- [ ] 数据库表设计（market_features_1m）
- [ ] 聚合视图（candles_5m, candles_1h, candles_1d）
- [ ] 保留策略配置

**AI 辅助**：
```
Prompt 示例:
"创建市场特征数据模型和数据库表：
1. Pydantic 模型 MarketFeature1Min（7 大类特征）
2. TimescaleDB 表 market_features_1m 的 DDL
3. Continuous Aggregates（5m/1h/1d）
4. 保留策略（10 天详细 + 50 天压缩）"
```

**交付物**：
- ✅ 数据模型定义
- ✅ 数据库表创建
- ✅ 聚合视图配置

---

#### Day 3-6: 特征计算实现

**任务**：
- [ ] MarketFeatureCalculator 框架
- [ ] 7 大类特征计算（价格、流动性、资金费率等）
- [ ] CVD 累计计算（改进版）
- [ ] OBI 计算
- [ ] Squeeze 检测（滚动窗口 + 历史对比）
- [ ] 异常值检测
- [ ] 质量评分

**AI 辅助**：
```
Prompt 示例:
"实现 MarketFeatureCalculator 类：
1. 从 P0 数据并发查询（Candles、Trades、OI 等）
2. 计算 7 大类特征（提供详细计算逻辑）
3. CVD 累计计算（从上一分钟累加）
4. Squeeze 检测（5 分钟滚动窗口，与 24h 平均对比）
5. 质量评分（Coverage + Quality）
6. 容错机制（部分数据源失败不影响整体）"
```

**交付物**：
- ✅ 特征计算逻辑完整
- ✅ 单元测试通过

---

#### Day 7-8: 定时任务 + API

**任务**：
- [ ] APScheduler 定时任务（每分钟计算）
- [ ] 批量存储优化
- [ ] FastAPI 查询接口
- [ ] Swagger 文档

**AI 辅助**：
```
Prompt 示例:
"创建特征计算定时任务和查询 API：
1. APScheduler 每分钟执行特征计算
2. 并发处理所有合约
3. 批量插入数据库
4. FastAPI 查询接口：
   - GET /market-features/{symbol}（时间序列）
   - GET /market-features/{symbol}/latest（最新）
   - GET /market-features/squeeze-events（Squeeze 事件）"
```

**交付物**：
- ✅ 定时任务运行
- ✅ API 可查询
- ✅ Swagger 文档生成

---

### Phase 3: 前端基础（4 天，使用 AI）

#### Day 1: 项目搭建

**任务**：
- [ ] Vite + React + TypeScript 项目初始化
- [ ] Ant Design / Shadcn UI 配置
- [ ] React Router 配置
- [ ] TanStack Query 配置
- [ ] Axios 封装

**AI 辅助**：
```
Prompt 示例:
"创建 React 前端项目：
1. Vite + React 18 + TypeScript
2. 集成 Ant Design
3. 配置 React Router（/、/leaderboard、/features、/opportunities）
4. 配置 TanStack Query（数据获取）
5. Axios 封装（baseURL、错误处理、拦截器）"
```

---

#### Day 2: 系统状态页面

**任务**：
- [ ] 系统概览（服务状态、数据统计）
- [ ] 数据质量 Dashboard
- [ ] 实时日志流

**AI 辅助**：
```
Prompt 示例:
"创建系统状态页面组件：
1. SystemOverview（服务状态卡片）
2. DataQualityChart（质量评分趋势图，使用 Recharts）
3. RealTimeLogs（WebSocket 日志流）
4. 使用 Ant Design 的 Card、Statistic、Table 组件"
```

---

#### Day 3-4: 涨跌幅榜单

**任务**：
- [ ] 榜单表格（TOP 10 涨幅/跌幅）
- [ ] 时间维度切换（1h/4h/24h/7d）
- [ ] TradingView 图表集成
- [ ] 添加到分析按钮

**AI 辅助**：
```
Prompt 示例:
"创建涨跌幅榜单页面：
1. LeaderboardTable 组件（Ant Table）
2. 时间维度选择器（Tabs）
3. TradingView Lightweight Charts 集成（点击查看 K 线）
4. 添加到分析按钮（调用 API）
5. 实时刷新（每 60 秒）"
```

**交付物**：
- ✅ 前端可运行
- ✅ 系统状态可查看
- ✅ 涨跌幅榜单可用

---

### Phase 4: 特征识别（7 天，使用 AI）

#### Day 1-2: LangChain + LLM 集成

**任务**：
- [ ] LangChain 安装配置
- [ ] OpenAI/Claude API 封装
- [ ] Prompt 模板设计
- [ ] 结构化输出解析（Pydantic）

**AI 辅助**：
```
Prompt 示例:
"使用 LangChain 集成大模型：
1. 封装 LLMService 类（支持 OpenAI 和 Claude）
2. 定义 Prompt 模板（特征提取）
3. 使用 PydanticOutputParser 解析结构化输出
4. 错误处理和重试机制"
```

---

#### Day 3-4: 特征提取服务

**任务**：
- [ ] 从数据库查询完整数据
- [ ] 构造 Prompt（包含价格、成交量、OI、Funding 等）
- [ ] 调用大模型
- [ ] 解析返回结果（阶段识别、关键转折点）
- [ ] 后台任务队列（Celery 或异步任务）

**AI 辅助**：
```
Prompt 示例:
"创建特征提取服务：
1. FeatureExtractionService 类
2. 查询指定时间段的完整市场数据
3. 构造大模型 Prompt（包含数据摘要）
4. 调用 LLM 分析
5. 解析返回的 JSON（阶段分析、转折点、特征分类）
6. 使用 Celery 后台异步处理"
```

---

#### Day 5-6: 特征分析前端

**任务**：
- [ ] 任务列表（创建、状态追踪）
- [ ] 时间轴组件（拖拽选择）
- [ ] 阶段详情卡片
- [ ] K 线图 + 特征标注
- [ ] 保存到特征库对话框

**AI 辅助**：
```
Prompt 示例:
"创建特征分析前端页面：
1. FeatureAnalysisPage 主组件
2. TaskList 组件（显示分析任务）
3. StageTimeline 组件（可拖拽时间轴）
4. StageDetailCard 组件（显示阶段特征）
5. TradingView 图表集成（标注转折点）
6. SaveCaseDialog 组件（选择容器、添加标签）"
```

---

#### Day 7: 特征容器 + pgvector

**任务**：
- [ ] pgvector 扩展安装
- [ ] 特征向量生成
- [ ] 向量相似度搜索
- [ ] 特征案例保存

**AI 辅助**：
```
Prompt 示例:
"实现特征向量化和相似度搜索：
1. 安装 pgvector 扩展
2. 将特征转换为向量（使用 OpenAI Embeddings）
3. 存储到 feature_cases 表（包含 vector 字段）
4. 实现相似度搜索（余弦相似度）
5. API 接口：保存案例、查询相似案例"
```

**交付物**：
- ✅ 特征识别功能完整
- ✅ 可手动添加合约分析
- ✅ 可保存到特征库

---

### Phase 5: 机会发现（4 天，使用 AI）

#### Day 1-2: 机会发现引擎

**任务**：
- [ ] 实时扫描服务（定时扫描所有合约）
- [ ] 计算当前特征
- [ ] 向量相似度匹配
- [ ] 阶段识别
- [ ] 机会评分

**AI 辅助**：
```
Prompt 示例:
"创建机会发现引擎：
1. OpportunityFinder 类
2. 定时扫描所有合约（每 5 分钟）
3. 计算当前市场特征
4. 使用 pgvector 查询相似历史案例
5. 识别当前阶段和预测后续走势
6. 计算机会评分（相似度 + 成功率 + 平均收益）"
```

---

#### Day 3-4: 机会发现前端

**任务**：
- [ ] 机会列表（卡片展示）
- [ ] 筛选器（最低置信度、成功率）
- [ ] 机会详情（相似案例、历史回测）
- [ ] 订阅提醒（可选）

**AI 辅助**：
```
Prompt 示例:
"创建机会发现前端页面：
1. OpportunitiesPage 主组件
2. OpportunityCard 组件（显示机会信息）
3. 筛选器（Slider 控制最低置信度/成功率）
4. OpportunityDetail 页面（详情 + 相似案例对比）
5. 实时刷新（每 5 分钟）"
```

**交付物**：
- ✅ 机会发现功能完整
- ✅ 可查看机会列表
- ✅ 可查看详情和历史案例

---

### Phase 6: 测试 + 优化 + 部署（4 天，使用 AI）

#### Day 1-2: 测试

**任务**：
- [ ] 单元测试补全（pytest）
- [ ] 集成测试（端到端）
- [ ] 性能测试（并发压力）
- [ ] 安全测试（SQL 注入、XSS）

**AI 辅助**：
```
Prompt 示例:
"生成测试用例：
1. 为 MarketFeatureCalculator 生成单元测试
2. 为 API 接口生成集成测试（pytest + httpx）
3. 生成性能测试脚本（Locust）
4. 检查代码安全问题（SQL 注入、XSS）"
```

---

#### Day 3: 性能优化

**任务**：
- [ ] SQL 查询优化（添加索引）
- [ ] 缓存策略（Redis）
- [ ] 前端代码分割（懒加载）
- [ ] 数据库连接池调优

**AI 辅助**：
```
Prompt 示例:
"优化系统性能：
1. 分析 SQL 查询性能（EXPLAIN ANALYZE）
2. 建议添加索引
3. 实现 Redis 缓存（最新价格、OBI、CVD）
4. 前端代码分割（React.lazy）
5. 数据库连接池配置优化"
```

---

#### Day 4: 部署 + 文档

**任务**：
- [ ] Docker 生产配置
- [ ] Nginx 反向代理配置
- [ ] 部署脚本（一键部署）
- [ ] 用户手册
- [ ] API 文档

**AI 辅助**：
```
Prompt 示例:
"生成部署文档和脚本：
1. docker-compose.prod.yml（生产配置）
2. Nginx 配置（反向代理、HTTPS）
3. 部署脚本（deploy.sh）
4. 用户手册（Markdown）
5. 运维手册（备份、恢复、监控）"
```

**交付物**：
- ✅ 系统通过测试
- ✅ 性能优化完成
- ✅ 可一键部署
- ✅ 文档齐全

---

## 团队配置方案

### 方案 A：单人全栈（推荐个人项目）

**技能要求**：
- Python（FastAPI、asyncio）
- TypeScript + React
- TimescaleDB / PostgreSQL
- Docker

**时间**：
- MVP（不含特征识别）：**3-4 周**
- 完整版（含 AI 特征识别）：**6-8 周（1.5-2 个月）**

**优势**：
- ✅ 决策快
- ✅ 沟通成本低
- ✅ 灵活调整

**劣势**：
- ⚠️ 需要全栈能力
- ⚠️ 时间较长

---

### 方案 B：2 人团队（推荐）

**团队配置**：
- 1 后端工程师（Python、数据库）
- 1 前端工程师（React、TypeScript）

**分工**：
```
后端工程师（+ AI）:
├─ Week 1-2: P0 数据采集（Cryptofeed + CCXT）
├─ Week 3-4: 特征数据层 + 聚合策略
├─ Week 5-6: 特征识别（LangChain + LLM）
├─ Week 7: 机会发现引擎
└─ Week 8: 联调 + 性能优化

前端工程师（+ AI）:
├─ Week 1-2: 学习业务 + 前端框架搭建
├─ Week 3-4: 系统状态页 + 涨跌幅榜单
├─ Week 5-6: 特征分析前端（时间轴、K 线图）
├─ Week 7: 机会发现前端
└─ Week 8: 联调 + UI/UX 优化
```

**时间**：**6-8 周（1.5-2 个月）**

**优势**：
- ✅ 并行开发，效率高
- ✅ 专业分工，质量好
- ✅ 时间短

**劣势**：
- ⚠️ 需要协调沟通
- ⚠️ 前期需要 API 设计对齐

---

### 方案 C：3-4 人团队（快速交付）

**团队配置**：
- 2 后端工程师（分工：数据采集 + 特征识别）
- 1 前端工程师
- 1 DevOps（可选，负责基础设施）

**时间**：**4-6 周（1-1.5 个月）**

**优势**：
- ✅ 最快交付
- ✅ 专业分工

**劣势**：
- ⚠️ 成本高
- ⚠️ 沟通成本增加

---

## 关键里程碑

### Milestone 1: 数据基础设施（Week 2）

**目标**：
- ✅ P0 数据稳定采集
- ✅ 数据质量监控运行
- ✅ Grafana Dashboard 可用

**验收标准**：
- 数据质量评分 > 0.9
- 7×24 稳定运行
- 数据延迟 < 5 秒

---

### Milestone 2: 特征数据层（Week 4）

**目标**：
- ✅ 市场特征每分钟计算
- ✅ 聚合策略生效（10 天详细 + 50 天压缩）
- ✅ API 可查询

**验收标准**：
- 特征计算延迟 < 10 秒
- API 响应时间 < 500ms
- 数据保留策略正确执行

---

### Milestone 3: 基础前端（Week 5）

**目标**：
- ✅ 系统状态页面可用
- ✅ 涨跌幅榜单可用
- ✅ 前后端联调完成

**验收标准**：
- 页面加载时间 < 2 秒
- 实时数据刷新正常
- UI/UX 符合预期

---

### Milestone 4: 特征识别（Week 7）

**目标**：
- ✅ AI 特征提取运行
- ✅ 特征案例可保存
- ✅ 向量搜索可用

**验收标准**：
- 特征提取成功率 > 90%
- AI 响应时间 < 30 秒
- 相似案例匹配准确

---

### Milestone 5: 完整交付（Week 8）

**目标**：
- ✅ 机会发现功能完整
- ✅ 测试通过
- ✅ 可生产部署

**验收标准**：
- 单元测试覆盖率 > 70%
- 性能测试通过
- 文档齐全

---

## 风险与对策

### 风险 1: Cryptofeed 数据源不稳定

**风险等级**：中

**对策**：
- 实现自动重连机制
- 使用 CCXT 作为备用数据源
- 监控数据质量，及时告警

---

### 风险 2: 大模型 API 成本过高

**风险等级**：中

**影响**：
- GPT-4 调用成本 ~$0.03/1K tokens
- 每次分析 ~8K tokens = $0.24
- 每天分析 20 个合约 = $4.8/天 = $144/月

**对策**：
- 使用 GPT-4 Turbo（更便宜）
- 只分析重要合约（涨跌幅 > 5%）
- 缓存分析结果（24 小时内不重复分析）
- 考虑使用本地模型（Llama 3）

---

### 风险 3: 存储空间不足

**风险等级**：低（已优化）

**对策**：
- 10 天详细 + 50 天压缩，总计 ~150 GB
- 定期监控存储使用率
- 自动清理策略生效

---

### 风险 4: 性能瓶颈

**风险等级**：中

**对策**：
- 数据库查询优化（索引）
- Redis 缓存热点数据
- 异步并发处理
- 水平扩展（增加服务器）

---

### 风险 5: 团队成员变动

**风险等级**：高（小团队）

**对策**：
- 完善文档（代码注释、API 文档）
- 代码规范统一
- 使用 Git 版本管理
- 定期 Code Review

---

## 附录

### A. 环境变量配置

```bash
# .env.example

# 应用配置
APP_ENV=production
APP_VERSION=1.0.0
LOG_LEVEL=INFO

# OKX API
OKX_MARKET_FILTER=*-USDT-SWAP
OKX_REST_URL=https://www.okx.com

# 数据库
DATABASE_URL=postgresql://sentinel:password@timescaledb:5432/sentinelperp
REDIS_URL=redis://redis:6379/0

# 大模型
LLM_PROVIDER=openai  # openai / anthropic
LLM_MODEL=gpt-4-turbo
LLM_API_KEY=sk-...
LLM_TEMPERATURE=0.1

# 数据保留
DETAILED_DATA_RETENTION_DAYS=10
COMPRESSED_DATA_RETENTION_DAYS=50
FEATURE_DATA_RETENTION_DAYS=60

# 性能配置
MAX_WORKERS=4
DB_POOL_SIZE=20
REDIS_MAX_CONNECTIONS=50
```

---

### B. 项目结构

```
SentinelPerp/
├── backend/
│   ├── collector/           # 数据采集
│   │   ├── cryptofeed_manager.py
│   │   ├── ccxt_client.py
│   │   ├── data_validator.py
│   │   └── quality_monitor.py
│   ├── storage/             # 存储层
│   │   ├── timescale_client.py
│   │   ├── redis_client.py
│   │   └── models.py
│   ├── services/            # 业务逻辑
│   │   ├── market_feature_calculator.py
│   │   ├── feature_extraction_service.py
│   │   └── opportunity_finder.py
│   ├── api/                 # API 层
│   │   ├── main.py
│   │   └── routes/
│   │       ├── leaderboard.py
│   │       ├── market_features.py
│   │       ├── features.py
│   │       └── opportunities.py
│   ├── tasks/               # 定时任务
│   │   ├── feature_calculator_task.py
│   │   └── aggregation_task.py
│   ├── config/              # 配置
│   │   └── settings.py
│   └── utils/               # 工具
│       ├── logger.py
│       └── helpers.py
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── SystemStatus.tsx
│   │   │   ├── Leaderboard.tsx
│   │   │   ├── FeatureAnalysis.tsx
│   │   │   └── Opportunities.tsx
│   │   ├── components/
│   │   ├── api/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── nginx.conf
├── scripts/
│   ├── init_db.sql
│   ├── deploy.sh
│   └── backup.sh
├── docs/
│   ├── DEVELOPMENT.md
│   ├── DATA_ARCHITECTURE.md
│   ├── MARKET_FEATURES.md
│   ├── FEATURE_RECOGNITION.md
│   └── DEPLOYMENT.md
├── tests/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

### C. 常用命令

```bash
# 开发环境启动
docker compose up -d

# 查看日志
docker compose logs -f backend

# 运行测试
pytest tests/ -v

# 代码格式化
black backend/
isort backend/

# 前端开发
cd frontend
npm run dev

# 生产部署
./scripts/deploy.sh

# 数据库备份
./scripts/backup.sh

# 查看系统状态
curl http://localhost:8000/health
```

---

**文档版本**: v1.0.0  
**创建时间**: 2024-10-30  
**维护者**: SentinelPerp 开发团队

---

## 总结

本开发大纲提供了 SentinelPerp 项目的完整实施方案，包括：

1. ✅ **技术架构**：分层设计，职责清晰
2. ✅ **开源优先**：最大化利用成熟库，节省 5-7 个月开发时间
3. ✅ **优化存储**：10 天详细 + 50 天压缩，节省 81% 存储空间
4. ✅ **AI 辅助**：再节省 50% 开发时间
5. ✅ **详细计划**：每个阶段的任务、时间、交付物明确
6. ✅ **风险管理**：识别关键风险并提供对策

**最终交付时间**：
- 单人 + AI：**6-8 周（1.5-2 个月）**
- 2 人团队 + AI：**6-8 周**
- MVP 版本：**3-4 周**

**核心成功要素**：
1. 使用 Cryptofeed + CCXT（节省 6 周）
2. 使用 FastAPI + Ant Design（节省 5 周）
3. AI 生成 70% 代码（节省 50% 时间）
4. 优化数据保留策略（节省 81% 存储）

现在可以开始开发了！🚀
