// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MockAdapter from "axios-mock-adapter";
import App from "./App";
import { http } from "./api";
import { authHttp } from "./auth";
import { getToken, setToken } from "./session";
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
let authMock: MockAdapter;
beforeEach(() => {
  setToken("test-token");
  authMock = new MockAdapter(authHttp);
  authMock.onGet("/users/me").reply(200, {
    username: "operator",
    expires_at: Math.floor(Date.now() / 1000) + 3600,
  });
});
afterEach(() => {
  cleanup();
  authMock.restore();
  setToken(null);
});
function renderRoute(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
it("redirects anonymous protected routes to login without requesting session", async () => {
  setToken(null);
  const client = renderRoute("/quality?window=24h");
  expect(await screen.findByText("登录您的市场分析工作台")).toBeTruthy();
  expect(authMock.history.get).toHaveLength(0);
  client.clear();
});
it("restores a session and clears the token after logout", async () => {
  authMock.onPost("/auth/jwt/logout").reply(204);
  const mock = new MockAdapter(http);
  mock.onGet("/status").reply(200, {
    collection: {}, redis: {}, database: {}, quality_score: 100,
  });
  const client = renderRoute("/status");
  expect(await screen.findByText("operator")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByText("登录您的市场分析工作台")).toBeTruthy();
  expect(getToken()).toBeNull();
  client.clear();
  mock.restore();
});
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
