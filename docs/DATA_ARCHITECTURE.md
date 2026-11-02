# SentinelPerp 数据架构与采集优先级

## 目录

- [数据优先级定义](#数据优先级定义)
- [P0 核心数据](#p0-核心数据)
- [P1 辅助数据](#p1-辅助数据)
- [P2 可选数据](#p2-可选数据)
- [数据清洗标准](#数据清洗标准)
- [数据质量监控](#数据质量监控)
- [存储架构](#存储架构)
- [实施路线图](#实施路线图)

---

## 数据优先级定义

数据质量是整个系统的根基。特征识别、机会发现等上层功能完全依赖于底层数据的准确性和完整性。

### 优先级说明

- **P0 (Critical)**：系统核心数据，必须 100% 可靠，缺失会导致系统不可用
- **P1 (High)**：重要辅助数据，提升分析准确性，缺失会降低系统价值
- **P2 (Nice to Have)**：增强功能数据，按需采集，缺失不影响核心功能

---

## P0 核心数据

### 1. Instruments (合约信息)

**数据来源**：
- REST API: `GET /api/v5/public/instruments?instType=SWAP`
- WebSocket: `public/instruments`

**采集范围**：
- 所有 USDT 永续合约 (`*-USDT-SWAP`)
- 对应的现货交易对 (`*-USDT`)

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "instType": "SWAP",
  "ctVal": "0.01",           // 合约面值
  "ctMult": "1",             // 合约乘数
  "tickSz": "0.1",           // 价格精度
  "lotSz": "1",              // 下单数量精度
  "minSz": "1",              // 最小下单量
  "state": "live",           // 合约状态
  "listTime": "1609344000000",
  "expTime": ""
}
```

**核心用途**：
- 合约精度计算（价格、数量）
- 合约上下架监控
- 现货-永续配对
- CVD 计算时的单位转换

**采集频率**：
- 初始化：启动时全量加载
- 增量更新：每 5 分钟刷新一次
- WebSocket 监听合约状态变化

**质量检查**：
```python
def validate_instrument(inst: dict) -> bool:
    """合约信息完整性检查"""
    required_fields = ['instId', 'instType', 'ctVal', 'tickSz', 'lotSz', 'state']
    
    # 字段完整性
    if not all(f in inst for f in required_fields):
        return False
    
    # 数值有效性
    if float(inst['ctVal']) <= 0:
        return False
    if float(inst['tickSz']) <= 0:
        return False
    
    # 状态有效性
    if inst['state'] not in ['live', 'suspend', 'preopen']:
        return False
    
    return True
```

---

### 2. K线 (Candles / OHLCV)

**数据来源**：
- REST API: `GET /api/v5/market/candles`
- WebSocket: `candle1m`, `candle5m`, `candle1H`, `candle1D`

**采集范围**：
- 永续合约：所有 USDT-SWAP
- 现货：对应的 USDT 现货对

**数据字段**：
```json
{
  "ts": "1698674400000",     // 时间戳（毫秒）
  "o": "67500.0",            // 开盘价
  "h": "67650.5",            // 最高价
  "l": "67480.2",            // 最低价
  "c": "67620.8",            // 收盘价
  "vol": "15.32",            // 成交量（合约张数）
  "volCcy": "1035482.5",     // 成交量（计价货币）
  "volCcyQuote": "1035482.5" // 成交额
}
```

**核心用途**：
- 价格涨跌事件识别
- 涨跌幅榜单计算
- 技术指标计算（MA、BOLL、RSI 等）
- 特征提取的基础数据

**采集频率**：
- 实时：1 分钟 K 线（WebSocket）
- 历史回填：启动时回填最近 60 天

**质量检查**：
```python
def validate_candle(candle: dict, symbol: str, interval: str) -> bool:
    """K 线数据质量检查"""
    try:
        o, h, l, c = float(candle['o']), float(candle['h']), float(candle['l']), float(candle['c'])
        vol = float(candle['vol'])
        ts = int(candle['ts'])
        
        # 价格逻辑一致性
        if not (l <= o <= h and l <= c <= h):
            logger.warning(f"Invalid OHLC logic: {symbol} {candle}")
            return False
        
        # 价格合理性（不能为零或负数）
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            logger.error(f"Invalid price values: {symbol} {candle}")
            return False
        
        # 成交量非负
        if vol < 0:
            logger.error(f"Negative volume: {symbol} {candle}")
            return False
        
        # 时间戳合理性（不能是未来时间）
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if ts > now_ms:
            logger.warning(f"Future timestamp: {symbol} {ts}")
            return False
        
        # K 线周期对齐检查
        expected_interval_ms = {
            '1m': 60000,
            '5m': 300000,
            '1H': 3600000,
            '1D': 86400000
        }
        if interval in expected_interval_ms:
            if ts % expected_interval_ms[interval] != 0:
                logger.warning(f"Misaligned timestamp: {symbol} {ts} for {interval}")
                return False
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"Candle validation error: {symbol} {e}")
        return False
```

**去重策略**：
```python
# 使用 (symbol, interval, timestamp) 作为唯一键
unique_key = f"{symbol}:{interval}:{timestamp}"

# PostgreSQL 唯一约束
CREATE UNIQUE INDEX idx_candles_unique 
ON candles (symbol, interval, time);
```

---

### 3. Trades (逐笔成交)

**数据来源**：
- WebSocket: `trades`
- WebSocket: `trades-all` (包含 Taker 方向)

**采集范围**：
- 永续合约：所有 USDT-SWAP
- 现货：主要币种的 USDT 现货对

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "tradeId": "123456789",
  "px": "67500.5",          // 成交价格
  "sz": "1.5",              // 成交数量（合约张数）
  "side": "buy",            // Taker 方向：buy/sell
  "ts": "1698674401234"     // 时间戳（毫秒）
}
```

**核心用途**：
- **Delta 计算**：买卖方向的逐笔成交差
- **CVD (Cumulative Volume Delta)**：累计成交量差
- 成交结构分析（大单、散单）
- 成交密集区识别

**采集频率**：
- 实时 WebSocket 推送
- 高频数据，需要高效处理

**质量检查**：
```python
def validate_trade(trade: dict, symbol: str) -> bool:
    """交易数据质量检查"""
    try:
        price = float(trade['px'])
        size = float(trade['sz'])
        trade_id = str(trade['tradeId'])
        side = trade['side']
        ts = int(trade['ts'])
        
        # 价格合理性
        if price <= 0:
            logger.error(f"Invalid trade price: {symbol} {price}")
            return False
        
        # 数量合理性
        if size <= 0:
            logger.error(f"Invalid trade size: {symbol} {size}")
            return False
        
        # 方向有效性
        if side not in ['buy', 'sell']:
            logger.error(f"Invalid trade side: {symbol} {side}")
            return False
        
        # Trade ID 非空
        if not trade_id:
            logger.error(f"Missing trade ID: {symbol}")
            return False
        
        # 时间戳合理性
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if ts > now_ms + 5000:  # 允许 5 秒时钟偏差
            logger.warning(f"Future trade timestamp: {symbol} {ts}")
            return False
        
        # 时效性检查（延迟不超过 10 秒）
        latency_ms = now_ms - ts
        if latency_ms > 10000:
            logger.warning(f"High trade latency: {symbol} {latency_ms}ms")
            # 不拒绝，只警告
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"Trade validation error: {symbol} {e}")
        return False
```

**去重策略**：
```python
# 使用 (symbol, tradeId) 作为唯一键
unique_key = f"{symbol}:{trade_id}"

# 两级去重
# 1. 内存哈希表（最近 1 小时）
# 2. Redis Set（24 小时 TTL）

# PostgreSQL 唯一约束
CREATE UNIQUE INDEX idx_trades_unique 
ON trades (symbol, trade_id);
```

**CVD 计算**：
```python
def calculate_cvd(trades: List[Trade]) -> float:
    """
    计算累计成交量差（Cumulative Volume Delta）
    
    买单为正，卖单为负
    """
    cvd = 0.0
    for trade in trades:
        volume = trade.size * trade.contract_value  # 转换为基础货币数量
        if trade.side == 'buy':
            cvd += volume
        else:
            cvd -= volume
    return cvd
```

---

### 4. Open Interest (持仓量)

**数据来源**：
- REST API: `GET /api/v5/public/open-interest`
- WebSocket: `open-interest`

**采集范围**：
- 所有 USDT 永续合约

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "oi": "123456.78",         // 持仓量（合约张数）
  "oiCcy": "1234.5678",      // 持仓量（币）
  "ts": "1698674401000"
}
```

**核心用途**：
- 杠杆仓位变化监控
- 市场情绪判断（OI 上升 + 价格上涨 = 看多；OI 上升 + 价格下跌 = 看空）
- 挤空/杀多预警（OI 快速下降）

**采集频率**：
- WebSocket 实时推送（通常每秒更新）
- REST API 补充（每 30 秒）

**质量检查**：
```python
def validate_open_interest(oi_data: dict, symbol: str) -> bool:
    """持仓量数据质量检查"""
    try:
        oi = float(oi_data['oi'])
        ts = int(oi_data['ts'])
        
        # 持仓量非负
        if oi < 0:
            logger.error(f"Negative OI: {symbol} {oi}")
            return False
        
        # 时间戳合理性
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if ts > now_ms + 5000:
            logger.warning(f"Future OI timestamp: {symbol} {ts}")
            return False
        
        # 突变检测（OI 不应该瞬间变化超过 50%）
        last_oi = get_last_oi(symbol)
        if last_oi and abs(oi - last_oi) / last_oi > 0.5:
            logger.warning(f"OI spike detected: {symbol} {last_oi} -> {oi}")
            # 不拒绝，只标记异常
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"OI validation error: {symbol} {e}")
        return False
```

---

### 5. Funding Rate (资金费率)

**数据来源**：
- REST API: `GET /api/v5/public/funding-rate`
- WebSocket: `funding-rate`

**采集范围**：
- 所有 USDT 永续合约

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "fundingRate": "0.0001",         // 当前资金费率
  "nextFundingRate": "0.00012",    // 预测的下期费率
  "fundingTime": "1698681600000",  // 下次结算时间
  "ts": "1698674401000"
}
```

**核心用途**：
- 资金费率拥挤程度分析
- 极端费率预警（>0.1% 或 <-0.1%）
- 套利机会识别（现货-永续 Basis）

**采集频率**：
- WebSocket 实时推送（费率变化时）
- REST API 补充（每 1 分钟）

**质量检查**：
```python
def validate_funding_rate(funding: dict, symbol: str) -> bool:
    """资金费率数据质量检查"""
    try:
        rate = float(funding['fundingRate'])
        next_rate = float(funding.get('nextFundingRate', rate))
        funding_time = int(funding['fundingTime'])
        ts = int(funding['ts'])
        
        # 费率合理性（通常在 -0.375% 到 0.375% 之间）
        if abs(rate) > 0.00375:
            logger.warning(f"Extreme funding rate: {symbol} {rate}")
            # 不拒绝，因为极端市场可能出现
        
        # 下次结算时间必须是未来
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if funding_time <= now_ms:
            logger.warning(f"Past funding time: {symbol} {funding_time}")
            return False
        
        # 下次结算时间应该在 8 小时内（OKX 是 8 小时一次）
        if funding_time - now_ms > 8 * 3600 * 1000 + 60000:  # 允许 1 分钟误差
            logger.warning(f"Invalid funding time: {symbol} {funding_time}")
            return False
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"Funding rate validation error: {symbol} {e}")
        return False
```

---

### 6. Mark Price / Index Price (标记价格 / 指数价格)

**数据来源**：
- REST API: `GET /api/v5/market/mark-price`
- REST API: `GET /api/v5/market/index-tickers`
- WebSocket: `mark-price`, `index-tickers`

**采集范围**：
- 永续合约的标记价格
- 对应的指数价格

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "markPx": "67520.5",       // 标记价格（用于清算）
  "indexPx": "67518.3",      // 指数价格（现货加权平均）
  "ts": "1698674401000"
}
```

**核心用途**：
- **Basis 计算**：永续价格 - 指数价格（现货价格）
- 价格偏离监控
- 套利机会识别

**采集频率**：
- WebSocket 实时推送（每秒）
- REST API 补充（每 10 秒）

**质量检查**：
```python
def validate_mark_index_price(data: dict, symbol: str) -> bool:
    """标记/指数价格质量检查"""
    try:
        mark_px = float(data['markPx'])
        index_px = float(data['indexPx'])
        ts = int(data['ts'])
        
        # 价格合理性
        if mark_px <= 0 or index_px <= 0:
            logger.error(f"Invalid mark/index price: {symbol} mark={mark_px} index={index_px}")
            return False
        
        # Basis 合理性（通常不超过 ±1%）
        basis_percent = abs(mark_px - index_px) / index_px * 100
        if basis_percent > 1.0:
            logger.warning(f"Large basis: {symbol} {basis_percent:.2f}%")
            # 不拒绝，极端市场可能出现
        
        # 时间戳合理性
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if ts > now_ms + 5000:
            logger.warning(f"Future timestamp: {symbol} {ts}")
            return False
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"Mark/Index price validation error: {symbol} {e}")
        return False
```

---

### 7. Order Book L2 (二档盘口)

**数据来源**：
- WebSocket: `books` (增量推送)
- WebSocket: `books5` / `books-l2-tbt` (快照)

**采集范围**：
- 永续合约：所有 USDT-SWAP
- 现货：按需选择流动性好的币种

**数据字段**：
```json
{
  "asks": [
    ["67521.0", "1.5", "0", "2"],  // [价格, 数量, 已弃用, 订单数]
    ["67522.0", "2.3", "0", "5"]
  ],
  "bids": [
    ["67520.0", "1.2", "0", "3"],
    ["67519.0", "3.1", "0", "7"]
  ],
  "ts": "1698674401234",
  "seqId": 123456789
}
```

**核心用途**：
- **OBI (Order Book Imbalance)**：买卖盘失衡度
- 流动性监控
- 盘口深度分析
- 大单挂单识别

**采集频率**：
- WebSocket 增量推送（高频）
- 每 60 秒存储一次快照到数据库

**质量检查**：
```python
def validate_orderbook(book: dict, symbol: str) -> bool:
    """订单簿质量检查"""
    try:
        asks = book['asks']
        bids = book['bids']
        ts = int(book['ts'])
        seq_id = int(book['seqId'])
        
        # 买卖盘非空
        if not asks or not bids:
            logger.warning(f"Empty orderbook: {symbol}")
            return False
        
        # 价格排序检查
        # Asks 应该递增
        for i in range(len(asks) - 1):
            if float(asks[i][0]) >= float(asks[i+1][0]):
                logger.error(f"Invalid ask order: {symbol} {asks[i]} >= {asks[i+1]}")
                return False
        
        # Bids 应该递减
        for i in range(len(bids) - 1):
            if float(bids[i][0]) <= float(bids[i+1][0]):
                logger.error(f"Invalid bid order: {symbol} {bids[i]} <= {bids[i+1]}")
                return False
        
        # 买卖价格不能交叉
        best_ask = float(asks[0][0])
        best_bid = float(bids[0][0])
        if best_bid >= best_ask:
            logger.error(f"Crossed book: {symbol} bid={best_bid} >= ask={best_ask}")
            return False
        
        # 数量非负
        for ask in asks:
            if float(ask[1]) < 0:
                logger.error(f"Negative ask size: {symbol} {ask}")
                return False
        for bid in bids:
            if float(bid[1]) < 0:
                logger.error(f"Negative bid size: {symbol} {bid}")
                return False
        
        # 序列号连续性检查
        last_seq = get_last_seq(symbol)
        if last_seq and seq_id != last_seq + 1:
            logger.warning(f"Sequence gap: {symbol} {last_seq} -> {seq_id}")
            # 需要重新订阅获取快照
        
        return True
    except (ValueError, KeyError, IndexError) as e:
        logger.error(f"Orderbook validation error: {symbol} {e}")
        return False
```

**OBI 计算**：
```python
def calculate_obi(orderbook: dict, depth: int = 10) -> float:
    """
    计算订单簿失衡度（Order Book Imbalance）
    
    OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)
    
    返回值范围: [-1, 1]
    - 正值：买盘占优
    - 负值：卖盘占优
    """
    asks = orderbook['asks'][:depth]
    bids = orderbook['bids'][:depth]
    
    ask_volume = sum(float(ask[1]) for ask in asks)
    bid_volume = sum(float(bid[1]) for bid in bids)
    
    if ask_volume + bid_volume == 0:
        return 0.0
    
    obi = (bid_volume - ask_volume) / (bid_volume + ask_volume)
    return obi
```

---

### 8. Liquidation (清算/爆仓)

**数据来源**：
- WebSocket: `liquidation-orders`

**采集范围**：
- 所有 USDT 永续合约

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "details": [
    {
      "side": "long",           // 被清算方向：long/short
      "bkPx": "67000.0",        // 破产价格
      "sz": "1.5",              // 清算数量
      "bkLoss": "150.0",        // 亏损金额
      "ts": "1698674401234"
    }
  ]
}
```

**核心用途**：
- 强平活动监控
- **Squeeze 研究**：短时间大量清算 = 挤空/杀多
- 市场拥挤度预警

**采集频率**：
- WebSocket 实时推送

**质量检查**：
```python
def validate_liquidation(liq: dict, symbol: str) -> bool:
    """清算数据质量检查"""
    try:
        details = liq['details']
        
        for detail in details:
            side = detail['side']
            price = float(detail['bkPx'])
            size = float(detail['sz'])
            loss = float(detail['bkLoss'])
            ts = int(detail['ts'])
            
            # 方向有效性
            if side not in ['long', 'short']:
                logger.error(f"Invalid liquidation side: {symbol} {side}")
                return False
            
            # 价格、数量、亏损非负
            if price <= 0 or size <= 0 or loss < 0:
                logger.error(f"Invalid liquidation values: {symbol} {detail}")
                return False
            
            # 时间戳合理性
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            if ts > now_ms + 5000:
                logger.warning(f"Future liquidation timestamp: {symbol} {ts}")
                return False
        
        return True
    except (ValueError, KeyError) as e:
        logger.error(f"Liquidation validation error: {symbol} {e}")
        return False
```

**Squeeze 检测**：
```python
def detect_squeeze(symbol: str, window_minutes: int = 5) -> dict:
    """
    检测挤空/杀多事件
    
    标准：
    - 5 分钟内清算量 > 正常水平的 10 倍
    - 单方向清算占比 > 80%
    """
    # 查询最近 5 分钟的清算数据
    recent_liqs = get_liquidations(symbol, minutes=window_minutes)
    
    long_liq_volume = sum(l.size for l in recent_liqs if l.side == 'long')
    short_liq_volume = sum(l.size for l in recent_liqs if l.side == 'short')
    total_liq_volume = long_liq_volume + short_liq_volume
    
    if total_liq_volume == 0:
        return {'squeeze_detected': False}
    
    # 计算单方向占比
    long_ratio = long_liq_volume / total_liq_volume
    short_ratio = short_liq_volume / total_liq_volume
    
    # 获取正常水平（过去 24 小时平均）
    normal_volume = get_average_liquidation_volume(symbol, hours=24)
    
    squeeze_detected = False
    squeeze_type = None
    intensity = 0.0
    
    if total_liq_volume > normal_volume * 10:
        if short_ratio > 0.8:
            squeeze_detected = True
            squeeze_type = 'short_squeeze'  # 挤空
            intensity = short_ratio
        elif long_ratio > 0.8:
            squeeze_detected = True
            squeeze_type = 'long_liquidation'  # 杀多
            intensity = long_ratio
    
    return {
        'squeeze_detected': squeeze_detected,
        'squeeze_type': squeeze_type,
        'intensity': intensity,
        'total_volume': total_liq_volume,
        'long_volume': long_liq_volume,
        'short_volume': short_liq_volume
    }
```

---

## P1 辅助数据

### 9. Tickers (行情快照)

**数据来源**：
- REST API: `GET /api/v5/market/tickers?instType=SWAP`
- WebSocket: `tickers`

**采集范围**：
- 所有目标市场

**数据字段**：
```json
{
  "instId": "BTC-USDT-SWAP",
  "last": "67520.5",         // 最新价
  "lastSz": "1.5",           // 最新成交量
  "askPx": "67521.0",        // 卖一价
  "askSz": "2.3",            // 卖一量
  "bidPx": "67520.0",        // 买一价
  "bidSz": "1.8",            // 买一量
  "open24h": "65000.0",      // 24h 开盘价
  "high24h": "68000.0",      // 24h 最高
  "low24h": "64500.0",       // 24h 最低
  "vol24h": "123456.78",     // 24h 成交量
  "volCcy24h": "8345678.9",  // 24h 成交额
  "ts": "1698674401234"
}
```

**核心用途**：
- 最新报价快速查询
- 24h 涨跌幅排名校验（与自己计算的结果对比）
- 监控面板展示

**采集频率**：
- REST API：每 10 秒
- WebSocket：实时推送

---

### 10. 多空比等统计

**数据来源**：
- REST API: `GET /api/v5/rubik/stat/trading-data/long-short-ratio`
- REST API: `GET /api/v5/rubik/stat/taker-volume`

**采集范围**：
- OKX 支持的主要币种

**数据字段**：
```json
{
  "ts": "1698674400000",
  "longShortRatio": "1.25",  // 多空比（>1 多头占优）
  "longAccount": "0.556",    // 多头账户占比
  "shortAccount": "0.444"    // 空头账户占比
}
```

**核心用途**：
- 辅助分析多空拥挤程度
- 与持仓量、资金费率结合判断市场情绪

**采集频率**：
- 每 5 分钟

---

## P2 可选数据

### 11. 完整 L2 历史增量

**数据来源**：
- WebSocket: `books-l2-tbt` (tick-by-tick)

**采集范围**：
- 按需选定市场（流动性好、波动大的币种）

**核心用途**：
- 秒级盘口重放
- 高频策略研究
- 市场微观结构分析

**存储策略**：
- 由于数据量巨大，只保留关键时刻的完整记录
- 平时只保留快照（每分钟）

---

## 数据清洗标准

### 清洗流程

```
原始数据 → 格式验证 → 逻辑校验 → 去重 → 时效性检查 → 异常值过滤 → 存储
```

### 清洗规则汇总

| 检查项 | 标准 | 处理方式 |
|--------|------|----------|
| 字段完整性 | 必填字段不能缺失 | 拒绝，记录错误日志 |
| 数据类型 | 数值字段必须可转换 | 拒绝，记录错误日志 |
| 价格合理性 | 价格 > 0，OHLC 逻辑正确 | 拒绝，记录错误日志 |
| 数量合理性 | 数量 >= 0 | 拒绝，记录错误日志 |
| 时间戳合理性 | 不能是未来时间 | 拒绝，记录错误日志 |
| 时效性 | 延迟 < 10 秒 | 超过 10 秒标记 `stale`，但不拒绝 |
| 乱序容忍 | 时间戳回退 < 2 秒 | 接受但标记 `out_of_order` |
| 去重 | 唯一键冲突 | 拒绝，增加去重计数器 |
| 序列号连续性 | WebSocket seqId 连续 | 断开重连，请求快照 |
| 突变检测 | OI/价格变化 < 50% | 标记 `spike`，发送告警 |
| Basis 合理性 | 永续-现货价差 < 1% | 超过 1% 标记 `large_basis` |
| 资金费率极值 | abs(funding_rate) < 0.375% | 超过标记 `extreme_funding` |

### 数据标记（Flags）

每条数据附带质量标记：

```python
class DataQualityFlags:
    CLEAN = 0x00            # 完全干净
    STALE = 0x01            # 陈旧（延迟 > 10s）
    OUT_OF_ORDER = 0x02     # 乱序
    SPIKE = 0x04            # 突变
    LARGE_BASIS = 0x08      # Basis 异常
    EXTREME_FUNDING = 0x10  # 资金费率极端
    PARTIAL_DATA = 0x20     # 数据不完整但可用
```

存储时记录：
```sql
CREATE TABLE trades (
    ...
    quality_flags INTEGER DEFAULT 0,
    latency_ms INTEGER,
    ...
);
```

---

## 数据质量监控

### 实时监控指标

```python
class DataQualityMetrics:
    """数据质量实时指标"""
    
    def __init__(self):
        self.metrics = {
            'trades': {
                'received_count': 0,
                'rejected_count': 0,
                'duplicate_count': 0,
                'stale_count': 0,
                'avg_latency_ms': 0.0,
                'last_update_time': None
            },
            'candles': {...},
            'orderbook': {...},
            'funding': {...},
            'oi': {...},
            'liquidations': {...}
        }
    
    def record_trade(self, trade: dict, is_valid: bool, latency_ms: float):
        """记录交易数据指标"""
        self.metrics['trades']['received_count'] += 1
        if not is_valid:
            self.metrics['trades']['rejected_count'] += 1
        if latency_ms > 10000:
            self.metrics['trades']['stale_count'] += 1
        
        # 更新平均延迟（指数移动平均）
        alpha = 0.1
        current_avg = self.metrics['trades']['avg_latency_ms']
        self.metrics['trades']['avg_latency_ms'] = alpha * latency_ms + (1 - alpha) * current_avg
        
        self.metrics['trades']['last_update_time'] = datetime.utcnow()
    
    def get_quality_score(self, data_type: str) -> float:
        """
        计算数据质量评分（0-1）
        
        评分标准：
        - 拒绝率 < 1%: 1.0
        - 拒绝率 1-5%: 0.8
        - 拒绝率 5-10%: 0.5
        - 拒绝率 > 10%: 0.0
        """
        m = self.metrics[data_type]
        if m['received_count'] == 0:
            return 0.0
        
        reject_rate = m['rejected_count'] / m['received_count']
        
        if reject_rate < 0.01:
            return 1.0
        elif reject_rate < 0.05:
            return 0.8
        elif reject_rate < 0.10:
            return 0.5
        else:
            return 0.0
```

### 质量告警

```python
class QualityAlerts:
    """数据质量告警"""
    
    def check_alerts(self, metrics: DataQualityMetrics):
        """检查并发送告警"""
        
        for data_type, m in metrics.metrics.items():
            # 告警 1：数据停止更新
            if m['last_update_time']:
                gap = (datetime.utcnow() - m['last_update_time']).total_seconds()
                if gap > 60:  # 超过 1 分钟无更新
                    self.send_alert(
                        level='ERROR',
                        message=f"{data_type} 数据停止更新 {gap:.0f} 秒"
                    )
            
            # 告警 2：拒绝率过高
            if m['received_count'] > 100:
                reject_rate = m['rejected_count'] / m['received_count']
                if reject_rate > 0.10:
                    self.send_alert(
                        level='ERROR',
                        message=f"{data_type} 数据拒绝率过高: {reject_rate:.2%}"
                    )
            
            # 告警 3：延迟过高
            if data_type == 'trades' and m['avg_latency_ms'] > 5000:
                self.send_alert(
                    level='WARNING',
                    message=f"交易数据平均延迟过高: {m['avg_latency_ms']:.0f}ms"
                )
    
    def send_alert(self, level: str, message: str):
        """发送告警（邮件、Webhook、日志）"""
        logger.log(level, message)
        # TODO: 发送到告警系统（PagerDuty、钉钉、Slack 等）
```

---

## 存储架构

### 分层存储

```
┌─────────────────────────────────────────────────────────┐
│  L1: Redis (实时层)                                      │
│  - 最新价格、最新交易、最新 OI                            │
│  - TTL: 1 小时                                           │
│  - 用途: API 快速查询、去重缓存                          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  L2: TimescaleDB (历史层 - 详细数据)                     │
│  - Trades（逐笔成交）                                    │
│  - 1分钟 K 线                                            │
│  - Order Book 快照（每分钟）                             │
│  - 清算数据                                              │
│  - 保留期: 60 天                                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  L3: TimescaleDB (历史层 - 聚合数据)                     │
│  - 5分钟/15分钟/1小时/1天 K 线                           │
│  - 每日持仓量汇总                                        │
│  - 每日资金费率汇总                                      │
│  - 保留期: 永久（或 2 年）                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  L4: 特征案例库（永久）                                  │
│  - 从 L2/L3 提取的特征案例                               │
│  - 用户标注数据                                          │
│  - 特征向量                                              │
│  - 保留期: 永久                                          │
└─────────────────────────────────────────────────────────┘
```

### 数据表设计

详见 `DEVELOPMENT.md` 中的数据库设计部分，增加质量字段：

```sql
-- 增强的 trades 表
CREATE TABLE trades (
    time TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    trade_id VARCHAR(100) NOT NULL,
    price NUMERIC(20, 8) NOT NULL,
    quantity NUMERIC(20, 8) NOT NULL,
    side VARCHAR(10) NOT NULL,
    receipt_timestamp TIMESTAMPTZ NOT NULL,
    
    -- 质量字段
    quality_flags INTEGER DEFAULT 0,
    latency_ms INTEGER,
    
    PRIMARY KEY (time, symbol, trade_id)
);

SELECT create_hypertable('trades', 'time');
CREATE INDEX idx_trades_symbol_time ON trades (symbol, time DESC);
CREATE UNIQUE INDEX idx_trades_dedup ON trades (symbol, trade_id);
```

---

## 实施路线图

### Phase 1: P0 数据基础设施（4-6 周）

**Week 1-2: 核心框架**
- [ ] Cryptofeed 集成和封装
- [ ] 数据验证框架
- [ ] Redis + TimescaleDB 连接层
- [ ] 基础监控和日志

**Week 3-4: P0 数据采集（前 4 项）**
- [ ] Instruments 发现和订阅
- [ ] K 线实时采集和历史回填
- [ ] Trades 采集和 CVD 计算
- [ ] Open Interest 采集

**Week 5-6: P0 数据采集（后 4 项）**
- [ ] Funding Rate 采集
- [ ] Mark/Index Price 采集
- [ ] Order Book L2 采集和 OBI 计算
- [ ] Liquidation 采集和 Squeeze 检测

### Phase 2: 数据质量保障（2-3 周）

**Week 7-8: 质量监控**
- [ ] 质量指标收集
- [ ] 告警系统
- [ ] 数据质量 Dashboard（Grafana）
- [ ] 压力测试和优化

**Week 9: 稳定性验证**
- [ ] 7x24 运行测试
- [ ] 故障恢复测试
- [ ] 性能调优

### Phase 3: P1 辅助数据（1-2 周）

**Week 10-11:**
- [ ] Tickers 采集
- [ ] 多空比统计采集
- [ ] 数据完整性校验

### Phase 4: 上层应用（在数据稳定后）

**Week 12+:**
- [ ] 涨跌幅榜单功能
- [ ] 特征分析功能
- [ ] 机会发现功能

---

## 总结

### 核心原则

1. **数据质量第一**：没有高质量的数据，上层功能都是空中楼阁
2. **P0 优先级绝对**：8 项 P0 数据必须 100% 可靠
3. **清洗比采集更重要**：每条数据都经过严格验证
4. **监控不可缺**：实时监控数据质量，快速发现问题
5. **分层存储**：实时层 + 历史层 + 特征层

### 验收标准（M1 完成）

- [ ] P0 数据全部采集，质量评分 > 0.95
- [ ] 7x24 小时稳定运行，无重大故障
- [ ] 数据延迟 < 5 秒（P99）
- [ ] 数据拒绝率 < 1%
- [ ] 数据去重率 > 99.9%
- [ ] WebSocket 断线自动重连，数据无缺口
- [ ] 质量监控 Dashboard 可用
- [ ] 告警系统工作正常

只有在这个基础上，才能开始构建特征识别、机会发现等上层功能。

---

**文档版本**: v1.0.0  
**创建时间**: 2024-10-30  
**维护者**: SentinelPerp 开发团队
