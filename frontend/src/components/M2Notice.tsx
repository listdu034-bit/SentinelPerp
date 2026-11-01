import { Alert } from "antd";
import { demoMode } from "../m2";
export default function M2Notice() {
  return demoMode ? (
    <Alert
      style={{ marginBottom: 16 }}
      showIcon
      type="warning"
      message="Mock 演示模式 · 所有分析、机会和保存操作均为模拟数据，刷新后重置"
    />
  ) : null;
}
