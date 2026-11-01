import { useQuery } from "@tanstack/react-query";
import { get } from "./api";
import type { CandleResponse, MarketRow, Page } from "./types";
import type { Window } from "./m2";
export function windowChange(candles: CandleResponse[], hours: number) {
  const sorted = candles
    .filter((row) => Number.isFinite(Date.parse(row.time)))
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  const latest = sorted.at(-1);
  if (!latest) return null;
  const boundary = Date.parse(latest.time) - (hours - 1) * 3600000;
  const start = sorted.find((row) => Date.parse(row.time) >= boundary);
  if (
    !start ||
    Date.parse(start.time) > boundary ||
    !Number.isFinite(start.open) ||
    start.open <= 0 ||
    !Number.isFinite(latest.close)
  )
    return null;
  return (latest.close / start.open - 1) * 100;
}
export function useRankingWindow(
  rows: Pick<MarketRow, "symbol">[],
  timeframe: Window,
) {
  const symbols = [...new Set(rows.map((row) => row.symbol))].sort();
  return useQuery({
    queryKey: ["ranking-window", timeframe, symbols],
    enabled: timeframe !== "24h" && symbols.length > 0,
    queryFn: async ({ signal }) =>
      Promise.all(
        symbols.map(async (symbol) => {
          const data = await get<Page<CandleResponse>>(
            `/candles/${encodeURIComponent(symbol)}`,
            signal,
            { interval: "1h", size: 24 },
          );
          return {
            symbol,
            change_percent: windowChange(
              data.items,
              timeframe === "1h" ? 1 : 4,
            ),
          };
        }),
      ),
  });
}
