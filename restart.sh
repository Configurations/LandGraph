#!/bin/bash
PROJECT_DIR="${HOME}/langgraph-project"
cd "${PROJECT_DIR}"
docker compose down
docker compose up -d
echo ""
docker compose ps


# Detecter l'IP locale (premiere interface non-loopback)
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$LOCAL_IP" ] && LOCAL_IP="localhost"

echo ""
curl -s http://localhost:8123/health
echo ""
curl -s http://localhost:8123/status | python3 -m json.tool 2>/dev/null
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Services disponibles :"
echo "  API Gateway         : http://${LOCAL_IP}:8123"
echo "  Dashboard Admin     : http://${LOCAL_IP}:8080"
echo "  hitl web            : http://${LOCAL_IP}:8090"
echo "  OpenLIT             : http://${LOCAL_IP}:3000"
echo "════════════════════════════════════════════════════════════════"

docker compose logs --tail 30
