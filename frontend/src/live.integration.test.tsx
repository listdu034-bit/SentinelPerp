// @vitest-environment jsdom
// Opt in against an isolated API seeded with the acceptance dataset in README.
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  get,
  http,
  queryClient,
  useCandles,
  useQualityLogs,
  useQualitySummary,
  useStatus,
} from "./api";
import { useMarket } from "./market";
import { candleSeries } from "./components/CandleChart";
import type { Page, QualityLogResponse, SystemStatusResponse } from "./types";
const base = process.env.CONSOLE_TEST_URL;
describe.skipIf(!base)(
  "live frontend/nginx/FastAPI/TimescaleDB/Redis integration",
  () => {
    beforeAll(() => {
      http.defaults.baseURL = `${base}/api/v1`;
      vi.stubEnv("VITE_WS_BASE_URL", base!.replace(/^http/, "ws"));
    });
    afterEach(() => {
      cleanup();
    });
    function setup() {
      const client = new QueryClient({
        defaultOptions: {
          queries: { ...queryClient.getDefaultOptions().queries, retry: false },
        },
      });
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      );
      return { client, wrapper };
    }
    it("reads seeded candles, quality charts and server-paginated logs through nginx", async () => {
      const { client, wrapper } = setup();
      try {
        const candles = renderHook(() => useCandles("BTC-USDT-SWAP", "1m"), {
          wrapper,
        });
        const summary = renderHook(() => useQualitySummary(), { wrapper });
        const logs = renderHook(() => useQualityLogs(2, 10, "warning"), {
          wrapper,
        });
        await waitFor(
          () => {
            expect(candles.result.current.data?.items.length).toBe(120);
            expect(
              summary.result.current.data?.by_symbol["BTC-USDT-SWAP"],
            ).toBe(25);
            expect(logs.result.current.data?.page).toBe(2);
          },
          { timeout: 15000 },
        );
        const points = candleSeries(candles.result.current.data!.items);
        expect(points).toHaveLength(120);
        expect(points[0].time).toBeLessThan(points[119].time);
        expect(logs.result.current.data?.items).toHaveLength(10);
        expect(logs.result.current.data?.total).toBe(20);
        expect(
          logs.result.current.data?.items.every(
            (row) => row.severity === "warning",
          ),
        ).toBe(true);
        const errors = await get<Page<QualityLogResponse>>(
          "/quality/logs",
          undefined,
          { severity: "error" },
        );
        expect(errors.total).toBe(5);
        for (const interval of ["5m", "1h", "1d"]) {
          const aggregate = await get<Page<unknown>>(
            "/candles/BTC-USDT-SWAP",
            undefined,
            { interval },
          );
          expect(aggregate.total).toBeGreaterThan(0);
        }
      } finally {
        cleanup();
        client.clear();
      }
    }, 30000);
    it("reuses the real status cache and automatically refreshes it after 30 seconds", async () => {
      const { client, wrapper } = setup();
      try {
        const first = renderHook(() => useStatus(), { wrapper });
        await waitFor(() => expect(first.result.current.isSuccess).toBe(true), {
          timeout: 15000,
        });
        const updated = first.result.current.dataUpdatedAt;
        expect(first.result.current.data?.collection.candles.count).toBe(120);
        first.unmount();
        const second = renderHook(() => useStatus(), { wrapper });
        expect(second.result.current.dataUpdatedAt).toBe(updated);
        expect(second.result.current.isFetching).toBe(false);
        await waitFor(
          () =>
            expect(second.result.current.dataUpdatedAt).toBeGreaterThan(
              updated,
            ),
          { timeout: 35000, interval: 500 },
        );
      } finally {
        cleanup();
        client.clear();
      }
    }, 55000);
    it("receives real market snapshots and subsequent pushes through nginx WebSocket upgrade", async () => {
      const { client, wrapper } = setup();
      try {
        const market = renderHook(() => useMarket(), { wrapper });
        await waitFor(
          () =>
            expect(
              market.result.current.data?.gainers.some(
                (row) => row.symbol === "BTC-USDT-SWAP",
              ),
            ).toBe(true),
          { timeout: 15000 },
        );
        const initial = market.result.current.data!.time;
        expect(market.result.current.connected).toBe(true);
        expect(
          client.getQueryData<SystemStatusResponse>(["status"])?.collection
            .candles.count,
        ).toBe(120);
        await waitFor(
          () => expect(market.result.current.data?.time).not.toBe(initial),
          { timeout: 35000, interval: 500 },
        );
        expect(market.result.current.connected).toBe(true);
      } finally {
        cleanup();
        client.clear();
      }
    }, 55000);
  },
);
