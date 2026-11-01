"""M2 feature, analysis, case library and opportunity endpoints."""

import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.analysis.models import AnalysisRequest, AnalysisTask
from backend.analysis.service import decode_task
from backend.api.dependencies import Symbol, TimeRange, get_db
from backend.cases.representation import feature_snapshot
from backend.features.models import MarketFeature1Min

router = APIRouter()
DB = Annotated[object, Depends(get_db)]


def get_runtime(request: Request):
    runtime = getattr(request.app.state, "m2", None)
    if runtime is None:
        raise HTTPException(503, "M2 service unavailable")
    return runtime


Runtime = Annotated[object, Depends(get_runtime)]


class CaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    title: str = Field(min_length=1, max_length=200)
    container_id: UUID | None = None
    outcome: Literal["success", "failure"] | None = None


class CaseResponse(CaseRequest):
    id: UUID
    symbol: str
    created_at: AwareDatetime


class ContainerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field("", max_length=2000)


class ContainerResponse(ContainerRequest):
    id: UUID
    created_at: AwareDatetime


class CaseMatch(BaseModel):
    id: UUID
    symbol: str
    title: str
    container_id: UUID | None
    analysis: dict
    outcome: Literal["success", "failure"] | None
    similarity: float


class Opportunity(BaseModel):
    symbol: str
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    stage: str
    similarity: float
    confidence: float
    historical_success_rate: float | None
    labeled_cases: int
    matches: list[dict]


@router.get("/features/{symbol}", response_model=list[MarketFeature1Min])
async def features(
    symbol: Symbol,
    db: DB,
    bounds: Annotated[TimeRange, Depends()],
    limit: int = Query(1000, ge=1, le=10000),
    min_quality: float = Query(0, ge=0, le=1),
    only_final: bool = False,
):
    """Latest minute features; inclusive start / exclusive end, UTC aware."""
    rows = await db.fetch(
        "SELECT * FROM market_features_1m WHERE symbol=$1 "
        "AND ($2::timestamptz IS NULL OR time >= $2) "
        "AND ($3::timestamptz IS NULL OR time < $3) AND quality >= $4 "
        "AND (NOT $5::boolean OR is_final) ORDER BY time DESC LIMIT $6",
        symbol,
        bounds.start,
        bounds.end,
        min_quality,
        only_final,
        limit,
    )
    return [dict(r) for r in rows]


@router.post("/analysis/create", status_code=202, response_model=AnalysisTask)
async def create_analysis(body: AnalysisRequest, runtime: Runtime):
    """Queue a bounded async analysis; poll /analysis/{id} for the persisted result."""
    try:
        return await runtime.analysis.create(body)
    except OverflowError as error:
        raise HTTPException(429, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/analysis/{task_id}", response_model=AnalysisTask)
async def analysis_task(task_id: UUID, db: DB):
    row = await db.fetchrow("SELECT * FROM feature_analysis_tasks WHERE id=$1", task_id)
    if not row:
        raise HTTPException(404, "Analysis task not found")
    return decode_task(row)


@router.post("/cases", status_code=201, response_model=CaseResponse)
async def save_case(body: CaseRequest, runtime: Runtime):
    if not runtime.embeddings.configured():
        raise HTTPException(503, "Embeddings service is not configured")
    try:
        return await runtime.cases.save(body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/cases/search", response_model=list[CaseMatch])
async def search_cases(
    symbol: Annotated[str, Query(pattern=r"^[A-Z0-9]+-USDT-SWAP$", max_length=80)],
    db: DB,
    runtime: Runtime,
    start_time: AwareDatetime,
    end_time: AwareDatetime,
    limit: int = Query(10, ge=1, le=100),
    min_similarity: float = Query(0.7, ge=0, le=1),
    container_id: UUID | None = None,
):
    """Search using the same numerical window representation as saved cases."""
    try:
        window = AnalysisRequest(
            symbol=symbol, start_time=start_time, end_time=end_time
        )
    except ValueError as error:
        raise HTTPException(422, "Invalid analysis window") from error
    if not runtime.embeddings.configured():
        raise HTTPException(503, "Embeddings service is not configured")
    rows = await db.fetch(
        "SELECT * FROM market_features_1m "
        "WHERE symbol=$1 AND time >= $2 "
        "AND time < $3 ORDER BY time LIMIT 1440",
        symbol,
        window.start_time,
        window.end_time,
    )
    if not rows:
        raise HTTPException(404, "No features in window")
    vector = await runtime.embeddings.embed(feature_snapshot(rows))
    return await runtime.cases.search(vector, limit, min_similarity, container_id)


@router.post("/containers", status_code=201, response_model=ContainerResponse)
async def create_container(body: ContainerRequest, db: DB):
    row = await db.fetchrow(
        "INSERT INTO feature_containers(id,name,description) "
        "VALUES($1,$2,$3) "
        "ON CONFLICT(name) DO NOTHING RETURNING *",
        uuid4(),
        body.name,
        body.description,
    )
    if not row:
        raise HTTPException(409, "Container name already exists")
    return dict(row)


@router.get("/containers", response_model=list[ContainerResponse])
async def list_containers(db: DB, limit: int = Query(100, ge=1, le=1000)):
    return [
        dict(r)
        for r in await db.fetch(
            "SELECT * FROM feature_containers ORDER BY created_at DESC LIMIT $1", limit
        )
    ]


@router.put("/containers/{container_id}", response_model=ContainerResponse)
async def update_container(container_id: UUID, body: ContainerRequest, db: DB):
    # Turn duplicate names into a client conflict.
    import asyncpg

    try:
        row = await db.fetchrow(
            "UPDATE feature_containers SET name=$2,description=$3 "
            "WHERE id=$1 RETURNING *",
            container_id,
            body.name,
            body.description,
        )
    except asyncpg.UniqueViolationError as error:
        raise HTTPException(409, "Container name already exists") from error
    if not row:
        raise HTTPException(404, "Container not found")
    return dict(row)


@router.delete("/containers/{container_id}", status_code=204)
async def delete_container(container_id: UUID, db: DB):
    row = await db.fetchrow(
        "DELETE FROM feature_containers WHERE id=$1 RETURNING id", container_id
    )
    if not row:
        raise HTTPException(404, "Container not found")


@router.get("/opportunities", response_model=list[Opportunity])
async def opportunities(
    db: DB,
    limit: int = Query(100, ge=1, le=1000),
    min_confidence: float = Query(0, ge=0, le=1),
):
    """Unexpired matches. Historical success uses only explicitly labeled cases."""
    rows = await db.fetch(
        "SELECT * FROM opportunities WHERE expires_at > now() AND confidence >= $1 "
        "ORDER BY confidence DESC, symbol LIMIT $2",
        min_confidence,
        limit,
    )
    items = []
    for row in rows:
        item = dict(row)
        if isinstance(item["matches"], str):
            item["matches"] = json.loads(item["matches"])
        items.append(item)
    return items
