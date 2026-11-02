#!/bin/bash
# Quick setup script for M2 public access with authentication

set -e

echo "🔐 M2 Security Configuration Setup"
echo "=================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy from .env.example first."
    exit 1
fi

# Check if auth config already exists
if grep -q "API_AUTH_ENABLED" .env; then
    echo "✅ Authentication config already exists in .env"
else
    echo "📝 Adding authentication configuration to .env..."
    cat >> .env << 'EOF'

# API Authentication (HTTP Basic Auth)
API_AUTH_ENABLED=true
API_AUTH_USERNAME=admin
API_AUTH_PASSWORD=SentinelPerp@2026!Secure
EOF
    echo "✅ Authentication config added"
fi

echo ""
echo "📋 Current Configuration:"
echo "  - Frontend: 0.0.0.0:8080 (Public)"
echo "  - API:      0.0.0.0:8000 (Public, Auth Required)"
echo "  - Database: 127.0.0.1:5432 (Local Only)"
echo "  - Redis:    Internal Only"
echo ""

# Get server IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "Unable to detect")
if [ "$SERVER_IP" != "Unable to detect" ]; then
    echo "🌐 Server Public IP: $SERVER_IP"
    echo ""
    echo "📍 Access URLs:"
    echo "  Frontend: http://$SERVER_IP:8080"
    echo "  API Docs: http://$SERVER_IP:8000/docs"
    echo ""
fi

echo "🔑 Default Credentials:"
echo "  Username: admin"
echo "  Password: (see .env file - API_AUTH_PASSWORD)"
echo ""
echo "⚠️  IMPORTANT: Please change the default password in .env file!"
echo ""

read -p "Rebuild and restart services now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔄 Rebuilding API service..."
    docker compose build api

    echo "🔄 Restarting services..."
    docker compose restart api backend

    echo ""
    echo "⏳ Waiting for services to be ready..."
    sleep 8

    echo "✅ Services restarted!"
    echo ""
    echo "🧪 Testing configuration..."

    # Test health endpoint (no auth)
    if curl -s http://localhost:8000/health | grep -q "ok"; then
        echo "  ✅ Health check: OK"
    else
        echo "  ❌ Health check: FAILED"
    fi

    # Test API without auth (should fail)
    if curl -s http://localhost:8000/api/v1/instruments 2>&1 | grep -q "401\|credentials"; then
        echo "  ✅ Authentication: ENABLED"
    else
        echo "  ⚠️  Authentication: May not be working"
    fi

    echo ""
    echo "✅ Setup complete!"
    echo ""
    echo "📖 See docs/SECURITY_CONFIG.md for detailed usage guide."
else
    echo "Skipped restart. Run 'docker compose restart api backend' when ready."
fi
