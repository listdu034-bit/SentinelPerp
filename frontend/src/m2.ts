import axios from "axios";
import { authenticated } from "./session";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CandleResponse } from "./types";
import { mockRequest } from "./m2Mock";
export type Window = "1h" | "4h" | "24h";
export interface Phase {
  stage: string;
  start_time: string;
  end_time: string;
  description: string;
  confidence?: number;
}
export interface TurningPoint {
  time: string;
  description: string;
  kind: string;
}
export interface AnalysisResult {
  summary: string;
  stages: {
    stage: string;
    start_time: string;
    end_time: string;
    confidence: number;
    evidence: string;
  }[];
  turning_points: { time: string; kind: string; reason: string }[];
}
export interface AnalysisTask {
  id: string;
  symbol: string;
  start_time: string;
  end_time: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  result: AnalysisResult | null;
  error: string | null;
}
export interface Analysis extends Omit<AnalysisTask, "result"> {
  timeframe: string;
  result?: { summary: string; phases: Phase[]; turning_points: TurningPoint[] };
}
export interface Case {
  id: string;
  symbol: string;
  title: string;
  similarity: number;
  outcome: "success" | "failure" | null;
  analysis: AnalysisResult;
  container_id: string | null;
}
export interface Opportunity {
  symbol: string;
  observed_at: string;
  expires_at: string;
  stage: string;
  similarity: number;
  confidence: number;
  historical_success_rate: number | null;
  labeled_cases: number;
  matches: {
    id: string;
    symbol: string;
    title: string;
    similarity: number;
    outcome: "success" | "failure" | null;
  }[];
}
export type Feature = {
  time: string;
  symbol: string;
  [name: string]: string | number | boolean | null;
};
export interface SaveCase {
  task_id: string;
  title: string;
  outcome: "success" | "failure" | null;
  rating?: number;
  tags?: string[];
}
export const demoMode = import.meta.env.VITE_M2_MOCK === "true";
export const m2Http = authenticated(axios.create({
  baseURL: import.meta.env.VITE_M2_API_BASE_URL || "/api",
  timeout: 15000,
}));
export async function request<T>(
  method: "get" | "post",
  path: string,
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (demoMode) return mockRequest(method, path, data) as Promise<T>;
  return (
    await m2Http.request<T>({
      method,
      url: path,
      ...(method === "get" ? { params: data } : { data }),
      signal,
    })
  ).data;
}
export const stageName = (stage: string) =>
  ({
    accumulation: "吸筹",
    markup: "拉升",
    distribution: "派发",
    markdown: "下跌",
    unknown: "未知",
  })[stage] || stage;
export function phases(result: AnalysisResult): Phase[] {
  return result.stages.map((stage) => ({
    ...stage,
    stage: stageName(stage.stage),
    description: stage.evidence,
  }));
}
export function analysisView(task: AnalysisTask): Analysis {
  const hours =
    (Date.parse(task.end_time) - Date.parse(task.start_time)) / 3600000;
  return {
    ...task,
    timeframe: hours >= 1 ? `${hours}h` : `${hours * 60}m`,
    result: task.result
      ? {
          summary: task.result.summary,
          phases: phases(task.result),
          turning_points: task.result.turning_points.map((point) => ({
            ...point,
            description: point.reason,
          })),
        }
      : undefined,
  };
}
export const activeTask = (task: Analysis) =>
  task.status === "pending" || task.status === "running";
export function analysisWindow(
  symbol: string,
  timeframe: Window,
  now = Date.now(),
) {
  const end = Math.floor(now / 60000) * 60000;
  return {
    symbol,
    start_time: new Date(end - parseInt(timeframe) * 3600000).toISOString(),
    end_time: new Date(end).toISOString(),
  };
}
export function opportunityWindow(opportunity: Opportunity) {
  const end = Math.floor(Date.parse(opportunity.observed_at) / 60000) * 60000;
  return {
    symbol: opportunity.symbol,
    start_time: new Date(end - 3600000).toISOString(),
    end_time: new Date(end).toISOString(),
  };
}
export function useAnalyses() {
  return useQuery({
    queryKey: ["analysis"],
    queryFn: async ({ signal }) =>
      (
        await request<AnalysisTask[]>("get", "/analysis", undefined, signal)
      ).map(analysisView),
    refetchInterval: 30000,
  });
}
export function useAnalysis(id?: string) {
  return useQuery({
    queryKey: ["analysis", id],
    queryFn: async ({ signal }) =>
      analysisView(
        await request<AnalysisTask>(
          "get",
          `/analysis/${encodeURIComponent(id!)}`,
          undefined,
          signal,
        ),
      ),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data && activeTask(query.state.data) ? 3000 : false,
  });
}
export function useCreateAnalysis() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (data: { symbol: string; timeframe: Window }) =>
      analysisView(
        await request<AnalysisTask>(
          "post",
          "/analysis/create",
          analysisWindow(data.symbol, data.timeframe),
        ),
      ),
    onSuccess: (task) => {
      client.setQueryData(["analysis", task.id], task);
      client.setQueryData<Analysis[]>(["analysis"], (previous) => [
        task,
        ...(previous || []).filter((item) => item.id !== task.id),
      ]);
      void client.invalidateQueries({ queryKey: ["analysis"] });
    },
  });
}
export function saveCase(values: SaveCase) {
  // Rating/tags are not accepted by the current backend (extra=forbid).
  const { rating, tags, ...body } = values;
  return request<{ id: string }>("post", "/cases", demoMode ? values : body);
}
export function useOpportunityCandles(symbol?: string) {
  return useQuery({
    queryKey: ["opportunity-candles", symbol],
    enabled: !!symbol && demoMode,
    queryFn: () =>
      request<CandleResponse[]>("get", "/demo/candles", { symbol }),
  });
}
