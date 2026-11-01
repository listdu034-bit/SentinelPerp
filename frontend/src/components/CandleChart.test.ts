import { describe, expect, it } from "vitest";
import { candleSeries } from "./CandleChart";
import type { CandleResponse } from "../types";
const row = (time: string, close = 2): CandleResponse => ({
  time,
  symbol: "BTC-USDT-SWAP",
  exchange: "OKX",
  interval: "1m",
  open: 1,
  high: 3,
  low: 1,
  close,
  volume: 10,
});
describe("candlestick API normalization", () => {
  it("sorts newest-first API data into chart order and deduplicates timestamps", () => {
    const data = candleSeries([
      row("2026-01-01T00:01:00Z"),
      row("2026-01-01T00:00:00Z"),
      row("2026-01-01T00:01:00Z", 3),
    ]);
    expect(data).toHaveLength(2);
    expect(data[0].time).toBeLessThan(data[1].time);
    expect(data[1].close).toBe(3);
  });
  it("rejects invalid dates and non-finite prices", () => {
    expect(
      candleSeries([row("invalid"), row("2026-01-01T00:01:00Z", NaN)]),
    ).toEqual([]);
  });
});
