// @vitest-environment jsdom
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MockAdapter from "axios-mock-adapter";
import App from "./App";
import { http } from "./api";
vi.mock("./market", () => ({
  useMarket: () => ({
    connected: true,
    reconnecting: false,
    data: {
      time: "2026-01-01T00:00:00Z",
      gainers: [{ symbol: "BTC-USDT-SWAP", change_percent: 5 }],
      losers: [],
    },
  }),
}));
vi.mock("@ant-design/charts", () => ({ Column: () => <div>质量统计图</div> }));
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  const original = window.getComputedStyle;
  window.getComputedStyle = (element) => original(element);
});
afterEach(cleanup);
it.each([
  [
    "/status",
    "系统状态",
    "/status",
    {
      time: "2026-01-01T00:00:00Z",
      collection: {},
      redis: {},
      database: {},
      quality_score: 100,
    },
  ],
  ["/rankings", "涨跌幅榜单", "/unused", {}],
  [
    "/markets/BTC-USDT-SWAP",
    "市场详情",
    "/candles/BTC-USDT-SWAP",
    { items: [], total: 0 },
  ],
  [
    "/quality",
    "数据质量",
    "/quality/summary",
    { by_symbol: {}, by_issue_type: {} },
  ],
])(
  "renders route %s with API contract fixtures",
  async (path, heading, endpoint, response) => {
    const mock = new MockAdapter(http);
    mock.onGet(endpoint).reply(200, response);
    mock.onGet("/quality/logs").reply(200, { items: [], total: 0 });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    try {
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter
            initialEntries={[path]}
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
          >
            <App />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(
        await screen.findByRole(
          "heading",
          { name: heading },
          { timeout: 15000 },
        ),
      ).toBeTruthy();
      if (path === "/rankings")
        expect(
          await screen.findByRole(
            "link",
            { name: "BTC-USDT-SWAP" },
            { timeout: 15000 },
          ),
        ).toBeTruthy();
    } finally {
      cleanup();
      client.clear();
      mock.restore();
    }
  },
  30000,
);
