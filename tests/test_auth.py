"""Real authentication boundaries without external database/Redis services."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from prometheus_client import REGISTRY
from starlette.websockets import WebSocketDisconnect

from backend.api.dependencies import get_redis
from backend.api.limiter import limiter
from backend.api.main import create_app
from backend.config.settings import Settings


@pytest.fixture
def auth_api():
    limiter.reset()
    app = create_app(
        Settings(
            _env_file=None,
            api_auth_username="operator",
            api_auth_password="correct password",
            api_jwt_secret="test-signing-key-" * 4,
            m2_scheduler_enabled=False,
        )
    )
    revoked = {}

    async def get(key):
        return revoked.get(key)

    async def set_(key, value, **kwargs):
        revoked[key] = value

    async def delete(key):
        revoked.pop(key, None)

    redis = SimpleNamespace(
        delete=AsyncMock(side_effect=delete),
        get=AsyncMock(side_effect=get),
        set=AsyncMock(side_effect=set_),
    )
    app.dependency_overrides[get_redis] = lambda: redis
    app.state.redis = SimpleNamespace(connection=lambda: redis)
    yield TestClient(app), app, redis
    collector = REGISTRY._names_to_collectors.get("http_requests_inprogress")
    if collector is not None:
        REGISTRY.unregister(collector)


def login(client):
    result = client.post(
        "/auth/jwt/login", data={"username": "operator", "password": "correct password"}
    )
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    return result.json()["access_token"]


@pytest.mark.parametrize(
    "path", ["/users/me", "/api/v1/status", "/api/opportunities", "/metrics"]
)
def test_no_anonymous_business_access(auth_api, path):
    assert auth_api[0].get(path).status_code == 401


def test_login_me_and_revocation(auth_api):
    client, _, redis = auth_api
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/users/me", headers=headers).json()["username"] == "operator"
    assert client.post("/auth/jwt/logout", headers=headers).status_code == 204
    assert redis.delete.await_count == 1
    assert client.get("/users/me", headers=headers).status_code == 401
    assert (
        client.get(
            "/users/me", headers={"Authorization": f"Bearer {login(client)}"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "username,password",
    [("operator", "wrong"), ("wrong", "correct password"), ("", "")],
)
def test_bad_credentials(auth_api, username, password):
    response = auth_api[0].post(
        "/auth/jwt/login", data={"username": username, "password": password}
    )
    assert response.status_code in (401, 422)
    assert "access_token" not in response.text


def test_invalid_expired_and_wrong_algorithm(auth_api):
    client, app, _ = auth_api
    token = login(client)
    claims = jwt.get_unverified_claims(token)
    expired = jwt.encode(
        {**claims, "exp": int(time.time()) - 10}, app.state.auth.key, algorithm="HS256"
    )
    wrong_alg = jwt.encode(claims, app.state.auth.key, algorithm="HS384")
    for invalid in [token + "tampered", "garbage", expired, wrong_alg]:
        assert (
            client.get(
                "/users/me", headers={"Authorization": f"Bearer {invalid}"}
            ).status_code
            == 401
        )


def test_login_rate_limit(auth_api):
    client, _, _ = auth_api
    for _ in range(5):
        assert (
            client.post(
                "/auth/jwt/login", data={"username": "x", "password": "x"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/auth/jwt/login", data={"username": "x", "password": "x"}
        ).status_code
        == 429
    )


@pytest.mark.parametrize(
    "message", [{"type": "ping"}, {"type": "authenticate", "token": "bad"}]
)
def test_websocket_requires_valid_first_frame(auth_api, message):
    with auth_api[0].websocket_connect("/ws/market") as ws:
        ws.send_json(message)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_websocket_valid_token_reaches_business_handler(auth_api):
    client, _, _ = auth_api
    # Symbol validation runs only after authentication succeeds.
    with client.websocket_connect("/ws/trades/INVALID") as ws:
        ws.send_json({"type": "authenticate", "token": login(client)})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_websocket_rejects_foreign_origin(auth_api):
    with pytest.raises(WebSocketDisconnect):
        with auth_api[0].websocket_connect(
            "/ws/market", headers={"origin": "https://foreign.invalid"}
        ):
            pass


def test_credentials_require_a_strong_signing_key():
    with pytest.raises(ValueError, match="API_JWT_SECRET"):
        Settings(
            _env_file=None, api_auth_username="operator", api_auth_password="password"
        )


def test_missing_redis_session_invalidates_signed_token(auth_api):
    client, _, redis = auth_api
    token = login(client)
    redis.get.side_effect = None
    redis.get.return_value = None
    assert (
        client.get(
            "/users/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_logout_closes_existing_websocket(auth_api, monkeypatch):
    import asyncio

    async def producer(ws):
        await ws.send_json({"type": "authenticated"})
        await asyncio.Event().wait()

    monkeypatch.setattr("backend.api.websocket.market", producer)
    client, _, _ = auth_api
    token = login(client)
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "authenticate", "token": token})
        assert ws.receive_json()["type"] == "authenticated"
        assert (
            client.post(
                "/auth/jwt/logout", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 204
        )
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008
