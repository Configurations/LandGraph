#!/bin/bash
cd ~/langgraph-project
docker compose down
docker compose up -d
echo ""
docker compose ps
