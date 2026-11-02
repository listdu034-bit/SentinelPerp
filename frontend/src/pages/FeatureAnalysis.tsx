import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Rate,
  Select,
  Space,
  Table,
  Timeline,
  Typography,
  message,
} from "antd";
import { errorMessage } from "../api";
import {
  demoMode,
  saveCase,
  useAnalyses,
  useAnalysis,
  type Analysis,
  type SaveCase,
} from "../m2";
import { timestamp } from "../format";
import QueryNotice from "../components/QueryNotice";
import AnalysisProgress from "../components/AnalysisProgress";
import M2Notice from "../components/M2Notice";
export default function FeatureAnalysis() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id") || undefined;
  const list = useAnalyses();
  const detail = useAnalysis(id);
  const [saved, setSaved] = useState<string[]>([]);
  const [feedback, context] = message.useMessage();
  const save = useMutation({
    mutationFn: (values: SaveCase) => saveCase(values),
    onSuccess: (_, values) => {
      setSaved((previous) => [...previous, values.task_id]);
      void feedback.success("案例已保存到特征库");
    },
    onError: (error) => void feedback.error(errorMessage(error)),
  });
  const task = detail.data;
  return (
    <>
      {context}
      <Typography.Title level={2}>特征分析</Typography.Title>
      <M2Notice />
      <QueryNotice query={list} />
      <Card title="分析任务">
        <Table<Analysis>
          rowKey="id"
          loading={list.isPending}
          dataSource={list.data || []}
          scroll={{ x: 700 }}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "合约", dataIndex: "symbol" },
            { title: "窗口", dataIndex: "timeframe" },
            { title: "创建时间", dataIndex: "created_at", render: timestamp },
            {
              title: "分析进度",
              render: (_, row) => <AnalysisProgress task={row} />,
            },
            {
              title: "操作",
              render: (_, row) => (
                <Button onClick={() => setParams({ id: row.id })}>
                  查看分析
                </Button>
              ),
            },
          ]}
        />
      </Card>
      {id ? (
        <Space direction="vertical" style={{ width: "100%", marginTop: 16 }}>
          <QueryNotice query={detail} />
          <Card
            title={task ? `${task.symbol} · AI 分析结果` : "AI 分析结果"}
            loading={detail.isPending}
          >
            {task && <AnalysisProgress task={task} />}
            {task?.status === "failed" && (
              <Alert
                type="error"
                showIcon
                message={task.error || "分析失败，请从榜单重新提交"}
              />
            )}
            {task?.result ? (
              <>
                <Typography.Paragraph style={{ marginTop: 16 }}>
                  {task.result.summary}
                </Typography.Paragraph>
                <Typography.Title level={4}>市场阶段</Typography.Title>
                <Timeline
                  items={task.result.phases.map((phase) => ({
                    children: (
                      <>
                        <strong>{phase.stage}</strong>
                        <p>
                          {timestamp(phase.start_time)} —{" "}
                          {timestamp(phase.end_time)}
                        </p>
                        <p>{phase.description}</p>
                      </>
                    ),
                  }))}
                />
                <Typography.Title level={4}>关键转折点</Typography.Title>
                <Timeline
                  items={task.result.turning_points.map((point) => ({
                    color: "red",
                    children: `${timestamp(point.time)} · ${point.kind} · ${point.description}`,
                  }))}
                />
                <Form
                  key={id}
                  layout="vertical"
                  initialValues={{
                    title: `${task.symbol} 特征案例`,
                    outcome: null,
                    rating: demoMode ? 3 : undefined,
                    tags: [],
                  }}
                  onFinish={(values) =>
                    save.mutate({
                      ...values,
                      task_id: id,
                      outcome: values.outcome ?? null,
                    })
                  }
                >
                  <Form.Item
                    name="title"
                    label="案例名称"
                    rules={[{ required: true, whitespace: true, max: 200 }]}
                  >
                    <Input maxLength={200} />
                  </Form.Item>
                  <Form.Item name="outcome" label="历史结果标注">
                    <Select
                      aria-label="历史结果标注"
                      options={[
                        { value: "success", label: "成功" },
                        { value: "failure", label: "失败" },
                      ]}
                      allowClear
                      placeholder="未标注"
                    />
                  </Form.Item>
                  {!demoMode && (
                    <Alert
                      type="info"
                      showIcon
                      message="当前 API 支持名称及历史结果；评分和标签待后端支持，暂不可保存。"
                    />
                  )}
                  <Form.Item
                    name="rating"
                    label="案例评分"
                    rules={[
                      {
                        required: demoMode,
                        type: "number",
                        min: 1,
                        message: "请至少选择 1 星",
                      },
                    ]}
                  >
                    <Rate disabled={!demoMode} />
                  </Form.Item>
                  <Form.Item
                    name="tags"
                    label="标签"
                    rules={[{ type: "array", max: 10 }]}
                  >
                    <Select
                      disabled={!demoMode}
                      mode="tags"
                      aria-label="案例标签"
                      tokenSeparators={[","]}
                      options={["突破", "吸筹", "拉升", "派发", "下跌"].map(
                        (value) => ({ value }),
                      )}
                    />
                  </Form.Item>

                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={save.isPending}
                    disabled={saved.includes(id)}
                  >
                    {" "}
                    {saved.includes(id) ? "已保存" : "保存到特征库"}
                  </Button>
                </Form>
              </>
            ) : (
              task &&
              task.status !== "failed" && (
                <Empty description="分析完成后显示阶段与转折点，进度自动更新" />
              )
            )}
          </Card>
        </Space>
      ) : (
        <Empty
          style={{ marginTop: 24 }}
          description="选择任务查看 AI 分析结果"
        />
      )}
    </>
  );
}
