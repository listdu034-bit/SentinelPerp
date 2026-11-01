import type { AnalysisResult, AnalysisTask, Opportunity, Case } from "./m2";
const now = Math.floor(Date.now() / 60000) * 60000;
const time = (hours = 0) => new Date(now - hours * 3600000).toISOString();
const result: AnalysisResult = {
  summary:
    "价格突破整理区间，持仓量与主动买盘同步上升。需持续关注突破后的成交量。",
  stages: [
    {
      stage: "accumulation",
      start_time: time(4),
      end_time: time(2),
      confidence: 0.8,
      evidence: "成交量逐步放大，价格区间收窄",
    },
    {
      stage: "markup",
      start_time: time(2),
      end_time: time(),
      confidence: 0.85,
      evidence: "价格突破区间，资金流入增强",
    },
  ],
  turning_points: [
    { time: time(2), kind: "breakout", reason: "放量突破整理区间" },
  ],
};
const tasks: AnalysisTask[] = [
  {
    id: "demo-analysis",
    symbol: "BTC-USDT-SWAP",
    start_time: time(4),
    end_time: time(),
    status: "completed",
    created_at: time(4),
    updated_at: time(),
    result,
    error: null,
  },
];
const opportunities: Opportunity[] = ["BTC", "ETH", "SOL"].map((symbol, i) => ({
  symbol: `${symbol}-USDT-SWAP`,
  stage: "markup",
  confidence: 0.86 - i * 0.08,
  historical_success_rate: i === 2 ? null : 0.74 - i * 0.06,
  labeled_cases: i === 2 ? 0 : 12,
  similarity: 0.9,
  observed_at: time(i),
  expires_at: new Date(now + 600000).toISOString(),
  matches: [
    {
      id: "case-demo",
      symbol: "BTC-USDT-SWAP",
      title: "历史突破案例",
      similarity: 0.9,
      outcome: "success",
    },
  ],
}));
export async function mockRequest(
  method: string,
  path: string,
  data: unknown,
): Promise<unknown> {
  const input = data as Record<string, unknown> | undefined;
  if (path === "/analysis/create") {
    const task: AnalysisTask = {
      id: `demo-${Date.now()}`,
      symbol: String(input?.symbol),
      start_time: String(input?.start_time),
      end_time: String(input?.end_time),
      status: "pending",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      result: null,
      error: null,
    };
    tasks.unshift(task);
    return { ...task };
  }
  for (const task of tasks.filter((t) => t.status !== "completed")) {
    task.status =
      Date.now() - Date.parse(task.created_at) > 10000
        ? "completed"
        : "running";
    if (task.status === "completed") {
      const mid = new Date(
        (Date.parse(task.start_time) + Date.parse(task.end_time)) / 2,
      ).toISOString();
      task.result = {
        ...result,
        stages: [
          { ...result.stages[0], start_time: task.start_time, end_time: mid },
          { ...result.stages[1], start_time: mid, end_time: task.end_time },
        ],
        turning_points: [{ ...result.turning_points[0], time: mid }],
      };
    }
  }
  if (path === "/analysis") return tasks.map((t) => ({ ...t }));
  if (path.startsWith("/analysis/")) {
    const task = tasks.find((t) => t.id === path.split("/").pop());
    if (!task) throw new Error("任务不存在");
    return { ...task };
  }
  if (path === "/cases" && method === "post")
    return { id: `case-${Date.now()}`, ...input };
  if (path === "/cases/search")
    return [
      {
        id: "case-demo",
        symbol: "BTC-USDT-SWAP",
        title: "历史突破拉升案例",
        similarity: 0.91,
        outcome: "success",
        analysis: result,
        container_id: null,
      },
    ] satisfies Case[];
  if (path === "/opportunities")
    return opportunities.filter(
      (o) => o.confidence >= Number(input?.min_confidence || 0),
    );
  if (path.startsWith("/opportunities/"))
    return opportunities.find(
      (o) => o.symbol === decodeURIComponent(path.split("/").pop()!),
    );
  if (path.startsWith("/features/"))
    return [
      {
        time: time(),
        symbol: String(input?.symbol || path.split("/").pop()),
        price_change_pct: 5.2,
        oi_change_pct: 8.1,
        obi: 0.3,
        quality: 0.92,
      },
    ];
  if (path === "/demo/candles")
    return Array.from({ length: 240 }, (_, i) => ({
      time: new Date(now - (240 - i) * 60000).toISOString(),
      symbol: input?.symbol,
      exchange: "OKX",
      interval: "1m",
      open: 65000 + i * 10,
      close: 65010 + i * 10,
      high: 65020 + i * 10,
      low: 64990 + i * 10,
      volume: 100 + i,
    }));
  throw new Error(`Mock endpoint missing: ${path}`);
}
