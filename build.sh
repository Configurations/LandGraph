#!/bin/bash
PROJECT_DIR="/${HOME}/langgraph-project"
cd "${PROJECT_DIR}"

docker compose stop
sleep 12

SERVICES="langgraph-admin langgraph-api discord-bot mail-bot hitl-console"

echo "  Arret des services..."
docker compose stop $SERVICES 2>/dev/null || true
docker compose rm -f $SERVICES 2>/dev/null || true

echo "  Build (--no-cache --pull)..."
docker compose build --no-cache --pull $SERVICES

echo "  Nettoyage des anciennes images et du build cache..."
docker image prune -f
docker builder prune -f

docker compose up -d
sleep 12

# Rejouer init.sql (idempotent — IF NOT EXISTS)
echo "  -> Application du schema SQL..."
docker exec -i langgraph-postgres psql -U "${POSTGRES_USER:-langgraph}" -d "${POSTGRES_DB:-langgraph}" < scripts/init.sql 2>/dev/null && echo "  -> Schema OK" || echo "  -> Schema: erreur (voir logs)"
echo ""
docker compose ps
sleep 12

docker compose logs --tail 30


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

