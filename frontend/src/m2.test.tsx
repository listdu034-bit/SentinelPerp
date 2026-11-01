// @vitest-environment jsdom
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import {
  cleanup,
  configure,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import MockAdapter from "axios-mock-adapter";
import { m2Http } from "./m2";
import FeatureAnalysis from "./pages/FeatureAnalysis";
import Opportunities from "./pages/Opportunities";
import Rankings from "./pages/Rankings";
import { windowChange } from "./rankingWindow";
vi.mock("./market", () => ({
  useMarket: () => ({
    connected: true,
    data: {
      gainers: [{ symbol: "BTC-USDT-SWAP", change_percent: 5 }],
      losers: [],
    },
  }),
}));
vi.mock("./components/CandleChart", () => ({ default: () => <div>K 线</div> }));
configure({ asyncUtilTimeout: 15000 });
vi.setConfig({ testTimeout: 60000 });
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: () => ({
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }),
  });
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  const original = window.getComputedStyle;
  // JSDOM has no layout; avoid repeatedly evaluating Ant Design's stylesheet.
  const computedStyle = original(document.body);
  window.getComputedStyle = () => computedStyle;
});
const clients: QueryClient[] = [];
const mock = new MockAdapter(m2Http);
afterEach(() => {
  cleanup();
  clients.forEach((client) => client.clear());
  mock.reset();
});
function mount(element: React.ReactNode, path = "/") {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const task = {
  id: "a1",
  symbol: "BTC-USDT-SWAP",
  timeframe: "24h",
  status: "completed",
  progress: 100,
  created_at: "2026-01-01T00:00:00Z",
  result: { summary: "突破形态", phases: [], turning_points: [], features: {} },
};
it("submits an analysis with the selected symbol and timeframe", async () => {
  mock.onGet("/analysis").reply(200, []);
  mock.onPost("/analysis/create").reply(200, task);
  mount(<Rankings />);
  fireEvent.click(await screen.findByRole("button", { name: "添加到分析" }));
  await waitFor(() => expect(mock.history.post).toHaveLength(1));
  expect(JSON.parse(mock.history.post[0].data)).toEqual({
    symbol: "BTC-USDT-SWAP",
    timeframe: "24h",
  });
});
it("loads analysis details and saves the rated case", async () => {
  mock.onGet("/analysis").reply(200, [task]);
  mock.onGet("/analysis/a1").reply(200, task);
  mock.onPost("/cases").reply(201, { id: "c1" });
  mount(<FeatureAnalysis />, "/feature-analysis?id=a1");
  expect(await screen.findByText("突破形态")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "保存到特征库" }));
  await screen.findByRole("button", { name: "已保存" });
  expect(JSON.parse(mock.history.post[0].data)).toMatchObject({
    analysis_id: "a1",
    rating: 3,
    tags: [],
  });
});
it("shows save failures and permits retry", async () => {
  mock.onGet("/analysis").reply(200, [task]);
  mock.onGet("/analysis/a1").reply(200, task);
  mock.onPost("/cases").reply(500);
  mount(<FeatureAnalysis />, "/feature-analysis?id=a1");
  fireEvent.click(await screen.findByRole("button", { name: "保存到特征库" }));
  await screen.findByText("Request failed with status code 500");
  expect(
    screen
      .getByRole("button", { name: "保存到特征库" })
      .hasAttribute("disabled"),
  ).toBe(false);
});
it("filters opportunities and loads detail and similar cases", async () => {
  const opportunity = {
    id: "o1",
    symbol: "BTC-USDT-SWAP",
    stage: "拉升",
    confidence: 0.9,
    success_rate: 0.8,
    detected_at: task.created_at,
    summary: "机会摘要",
    features: { oi: 3 },
    historical_features: { oi: 2 },
    phases: [],
  };
  mock.onGet("/opportunities").reply(200, [opportunity]);
  mock.onGet("/opportunities/o1").reply(200, opportunity);
  mock.onGet("/cases/search").reply(200, []);
  mount(<Opportunities />);
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "最低置信度" }));
  fireEvent.click(await screen.findByText("80%"));
  await waitFor(() =>
    expect(
      mock.history.get.some((item) => item.params?.min_confidence === 0.8),
    ).toBe(true),
  );
  fireEvent.click(await screen.findByRole("button", { name: "查看机会详情" }));
  await screen.findByText("相似历史案例");
  await waitFor(() =>
    expect(
      mock.history.get.some(
        (item) =>
          item.url === "/cases/search" && item.params.opportunity_id === "o1",
      ),
    ).toBe(true),
  );
  expect(await screen.findByText("历史案例参考值")).toBeTruthy();
});
it("computes the selected candle window and rejects incomplete history", () => {
  const rows = [0, 1, 2, 3].map((i) => ({
    time: `2026-01-01T0${i}:00:00Z`,
    symbol: "BTC-USDT-SWAP",
    exchange: "OKX",
    interval: "1h",
    open: 100,
    high: 120,
    low: 90,
    close: 110,
    volume: 100,
  }));
  expect(windowChange(rows, 4)).toBeCloseTo(10);
  expect(windowChange(rows.slice(1), 4)).toBeNull();
});
