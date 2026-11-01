# M2 后端 API 与运行指南

M2 在 M1 FastAPI 应用内提供特征计算、异步市场分析、案例库、容器管理和机会扫描。
接口前缀为 `/api`，M1 的 `/api/v1` 保持可用。交互文档：`/docs`；完整机器可读契约：`/openapi.json`。
时间均须带时区，开始时间包含、结束时间不包含；推荐使用 UTC `Z`。

## 安装与迁移

```bash
pip install -r requirements-dev.txt
# 新建数据库：Compose 初始化时按顺序执行 init_db.sql 和 migrate_m2.sql。
docker compose build timescaledb api backend
docker compose up -d
```

数据库镜像在 TimescaleDB 2.17.2 / PostgreSQL 15 上编译固定版本 pgvector 0.8.0。
Python pgvector 包不包含服务器扩展，必须使用此镜像或在数据库服务器安装相同扩展。
**已有 M1 数据卷不会自动执行初始化脚本**。升级时先备份数据库、构建镜像，
重建数据库容器以载入扩展文件，再执行迁移（不要删除数据卷）：

```bash
docker compose build timescaledb api backend
docker compose up -d timescaledb
# 使用容器内的 PostgreSQL 用户与数据库配置，不打印数据库密码。
docker compose exec -T timescaledb sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scripts/migrate_m2.sql
docker compose up -d api backend
```

迁移按事务执行，可重复运行；应用不自动迁移。`market_features_1m` 保留 60 天，
`market_features_5m`、`market_features_1h`、`market_features_1d` 为永久保留的连续聚合。
它们各自从 1m 表计算，刷新范围仅覆盖最近 59 天，避免刷新已删除的原始范围而丢失聚合。
首次部署后如需已有历史特征聚合，可使用 TimescaleDB 的 `refresh_continuous_aggregate`。

## 配置与生命周期

参见 `.env.example`。没有 `OPENAI_API_KEY` 时，特征计算与查询仍可运行；
创建分析和案例、向量搜索返回 503，机会扫描跳过，不生成模拟结果。
AI 模型和 Embeddings 模型分别由 `OPENAI_ANALYSIS_MODEL`、`OPENAI_EMBEDDING_MODEL` 配置。
Embeddings 固定为 1536 维；更换模型后旧模型向量不会参与新模型搜索，需重新保存案例。

APScheduler 3.x 在 FastAPI lifespan 启动，UTC 每分钟第 10 秒计算两分钟前的已结束分钟，
为采集器刷盘和迟到数据预留时间。每五分钟第 10 秒扫描活跃合约；
合约目录和面值来自 M1 的 CCXT / OKX discovery，按 `INSTRUMENT_REFRESH_SECONDS` 缓存。
每类调度任务最多一个实例，合并错过的触发；数据库事务咨询锁避免多个 API 进程同时扫描。
建议一个 API worker；池应至少三个连接（两个调度锁连接，另一个处理工作）。
`M2_SCHEDULER_ENABLED=false` 可关闭这两类调度任务，分析任务恢复仍会运行。

分析请求先写数据库，再用 asyncio 处理。状态为 `pending → running → completed / failed`。
队列有界，执行并发有界，超时、模型拒绝、解析失败、越界时间线都记为 failed。
运行任务持有数据库租约；每 30 秒恢复 pending 或租约过期的任务，原子认领避免重复执行。
进程正常关闭时停止调度、取消并收集运行任务，任务错误不包含上游密钥或连接串。
强制退出的任务在租约到期后恢复；外部 API 调用本身不能保证仅收费一次。
案例和分析记录持久保存，未提供自动清理；应根据业务存储预算进行管理。

## 特征定义

所有金额为美元近似值（USDT 按 1 USD），线性合约成交和盘口金额为 `price × quantity × contractSize`。
OI 原始单位为合约张数；`oi_usd = oi × contractSize × close`。
所有零分母比例返回 null，不返回 Infinity。数据缺失不冒充零。

| 类别 | 字段与算法 |
| --- | --- |
| 价格 | OHLC、volume；price_change_pct = (close/open−1)×100；amplitude_pct = (high−low)/open×100；volatility 为连续最多 60 根收盘价的对数收益率总体标准差×100，至少三个连续观测，否则 null |
| 资金流 | buy_volume_usd、sell_volume_usd、delta_usd；cvd 为 UTC 当日开始到该分钟结束的有符号美元成交累计；trade_count 使用原始合并成交计数；buy_sell_ratio=buy/sell |
| OI | 使用分钟结束前最近 5 分钟内观测；oi_delta / oi_change_pct 相对分钟开始之前最近 5 分钟观测；oi_volume_ratio=OI 张数/分钟成交张数；oi_direction 根据价格方向及 OI 增减分类 |
| 资金费率 | 最近 9 小时内最新 funding_rate；funding_trend 为其与窗口内上一条观测的差，单位为费率小数，不是百分比 |
| 盘口 | 最近 2 分钟内快照；前 10 档美元深度；obi=(bid−ask)/(bid+ask)，范围 [-1,1]；spread_bps=(ask1−bid1)/mid×10000 |
| 清算 | 执行 sell 对应多头清算，buy 对应空头清算；liq_imbalance=(short−long)/(short+long)；liquidation_intensity=清算金额/成交金额；liquidation_long_short_ratio=long/short |
| 质量 | coverage=可用源位数/7；source_flags 的 bit0..6 为 candle、trade、OI、funding、book、liquidation、spot。M1 无 spot 源，该位不置位；空清算窗口不能证明源健康，也不置位 |

`age_seconds` 为分钟结束时最旧的可用源观测年龄。
新鲜度分数在 `<60 / <300 / <600 / ≥600` 秒时分别为 `1 / .8 / .5 / .2`。
质量为 `.5×coverage + .3×freshness + .2×anomaly_score`；分钟内若有 M1 error 级 quality_logs，anomaly_score=0，否则为 1。
因此完整且新鲜的六个 M1 源可以超过 .9，但不能承诺每个分钟都达到 .9；缺失源如实降低评分。
`is_final=false` 表示本版本没有不可再修订保证，重复计算会更新同一主键并增加 revision_count。
CVD 仅覆盖数据库仍保留的当日成交；采集缺口会影响数值，不能视为交易所完整历史。
现货价、basis 和 8h 费率归一化依赖 M1 尚无的数据，不生成推测值。

## GET /api/features/{symbol}

symbol 示例：`BTC-USDT-SWAP`。返回 `MarketFeature1Min[]`，按分钟倒序，无数据返回 `[]`。

| 参数 | 默认 / 限制 |
| --- | --- |
| start_time, end_time | 可选，带时区；同时提供时 start < end |
| limit | 1000，1..10000 |
| min_quality | 0，0..1 |
| only_final | false；当前无 final 保证，true 时通常返回空数组 |

```bash
curl 'http://localhost:8000/api/features/BTC-USDT-SWAP?limit=60&min_quality=0.7'
```

## POST /api/analysis/create

返回 202 和 `AnalysisTask`（包含 UUID `id`、symbol、时间范围、状态、result、error、创建/更新时间）。
窗口必须为整分钟、1 分钟至 24 小时，结束时间不得在未来。
最多读取 1440 根特征，并向模型发送最多 120 个均匀间隔样本；完整数值摘要保存在内部供案例向量化使用。

```json
{"symbol":"BTC-USDT-SWAP","start_time":"2026-10-30T00:00:00Z","end_time":"2026-10-30T01:00:00Z"}
```

## GET /api/analysis/{task_id}

返回上述任务，不存在返回 404。完成时 `result` 包含：

```json
{
  "summary":"OI 与资金流共同支持积累阶段假设",
  "stages":[{"stage":"accumulation","start_time":"2026-10-30T00:00:00Z","end_time":"2026-10-30T01:00:00Z","confidence":0.7,"evidence":"持仓增加，价格区间收窄"}],
  "turning_points":[{"time":"2026-10-30T00:45:00Z","kind":"breakout","reason":"资金流与价格同步增强"}]
}
```

stage：`accumulation / markup / distribution / markdown / unknown`。
turning point kind：`breakout / reversal / acceleration / exhaustion`。
阶段须在请求窗口内、按时间排序且不重叠；转折点须在半开窗口内；置信度为 0..1。
失败时 result 为 null，error 为不含上游细节的提示；队列满返回 429。

## POST /api/cases

返回 201。只能保存已完成分析，特征快照和分析由服务器读取，不接受客户端伪造。
先调用 Embeddings，再在一个事务中写案例与向量；失败不会留下半个案例。

```json
{"task_id":"00000000-0000-0000-0000-000000000001","title":"放量积累案例","container_id":null,"outcome":null}
```

title 长度 1..200；container_id 可选；outcome 为 `success / failure / null`，是人工历史结果标注。
返回 id、task_id、container_id、symbol、title、outcome、created_at。
不存在的任务或容器返回 422。

## GET /api/cases/search

必填：symbol、start_time、end_time；窗口限制同分析。
可选：`limit=10`（1..100）、`min_similarity=.7`（0..1）、container_id。
使用窗口各数值特征的均值形成 `market-window-v1` 规范 JSON，经 OpenAI Embeddings 转为 1536 维向量。
历史和实时窗口共用同一表示；缺失指标明确为 null。
查询按 pgvector cosine distance 排序，并按模型、表示版本、容器和最小相似度筛选。
该版本是基础统计摘要，会丢失分钟顺序；相似度不代表模式识别准确率。

返回 `CaseMatch[]`，每项包含 id、symbol、title、container_id、analysis、outcome、similarity。
相似度是 `1 − cosine_distance`，无匹配为 `[]`；查询窗口没有特征返回 404。

## 容器管理

- `POST /api/containers`：`{"name":"积累","description":"OI 增加且价格横盘"}`，返回 201 和容器。
- `GET /api/containers?limit=100`：最新容器列表，limit 1..1000。
- `PUT /api/containers/{id}`：同创建请求，替换名称和描述。
- `DELETE /api/containers/{id}`：返回 204；已有案例 container_id 置 null，不删除案例。

容器包含 id、name、description、created_at。名称唯一，冲突返回 409，未知 id 返回 404。
容器用于人工分类与搜索过滤，本版本不实现规则 DSL 或自动归类。

## GET /api/opportunities

参数：`limit=100`（1..1000）、`min_confidence=0`（0..1）。
按 confidence 降序返回未过期机会。
扫描使用最近 1 小时内至少 45 根特征，最后一根不超过 3 分钟，平均质量至少 `OPPORTUNITY_MIN_QUALITY`。
匹配最多 10 个案例，最低相似度默认为 .8。
无新鲜数据或无匹配时移除该 symbol 的旧机会；结果 TTL 为 10 分钟。

返回 symbol、observed_at、expires_at、stage、similarity、confidence、historical_success_rate、labeled_cases、matches。
stage 取最相似历史案例最后一个阶段；confidence 为相似度乘该阶段的 AI 置信度。
`historical_success_rate` 只统计显式 success/failure 标注，没有标注则为 null，并同时返回样本数。
这是基础模式匹配假设和经验比例，未经校准，不是未来收益概率。
matches 包含 case id、symbol、title、similarity、outcome。

## 错误与验证

沿用 M1 错误包装：`{"error":{"code":422,"message":"Invalid request",...}}`。
不合法 symbol、无时区时间、窗口范围、UUID 和数值参数返回 422。
依赖连接错误 / OpenAI API 错误返回 503；队列满 429；未找到记录 404。
分析开始后发生的模型错误通过任务 failed 状态体现，不改变已返回的 202。
接口沿用 M1 部署边界；本版本未添加用户身份、权限或多租户隔离。

## 测试

```bash
python -m pytest -q
ruff check backend tests
# 仅对独立、可写入的测试数据库执行；不得指向生产库。
TEST_M2_DATABASE_URL=postgresql://... python -m pytest tests/test_m2_integration.py -q
```

单元测试不访问外部 AI；模型和 Embeddings 用确定性替身。
集成测试执行真实迁移和 pgvector 操作，验证 SQL 兼容性、金额换算、任务与案例持久化、相似度排序和级联关系。
