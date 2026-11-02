"""Redis broadcast bridge with bounded sends, heartbeats and resubscription."""

import asyncio
import json
import re
from contextlib import suppress

from anyio import CancelScope
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from redis.exceptions import RedisError

from backend.api.auth import socket_user, watch_socket_auth
from backend.api.routes.status import market_snapshot
from backend.api.schemas import TradeResponse

router = APIRouter(dependencies=[Depends(socket_user)])


async def send(ws, payload):
    await asyncio.wait_for(ws.send_json(jsonable_encoder(payload)), timeout=10)


async def receive(ws, pong):
    """Observe disconnects immediately, independently of the heartbeat clock."""
    while True:
        message = await ws.receive_json()
        if not isinstance(message, dict):
            raise ValueError("Expected a JSON object")
        if message.get("type") == "pong":
            pong.set()
        elif message.get("type") == "ping":
            await send(ws, {"type": "pong"})


async def heartbeat(ws, pong):
    """Application heartbeat: respond to each server ping with {type: pong}."""
    while True:
        await asyncio.sleep(30)
        pong.clear()
        await send(ws, {"type": "ping"})
        await asyncio.wait_for(pong.wait(), timeout=10)


async def broadcast(ws, channels):
    redis = ws.app.state.redis.connection()
    while True:
        try:
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(*channels)
                await send(
                    ws,
                    {
                        "type": "subscribed",
                        "channels": channels,
                        "delivery": "live-only; use REST to backfill after reconnect",
                    },
                )
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1
                    )
                    if message and message["type"] == "message":
                        await send(
                            ws,
                            {
                                "type": "trade",
                                "data": TradeResponse.model_validate_json(
                                    message["data"]
                                ).model_dump(mode="json"),
                            },
                        )
        except RedisError:
            await send(ws, {"type": "reconnecting"})
            await asyncio.sleep(1)


async def market(ws):
    """One producer per API process publishes snapshots to a Redis channel."""
    redis = ws.app.state.redis.connection()
    while True:
        try:
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe("market:overview")
                async with ws.app.state.database.pool.acquire() as db:
                    await send(ws, await market_snapshot(db, redis))
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1
                    )
                    if message and message["type"] == "message":
                        await send(ws, json.loads(message["data"]))
        except RedisError:
            await send(ws, {"type": "reconnecting"})
            await asyncio.sleep(1)


async def market_publisher(app):
    import logging

    while True:
        try:
            async with app.state.database.pool.acquire() as db:
                snapshot = await market_snapshot(db, app.state.redis.connection())
            await app.state.redis.connection().publish(
                "market:overview", json.dumps(jsonable_encoder(snapshot))
            )
        except Exception:
            logging.getLogger(__name__).exception("Market broadcast failed")
        await asyncio.sleep(30)


async def serve(ws, producer):
    pong = asyncio.Event()
    tasks = [
        asyncio.create_task(watch_socket_auth(ws)),
        asyncio.create_task(heartbeat(ws, pong)),
        asyncio.create_task(receive(ws, pong)),
        asyncio.create_task(producer(ws)),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (
        asyncio.CancelledError,
        WebSocketDisconnect,
        TimeoutError,
        RuntimeError,
        ValueError,
    ):
        pass
    finally:
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(RuntimeError, WebSocketDisconnect):
                await ws.close(code=1001)


@router.websocket("/ws/trades/{symbol}")
async def trades(ws: WebSocket, symbol: str):
    symbols = list(dict.fromkeys(symbol.split(",")))
    if not 1 <= len(symbols) <= 50 or any(
        not re.fullmatch(r"[A-Z0-9]{1,65}-USDT-SWAP", s) for s in symbols
    ):
        await ws.close(code=1008)
        return
    await serve(
        ws, lambda socket: broadcast(socket, [f"events:trade:{s}" for s in symbols])
    )


@router.websocket("/ws/market")
async def overview(ws: WebSocket):
    await serve(ws, market)
