import { useState } from "react";
import { Card, Empty, Input, Select, Space, Statistic, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useCandles } from "../api";
import CandleChart from "../components/CandleChart";
import QueryNotice from "../components/QueryNotice";
import type { Interval } from "../types";
export default function Market() {
  const { symbol = "BTC-USDT-SWAP" } = useParams();
  const navigate = useNavigate();
  const [interval, setInterval] = useState<Interval>("1m");
  const query = useCandles(symbol, interval);
  const rows = query.data?.items || [];
  const latest = rows[0];
  const valid = /^[A-Z0-9]+-USDT-SWAP$/.test(symbol);
  return (
    <>
      <Typography.Title level={2}>市场详情</Typography.Title>
      <Space wrap style={{ marginBottom: 20 }}>
        <Input.Search
          key={symbol}
          aria-label="合约代码"
          defaultValue={symbol}
          placeholder="BTC-USDT-SWAP"
          enterButton="查看合约"
          onSearch={(value) => {
            if (value.trim())
              navigate(
                `/markets/${encodeURIComponent(value.trim().toUpperCase())}`,
              );
          }}
        />
        <Select<Interval>
          aria-label="K 线周期"
          value={interval}
          onChange={setInterval}
          options={["1m", "5m", "1h", "1d"].map((value) => ({
            value: value as Interval,
            label: value,
          }))}
        />
      </Space>
      {!valid && (
        <Typography.Paragraph type="danger">
          请输入有效合约代码，例如 BTC-USDT-SWAP。
        </Typography.Paragraph>
      )}
      <QueryNotice query={query} />
      <Card
        title={`${symbol} · ${interval}`}
        loading={query.isPending && valid}
      >
        <Space size="large" wrap style={{ marginBottom: 20 }}>
          <Statistic
            title="最新收盘价"
            value={latest?.close ?? "—"}
            precision={4}
          />
          <Statistic
            title="最新成交量"
            value={latest?.volume ?? "—"}
            precision={4}
          />
        </Space>
        {rows.length ? (
          <CandleChart rows={rows} />
        ) : (
          <Empty description="当前窗口没有 K 线数据" />
        )}
        <Typography.Paragraph type="secondary">
          展示最新最多 500 根 K 线。较长周期受后端聚合刷新策略影响。
        </Typography.Paragraph>
      </Card>
    </>
  );
}
