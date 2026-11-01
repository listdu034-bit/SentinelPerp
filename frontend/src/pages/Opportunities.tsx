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
  useOpportunityCandles,
  type Case,
  type Opportunity,
} from "../m2";
import CandleChart from "../components/CandleChart";
import QueryNotice from "../components/QueryNotice";
import M2Notice from "../components/M2Notice";
import { timestamp } from "../format";
function OpportunityDetail({ id }: { id: string }) {
  const detail = useQuery({
    queryKey: ["opportunities", id],
    queryFn: ({ signal }) =>
      request<Opportunity>(
        "get",
        `/opportunities/${encodeURIComponent(id)}`,
        undefined,
        signal,
      ),
  });
  const opportunity = detail.data;
  const similar = useQuery({
    queryKey: ["cases", "search", id],
    enabled: !!opportunity,
    queryFn: ({ signal }) =>
      request<Case[]>("get", "/cases/search", { opportunity_id: id }, signal),
  });
  const candles = useCandles(demoMode ? "" : opportunity?.symbol || "", "1m");
  const mockCandles = useOpportunityCandles(opportunity?.symbol);
  const rows = demoMode ? mockCandles.data || [] : candles.data?.items || [];
  return (
    <>
      <QueryNotice query={detail} />
      {opportunity && (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Paragraph>{opportunity.summary}</Typography.Paragraph>
          <Tag color="blue">当前阶段：{opportunity.stage}</Tag>
          <Table
            pagination={false}
            rowKey="name"
            scroll={{ x: 400 }}
            dataSource={Object.entries(opportunity.features).map(
              ([name, value]) => ({
                name,
                current: value,
                historical: opportunity.historical_features[name],
              }),
            )}
            columns={[
              { title: "特征", dataIndex: "name" },
              { title: "当前值", dataIndex: "current" },
              {
                title: "历史案例参考值",
                dataIndex: "historical",
                render: (value) => value ?? "—",
              },
            ]}
          />
          <Card title="K 线与阶段识别">
            <QueryNotice query={demoMode ? mockCandles : candles} />
            {rows.length ? (
              <CandleChart rows={rows} phases={opportunity.phases} />
            ) : (
              <Empty description="当前暂无 K 线数据" />
            )}
            <Timeline
              items={opportunity.phases.map((phase) => ({
                children: `${phase.stage} · ${timestamp(phase.start_time)} — ${timestamp(phase.end_time)} · ${phase.description}`,
              }))}
            />
          </Card>
          <Card title="相似历史案例">
            <QueryNotice query={similar} />
            <Table<Case>
              rowKey="id"
              loading={similar.isPending}
              dataSource={similar.data || []}
              pagination={{ pageSize: 5 }}
              scroll={{ x: 500 }}
              columns={[
                { title: "合约", dataIndex: "symbol" },
                { title: "案例", dataIndex: "summary" },
                {
                  title: "相似度",
                  dataIndex: "similarity",
                  render: (value) => `${(value * 100).toFixed(0)}%`,
                },
                {
                  title: "成功率",
                  dataIndex: "success_rate",
                  render: (value) => `${(value * 100).toFixed(0)}%`,
                },
              ]}
            />
          </Card>
        </Space>
      )}
    </>
  );
}
export default function Opportunities() {
  const [confidence, setConfidence] = useState(0);
  const [success, setSuccess] = useState(0);
  const [hours, setHours] = useState(24);
  const [selected, setSelected] = useState<Opportunity>();
  const query = useQuery({
    queryKey: ["opportunities", { confidence, success, hours }],
    queryFn: ({ signal }) =>
      request<Opportunity[]>(
        "get",
        "/opportunities",
        { min_confidence: confidence, min_success_rate: success, hours },
        signal,
      ),
  });
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
      <QueryNotice query={query} />
      {query.isPending ? (
        <Card loading />
      ) : query.data?.length ? (
        <Row gutter={[16, 16]}>
          {query.data.map((opportunity) => (
            <Col key={opportunity.id} xs={24} md={12} xl={8}>
              <Card
                title={opportunity.symbol}
                extra={<Tag color="blue">{opportunity.stage}</Tag>}
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
                      value={opportunity.success_rate * 100}
                      precision={0}
                      suffix="%"
                    />
                  </Col>
                </Row>
                <Typography.Paragraph style={{ marginTop: 16 }}>
                  {opportunity.summary}
                </Typography.Paragraph>
                <Typography.Paragraph type="secondary">
                  发现于 {timestamp(opportunity.detected_at)}
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
        {selected && <OpportunityDetail key={selected.id} id={selected.id} />}
      </Modal>
    </>
  );
}
