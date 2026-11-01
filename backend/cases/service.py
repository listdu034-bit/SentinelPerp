"""OpenAI embeddings and atomic pgvector case storage / cosine matching."""

import json
from uuid import uuid4

from openai import AsyncOpenAI
from pgvector import Vector

from backend.cases.representation import (
    DIMENSIONS,
    REPRESENTATION,
    embedding_text,
    valid_vector,
)


class EmbeddingService:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def configured(self):
        return self.client is not None or bool(
            self.settings.openai_api_key.get_secret_value()
        )

    async def embed(self, snapshot):
        if not self.configured():
            raise RuntimeError("Embeddings service is not configured")
        if self.client is None:
            self.client = AsyncOpenAI(
                api_key=self.settings.openai_api_key.get_secret_value(),
                timeout=self.settings.ai_timeout_seconds,
                max_retries=2,
            )
        response = await self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=embedding_text(snapshot),
            dimensions=DIMENSIONS,
        )
        return valid_vector(response.data[0].embedding)

    async def close(self):
        if self.client is not None:
            await self.client.close()


class CaseService:
    def __init__(self, pool, embeddings, model):
        self.pool, self.embeddings, self.model = pool, embeddings, model

    async def save(self, request):
        task = await self.pool.fetchrow(
            "SELECT * FROM feature_analysis_tasks WHERE id=$1 AND status='completed'",
            request.task_id,
        )
        if not task:
            raise ValueError("Completed analysis task not found")
        analysis = task["result"]
        if isinstance(analysis, str):
            analysis = json.loads(analysis)
        snapshot = analysis.get("feature_snapshot")
        if not snapshot:
            raise ValueError("Analysis has no feature snapshot; create a new analysis")
        vector = await self.embeddings.embed(snapshot)
        case_id = uuid4()
        async with self.pool.acquire() as db:
            async with db.transaction():
                if request.container_id and not await db.fetchval(
                    "SELECT id FROM feature_containers WHERE id=$1 FOR KEY SHARE",
                    request.container_id,
                ):
                    raise ValueError("Container not found")
                row = await db.fetchrow(
                    "INSERT INTO "
                    "feature_cases(id,task_id,container_id,symbol,title,analysis,"
                    "feature_snapshot,outcome) "
                    "VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8) "
                    "RETURNING id,task_id,container_id,symbol,title,outcome,created_at",
                    case_id,
                    request.task_id,
                    request.container_id,
                    task["symbol"],
                    request.title,
                    json.dumps(analysis),
                    json.dumps(snapshot),
                    request.outcome,
                )
                # Text conversion works with M1 pools without
                # changing their type codecs.
                await db.execute(
                    "INSERT INTO "
                    "feature_vectors(case_id,embedding,model,representation) "
                    "VALUES($1,$2::text::vector,$3,$4)",
                    case_id,
                    Vector(vector).to_text(),
                    self.model,
                    REPRESENTATION,
                )
        return dict(row)

    async def search(self, vector, limit=10, min_similarity=0.7, container_id=None):
        vector = valid_vector(vector)
        rows = await self.pool.fetch(
            "SELECT c.id,c.symbol,c.title,c.container_id,c.analysis,c.outcome, "
            "1-(v.embedding <=> $1::text::vector) AS similarity "
            "FROM feature_vectors v JOIN feature_cases c ON c.id=v.case_id "
            "WHERE v.model=$2 AND v.representation=$3 "
            "AND ($4::uuid IS NULL OR c.container_id=$4) "
            "AND 1-(v.embedding <=> $1::text::vector) >= $5 "
            "ORDER BY v.embedding <=> $1::text::vector, c.id LIMIT $6",
            Vector(vector).to_text(),
            self.model,
            REPRESENTATION,
            container_id,
            min_similarity,
            limit,
        )
        results = []
        for row in rows:
            item = dict(row)
            if isinstance(item["analysis"], str):
                item["analysis"] = json.loads(item["analysis"])
            item["similarity"] = min(1.0, max(-1.0, item["similarity"]))
            results.append(item)
        return results
