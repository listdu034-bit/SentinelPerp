import { useState } from "react";
import { Column } from "@ant-design/charts";
import { Card, Col, Empty, Row, Select, Table, Tag, Typography } from "antd";
import { useQualityLogs, useQualitySummary } from "../api";
import QueryNotice from "../components/QueryNotice";
import { timestamp } from "../format";
import type { QualityLogResponse } from "../types";
export default function Quality() {
  const [pagination, setPagination] = useState({ page: 1, size: 20 });
  const [severity, setSeverity] = useState<string>();
  const logs = useQualityLogs(pagination.page, pagination.size, severity);
  const summary = useQualitySummary();
  return (
    <>
      <Typography.Title level={2}>数据质量</Typography.Title>
      <QueryNotice query={summary} />
      <Row gutter={[16, 16]}>
        {(["by_symbol", "by_issue_type"] as const).map((key) => {
          const data = Object.entries(summary.data?.[key] || {}).map(
            ([name, count]) => ({ name, count }),
          );
          return (
            <Col xs={24} xl={12} key={key}>
              <Card
                title={
                  key === "by_symbol"
                    ? "按合约统计 · 全部历史"
                    : "按问题类型统计 · 全部历史"
                }
                loading={summary.isPending}
              >
                {data.length ? (
                  <Column
                    data={data}
                    xField="name"
                    yField="count"
                    height={280}
                    axis={{ x: { title: false }, y: { title: "事件数量" } }}
                  />
                ) : (
                  <Empty description="暂无质量事件" />
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
      <Card
        title="质量事件日志"
        style={{ marginTop: 24 }}
        extra={
          <Select
            aria-label="严重程度"
            value={severity}
            placeholder="全部级别"
            allowClear
            style={{ width: 140 }}
            options={[
              { value: "warning", label: "警告" },
              { value: "error", label: "错误" },
            ]}
            onChange={(value) => {
              setSeverity(value);
              setPagination((p) => ({ ...p, page: 1 }));
            }}
          />
        }
      >
        <QueryNotice query={logs} />
        <Table<QualityLogResponse>
          rowKey="event_id"
          loading={logs.isPending}
          dataSource={logs.data?.items || []}
          scroll={{ x: 780 }}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: logs.data?.total || 0,
            showSizeChanger: true,
            onChange: (page, size) => setPagination({ page, size }),
          }}
          expandable={{
            expandedRowRender: (record) => (
              <pre style={{ whiteSpace: "pre-wrap" }}>
                {JSON.stringify(record.details, null, 2)}
              </pre>
            ),
          }}
          columns={[
            { title: "时间", dataIndex: "time", render: timestamp },
            { title: "合约", dataIndex: "symbol" },
            { title: "数据类型", dataIndex: "data_type" },
            { title: "问题类型", dataIndex: "issue_type" },
            {
              title: "级别",
              dataIndex: "severity",
              render: (value) => (
                <Tag color={value === "error" ? "red" : "gold"}>{value}</Tag>
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}
