"""Opt-in M2 SQL integration against a dedicated disposable database only."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import numpy as np
import pytest

from backend.analysis.models import AnalysisRequest
from backend.analysis.service import FeatureExtractionService
from backend.api.routes.m2 import CaseRequest
from backend.cases.service import CaseService
from backend.config.settings import Settings
from backend.features.calculator import MarketFeatureCalculator
from backend.opportunities.service import OpportunityFinder

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_M2_DATABASE_URL"), reason="Requires dedicated M2 test database"
)


async def test_migration_calculation_analysis_cases_vectors_and_opportunities():
    pool = await asyncpg.create_pool(
        os.environ["TEST_M2_DATABASE_URL"], min_size=2, max_size=5
    )
    root = Path(__file__).resolve().parents[1]
    symbol = f"TEST{uuid4().hex.upper()}-USDT-SWAP"
    task_id, second_task_id, container = uuid4(), uuid4(), uuid4()
    cases_created = []
    try:
        async with pool.acquire() as db:
            await db.execute((root / "scripts/init_db.sql").read_text())
            await db.execute((root / "scripts/migrate_m2.sql").read_text())
            await db.execute((root / "scripts/migrate_m2.sql").read_text())
            assert (
                await db.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname='vector'"
                )
                == "0.8.0"
            )
            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            minute = now - timedelta(minutes=2)
            await db.execute(
                "INSERT INTO "
                "candles(time,symbol,receipt_timestamp,interval,ope"
                "n,high,low,close,volume) "
                "VALUES($1,$2,$1,'1m',100,110,90,105,20)",
                minute,
                symbol,
            )
            for index, (side, price, qty) in enumerate(
                [("buy", 100, 3), ("sell", 100, 1)]
            ):
                await db.execute(
                    "INSERT INTO "
                    "trades(time,symbol,receipt_timestamp,trade_id,pric"
                    "e,quantity,side) "
                    "VALUES($1,$2,$1,$3,$4,$5,$6)",
                    minute + timedelta(seconds=index + 1),
                    symbol,
                    str(index),
                    price,
                    qty,
                    side,
                )
                await db.execute(
                    "INSERT INTO "
                    "liquidations(time,symbol,receipt_timestamp,liquida"
                    "tion_id,price,quantity,side) "
                    "VALUES($1,$2,$1,$3,$4,$5,$6)",
                    minute + timedelta(seconds=index + 1),
                    symbol,
                    str(index),
                    price,
                    qty,
                    side,
                )
            for offset, interest in [(-1, 40), (1, 50)]:
                await db.execute(
                    "INSERT INTO "
                    "open_interest(time,symbol,receipt_timestamp,open_interest) "
                    "VALUES($1,$2,$1,$3)",
                    minute + timedelta(seconds=offset),
                    symbol,
                    interest,
                )
            await db.execute(
                "INSERT INTO "
                "funding_rates(time,symbol,receipt_timestamp,fundin"
                "g_rate) VALUES($1,$2,$1,.001)",
                minute,
                symbol,
            )
            await db.execute(
                "INSERT INTO "
                "orderbook_snapshots(time,symbol,receipt_timestamp,bids,asks) "
                "VALUES($1,$2,$1,'[[99,3]]','[[101,1]]')",
                minute,
                symbol,
            )
        calculator = MarketFeatureCalculator(pool)
        feature = await calculator.calculate(symbol, minute, 0.01)
        assert feature.delta_usd == 2 and feature.oi_delta == 10
        assert feature.long_liq_usd == 1 and feature.short_liq_usd == 3
        await calculator.calculate(symbol, minute, 0.01)
        assert (
            await pool.fetchval(
                "SELECT revision_count FROM market_features_1m WHERE symbol=$1", symbol
            )
            == 1
        )
        output = dict(
            summary="Test pattern",
            stages=[
                dict(
                    stage="accumulation",
                    start_time=minute,
                    end_time=minute + timedelta(minutes=1),
                    confidence=0.8,
                    evidence="Rising OI",
                )
            ],
            turning_points=[],
        )
        request = AnalysisRequest(
            symbol=symbol, start_time=minute, end_time=minute + timedelta(minutes=1)
        )
        chain = SimpleNamespace(ainvoke=AsyncMock(return_value=output))
        service = FeatureExtractionService(pool, Settings(_env_file=None), chain)
        task = await service.create(request)
        task_id = task["id"]
        await asyncio.gather(*list(service.jobs))
        row = await pool.fetchrow(
            "SELECT * FROM feature_analysis_tasks WHERE id=$1", task_id
        )
        assert row["status"] == "completed"
        assert "feature_snapshot" in json.loads(row["result"])
        # Failed or completed tasks cannot be claimed a second time.
        await service._run(task_id, request)
        assert chain.ainvoke.await_count == 1
        # Recovery can claim a crashed worker's expired lease.
        await pool.execute(
            "INSERT INTO "
            "feature_analysis_tasks(id,symbol,start_time,end_ti"
            "me,status,lease_expires_at) "
            "VALUES($1,$2,$3,$4,'running',now()-interval '1 minute')",
            second_task_id,
            symbol,
            minute,
            minute + timedelta(minutes=1),
        )
        await service._run(second_task_id, request)
        assert (
            await pool.fetchval(
                "SELECT status FROM feature_analysis_tasks WHERE id=$1", second_task_id
            )
            == "completed"
        )
        await pool.execute(
            "INSERT INTO feature_containers(id,name) VALUES($1,$2)",
            container,
            str(container),
        )
        embeddings = SimpleNamespace(embed=AsyncMock(return_value=np.ones(1536)))
        cases = CaseService(pool, embeddings, "test-embedding-model")
        first = await cases.save(
            CaseRequest(
                task_id=task_id,
                title="Identical",
                container_id=container,
                outcome="success",
            )
        )
        cases_created.append(first["id"])
        embeddings.embed.return_value = np.array([1.0, -1.0] * 768)
        second = await cases.save(
            CaseRequest(task_id=second_task_id, title="Orthogonal", outcome="failure")
        )
        cases_created.append(second["id"])
        matches = await cases.search(np.ones(1536), 10, 0.7, container)
        assert len(matches) == 1 and matches[0]["id"] == first["id"]
        assert matches[0]["similarity"] == pytest.approx(1)
        assert (
            await CaseService(pool, embeddings, "different-model").search(np.ones(1536))
            == []
        )
        await pool.execute("DELETE FROM feature_containers WHERE id=$1", container)
        assert (
            await pool.fetchval(
                "SELECT container_id FROM feature_cases WHERE id=$1", first["id"]
            )
            is None
        )
        # A fresh hour of feature rows drives the real scanner persistence path.
        await pool.execute(
            "INSERT INTO "
            "market_features_1m(time,symbol,price_change_pct,qu"
            "ality,coverage,age_seconds,source_flags) "
            "SELECT $1::timestamptz-i*interval '1 "
            "minute',$2,5,.95,.85,1,63 FROM generate_series(3,60) i",
            now,
            symbol,
        )
        embeddings.embed.return_value = np.ones(1536)
        finder = OpportunityFinder(pool, cases, Settings(_env_file=None))
        opportunity = await finder.scan_symbol(symbol, now)
        assert opportunity["historical_success_rate"] == 1
        assert opportunity["stage"] == "accumulation"
        assert (
            await pool.fetchval(
                "SELECT count(*) FROM opportunities WHERE symbol=$1", symbol
            )
            == 1
        )
        assert await finder.scan_symbol(symbol, now + timedelta(hours=2)) is None
        assert (
            await pool.fetchval(
                "SELECT count(*) FROM opportunities WHERE symbol=$1", symbol
            )
            == 0
        )
        await service.close()
        # Validate continuous aggregates materialize and preserve LAST(CVD).
        async with pool.acquire() as db:
            for view in [
                "market_features_5m",
                "market_features_1h",
                "market_features_1d",
            ]:
                await db.execute(
                    f"CALL refresh_continuous_aggregate('{view}', "
                    "$1::timestamptz, $2::timestamptz)",
                    now - timedelta(days=2),
                    now + timedelta(days=2),
                )
                assert (
                    await db.fetchval(
                        f"SELECT count(*) FROM {view} WHERE symbol=$1", symbol
                    )
                    > 0
                )
    finally:
        await pool.execute("DELETE FROM opportunities WHERE symbol=$1", symbol)
        await pool.execute("DELETE FROM feature_cases WHERE symbol=$1", symbol)
        assert (
            await pool.fetchval(
                "SELECT count(*) FROM feature_vectors WHERE case_id=ANY($1::uuid[])",
                cases_created,
            )
            == 0
        )
        await pool.execute("DELETE FROM feature_containers WHERE id=$1", container)
        await pool.execute("DELETE FROM feature_analysis_tasks WHERE symbol=$1", symbol)
        for table in [
            "market_features_1m",
            "candles",
            "trades",
            "liquidations",
            "open_interest",
            "funding_rates",
            "orderbook_snapshots",
        ]:
            await pool.execute(f"DELETE FROM {table} WHERE symbol=$1", symbol)
        await pool.close()
