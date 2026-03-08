#!/bin/bash
PROJECT_DIR="${HOME}/langgraph-project"
cd "${PROJECT_DIR}"
docker compose up -d
echo ""
docker compose ps
