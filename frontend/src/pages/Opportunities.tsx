import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Col,
  Empty,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Timeline,
  Typography,
} from "antd";
import { useCandles } from "../api";
import {
  demoMode,
  request,
  stageName,
  phases,
  opportunityWindow,
  useOpportunityCandles,
  type Case,
  type Opportunity,
  type Feature,
} from "../m2";
import CandleChart from "../components/CandleChart";
import QueryNotice from "../components/QueryNotice";
import M2Notice from "../components/M2Notice";
import { timestamp } from "../format";
function OpportunityDetail({ selected }: { selected: Opportunity }) {
  const detail = useQuery({
    queryKey: ["opportunities", "detail", selected.symbol],
    initialData: selected,
    staleTime: 0,
    queryFn: ({ signal }) =>
      request<Opportunity>(
        "get",
        `/opportunities/${encodeURIComponent(selected.symbol)}`,
        undefined,
        signal,
      ),
  });
  const opportunity = detail.data;
  const bounds = opportunityWindow(opportunity);
  const similar = useQuery({
    queryKey: ["cases", "search", bounds],
    queryFn: ({ signal }) =>
      request<Case[]>(
        "get",
        "/cases/search",
        { ...bounds, limit: 10, min_similarity: 0.7 },
        signal,
      ),
  });
  const features = useQuery({
    queryKey: ["features", bounds],
    queryFn: ({ signal }) =>
      request<Feature[]>(
        "get",
        `/features/${encodeURIComponent(opportunity.symbol)}`,
        { start_time: bounds.start_time, end_time: bounds.end_time, limit: 60 },
        signal,
      ),
  });
  const candles = useCandles(demoMode ? "" : opportunity.symbol, "1m");
  const mockCandles = useOpportunityCandles(opportunity.symbol);
  const rows = demoMode ? mockCandles.data || [] : candles.data?.items || [];
  const current = features.data?.[0];
  return (
    <>
      <QueryNotice query={detail} />
      <Space direction="vertical" style={{ width: "100%" }}>
        <Tag color="blue">
          当前识别：{stageName(opportunity.stage)} ·{" "}
          {timestamp(opportunity.observed_at)}
        </Tag>
        <Card title="当前特征">
          <QueryNotice query={features} />
          {current ? (
            <Table
              pagination={false}
              rowKey="name"
              dataSource={Object.entries(current)
                .filter(([, value]) => typeof value === "number")
                .map(([name, value]) => ({ name, value }))}
              columns={[
                { title: "特征", dataIndex: "name" },
                { title: "当前值", dataIndex: "value" },
              ]}
              scroll={{ x: 400 }}
            />
          ) : (
            <Empty description="该机会窗口没有特征数据" />
          )}
        </Card>
        <Card title="K 线与阶段识别">
          <QueryNotice query={demoMode ? mockCandles : candles} />
          {rows.length ? (
            <CandleChart
              rows={rows}
              currentStage={{
                time: opportunity.observed_at,
                label: stageName(opportunity.stage),
              }}
            />
          ) : (
            <Empty description="当前暂无 K 线数据" />
          )}
        </Card>
        <Card title="相似历史案例">
          <QueryNotice query={similar} />
          <Typography.Paragraph type="secondary">
            对比最近一小时的当前特征与历史阶段证据。API
            未提供历史数值快照；相似度及历史标注不代表未来收益概率。
          </Typography.Paragraph>
          <Table<Case>
            rowKey="id"
            loading={similar.isPending}
            dataSource={similar.data || []}
            pagination={{ pageSize: 5 }}
            scroll={{ x: 600 }}
            columns={[
              { title: "合约", dataIndex: "symbol" },
              { title: "案例", dataIndex: "title" },
              {
                title: "相似度",
                dataIndex: "similarity",
                render: (value) => `${(value * 100).toFixed(0)}%`,
              },
              {
                title: "历史结果",
                dataIndex: "outcome",
                render: (value) =>
                  value === "success"
                    ? "成功"
                    : value === "failure"
                      ? "失败"
                      : "未标注",
              },
            ]}
            expandable={{
              expandedRowRender: (item) => (
                <>
                  <Typography.Paragraph>
                    {item.analysis.summary}
                  </Typography.Paragraph>
                  <Timeline
                    items={phases(item.analysis).map((phase) => ({
                      children: `${phase.stage} · ${timestamp(phase.start_time)} — ${timestamp(phase.end_time)} · ${phase.description}`,
                    }))}
                  />
                </>
              ),
            }}
          />
        </Card>
      </Space>
    </>
  );
}
export default function Opportunities() {
  const [confidence, setConfidence] = useState(0);
  const [success, setSuccess] = useState(0);
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<Opportunity>();
  const query = useQuery({
    queryKey: ["opportunities", "list", confidence],
    queryFn: ({ signal }) =>
      request<Opportunity[]>(
        "get",
        "/opportunities",
        { min_confidence: confidence, limit: 1000 },
        signal,
      ),
  });
  const visible = (query.data || []).filter(
    (item) =>
      (success === 0 ||
        (item.historical_success_rate != null &&
          item.historical_success_rate >= success)) &&
      Date.parse(item.observed_at) >= Date.now() - hours * 3600000 &&
      Date.parse(item.expires_at) > Date.now(),
  );
  return (
    <>
      <Typography.Title level={2}>机会发现</Typography.Title>
      <M2Notice />
      <Space wrap style={{ marginBottom: 20 }}>
        <Space>
          最低置信度
          <Select
            aria-label="最低置信度"
            value={confidence}
            onChange={setConfidence}
            options={[0, 0.6, 0.7, 0.8, 0.9].map((value) => ({
              value,
              label: `${value * 100}%`,
            }))}
          />
        </Space>
        <Space>
          最低成功率
          <Select
            aria-label="最低成功率"
            value={success}
            onChange={setSuccess}
            options={[0, 0.5, 0.6, 0.7, 0.8].map((value) => ({
              value,
              label: `${value * 100}%`,
            }))}
          />
        </Space>
        <Space>
          时间范围
          <Select
            aria-label="时间范围"
            value={hours}
            onChange={setHours}
            options={[1, 4, 24, 168].map((value) => ({
              value,
              label: `最近 ${value} 小时`,
            }))}
          />
        </Space>
      </Space>
      <Typography.Paragraph type="secondary">
        成功率与时间范围在本次返回的最多 1000
        条候选中筛选；仅展示未过期机会。未标注案例不参与成功率估计。
      </Typography.Paragraph>
      <QueryNotice query={query} />
      {query.isPending ? (
        <Card loading />
      ) : visible.length ? (
        <Row gutter={[16, 16]}>
          {visible.map((opportunity) => (
            <Col key={opportunity.symbol} xs={24} md={12} xl={8}>
              <Card
                title={opportunity.symbol}
                extra={<Tag color="blue">{stageName(opportunity.stage)}</Tag>}
              >
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic
                      title="置信度"
                      value={opportunity.confidence * 100}
                      precision={0}
                      suffix="%"
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="历史成功率"
                      value={
                        opportunity.historical_success_rate == null
                          ? "未标注"
                          : opportunity.historical_success_rate * 100
                      }
                      precision={0}
                      suffix={
                        opportunity.historical_success_rate == null
                          ? undefined
                          : "%"
                      }
                    />
                  </Col>
                </Row>
                <Typography.Paragraph style={{ marginTop: 16 }}>
                  已标注案例：{opportunity.labeled_cases} · 历史匹配：
                  {opportunity.matches.length}
                </Typography.Paragraph>
                <Typography.Paragraph type="secondary">
                  发现于 {timestamp(opportunity.observed_at)}
                </Typography.Paragraph>
                <Button onClick={() => setSelected(opportunity)}>
                  查看机会详情
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      ) : (
        !query.isError && <Empty description="当前筛选条件下没有机会" />
      )}
      <Modal
        title={selected ? `${selected.symbol} · 机会详情` : "机会详情"}
        open={!!selected}
        onCancel={() => setSelected(undefined)}
        footer={null}
        width={1000}
        destroyOnHidden
      >
        {selected && (
          <OpportunityDetail key={selected.symbol} selected={selected} />
        )}
      </Modal>
    </>
  );
}
