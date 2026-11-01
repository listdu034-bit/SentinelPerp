import { useEffect, useRef } from "react";
import { createChart, type UTCTimestamp } from "lightweight-charts";
import type { Phase } from "../m2";
import type { CandleResponse } from "../types";
export function candleSeries(rows: CandleResponse[]) {
  const unique = new Map<number, CandleResponse>();
  for (const row of rows) {
    const time = Math.floor(Date.parse(row.time) / 1000);
    if (
      Number.isFinite(time) &&
      [row.open, row.high, row.low, row.close].every(Number.isFinite)
    )
      unique.set(time, row);
  }
  return [...unique]
    .sort(([a], [b]) => a - b)
    .map(([time, row]) => ({
      time: time as UTCTimestamp,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
}
export default function CandleChart({
  rows,
  phases = [],
}: {
  rows: CandleResponse[];
  phases?: Phase[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const series =
    useRef<
      ReturnType<ReturnType<typeof createChart>["addCandlestickSeries"]>
    >();
  const chartRef = useRef<ReturnType<typeof createChart>>();
  const previousRange = useRef<string>("");
  useEffect(() => {
    if (!container.current) return;
    const chart = createChart(container.current, {
      autoSize: true,
      height: 400,
      timeScale: { timeVisible: true, secondsVisible: false },
      localization: { locale: "zh-CN" },
    });
    chartRef.current = chart;
    series.current = chart.addCandlestickSeries({
      upColor: "#16a085",
      downColor: "#df5263",
      borderVisible: false,
      wickUpColor: "#16a085",
      wickDownColor: "#df5263",
    });
    return () => {
      chart.remove();
      series.current = undefined;
      chartRef.current = undefined;
      previousRange.current = "";
    };
  }, []);
  useEffect(() => {
    const data = candleSeries(rows);
    series.current?.setData(data);
    const markers = new Map<number, string>();
    for (const phase of phases) {
      const start = Date.parse(phase.start_time) / 1000;
      if (
        !Number.isFinite(start) ||
        !data.length ||
        start < Number(data[0].time) ||
        start > Number(data[data.length - 1].time)
      )
        continue;
      const candle = data.find((row) => Number(row.time) >= start);
      if (candle) markers.set(Number(candle.time), phase.stage);
    }
    series.current?.setMarkers(
      [...markers]
        .sort(([a], [b]) => a - b)
        .map(([time, text]) => ({
          time: time as UTCTimestamp,
          position: "aboveBar" as const,
          shape: "arrowDown" as const,
          color: "#1677ff",
          text,
        })),
    );
    const key = `${rows[0]?.symbol}-${rows[0]?.interval}`;
    if (previousRange.current !== key) {
      chartRef.current?.timeScale().fitContent();
      previousRange.current = key;
    }
  }, [rows, phases]);
  return (
    <>
      <div ref={container} role="img" aria-label="市场 OHLC K 线图" />
      <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
        TradingView Lightweight Charts™ · Copyright (с) 2024 TradingView, Inc.
      </a>
    </>
  );
}
