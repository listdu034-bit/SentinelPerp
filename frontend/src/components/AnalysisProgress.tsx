import { Progress, Space, Tag } from "antd";
import type { Analysis } from "../m2";
export default function AnalysisProgress({ task }: { task: Analysis }) {
  return (
    <Space direction="vertical" style={{ width: 150 }}>
      <Tag
        color={
          task.status === "failed"
            ? "red"
            : task.status === "completed"
              ? "green"
              : "blue"
        }
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
        percent={Math.max(0, Math.min(100, task.progress))}
        status={
          task.status === "failed"
            ? "exception"
            : task.status === "completed"
              ? "success"
              : "active"
        }
      />
    </Space>
  );
}
