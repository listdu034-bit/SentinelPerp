import { Card, Col, Row, Statistic, Table, Typography } from "antd";
import { useStatus } from "../api";
import QueryNotice from "../components/QueryNotice";
import { number, timestamp } from "../format";
export default function Status() {
  const query = useStatus();
  const data = query.data;
  const rows = Object.entries(data?.collection || {}).map(([name, value]) => ({
    name,
    ...value,
    bytes: data?.database.table_bytes?.[name],
  }));
  return (
    <>
      <Typography.Title level={2}>系统状态</Typography.Title>
      <QueryNotice query={query} />
      <Row gutter={[16, 16]}>
        {[
          ["质量评分", data?.quality_score, "%"],
          ["数据库连接", data?.database.connections, ""],
          [
            "Redis 内存",
            data?.redis.used_memory == null
              ? undefined
              : data.redis.used_memory / 1048576,
            "MB",
          ],
          ["Redis 键数", data?.redis.keys, ""],
        ].map(([title, value, suffix]) => (
          <Col xs={24} sm={12} xl={6} key={title}>
            <Card loading={query.isPending}>
              <Statistic
                title={title}
                value={value ?? "—"}
                suffix={suffix}
                precision={
                  title === "质量评分" || title === "Redis 内存" ? 2 : 0
                }
              />
            </Card>
          </Col>
        ))}
      </Row>
      <Card title="采集与存储" style={{ marginTop: 24 }}>
        <Table
          rowKey="name"
          loading={query.isPending}
          dataSource={rows}
          scroll={{ x: 650 }}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "数据流", dataIndex: "name" },
            {
              title: "保留记录",
              dataIndex: "count",
              render: number,
              sorter: (a, b) => a.count - b.count,
            },
            {
              title: "最近采集时间",
              dataIndex: "latest_time",
              render: timestamp,
            },
            {
              title: "存储 MB",
              dataIndex: "bytes",
              render: (value) =>
                value == null ? "—" : number(value / 1048576),
            },
          ]}
        />
        <Typography.Text type="secondary">
          质量评分窗口：{data?.quality_window || "24h"}
          。评分基于事件数与交易数，不代表交易所数据完整率。服务端快照：
          {timestamp(data?.time)}
        </Typography.Text>
      </Card>
    </>
  );
}
