# M2 控制台登录

采用用户指定的轻量方案：**python-jose[cryptography] 3.5.0** 签发/验证 JWT，
**Passlib 1.7.4** 使用 PBKDF2-SHA256 哈希和校验密码。
前端采用 **@ant-design/pro-components 2.8.10** 的 LoginForm、ProFormText、ProLayout，
以及 **@ant-design/pro-layout 7.22.7**。传递依赖 path-to-regexp 覆盖为 8.4+ 安全修复版。
没有新增用户数据库、注册入口或自制加密算法。

## 配置

在仓库根目录 `.env` 配置（不要提交真实值）：

```dotenv
API_AUTH_USERNAME=your-operator
API_AUTH_PASSWORD=your-long-unique-password
API_JWT_SECRET=your-independent-random-signing-secret-at-least-32-characters
API_JWT_TTL_SECONDS=3600
```

用 `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成独立签名密钥。
所有 API 实例必须使用同一密钥和 Redis。修改配置后重启 API。
未配置账号密码时登录返回 503，业务 API 仍拒绝匿名访问；配置账号密码时必须同时配置至少 32 字符签名密钥。
Docker Compose 已使用 `env_file: .env`，本地从仓库根目录运行 uvicorn。
安装 `requirements-dev.txt` 后运行 `uvicorn backend.api.main:app`；前端执行 `npm ci && npm run dev`。
生产使用 HTTPS/WSS；`API_CORS_ORIGINS` 应仅包含实际控制台来源。
任何凭据都不要放进 `VITE_*`。

## 接口和会话

- `POST /auth/jwt/login`：OAuth2 表单 `username`、`password`；返回 `access_token`、`token_type=bearer` 和 `expires_in`。
- `GET /users/me`：携带 `Authorization: Bearer <token>`，返回 `username`、`expires_at`。
- `POST /auth/jwt/logout`：携带令牌，删除 Redis 有效会话，成功返回 204。
- `/api/v1/*`、M2 `/api/*` 和 `/metrics` 均要求认证。健康探针 `/health`、`/health/detailed` 保持可用。
- `/ws/market` 和 `/ws/trades/{symbol}`：连接建立后 5 秒内发送
  `{"type":"authenticate","token":"<access_token>"}`，随后才发送业务数据；认证失败关闭码为 1008。
  已连接会话每 2 秒检查到期和撤销。令牌不放入 WebSocket URL。

JWT 使用固定 HS256 算法并验证 issuer、audience、subject、expiry、jti。
Redis 使用带 TTL 的有效会话表；退出、Redis 重启或键淘汰后，旧 JWT 均无法继续访问。
Redis 不可用时认证失败关闭，不降级为匿名访问。每个来源登录限速 5 次/分钟（当前限速器按 API 进程计数）。
令牌存储在当前标签页 sessionStorage；刷新后通过 `/users/me` 恢复，关闭标签页结束本地会话。
退出必须服务端成功才清除本地会话，失败会显示重试提示。
React Context 管理认证，M1/M2 Axios 拦截器统一附加 Bearer；401 和到期会清空会话、查询缓存并跳转登录。
无刷新令牌，到期需要重新登录。深链在登录成功后回到原页面。

## 验证

```bash
python3 -m pytest tests/test_auth.py tests/test_api.py tests/test_m2.py -q
cd frontend
npm test -- --maxWorkers=1 --no-file-parallelism
npm run build
```

认证测试覆盖正确/错误凭据、未认证业务 API、过期/篡改/错误算法令牌、退出撤销、登录限流及 WebSocket 首帧认证。
前端覆盖受保护页面、登录回跳、错误提示、刷新恢复、退出清缓存、M1/M2 请求认证及 401。

参考：[FastAPI OAuth2/JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)、
[python-jose](https://github.com/mpdavis/python-jose)、
[Passlib](https://passlib.readthedocs.io/)、
[ProComponents LoginForm](https://procomponents.ant.design/components/login-form/)。

可选真实服务测试：后端设置 `TEST_DATABASE_URL` 和 `TEST_REDIS_URL` 后运行
`tests/test_api_integration.py`；前端还需设置 `CONSOLE_TEST_URL`、
`CONSOLE_TEST_USERNAME` 和 `CONSOLE_TEST_PASSWORD`，再执行 `npm run test:integration`。
这些变量必须指向隔离的测试服务。

依赖审计：新增 ProLayout 传递依赖的高危公告已通过覆盖 path-to-regexp 8.4+ 修复。
原有 React Router 6 仍有两项中危审计记录，修复需迁移至 7.18+；本任务未作路由器大版本迁移。
应用没有 SSR hydration，登录回跳仅接受本应用内且不含反斜杠的相对路径。
