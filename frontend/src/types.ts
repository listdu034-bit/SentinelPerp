// Mirrors backend/api/schemas.py and fastapi-pagination response envelopes.
export interface EventResponse {
  time: string;
  symbol: string;
  exchange: string;
}
export interface InstrumentResponse extends EventResponse {}
export interface CandleResponse extends EventResponse {
  interval: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
export interface TradeResponse extends EventResponse {
  trade_id: string;
  trade_count: number;
  price: number;
  quantity: number;
  side: "buy" | "sell";
  receipt_timestamp: string;
}
export interface FundingRateResponse extends EventResponse {
  funding_rate: number;
  next_funding_time: string | null;
}
export interface OpenInterestResponse extends EventResponse {
  open_interest: number;
}
export interface LiquidationResponse extends EventResponse {
  liquidation_id: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
}
export interface QualityLogResponse extends EventResponse {
  event_id: string;
  data_type: string;
  issue_type: string;
  severity: "warning" | "error";
  details: Record<string, unknown>;
}
export interface SystemStatusResponse {
  time: string;
  collection: Record<string, { count: number; latest_time: string | null }>;
  redis: { keys?: number; used_memory?: number };
  database: { table_bytes?: Record<string, number>; connections?: number };
  quality_score: number;
  quality_window: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}
export interface QualitySummary {
  by_symbol: Record<string, number>;
  by_issue_type: Record<string, number>;
}
export interface MarketRow {
  symbol: string;
  change_percent: number | null;
  ranking: "gainer" | "loser";
}
export interface MarketSnapshot {
  type: "market";
  time: string;
  gainers: MarketRow[];
  losers: MarketRow[];
  status: SystemStatusResponse;
}
export type Interval = "1m" | "5m" | "1h" | "1d";
