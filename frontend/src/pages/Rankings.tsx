import { useState } from "react";
import { Button, Segmented, Space, message } from "antd";
import { demoMode, useAnalyses, useCreateAnalysis, type Window } from "../m2";
import { useRankingWindow } from "../rankingWindow";
import AnalysisProgress from "../components/AnalysisProgress";
import M2Notice from "../components/M2Notice";
import QueryNotice from "../components/QueryNotice";
import { errorMessage } from "../api";
import { Alert, Card, Table, Tabs, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { useMarket } from "../market";
import { timestamp } from "../format";
import type { MarketRow } from "../types";
export default function Rankings() {
  const query = useMarket();
  const [timeframe, setTimeframe] = useState<Window>("24h");
  const tasks = useAnalyses();
  const create = useCreateAnalysis();
  const [feedback, context] = message.useMessage();
  const snapshot = demoMode
    ? {
        gainers: [
          { symbol: "BTC-USDT-SWAP", change_percent: 5.2 },
          { symbol: "ETH-USDT-SWAP", change_percent: 3.1 },
        ],
        losers: [{ symbol: "SOL-USDT-SWAP", change_percent: -2.1 }],
      }
    : query.data;
  const windowQuery = useRankingWindow(
    [...(snapshot?.gainers || []), ...(snapshot?.losers || [])],
    demoMode ? "24h" : timeframe,
  );
  const data = (key: "gainers" | "losers") =>
    demoMode
      ? (snapshot?.[key] || []).map((row) => ({
          ...row,
          change_percent:
            row.change_percent! *
            (timeframe === "1h" ? 0.1 : timeframe === "4h" ? 0.4 : 1),
        }))
      : timeframe === "24h"
        ? snapshot?.[key] || []
        : (windowQuery.data || [])
            .filter(
              (row) =>
                row.change_percent != null &&
                (key === "gainers"
                  ? row.change_percent >= 0
                  : row.change_percent < 0),
            )
            .sort((a, b) =>
              key === "gainers"
                ? b.change_percent! - a.change_percent!
                : a.change_percent! - b.change_percent!,
            );
  return (
    <>
      <Typography.Title level={2}>涨跌幅榜单</Typography.Title>
      {context}
      <M2Notice />
      <Segmented
        aria-label="榜单时间窗口"
        value={timeframe}
        options={["1h", "4h", "24h"]}
        onChange={(value) => setTimeframe(value as Window)}
        style={{ marginBottom: 16 }}
      />
      {timeframe !== "24h" && <QueryNotice query={windowQuery} />}
      <QueryNotice query={tasks} />
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
      <Card title="OKX · USDT 永续合约" extra={<Tag>{timeframe} 观察窗口</Tag>}>
        <Typography.Paragraph type="secondary">
          24h 使用实时榜单；1h/4h 使用榜单合约的小时 K
          线重新计算，范围限于当前快照合约。最近快照：
          {timestamp(query.data?.time)}
        </Typography.Paragraph>
        <Tabs
          items={(["gainers", "losers"] as const).map((key) => ({
            key,
            label: key === "gainers" ? "涨幅榜" : "跌幅榜",
            children: (
              <Table<Pick<MarketRow, "symbol" | "change_percent">>
                rowKey="symbol"
                dataSource={data(key)}
                loading={timeframe !== "24h" && windowQuery.isFetching}
                scroll={{ x: 600 }}
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
                    title: `${timeframe} 涨跌幅`,
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
                  {
                    title: "分析",
                    render: (_, row) => {
                      const task = tasks.data?.find(
                        (task) =>
                          task.symbol === row.symbol &&
                          task.timeframe === timeframe,
                      );
                      const pending =
                        create.isPending &&
                        create.variables?.symbol === row.symbol;
                      return (
                        <Space direction="vertical">
                          {task && <AnalysisProgress task={task} />}
                          <Button
                            loading={pending}
                            disabled={
                              create.isPending ||
                              task?.status === "pending" ||
                              task?.status === "running"
                            }
                            onClick={() =>
                              create.mutate(
                                { symbol: row.symbol, timeframe },
                                {
                                  onSuccess: () =>
                                    void feedback.success("已添加分析任务"),
                                  onError: (error) =>
                                    void feedback.error(errorMessage(error)),
                                },
                              )
                            }
                          >
                            添加到分析
                          </Button>
                          {task && (
                            <Link
                              to={`/feature-analysis?id=${encodeURIComponent(task.id)}`}
                            >
                              查看分析
                            </Link>
                          )}
                        </Space>
                      );
                    },
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
