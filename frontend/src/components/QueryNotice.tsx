import { Alert, Button, Space, Typography } from "antd";
import { errorMessage } from "../api";
import { timestamp } from "../format";
export default function QueryNotice({
  query,
}: {
  query: {
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
    dataUpdatedAt: number;
    isFetching: boolean;
  };
}) {
  return (
    <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
      {query.isError && (
        <Alert
          showIcon
          type="error"
          message="数据暂时不可用"
          description={errorMessage(query.error)}
          action={<Button onClick={() => void query.refetch()}>重试</Button>}
        />
      )}
      <Typography.Text type="secondary">
        {query.isFetching
          ? "正在更新…"
          : `最近获取：${query.dataUpdatedAt ? timestamp(new Date(query.dataUpdatedAt).toISOString()) : "等待数据"}`}{" "}
        · 每 30 秒自动刷新 · 时间为本地时间
      </Typography.Text>
    </Space>
  );
}
