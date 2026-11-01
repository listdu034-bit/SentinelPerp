import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CandleResponse } from "./types";
import { mockRequest } from "./m2Mock";
export type Window = "1h" | "4h" | "24h";
export interface Phase {
  stage: string;
  start_time: string;
  end_time: string;
  description: string;
}
export interface TurningPoint {
  time: string;
  description: string;
  price: number;
}
export interface Analysis {
  id: string;
  symbol: string;
  timeframe: Window;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  created_at: string;
  error?: string;
  result?: {
    summary: string;
    phases: Phase[];
    turning_points: TurningPoint[];
    features: Record<string, number>;
  };
}
export interface Case {
  id: string;
  symbol: string;
  summary: string;
  similarity: number;
  success_rate: number;
  tags: string[];
}
export interface Opportunity {
  id: string;
  symbol: string;
  stage: string;
  confidence: number;
  success_rate: number;
  detected_at: string;
  summary: string;
  features: Record<string, number>;
  historical_features: Record<string, number>;
  phases: Phase[];
}
export const demoMode = import.meta.env.VITE_M2_MOCK === "true";
export const m2Http = axios.create({
  baseURL: import.meta.env.VITE_M2_API_BASE_URL || "/api",
  timeout: 15000,
});
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
export const activeTask = (task: Analysis) =>
  task.status === "pending" || task.status === "running";
export function useAnalyses() {
  return useQuery({
    queryKey: ["analysis"],
    queryFn: ({ signal }) =>
      request<Analysis[]>("get", "/analysis", undefined, signal),
    refetchInterval: 3000,
  });
}
export function useAnalysis(id?: string) {
  return useQuery({
    queryKey: ["analysis", id],
    queryFn: ({ signal }) =>
      request<Analysis>(
        "get",
        `/analysis/${encodeURIComponent(id!)}`,
        undefined,
        signal,
      ),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data && activeTask(query.state.data) ? 2000 : false,
  });
}
export function useCreateAnalysis() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: { symbol: string; timeframe: Window }) =>
      request<Analysis>("post", "/analysis/create", data),
    onSuccess: (task) => {
      client.setQueryData(["analysis", task.id], task);
      void client.invalidateQueries({ queryKey: ["analysis"] });
    },
  });
}
export function useOpportunityCandles(symbol?: string) {
  return useQuery({
    queryKey: ["opportunity-candles", symbol],
    enabled: !!symbol && demoMode,
    queryFn: () =>
      request<CandleResponse[]>("get", "/demo/candles", { symbol }),
  });
}
