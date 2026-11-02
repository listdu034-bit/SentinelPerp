# 市场特征数据层设计文档

## 目录

- [概述](#概述)
- [数据分类](#数据分类)
- [数据模型](#数据模型)
- [特征计算服务](#特征计算服务)
- [数据库设计](#数据库设计)
- [质量保证](#质量保证)
- [API 设计](#api-设计)
- [前端组件](#前端组件)
- [实施路线图](#实施路线图)

---

## 概述

市场特征数据层是 SentinelPerp 的**核心中间层**，位于原始数据采集和上层应用之间。它的职责是：

1. **从原始 P0 数据计算派生特征**
2. **提供清洗后的、结构化的市场特征数据**
3. **为特征识别、机会发现等上层功能提供统一数据源**

### 架构位置

```
┌─────────────────────────────────────────────────────────┐
│  原始数据层 (P0)                                         │
│  Trades | Candles | OI | Funding | OrderBook | Liq     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  市场特征数据层（本文档）                                │
│  ┌─────────────────────────────────────────────────┐   │
│  │  MarketFeatureCalculator                        │   │
│  │  - 每分钟计算一次                                │   │
│  │  - 聚合原始数据                                  │   │
│  │  - 计算派生指标                                  │   │
│  │  - 评估数据质量                                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  输出: market_features_1m 表（干净的结构化数据）        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  上层应用                                                │
│  - 涨跌幅榜单                                            │
│  - 特征识别                                              │
│  - 机会发现                                              │
│  - 告警系统                                              │
└─────────────────────────────────────────────────────────┘
```

### 核心价值

- ✅ **数据质量保证**：每条记录都有质量评分
- ✅ **统一数据接口**：上层应用不直接访问原始数据
- ✅ **计算复用**：避免重复计算相同指标
- ✅ **易于调试**：数据结构清晰，便于验证
- ✅ **支持时间序列分析**：规整的分钟级时间序列

---

## 数据分类

市场特征数据分为 **7 大类**，覆盖加密货币市场的所有关键维度：

### 数据类别汇总

| 类别 | 主要字段 | 核心用途 | 对特征识别的作用 |
|------|---------|---------|-----------------|
| **1. 价格与成交量** | OHLC、Volume、Spot Price、Perp Price | 判断价格变化、成交活跃程度 | 识别趋势、波动率、突破 |
| **2. Trade / Order Flow** | Buy/Sell Notional、Delta、CVD、Trade Count | 判断主动买卖压力 | **CVD 是核心**，资金流向 |
| **3. Open Interest** | OI、OI USD、OI Delta、OI Change % | 观察未平仓合约规模变化 | 结合价格判断多空力量 |
| **4. Funding / Basis** | Funding Rate、Basis、Basis bps | 观察永续与现货的偏离 | 识别过度拥挤和套利机会 |
| **5. L2 OrderBook** | Bid/Ask Depth、OBI、Spread | 衡量盘口流动性和不平衡 | **OBI 是核心**，买卖盘失衡 |
| **6. Liquidation** | Long/Short Liquidation USD、Count、Imbalance | 观察强制平仓事件 | **Squeeze 检测的关键** |
| **7. 数据质量** | Coverage、Quality、Age、Final、Revision | 判断特征是否可信 | **过滤低质量数据** |

### 示例数据

一条 BTC-USDT-SWAP 的 1 分钟特征记录：

```
BTC-USDT-SWAP | 2026-10-30 12:30:00 UTC | 1 分钟
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
价格变化:         +0.42%
主动买卖 Delta:   +$240,000
OI 变化:          +0.18%
资金费率:         +0.010%
盘口 OBI:         +0.21
空头清算金额:     $85,000
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
数据质量评分:     0.97 ✓ Final
```

---

## 数据模型

### Python 数据模型

```python
# backend/models/market_feature.py

from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class MarketFeature1Min(BaseModel):
    """
    1 分钟市场特征数据模型（清洗后）
    
    这是特征识别的核心数据源，每个字段都经过质量验证
    """
    
    # ============ 元数据 ============
    symbol: str = Field(..., description="合约代码，如 BTC-USDT-SWAP")
    timestamp: datetime = Field(..., description="时间戳（分钟对齐）")
    interval: str = Field(default="1m", description="时间周期")
    
    # ============ 1. 价格与成交量 ============
    price_open: Optional[Decimal] = Field(None, description="开盘价")
    price_high: Optional[Decimal] = Field(None, description="最高价")
    price_low: Optional[Decimal] = Field(None, description="最低价")
    price_close: Optional[Decimal] = Field(None, description="收盘价")
    volume: Optional[Decimal] = Field(None, description="成交量（合约张数）")
    volume_usd: Optional[Decimal] = Field(None, description="成交量（美元）")
    spot_price: Optional[Decimal] = Field(None, description="对应现货价格")
    perp_price: Optional[Decimal] = Field(None, description="永续价格")
    
    # 派生字段
    price_change_pct: Optional[float] = Field(None, description="价格变化百分比")
    volatility: Optional[float] = Field(None, description="波动率（high-low)/open")
    
    # ============ 2. Trade / Order Flow ============
    buy_volume_usd: Optional[Decimal] = Field(None, description="主动买入金额")
    sell_volume_usd: Optional[Decimal] = Field(None, description="主动卖出金额")
    delta_usd: Optional[Decimal] = Field(None, description="买卖差额（Delta）")
    cvd: Optional[Decimal] = Field(None, description="累计成交量差（CVD）")
    trade_count: Optional[int] = Field(None, description="交易笔数")
    
    # 派生字段
    buy_sell_ratio: Optional[float] = Field(None, description="买卖比")
    avg_trade_size_usd: Optional[Decimal] = Field(None, description="平均成交金额")
    
    # ============ 3. Open Interest ============
    oi: Optional[Decimal] = Field(None, description="持仓量（合约张数）")
    oi_usd: Optional[Decimal] = Field(None, description="持仓量（美元）")
    oi_delta: Optional[Decimal] = Field(None, description="OI 变化量")
    oi_change_pct: Optional[float] = Field(None, description="OI 变化百分比")
    
    # 派生字段
    oi_direction: Optional[str] = Field(
        None, 
        description="OI 方向性: long_build | long_unwind | short_build | short_unwind | neutral"
    )
    
    # ============ 4. Funding / Basis ============
    funding_rate: Optional[Decimal] = Field(None, description="资金费率")
    funding_rate_8h: Optional[Decimal] = Field(None, description="8小时资金费率")
    basis: Optional[Decimal] = Field(None, description="永续 - 现货")
    basis_bps: Optional[Decimal] = Field(None, description="Basis（基点）")
    
    # 派生字段
    funding_percentile: Optional[float] = Field(None, description="资金费率历史分位数（0-1）")
    basis_percentile: Optional[float] = Field(None, description="Basis 历史分位数（0-1）")
    
    # ============ 5. L2 OrderBook ============
    bid_depth_10: Optional[Decimal] = Field(None, description="前10档买单深度（USD）")
    ask_depth_10: Optional[Decimal] = Field(None, description="前10档卖单深度（USD）")
    obi: Optional[float] = Field(None, description="Order Book Imbalance（-1 到 1）")
    spread_bps: Optional[Decimal] = Field(None, description="买卖价差（基点）")
    
    # 派生字段
    liquidity_score: Optional[float] = Field(None, description="流动性评分（0-1）")
    
    # ============ 6. Liquidation ============
    long_liq_usd: Optional[Decimal] = Field(None, description="多单清算金额")
    short_liq_usd: Optional[Decimal] = Field(None, description="空单清算金额")
    liq_count: Optional[int] = Field(None, description="清算笔数")
    liq_imbalance: Optional[float] = Field(None, description="清算失衡度（-1 到 1）")
    
    # 派生字段：Squeeze 检测
    is_squeeze: Optional[bool] = Field(None, description="是否检测到挤压")
    squeeze_type: Optional[str] = Field(None, description="挤压类型: short_squeeze | long_liquidation | None")
    squeeze_intensity: Optional[float] = Field(None, description="挤压强度（0-1）")
    
    # ============ 7. 数据质量 ============
    coverage: float = Field(..., description="数据完整度（0-1）")
    quality: float = Field(..., description="质量评分（0-1）")
    age_seconds: int = Field(..., description="数据新鲜度（秒）")
    is_final: bool = Field(default=False, description="数据是否已确定（不会再修订）")
    revision_count: int = Field(default=0, description="修订次数")
    
    # 额外：数据来源追踪
    source_flags: int = Field(default=0, description="位标记，表示哪些数据源有效")
    missing_fields: List[str] = Field(default_factory=list, description="缺失的字段列表")
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat()
        }


class SourceFlags:
    """数据源标记位"""
    CANDLES = 1 << 0        # 0x01
    TRADES = 1 << 1         # 0x02
    OI = 1 << 2             # 0x04
    FUNDING = 1 << 3        # 0x08
    ORDERBOOK = 1 << 4      # 0x10
    LIQUIDATIONS = 1 << 5   # 0x20
    SPOT_PRICE = 1 << 6     # 0x40


class OIDirection:
    """OI 方向性分类"""
    LONG_BUILD = "long_build"           # OI 上升 + 价格上涨 = 多头建仓
    LONG_UNWIND = "long_unwind"         # OI 下降 + 价格下跌 = 多头平仓
    SHORT_BUILD = "short_build"         # OI 上升 + 价格下跌 = 空头建仓
    SHORT_UNWIND = "short_unwind"       # OI 下降 + 价格上涨 = 空头平仓
    NEUTRAL = "neutral"                 # 无明显方向
```

---

## 特征计算服务

### MarketFeatureCalculator

```python
# backend/services/market_feature_calculator.py

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import asyncio

from backend.models.market_feature import MarketFeature1Min, SourceFlags, OIDirection
from backend.storage.timescale_client import TimescaleClient
from backend.storage.redis_client import RedisClient
from backend.config.settings import settings


class MarketFeatureCalculator:
    """
    市场特征计算服务
    
    职责：
    1. 从原始 P0 数据计算 1 分钟特征
    2. 评估数据质量
    3. 存储到 market_features_1m 表
    """
    
    def __init__(self, db: TimescaleClient, redis: RedisClient):
        self.db = db
        self.redis = redis
    
    async def calculate_1m_feature(
        self, 
        symbol: str, 
        timestamp: datetime
    ) -> MarketFeature1Min:
        """
        计算指定时间点的 1 分钟特征
        
        Args:
            symbol: 合约代码，如 BTC-USDT-SWAP
            timestamp: 分钟对齐的时间戳
        
        Returns:
            MarketFeature1Min 对象
        """
        # 确保时间戳是分钟对齐的
        timestamp = timestamp.replace(second=0, microsecond=0)
        
        # 时间范围：[timestamp, timestamp + 1分钟)
        start_time = timestamp
        end_time = timestamp + timedelta(minutes=1)
        
        # 并发查询所有原始数据
        results = await asyncio.gather(
            self._get_candle_data(symbol, start_time, end_time),
            self._get_trade_data(symbol, start_time, end_time),
            self._get_oi_data(symbol, timestamp),
            self._get_funding_data(symbol, timestamp),
            self._get_orderbook_data(symbol, timestamp),
            self._get_liquidation_data(symbol, start_time, end_time),
            self._get_spot_price(symbol, timestamp),
            return_exceptions=True
        )
        
        candle_data, trade_data, oi_data, funding_data, orderbook_data, liq_data, spot_price = results
        
        # 计算各类特征
        price_features = self._calculate_price_features(candle_data, spot_price)
        flow_features = self._calculate_flow_features(trade_data, symbol, timestamp)
        oi_features = self._calculate_oi_features(oi_data, symbol, timestamp, price_features)
        funding_features = self._calculate_funding_features(funding_data, spot_price, price_features)
        orderbook_features = self._calculate_orderbook_features(orderbook_data)
        liq_features = self._calculate_liquidation_features(liq_data, symbol, timestamp)
        
        # 计算数据质量
        quality_metrics = self._calculate_quality_metrics(
            candle_data, trade_data, oi_data, funding_data, 
            orderbook_data, liq_data, spot_price, timestamp
        )
        
        # 组装最终特征对象
        feature = MarketFeature1Min(
            symbol=symbol,
            timestamp=timestamp,
            interval='1m',
            **(price_features or {}),
            **(flow_features or {}),
            **(oi_features or {}),
            **(funding_features or {}),
            **(orderbook_features or {}),
            **(liq_features or {}),
            **quality_metrics
        )
        
        return feature
    
    # ============ 数据查询方法 ============
    
    async def _get_candle_data(self, symbol: str, start_time: datetime, end_time: datetime) -> Optional[Dict]:
        """查询 1 分钟 K 线数据"""
        query = """
        SELECT time, open, high, low, close, volume, vol_ccy
        FROM candles
        WHERE symbol = $1 AND interval = '1m'
        AND time >= $2 AND time < $3
        ORDER BY time DESC
        LIMIT 1
        """
        result = await self.db.fetchrow(query, symbol, start_time, end_time)
        return dict(result) if result else None
    
    async def _get_trade_data(self, symbol: str, start_time: datetime, end_time: datetime) -> Optional[Dict]:
        """查询该分钟的所有交易数据"""
        query = """
        SELECT 
            COUNT(*) as trade_count,
            SUM(CASE WHEN side = 'buy' THEN quantity * price ELSE 0 END) as buy_volume_usd,
            SUM(CASE WHEN side = 'sell' THEN quantity * price ELSE 0 END) as sell_volume_usd,
            SUM(CASE WHEN side = 'buy' THEN quantity * price ELSE -quantity * price END) as delta_usd
        FROM trades
        WHERE symbol = $1 AND time >= $2 AND time < $3
        """
        result = await self.db.fetchrow(query, symbol, start_time, end_time)
        return dict(result) if result else None
    
    async def _get_oi_data(self, symbol: str, timestamp: datetime) -> Optional[Dict]:
        """查询最接近该时间点的持仓量数据"""
        query = """
        SELECT oi, oi_ccy, time
        FROM open_interest
        WHERE symbol = $1 AND time <= $2
        ORDER BY time DESC
        LIMIT 1
        """
        result = await self.db.fetchrow(query, symbol, timestamp + timedelta(minutes=1))
        return dict(result) if result else None
    
    async def _get_funding_data(self, symbol: str, timestamp: datetime) -> Optional[Dict]:
        """查询最近的资金费率"""
        query = """
        SELECT funding_rate, next_funding_rate, funding_time, time
        FROM funding_rates
        WHERE symbol = $1 AND time <= $2
        ORDER BY time DESC
        LIMIT 1
        """
        result = await self.db.fetchrow(query, symbol, timestamp + timedelta(minutes=1))
        return dict(result) if result else None
    
    async def _get_orderbook_data(self, symbol: str, timestamp: datetime) -> Optional[Dict]:
        """查询最接近该时间点的订单簿快照"""
        # 从 Redis 获取最新快照
        cache_key = f"orderbook:snapshot:{symbol}"
        cached = await self.redis.get(cache_key)
        if cached:
            return cached
        
        # 如果 Redis 没有，从数据库查询
        query = """
        SELECT asks, bids, time
        FROM orderbook_snapshots
        WHERE symbol = $1 AND time <= $2
        ORDER BY time DESC
        LIMIT 1
        """
        result = await self.db.fetchrow(query, symbol, timestamp + timedelta(minutes=1))
        return dict(result) if result else None
    
    async def _get_liquidation_data(self, symbol: str, start_time: datetime, end_time: datetime) -> Optional[Dict]:
        """查询该分钟的清算数据"""
        query = """
        SELECT 
            COUNT(*) as liq_count,
            SUM(CASE WHEN side = 'long' THEN quantity * price ELSE 0 END) as long_liq_usd,
            SUM(CASE WHEN side = 'short' THEN quantity * price ELSE 0 END) as short_liq_usd
        FROM liquidations
        WHERE symbol = $1 AND time >= $2 AND time < $3
        """
        result = await self.db.fetchrow(query, symbol, start_time, end_time)
        return dict(result) if result else None
    
    async def _get_spot_price(self, symbol: str, timestamp: datetime) -> Optional[Decimal]:
        """查询对应现货价格"""
        # 将永续合约代码转换为现货代码
        # BTC-USDT-SWAP -> BTC-USDT
        spot_symbol = symbol.replace('-SWAP', '')
        
        query = """
        SELECT close
        FROM candles
        WHERE symbol = $1 AND interval = '1m'
        AND time >= $2 AND time < $3
        ORDER BY time DESC
        LIMIT 1
        """
        result = await self.db.fetchval(
            query, 
            spot_symbol, 
            timestamp, 
            timestamp + timedelta(minutes=1)
        )
        return Decimal(str(result)) if result else None
    
    # ============ 特征计算方法 ============
    
    def _calculate_price_features(self, candle_data: Optional[Dict], spot_price: Optional[Decimal]) -> Dict:
        """计算价格与成交量特征"""
        if not candle_data:
            return {}
        
        o = Decimal(str(candle_data['open']))
        h = Decimal(str(candle_data['high']))
        l = Decimal(str(candle_data['low']))
        c = Decimal(str(candle_data['close']))
        vol = Decimal(str(candle_data['volume']))
        vol_usd = Decimal(str(candle_data['vol_ccy']))
        
        return {
            'price_open': o,
            'price_high': h,
            'price_low': l,
            'price_close': c,
            'volume': vol,
            'volume_usd': vol_usd,
            'spot_price': spot_price,
            'perp_price': c,
            'price_change_pct': float((c - o) / o * 100) if o > 0 else 0.0,
            'volatility': float((h - l) / o * 100) if o > 0 else 0.0
        }
    
    def _calculate_flow_features(
        self, 
        trade_data: Optional[Dict], 
        symbol: str, 
        timestamp: datetime
    ) -> Dict:
        """计算 Trade / Order Flow 特征"""
        if not trade_data or trade_data['trade_count'] == 0:
            return {}
        
        buy_vol = Decimal(str(trade_data['buy_volume_usd']))
        sell_vol = Decimal(str(trade_data['sell_volume_usd']))
        delta = Decimal(str(trade_data['delta_usd']))
        count = int(trade_data['trade_count'])
        
        # 获取 CVD（累计值）
        cvd = self._get_cvd(symbol, timestamp)
        
        return {
            'buy_volume_usd': buy_vol,
            'sell_volume_usd': sell_vol,
            'delta_usd': delta,
            'cvd': cvd,
            'trade_count': count,
            'buy_sell_ratio': float(buy_vol / sell_vol) if sell_vol > 0 else None,
            'avg_trade_size_usd': (buy_vol + sell_vol) / count if count > 0 else None
        }
    
    def _calculate_oi_features(
        self, 
        oi_data: Optional[Dict], 
        symbol: str, 
        timestamp: datetime,
        price_features: Dict
    ) -> Dict:
        """计算 Open Interest 特征"""
        if not oi_data:
            return {}
        
        current_oi = Decimal(str(oi_data['oi']))
        current_oi_ccy = Decimal(str(oi_data['oi_ccy']))
        
        # 获取上一分钟的 OI
        last_oi = self._get_last_oi(symbol, timestamp)
        
        oi_delta = current_oi - last_oi if last_oi else Decimal('0')
        oi_change_pct = float(oi_delta / last_oi * 100) if last_oi and last_oi > 0 else 0.0
        
        # 计算 OI 方向性
        oi_direction = self._classify_oi_direction(
            oi_change=float(oi_delta),
            price_change_pct=price_features.get('price_change_pct', 0.0)
        )
        
        # 计算 OI USD
        price_close = price_features.get('price_close')
        oi_usd = current_oi * price_close if price_close else None
        
        return {
            'oi': current_oi,
            'oi_usd': oi_usd,
            'oi_delta': oi_delta,
            'oi_change_pct': oi_change_pct,
            'oi_direction': oi_direction
        }
    
    def _calculate_funding_features(
        self, 
        funding_data: Optional[Dict],
        spot_price: Optional[Decimal],
        price_features: Dict
    ) -> Dict:
        """计算 Funding / Basis 特征"""
        if not funding_data:
            return {}
        
        funding_rate = Decimal(str(funding_data['funding_rate']))
        
        # OKX 每 8 小时结算一次，所以 8h 费率 = 单次费率 × 3
        funding_rate_8h = funding_rate * 3
        
        # 计算 Basis
        perp_price = price_features.get('price_close')
        basis = (perp_price - spot_price) if (perp_price and spot_price) else None
        basis_bps = float(basis / spot_price * 10000) if (basis and spot_price and spot_price > 0) else None
        
        # 计算资金费率历史分位数
        funding_percentile = self._get_funding_percentile(symbol, funding_rate)
        basis_percentile = self._get_basis_percentile(symbol, basis) if basis else None
        
        return {
            'funding_rate': funding_rate,
            'funding_rate_8h': funding_rate_8h,
            'basis': basis,
            'basis_bps': basis_bps,
            'funding_percentile': funding_percentile,
            'basis_percentile': basis_percentile
        }
    
    def _calculate_orderbook_features(self, orderbook_data: Optional[Dict]) -> Dict:
        """计算 L2 OrderBook 特征"""
        if not orderbook_data:
            return {}
        
        asks = orderbook_data['asks']  # [[price, size], ...]
        bids = orderbook_data['bids']
        
        # 前 10 档深度
        bid_depth_10 = sum(Decimal(bid[0]) * Decimal(bid[1]) for bid in bids[:10])
        ask_depth_10 = sum(Decimal(ask[0]) * Decimal(ask[1]) for ask in asks[:10])
        
        # 计算 OBI (Order Book Imbalance)
        obi = float((bid_depth_10 - ask_depth_10) / (bid_depth_10 + ask_depth_10)) if (bid_depth_10 + ask_depth_10) > 0 else 0.0
        
        # 计算价差（基点）
        best_bid = Decimal(bids[0][0])
        best_ask = Decimal(asks[0][0])
        spread_bps = float((best_ask - best_bid) / best_bid * 10000) if best_bid > 0 else None
        
        # 流动性评分（简化版）
        total_depth = bid_depth_10 + ask_depth_10
        liquidity_score = min(float(total_depth / 1_000_000), 1.0)  # 归一化到 0-1
        
        return {
            'bid_depth_10': bid_depth_10,
            'ask_depth_10': ask_depth_10,
            'obi': obi,
            'spread_bps': spread_bps,
            'liquidity_score': liquidity_score
        }
    
    def _calculate_liquidation_features(
        self, 
        liq_data: Optional[Dict],
        symbol: str,
        timestamp: datetime
    ) -> Dict:
        """计算 Liquidation 特征"""
        if not liq_data or liq_data['liq_count'] == 0:
            return {
                'long_liq_usd': Decimal('0'),
                'short_liq_usd': Decimal('0'),
                'liq_count': 0,
                'liq_imbalance': 0.0,
                'is_squeeze': False,
                'squeeze_type': None,
                'squeeze_intensity': 0.0
            }
        
        long_liq = Decimal(str(liq_data['long_liq_usd']))
        short_liq = Decimal(str(liq_data['short_liq_usd']))
        count = int(liq_data['liq_count'])
        
        # 清算失衡度
        total_liq = long_liq + short_liq
        liq_imbalance = float((short_liq - long_liq) / total_liq) if total_liq > 0 else 0.0
        
        # Squeeze 检测
        squeeze_result = self._detect_squeeze(symbol, timestamp, long_liq, short_liq)
        
        return {
            'long_liq_usd': long_liq,
            'short_liq_usd': short_liq,
            'liq_count': count,
            'liq_imbalance': liq_imbalance,
            'is_squeeze': squeeze_result['is_squeeze'],
            'squeeze_type': squeeze_result['squeeze_type'],
            'squeeze_intensity': squeeze_result['intensity']
        }
    
    # ============ 数据质量评估 ============
    
    def _calculate_quality_metrics(
        self,
        candle_data: Optional[Dict],
        trade_data: Optional[Dict],
        oi_data: Optional[Dict],
        funding_data: Optional[Dict],
        orderbook_data: Optional[Dict],
        liq_data: Optional[Dict],
        spot_price: Optional[Decimal],
        timestamp: datetime
    ) -> Dict:
        """
        计算数据质量指标
        
        Coverage = 有值的数据源数 / 总数据源数
        Quality = 数据源质量的加权平均
        """
        source_flags = 0
        quality_scores = []
        missing_fields = []
        
        # 检查各数据源
        if candle_data:
            source_flags |= SourceFlags.CANDLES
            quality_scores.append(1.0)
        else:
            missing_fields.append('candles')
        
        if trade_data and trade_data.get('trade_count', 0) > 0:
            source_flags |= SourceFlags.TRADES
            quality_scores.append(1.0)
        else:
            missing_fields.append('trades')
        
        if oi_data:
            source_flags |= SourceFlags.OI
            # 检查 OI 数据是否陈旧（超过 5 分钟）
            oi_age = (timestamp - oi_data['time']).total_seconds()
            oi_quality = 1.0 if oi_age < 300 else 0.5
            quality_scores.append(oi_quality)
        else:
            missing_fields.append('oi')
        
        if funding_data:
            source_flags |= SourceFlags.FUNDING
            quality_scores.append(1.0)
        else:
            missing_fields.append('funding')
        
        if orderbook_data:
            source_flags |= SourceFlags.ORDERBOOK
            quality_scores.append(1.0)
        else:
            missing_fields.append('orderbook')
        
        if liq_data:
            source_flags |= SourceFlags.LIQUIDATIONS
            quality_scores.append(1.0)
        # 清算数据可以为空（没有清算发生），不算缺失
        
        if spot_price:
            source_flags |= SourceFlags.SPOT_PRICE
            quality_scores.append(1.0)
        else:
            missing_fields.append('spot_price')
        
        # 计算 Coverage 和 Quality
        total_sources = 7  # 总共 7 个数据源
        coverage = len(quality_scores) / total_sources
        quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        
        # 计算 Age
        age_seconds = int((datetime.utcnow() - timestamp).total_seconds())
        
        # 判断是否 Final
        # 如果数据超过 2 分钟且质量稳定（>0.9），则认为是 final
        is_final = age_seconds > 120 and quality > 0.9
        
        return {
            'coverage': coverage,
            'quality': quality,
            'age_seconds': age_seconds,
            'is_final': is_final,
            'revision_count': 0,
            'source_flags': source_flags,
            'missing_fields': missing_fields
        }
    
    # ============ 辅助方法 ============
    
    def _get_cvd(self, symbol: str, timestamp: datetime) -> Decimal:
        """
        获取累计成交量差（CVD）
        
        CVD 是累计值，需要从历史数据累加
        这里简化处理，从 Redis 缓存获取
        """
        # TODO: 实现 CVD 累计逻辑
        # 可以在 Redis 中维护每个合约的 CVD
        cache_key = f"cvd:{symbol}:{timestamp.strftime('%Y%m%d')}"
        cached_cvd = self.redis.get(cache_key)
        return Decimal(cached_cvd) if cached_cvd else Decimal('0')
    
    def _get_last_oi(self, symbol: str, timestamp: datetime) -> Optional[Decimal]:
        """获取上一分钟的 OI"""
        # 从 Redis 缓存或数据库查询
        # 简化处理：查询前一分钟的 market_features_1m 表
        query = """
        SELECT oi
        FROM market_features_1m
        WHERE symbol = $1 AND time < $2
        ORDER BY time DESC
        LIMIT 1
        """
        result = self.db.fetchval(query, symbol, timestamp)
        return Decimal(str(result)) if result else None
    
    def _classify_oi_direction(self, oi_change: float, price_change_pct: float) -> str:
        """
        分类 OI 方向性
        
        规则：
        - OI 上升 + 价格上涨 = long_build（多头建仓）
        - OI 上升 + 价格下跌 = short_build（空头建仓）
        - OI 下降 + 价格上涨 = short_unwind（空头平仓/挤空）
        - OI 下降 + 价格下跌 = long_unwind（多头平仓/杀多）
        - 变化不明显 = neutral
        """
        oi_threshold = 0.05  # 0.05% 视为无变化
        price_threshold = 0.1  # 0.1% 视为无变化
        
        if abs(oi_change) < oi_threshold or abs(price_change_pct) < price_threshold:
            return OIDirection.NEUTRAL
        
        if oi_change > 0:
            return OIDirection.LONG_BUILD if price_change_pct > 0 else OIDirection.SHORT_BUILD
        else:
            return OIDirection.SHORT_UNWIND if price_change_pct > 0 else OIDirection.LONG_UNWIND
    
    def _get_funding_percentile(self, symbol: str, funding_rate: Decimal) -> Optional[float]:
        """计算资金费率在过去 30 天的分位数"""
        # TODO: 实现历史分位数计算
        # 从数据库查询过去 30 天的资金费率，计算分位数
        return None
    
    def _get_basis_percentile(self, symbol: str, basis: Decimal) -> Optional[float]:
        """计算 Basis 在过去 30 天的分位数"""
        # TODO: 实现历史分位数计算
        return None
    
    def _detect_squeeze(
        self, 
        symbol: str, 
        timestamp: datetime,
        long_liq_usd: Decimal,
        short_liq_usd: Decimal
    ) -> Dict:
        """
        检测 Squeeze（挤压）事件
        
        标准：
        - 5 分钟内清算量 > 正常水平的 10 倍
        - 单方向清算占比 > 80%
        """
        # 查询过去 5 分钟的清算数据
        # TODO: 实现完整的 Squeeze 检测逻辑
        
        total_liq = long_liq_usd + short_liq_usd
        if total_liq == 0:
            return {'is_squeeze': False, 'squeeze_type': None, 'intensity': 0.0}
        
        short_ratio = float(short_liq_usd / total_liq)
        long_ratio = float(long_liq_usd / total_liq)
        
        # 简化版判断
        if short_ratio > 0.8 and total_liq > 100000:  # $100K 阈值
            return {
                'is_squeeze': True,
                'squeeze_type': 'short_squeeze',
                'intensity': short_ratio
            }
        elif long_ratio > 0.8 and total_liq > 100000:
            return {
                'is_squeeze': True,
                'squeeze_type': 'long_liquidation',
                'intensity': long_ratio
            }
        else:
            return {'is_squeeze': False, 'squeeze_type': None, 'intensity': 0.0}
    
    # ============ 存储方法 ============
    
    async def save_feature(self, feature: MarketFeature1Min) -> bool:
        """保存特征到数据库"""
        query = """
        INSERT INTO market_features_1m (
            time, symbol,
            price_open, price_high, price_low, price_close, volume, volume_usd,
            spot_price, perp_price, price_change_pct, volatility,
            buy_volume_usd, sell_volume_usd, delta_usd, cvd, trade_count, buy_sell_ratio, avg_trade_size_usd,
            oi, oi_usd, oi_delta, oi_change_pct, oi_direction,
            funding_rate, funding_rate_8h, basis, basis_bps, funding_percentile, basis_percentile,
            bid_depth_10, ask_depth_10, obi, spread_bps, liquidity_score,
            long_liq_usd, short_liq_usd, liq_count, liq_imbalance, 
            is_squeeze, squeeze_type, squeeze_intensity,
            coverage, quality, age_seconds, is_final, revision_count, source_flags
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19,
            $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35,
            $36, $37, $38, $39, $40, $41, $42, $43, $44, $45, $46, $47, $48
        )
        ON CONFLICT (time, symbol) DO UPDATE SET
            price_close = EXCLUDED.price_close,
            quality = EXCLUDED.quality,
            is_final = EXCLUDED.is_final,
            revision_count = market_features_1m.revision_count + 1
        """
        
        try:
            await self.db.execute(query, 
                feature.timestamp, feature.symbol,
                feature.price_open, feature.price_high, feature.price_low, feature.price_close,
                feature.volume, feature.volume_usd, feature.spot_price, feature.perp_price,
                feature.price_change_pct, feature.volatility,
                feature.buy_volume_usd, feature.sell_volume_usd, feature.delta_usd, feature.cvd,
                feature.trade_count, feature.buy_sell_ratio, feature.avg_trade_size_usd,
                feature.oi, feature.oi_usd, feature.oi_delta, feature.oi_change_pct, feature.oi_direction,
                feature.funding_rate, feature.funding_rate_8h, feature.basis, feature.basis_bps,
                feature.funding_percentile, feature.basis_percentile,
                feature.bid_depth_10, feature.ask_depth_10, feature.obi, feature.spread_bps, feature.liquidity_score,
                feature.long_liq_usd, feature.short_liq_usd, feature.liq_count, feature.liq_imbalance,
                feature.is_squeeze, feature.squeeze_type, feature.squeeze_intensity,
                feature.coverage, feature.quality, feature.age_seconds, feature.is_final,
                feature.revision_count, feature.source_flags
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save feature: {symbol} {timestamp} - {e}")
            return False
```

### 定时任务

```python
# backend/tasks/feature_calculator_task.py

import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services.market_feature_calculator import MarketFeatureCalculator
from backend.storage.timescale_client import TimescaleClient
from backend.storage.redis_client import RedisClient
from backend.config.settings import settings
from backend.utils.logger import logger


class FeatureCalculatorTask:
    """
    特征计算定时任务
    
    每分钟执行一次，计算所有活跃合约的市场特征
    """
    
    def __init__(self):
        self.db = TimescaleClient()
        self.redis = RedisClient()
        self.calculator = MarketFeatureCalculator(self.db, self.redis)
        self.scheduler = AsyncIOScheduler()
    
    async def start(self):
        """启动定时任务"""
        # 每分钟的第 5 秒执行（给数据采集留出时间）
        self.scheduler.add_job(
            self.calculate_all_features,
            'cron',
            second=5,
            id='feature_calculator',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Feature calculator task started")
    
    async def calculate_all_features(self):
        """计算所有合约的特征"""
        # 计算上一分钟的特征（因为当前分钟还未完成）
        timestamp = datetime.utcnow().replace(second=0, microsecond=0) - timedelta(minutes=1)
        
        # 获取所有活跃合约
        symbols = await self._get_active_symbols()
        
        logger.info(f"Calculating features for {len(symbols)} symbols at {timestamp}")
        
        # 并发计算所有合约的特征
        tasks = [
            self.calculator.calculate_1m_feature(symbol, timestamp)
            for symbol in symbols
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 保存到数据库
        save_tasks = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to calculate feature for {symbol}: {result}")
            else:
                save_tasks.append(self.calculator.save_feature(result))
        
        if save_tasks:
            save_results = await asyncio.gather(*save_tasks, return_exceptions=True)
            success_count = sum(1 for r in save_results if r is True)
            logger.info(f"Saved {success_count}/{len(save_tasks)} features")
    
    async def _get_active_symbols(self) -> list:
        """获取所有活跃合约"""
        query = """
        SELECT DISTINCT symbol
        FROM instruments
        WHERE state = 'live' AND symbol LIKE '%-USDT-SWAP'
        ORDER BY symbol
        """
        results = await self.db.fetch(query)
        return [row['symbol'] for row in results]
```

---

## 数据库设计

### 市场特征表

```sql
-- 1 分钟市场特征表（清洗后的核心数据）
CREATE TABLE market_features_1m (
    -- 元数据
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    
    -- 1. 价格与成交量
    price_open NUMERIC(20, 8),
    price_high NUMERIC(20, 8),
    price_low NUMERIC(20, 8),
    price_close NUMERIC(20, 8),
    volume NUMERIC(20, 8),
    volume_usd NUMERIC(20, 2),
    spot_price NUMERIC(20, 8),
    perp_price NUMERIC(20, 8),
    price_change_pct NUMERIC(10, 4),
    volatility NUMERIC(10, 4),
    
    -- 2. Trade / Order Flow
    buy_volume_usd NUMERIC(20, 2),
    sell_volume_usd NUMERIC(20, 2),
    delta_usd NUMERIC(20, 2),
    cvd NUMERIC(20, 2),
    trade_count INTEGER,
    buy_sell_ratio NUMERIC(10, 4),
    avg_trade_size_usd NUMERIC(20, 2),
    
    -- 3. Open Interest
    oi NUMERIC(20, 8),
    oi_usd NUMERIC(20, 2),
    oi_delta NUMERIC(20, 2),
    oi_change_pct NUMERIC(10, 4),
    oi_direction VARCHAR(20),
    
    -- 4. Funding / Basis
    funding_rate NUMERIC(10, 8),
    funding_rate_8h NUMERIC(10, 8),
    basis NUMERIC(20, 8),
    basis_bps NUMERIC(10, 2),
    funding_percentile NUMERIC(5, 4),
    basis_percentile NUMERIC(5, 4),
    
    -- 5. L2 OrderBook
    bid_depth_10 NUMERIC(20, 2),
    ask_depth_10 NUMERIC(20, 2),
    obi NUMERIC(5, 4),
    spread_bps NUMERIC(10, 2),
    liquidity_score NUMERIC(5, 4),
    
    -- 6. Liquidation
    long_liq_usd NUMERIC(20, 2),
    short_liq_usd NUMERIC(20, 2),
    liq_count INTEGER,
    liq_imbalance NUMERIC(5, 4),
    is_squeeze BOOLEAN,
    squeeze_type VARCHAR(20),
    squeeze_intensity NUMERIC(5, 4),
    
    -- 7. 数据质量
    coverage NUMERIC(5, 4) NOT NULL,
    quality NUMERIC(5, 4) NOT NULL,
    age_seconds INTEGER NOT NULL,
    is_final BOOLEAN DEFAULT FALSE,
    revision_count INTEGER DEFAULT 0,
    source_flags INTEGER DEFAULT 0,
    
    PRIMARY KEY (time, symbol)
);

-- 转换为 TimescaleDB 超表
SELECT create_hypertable('market_features_1m', 'time');

-- 索引
CREATE INDEX idx_mf1m_symbol_time ON market_features_1m (symbol, time DESC);
CREATE INDEX idx_mf1m_quality ON market_features_1m (quality) WHERE quality < 0.9;
CREATE INDEX idx_mf1m_squeeze ON market_features_1m (symbol, time) WHERE is_squeeze = true;
CREATE INDEX idx_mf1m_oi_direction ON market_features_1m (symbol, oi_direction, time DESC);
CREATE INDEX idx_mf1m_final ON market_features_1m (time) WHERE is_final = true;

-- 数据保留策略：60 天
SELECT add_retention_policy('market_features_1m', INTERVAL '60 days');

-- 注释
COMMENT ON TABLE market_features_1m IS '1分钟市场特征（清洗后的核心数据，供上层应用使用）';
COMMENT ON COLUMN market_features_1m.coverage IS '数据完整度（0-1），表示有多少数据源可用';
COMMENT ON COLUMN market_features_1m.quality IS '质量评分（0-1），综合评估数据质量';
COMMENT ON COLUMN market_features_1m.is_final IS '数据是否已确定（不会再修订）';
COMMENT ON COLUMN market_features_1m.obi IS 'Order Book Imbalance，范围 -1 到 1';
COMMENT ON COLUMN market_features_1m.cvd IS 'Cumulative Volume Delta，累计成交量差';
```

### 聚合表（可选）

```sql
-- 5 分钟聚合表
CREATE TABLE market_features_5m (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    
    -- 聚合方式：
    -- 价格：OHLC
    -- 成交量：SUM
    -- Delta/CVD：SUM
    -- OI：LAST
    -- Funding：LAST
    -- OBI：AVG
    -- 清算：SUM
    -- 质量：MIN（取最差的）
    
    -- 省略具体字段，结构类似 1m 表
    ...
    
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable('market_features_5m', 'time');

-- 自动聚合任务（使用 TimescaleDB Continuous Aggregates）
CREATE MATERIALIZED VIEW market_features_5m_view
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('5 minutes', time) AS time,
    symbol,
    FIRST(price_open, time) AS price_open,
    MAX(price_high) AS price_high,
    MIN(price_low) AS price_low,
    LAST(price_close, time) AS price_close,
    SUM(volume) AS volume,
    SUM(volume_usd) AS volume_usd,
    -- ... 其他聚合字段
    MIN(quality) AS quality
FROM market_features_1m
GROUP BY time_bucket('5 minutes', time), symbol;

-- 刷新策略
SELECT add_continuous_aggregate_policy('market_features_5m_view',
    start_offset => INTERVAL '10 minutes',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes');
```

---

## 质量保证

### 质量评分规则

```python
class QualityScoring:
    """数据质量评分规则"""
    
    @staticmethod
    def calculate_coverage(source_flags: int) -> float:
        """
        计算数据完整度
        
        Coverage = 有效数据源数 / 总数据源数
        """
        total_sources = 7  # CANDLES, TRADES, OI, FUNDING, ORDERBOOK, LIQUIDATIONS, SPOT_PRICE
        available_sources = bin(source_flags).count('1')
        return available_sources / total_sources
    
    @staticmethod
    def calculate_quality(
        coverage: float,
        data_age_seconds: int,
        has_anomalies: bool
    ) -> float:
        """
        计算综合质量评分
        
        因素：
        1. Coverage（权重 0.5）
        2. 数据新鲜度（权重 0.3）
        3. 异常检测（权重 0.2）
        """
        # Coverage 分数
        coverage_score = coverage
        
        # 新鲜度分数
        if data_age_seconds < 60:
            freshness_score = 1.0
        elif data_age_seconds < 300:
            freshness_score = 0.8
        elif data_age_seconds < 600:
            freshness_score = 0.5
        else:
            freshness_score = 0.2
        
        # 异常分数
        anomaly_score = 0.0 if has_anomalies else 1.0
        
        # 加权平均
        quality = (
            coverage_score * 0.5 +
            freshness_score * 0.3 +
            anomaly_score * 0.2
        )
        
        return quality
```

### 数据验证

```python
class FeatureValidator:
    """特征数据验证器"""
    
    @staticmethod
    def validate_feature(feature: MarketFeature1Min) -> tuple[bool, list[str]]:
        """
        验证特征数据的合理性
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # 1. 价格逻辑检查
        if feature.price_open and feature.price_high and feature.price_low and feature.price_close:
            if not (feature.price_low <= feature.price_open <= feature.price_high):
                errors.append("Invalid OHLC: open not in [low, high]")
            if not (feature.price_low <= feature.price_close <= feature.price_high):
                errors.append("Invalid OHLC: close not in [low, high]")
        
        # 2. 成交量非负
        if feature.volume and feature.volume < 0:
            errors.append("Negative volume")
        
        # 3. OBI 范围检查
        if feature.obi and abs(feature.obi) > 1:
            errors.append(f"OBI out of range: {feature.obi}")
        
        # 4. 清算失衡度范围检查
        if feature.liq_imbalance and abs(feature.liq_imbalance) > 1:
            errors.append(f"Liquidation imbalance out of range: {feature.liq_imbalance}")
        
        # 5. 质量评分范围检查
        if not (0 <= feature.coverage <= 1):
            errors.append(f"Coverage out of range: {feature.coverage}")
        if not (0 <= feature.quality <= 1):
            errors.append(f"Quality out of range: {feature.quality}")
        
        # 6. Basis 合理性（通常不超过 ±2%）
        if feature.basis_bps and abs(feature.basis_bps) > 200:
            errors.append(f"Extreme basis: {feature.basis_bps} bps")
        
        # 7. 资金费率合理性（通常不超过 ±0.5%）
        if feature.funding_rate and abs(float(feature.funding_rate)) > 0.005:
            errors.append(f"Extreme funding rate: {feature.funding_rate}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
```

---

## API 设计

### 获取市场特征

```python
# backend/api/routes/market_features.py

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timedelta
from typing import List, Optional

from backend.models.market_feature import MarketFeature1Min
from backend.storage.timescale_client import TimescaleClient

router = APIRouter()
db = TimescaleClient()


@router.get("/market-features/{symbol}")
async def get_market_features(
    symbol: str,
    start_time: datetime = Query(..., description="开始时间（UTC）"),
    end_time: datetime = Query(..., description="结束时间（UTC）"),
    min_quality: float = Query(0.0, ge=0.0, le=1.0, description="最低质量阈值"),
    only_final: bool = Query(False, description="只返回 final 数据")
) -> List[MarketFeature1Min]:
    """
    获取指定合约的市场特征时间序列
    
    Example:
        GET /api/v1/market-features/BTC-USDT-SWAP
            ?start_time=2026-10-30T00:00:00Z
            &end_time=2026-10-30T12:00:00Z
            &min_quality=0.9
            &only_final=true
    """
    query = """
    SELECT *
    FROM market_features_1m
    WHERE symbol = $1
    AND time >= $2 AND time < $3
    AND quality >= $4
    """
    
    if only_final:
        query += " AND is_final = true"
    
    query += " ORDER BY time ASC"
    
    results = await db.fetch(query, symbol, start_time, end_time, min_quality)
    
    if not results:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
    
    return [MarketFeature1Min(**dict(row)) for row in results]


@router.get("/market-features/{symbol}/latest")
async def get_latest_feature(symbol: str) -> MarketFeature1Min:
    """
    获取最新的市场特征
    
    Example:
        GET /api/v1/market-features/BTC-USDT-SWAP/latest
    """
    query = """
    SELECT *
    FROM market_features_1m
    WHERE symbol = $1
    ORDER BY time DESC
    LIMIT 1
    """
    
    result = await db.fetchrow(query, symbol)
    
    if not result:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
    
    return MarketFeature1Min(**dict(result))


@router.get("/market-features/squeeze-events")
async def get_squeeze_events(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    min_intensity: float = Query(0.5, ge=0.0, le=1.0)
) -> List[dict]:
    """
    获取所有 Squeeze 事件
    
    Example:
        GET /api/v1/market-features/squeeze-events
            ?start_time=2026-10-30T00:00:00Z
            &end_time=2026-10-30T12:00:00Z
            &min_intensity=0.8
    """
    query = """
    SELECT symbol, time, squeeze_type, squeeze_intensity,
           price_close, long_liq_usd, short_liq_usd, oi_change_pct
    FROM market_features_1m
    WHERE time >= $1 AND time < $2
    AND is_squeeze = true
    AND squeeze_intensity >= $3
    ORDER BY time DESC, squeeze_intensity DESC
    """
    
    results = await db.fetch(query, start_time, end_time, min_intensity)
    
    return [dict(row) for row in results]


@router.get("/market-features/quality-report")
async def get_quality_report(
    lookback_hours: int = Query(24, ge=1, le=168)
) -> dict:
    """
    获取数据质量报告
    
    Example:
        GET /api/v1/market-features/quality-report?lookback_hours=24
    """
    start_time = datetime.utcnow() - timedelta(hours=lookback_hours)
    
    query = """
    SELECT 
        symbol,
        COUNT(*) as total_records,
        AVG(coverage) as avg_coverage,
        AVG(quality) as avg_quality,
        SUM(CASE WHEN is_final THEN 1 ELSE 0 END) as final_count,
        MIN(quality) as min_quality,
        MAX(quality) as max_quality
    FROM market_features_1m
    WHERE time >= $1
    GROUP BY symbol
    ORDER BY avg_quality DESC
    """
    
    results = await db.fetch(query, start_time)
    
    return {
        "lookback_hours": lookback_hours,
        "symbols": [dict(row) for row in results]
    }
```

---

## 前端组件

### 市场特征卡片

```typescript
// frontend/src/components/MarketFeatureCard.tsx

import React from 'react';
import './MarketFeatureCard.css';

interface MarketFeature {
  symbol: string;
  timestamp: string;
  priceChangePct: number;
  deltaUsd: number;
  oiChangePct: number;
  fundingRate: number;
  obi: number;
  shortLiqUsd: number;
  quality: number;
  isFinal: boolean;
  isSqueeze: boolean;
  squeezeType?: string;
}

interface MetricProps {
  label: string;
  value: string;
  positive?: boolean;
}

const Metric: React.FC<MetricProps> = ({ label, value, positive }) => {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${positive ? 'positive' : positive === false ? 'negative' : ''}`}>
        {value}
      </span>
    </div>
  );
};

export const MarketFeatureCard: React.FC<{ feature: MarketFeature }> = ({ feature }) => {
  return (
    <div className={`feature-card ${feature.isSqueeze ? 'squeeze-highlight' : ''}`}>
      {/* Header */}
      <div className="card-header">
        <h3>{feature.symbol}</h3>
        <span className="timestamp">
          {new Date(feature.timestamp).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
          })}
        </span>
        <div className="quality-badge">
          <span className={`quality ${feature.quality > 0.9 ? 'high' : feature.quality > 0.7 ? 'medium' : 'low'}`}>
            质量: {(feature.quality * 100).toFixed(0)}%
          </span>
          {feature.isFinal && <span className="badge-final">✓ Final</span>}
        </div>
      </div>

      {/* Squeeze Alert */}
      {feature.isSqueeze && (
        <div className="squeeze-alert">
          ⚠️ {feature.squeezeType === 'short_squeeze' ? '挤空' : '杀多'}事件
        </div>
      )}

      {/* Metrics Grid */}
      <div className="metrics-grid">
        <Metric 
          label="价格变化" 
          value={`${feature.priceChangePct > 0 ? '+' : ''}${feature.priceChangePct.toFixed(2)}%`}
          positive={feature.priceChangePct > 0}
        />
        <Metric 
          label="买卖 Delta" 
          value={`$${(feature.deltaUsd / 1000).toFixed(0)}K`}
          positive={feature.deltaUsd > 0}
        />
        <Metric 
          label="OI 变化" 
          value={`${feature.oiChangePct > 0 ? '+' : ''}${feature.oiChangePct.toFixed(2)}%`}
          positive={feature.oiChangePct > 0}
        />
        <Metric 
          label="资金费率" 
          value={`${(feature.fundingRate * 100).toFixed(3)}%`}
        />
        <Metric 
          label="盘口 OBI" 
          value={feature.obi.toFixed(2)}
          positive={feature.obi > 0}
        />
        <Metric 
          label="空头清算" 
          value={`$${(feature.shortLiqUsd / 1000).toFixed(0)}K`}
        />
      </div>
    </div>
  );
};
```

### 市场特征时间线

```typescript
// frontend/src/components/MarketFeatureTimeline.tsx

import React, { useState, useEffect } from 'react';
import { MarketFeatureCard } from './MarketFeatureCard';

interface TimelineProps {
  symbol: string;
  hours: number;
}

export const MarketFeatureTimeline: React.FC<TimelineProps> = ({ symbol, hours }) => {
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchFeatures = async () => {
      const endTime = new Date();
      const startTime = new Date(endTime.getTime() - hours * 3600 * 1000);

      const res = await fetch(
        `/api/v1/market-features/${symbol}` +
        `?start_time=${startTime.toISOString()}` +
        `&end_time=${endTime.toISOString()}` +
        `&min_quality=0.7` +
        `&only_final=true`
      );

      const data = await res.json();
      setFeatures(data);
      setLoading(false);
    };

    fetchFeatures();
    const interval = setInterval(fetchFeatures, 60000); // 每分钟刷新
    return () => clearInterval(interval);
  }, [symbol, hours]);

  if (loading) return <div>加载中...</div>;

  return (
    <div className="feature-timeline">
      <h2>{symbol} - 最近 {hours} 小时</h2>
      <div className="timeline-grid">
        {features.map((feature, idx) => (
          <MarketFeatureCard key={idx} feature={feature} />
        ))}
      </div>
    </div>
  );
};
```

---

## 实施路线图

### Phase 1: 数据模型和基础设施（1-2 周）

- [ ] 定义 `MarketFeature1Min` 数据模型
- [ ] 创建 `market_features_1m` 数据库表
- [ ] 实现 `MarketFeatureCalculator` 框架
- [ ] 实现数据质量评估逻辑

### Phase 2: 特征计算实现（2-3 周）

- [ ] 实现价格与成交量特征计算
- [ ] 实现 Trade / Order Flow 特征计算（包括 CVD）
- [ ] 实现 Open Interest 特征计算（包括 OI Direction）
- [ ] 实现 Funding / Basis 特征计算
- [ ] 实现 L2 OrderBook 特征计算（包括 OBI）
- [ ] 实现 Liquidation 特征计算（包括 Squeeze 检测）

### Phase 3: 定时任务和存储（1 周）

- [ ] 实现 `FeatureCalculatorTask` 定时任务
- [ ] 测试并发计算性能
- [ ] 实现数据保存和更新逻辑
- [ ] 实现历史数据回填

### Phase 4: API 和前端（1-2 周）

- [ ] 实现市场特征 API 端点
- [ ] 实现质量报告 API
- [ ] 实现 Squeeze 事件 API
- [ ] 开发前端组件（MarketFeatureCard、Timeline）

### Phase 5: 测试和优化（1-2 周）

- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能测试和优化
- [ ] 7x24 稳定性测试

### 验收标准

- [ ] 每分钟成功计算所有合约的特征
- [ ] 平均计算延迟 < 5 秒
- [ ] 数据质量评分平均 > 0.9
- [ ] 7x24 稳定运行，无重大故障
- [ ] API 响应时间 < 500ms (P99)

---

## 总结

市场特征数据层是 SentinelPerp 的**核心中间层**，承上启下：

- **向下**：从 P0 原始数据计算派生特征
- **向上**：为特征识别、机会发现提供统一、干净的数据源

### 核心优势

1. ✅ **数据质量保证**：每条记录都有 Coverage 和 Quality 评分
2. ✅ **结构清晰**：7 大类特征，涵盖市场所有维度
3. ✅ **易于使用**：上层应用不需要关心原始数据的复杂性
4. ✅ **支持时间序列分析**：规整的分钟级数据，适合大模型分析
5. ✅ **可扩展**：易于添加新的派生指标

### 与其他模块的关系

```
P0 原始数据 → [市场特征层] → 特征识别 → 机会发现
                  ↓
              涨跌幅榜单
```

只有在市场特征层稳定、高质量运行后，才能开始构建上层应用。

---

**文档版本**: v1.0.0  
**创建时间**: 2024-10-30  
**维护者**: SentinelPerp 开发团队
