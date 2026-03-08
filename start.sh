#!/bin/bash
PROJECT_DIR="${HOME}/langgraph-project"
cd "${PROJECT_DIR}"

docker compose stop langgraph-admin 2>/dev/null || true
docker compose rm -f langgraph-admin 2>/dev/null || true
docker compose build --no-cache langgraph-admin

docker compose up -d
echo ""
docker compose ps
docker compose logs --tail 30