import { Alert, Card, Table, Tabs, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { useMarket } from "../market";
import { timestamp } from "../format";
import type { MarketRow } from "../types";
export default function Rankings() {
  const query = useMarket();
  return (
    <>
      <Typography.Title level={2}>涨跌幅榜单</Typography.Title>
      <Alert
        style={{ marginBottom: 16 }}
        showIcon
        type={query.connected && !query.reconnecting ? "success" : "warning"}
        message={
          query.reconnecting
            ? "服务端正在恢复数据源，当前展示缓存快照"
            : query.connected
              ? "实时连接已建立 · 服务端每 30 秒推送榜单"
              : "实时连接中断或正在连接，将自动重连；已有数据保留在缓存中"
        }
      />
      <Card title="OKX · USDT 永续合约" extra={<Tag>24 小时观察窗口</Tag>}>
        <Typography.Paragraph type="secondary">
          依据已采集 1 分钟 K 线的首个开盘价与最后收盘价计算。最近快照：
          {timestamp(query.data?.time)}
        </Typography.Paragraph>
        <Tabs
          items={(["gainers", "losers"] as const).map((key) => ({
            key,
            label: key === "gainers" ? "涨幅榜" : "跌幅榜",
            children: (
              <Table<MarketRow>
                rowKey="symbol"
                dataSource={query.data?.[key] || []}
                pagination={{ pageSize: 10 }}
                locale={{ emptyText: "等待市场快照，或当前没有 K 线数据" }}
                columns={[
                  {
                    title: "合约",
                    dataIndex: "symbol",
                    render: (symbol) => (
                      <Link to={`/markets/${encodeURIComponent(symbol)}`}>
                        {symbol}
                      </Link>
                    ),
                  },
                  {
                    title: "24h 涨跌幅",
                    dataIndex: "change_percent",
                    sorter: (a, b) =>
                      (a.change_percent ?? -Infinity) -
                      (b.change_percent ?? -Infinity),
                    render: (value) =>
                      value == null ? (
                        "—"
                      ) : (
                        <Tag color={value >= 0 ? "green" : "red"}>
                          {value >= 0 ? "+" : ""}
                          {value.toFixed(2)}%
                        </Tag>
                      ),
                  },
                ]}
              />
            ),
          }))}
        />
      </Card>
    </>
  );
}
