import axios from "axios";
import { authenticated } from "./session";
import { QueryClient, useQuery } from "@tanstack/react-query";
import type {
  CandleResponse,
  Interval,
  Page,
  QualityLogResponse,
  QualitySummary,
  SystemStatusResponse,
} from "./types";
export const http = authenticated(axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 15000,
}));
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10000,
      gcTime: 300000,
      refetchInterval: 30000,
      retry: (count, error) =>
        count < 2 &&
        !(
          axios.isAxiosError(error) &&
          error.response &&
          error.response.status < 500 &&
          error.response.status !== 429
        ),
      refetchOnWindowFocus: true,
    },
  },
});
export async function get<T>(
  url: string,
  signal?: AbortSignal,
  params?: Record<string, unknown>,
) {
  return (await http.get<T>(url, { signal, params })).data;
}
export const useStatus = () =>
  useQuery({
    queryKey: ["status"],
    queryFn: ({ signal }) => get<SystemStatusResponse>("/status", signal),
  });
export const useCandles = (symbol: string, interval: Interval) =>
  useQuery({
    queryKey: ["candles", symbol, interval],
    queryFn: ({ signal }) =>
      get<Page<CandleResponse>>(
        `/candles/${encodeURIComponent(symbol)}`,
        signal,
        { interval, size: 500 },
      ),
    enabled: /^[A-Z0-9]+-USDT-SWAP$/.test(symbol),
  });
export const useQualityLogs = (page: number, size: number, severity?: string) =>
  useQuery({
    queryKey: ["quality", "logs", page, size, severity],
    queryFn: ({ signal }) =>
      get<Page<QualityLogResponse>>("/quality/logs", signal, {
        page,
        size,
        severity,
      }),
  });
export const useQualitySummary = () =>
  useQuery({
    queryKey: ["quality", "summary"],
    queryFn: ({ signal }) => get<QualitySummary>("/quality/summary", signal),
  });
export function errorMessage(error: unknown) {
  if (axios.isAxiosError(error))
    return error.response?.data?.error?.message || error.message;
  return error instanceof Error ? error.message : "请求失败";
}
