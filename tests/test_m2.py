"""Deterministic M2 tests; no billable model calls or production services."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from backend.analysis.models import AnalysisRequest
from backend.analysis.service import FeatureExtractionService
from backend.api.auth import current_user
from backend.api.dependencies import get_db
from backend.api.main import create_app
from backend.api.routes.m2 import CaseRequest, get_runtime
from backend.cases.representation import embedding_text, feature_snapshot, valid_vector
from backend.cases.service import CaseService, EmbeddingService
from backend.config.settings import Settings
from backend.features.calculator import calculate_features
from backend.features.runtime import M2Runtime
from backend.opportunities.service import OpportunityFinder

NOW = datetime(2026, 10, 30, 12, 30, tzinfo=timezone.utc)
SYMBOL = "BTC-USDT-SWAP"


def sources():
    return dict(
        candles=[
            dict(
                time=NOW - timedelta(minutes=i),
                open=100,
                high=110,
                low=90,
                close=105 - i,
                volume=20,
            )
            for i in (2, 1, 0)
        ],
        trades=dict(
            time=NOW + timedelta(seconds=59),
            trade_count=5,
            buy_notional=300,
            sell_notional=100,
        ),
        cvd=1000,
        oi=dict(time=NOW + timedelta(seconds=59), open_interest=50),
        previous_oi=dict(open_interest=40),
        funding=dict(time=NOW + timedelta(seconds=59), funding_rate=0.001),
        previous_funding=dict(funding_rate=0.0008),
        book=dict(
            time=NOW + timedelta(seconds=59), bids="[[99, 3]]", asks="[[101, 1]]"
        ),
        liquidations=dict(
            time=NOW + timedelta(seconds=59),
            liq_count=2,
            long_notional=100,
            short_notional=200,
        ),
    )


def feature():
    return calculate_features(SYMBOL, NOW, sources(), 0.01)


def test_seven_categories_contract_units_and_quality():
    result = feature()
    assert result.price_change_pct == pytest.approx(5)
    assert result.amplitude_pct == 20
    assert result.volatility > 0
    assert result.volume_usd == 4 and result.delta_usd == 2
    assert result.cvd == 10 and result.buy_sell_ratio == 3
    assert result.avg_trade_size_usd == 0.8
    assert result.oi_usd == 52.5 and result.oi_delta == 10
    assert result.oi_change_pct == 25 and result.oi_volume_ratio == 2.5
    assert result.oi_direction == "long_build"
    assert result.funding_trend == pytest.approx(0.0002)
    assert result.obi == pytest.approx((2.97 - 1.01) / (2.97 + 1.01))
    assert result.spread_bps == 200
    assert result.long_liq_usd == 1 and result.short_liq_usd == 2
    assert result.liquidation_intensity == 0.75
    assert result.liquidation_long_short_ratio == 0.5
    assert result.source_flags == 63 and result.coverage == pytest.approx(6 / 7)
    assert result.quality > 0.9
    assert not result.is_final


def test_missing_stale_zero_and_candle_gap():
    data = sources()
    data["candles"].pop(1)
    data["trades"]["sell_notional"] = 0
    data["previous_oi"]["open_interest"] = 0
    data["funding"]["time"] = NOW - timedelta(hours=8)
    result = calculate_features(SYMBOL, NOW, data, 0.01)
    assert result.volatility is None and result.buy_sell_ratio is None
    assert result.oi_change_pct is None and result.quality < 0.9
    result = calculate_features(SYMBOL, NOW, dict(candles=[]), 0.01)
    assert result.coverage == 0 and result.price_close is None
    assert result.liq_count is None and result.cvd is None
    with pytest.raises(ValueError):
        calculate_features(SYMBOL, NOW, sources(), 0)


@pytest.mark.parametrize(
    "change,move,expected",
    [
        (10, 5, "long_build"),
        (10, -5, "short_build"),
        (-10, 5, "short_unwind"),
        (-10, -5, "long_unwind"),
        (0, 5, "neutral"),
    ],
)
def test_oi_directions(change, move, expected):
    data = sources()
    data["previous_oi"]["open_interest"] = 50 - change
    data["candles"][-1]["close"] = 100 + move
    assert calculate_features(SYMBOL, NOW, data, 1).oi_direction == expected


def test_shared_representation_and_vectors():
    snapshot = feature_snapshot([feature().model_dump()])
    assert snapshot["metrics"]["price_change_pct"] == 5
    assert "symbol" not in embedding_text(snapshot)
    assert len(valid_vector([1] * 1536)) == 1536
    for invalid in ([1, 2], [0] * 1536, [float("nan")] * 1536):
        with pytest.raises(ValueError):
            valid_vector(invalid)


def analysis_output():
    return dict(
        summary="Accumulation with uncertain breakout",
        stages=[
            dict(
                stage="accumulation",
                start_time=NOW,
                end_time=NOW + timedelta(minutes=1),
                confidence=0.8,
                evidence="OI rising",
            )
        ],
        turning_points=[],
    )


def request():
    return AnalysisRequest(
        symbol=SYMBOL, start_time=NOW, end_time=NOW + timedelta(minutes=1)
    )


def pool():
    return SimpleNamespace(
        fetch=AsyncMock(return_value=[feature().model_dump()]),
        execute=AsyncMock(),
        fetchval=AsyncMock(return_value=uuid4()),
    )


async def test_analysis_persists_result_and_snapshot():
    db = pool()
    chain = SimpleNamespace(ainvoke=AsyncMock(return_value=analysis_output()))
    service = FeatureExtractionService(db, Settings(_env_file=None), chain)
    await service._run(uuid4(), request())
    query, _, payload, _owner = db.execute.call_args.args
    assert "status='completed'" in query
    assert (
        json.loads(payload)["feature_snapshot"]["representation"] == "market-window-v1"
    )
    assert chain.ainvoke.await_count == 1


@pytest.mark.parametrize("failure", ["timeline", "model", "missing", "timeout"])
async def test_analysis_failure_is_persisted_and_sanitized(failure):
    db = pool()
    output = analysis_output()
    chain = SimpleNamespace(ainvoke=AsyncMock(return_value=output))
    if failure == "timeline":
        output["stages"][0]["start_time"] = NOW - timedelta(days=1)
    elif failure == "model":
        chain.ainvoke.side_effect = RuntimeError("secret key")
    elif failure == "missing":
        db.fetch.return_value = []
    else:
        chain.ainvoke.side_effect = TimeoutError("secret")
    service = FeatureExtractionService(db, Settings(_env_file=None), chain)
    await service._run(uuid4(), request())
    assert "status='failed'" in db.execute.call_args.args[0]
    assert "secret" not in db.execute.call_args.args[2]


async def test_analysis_cancelled_work_and_admission_limits():
    db = pool()
    db.fetch.side_effect = asyncio.CancelledError()
    service = FeatureExtractionService(db, Settings(_env_file=None), object())
    with pytest.raises(asyncio.CancelledError):
        await service._run(uuid4(), request())
    assert "status='failed'" in db.execute.call_args.args[0]
    service.accepting = False
    with pytest.raises(OverflowError):
        await service.create(request())
    service = FeatureExtractionService(db, Settings(_env_file=None))
    with pytest.raises(RuntimeError):
        await service.create(request())


async def test_embedding_sdk_dimensions_and_validation():
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[SimpleNamespace(embedding=[1] * 1536)]
                )
            )
        )
    )
    service = EmbeddingService(Settings(_env_file=None), client)
    assert len(await service.embed(feature_snapshot([feature().model_dump()]))) == 1536
    assert client.embeddings.create.call_args.kwargs["dimensions"] == 1536


class Connection:
    def __init__(self):
        self.fetchrow = AsyncMock(return_value={"id": uuid4()})
        self.execute = AsyncMock()
        self.fetchval = AsyncMock(return_value=True)

    @asynccontextmanager
    async def transaction(self, **kwargs):
        yield


class Pool:
    def __init__(self, db):
        self.db = db

    @asynccontextmanager
    async def acquire(self):
        yield self.db


async def test_case_save_atomic_vector_and_completed_task_requirement():
    db = Connection()
    store = Pool(db)
    store.fetchrow = AsyncMock(
        return_value=dict(
            symbol=SYMBOL,
            result=dict(
                **json.loads(json.dumps(analysis_output(), default=str)),
                feature_snapshot=feature_snapshot([feature().model_dump()]),
            ),
        )
    )
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=np.ones(1536)))
    service = CaseService(store, embeddings, "test-model")
    await service.save(CaseRequest(task_id=uuid4(), title="Test"))
    assert "INSERT INTO feature_cases" in db.fetchrow.call_args.args[0]
    assert "::text::vector" in db.execute.call_args.args[0]
    store.fetchrow.return_value = None
    with pytest.raises(ValueError):
        await service.save(CaseRequest(task_id=uuid4(), title="Test"))


async def test_search_filters_model_representation_container_and_threshold():
    db = pool()
    db.fetch.return_value = []
    service = CaseService(db, None, "test-model")
    container = uuid4()
    assert await service.search(np.ones(1536), 5, 0.8, container) == []
    sql, *args = db.fetch.call_args.args
    assert "<=>" in sql and "v.model=$2" in sql
    assert args[1:] == ["test-model", "market-window-v1", container, 0.8, 5]


async def test_opportunities_freshness_matching_and_empirical_probability():
    db = pool()
    db.fetch.return_value = [
        dict(feature().model_dump(), time=NOW - timedelta(minutes=i))
        for i in reversed(range(60))
    ]
    cases = SimpleNamespace(
        embeddings=SimpleNamespace(embed=AsyncMock(return_value=np.ones(1536))),
        search=AsyncMock(
            return_value=[
                dict(
                    id=uuid4(),
                    symbol=SYMBOL,
                    title="A",
                    similarity=0.9,
                    outcome="success",
                    analysis=analysis_output(),
                ),
                dict(
                    id=uuid4(),
                    symbol=SYMBOL,
                    title="B",
                    similarity=0.8,
                    outcome="failure",
                    analysis=analysis_output(),
                ),
                dict(
                    id=uuid4(),
                    symbol=SYMBOL,
                    title="C",
                    similarity=0.8,
                    outcome=None,
                    analysis=analysis_output(),
                ),
            ]
        ),
    )
    finder = OpportunityFinder(db, cases, Settings(_env_file=None))
    result = await finder.scan_symbol(SYMBOL, NOW + timedelta(minutes=1))
    assert result["stage"] == "accumulation"
    assert result["confidence"] == pytest.approx(0.72)
    assert result["historical_success_rate"] == 0.5 and result["labeled_cases"] == 2
    db.fetch.return_value = []
    assert await finder.scan_symbol(SYMBOL, NOW) is None
    assert "DELETE" in db.execute.call_args.args[0]


async def test_scheduler_job_registration_and_shutdown():
    runtime = M2Runtime(Pool(Connection()), None, Settings(_env_file=None))
    runtime.start()
    jobs = {job.id: job for job in runtime.scheduler.get_jobs()}
    assert set(jobs) == {"features", "opportunities"}
    assert jobs["features"].max_instances == 1
    assert "*/5" in str(jobs["opportunities"].trigger)
    await runtime.close()


@pytest.fixture
def api():
    collector = REGISTRY._names_to_collectors.get("http_requests_inprogress")
    if collector is not None:
        REGISTRY.unregister(collector)
    app = create_app(Settings(_env_file=None, m2_scheduler_enabled=False))
    app.dependency_overrides[current_user] = lambda: {"sub": "test"}
    db = pool()
    db.fetchrow = AsyncMock(return_value=None)
    runtime = SimpleNamespace(
        analysis=SimpleNamespace(
            create=AsyncMock(side_effect=RuntimeError("AI service is not configured"))
        ),
        embeddings=SimpleNamespace(configured=lambda: False),
    )

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield TestClient(app), db, runtime
    collector = REGISTRY._names_to_collectors.get("http_requests_inprogress")
    if collector is not None:
        REGISTRY.unregister(collector)


def test_features_api_and_openapi(api):
    client, db, _ = api
    response = client.get(f"/api/features/{SYMBOL}")
    assert response.status_code == 200, response.text
    assert response.json()[0]["coverage"] == pytest.approx(6 / 7)
    for query in (
        "limit=0",
        "min_quality=2",
        "start_time=2026-11-01T00:00:00",
        "start_time=2026-11-02T00:00:00Z&end_time=2026-11-01T00:00:00Z",
    ):
        assert client.get(f"/api/features/{SYMBOL}?{query}").status_code == 422
    schema = client.get("/openapi.json").json()
    assert "/api/analysis/create" in schema["paths"]
    assert "/api/cases/search" in schema["paths"]
    assert "AnalysisResult" in schema["components"]["schemas"]


def test_task_case_search_and_container_api_errors(api):
    client, _, _ = api
    assert (
        client.post(
            "/api/analysis/create", json=request().model_dump(mode="json")
        ).status_code
        == 503
    )
    assert client.get(f"/api/analysis/{uuid4()}").status_code == 404
    assert client.get("/api/analysis/invalid").status_code == 422
    assert (
        client.post(
            "/api/cases", json={"task_id": str(uuid4()), "title": "A"}
        ).status_code
        == 503
    )
    assert (
        client.get(
            f"/api/cases/search?symbol={SYMBOL}&start_time=2026-10-30T12:30:00Z"
            "&end_time=2026-10-30T12:31:00Z"
        ).status_code
        == 503
    )
    assert client.post("/api/containers", json={"name": ""}).status_code == 422
    assert client.delete(f"/api/containers/{uuid4()}").status_code == 404
    response = client.options(
        "/api/analysis/create",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200


def test_opportunities_api_decodes_matches(api):
    client, db, _ = api
    db.fetch.return_value = [
        dict(
            symbol=SYMBOL,
            observed_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
            stage="unknown",
            similarity=0.8,
            confidence=0.4,
            historical_success_rate=None,
            labeled_cases=0,
            matches="[]",
        )
    ]
    response = client.get("/api/opportunities")
    assert response.status_code == 200, response.text
    assert response.json()[0]["matches"] == []
    assert "expires_at > now()" in db.fetch.call_args.args[0]


def test_analysis_case_container_and_search_success_paths(api):
    client, db, runtime = api
    task_id = uuid4()
    task = dict(
        id=task_id,
        symbol=SYMBOL,
        start_time=NOW,
        end_time=NOW + timedelta(minutes=1),
        status="pending",
        result=None,
        error=None,
        created_at=NOW,
        updated_at=NOW,
    )
    runtime.analysis.create.side_effect = None
    runtime.analysis.create.return_value = task
    response = client.post(
        "/api/analysis/create", json=request().model_dump(mode="json")
    )
    assert response.status_code == 202, response.text
    db.fetchrow.return_value = dict(
        task, status="completed", result=json.dumps(analysis_output(), default=str)
    )
    assert (
        client.get(f"/api/analysis/{task_id}").json()["result"]["stages"][0]["stage"]
        == "accumulation"
    )
    runtime.embeddings = SimpleNamespace(
        configured=lambda: True, embed=AsyncMock(return_value=np.ones(1536))
    )
    runtime.cases = SimpleNamespace(
        save=AsyncMock(
            return_value=dict(
                id=uuid4(),
                task_id=task_id,
                symbol=SYMBOL,
                title="A",
                container_id=None,
                outcome=None,
                created_at=NOW,
            )
        ),
        search=AsyncMock(return_value=[]),
    )
    assert (
        client.post(
            "/api/cases", json={"task_id": str(task_id), "title": "A"}
        ).status_code
        == 201
    )
    response = client.get(
        f"/api/cases/search?symbol={SYMBOL}&start_time=2026-10-30T12:30:00Z"
        "&end_time=2026-10-30T12:31:00Z"
    )
    assert response.status_code == 200, response.text
    runtime.cases.search.assert_awaited_once()
    db.fetchrow.return_value = dict(
        id=uuid4(), name="Test", description="", created_at=NOW
    )
    assert client.post("/api/containers", json={"name": "Test"}).status_code == 201
    assert (
        client.put(f"/api/containers/{uuid4()}", json={"name": "Test"}).status_code
        == 200
    )
    assert client.delete(f"/api/containers/{uuid4()}").status_code == 204
    db.fetchrow.return_value = None
    assert client.post("/api/containers", json={"name": "Test"}).status_code == 409


def test_error_quality_logs_reduce_score():
    data = sources()
    normal = calculate_features(SYMBOL, NOW, data, 0.01)
    anomalous = calculate_features(SYMBOL, NOW, dict(data, has_anomalies=True), 0.01)
    assert normal.quality - anomalous.quality == pytest.approx(0.2)


def test_scheduler_requires_pool_capacity():
    with pytest.raises(ValueError, match="db_pool_size >= 3"):
        Settings(_env_file=None, db_pool_size=1, db_pool_min_size=1)


async def test_real_langchain_and_openai_sdk_with_mock_transport():
    import httpx
    from langchain_openai import ChatOpenAI
    from openai import AsyncOpenAI

    from backend.analysis.models import AnalysisResult
    from backend.analysis.service import PROMPT

    calls = []

    def respond(http_request):
        body = json.loads(http_request.content)
        calls.append((http_request.url.path, body))
        if http_request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json=dict(
                    object="list",
                    model="text-embedding-3-small",
                    data=[dict(object="embedding", index=0, embedding=[1.0] * 1536)],
                    usage=dict(prompt_tokens=1, total_tokens=1),
                ),
            )
        assert body["response_format"]["type"] == "json_schema"
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json=dict(
                id="chatcmpl-test",
                object="chat.completion",
                created=1,
                model="gpt-4o-mini",
                choices=[
                    dict(
                        index=0,
                        finish_reason="stop",
                        message=dict(
                            role="assistant",
                            content=json.dumps(analysis_output(), default=str),
                        ),
                    )
                ],
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        model = ChatOpenAI(
            api_key="test-not-real",
            model="gpt-4o-mini",
            http_async_client=http_client,
            max_retries=0,
        )
        chain = PROMPT | model.with_structured_output(AnalysisResult)
        db = pool()
        service = FeatureExtractionService(db, Settings(_env_file=None), chain)
        await service._run(uuid4(), request())
        assert "status='completed'" in db.execute.call_args.args[0]
        sdk = AsyncOpenAI(
            api_key="test-not-real", http_client=http_client, max_retries=0
        )
        embeddings = EmbeddingService(Settings(_env_file=None), sdk)
        assert (
            len(await embeddings.embed(feature_snapshot([feature().model_dump()])))
            == 1536
        )
        assert calls[-1][1]["dimensions"] == 1536
