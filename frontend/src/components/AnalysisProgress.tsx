import { Progress, Space, Tag, Typography } from "antd";
import type { Analysis } from "../m2";
export default function AnalysisProgress({ task }: { task: Analysis }) {
  const completed = task.status === "completed";
  return (
    <Space direction="vertical" style={{ width: 150 }}>
      <Tag
        color={task.status === "failed" ? "red" : completed ? "green" : "blue"}
      >
        {
          {
            pending: "排队中",
            running: "分析中",
            completed: "已完成",
            failed: "失败",
          }[task.status]
        }
      </Tag>
      <Progress
        size="small"
        percent={completed ? 100 : 0}
        showInfo={completed}
        status={
          task.status === "failed"
            ? "exception"
            : completed
              ? "success"
              : "active"
        }
      />
      {!completed && task.status !== "failed" && (
        <Typography.Text type="secondary">
          等待任务完成 · 无百分比数据
        </Typography.Text>
      )}
    </Space>
  );
}
