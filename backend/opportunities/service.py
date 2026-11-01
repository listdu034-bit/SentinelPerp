"""Match fresh windows against historical cases; scores are empirical, not forecasts."""

import json
from datetime import datetime, timedelta, timezone

from backend.cases.representation import feature_snapshot


class OpportunityFinder:
    def __init__(self, pool, cases, settings):
        self.pool, self.cases, self.settings = pool, cases, settings

    async def scan_symbol(self, symbol, now=None):
        now = now or datetime.now(timezone.utc)
        rows = await self.pool.fetch(
            "SELECT * FROM market_features_1m WHERE symbol=$1 AND time >= $2 "
            "AND time < $3 ORDER BY time",
            symbol,
            now - timedelta(hours=1),
            now,
        )
        if (
            not rows
            or rows[-1]["time"] < now - timedelta(minutes=3)
            or sum(float(r["quality"]) for r in rows) / len(rows)
            < self.settings.opportunity_min_quality
            or len(rows) < 45
        ):
            await self.pool.execute("DELETE FROM opportunities WHERE symbol=$1", symbol)
            return None
        vector = await self.cases.embeddings.embed(feature_snapshot(rows))
        matches = await self.cases.search(
            vector, limit=10, min_similarity=self.settings.opportunity_min_similarity
        )
        if not matches:
            await self.pool.execute("DELETE FROM opportunities WHERE symbol=$1", symbol)
            return None
        # Most similar case provides the current stage hypothesis.
        stages = matches[0]["analysis"].get("stages", [])
        stage = stages[-1]["stage"] if stages else "unknown"
        confidence = matches[0]["similarity"] * (
            stages[-1]["confidence"] if stages else 0
        )
        labeled = [m for m in matches if m["outcome"] is not None]
        success = (
            sum(m["outcome"] == "success" for m in labeled) / len(labeled)
            if labeled
            else None
        )
        public_matches = [
            {k: m[k] for k in ("id", "symbol", "title", "similarity", "outcome")}
            for m in matches
        ]
        result = dict(
            symbol=symbol,
            observed_at=now,
            expires_at=now + timedelta(minutes=10),
            stage=stage,
            similarity=matches[0]["similarity"],
            confidence=confidence,
            historical_success_rate=success,
            labeled_cases=len(labeled),
            matches=public_matches,
        )
        await self.pool.execute(
            "INSERT INTO "
            "opportunities(symbol,observed_at,expires_at,stage,similarity,confidence,"
            "historical_success_rate,labeled_cases,matches) "
            "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb) "
            "ON CONFLICT(symbol) DO UPDATE SET observed_at=EXCLUDED.observed_at,"
            "expires_at=EXCLUDED.expires_at,stage=EXCLUDED.stage,similarity=EXCLUDED.similarity,"
            "confidence=EXCLUDED.confidence,historical_success_rate=EXCLUDED.historical_success_rate,"
            "labeled_cases=EXCLUDED.labeled_cases,matches=EXCLUDED.matches",
            *[
                result[k]
                for k in (
                    "symbol",
                    "observed_at",
                    "expires_at",
                    "stage",
                    "similarity",
                    "confidence",
                    "historical_success_rate",
                    "labeled_cases",
                )
            ],
            json.dumps(public_matches, default=str),
        )
        return result
