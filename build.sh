#!/bin/bash
PROJECT_DIR="${HOME}/langgraph-project"
cd "${PROJECT_DIR}"

docker compose stop langgraph-admin 2>/dev/null || true
docker compose rm -f langgraph-admin 2>/dev/null || true
docker compose build --no-cache langgraph-admin langgraph-api discord-bot mail-bot

docker compose up -d
sleep 12
echo ""
docker compose ps
echo ""
curl -s http://localhost:8123/health
echo ""
curl -s http://localhost:8123/status | python3 -m json.tool 2>/dev/null
