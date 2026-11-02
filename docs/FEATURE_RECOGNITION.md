# 智能特征识别与机会发现系统

## 目录

- [功能概述](#功能概述)
- [系统架构](#系统架构)
- [功能模块详解](#功能模块详解)
- [数据库设计](#数据库设计)
- [API 设计](#api-设计)
- [大模型集成](#大模型集成)
- [前端页面设计](#前端页面设计)
- [实现路线图](#实现路线图)

---

## 功能概述

该系统在 M1 基础数据采集之上，构建智能特征识别和机会发现能力，主要包括：

### 核心功能

1. **每日涨跌幅榜单页面**
   - 实时显示涨跌幅 TOP 10 合约
   - 支持多时间维度（1h、4h、24h、7d）
   - 一键添加到特征分析

2. **特征分析页面**
   - 手动从涨跌幅榜添加合约
   - 通过大模型自动提取完整涨跌过程
   - 将行情特征分类到预定义容器

3. **特征容器管理**
   - 可配置的特征类型（吸筹、挤空、杀多等）
   - 特征模板定义
   - 特征匹配规则

4. **机会发现页面**
   - 基于历史特征库匹配当前市场
   - 识别币种所处阶段
   - 给出概率化的机会评估

### 业务价值

- **模式识别**：从历史数据中提取可复用的行情模式
- **早期预警**：识别特征相似的机会，提前布局
- **决策辅助**：量化评估机会质量，减少主观判断
- **知识沉淀**：将经验转化为可验证的特征库

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据采集层（M1）                          │
│  Trades | Candles | Funding | OI | Liquidations | Order Book    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      特征计算引擎（新增）                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  实时涨跌幅计算                                         │   │
│  │  - 1h / 4h / 24h / 7d 涨跌幅                            │   │
│  │  - 成交量变化率                                         │   │
│  │  - 波动率                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  派生特征计算                                           │   │
│  │  - CVD (累计成交量差)                                   │   │
│  │  - 盘口失衡度                                           │   │
│  │  - 资金费率分位数                                       │   │
│  │  - OI 变化率                                            │   │
│  │  - 清算强度                                             │   │
│  │  - 多空比                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      特征提取服务（新增）                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  大模型特征提取                                         │   │
│  │  - 输入：合约代码 + 时间段                              │   │
│  │  - 从数据库查询完整行情数据                             │   │
│  │  - 调用大模型分析涨跌过程                               │   │
│  │  - 输出：结构化特征描述                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  特征分类器                                             │   │
│  │  - 根据特征模板匹配                                     │   │
│  │  - 分配到特征容器                                       │   │
│  │  - 计算相似度得分                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      特征库（新增存储）                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  特征案例库                                             │   │
│  │  - 历史涨跌案例                                         │   │
│  │  - 特征向量                                             │   │
│  │  - 阶段标注                                             │   │
│  │  - 结果标签（涨幅/跌幅）                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  特征容器配置                                           │   │
│  │  - 容器定义（吸筹、挤空、杀多等）                       │   │
│  │  - 特征模板                                             │   │
│  │  - 匹配规则                                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      机会发现引擎（新增）                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  实时特征匹配                                           │   │
│  │  - 计算当前市场特征                                     │   │
│  │  - 与历史案例库对比                                     │   │
│  │  - 找出相似案例                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  阶段识别                                               │   │
│  │  - 判断当前所处阶段                                     │   │
│  │  - 预测后续走势概率                                     │   │
│  │  - 计算置信度                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                        前端展示层（新增）                        │
│  ┌────────────────┬────────────────┬────────────────────────┐   │
│  │ 涨跌幅榜单页面  │ 特征分析页面    │ 机会发现页面           │   │
│  │ - TOP 10 涨幅   │ - 添加分析对象  │ - 机会列表             │   │
│  │ - TOP 10 跌幅   │ - AI 特征提取   │ - 相似历史案例         │   │
│  │ - 多时间维度    │ - 特征分类      │ - 阶段判断             │   │
│  │ - 一键添加分析  │ - 可视化展示    │ - 概率评估             │   │
│  └────────────────┴────────────────┴────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 功能模块详解

### 1. 每日涨跌幅榜单页面

#### 功能需求

- **多时间维度排行**：
  - 1小时涨跌幅 TOP 10
  - 4小时涨跌幅 TOP 10
  - 24小时涨跌幅 TOP 10
  - 7天涨跌幅 TOP 10

- **展示信息**：
  - 合约名称（如 BTC-USDT-SWAP）
  - 当前价格
  - 涨跌幅百分比
  - 成交量变化
  - 资金费率
  - 持仓量变化

- **交互功能**：
  - 点击合约查看详细 K 线图
  - "添加到特征分析" 按钮
  - 自动刷新（60 秒）

#### 技术实现

**后端 API**：

```python
# backend/api/routes/leaderboard.py

from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from typing import List, Literal

router = APIRouter()

@router.get("/leaderboard/gainers")
async def get_top_gainers(
    timeframe: Literal["1h", "4h", "24h", "7d"] = "24h",
    limit: int = Query(10, le=50)
) -> List[LeaderboardItem]:
    """
    获取涨幅榜
    
    返回结构：
    {
        "symbol": "BTC-USDT-SWAP",
        "current_price": 67500.5,
        "change_percent": 8.5,
        "volume_change_percent": 45.2,
        "funding_rate": 0.0001,
        "oi_change_percent": 12.3,
        "start_price": 62200.0,
        "start_time": "2024-10-29T00:00:00Z",
        "end_time": "2024-10-30T00:00:00Z"
    }
    """
    # 1. 根据 timeframe 计算时间范围
    end_time = datetime.utcnow()
    if timeframe == "1h":
        start_time = end_time - timedelta(hours=1)
    elif timeframe == "4h":
        start_time = end_time - timedelta(hours=4)
    elif timeframe == "24h":
        start_time = end_time - timedelta(days=1)
    else:  # 7d
        start_time = end_time - timedelta(days=7)
    
    # 2. 从数据库查询每个合约的起始价和结束价
    query = """
    WITH price_range AS (
        SELECT 
            symbol,
            FIRST(close, time) as start_price,
            LAST(close, time) as end_price,
            SUM(volume) as total_volume
        FROM candles
        WHERE time >= $1 AND time <= $2
        AND interval = '1m'
        GROUP BY symbol
    )
    SELECT 
        pr.symbol,
        pr.start_price,
        pr.end_price,
        pr.total_volume,
        ((pr.end_price - pr.start_price) / pr.start_price * 100) as change_percent,
        latest.funding_rate,
        latest.open_interest
    FROM price_range pr
    LEFT JOIN LATERAL (
        SELECT funding_rate, open_interest
        FROM market_metrics
        WHERE symbol = pr.symbol
        ORDER BY time DESC
        LIMIT 1
    ) latest ON true
    ORDER BY change_percent DESC
    LIMIT $3
    """
    
    results = await db.fetch(query, start_time, end_time, limit)
    return results

@router.get("/leaderboard/losers")
async def get_top_losers(
    timeframe: Literal["1h", "4h", "24h", "7d"] = "24h",
    limit: int = Query(10, le=50)
) -> List[LeaderboardItem]:
    """获取跌幅榜（逻辑同涨幅榜，排序反向）"""
    pass
```

**前端组件**：

```typescript
// frontend/src/pages/Leaderboard.tsx

import React, { useState, useEffect } from 'react';

interface LeaderboardItem {
  symbol: string;
  current_price: number;
  change_percent: number;
  volume_change_percent: number;
  funding_rate: number;
  oi_change_percent: number;
}

const Leaderboard: React.FC = () => {
  const [timeframe, setTimeframe] = useState<'1h' | '4h' | '24h' | '7d'>('24h');
  const [gainers, setGainers] = useState<LeaderboardItem[]>([]);
  const [losers, setLosers] = useState<LeaderboardItem[]>([]);

  useEffect(() => {
    const fetchData = async () => {
      const [gainersRes, losersRes] = await Promise.all([
        fetch(`/api/v1/leaderboard/gainers?timeframe=${timeframe}`),
        fetch(`/api/v1/leaderboard/losers?timeframe=${timeframe}`)
      ]);
      setGainers(await gainersRes.json());
      setLosers(await losersRes.json());
    };

    fetchData();
    const interval = setInterval(fetchData, 60000); // 每分钟刷新
    return () => clearInterval(interval);
  }, [timeframe]);

  const handleAddToAnalysis = async (symbol: string) => {
    await fetch('/api/v1/features/analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, timeframe })
    });
    alert(`${symbol} 已添加到特征分析`);
  };

  return (
    <div className="leaderboard">
      {/* 时间维度选择器 */}
      <div className="timeframe-selector">
        {['1h', '4h', '24h', '7d'].map(tf => (
          <button 
            key={tf}
            className={timeframe === tf ? 'active' : ''}
            onClick={() => setTimeframe(tf as any)}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* 涨幅榜 */}
      <div className="gainers">
        <h2>涨幅榜 TOP 10</h2>
        <table>
          <thead>
            <tr>
              <th>合约</th>
              <th>当前价格</th>
              <th>涨幅</th>
              <th>成交量变化</th>
              <th>资金费率</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {gainers.map(item => (
              <tr key={item.symbol}>
                <td>{item.symbol}</td>
                <td>${item.current_price.toFixed(2)}</td>
                <td className="positive">+{item.change_percent.toFixed(2)}%</td>
                <td>{item.volume_change_percent.toFixed(1)}%</td>
                <td>{item.funding_rate.toFixed(4)}</td>
                <td>
                  <button onClick={() => handleAddToAnalysis(item.symbol)}>
                    添加分析
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 跌幅榜（结构同上）*/}
      <div className="losers">
        <h2>跌幅榜 TOP 10</h2>
        {/* ... */}
      </div>
    </div>
  );
};

export default Leaderboard;
```

---

### 2. 特征分析页面

#### 功能需求

- **添加分析对象**：从涨跌幅榜单一键添加
- **AI 特征提取**：调用大模型分析完整涨跌过程
- **特征可视化**：图表展示关键特征
- **手动分类**：将案例归入特征容器

#### 工作流程

```
用户点击"添加分析" 
    ↓
创建特征分析任务
    ↓
后台查询数据库（价格、成交量、资金费率、OI、清算等）
    ↓
构造 Prompt 调用大模型
    ↓
大模型返回结构化特征描述
    ↓
前端展示分析结果
    ↓
用户选择特征容器分类
    ↓
保存到特征案例库
```

#### 技术实现

**后端服务**：

```python
# backend/services/feature_extraction.py

from langchain import LLMChain, PromptTemplate
from langchain.chat_models import ChatOpenAI
import asyncio

class FeatureExtractionService:
    """
    大模型特征提取服务
    """
    
    def __init__(self, llm_provider: str = "openai"):
        # 支持 OpenAI / Claude / 本地模型
        self.llm = ChatOpenAI(model="gpt-4", temperature=0)
        
    async def extract_features(self, symbol: str, start_time, end_time):
        """
        提取合约在指定时间段的特征
        
        步骤：
        1. 从数据库查询完整数据
        2. 构造 Prompt
        3. 调用大模型
        4. 解析返回结果
        """
        # 1. 查询数据
        data = await self._fetch_complete_data(symbol, start_time, end_time)
        
        # 2. 构造 Prompt
        prompt = self._build_prompt(symbol, data)
        
        # 3. 调用大模型
        response = await self.llm.apredict(prompt)
        
        # 4. 解析结果
        features = self._parse_response(response)
        
        return features
    
    async def _fetch_complete_data(self, symbol: str, start_time, end_time):
        """
        从数据库查询完整数据
        """
        # 查询 1 分钟 K 线
        candles = await db.fetch("""
            SELECT time, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            AND interval = '1m'
            ORDER BY time
        """, symbol, start_time, end_time)
        
        # 查询资金费率
        funding_rates = await db.fetch("""
            SELECT time, funding_rate
            FROM funding_rates
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            ORDER BY time
        """, symbol, start_time, end_time)
        
        # 查询持仓量
        open_interest = await db.fetch("""
            SELECT time, open_interest
            FROM open_interest
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            ORDER BY time
        """, symbol, start_time, end_time)
        
        # 查询清算数据
        liquidations = await db.fetch("""
            SELECT time, side, quantity, price
            FROM liquidations
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            ORDER BY time
        """, symbol, start_time, end_time)
        
        # 计算派生指标
        cvd = self._calculate_cvd(candles)
        imbalance = self._calculate_orderbook_imbalance(symbol, start_time, end_time)
        
        return {
            "candles": candles,
            "funding_rates": funding_rates,
            "open_interest": open_interest,
            "liquidations": liquidations,
            "cvd": cvd,
            "imbalance": imbalance
        }
    
    def _build_prompt(self, symbol: str, data: dict) -> str:
        """
        构造大模型 Prompt
        """
        prompt = f"""
你是一个专业的加密货币市场分析师。请分析以下合约 {symbol} 在指定时间段的完整涨跌过程，并提取关键特征。

## 数据摘要

### 价格走势
- 起始价格: {data['candles'][0]['close']}
- 结束价格: {data['candles'][-1]['close']}
- 最高价: {max(c['high'] for c in data['candles'])}
- 最低价: {min(c['low'] for c in data['candles'])}
- 涨跌幅: {((data['candles'][-1]['close'] - data['candles'][0]['close']) / data['candles'][0]['close'] * 100):.2f}%

### 成交量
- 总成交量: {sum(c['volume'] for c in data['candles'])}
- 前半段成交量: {sum(c['volume'] for c in data['candles'][:len(data['candles'])//2])}
- 后半段成交量: {sum(c['volume'] for c in data['candles'][len(data['candles'])//2:])}

### 资金费率
- 平均资金费率: {sum(f['funding_rate'] for f in data['funding_rates']) / len(data['funding_rates']):.6f}
- 最高资金费率: {max(f['funding_rate'] for f in data['funding_rates']):.6f}
- 最低资金费率: {min(f['funding_rate'] for f in data['funding_rates']):.6f}

### 持仓量变化
- 起始持仓量: {data['open_interest'][0]['open_interest']}
- 结束持仓量: {data['open_interest'][-1]['open_interest']}
- 变化率: {((data['open_interest'][-1]['open_interest'] - data['open_interest'][0]['open_interest']) / data['open_interest'][0]['open_interest'] * 100):.2f}%

### 清算情况
- 多单清算总量: {sum(l['quantity'] for l in data['liquidations'] if l['side'] == 'long')}
- 空单清算总量: {sum(l['quantity'] for l in data['liquidations'] if l['side'] == 'short')}

### CVD（累计成交量差）
- 起始 CVD: {data['cvd'][0]}
- 结束 CVD: {data['cvd'][-1]}
- CVD 变化: {data['cvd'][-1] - data['cvd'][0]}

## 分析要求

请按以下格式输出分析结果（JSON 格式）：

```json
{{
  "stage_analysis": {{
    "accumulation": {{
      "detected": true/false,
      "time_range": ["2024-10-29T00:00:00Z", "2024-10-29T06:00:00Z"],
      "description": "在此阶段的特征描述",
      "key_indicators": {{
        "price_range": "窄幅震荡",
        "volume": "低位放量",
        "funding_rate": "接近零或负值",
        "oi_change": "缓慢上升",
        "cvd": "持续流入"
      }}
    }},
    "markup": {{
      "detected": true/false,
      "time_range": ["2024-10-29T06:00:00Z", "2024-10-29T18:00:00Z"],
      "description": "在此阶段的特征描述",
      "key_indicators": {{
        "price_action": "快速拉升",
        "volume": "显著放大",
        "funding_rate": "转正并上升",
        "liquidations": "空单集中爆仓",
        "oi_change": "急剧增加"
      }}
    }},
    "distribution": {{
      "detected": true/false,
      "time_range": ["2024-10-29T18:00:00Z", "2024-10-30T00:00:00Z"],
      "description": "在此阶段的特征描述",
      "key_indicators": {{
        "price_action": "高位震荡",
        "volume": "放量滞涨",
        "funding_rate": "极高水平",
        "cvd": "开始流出"
      }}
    }}
  }},
  "feature_classification": {{
    "primary_pattern": "accumulation_breakout / short_squeeze / bull_trap / wash_out",
    "confidence": 0.85,
    "similar_cases": ["历史案例1", "历史案例2"]
  }},
  "key_turning_points": [
    {{
      "time": "2024-10-29T06:15:00Z",
      "event": "突破吸筹区间",
      "trigger": "大额买单涌入，空单开始爆仓"
    }},
    {{
      "time": "2024-10-29T14:30:00Z",
      "event": "短暂回调",
      "trigger": "资金费率过高，多头止盈"
    }}
  ],
  "summary": "整体行情特征的总结描述"
}}
```

请基于数据进行深入分析，识别关键阶段和转折点。
"""
        return prompt
    
    def _parse_response(self, response: str) -> dict:
        """
        解析大模型返回的 JSON 结果
        """
        import json
        # 提取 JSON 部分
        start = response.find('{')
        end = response.rfind('}') + 1
        json_str = response[start:end]
        return json.loads(json_str)
```

**API 端点**：

```python
# backend/api/routes/features.py

from fastapi import APIRouter, BackgroundTasks
from datetime import datetime, timedelta

router = APIRouter()

@router.post("/features/analysis")
async def create_feature_analysis(
    symbol: str,
    timeframe: str,
    background_tasks: BackgroundTasks
):
    """
    创建特征分析任务
    
    这是一个异步任务，因为大模型调用可能需要较长时间
    """
    # 1. 计算时间范围
    end_time = datetime.utcnow()
    if timeframe == "1h":
        start_time = end_time - timedelta(hours=1)
    elif timeframe == "4h":
        start_time = end_time - timedelta(hours=4)
    elif timeframe == "24h":
        start_time = end_time - timedelta(days=1)
    else:  # 7d
        start_time = end_time - timedelta(days=7)
    
    # 2. 创建任务记录
    task_id = await db.fetchval("""
        INSERT INTO feature_analysis_tasks 
        (symbol, start_time, end_time, status, created_at)
        VALUES ($1, $2, $3, 'pending', NOW())
        RETURNING id
    """, symbol, start_time, end_time)
    
    # 3. 后台执行特征提取
    background_tasks.add_task(
        process_feature_extraction,
        task_id, symbol, start_time, end_time
    )
    
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "特征分析任务已创建，预计需要 30-60 秒"
    }

async def process_feature_extraction(task_id: int, symbol: str, start_time, end_time):
    """
    后台任务：执行特征提取
    """
    try:
        # 更新状态为处理中
        await db.execute("""
            UPDATE feature_analysis_tasks
            SET status = 'processing', updated_at = NOW()
            WHERE id = $1
        """, task_id)
        
        # 调用特征提取服务
        service = FeatureExtractionService()
        features = await service.extract_features(symbol, start_time, end_time)
        
        # 保存结果
        await db.execute("""
            UPDATE feature_analysis_tasks
            SET status = 'completed', 
                result = $2,
                updated_at = NOW()
            WHERE id = $1
        """, task_id, json.dumps(features))
        
    except Exception as e:
        # 记录错误
        await db.execute("""
            UPDATE feature_analysis_tasks
            SET status = 'failed',
                error_message = $2,
                updated_at = NOW()
            WHERE id = $1
        """, task_id, str(e))

@router.get("/features/analysis/{task_id}")
async def get_analysis_result(task_id: int):
    """
    查询特征分析结果
    """
    result = await db.fetchrow("""
        SELECT id, symbol, status, result, error_message, created_at, updated_at
        FROM feature_analysis_tasks
        WHERE id = $1
    """, task_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return result

@router.post("/features/cases")
async def save_feature_case(
    task_id: int,
    container_type: str,  # accumulation, short_squeeze, long_liquidation 等
    manual_labels: dict = None
):
    """
    将分析结果保存为特征案例
    
    用户可以：
    - 选择特征容器类型
    - 添加手动标签
    - 调整大模型的分类结果
    """
    # 1. 获取分析结果
    analysis = await db.fetchrow("""
        SELECT symbol, start_time, end_time, result
        FROM feature_analysis_tasks
        WHERE id = $1 AND status = 'completed'
    """, task_id)
    
    if not analysis:
        raise HTTPException(status_code=400, detail="任务未完成或不存在")
    
    # 2. 保存到特征案例库
    case_id = await db.fetchval("""
        INSERT INTO feature_cases
        (symbol, start_time, end_time, container_type, features, manual_labels, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING id
    """, 
        analysis['symbol'],
        analysis['start_time'],
        analysis['end_time'],
        container_type,
        analysis['result'],
        json.dumps(manual_labels) if manual_labels else None
    )
    
    return {
        "case_id": case_id,
        "message": "特征案例已保存"
    }
```

**前端组件**：

```typescript
// frontend/src/pages/FeatureAnalysis.tsx

import React, { useState, useEffect } from 'react';

const FeatureAnalysis: React.FC = () => {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);

  // 轮询检查任务状态
  useEffect(() => {
    const interval = setInterval(async () => {
      for (const task of tasks.filter(t => t.status === 'pending' || t.status === 'processing')) {
        const res = await fetch(`/api/v1/features/analysis/${task.id}`);
        const updated = await res.json();
        if (updated.status === 'completed') {
          setTasks(prev => prev.map(t => t.id === task.id ? updated : t));
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [tasks]);

  const handleSaveCase = async (taskId: number, containerType: string) => {
    await fetch('/api/v1/features/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, container_type: containerType })
    });
    alert('案例已保存到特征库');
  };

  return (
    <div className="feature-analysis">
      <h1>特征分析</h1>
      
      {/* 任务列表 */}
      <div className="tasks-list">
        {tasks.map(task => (
          <div key={task.id} className={`task-card ${task.status}`}>
            <h3>{task.symbol}</h3>
            <p>状态: {task.status}</p>
            {task.status === 'completed' && (
              <button onClick={() => setSelectedTask(task)}>
                查看分析结果
              </button>
            )}
          </div>
        ))}
      </div>

      {/* 分析结果详情 */}
      {selectedTask && (
        <div className="analysis-detail">
          <h2>{selectedTask.symbol} 特征分析</h2>
          
          {/* 阶段分析 */}
          <div className="stages">
            <h3>阶段识别</h3>
            {Object.entries(selectedTask.result.stage_analysis).map(([stage, data]) => (
              data.detected && (
                <div key={stage} className="stage-card">
                  <h4>{stage}</h4>
                  <p>{data.description}</p>
                  <ul>
                    {Object.entries(data.key_indicators).map(([key, value]) => (
                      <li key={key}>{key}: {value}</li>
                    ))}
                  </ul>
                </div>
              )
            ))}
          </div>

          {/* 关键转折点 */}
          <div className="turning-points">
            <h3>关键转折点</h3>
            <timeline>
              {selectedTask.result.key_turning_points.map((point, idx) => (
                <div key={idx} className="point">
                  <span className="time">{point.time}</span>
                  <span className="event">{point.event}</span>
                  <span className="trigger">{point.trigger}</span>
                </div>
              ))}
            </timeline>
          </div>

          {/* 特征分类 */}
          <div className="classification">
            <h3>特征分类</h3>
            <p>主要模式: {selectedTask.result.feature_classification.primary_pattern}</p>
            <p>置信度: {(selectedTask.result.feature_classification.confidence * 100).toFixed(1)}%</p>
            
            {/* 选择特征容器 */}
            <div className="container-selector">
              <h4>保存到特征容器</h4>
              <select onChange={(e) => handleSaveCase(selectedTask.id, e.target.value)}>
                <option value="">选择容器...</option>
                <option value="accumulation">吸筹（卖盘枯竭）</option>
                <option value="short_squeeze">挤空（多空比失衡）</option>
                <option value="long_liquidation">杀多（多单爆仓）</option>
                <option value="distribution">派发（高位出货）</option>
                <option value="wash_out">洗盘（假跌真涨）</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FeatureAnalysis;
```

---

### 3. 特征容器管理

#### 功能需求

- **容器定义**：管理员可配置特征容器类型
- **特征模板**：定义每个容器的典型特征
- **匹配规则**：设置自动分类的规则

#### 容器配置示例

```yaml
# config/feature_containers.yaml

containers:
  - id: accumulation
    name: 吸筹（卖盘枯竭）
    description: 价格在低位窄幅震荡，成交量萎缩，卖盘逐渐枯竭
    template:
      price_pattern: sideways_consolidation
      volume_pattern: decreasing
      funding_rate: near_zero_or_negative
      oi_change: slow_increase
      cvd: accumulating
      orderbook_imbalance: bid_side_building
    
  - id: short_squeeze
    name: 挤空（多空比失衡）
    description: 空头持仓过大，突然上涨导致空单爆仓，形成连锁反应
    template:
      price_pattern: sharp_breakout_up
      volume_pattern: explosive
      funding_rate: turning_positive
      liquidations: short_dominated
      oi_change: rapid_increase_then_drop
      cvd: strong_buying
      
  - id: long_liquidation
    name: 杀多（多单爆仓）
    description: 多头持仓过大，突然下跌导致多单爆仓
    template:
      price_pattern: sharp_breakdown
      volume_pattern: spike
      funding_rate: extremely_high_before_drop
      liquidations: long_dominated
      oi_change: rapid_decrease
      cvd: strong_selling
      
  - id: distribution
    name: 派发（高位出货）
    description: 价格在高位震荡，大资金逐步出货
    template:
      price_pattern: sideways_at_top
      volume_pattern: high_but_declining
      funding_rate: very_high
      cvd: starting_to_distribute
      orderbook_imbalance: ask_side_building
      
  - id: wash_out
    name: 洗盘（假跌真涨）
    description: 上涨途中突然回调，清洗浮筹后继续上涨
    template:
      price_pattern: temporary_pullback
      volume_pattern: spike_on_drop
      liquidations: long_flush
      oi_change: slight_decrease
      cvd: absorption_after_drop
```

#### 自动分类逻辑

```python
# backend/services/feature_classifier.py

class FeatureClassifier:
    """
    特征自动分类器
    """
    
    def __init__(self):
        self.containers = self._load_container_config()
    
    def classify(self, features: dict) -> List[Tuple[str, float]]:
        """
        将特征分类到容器
        
        返回: [(container_id, confidence_score), ...]
        """
        scores = []
        
        for container in self.containers:
            score = self._calculate_similarity(features, container['template'])
            scores.append((container['id'], score))
        
        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def _calculate_similarity(self, features: dict, template: dict) -> float:
        """
        计算特征与模板的相似度
        
        使用加权匹配算法
        """
        weights = {
            'price_pattern': 0.25,
            'volume_pattern': 0.20,
            'funding_rate': 0.15,
            'liquidations': 0.15,
            'oi_change': 0.15,
            'cvd': 0.10
        }
        
        total_score = 0.0
        for key, weight in weights.items():
            if key in features and key in template:
                match_score = self._pattern_match(features[key], template[key])
                total_score += match_score * weight
        
        return total_score
    
    def _pattern_match(self, actual: str, expected: str) -> float:
        """
        模式匹配评分（0-1）
        """
        # 实现具体的模式匹配逻辑
        # 例如：字符串相似度、数值范围匹配等
        if actual == expected:
            return 1.0
        # 更复杂的匹配逻辑...
        return 0.5
```

---

### 4. 机会发现页面

#### 功能需求

- **实时扫描**：定期扫描所有合约的当前特征
- **相似度匹配**：与历史案例库对比
- **阶段判断**：识别当前所处阶段
- **机会排序**：按置信度和潜在收益排序

#### 技术实现

**后端服务**：

```python
# backend/services/opportunity_finder.py

class OpportunityFinder:
    """
    机会发现引擎
    """
    
    async def scan_opportunities(self, lookback_minutes: int = 60):
        """
        扫描当前市场中的机会
        
        返回: List[Opportunity]
        """
        opportunities = []
        
        # 1. 获取所有活跃合约
        symbols = await self._get_active_symbols()
        
        # 2. 并发计算每个合约的当前特征
        current_features = await asyncio.gather(*[
            self._calculate_current_features(symbol, lookback_minutes)
            for symbol in symbols
        ])
        
        # 3. 与历史案例库匹配
        for symbol, features in zip(symbols, current_features):
            similar_cases = await self._find_similar_cases(features, limit=10)
            
            if similar_cases:
                opportunity = self._evaluate_opportunity(
                    symbol, features, similar_cases
                )
                if opportunity['confidence'] > 0.6:  # 置信度阈值
                    opportunities.append(opportunity)
        
        # 4. 按评分排序
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        return opportunities
    
    async def _find_similar_cases(self, features: dict, limit: int = 10):
        """
        从特征案例库中找出相似案例
        
        使用向量相似度搜索（需要预先计算特征向量）
        """
        # 1. 将当前特征转换为向量
        feature_vector = self._features_to_vector(features)
        
        # 2. 在数据库中搜索相似向量
        # 使用 pgvector 扩展进行高效向量搜索
        query = """
        SELECT 
            id, symbol, start_time, end_time,
            container_type, features,
            outcome_return,
            1 - (feature_vector <=> $1) as similarity
        FROM feature_cases
        WHERE container_type = $2
        ORDER BY feature_vector <=> $1
        LIMIT $3
        """
        
        results = await db.fetch(
            query,
            feature_vector,
            features['primary_container'],
            limit
        )
        
        return results
    
    def _evaluate_opportunity(
        self, 
        symbol: str, 
        current_features: dict, 
        similar_cases: List[dict]
    ) -> dict:
        """
        评估机会质量
        
        计算：
        - 相似度均值
        - 历史案例的平均收益
        - 成功率
        - 置信度
        """
        # 计算平均相似度
        avg_similarity = sum(c['similarity'] for c in similar_cases) / len(similar_cases)
        
        # 计算历史收益统计
        returns = [c['outcome_return'] for c in similar_cases if c['outcome_return']]
        avg_return = sum(returns) / len(returns) if returns else 0
        success_rate = sum(1 for r in returns if r > 0) / len(returns) if returns else 0
        
        # 识别当前阶段
        stage = self._identify_stage(current_features, similar_cases)
        
        # 计算综合评分
        score = (
            avg_similarity * 0.4 +
            success_rate * 0.3 +
            min(abs(avg_return) / 20, 1.0) * 0.3  # 归一化收益率
        )
        
        return {
            "symbol": symbol,
            "stage": stage,
            "confidence": avg_similarity,
            "similar_cases_count": len(similar_cases),
            "avg_historical_return": avg_return,
            "success_rate": success_rate,
            "score": score,
            "top_similar_cases": similar_cases[:3]
        }
    
    def _identify_stage(self, current_features: dict, similar_cases: List[dict]) -> dict:
        """
        识别当前所处阶段
        
        基于相似案例的阶段分布
        """
        # 从相似案例中提取阶段信息
        stages_distribution = {}
        for case in similar_cases:
            case_features = case['features']
            for stage_name, stage_data in case_features.get('stage_analysis', {}).items():
                if stage_data.get('detected'):
                    stages_distribution[stage_name] = stages_distribution.get(stage_name, 0) + 1
        
        # 找出最可能的阶段
        if stages_distribution:
            most_likely_stage = max(stages_distribution.items(), key=lambda x: x[1])
            return {
                "current_stage": most_likely_stage[0],
                "probability": most_likely_stage[1] / len(similar_cases),
                "next_stages": self._predict_next_stages(most_likely_stage[0], similar_cases)
            }
        
        return {"current_stage": "unknown", "probability": 0}
    
    def _predict_next_stages(self, current_stage: str, similar_cases: List[dict]) -> List[dict]:
        """
        基于历史案例预测后续可能的阶段
        """
        # 分析历史案例中当前阶段后发生了什么
        next_stage_count = {}
        
        for case in similar_cases:
            stages = case['features'].get('stage_analysis', {})
            stage_names = [s for s, d in stages.items() if d.get('detected')]
            
            # 找到当前阶段的索引
            if current_stage in stage_names:
                idx = stage_names.index(current_stage)
                if idx < len(stage_names) - 1:
                    next_stage = stage_names[idx + 1]
                    next_stage_count[next_stage] = next_stage_count.get(next_stage, 0) + 1
        
        # 转换为概率分布
        total = sum(next_stage_count.values())
        predictions = [
            {"stage": stage, "probability": count / total}
            for stage, count in next_stage_count.items()
        ]
        predictions.sort(key=lambda x: x['probability'], reverse=True)
        
        return predictions[:3]
```

**API 端点**：

```python
# backend/api/routes/opportunities.py

from fastapi import APIRouter

router = APIRouter()

@router.get("/opportunities")
async def get_opportunities(
    min_confidence: float = 0.6,
    min_success_rate: float = 0.5,
    limit: int = 20
):
    """
    获取当前市场机会列表
    
    返回结构：
    {
        "symbol": "BTC-USDT-SWAP",
        "stage": {
            "current_stage": "accumulation",
            "probability": 0.85,
            "next_stages": [
                {"stage": "markup", "probability": 0.7},
                {"stage": "distribution", "probability": 0.3}
            ]
        },
        "confidence": 0.82,
        "avg_historical_return": 15.3,
        "success_rate": 0.75,
        "score": 0.78,
        "similar_cases_count": 8
    }
    """
    finder = OpportunityFinder()
    opportunities = await finder.scan_opportunities()
    
    # 过滤
    filtered = [
        opp for opp in opportunities
        if opp['confidence'] >= min_confidence
        and opp['success_rate'] >= min_success_rate
    ]
    
    return filtered[:limit]

@router.get("/opportunities/{symbol}")
async def get_opportunity_detail(symbol: str):
    """
    获取特定合约的机会详情
    
    包括：
    - 当前特征
    - 相似历史案例（带图表）
    - 阶段判断
    - 风险提示
    """
    finder = OpportunityFinder()
    
    # 计算当前特征
    current_features = await finder._calculate_current_features(symbol, lookback_minutes=60)
    
    # 找相似案例
    similar_cases = await finder._find_similar_cases(current_features, limit=10)
    
    # 评估
    opportunity = finder._evaluate_opportunity(symbol, current_features, similar_cases)
    
    return {
        "symbol": symbol,
        "current_features": current_features,
        "opportunity": opportunity,
        "similar_cases": similar_cases
    }
```

**前端组件**：

```typescript
// frontend/src/pages/Opportunities.tsx

import React, { useState, useEffect } from 'react';

const Opportunities: React.FC = () => {
  const [opportunities, setOpportunities] = useState([]);
  const [filters, setFilters] = useState({
    minConfidence: 0.6,
    minSuccessRate: 0.5
  });

  useEffect(() => {
    const fetchOpportunities = async () => {
      const res = await fetch(
        `/api/v1/opportunities?min_confidence=${filters.minConfidence}&min_success_rate=${filters.minSuccessRate}`
      );
      const data = await res.json();
      setOpportunities(data);
    };

    fetchOpportunities();
    const interval = setInterval(fetchOpportunities, 300000); // 每 5 分钟刷新
    return () => clearInterval(interval);
  }, [filters]);

  return (
    <div className="opportunities">
      <h1>机会发现</h1>

      {/* 过滤器 */}
      <div className="filters">
        <label>
          最低置信度:
          <input 
            type="range" 
            min="0" 
            max="1" 
            step="0.1"
            value={filters.minConfidence}
            onChange={e => setFilters({...filters, minConfidence: parseFloat(e.target.value)})}
          />
          {(filters.minConfidence * 100).toFixed(0)}%
        </label>
        <label>
          最低成功率:
          <input 
            type="range" 
            min="0" 
            max="1" 
            step="0.1"
            value={filters.minSuccessRate}
            onChange={e => setFilters({...filters, minSuccessRate: parseFloat(e.target.value)})}
          />
          {(filters.minSuccessRate * 100).toFixed(0)}%
        </label>
      </div>

      {/* 机会列表 */}
      <div className="opportunities-grid">
        {opportunities.map(opp => (
          <div key={opp.symbol} className="opportunity-card">
            <h3>{opp.symbol}</h3>
            
            {/* 阶段显示 */}
            <div className="stage">
              <span className="label">当前阶段:</span>
              <span className="value">{opp.stage.current_stage}</span>
              <span className="probability">({(opp.stage.probability * 100).toFixed(0)}%)</span>
            </div>

            {/* 预测下一阶段 */}
            <div className="next-stages">
              <span className="label">预测走势:</span>
              {opp.stage.next_stages.map(ns => (
                <div key={ns.stage}>
                  {ns.stage} ({(ns.probability * 100).toFixed(0)}%)
                </div>
              ))}
            </div>

            {/* 统计指标 */}
            <div className="metrics">
              <div className="metric">
                <span className="label">置信度</span>
                <span className="value">{(opp.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="metric">
                <span className="label">历史平均收益</span>
                <span className={`value ${opp.avg_historical_return > 0 ? 'positive' : 'negative'}`}>
                  {opp.avg_historical_return > 0 ? '+' : ''}{opp.avg_historical_return.toFixed(2)}%
                </span>
              </div>
              <div className="metric">
                <span className="label">成功率</span>
                <span className="value">{(opp.success_rate * 100).toFixed(0)}%</span>
              </div>
              <div className="metric">
                <span className="label">相似案例</span>
                <span className="value">{opp.similar_cases_count} 个</span>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="actions">
              <button onClick={() => window.location.href = `/opportunities/${opp.symbol}`}>
                查看详情
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Opportunities;
```

---

## 数据库设计

### 新增表结构

```sql
-- 特征分析任务表
CREATE TABLE feature_analysis_tasks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed
    result JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

CREATE INDEX idx_feature_tasks_status ON feature_analysis_tasks(status);
CREATE INDEX idx_feature_tasks_symbol ON feature_analysis_tasks(symbol);

-- 特征案例库
CREATE TABLE feature_cases (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    container_type VARCHAR(50) NOT NULL,  -- accumulation, short_squeeze, 等
    features JSONB NOT NULL,
    manual_labels JSONB,
    outcome_return NUMERIC(10, 4),  -- 后续实际涨跌幅
    outcome_time TIMESTAMPTZ,       -- 收益计算的截止时间
    feature_vector VECTOR(128),     -- 特征向量（用于相似度搜索）
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

-- 为向量搜索创建索引（需要 pgvector 扩展）
CREATE INDEX idx_feature_cases_vector ON feature_cases USING ivfflat (feature_vector vector_cosine_ops);
CREATE INDEX idx_feature_cases_container ON feature_cases(container_type);
CREATE INDEX idx_feature_cases_symbol ON feature_cases(symbol);

-- 特征容器配置表
CREATE TABLE feature_containers (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    template JSONB NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

-- 市场指标缓存表（加速机会扫描）
CREATE TABLE market_metrics (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    price NUMERIC(20, 8),
    volume_1h NUMERIC(20, 8),
    price_change_1h NUMERIC(10, 4),
    price_change_4h NUMERIC(10, 4),
    price_change_24h NUMERIC(10, 4),
    price_change_7d NUMERIC(10, 4),
    funding_rate NUMERIC(10, 8),
    open_interest NUMERIC(20, 8),
    oi_change_24h NUMERIC(10, 4),
    liquidation_volume_24h NUMERIC(20, 8),
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable('market_metrics', 'time');
CREATE INDEX idx_market_metrics_symbol ON market_metrics(symbol, time DESC);
```

---

## API 设计

### 完整 API 清单

```
# 涨跌幅榜单
GET  /api/v1/leaderboard/gainers?timeframe=24h&limit=10
GET  /api/v1/leaderboard/losers?timeframe=24h&limit=10

# 特征分析
POST /api/v1/features/analysis
GET  /api/v1/features/analysis/{task_id}
POST /api/v1/features/cases

# 特征容器管理
GET  /api/v1/features/containers
POST /api/v1/features/containers
PUT  /api/v1/features/containers/{container_id}
GET  /api/v1/features/cases?container_type=accumulation&limit=20

# 机会发现
GET  /api/v1/opportunities?min_confidence=0.6&limit=20
GET  /api/v1/opportunities/{symbol}
```

---

## 大模型集成

### 支持的模型

1. **OpenAI GPT-4**
   - 适合：快速迭代，API 稳定
   - 成本：约 $0.03 / 1K tokens（输入）

2. **Anthropic Claude**
   - 适合：更长上下文（100K tokens）
   - 成本：约 $0.01 / 1K tokens

3. **本地模型（可选）**
   - 适合：降低成本，数据隐私
   - 选项：Llama 3, Mixtral

### 配置方式

```yaml
# .env

# 大模型配置
LLM_PROVIDER=openai  # openai / anthropic / local
LLM_MODEL=gpt-4-turbo
LLM_API_KEY=sk-...
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096

# 特征提取配置
FEATURE_EXTRACTION_ENABLED=true
FEATURE_EXTRACTION_CONCURRENCY=3  # 并发数量
```

### 成本估算

假设：
- 每次分析平均使用 8K tokens
- 每天分析 20 个合约
- 使用 GPT-4 Turbo

**月成本估算**：
- 输入: 8K tokens × 20 次/天 × 30 天 = 4.8M tokens
- 成本: 4.8M × $0.01 / 1K ≈ **$48/月**

---

## 前端页面设计

### 页面结构

```
/leaderboard         涨跌幅榜单页
/features/analysis   特征分析页
/features/containers 特征容器管理页
/opportunities       机会发现页
/opportunities/:symbol  机会详情页
```

### 技术选型建议

- **框架**: React 18 + TypeScript
- **状态管理**: Zustand / Jotai（轻量级）
- **图表**: Recharts / TradingView Lightweight Charts
- **UI 组件**: Ant Design / Shadcn UI
- **实时通信**: WebSocket（可选，推送机会提醒）

---

## 实现路线图

### Phase 1: 基础功能（2-3 周）

- [ ] 涨跌幅计算引擎
- [ ] 涨跌幅榜单 API 和前端页面
- [ ] 数据库表结构创建
- [ ] 大模型集成基础框架

### Phase 2: 特征提取（3-4 周）

- [ ] 完整数据查询逻辑
- [ ] Prompt 工程和优化
- [ ] 特征分析任务后台处理
- [ ] 特征分析前端页面
- [ ] 特征案例库存储

### Phase 3: 特征容器（2 周）

- [ ] 特征容器配置管理
- [ ] 自动分类器实现
- [ ] 手动标注界面
- [ ] 特征向量生成

### Phase 4: 机会发现（3-4 周）

- [ ] 相似度搜索引擎（pgvector）
- [ ] 阶段识别算法
- [ ] 机会评分系统
- [ ] 机会发现前端页面
- [ ] 机会详情页和历史案例对比

### Phase 5: 优化与迭代（持续）

- [ ] 性能优化（缓存、索引）
- [ ] 模型准确性调优
- [ ] 增加更多特征容器
- [ ] 用户反馈和修正机制
- [ ] 移动端适配（可选）

---

## 总结

这个功能模块是 SentinelPerp 项目从数据采集到智能分析的关键升级，核心价值在于：

1. **自动化特征识别**：用 AI 代替人工分析，提高效率
2. **知识沉淀**：将市场模式转化为可复用的案例库
3. **概率化决策**：基于历史数据给出量化的机会评估
4. **持续学习**：随着案例积累，系统准确性不断提升

建议先实现 Phase 1 和 Phase 2，验证核心价值后再扩展到完整系统。

---

**文档版本**: v0.1.0  
**创建时间**: 2024-10-30  
**维护者**: SentinelPerp 开发团队
