#!/bin/bash
cd ~/langgraph-project
docker compose up -d --build langgraph-api discord-bot
sleep 12
echo ""
docker compose ps
echo ""
curl -s http://localhost:8123/health
echo ""
curl -s http://localhost:8123/status | python3 -m json.tool 2>/dev/null
