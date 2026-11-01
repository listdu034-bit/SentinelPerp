// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
const socket = vi.hoisted(() => ({
  message: null as Record<string, unknown> | null,
  send: vi.fn(),
}));
vi.mock("react-use-websocket", () => ({
  default: () => ({
    lastJsonMessage: socket.message,
    readyState: 1,
    sendJsonMessage: socket.send,
  }),
  ReadyState: { OPEN: 1 },
}));
import { useMarket } from "./market";
afterEach(() => {
  cleanup();
  socket.message = null;
  socket.send.mockClear();
});
function setup() {
  const client = new QueryClient();
  return {
    client,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}
it("responds to server heartbeat using the established socket", () => {
  socket.message = { type: "ping" };
  const { client, wrapper } = setup();
  renderHook(() => useMarket(), { wrapper });
  expect(socket.send).toHaveBeenCalledWith({ type: "pong" });
  client.clear();
});
it("shares pushed market and system snapshots through Query cache", async () => {
  const status = { quality_score: 99 };
  socket.message = {
    type: "market",
    time: "2026-01-01T00:00:00Z",
    gainers: [],
    losers: [],
    status,
  };
  const { client, wrapper } = setup();
  const hook = renderHook(() => useMarket(), { wrapper });
  await waitFor(() =>
    expect(hook.result.current.data?.time).toBe("2026-01-01T00:00:00Z"),
  );
  expect(client.getQueryData(["status"])).toEqual(status);
  expect(hook.result.current.connected).toBe(true);
  client.clear();
});
