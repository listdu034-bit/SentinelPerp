// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MockAdapter from "axios-mock-adapter";
import type { PropsWithChildren } from "react";
import {
  http,
  queryClient,
  useCandles,
  useQualityLogs,
  useStatus,
} from "./api";
const mock = new MockAdapter(http);
afterEach(() => {
  cleanup();
  mock.reset();
});
function setup() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { ...queryClient.getDefaultOptions().queries, retry: false },
    },
  });
  return {
    client,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}
describe("API integration and query lifecycle", () => {
  it("shares fresh status across mounts without another request", async () => {
    mock.onGet("/status").reply(200, { quality_score: 99 });
    const { wrapper, client } = setup();
    const first = renderHook(() => useStatus(), { wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    first.unmount();
    const second = renderHook(() => useStatus(), { wrapper });
    expect(second.result.current.data?.quality_score).toBe(99);
    expect(mock.history.get).toHaveLength(1);
    client.clear();
  });
  it("polls mounted status at configured interval", async () => {
    vi.useFakeTimers();
    const { wrapper, client } = setup();
    mock.onGet("/status").reply(200, { quality_score: 100 });
    try {
      renderHook(() => useStatus(), { wrapper });
      await vi.advanceTimersByTimeAsync(100);
      expect(mock.history.get).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(30000);
      expect(mock.history.get.length).toBeGreaterThanOrEqual(2);
    } finally {
      client.clear();
      vi.useRealTimers();
    }
  });
  it("uses backend candle interval and pagination contract", async () => {
    mock
      .onGet("/candles/BTC-USDT-SWAP", {
        params: { interval: "5m", size: 500 },
      })
      .reply(200, { items: [], total: 0, page: 1, size: 500, pages: 0 });
    const { wrapper, client } = setup();
    const hook = renderHook(() => useCandles("BTC-USDT-SWAP", "5m"), {
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
    client.clear();
  });
  it("sends server-side quality pagination and severity filter", async () => {
    mock
      .onGet("/quality/logs", {
        params: { page: 2, size: 20, severity: "error" },
      })
      .reply(200, { items: [], total: 25, page: 2, size: 20, pages: 2 });
    const { wrapper, client } = setup();
    const hook = renderHook(() => useQualityLogs(2, 20, "error"), { wrapper });
    await waitFor(() => expect(hook.result.current.data?.total).toBe(25));
    client.clear();
  });
  it("exposes request failures instead of synthesizing data", async () => {
    mock
      .onGet("/status")
      .reply(503, { error: { message: "Dependency unavailable" } });
    const { wrapper, client } = setup();
    const hook = renderHook(() => useStatus(), { wrapper });
    await waitFor(() => expect(hook.result.current.isError).toBe(true));
    expect(hook.result.current.data).toBeUndefined();
    client.clear();
  });
});
