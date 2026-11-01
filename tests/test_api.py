"""Behavioral API tests independent of external services."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.websockets import WebSocketDisconnect

from backend.api.dependencies import get_db, get_redis
from backend.api.limiter import limiter
from backend.api.main import create_app
from backend.api.routes.status import system_status
from backend.api.websocket import broadcast, heartbeat
from backend.config.settings import Settings

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
TRADE = dict(
    time=NOW,
    exchange="OKX",
    symbol="BTC-USDT-SWAP",
    receipt_timestamp=NOW,
    trade_id="10",
    trade_count=1,
    price=Decimal("123.25"),
    quantity=Decimal("2"),
    side="buy",
)


class Database:
    def __init__(self):
        self.calls = []
        self.rows = [TRADE]

    @asynccontextmanager
    async def transaction(self, **kwargs):
        yield

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return 1

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return self.rows


@pytest.fixture(autouse=True)
def clean_inprogress_metric():
    """Instrumentator uses a process-global in-progress Gauge."""
    yield
    collector = REGISTRY._names_to_collectors.get("http_requests_inprogress")
    if collector is not None:
        REGISTRY.unregister(collector)


@pytest.fixture
def api():
    limiter.reset()
    app = create_app(Settings(_env_file=None))
    db = Database()
    redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock())

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_redis] = lambda: redis
    app.state.catalog_lock = asyncio.Lock()
    app.state.discovery = SimpleNamespace(
        discover_instruments=AsyncMock(return_value={"BTC-USDT-SWAP", "ETH-USDT-SWAP"})
    )
    return app, db, redis


def test_trade_pagination_time_filters_and_serialization(api):
    app, db, _ = api
    client = TestClient(app)
    response = client.get(
        "/api/v1/trades/BTC-USDT-SWAP",
        params={
            "page": 2,
            "limit": 25,
            "start_time": "2026-10-31T00:00:00Z",
            "end_time": "2026-11-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["page"], data["size"], data["total"]) == (2, 25, 1)
    assert data["items"][0]["price"] == 123.25
    assert data["items"][0]["time"].endswith("Z")
    sql, args = db.calls[-1]
    assert "ORDER BY time DESC" in sql and "LIMIT 25 OFFSET 25" in sql
    assert args[0] == "BTC-USDT-SWAP" and len(args) == 3
    assert args[1].tzinfo is not None


@pytest.mark.parametrize(
    "query",
    [
        "size=1001",
        "limit=0",
        "page=0",
        "start_time=2026-11-01T00:00:00",
        "start_time=2026-11-02T00:00:00Z&end_time=2026-11-01T00:00:00Z",
    ],
)
def test_reject_invalid_ranges_and_pagination(api, query):
    response = TestClient(api[0]).get(f"/api/v1/trades/BTC-USDT-SWAP?{query}")
    assert response.status_code == 422
    assert "error" in response.json()


@pytest.mark.parametrize(
    "interval, table",
    [
        ("1m", "candles"),
        ("5m", "candles_5m"),
        ("1h", "candles_1h"),
        ("1d", "candles_1d"),
    ],
)
def test_candle_table_routing(api, interval, table):
    app, db, _ = api
    db.rows = [
        dict(
            time=NOW,
            symbol="BTC-USDT-SWAP",
            exchange="OKX",
            interval=interval,
            open=1,
            high=2,
            low=1,
            close=2,
            volume=5,
        )
    ]
    response = TestClient(app).get(f"/api/v1/candles/BTC-USDT-SWAP?interval={interval}")
    assert response.status_code == 200, response.text
    assert f"FROM {table} WHERE" in db.calls[-1][0]
    assert response.json()["size"] == 50


@pytest.mark.parametrize(
    "resource, extra",
    [
        ("funding", {"funding_rate": "0.001"}),
        ("open-interest", {"open_interest": "100"}),
        (
            "liquidations",
            {"liquidation_id": "1", "side": "buy", "price": 10, "quantity": 2},
        ),
    ],
)
def test_other_histories(api, resource, extra):
    app, db, _ = api
    db.rows = [dict(time=NOW, symbol="BTC-USDT-SWAP", exchange="OKX", **extra)]
    response = TestClient(app).get(f"/api/v1/{resource}/BTC-USDT-SWAP")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


def test_quality_filters_and_summary(api):
    app, db, _ = api
    db.rows = [
        dict(
            time=NOW,
            symbol="BTC-USDT-SWAP",
            data_type="trade",
            event_id="00000000-0000-0000-0000-000000000001",
            issue_type="gap",
            severity="error",
            details='{"missing":2}',
        )
    ]
    client = TestClient(app)
    response = client.get(
        "/api/v1/quality/logs?symbol=BTC-USDT-SWAP&issue_type=gap&severity=error"
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["details"] == {"missing": 2}
    assert db.calls[-1][1] == ("BTC-USDT-SWAP", "gap", "error")
    db.rows = [
        dict(symbol="BTC-USDT-SWAP", issue_type="gap", count=3),
        dict(symbol="ETH-USDT-SWAP", issue_type="gap", count=1),
    ]
    assert client.get("/api/v1/quality/summary").json() == {
        "by_symbol": {"BTC-USDT-SWAP": 3, "ETH-USDT-SWAP": 1},
        "by_issue_type": {"gap": 4},
    }


def test_instrument_search_cache(api):
    app, _, redis = api
    client = TestClient(app)
    response = client.get("/api/v1/instruments?symbol=btc")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    cached = redis.set.call_args.args[1]
    redis.get.return_value = cached
    assert client.get("/api/v1/instruments").json()["total"] == 2
    app.state.discovery.discover_instruments.assert_awaited_once()


def test_docs_metrics_cors_health_rate_limit(api):
    client = TestClient(api[0])
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    response = client.options(
        "/api/v1/instruments",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    for _ in range(101):
        response = client.get("/health")
    assert response.status_code == 429


def test_readiness_and_dependency_errors(api):
    app, _, _ = api
    redis = SimpleNamespace(ping=AsyncMock(return_value=True))
    app.state.redis = SimpleNamespace(connection=lambda: redis)
    app.state.database = SimpleNamespace(
        pool=SimpleNamespace(fetchval=AsyncMock(return_value=1))
    )
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health/detailed").status_code == 200
    redis.ping.side_effect = RedisConnectionError("secret connection string")
    response = client.get("/health/detailed")
    assert response.status_code == 503 and response.json()["redis"] is False

    async def failing_db():
        raise RedisConnectionError("secret connection string")
        yield

    app.dependency_overrides[get_db] = failing_db
    response = client.get("/api/v1/trades/BTC-USDT-SWAP")
    assert response.status_code == 503 and "secret" not in response.text


async def test_status_cache_and_score():
    db = SimpleNamespace(
        fetchrow=AsyncMock(return_value={"count": 100, "latest_time": NOW}),
        fetchval=AsyncMock(side_effect=[100] * 7 + [2, 3, 100]),
    )
    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(),
        info=AsyncMock(return_value={"used_memory": 1024}),
        dbsize=AsyncMock(return_value=5),
    )
    result = await system_status(db, redis)
    assert result.quality_score == 97 and result.database["connections"] == 2
    redis.get.return_value = result.model_dump_json()
    await system_status(db, redis)
    assert db.fetchrow.await_count == 7


class PubSub:
    def __init__(self):
        self.closed = False
        self.subscribe = AsyncMock()
        self.get_message = AsyncMock(
            side_effect=[{"type": "message", "data": json.dumps(TRADE, default=str)}]
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


def test_websocket_multi_symbol_and_cleanup(api):
    app, _, _ = api
    pubsub = PubSub()

    # Block after one event until the client disconnects and the task is cancelled.
    async def message(**kwargs):
        if not getattr(pubsub, "sent", False):
            pubsub.sent = True
            return {"type": "message", "data": json.dumps(TRADE, default=str)}
        await asyncio.Event().wait()

    pubsub.get_message.side_effect = message
    app.state.redis = SimpleNamespace(
        connection=lambda: SimpleNamespace(pubsub=lambda: pubsub)
    )
    with TestClient(app).websocket_connect(
        "/ws/trades/BTC-USDT-SWAP,ETH-USDT-SWAP"
    ) as ws:
        assert ws.receive_json()["type"] == "subscribed"
        assert ws.receive_json()["data"]["trade_id"] == "10"
    assert pubsub.closed
    assert pubsub.subscribe.call_args.args == (
        "events:trade:BTC-USDT-SWAP",
        "events:trade:ETH-USDT-SWAP",
    )


def test_websocket_reject_invalid_symbol_and_origin(api):
    for path, headers in [
        ("/ws/trades/INVALID", {}),
        ("/ws/market", {"origin": "https://untrusted.example"}),
    ]:
        with pytest.raises(WebSocketDisconnect) as error:
            with TestClient(api[0]).websocket_connect(path, headers=headers):
                pass
        assert error.value.code == 1008


async def test_heartbeat_timeout(monkeypatch):
    async def sleep(_):
        pass

    monkeypatch.setattr("backend.api.websocket.asyncio.sleep", sleep)
    ws = SimpleNamespace(send_json=AsyncMock())
    pong = SimpleNamespace(clear=lambda: None, wait=AsyncMock(side_effect=TimeoutError))
    with pytest.raises(TimeoutError):
        await heartbeat(ws, pong)
    ws.send_json.assert_awaited_once_with({"type": "ping"})


async def test_redis_resubscription(monkeypatch):
    async def sleep(_):
        pass

    monkeypatch.setattr("backend.api.websocket.asyncio.sleep", sleep)
    first, second = PubSub(), PubSub()
    first.get_message.side_effect = RedisConnectionError()
    second.get_message.side_effect = asyncio.CancelledError()
    redis = SimpleNamespace(pubsub=lambda: next(subscriptions))
    subscriptions = iter([first, second])
    ws = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(redis=SimpleNamespace(connection=lambda: redis))
        ),
        send_json=AsyncMock(),
    )
    with pytest.raises(asyncio.CancelledError):
        await broadcast(ws, ["events:trade:BTC-USDT-SWAP"])
    assert first.closed and second.closed
    assert {"type": "reconnecting"} in [c.args[0] for c in ws.send_json.call_args_list]
