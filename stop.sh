#!/bin/bash
PROJECT_DIR="${HOME}/langgraph-project"
cd "${PROJECT_DIR}"
docker compose down
echo ""
docker compose ps
