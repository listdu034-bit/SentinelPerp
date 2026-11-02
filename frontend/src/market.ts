import { useEffect } from "react";
import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";
import useWebSocket, { ReadyState } from "react-use-websocket";
import { getToken, setToken } from "./session";
import type { MarketSnapshot } from "./types";
export function marketSocketUrl() {
  if (import.meta.env.VITE_WS_BASE_URL)
    return `${import.meta.env.VITE_WS_BASE_URL.replace(/\/$/, "")}/ws/market`;
  const url = new URL(
    import.meta.env.VITE_API_BASE_URL || "/",
    window.location.origin,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/market";
  url.search = "";
  url.hash = "";
  return url.toString();
}
export function useMarket() {
  const client = useQueryClient();
  const { lastJsonMessage, readyState, sendJsonMessage } = useWebSocket<
    Record<string, unknown>
  >(marketSocketUrl(), {
    onOpen: (event) =>
      (event.target as WebSocket).send(
        JSON.stringify({ type: "authenticate", token: getToken() }),
      ),
    onClose: (event) => {
      if (event.code === 1008) setToken(null);
    },
    shouldReconnect: (event) => event.code !== 1008 && !!getToken(),
    reconnectAttempts: Infinity,
    reconnectInterval: (attempt) => Math.min(1000 * 2 ** attempt, 30000),
    retryOnError: true,
  });
  const query = useQuery<MarketSnapshot>({
    queryKey: ["market"],
    queryFn: skipToken,
    enabled: false,
    refetchInterval: false,
  });
  useEffect(() => {
    if (lastJsonMessage?.type === "ping") sendJsonMessage({ type: "pong" });
    if (lastJsonMessage?.type === "market") {
      const snapshot = lastJsonMessage as unknown as MarketSnapshot;
      client.setQueryData(["market"], snapshot);
      client.setQueryData(["status"], snapshot.status);
    }
  }, [lastJsonMessage, client, sendJsonMessage]);
  return {
    ...query,
    connected: readyState === ReadyState.OPEN,
    reconnecting: lastJsonMessage?.type === "reconnecting",
  };
}
