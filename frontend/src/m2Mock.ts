import type { Analysis, Opportunity, Case } from "./m2";
const now = Date.now();
const time = (hours = 0) => new Date(now - hours * 3600000).toISOString();
const phases = [
  {
    stage: "吸筹",
    start_time: time(4),
    end_time: time(2),
    description: "成交量逐步放大，价格区间收窄",
  },
  {
    stage: "拉升",
    start_time: time(2),
    end_time: time(),
    description: "价格突破区间，资金流入增强",
  },
];
const result = {
  summary:
    "价格突破整理区间，持仓量与主动买盘同步上升。需持续关注突破后的成交量。",
  phases,
  turning_points: [
    { time: time(2), price: 65000, description: "放量突破整理区间" },
  ],
  features: { price_change: 5.2, oi_change: 8.1 },
};
const tasks: Analysis[] = [
  {
    id: "demo-analysis",
    symbol: "BTC-USDT-SWAP",
    timeframe: "4h",
    status: "completed",
    progress: 100,
    created_at: time(4),
    result,
  },
];
const opportunities: Opportunity[] = ["BTC", "ETH", "SOL"].map((symbol, i) => ({
  id: `demo-${i}`,
  symbol: `${symbol}-USDT-SWAP`,
  stage: "拉升",
  confidence: 0.86 - i * 0.08,
  success_rate: 0.74 - i * 0.06,
  detected_at: time(i),
  summary: result.summary,
  features: result.features,
  historical_features: { price_change: 4.8, oi_change: 7.6 },
  phases,
}));
export async function mockRequest(
  method: string,
  path: string,
  data: unknown,
): Promise<unknown> {
  const input = data as Record<string, unknown> | undefined;
  if (path === "/analysis/create") {
    const task: Analysis = {
      id: `demo-${Date.now()}`,
      symbol: String(input?.symbol),
      timeframe: input?.timeframe as Analysis["timeframe"],
      status: "pending",
      progress: 0,
      created_at: new Date().toISOString(),
    };
    tasks.unshift(task);
    return { ...task };
  }
  for (const task of tasks.filter((t) => t.status !== "completed")) {
    task.progress = Math.min(
      100,
      Math.floor((Date.now() - Date.parse(task.created_at)) / 100),
    );
    task.status = task.progress === 100 ? "completed" : "running";
    if (task.status === "completed") task.result = result;
  }
  if (path === "/analysis") return tasks.map((t) => ({ ...t }));
  if (path.startsWith("/analysis/"))
    return { ...tasks.find((t) => t.id === path.split("/").pop())! };
  if (path === "/cases" && method === "post")
    return { id: `case-${Date.now()}`, ...input };
  if (path === "/cases/search")
    return [
      {
        id: "case-demo",
        symbol: "BTC-USDT-SWAP",
        summary: "历史突破拉升案例",
        similarity: 0.91,
        success_rate: 0.78,
        tags: ["突破", "量价齐升"],
      },
    ] satisfies Case[];
  if (path === "/opportunities")
    return opportunities.filter(
      (o) =>
        o.confidence >= Number(input?.min_confidence || 0) &&
        o.success_rate >= Number(input?.min_success_rate || 0) &&
        Date.parse(o.detected_at) >=
          Date.now() - Number(input?.hours || 24) * 3600000,
    );
  if (path.startsWith("/opportunities/"))
    return opportunities.find((o) => o.id === path.split("/").pop());
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
