#!/bin/bash
cd "$(dirname "$0")"
docker compose up -d
echo ""
docker compose ps
