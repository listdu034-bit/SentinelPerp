# SentinelPerp console API

## Run

Copy `.env.example` to `.env` and replace both password placeholders, then run:

```sh
docker compose up -d --build
curl http://localhost:8000/health/detailed
```

Swagger: <http://localhost:8000/docs>; ReDoc: <http://localhost:8000/redoc>.
Prometheus scrapes `GET /metrics` (request totals, latency, in-progress requests;
error rates can be calculated from status-labelled totals). `GET /health` is
liveness; `GET /health/detailed` returns 503 when either dependency is unhealthy.
Startup requires both dependencies; shutdown closes pools and subscriptions.
No authentication is enabled. Compose binds the API to loopback by default.

For local development set DATABASE_URL/REDIS_URL to host-accessible addresses:

```sh
pip install -r requirements-dev.txt
uvicorn backend.api.main:app --reload
```

`API_CORS_ORIGINS` is a JSON array, default `["http://localhost:3000"]`.
WebSocket browser origins use the same allowlist. No-Origin native clients are
supported. CORS permits GET plus preflight. HTTP requests are limited to 100 per
minute per client IP per API process using slowapi; excess requests return 429.
Only trust forwarded client IP headers from a configured, trusted reverse proxy.

## REST conventions

All histories return the fastapi-pagination envelope:

```json
{"items": [], "total": 0, "page": 1, "size": 50, "pages": 0}
```

`page` starts at 1. `size` defaults to 50 and is limited to 1000. Trades also
accept `limit` as a compatibility alias for `size`; when both are provided,
`limit` takes precedence. All values are validated. Filters use timezone-aware
ISO 8601 `start_time` (inclusive) and `end_time` (exclusive). Histories sort by
time descending. Empty histories return 200 with an empty page. Decimal market
values are JSON numbers and timestamps are ISO 8601. Quality logs originate
from OKX and expose that exchange default because storage has no exchange column.

```sh
curl 'http://localhost:8000/api/v1/instruments?symbol=BTC&page=1&size=50'
curl 'http://localhost:8000/api/v1/trades/BTC-USDT-SWAP?limit=100&start_time=2026-11-01T00:00:00Z'
curl 'http://localhost:8000/api/v1/candles/BTC-USDT-SWAP?interval=1h'
curl 'http://localhost:8000/api/v1/funding/BTC-USDT-SWAP'
curl 'http://localhost:8000/api/v1/open-interest/BTC-USDT-SWAP'
curl 'http://localhost:8000/api/v1/liquidations/BTC-USDT-SWAP?side=sell'
curl 'http://localhost:8000/api/v1/quality/logs?symbol=BTC-USDT-SWAP&severity=error&issue_type=gap'
curl 'http://localhost:8000/api/v1/quality/summary'
curl 'http://localhost:8000/api/v1/status'
```

`instruments` is the active OKX linear USDT perpetual catalog obtained through
existing CCXT discovery, cached in Redis for 300 seconds. Search is a
case-insensitive symbol substring. Funding, open interest and liquidations
support the same time filters and pagination as trades. Quality summary accepts
time filters and returns `by_symbol` and `by_issue_type` counts.

Candles accept `1m`, `5m`, `1h`, `1d`. `1m` uses raw candles; other intervals
use `candles_5m`, `candles_1h`, `candles_1d`. Raw retention is 7 days; aggregate
retention is 60 days. Continuous aggregates follow the existing refresh policy,
so the current unfinished or not-yet-refreshed bucket may be absent.

Status is cached for 30 seconds and reports exact retained row counts/latest
timestamps, Redis keys/memory, hypertable sizes including chunks, DB connection
count, and a 24h quality score. Score is
`100 * max(0, 1 - quality_incidents / max(1, trade_rows))`, an operational
indicator rather than an exchange completeness guarantee. Exact counts may be
costly at scale; caching limits repeated queries.

Validation errors return 422, dependency failures 503, unexpected failures 500.
Error bodies use `{"error":{"code":422,"message":"..."}}`; validation errors
also include field locations. Internal errors and connection credentials are
not exposed. slowapi's 429 response uses its native error message format.

## Live WebSockets

Trades: `/ws/trades/BTC-USDT-SWAP,ETH-USDT-SWAP` (maximum 50 distinct symbols).
After `subscribed`, messages are `{"type":"trade","data":{...}}`.
Redis channels are `events:trade:{symbol}`. The collector's Lua operation
publishes after the durability acknowledgement when it updates latest state.
All subscribers receive the same live event; stale events do not move latest
state backwards or publish. Pub/sub is live-only and does not replay history.

Market: `/ws/market` immediately sends a snapshot, then receives Redis
`market:overview` broadcasts every 30 seconds. Each snapshot includes up to 10
highest and 10 lowest observed 24h candle open-to-close percentage changes,
plus cached system status. Rankings describe available candles, not exchange
ticker 24h changes; short histories represent partial windows.

```js
const socket = new WebSocket('ws://localhost:8000/ws/trades/BTC-USDT-SWAP');
socket.onmessage = ({data}) => {
  const event = JSON.parse(data);
  if (event.type === 'ping') socket.send(JSON.stringify({type: 'pong'}));
  else console.log(event);
};
```

The server sends an application ping every 30 seconds and requires pong within
10 seconds. Client pings also receive pong. Slow sends time out after 10 seconds.
Disconnects cancel producers and release subscriptions. Redis outages emit
`reconnecting` and trigger resubscription; missed data must be fetched by REST.
Clients should reconnect with exponential backoff after transport disconnects,
resubscribe, and backfill REST from their last observed timestamp, deduplicating
by exchange/symbol/trade_id/time. The server cannot reconnect a closed client.

## Verification

```sh
pytest -q
ruff check backend tests
# Dedicated, initialized test services only:
TEST_DATABASE_URL=postgresql://... TEST_REDIS_URL=redis://... pytest -q
```

The opt-in API integration test inserts uniquely named test symbols, refreshes
candle aggregates, checks every resource and real Redis-to-WebSocket delivery,
and removes its raw data and API caches. Run only against dedicated test
services because aggregate refresh and shared API cache changes affect the
selected database/Redis instance.
