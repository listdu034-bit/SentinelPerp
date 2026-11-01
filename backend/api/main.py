"""FastAPI service entry point: uvicorn backend.api.main:app."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from openai import OpenAIError
from prometheus_fastapi_instrumentator import Instrumentator
from redis.exceptions import RedisError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException

from backend.api import websocket
from backend.api.limiter import limiter
from backend.api.routes import (
    candles,
    funding,
    health,
    instruments,
    liquidations,
    m2,
    open_interest,
    quality,
    status,
    trades,
)
from backend.collector.instrument_discovery import InstrumentDiscovery
from backend.config.settings import get_settings
from backend.features.runtime import M2Runtime
from backend.storage.redis_client import RedisClient
from backend.storage.timescale_client import TimescaleClient


@asynccontextmanager
async def lifespan(app):
    settings = app.state.settings
    database, redis = TimescaleClient(settings), RedisClient(settings)
    discovery = InstrumentDiscovery(settings, None)
    app.state.database, app.state.redis = database, redis
    app.state.discovery, app.state.catalog_lock = discovery, asyncio.Lock()
    publisher = None
    runtime = None
    try:
        await database.connect()
        await redis.connect()
        runtime = M2Runtime(database.pool, discovery, settings)
        app.state.m2 = runtime
        runtime.start()
        publisher = asyncio.create_task(websocket.market_publisher(app))
        yield
    finally:
        try:
            if runtime:
                await runtime.close()
        finally:
            if publisher:
                publisher.cancel()
                with suppress(asyncio.CancelledError):
                    await publisher
            try:
                await discovery.close()
            finally:
                try:
                    await redis.close()
                finally:
                    await database.close()


def create_app(settings=None):
    app = FastAPI(
        title="SentinelPerp API",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "USDT perpetual history and live data. All time filters require a timezone."
        ),
    )
    app.state.settings = settings or get_settings()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.status_code, "message": exc.detail}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": 422,
                    "message": "Invalid request",
                    "details": [
                        {"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()
                    ],
                }
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        unavailable = isinstance(
            exc, (asyncpg.PostgresError, RedisError, OpenAIError, OSError, TimeoutError)
        )
        code = 503 if unavailable else 500
        logging.getLogger(__name__).exception("API request failed")
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "message": "Dependency unavailable"
                    if unavailable
                    else "Internal server error",
                }
            },
            status_code=code,
        )

    for error_type in (
        asyncpg.PostgresError,
        RedisError,
        OpenAIError,
        OSError,
        TimeoutError,
    ):
        app.add_exception_handler(error_type, unexpected_error)

    app.include_router(health.router, tags=["Health"])
    for module in (
        instruments,
        trades,
        candles,
        funding,
        open_interest,
        liquidations,
        quality,
        status,
    ):
        app.include_router(
            module.router, prefix="/api/v1", tags=[module.__name__.split(".")[-1]]
        )
    app.include_router(m2.router, prefix="/api", tags=["M2"])
    app.include_router(websocket.router)
    add_pagination(app)
    Instrumentator(
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics")
    return app


app = create_app()
