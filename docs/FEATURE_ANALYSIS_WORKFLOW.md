# 特征分析工作流程详细设计

## 核心改进：手动时间段选择

根据最新需求，特征分析页面支持：
1. 从涨跌幅榜手动添加合约到特征分析
2. 大模型自动提取完整涨跌过程（查询最近 60 天内的数据）
3. **用户可以手动选择时间段**，只将特定阶段保存到特征库
4. 数据库保存 60 天历史数据

---

## 完整工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 用户从涨跌幅榜添加合约                              │
│  - 点击"添加分析"按钮                                        │
│  - 选择分析时间范围（默认根据榜单的 timeframe）              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 创建特征分析任务                                    │
│  - 记录：symbol, start_time, end_time                        │
│  - 状态：pending                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: 后台查询完整数据（最近 60 天内）                    │
│  - 1分钟 K 线数据                                            │
│  - 资金费率变化                                              │
│  - 持仓量变化                                                │
│  - 清算数据                                                  │
│  - 订单簿快照                                                │
│  - 计算派生指标（CVD、盘口失衡等）                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 调用大模型分析                                      │
│  - 识别完整的涨跌阶段（吸筹、拉升、派发等）                  │
│  - 标注关键转折点                                            │
│  - 提取每个阶段的特征指标                                    │
│  - 返回结构化 JSON                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 5: 前端展示分析结果                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  时间轴可视化（支持拖拽选择）                         │  │
│  │  ════════════════════════════════════════════════════ │  │
│  │  [吸筹阶段]   [拉升阶段]   [派发阶段]                │  │
│  │  12:00-18:00  18:00-22:00  22:00-02:00               │  │
│  │  ════════════════════════════════════════════════════ │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  K 线图 + 成交量 + 特征标注                           │  │
│  │  - 显示完整时间段的行情                               │  │
│  │  - 高亮显示大模型识别的阶段                           │  │
│  │  - 标注关键转折点                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  阶段详情面板                                         │  │
│  │  - 每个阶段的特征描述                                 │  │
│  │  - 关键指标数值                                       │  │
│  │  - 大模型的置信度                                     │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 6: 用户手动选择时间段保存                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  选择方式 1: 点击预识别的阶段                         │  │
│  │  [吸筹阶段] ← 点击这里                                │  │
│  │  ↓                                                     │  │
│  │  弹出保存对话框                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  选择方式 2: 在时间轴上手动拖拽选择                   │  │
│  │  ════════[════用户选择范围════]══════════════════════ │  │
│  │  ↓                                                     │  │
│  │  弹出保存对话框                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  保存对话框                                           │  │
│  │  - 选择特征容器（吸筹/挤空/杀多/派发/洗盘）          │  │
│  │  - 添加自定义标签                                     │  │
│  │  - 调整时间范围                                       │  │
│  │  - 备注说明                                           │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 7: 保存到特征案例库                                    │
│  - 只保存用户选择的时间段数据                                │
│  - 关联到特征容器                                            │
│  - 生成特征向量（用于后续相似度搜索）                        │
│  - 记录用户标注信息                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## API 设计

### 1. 创建特征分析任务

```http
POST /api/v1/features/analysis

Request Body:
{
  "symbol": "BTC-USDT-SWAP",
  "start_time": "2024-10-29T00:00:00Z",  // 可选，默认根据当前时间往前推
  "end_time": "2024-10-30T00:00:00Z",    // 可选，默认当前时间
  "lookback_days": 7                     // 可选，分析最近 N 天（优先级低于 start_time/end_time）
}

Response:
{
  "task_id": 12345,
  "symbol": "BTC-USDT-SWAP",
  "start_time": "2024-10-29T00:00:00Z",
  "end_time": "2024-10-30T00:00:00Z",
  "status": "pending",
  "created_at": "2024-10-30T15:00:00Z",
  "estimated_completion_seconds": 45
}
```

### 2. 查询分析结果

```http
GET /api/v1/features/analysis/{task_id}

Response:
{
  "task_id": 12345,
  "symbol": "BTC-USDT-SWAP",
  "start_time": "2024-10-29T00:00:00Z",
  "end_time": "2024-10-30T00:00:00Z",
  "status": "completed",  // pending | processing | completed | failed
  "result": {
    "stages": [
      {
        "stage_type": "accumulation",
        "start_time": "2024-10-29T00:00:00Z",
        "end_time": "2024-10-29T06:00:00Z",
        "duration_hours": 6,
        "description": "价格在 62000-63000 窄幅震荡，成交量萎缩，卖盘枯竭",
        "key_indicators": {
          "price_range": "narrow",
          "volume_trend": "decreasing",
          "funding_rate_avg": -0.0001,
          "oi_change_percent": 2.5,
          "cvd_change": 150.3
        },
        "confidence": 0.85
      },
      {
        "stage_type": "markup",
        "start_time": "2024-10-29T06:00:00Z",
        "end_time": "2024-10-29T18:00:00Z",
        "duration_hours": 12,
        "description": "突破 63000 后快速拉升至 67500，空单爆仓 1200 BTC",
        "key_indicators": {
          "price_change_percent": 7.1,
          "volume_spike": 3.5,
          "liquidation_long": 230.5,
          "liquidation_short": 1210.8,
          "funding_rate_change": 0.0005
        },
        "confidence": 0.92
      },
      {
        "stage_type": "distribution",
        "start_time": "2024-10-29T18:00:00Z",
        "end_time": "2024-10-30T00:00:00Z",
        "duration_hours": 6,
        "description": "高位震荡，资金费率极高，CVD 开始流出",
        "key_indicators": {
          "price_range": "narrow_at_top",
          "volume": "high_but_declining",
          "funding_rate_avg": 0.0008,
          "cvd_change": -85.2
        },
        "confidence": 0.78
      }
    ],
    "turning_points": [
      {
        "time": "2024-10-29T06:15:00Z",
        "event": "突破吸筹区间",
        "trigger": "大额买单涌入，空单开始爆仓",
        "price_before": 62950,
        "price_after": 63850
      },
      {
        "time": "2024-10-29T14:30:00Z",
        "event": "短暂回调",
        "trigger": "资金费率过高，多头止盈",
        "price_before": 67200,
        "price_after": 65800
      }
    ],
    "overall_summary": "典型的吸筹-拉升-派发周期，空单挤压是主要推动力",
    "suggested_container": "short_squeeze",
    "ai_confidence": 0.88
  },
  "raw_data": {
    "candles_count": 1440,  // 1分钟 K 线数量
    "data_completeness": 0.98
  }
}
```

### 3. 保存特征案例（支持时间段选择）

```http
POST /api/v1/features/cases

Request Body:
{
  "task_id": 12345,
  "symbol": "BTC-USDT-SWAP",
  
  // 关键：用户选择的时间段
  "selected_start_time": "2024-10-29T00:00:00Z",
  "selected_end_time": "2024-10-29T06:00:00Z",
  
  // 特征容器分类
  "container_type": "accumulation",
  
  // 可选：用户自定义标签
  "custom_tags": ["低位吸筹", "卖盘枯竭", "资金费率负值"],
  
  // 可选：用户备注
  "notes": "这是一个典型的低位吸筹案例，成交量持续萎缩，最终突破",
  
  // 可选：手动调整特征
  "manual_features": {
    "price_pattern": "sideways_consolidation",
    "volume_pattern": "decreasing",
    "key_observation": "资金费率从正转负，显示空头优势消失"
  }
}

Response:
{
  "case_id": 789,
  "symbol": "BTC-USDT-SWAP",
  "start_time": "2024-10-29T00:00:00Z",
  "end_time": "2024-10-29T06:00:00Z",
  "container_type": "accumulation",
  "feature_vector_id": "vec_abc123",
  "message": "特征案例已保存到吸筹容器",
  "similar_cases_count": 5  // 特征库中已有相似案例数量
}
```

### 4. 获取分析任务的可用时间范围

```http
GET /api/v1/features/analysis/{task_id}/timerange

Response:
{
  "task_id": 12345,
  "symbol": "BTC-USDT-SWAP",
  "available_range": {
    "start_time": "2024-09-01T00:00:00Z",  // 数据库最早数据
    "end_time": "2024-10-30T15:00:00Z",     // 当前时间
    "max_lookback_days": 60
  },
  "current_analysis_range": {
    "start_time": "2024-10-29T00:00:00Z",
    "end_time": "2024-10-30T00:00:00Z"
  },
  "stages": [...]  // 已识别的阶段（方便用户快速选择）
}
```

---

## 前端组件设计

### 特征分析页面核心组件

```typescript
// frontend/src/pages/FeatureAnalysis.tsx

import React, { useState, useEffect } from 'react';
import { TimeRangeSelector } from '../components/TimeRangeSelector';
import { StageTimeline } from '../components/StageTimeline';
import { FeatureChart } from '../components/FeatureChart';
import { SaveCaseDialog } from '../components/SaveCaseDialog';

interface AnalysisTask {
  task_id: number;
  symbol: string;
  status: string;
  result?: AnalysisResult;
}

interface AnalysisResult {
  stages: Stage[];
  turning_points: TurningPoint[];
  overall_summary: string;
}

interface Stage {
  stage_type: string;
  start_time: string;
  end_time: string;
  duration_hours: number;
  description: string;
  key_indicators: Record<string, any>;
  confidence: number;
}

const FeatureAnalysis: React.FC = () => {
  const [tasks, setTasks] = useState<AnalysisTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<AnalysisTask | null>(null);
  const [selectedTimeRange, setSelectedTimeRange] = useState<{start: string, end: string} | null>(null);
  const [showSaveDialog, setShowSaveDialog] = useState(false);

  // 轮询任务状态
  useEffect(() => {
    const interval = setInterval(async () => {
      for (const task of tasks.filter(t => t.status === 'pending' || t.status === 'processing')) {
        const res = await fetch(`/api/v1/features/analysis/${task.task_id}`);
        const updated = await res.json();
        if (updated.status === 'completed') {
          setTasks(prev => prev.map(t => t.task_id === task.task_id ? updated : t));
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [tasks]);

  // 处理阶段点击
  const handleStageClick = (stage: Stage) => {
    setSelectedTimeRange({
      start: stage.start_time,
      end: stage.end_time
    });
    setShowSaveDialog(true);
  };

  // 处理时间轴拖拽选择
  const handleTimeRangeSelect = (start: string, end: string) => {
    setSelectedTimeRange({ start, end });
    setShowSaveDialog(true);
  };

  // 保存特征案例
  const handleSaveCase = async (data: SaveCaseData) => {
    await fetch('/api/v1/features/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: selectedTask.task_id,
        symbol: selectedTask.symbol,
        selected_start_time: selectedTimeRange.start,
        selected_end_time: selectedTimeRange.end,
        container_type: data.containerType,
        custom_tags: data.tags,
        notes: data.notes,
        manual_features: data.manualFeatures
      })
    });
    
    alert('特征案例已保存！');
    setShowSaveDialog(false);
  };

  return (
    <div className="feature-analysis-page">
      <h1>特征分析</h1>

      {/* 任务列表 */}
      <div className="tasks-section">
        <h2>分析任务</h2>
        <div className="tasks-grid">
          {tasks.map(task => (
            <div key={task.task_id} className={`task-card ${task.status}`}>
              <h3>{task.symbol}</h3>
              <div className="status">
                状态: {task.status === 'pending' && '等待中...'}
                     {task.status === 'processing' && '分析中...'}
                     {task.status === 'completed' && '已完成'}
                     {task.status === 'failed' && '失败'}
              </div>
              {task.status === 'completed' && (
                <button onClick={() => setSelectedTask(task)}>
                  查看分析结果
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 分析结果详情 */}
      {selectedTask?.result && (
        <div className="analysis-detail">
          <div className="header">
            <h2>{selectedTask.symbol} - 特征分析结果</h2>
            <p className="time-range">
              分析时间段: {new Date(selectedTask.start_time).toLocaleString()} 
              - {new Date(selectedTask.end_time).toLocaleString()}
            </p>
          </div>

          {/* 阶段时间轴（可点击） */}
          <StageTimeline
            stages={selectedTask.result.stages}
            onStageClick={handleStageClick}
            onTimeRangeSelect={handleTimeRangeSelect}
          />

          {/* K 线图 + 特征标注 */}
          <FeatureChart
            symbol={selectedTask.symbol}
            startTime={selectedTask.start_time}
            endTime={selectedTask.end_time}
            stages={selectedTask.result.stages}
            turningPoints={selectedTask.result.turning_points}
          />

          {/* 阶段详情卡片 */}
          <div className="stages-detail">
            <h3>识别的阶段</h3>
            <div className="stages-grid">
              {selectedTask.result.stages.map((stage, idx) => (
                <div key={idx} className="stage-card" onClick={() => handleStageClick(stage)}>
                  <div className="stage-header">
                    <h4>{stage.stage_type}</h4>
                    <span className="confidence">置信度: {(stage.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="description">{stage.description}</p>
                  <div className="time-info">
                    <span>{new Date(stage.start_time).toLocaleString()}</span>
                    <span> → </span>
                    <span>{new Date(stage.end_time).toLocaleString()}</span>
                    <span> ({stage.duration_hours}h)</span>
                  </div>
                  <div className="indicators">
                    {Object.entries(stage.key_indicators).map(([key, value]) => (
                      <div key={key} className="indicator">
                        <span className="label">{key}:</span>
                        <span className="value">{JSON.stringify(value)}</span>
                      </div>
                    ))}
                  </div>
                  <button className="save-btn">
                    保存到特征库
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* 关键转折点 */}
          <div className="turning-points">
            <h3>关键转折点</h3>
            <div className="points-timeline">
              {selectedTask.result.turning_points.map((point, idx) => (
                <div key={idx} className="point">
                  <div className="time">{new Date(point.time).toLocaleString()}</div>
                  <div className="event">{point.event}</div>
                  <div className="trigger">{point.trigger}</div>
                  <div className="price-change">
                    ${point.price_before.toFixed(2)} → ${point.price_after.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* AI 总结 */}
          <div className="summary">
            <h3>AI 分析总结</h3>
            <p>{selectedTask.result.overall_summary}</p>
            <p>建议分类: <strong>{selectedTask.result.suggested_container}</strong></p>
          </div>
        </div>
      )}

      {/* 保存案例对话框 */}
      {showSaveDialog && selectedTimeRange && (
        <SaveCaseDialog
          symbol={selectedTask.symbol}
          timeRange={selectedTimeRange}
          onSave={handleSaveCase}
          onCancel={() => setShowSaveDialog(false)}
        />
      )}
    </div>
  );
};

export default FeatureAnalysis;
```

### 时间轴组件（支持拖拽选择）

```typescript
// frontend/src/components/StageTimeline.tsx

import React, { useState, useRef } from 'react';
import './StageTimeline.css';

interface StageTimelineProps {
  stages: Stage[];
  onStageClick: (stage: Stage) => void;
  onTimeRangeSelect: (start: string, end: string) => void;
}

export const StageTimeline: React.FC<StageTimelineProps> = ({
  stages,
  onStageClick,
  onTimeRangeSelect
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragEnd, setDragEnd] = useState<number | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  // 计算整体时间范围
  const allTimes = stages.flatMap(s => [new Date(s.start_time).getTime(), new Date(s.end_time).getTime()]);
  const minTime = Math.min(...allTimes);
  const maxTime = Math.max(...allTimes);
  const totalDuration = maxTime - minTime;

  // 将时间转换为时间轴上的位置百分比
  const timeToPosition = (time: string) => {
    const timestamp = new Date(time).getTime();
    return ((timestamp - minTime) / totalDuration) * 100;
  };

  // 处理鼠标按下
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = (x / rect.width) * 100;
    setDragStart(percent);
    setIsDragging(true);
  };

  // 处理鼠标移动
  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setDragEnd(percent);
  };

  // 处理鼠标松开
  const handleMouseUp = () => {
    if (isDragging && dragStart !== null && dragEnd !== null) {
      const start = Math.min(dragStart, dragEnd);
      const end = Math.max(dragStart, dragEnd);
      
      // 转换回时间
      const startTime = new Date(minTime + (start / 100) * totalDuration).toISOString();
      const endTime = new Date(minTime + (end / 100) * totalDuration).toISOString();
      
      onTimeRangeSelect(startTime, endTime);
    }
    setIsDragging(false);
    setDragStart(null);
    setDragEnd(null);
  };

  return (
    <div className="stage-timeline-container">
      <h3>阶段时间轴（点击阶段或拖拽选择时间段）</h3>
      <div
        ref={timelineRef}
        className="timeline"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* 绘制阶段 */}
        {stages.map((stage, idx) => {
          const left = timeToPosition(stage.start_time);
          const width = timeToPosition(stage.end_time) - left;
          
          return (
            <div
              key={idx}
              className={`stage-block ${stage.stage_type}`}
              style={{ left: `${left}%`, width: `${width}%` }}
              onClick={() => onStageClick(stage)}
              title={stage.description}
            >
              <span className="stage-label">{stage.stage_type}</span>
              <span className="stage-duration">{stage.duration_hours}h</span>
            </div>
          );
        })}

        {/* 拖拽选择区域 */}
        {isDragging && dragStart !== null && dragEnd !== null && (
          <div
            className="drag-selection"
            style={{
              left: `${Math.min(dragStart, dragEnd)}%`,
              width: `${Math.abs(dragEnd - dragStart)}%`
            }}
          />
        )}
      </div>

      <div className="timeline-labels">
        <span>{new Date(minTime).toLocaleString()}</span>
        <span>{new Date(maxTime).toLocaleString()}</span>
      </div>
    </div>
  );
};
```

### 保存案例对话框

```typescript
// frontend/src/components/SaveCaseDialog.tsx

import React, { useState } from 'react';

interface SaveCaseDialogProps {
  symbol: string;
  timeRange: { start: string; end: string };
  onSave: (data: SaveCaseData) => void;
  onCancel: () => void;
}

export interface SaveCaseData {
  containerType: string;
  tags: string[];
  notes: string;
  manualFeatures?: Record<string, any>;
}

export const SaveCaseDialog: React.FC<SaveCaseDialogProps> = ({
  symbol,
  timeRange,
  onSave,
  onCancel
}) => {
  const [containerType, setContainerType] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [tagInput, setTagInput] = useState('');

  const containerOptions = [
    { id: 'accumulation', name: '吸筹（卖盘枯竭）' },
    { id: 'short_squeeze', name: '挤空（多空比失衡）' },
    { id: 'long_liquidation', name: '杀多（多单爆仓）' },
    { id: 'distribution', name: '派发（高位出货）' },
    { id: 'wash_out', name: '洗盘（假跌真涨）' }
  ];

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()]);
      setTagInput('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag));
  };

  const handleSubmit = () => {
    if (!containerType) {
      alert('请选择特征容器');
      return;
    }
    onSave({ containerType, tags, notes });
  };

  return (
    <div className="dialog-overlay">
      <div className="save-case-dialog">
        <h2>保存特征案例</h2>

        <div className="dialog-content">
          {/* 合约和时间信息 */}
          <div className="info-section">
            <p><strong>合约:</strong> {symbol}</p>
            <p>
              <strong>时间段:</strong><br />
              {new Date(timeRange.start).toLocaleString()}<br />
              → {new Date(timeRange.end).toLocaleString()}
            </p>
            <p>
              <strong>持续时间:</strong> {
                ((new Date(timeRange.end).getTime() - new Date(timeRange.start).getTime()) / 3600000).toFixed(1)
              } 小时
            </p>
          </div>

          {/* 选择特征容器 */}
          <div className="form-group">
            <label>特征容器 *</label>
            <select value={containerType} onChange={e => setContainerType(e.target.value)}>
              <option value="">-- 选择容器 --</option>
              {containerOptions.map(opt => (
                <option key={opt.id} value={opt.id}>{opt.name}</option>
              ))}
            </select>
          </div>

          {/* 自定义标签 */}
          <div className="form-group">
            <label>自定义标签</label>
            <div className="tag-input">
              <input
                type="text"
                value={tagInput}
                onChange={e => setTagInput(e.target.value)}
                onKeyPress={e => e.key === 'Enter' && handleAddTag()}
                placeholder="输入标签后按回车"
              />
              <button onClick={handleAddTag}>添加</button>
            </div>
            <div className="tags-list">
              {tags.map(tag => (
                <span key={tag} className="tag">
                  {tag}
                  <button onClick={() => handleRemoveTag(tag)}>×</button>
                </span>
              ))}
            </div>
          </div>

          {/* 备注 */}
          <div className="form-group">
            <label>备注说明</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="描述这个案例的特殊之处..."
              rows={4}
            />
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="dialog-actions">
          <button className="btn-cancel" onClick={onCancel}>
            取消
          </button>
          <button className="btn-save" onClick={handleSubmit}>
            保存到特征库
          </button>
        </div>
      </div>
    </div>
  );
};
```

---

## 数据保留策略（60天）

### 数据库配置

```sql
-- 设置 TimescaleDB 数据保留策略

-- 1分钟 K 线保留 60 天
SELECT add_retention_policy('candles', INTERVAL '60 days');

-- 资金费率保留 60 天
SELECT add_retention_policy('funding_rates', INTERVAL '60 days');

-- 持仓量保留 60 天
SELECT add_retention_policy('open_interest', INTERVAL '60 days');

-- 清算数据保留 60 天
SELECT add_retention_policy('liquidations', INTERVAL '60 days');

-- 交易数据保留 60 天
SELECT add_retention_policy('trades', INTERVAL '60 days');

-- 质量日志保留 7 天（不需要长期保存）
SELECT add_retention_policy('quality_logs', INTERVAL '7 days');

-- 特征案例库永久保存（无保留策略）
-- feature_cases 表不设置保留策略
```

### 环境变量配置

```bash
# .env

# 数据保留天数
DATA_RETENTION_DAYS=60

# 自动清理间隔（秒）
RETENTION_CLEANUP_INTERVAL=86400  # 每天运行一次

# 特征分析最大回溯天数
FEATURE_ANALYSIS_MAX_LOOKBACK_DAYS=60
```

---

## 工作流程示例

### 用户操作示例

```
1. 用户在涨跌幅榜看到 BTC 24h 上涨 12%
   ↓
2. 点击"添加分析"，系统创建分析任务
   - 默认分析最近 24 小时
   ↓
3. 30 秒后，分析完成
   - AI 识别出 3 个阶段：吸筹（6h）→ 拉升（12h）→ 派发（6h）
   ↓
4. 用户查看分析结果
   - 时间轴展示 3 个阶段
   - K 线图高亮显示各阶段
   - 阶段详情显示关键指标
   ↓
5. 用户对"拉升阶段"感兴趣
   - 点击时间轴上的"拉升阶段"
   - 或者手动拖拽选择 06:00-18:00
   ↓
6. 弹出保存对话框
   - 选择特征容器："挤空（多空比失衡）"
   - 添加标签："空单爆仓"、"资金费率飙升"
   - 备注："典型的 short squeeze，1200 BTC 空单爆仓"
   ↓
7. 点击"保存到特征库"
   - 只保存 06:00-18:00 这 12 小时的数据
   - 关联到"挤空"容器
   - 生成特征向量
   ↓
8. 系统提示："特征案例已保存！特征库中已有 5 个相似案例"
```

---

## 总结

关键改进点：

1. ✅ **手动时间段选择**：用户可以只保存感兴趣的阶段，不需要保存整个分析结果
2. ✅ **60天数据保留**：TimescaleDB 自动清理 60 天前的数据
3. ✅ **灵活的选择方式**：既可以点击 AI 识别的阶段，也可以手动拖拽选择
4. ✅ **精准的特征库**：只保存有价值的时间段，提高特征库质量
5. ✅ **自定义标注**：用户可以添加标签和备注，补充 AI 分析

这样的设计让用户能够更精准地构建特征库，避免保存无关的数据。