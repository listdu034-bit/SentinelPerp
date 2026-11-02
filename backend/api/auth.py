"""Single-operator OAuth2/JWT authentication using python-jose and Passlib."""

import asyncio
import secrets
import time
from hmac import compare_digest
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketException,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from redis.exceptions import RedisError

from backend.api.dependencies import get_redis
from backend.api.limiter import limiter

router = APIRouter()
bearer = OAuth2PasswordBearer(tokenUrl="/auth/jwt/login")
passwords = CryptContext(
    schemes=["pbkdf2_sha256"], pbkdf2_sha256__rounds=600_000, deprecated="auto"
)
ISSUER = "sentinelperp"
AUDIENCE = "sentinelperp-console"


class AuthService:
    def __init__(self, settings):
        self.username = settings.api_auth_username
        password = settings.api_auth_password.get_secret_value()
        self.configured = bool(self.username and password)
        self.password_hash = passwords.hash(password or secrets.token_urlsafe(32))
        # Configured deployments require a stable signing key.
        self.key = settings.api_jwt_secret.get_secret_value() or secrets.token_hex(32)
        self.ttl = settings.api_jwt_ttl_seconds

    def issue(self):
        now = int(time.time())
        return jwt.encode(
            {
                "sub": self.username,
                "iat": now,
                "exp": now + self.ttl,
                "jti": str(uuid4()),
                "iss": ISSUER,
                "aud": AUDIENCE,
            },
            self.key,
            algorithm="HS256",
        )

    async def validate(self, token, redis):
        try:
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["HS256"],
                audience=AUDIENCE,
                issuer=ISSUER,
                options={
                    "require_exp": True,
                    "require_iat": True,
                    "require_sub": True,
                    "require_jti": True,
                },
            )
            if not self.configured or claims["sub"] != self.username:
                raise JWTError("Unknown user")
            if await redis.get(f"auth:session:{claims['jti']}") != self.username:
                raise JWTError("Session expired or revoked")
            return claims
        except JWTError as exc:
            raise HTTPException(
                401, "登录已失效，请重新登录", headers={"WWW-Authenticate": "Bearer"}
            ) from exc
        except RedisError as exc:
            raise HTTPException(503, "认证服务暂不可用") from exc


async def current_user(
    request: Request, token: str = Depends(bearer), redis=Depends(get_redis)
):
    return await request.app.state.auth.validate(token, redis)


@router.post("/auth/jwt/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    redis=Depends(get_redis),
):
    auth = request.app.state.auth
    if not auth.configured:
        raise HTTPException(503, "请先配置 API_AUTH_USERNAME 和 API_AUTH_PASSWORD")
    # Always check both fields; run password verification off the event loop.
    valid_password = await asyncio.to_thread(
        passwords.verify, form.password, auth.password_hash
    )
    valid_username = compare_digest(form.username.encode(), auth.username.encode())
    if not (valid_password and valid_username):
        raise HTTPException(
            401, "用户名或密码错误", headers={"WWW-Authenticate": "Bearer"}
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    token = auth.issue()
    claims = jwt.get_unverified_claims(token)
    await redis.set(f"auth:session:{claims['jti']}", auth.username, ex=auth.ttl)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": auth.ttl,
    }


@router.get("/users/me")
async def me(response: Response, user=Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return {"username": user["sub"], "expires_at": user["exp"]}


@router.post("/auth/jwt/logout", status_code=204)
async def logout(user=Depends(current_user), redis=Depends(get_redis)):
    await redis.delete(f"auth:session:{user['jti']}")
    return Response(status_code=204)


async def socket_user(ws: WebSocket):
    """Authenticate the first frame; never put bearer tokens into URL/access logs."""
    origin = ws.headers.get("origin")
    if origin and origin not in ws.app.state.settings.api_cors_origins:
        raise WebSocketException(code=1008)
    await ws.accept()
    try:
        message = await asyncio.wait_for(ws.receive_json(), timeout=5)
        if not isinstance(message, dict) or message.get("type") != "authenticate":
            raise ValueError("Authentication required")
        token = message.get("token")
        if not isinstance(token, str) or len(token) > 8192:
            raise ValueError("Invalid token")
        redis = ws.app.state.redis.connection()
        await ws.app.state.auth.validate(token, redis)
        ws.state.auth_token = token
    except (TimeoutError, ValueError, HTTPException):
        raise WebSocketException(code=1008)


async def watch_socket_auth(ws):
    """Close live sessions promptly after expiry or revocation."""
    while True:
        await asyncio.sleep(2)
        try:
            await ws.app.state.auth.validate(
                ws.state.auth_token, ws.app.state.redis.connection()
            )
        except HTTPException:
            await ws.close(code=1008)
            return
