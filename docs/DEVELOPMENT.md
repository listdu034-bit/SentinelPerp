# SentinelPerp 开发文档

## 目录

- [项目概述](#项目概述)
- [技术架构](#技术架构)
- [开发环境搭建](#开发环境搭建)
- [项目结构](#项目结构)
- [核心组件](#核心组件)
- [数据流](#数据流)
- [开发规范](#开发规范)
- [测试指南](#测试指南)
- [部署指南](#部署指南)
- [故障排查](#故障排查)
- [贡献指南](#贡献指南)

---

## 项目概述

SentinelPerp 是一个面向加密货币现货与永续合约市场的观测系统，旨在持续采集交易所市场数据，将实时数据转化为可验证的结构化特征，最终沉淀为市场状态、历史行情案例（Episode）与交易行为模板（Playbook）。

### 核心目标

- **数据可靠性优先**：确保数据质量高于指标数量
- **分层数据管理**：原始数据、标准化数据和派生特征分层保存
- **可追溯性**：所有市场判断必须可追溯到数据、规则与历史样本
- **可扩展架构**：以 Cryptofeed 为核心，外围扩展业务模块

### 当前阶段：里程碑 M1

第一里程碑专注于构建可通过 Docker Compose 一键部署、能够 7×24 小时运行的 OKX USDT 永续市场数据采集与监控系统。

**M1 交付内容**：
- OKX USDT 永续合约发现与订阅
- 多类型数据采集：Trades、L2 Order Book、Funding、Open Interest、Liquidations、Candles
- 数据标准化、去重、时效性与缺口监控
- Redis 实时层 + PostgreSQL/TimescaleDB 历史层
- Docker Compose 一键部署
- Web 控制台展示运行状态、数据质量和基础市场数据

---

## 技术架构

### 技术栈

**后端**：
- Python 3.10+
- FastAPI（API 服务）
- Cryptofeed（市场数据采集）
- PostgreSQL + TimescaleDB（时序数据存储）
- Redis（实时数据缓存与去重）

**前端**：
- 现代 Web 框架（待定：React/Vue/Svelte）
- 实时数据可视化

**基础设施**：
- Docker & Docker Compose
- Grafana（可选运维监控）

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        OKX Exchange                          │
│  WebSocket API (Trades, Books, Liquidations, Funding, OI)   │
│              REST API (Instruments, Candles)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Data Collection Layer                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Cryptofeed Framework                                │   │
│  │  - WebSocket handlers                                │   │
│  │  - Data normalization                                │   │
│  │  - Connection management                             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Instrument Discovery Service                        │   │
│  │  - Periodic polling (300s)                           │   │
│  │  - USDT-SWAP filter                                  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Data Processing Layer                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Data Quality Monitor                                │   │
│  │  - Latency check (max 5000ms)                        │   │
│  │  - Out-of-order detection (tolerance 2000ms)         │   │
│  │  - Staleness detection (15s threshold)               │   │
│  │  - Gap detection                                     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Deduplication Engine                                │   │
│  │  - Dual mode (memory + Redis)                        │   │
│  │  - 60-minute buckets                                 │   │
│  │  - 24h TTL                                           │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  │   Redis (Real-time)     │  │  TimescaleDB (History)  │   │
│  │  - Latest market state  │  │  - Trades               │   │
│  │  - Dedup cache          │  │  - Candles              │   │
│  │  - Quality metrics      │  │  - Funding rates        │   │
│  │  - Max memory: 1536MB   │  │  - Open interest        │   │
│  └─────────────────────────┘  │  - Liquidations         │   │
│                                │  - Order book snapshots │   │
│                                │  - Quality logs         │   │
│                                │  Retention:             │   │
│                                │  - Detailed: 3 days     │   │
│                                │  - Daily agg: 90 days   │   │
│                                └─────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Layer                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI Service (Port 8000)                         │   │
│  │  - /health                                           │   │
│  │  - /api/v1/instruments                               │   │
│  │  - /api/v1/trades                                    │   │
│  │  - /api/v1/candles                                   │   │
│  │  - /api/v1/funding                                   │   │
│  │  - /api/v1/quality                                   │   │
│  │  - /docs (Swagger UI)                                │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Web Console (Port 3000)                             │   │
│  │  - System status dashboard                           │   │
│  │  - Data quality metrics                              │   │
│  │  - Market overview                                   │   │
│  │  - Real-time data viewer                             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Grafana (Port 3001, Optional)                       │   │
│  │  - Operational metrics                               │   │
│  │  - System monitoring                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 开发环境搭建

### 前置要求

- Docker >= 20.10
- Docker Compose >= 2.0
- Python >= 3.10（本地开发）
- Node.js >= 18（前端开发）
- Git

### 快速启动

1. **克隆仓库**

```bash
git clone <repository-url>
cd SentinelPerp
```

2. **配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少修改以下敏感配置：
- `POSTGRES_PASSWORD`: 数据库密码
- `ADMIN_TOKEN`: 管理接口令牌

3. **启动服务**

```bash
docker compose up -d --build
```

4. **验证部署**

```bash
# 检查服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 访问服务
# Web 控制台: http://localhost:3000
# API 文档: http://localhost:8000/docs
# Grafana: http://localhost:3001
```

### 本地开发环境

对于需要频繁修改代码的开发者，推荐使用本地开发模式：

1. **安装 Python 依赖**

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖
```

2. **启动基础设施服务**

```bash
# 只启动 Redis 和 TimescaleDB
docker compose up -d redis timescaledb
```

3. **本地运行后端**

```bash
# 修改 .env 中的连接地址为 localhost
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql://sentinel:change-me@localhost:5432/sentinelperp

# 运行数据采集服务
python -m backend.collector

# 运行 API 服务
python -m backend.api
```

4. **本地运行前端**

```bash
cd frontend
npm install
npm run dev
```

---

## 项目结构

```
SentinelPerp/
├── backend/                    # 后端服务
│   ├── collector/              # 数据采集模块
│   │   ├── __init__.py
│   │   ├── cryptofeed_wrapper.py   # Cryptofeed 封装
│   │   ├── instrument_discovery.py # 合约发现
│   │   ├── deduplication.py        # 去重引擎
│   │   └── quality_monitor.py      # 质量监控
│   ├── storage/                # 存储层
│   │   ├── __init__.py
│   │   ├── redis_client.py         # Redis 客户端
│   │   ├── timescale_client.py     # TimescaleDB 客户端
│   │   └── models.py               # 数据模型
│   ├── api/                    # API 服务
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI 应用
│   │   ├── routes/                 # API 路由
│   │   │   ├── health.py
│   │   │   ├── instruments.py
│   │   │   ├── trades.py
│   │   │   ├── candles.py
│   │   │   ├── funding.py
│   │   │   └── quality.py
│   │   └── schemas.py              # Pydantic 模型
│   ├── config/                 # 配置管理
│   │   ├── __init__.py
│   │   └── settings.py             # 环境变量加载
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── logger.py               # 日志配置
│       └── metrics.py              # 指标收集
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   ├── pages/              # 页面
│   │   ├── api/                # API 客户端
│   │   └── utils/              # 工具函数
│   ├── package.json
│   └── vite.config.js          # 构建配置
├── docker/                     # Docker 配置
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── grafana/                # Grafana 配置
│       └── dashboards/
├── scripts/                    # 运维脚本
│   ├── init_db.sql             # 数据库初始化
│   ├── backup.sh               # 备份脚本
│   └── health_check.sh         # 健康检查
├── tests/                      # 测试
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   └── fixtures/               # 测试数据
├── docs/                       # 文档
│   ├── DEVELOPMENT.md          # 开发文档（本文档）
│   ├── milestone-1.md          # M1 里程碑详细设计
│   ├── API.md                  # API 文档
│   └── DEPLOYMENT.md           # 部署文档
├── .env.example                # 环境变量模板
├── .gitignore
├── docker-compose.yml          # Docker Compose 配置
├── requirements.txt            # Python 依赖
├── requirements-dev.txt        # 开发依赖
└── README.md                   # 项目说明
```

---

## 核心组件

### 1. 数据采集层（Collector）

#### Cryptofeed 封装

```python
# backend/collector/cryptofeed_wrapper.py

from cryptofeed import FeedHandler
from cryptofeed.defines import TRADES, L2_BOOK, FUNDING, OPEN_INTEREST, LIQUIDATIONS
from cryptofeed.exchanges import OKX

class CryptofeedWrapper:
    """
    Cryptofeed 框架的封装层，负责：
    - WebSocket 连接管理
    - 数据回调处理
    - 异常重连
    """
    
    def __init__(self, config):
        self.config = config
        self.feed_handler = FeedHandler()
        
    async def setup_feeds(self, symbols):
        """配置数据源订阅"""
        self.feed_handler.add_feed(
            OKX(
                symbols=symbols,
                channels=[TRADES, L2_BOOK, FUNDING, OPEN_INTEREST, LIQUIDATIONS],
                callbacks={
                    TRADES: self.on_trade,
                    L2_BOOK: self.on_book,
                    FUNDING: self.on_funding,
                    OPEN_INTEREST: self.on_open_interest,
                    LIQUIDATIONS: self.on_liquidation,
                }
            )
        )
    
    async def on_trade(self, trade, receipt_timestamp):
        """交易数据回调"""
        # 数据标准化 -> 质量检查 -> 去重 -> 存储
        pass
```

#### 合约发现服务

```python
# backend/collector/instrument_discovery.py

class InstrumentDiscovery:
    """
    定期发现 OKX USDT 永续合约
    - 每 300 秒刷新一次
    - 过滤规则: *-USDT-SWAP
    - 自动订阅新合约
    """
    
    async def discover_instruments(self):
        """
        从 OKX REST API 获取所有 USDT 永续合约
        返回: List[Instrument]
        """
        pass
    
    async def refresh_subscriptions(self):
        """更新 Cryptofeed 订阅列表"""
        pass
```

#### 去重引擎

```python
# backend/collector/deduplication.py

class DeduplicationEngine:
    """
    双模式去重引擎
    - Memory mode: 内存哈希表（快速但不持久）
    - Dual mode: 内存 + Redis（推荐）
    - 60 分钟时间桶
    - 24 小时 TTL
    """
    
    def __init__(self, mode: str, redis_client):
        self.mode = mode  # "memory" or "dual"
        self.redis = redis_client
        self.memory_cache = {}
    
    def is_duplicate(self, data_type: str, key: str) -> bool:
        """检查是否重复"""
        pass
    
    def mark_seen(self, data_type: str, key: str, ttl: int = 86400):
        """标记已处理"""
        pass
```

#### 质量监控器

```python
# backend/collector/quality_monitor.py

class QualityMonitor:
    """
    数据质量实时监控
    - 延迟检测: max 5000ms
    - 乱序容忍: 2000ms
    - 陈旧度: 15 秒阈值
    - 缺口检测: 连续性验证
    """
    
    def check_latency(self, receipt_ts, exchange_ts) -> bool:
        """检查延迟"""
        latency_ms = (receipt_ts - exchange_ts) * 1000
        return latency_ms <= self.config.TRADE_MAX_LATENCY_MS
    
    def check_staleness(self, last_ts, current_ts) -> bool:
        """检查陈旧度"""
        gap = current_ts - last_ts
        return gap <= self.config.TRADE_STALE_SECONDS
    
    def detect_gap(self, symbol: str, last_trade_id: int, current_trade_id: int):
        """检测交易 ID 缺口"""
        if current_trade_id - last_trade_id > 1:
            self.log_gap(symbol, last_trade_id, current_trade_id)
```

### 2. 存储层（Storage）

#### Redis 客户端

```python
# backend/storage/redis_client.py

class RedisClient:
    """
    Redis 实时数据层
    - 最新市场状态
    - 去重缓存
    - 质量指标
    """
    
    async def set_latest_trade(self, symbol: str, trade: dict):
        """存储最新交易"""
        key = f"latest:trade:{symbol}"
        await self.redis.set(key, json.dumps(trade), ex=3600)
    
    async def get_market_state(self, symbol: str) -> dict:
        """获取市场实时状态"""
        pass
```

#### TimescaleDB 客户端

```python
# backend/storage/timescale_client.py

class TimescaleClient:
    """
    TimescaleDB 历史数据层
    - 时序数据存储
    - 自动分区
    - 保留策略: 详细 3 天，聚合 90 天
    """
    
    async def insert_trades(self, trades: List[Trade]):
        """批量插入交易记录"""
        pass
    
    async def query_candles(self, symbol: str, start: datetime, end: datetime) -> List[Candle]:
        """查询 K 线数据"""
        pass
```

### 3. API 层

#### FastAPI 主应用

```python
# backend/api/main.py

from fastapi import FastAPI
from backend.api.routes import health, instruments, trades, candles, funding, quality

app = FastAPI(
    title="SentinelPerp API",
    version="0.1.0",
    description="加密货币市场数据采集与监控系统"
)

app.include_router(health.router, tags=["Health"])
app.include_router(instruments.router, prefix="/api/v1", tags=["Instruments"])
app.include_router(trades.router, prefix="/api/v1", tags=["Trades"])
app.include_router(candles.router, prefix="/api/v1", tags=["Candles"])
app.include_router(funding.router, prefix="/api/v1", tags=["Funding"])
app.include_router(quality.router, prefix="/api/v1", tags=["Quality"])
```

#### 示例路由

```python
# backend/api/routes/trades.py

from fastapi import APIRouter, Query
from datetime import datetime
from typing import List

router = APIRouter()

@router.get("/trades/{symbol}")
async def get_trades(
    symbol: str,
    start: datetime = Query(...),
    end: datetime = Query(...),
    limit: int = Query(1000, le=10000)
) -> List[TradeSchema]:
    """
    获取历史交易记录
    
    参数:
    - symbol: 交易对，如 BTC-USDT-SWAP
    - start: 开始时间（UTC）
    - end: 结束时间（UTC）
    - limit: 最大返回数量（<=10000）
    """
    pass
```

---

## 数据流

### 交易数据流（Trades）

```
OKX WebSocket
    │
    ├─ Raw Trade Data
    │   ├─ symbol: "BTC-USDT-SWAP"
    │   ├─ price: 67500.5
    │   ├─ amount: 0.15
    │   ├─ side: "buy"
    │   ├─ timestamp: 1698674321.456
    │   └─ trade_id: "1234567890"
    │
    ▼
[Data Normalization]
    │
    ├─ Standardized Trade
    │   ├─ exchange: "okx"
    │   ├─ symbol: "BTC-USDT-SWAP"
    │   ├─ price: Decimal("67500.5")
    │   ├─ quantity: Decimal("0.15")
    │   ├─ side: "buy"
    │   ├─ timestamp: datetime(...)
    │   ├─ trade_id: "1234567890"
    │   └─ receipt_timestamp: datetime(...)
    │
    ▼
[Quality Check]
    │
    ├─ Latency: 245ms ✓
    ├─ Out-of-order: No ✓
    └─ Staleness: 0.5s ✓
    │
    ▼
[Deduplication]
    │
    ├─ Key: "okx:BTC-USDT-SWAP:1234567890"
    ├─ Check Memory Cache: Not Found ✓
    ├─ Check Redis: Not Found ✓
    └─ Mark as Seen (TTL: 24h)
    │
    ▼
[Parallel Write]
    │
    ├─ Redis
    │   └─ Key: "latest:trade:BTC-USDT-SWAP"
    │       └─ Value: {...trade_data...}
    │
    └─ TimescaleDB
        └─ Table: trades
            └─ INSERT INTO trades VALUES (...)
    │
    ▼
[Consumers]
    │
    ├─ API Service (查询接口)
    ├─ Web Console (实时展示)
    └─ Quality Dashboard (监控指标)
```

### 订单簿数据流（L2 Order Book）

```
OKX WebSocket
    │
    ├─ L2 Book Update
    │   ├─ symbol: "BTC-USDT-SWAP"
    │   ├─ bids: [[67500.0, 1.5], [67499.5, 2.3], ...]
    │   ├─ asks: [[67500.5, 1.2], [67501.0, 3.1], ...]
    │   └─ timestamp: 1698674321.456
    │
    ▼
[Book Manager]
    │
    ├─ Update Local Order Book
    ├─ Calculate Depth
    │   ├─ Bid depth (top 10): 15.6 BTC
    │   └─ Ask depth (top 10): 18.3 BTC
    ├─ Calculate Imbalance
    │   └─ Imbalance ratio: -0.08 (slight ask pressure)
    │
    ▼
[Periodic Snapshot]
    │
    └─ Every 60 seconds
        │
        ├─ Redis: Store latest book state
        └─ TimescaleDB: Insert compressed snapshot
```

### 资金费率数据流（Funding）

```
OKX WebSocket / REST API
    │
    ├─ Funding Rate Update
    │   ├─ symbol: "BTC-USDT-SWAP"
    │   ├─ funding_rate: 0.0001
    │   ├─ next_funding_time: "2024-10-31T00:00:00Z"
    │   └─ timestamp: 1698674321
    │
    ▼
[Storage]
    │
    ├─ TimescaleDB: Insert funding_rates
    └─ Redis: Cache latest rate
    │
    ▼
[Feature Calculation]
    │
    └─ 7-day funding percentile
        └─ Used in Market State (M2)
```

---

## 开发规范

### 代码风格

- **Python**: 遵循 PEP 8，使用 `black` 格式化，`flake8` 检查
- **JavaScript/TypeScript**: 使用 Prettier + ESLint
- **命名约定**:
  - 函数/变量: snake_case
  - 类: PascalCase
  - 常量: UPPER_SNAKE_CASE

### Git 工作流

1. **分支策略**
   - `main`: 生产稳定分支
   - `develop`: 开发主分支
   - `feature/*`: 功能分支
   - `bugfix/*`: 修复分支

2. **提交规范**

遵循 Conventional Commits：

```
feat: 添加交易数据去重功能
fix: 修复 TimescaleDB 连接超时问题
docs: 更新开发文档
test: 添加质量监控单元测试
refactor: 重构 Redis 客户端
chore: 升级 Cryptofeed 到 2.5.0
```

3. **Pull Request 流程**
   - 从 `develop` 创建 feature 分支
   - 完成功能后提交 PR 到 `develop`
   - 至少一名审查者通过
   - 通过 CI 测试
   - 合并后删除 feature 分支

### 日志规范

使用结构化日志，统一格式：

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "trade_received",
    symbol="BTC-USDT-SWAP",
    price=67500.5,
    quantity=0.15,
    latency_ms=245
)

logger.warning(
    "quality_check_failed",
    symbol="ETH-USDT-SWAP",
    reason="excessive_latency",
    latency_ms=6200,
    threshold_ms=5000
)
```

日志级别：
- `DEBUG`: 详细调试信息（本地开发）
- `INFO`: 正常业务流程（生产环境）
- `WARNING`: 异常但可恢复的情况
- `ERROR`: 错误需要关注
- `CRITICAL`: 严重错误需要立即处理

### 错误处理

1. **使用明确的异常类型**

```python
class DataQualityError(Exception):
    """数据质量检查失败"""
    pass

class DuplicateDataError(Exception):
    """重复数据"""
    pass

class StorageError(Exception):
    """存储层错误"""
    pass
```

2. **失败重试策略**

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def write_to_timescale(data):
    """写入 TimescaleDB，失败自动重试 3 次"""
    pass
```

### 配置管理

所有配置通过环境变量管理，使用 Pydantic 验证：

```python
# backend/config/settings.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    
    # OKX
    OKX_MARKET_FILTER: str = "*-USDT-SWAP"
    OKX_CHANNELS: str = "trades,candles,funding"
    
    # Redis
    REDIS_URL: str
    REDIS_MAXMEMORY: str = "1536mb"
    
    # Database
    DATABASE_URL: str
    
    # Quality
    TRADE_MAX_LATENCY_MS: int = 5000
    TRADE_STALE_SECONDS: int = 15
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 测试指南

### 测试结构

```
tests/
├── unit/                       # 单元测试
│   ├── test_deduplication.py
│   ├── test_quality_monitor.py
│   └── test_redis_client.py
├── integration/                # 集成测试
│   ├── test_collector_e2e.py
│   ├── test_api_endpoints.py
│   └── test_storage_pipeline.py
└── fixtures/                   # 测试数据
    ├── sample_trades.json
    └── sample_orderbook.json
```

### 单元测试示例

```python
# tests/unit/test_deduplication.py

import pytest
from backend.collector.deduplication import DeduplicationEngine

@pytest.fixture
def dedup_engine():
    return DeduplicationEngine(mode="memory", redis_client=None)

def test_first_time_not_duplicate(dedup_engine):
    """首次出现的数据不应被标记为重复"""
    assert not dedup_engine.is_duplicate("trade", "BTC-USDT-SWAP:123456")

def test_second_time_is_duplicate(dedup_engine):
    """第二次出现的数据应被标记为重复"""
    key = "BTC-USDT-SWAP:123456"
    dedup_engine.mark_seen("trade", key)
    assert dedup_engine.is_duplicate("trade", key)

def test_different_buckets_not_duplicate(dedup_engine):
    """不同时间桶的相同数据不应被视为重复"""
    # 实现测试逻辑
    pass
```

### 集成测试示例

```python
# tests/integration/test_api_endpoints.py

from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)

def test_health_check():
    """测试健康检查接口"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_instruments():
    """测试获取合约列表"""
    response = client.get("/api/v1/instruments")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "symbol" in data[0]
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行指定模块
pytest tests/unit/test_deduplication.py

# 运行并显示覆盖率
pytest --cov=backend --cov-report=html

# 运行并输出详细信息
pytest -v -s

# 只运行标记的测试
pytest -m "not slow"
```

### 性能测试

```python
# tests/performance/test_dedup_throughput.py

import time
from backend.collector.deduplication import DeduplicationEngine

def test_dedup_throughput():
    """测试去重引擎吞吐量"""
    engine = DeduplicationEngine(mode="memory", redis_client=None)
    
    num_items = 100000
    start = time.time()
    
    for i in range(num_items):
        key = f"trade:{i}"
        engine.is_duplicate("trade", key)
        engine.mark_seen("trade", key)
    
    elapsed = time.time() - start
    throughput = num_items / elapsed
    
    print(f"Throughput: {throughput:.2f} ops/s")
    assert throughput > 10000  # 期望 >10k ops/s
```

---

## 部署指南

### 生产环境部署检查清单

- [ ] 修改 `.env` 中的敏感配置（密码、令牌）
- [ ] 配置数据持久化卷（避免容器重启丢失数据）
- [ ] 设置合理的资源限制（CPU、内存）
- [ ] 配置日志轮转和归档
- [ ] 启用 HTTPS（使用 Nginx/Caddy 反向代理）
- [ ] 设置监控告警（Prometheus + Grafana）
- [ ] 配置数据库备份策略
- [ ] 验证网络连接（防火墙、OKX API 可达性）

### Docker Compose 生产配置

```yaml
# docker-compose.prod.yml

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 1536mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'

  timescaledb:
    image: timescale/timescaledb:latest-pg15
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - timescale-data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'

  collector:
    build: .
    restart: unless-stopped
    depends_on:
      - redis
      - timescaledb
    env_file: .env
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'

  api:
    build: .
    restart: unless-stopped
    depends_on:
      - redis
      - timescaledb
    ports:
      - "8000:8000"
    env_file: .env
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

volumes:
  redis-data:
  timescale-data:
```

### 数据库迁移

```sql
-- scripts/init_db.sql

-- 启用 TimescaleDB 扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 创建交易表
CREATE TABLE trades (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    trade_id VARCHAR(100) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL
);

-- 转换为超表（时序数据）
SELECT create_hypertable('trades', 'time');

-- 创建索引
CREATE INDEX idx_trades_symbol_time ON trades (symbol, time DESC);
CREATE INDEX idx_trades_trade_id ON trades (trade_id);

-- 设置数据保留策略（3 天详细数据）
SELECT add_retention_policy('trades', INTERVAL '3 days');

-- 创建 K 线表
CREATE TABLE candles (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- 1m, 5m, 1h, 1d
    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 8) NOT NULL
);

SELECT create_hypertable('candles', 'time');
CREATE INDEX idx_candles_symbol_interval_time ON candles (symbol, interval, time DESC);

-- 创建资金费率表
CREATE TABLE funding_rates (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    funding_rate NUMERIC(10, 8) NOT NULL,
    next_funding_time TIMESTAMPTZ NOT NULL
);

SELECT create_hypertable('funding_rates', 'time');

-- 创建持仓量表
CREATE TABLE open_interest (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    open_interest NUMERIC(20, 8) NOT NULL
);

SELECT create_hypertable('open_interest', 'time');

-- 创建清算表
CREATE TABLE liquidations (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    price NUMERIC(20, 8) NOT NULL
);

SELECT create_hypertable('liquidations', 'time');

-- 创建质量日志表
CREATE TABLE quality_logs (
    time TIMESTAMPTZ NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    issue_type VARCHAR(50) NOT NULL,  -- latency, staleness, gap, out_of_order
    severity VARCHAR(20) NOT NULL,    -- warning, error
    details JSONB
);

SELECT create_hypertable('quality_logs', 'time');
SELECT add_retention_policy('quality_logs', INTERVAL '7 days');
```

### 备份与恢复

```bash
# scripts/backup.sh

#!/bin/bash

# 配置
BACKUP_DIR="/var/backups/sentinelperp"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份 PostgreSQL
docker compose exec -T timescaledb pg_dump -U sentinel sentinelperp | \
    gzip > $BACKUP_DIR/db_backup_$DATE.sql.gz

# 备份 Redis
docker compose exec -T redis redis-cli SAVE
docker cp sentinelperp-redis-1:/data/dump.rdb $BACKUP_DIR/redis_backup_$DATE.rdb

# 保留最近 7 天的备份
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.rdb" -mtime +7 -delete

echo "Backup completed: $DATE"
```

### 监控配置

推荐使用 Prometheus + Grafana 进行监控。

**关键指标**：
- 数据采集速率（trades/s, books/s）
- 数据质量指标（延迟、陈旧度、缺口数）
- 去重命中率
- 存储写入延迟
- Redis 内存使用率
- TimescaleDB 连接数
- API 响应时间

**告警规则**：
- 数据采集中断 > 60 秒
- 数据延迟 > 10 秒
- Redis 内存使用 > 90%
- 数据库连接数 > 80%
- API 错误率 > 5%

---

## 故障排查

### 常见问题

#### 1. 数据采集中断

**症状**：Web 控制台显示某些交易对长时间无新数据

**排查步骤**：
```bash
# 检查采集服务日志
docker compose logs -f collector

# 检查 OKX API 连通性
curl -I https://www.okx.com

# 检查 WebSocket 连接状态
docker compose exec collector python -c "
from backend.collector.cryptofeed_wrapper import CryptofeedWrapper
# 查看连接状态
"
```

**可能原因**：
- OKX API 限流
- 网络连接问题
- 订阅配置错误
- 内存不足导致进程崩溃

#### 2. Redis 内存溢出

**症状**：`OOM command not allowed when used memory > 'maxmemory'`

**解决方案**：
```bash
# 检查 Redis 内存使用
docker compose exec redis redis-cli INFO memory

# 清理过期键
docker compose exec redis redis-cli FLUSHDB

# 调整 maxmemory 配置（.env）
REDIS_MAXMEMORY=2048mb

# 重启 Redis
docker compose restart redis
```

#### 3. TimescaleDB 连接超时

**症状**：API 查询超时或失败

**排查步骤**：
```bash
# 检查数据库连接数
docker compose exec timescaledb psql -U sentinel -d sentinelperp -c \
    "SELECT count(*) FROM pg_stat_activity;"

# 检查慢查询
docker compose exec timescaledb psql -U sentinel -d sentinelperp -c \
    "SELECT query, query_start FROM pg_stat_activity WHERE state = 'active';"

# 检查表大小
docker compose exec timescaledb psql -U sentinel -d sentinelperp -c \
    "SELECT pg_size_pretty(pg_total_relation_size('trades'));"
```

**优化措施**：
- 增加连接池大小
- 优化查询索引
- 调整数据保留策略
- 升级硬件资源

#### 4. 数据质量问题

**症状**：质量日志中出现大量告警

**排查步骤**：
```sql
-- 查询最近 1 小时的质量问题
SELECT 
    issue_type, 
    COUNT(*) as count,
    AVG((details->>'latency_ms')::float) as avg_latency
FROM quality_logs
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY issue_type
ORDER BY count DESC;
```

**可能原因**：
- 网络波动
- 交易所数据源问题
- 系统时钟不同步
- 计算资源不足

### 日志分析

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f collector

# 过滤错误日志
docker compose logs collector | grep ERROR

# 统计日志中的告警数量
docker compose logs collector --since 1h | grep WARNING | wc -l
```

### 性能分析

```bash
# 查看容器资源使用
docker stats

# 查看 Python 进程性能
docker compose exec collector python -m cProfile -s cumtime backend/collector/main.py

# 查看数据库查询性能
docker compose exec timescaledb psql -U sentinel -d sentinelperp -c \
    "EXPLAIN ANALYZE SELECT * FROM trades WHERE symbol = 'BTC-USDT-SWAP' 
     AND time > NOW() - INTERVAL '1 hour';"
```

---

## 贡献指南

### 如何贡献

1. **Fork 仓库并创建分支**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **编写代码并添加测试**
   - 确保新功能有对应的单元测试
   - 保持测试覆盖率 > 80%

3. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add my new feature"
   ```

4. **推送并创建 Pull Request**
   ```bash
   git push origin feature/my-new-feature
   ```

### 代码审查标准

- [ ] 代码符合项目风格规范
- [ ] 所有测试通过
- [ ] 新功能有文档说明
- [ ] 提交信息清晰
- [ ] 无明显性能问题
- [ ] 无安全隐患

### 开发优先级

**M1 阶段需要帮助的领域**：
1. 前端 Web 控制台开发
2. Grafana Dashboard 配置
3. 性能优化和压力测试
4. 文档完善
5. CI/CD 流程搭建

---

## 参考资源

### 官方文档

- [Cryptofeed](https://github.com/bmoscon/cryptofeed): 市场数据采集框架
- [FastAPI](https://fastapi.tiangolo.com/): API 框架
- [TimescaleDB](https://docs.timescale.com/): 时序数据库
- [OKX API](https://www.okx.com/docs-v5/en/): 交易所 API 文档

### 相关项目

- [Nautilus Trader](https://nautilustrader.io/): 交易执行框架（M5 阶段）
- [ccxt](https://github.com/ccxt/ccxt): 多交易所接入库
- [Freqtrade](https://www.freqtrade.io/): 量化交易框架

### 社区

- GitHub Issues: 问题反馈和功能建议
- Discord/Slack: 实时交流（待建立）

---

## 附录

### 环境变量完整说明

| 变量名 | 说明 | 默认值 | 示例 |
|--------|------|--------|------|
| `APP_ENV` | 运行环境 | `development` | `production` |
| `LOG_LEVEL` | 日志级别 | `INFO` | `DEBUG` |
| `OKX_MARKET_FILTER` | 合约过滤规则 | `*-USDT-SWAP` | `BTC-USDT-SWAP` |
| `REDIS_URL` | Redis 连接地址 | - | `redis://localhost:6379/0` |
| `DATABASE_URL` | PostgreSQL 连接地址 | - | `postgresql://user:pass@host:5432/db` |
| `TRADE_MAX_LATENCY_MS` | 最大允许延迟 | `5000` | `3000` |
| `TRADE_STALE_SECONDS` | 数据陈旧阈值 | `15` | `30` |
| `DEDUP_MODE` | 去重模式 | `dual` | `memory` |

### 数据库表结构

详见 `scripts/init_db.sql`

### API 端点清单

详见 `docs/API.md`（待创建）

---

**文档版本**: v0.1.0  
**最后更新**: 2024-10-30  
**维护者**: SentinelPerp 开发团队
