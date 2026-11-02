# 安全配置指南

## API 认证配置

M2 集成测试版本已启用 HTTP Basic Auth 认证机制，保护所有 API 端点（除 `/health`）。

### 配置步骤

1. **编辑 `.env` 文件**，添加以下配置：

```bash
# API Authentication (HTTP Basic Auth)
API_AUTH_ENABLED=true
API_AUTH_USERNAME=admin
API_AUTH_PASSWORD=your-secure-password-here
```

2. **设置强密码**

建议使用复杂密码，例如：
- 至少 16 个字符
- 包含大小写字母、数字、特殊字符
- 示例格式：`SentinelPerp@2026!SecurePass`

3. **重启服务**

```bash
cd /root/SentinelPerp
docker compose restart api backend
```

---

## 网络配置

当前配置已开放到公网 (0.0.0.0)：

- **前端**: `0.0.0.0:8080` → 公网可访问
- **API**: `0.0.0.0:8000` → 公网可访问，**需要认证**
- **数据库**: `127.0.0.1:5432` → 仅本地访问 ✅
- **Redis**: 无端口暴露 → 仅 Docker 内部 ✅

---

## 访问示例

### 前端访问（无需认证）

```bash
# 通过公网 IP 访问
http://<your-server-ip>:8080
```

### API 访问（需要认证）

#### 使用 curl

```bash
# 使用 Basic Auth
curl -u admin:your-password http://<your-server-ip>:8000/api/v1/instruments

# 或使用 Authorization header
curl -H "Authorization: Basic $(echo -n 'admin:your-password' | base64)" \
  http://<your-server-ip>:8000/api/v1/instruments
```

#### 使用浏览器

访问 API 文档时会自动弹出认证对话框：
```
http://<your-server-ip>:8000/docs
```

输入用户名和密码即可。

#### 使用 Python

```python
import requests

response = requests.get(
    "http://<your-server-ip>:8000/api/v1/instruments",
    auth=("admin", "your-password")
)
```

---

## 前端 API 配置

前端需要配置 API 凭证。编辑 `frontend/.env`：

```bash
VITE_API_BASE_URL=http://<your-server-ip>:8000
VITE_API_USERNAME=admin
VITE_API_PASSWORD=your-password
```

**注意**：前端环境变量会暴露在浏览器中，因此不应在生产环境使用此方式。生产环境建议使用反向代理 + Session 管理。

---

## 安全建议

### 1. 防火墙配置

```bash
# 只允许特定 IP 访问
ufw allow from <trusted-ip> to any port 8000
ufw allow from <trusted-ip> to any port 8080

# 或允许所有（需要强认证）
ufw allow 8000/tcp
ufw allow 8080/tcp
```

### 2. 使用 Nginx 反向代理 + HTTPS

```nginx
server {
    listen 443 ssl http2;
    server_name sentinelperp.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 前端
    location / {
        proxy_pass http://localhost:8080;
    }

    # API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}
```

### 3. 定期更换密码

建议每 90 天更换一次 `API_AUTH_PASSWORD`。

### 4. 监控访问日志

```bash
# 查看 API 访问日志
docker compose logs -f api | grep -E "(401|403)"
```

### 5. 禁用认证（仅开发环境）

如果在完全受信任的内网环境，可以禁用认证：

```bash
API_AUTH_ENABLED=false
```

---

## 故障排除

### 问题 1: 前端无法连接 API

**症状**: 前端报 401 错误

**解决**:
1. 检查 API 认证配置是否正确
2. 确认前端环境变量已设置
3. 查看浏览器 Network 面板，确认 Authorization header

### 问题 2: API 返回 401 Unauthorized

**原因**: 用户名或密码错误

**解决**:
1. 检查 `.env` 文件中的配置
2. 确认没有多余的空格或引号
3. 重启 API 服务

### 问题 3: WebSocket 连接失败

**原因**: WebSocket 也需要认证

**解决**: 前端 WebSocket 连接需要在 URL 中包含认证信息：
```javascript
ws://admin:password@<server-ip>:8000/ws/market
```

---

## 状态检查

```bash
# 检查认证是否启用
curl -s http://localhost:8000/health | jq

# 测试认证（应返回 401）
curl -s http://localhost:8000/api/v1/instruments
# 输出: {"error":{"code":401,"message":"Not authenticated"}}

# 测试认证（应返回数据）
curl -s -u admin:your-password http://localhost:8000/api/v1/instruments
```

---

**重要**: 完成认证配置后，请删除此文档中的示例密码，并妥善保管实际密码。
