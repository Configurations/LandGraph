#!/bin/bash
# ─────────────────────────────────────────────────────────────
# deploy.sh — Push local files to remote host, rebuild & restart
#
# Usage:
#   ./deploy.sh <prefix> [action]
#   ./deploy.sh prod                     # sync + rebuild + restart on prod
#   ./deploy.sh staging --sync-only      # sync files only to staging
#   ./deploy.sh dev --status             # show status on dev
#   ./deploy.sh prod --logs              # show logs on prod
#
# Preserved on remote (never overwritten):
#   .env            — production secrets
#   config/         — team configs, prompts (editable via dashboard)
#   Shared/         — team configs alternate location
#
# Config: create a .deploy.<prefix>.env file next to this script:
#   .deploy.prod.env, .deploy.staging.env, .deploy.dev.env, ...
#
#   SSH_HOST=10.0.0.110
#   SSH_USER=root
#   SSH_PORT=22
#   REMOTE_DIR=/root/langgraph-project
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_DIR="$SCRIPT_DIR"

# ── Parse args: <prefix> [action] ──────────────────────────
PREFIX="${1:-}"
ACTION="${2:-deploy}"

if [[ -z "$PREFIX" ]]; then
    echo "Usage: $0 <prefix> [--sync-only|--restart-only|--status|--logs]"
    echo ""
    echo "  prefix = name of the target (prod, staging, dev, ...)"
    echo "  Loads config from .deploy.<prefix>.env"
    echo ""
    # List available configs
    CONFIGS=$(ls "$SCRIPT_DIR"/.deploy.*.env 2>/dev/null | sed 's/.*\.deploy\.\(.*\)\.env/  \1/')
    if [[ -n "$CONFIGS" ]]; then
        echo "Available targets:"
        echo "$CONFIGS"
    else
        echo "No .deploy.<prefix>.env files found. Create one first."
    fi
    exit 1
fi

# ── Load .deploy.<prefix>.env ──────────────────────────────
DEPLOY_ENV="$SCRIPT_DIR/.deploy.${PREFIX}.env"
if [[ ! -f "$DEPLOY_ENV" ]]; then
    echo "ERROR: Config file not found: .deploy.${PREFIX}.env"
    exit 1
fi
source "$DEPLOY_ENV"

# ── Defaults ───────────────────────────────────────────────
SSH_HOST="${SSH_HOST:-}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-}"
REMOTE_DIR="${REMOTE_DIR:-/root/langgraph-project}"

# ── Validate ───────────────────────────────────────────────
if [[ -z "$SSH_HOST" ]]; then
    echo "ERROR: SSH_HOST not set in .deploy.${PREFIX}.env"
    exit 1
fi

SSH_TARGET="${SSH_USER}@${SSH_HOST}"
SSH_OPTS="-p ${SSH_PORT} -o StrictHostKeyChecking=accept-new"
SCP_OPTS="-P ${SSH_PORT} -o StrictHostKeyChecking=accept-new"
[[ -n "$SSH_KEY" ]] && SSH_OPTS="$SSH_OPTS -i $SSH_KEY" && SCP_OPTS="$SCP_OPTS -i $SSH_KEY"

# ── Colors ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }

# ── Exclude from tar (not uploaded at all) ───────────────────
TAR_EXCLUDES=(
    --exclude='.git'
    --exclude='.claude'
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='.env'
    --exclude='.deploy.*.env'
    --exclude='node_modules'
    --exclude='.pytest_cache'
    --exclude='tests'
    --exclude='*.egg-info'
    --exclude='./config'
    --exclude='./Shared'
)

# ── Dirs preserved on remote (not deleted during clean) ──────
PRESERVE_ON_REMOTE=('.env' '.deploy.env' 'config' 'Shared')

# ── Functions ────────────────────────────────────────────────

do_sync() {
    log "Syncing files to ${SSH_TARGET}:${REMOTE_DIR} ..."
    log "  Preserved on remote: ${PRESERVE_ON_REMOTE[*]}"

    # Ensure remote dir and required subdirs exist
    # config/Teams/ and Shared/Teams/ hold team configs and prompts (managed via dashboard)
    ssh $SSH_OPTS "${SSH_TARGET}" "mkdir -p ${REMOTE_DIR} ${REMOTE_DIR}/config/Teams ${REMOTE_DIR}/Shared/Teams ${REMOTE_DIR}/Shared/Agents"

    # Build find exclusion for preserved dirs/files
    FIND_EXCLUDES=""
    for name in "${PRESERVE_ON_REMOTE[@]}"; do
        FIND_EXCLUDES="$FIND_EXCLUDES -not -name '$name'"
    done

    # Clean remote (except preserved dirs)
    log "Cleaning remote directory ..."
    ssh $SSH_OPTS "${SSH_TARGET}" bash -s <<REMOTE_CLEAN
cd "${REMOTE_DIR}"
find . -maxdepth 1 -not -name '.' $FIND_EXCLUDES -exec rm -rf {} + 2>/dev/null || true
REMOTE_CLEAN

    # Generate .version with build timestamp (dd.HH.mm format)
    date +"%d.%H.%M" > "$LOCAL_DIR/.version"
    log "Version: $(cat "$LOCAL_DIR/.version")"

    # Tar locally (excluding config/ Shared/ .git etc), pipe to remote
    log "Uploading code + Dockerfiles + scripts ..."
    tar cf - -C "$LOCAL_DIR" "${TAR_EXCLUDES[@]}" . \
        | ssh $SSH_OPTS "${SSH_TARGET}" "tar xf - -C ${REMOTE_DIR}"

    # Copy mcp_catalog.csv into Shared/ (not included in tar since Shared/ is excluded)
    log "Uploading Shared/mcp_catalog.csv ..."
    scp $SCP_OPTS "$LOCAL_DIR/Shared/Teams/mcp_catalog.csv" "${SSH_TARGET}:${REMOTE_DIR}/Shared/Teams/mcp_catalog.csv"

    # Seed config/ with global config files if they don't exist yet on remote
    # These are needed by Dockerfiles (COPY config/) and by the app at runtime
    log "Seeding config files (skip existing) ..."
    for f in "$LOCAL_DIR"/config/*.json "$LOCAL_DIR"/config/*.yaml "$LOCAL_DIR"/config/*.yml; do
        [[ -f "$f" ]] || continue
        fname=$(basename "$f")
        ssh $SSH_OPTS "${SSH_TARGET}" "test -f ${REMOTE_DIR}/config/${fname}" \
            || scp $SCP_OPTS "$f" "${SSH_TARGET}:${REMOTE_DIR}/config/${fname}"
    done

    # If no .env on remote, seed it from env.example so services can start
    ssh $SSH_OPTS "${SSH_TARGET}" bash -s <<REMOTE_ENV
if [[ ! -f "${REMOTE_DIR}/.env" ]]; then
    cp "${REMOTE_DIR}/env.example" "${REMOTE_DIR}/.env"
    echo "  [deploy] .env created from env.example — edit it with real values"
fi
REMOTE_ENV

    log "Sync complete."
}

do_rebuild() {
    log "Rebuilding and restarting containers on ${SSH_TARGET} ..."

    ssh $SSH_OPTS "${SSH_TARGET}" bash -s -- "${REMOTE_DIR}" <<'REMOTE_SCRIPT'
set -euo pipefail
cd "$1"

SERVICES="langgraph-admin langgraph-api discord-bot mail-bot hitl-console"

echo "  Stopping services..."
docker compose stop $SERVICES 2>/dev/null || true
docker compose rm -f $SERVICES 2>/dev/null || true

echo "  Building (--no-cache)..."
docker compose build --no-cache $SERVICES

echo "  Cleaning old images..."
docker image prune -f
docker builder prune -f

echo "  Starting all services..."
docker compose up -d

echo "  Waiting for services to start..."
sleep 15

# Apply SQL schema
if [[ -f scripts/init.sql ]]; then
    echo "  Applying SQL schema..."
    docker exec -i langgraph-postgres psql -U "${POSTGRES_USER:-langgraph}" -d "${POSTGRES_DB:-langgraph}" < scripts/init.sql 2>/dev/null \
        && echo "  Schema OK" || echo "  Schema: error (check logs)"
fi

echo ""
docker compose ps
REMOTE_SCRIPT

    log "Rebuild complete."
}

do_status() {
    log "Checking status on ${SSH_TARGET} ..."

    ssh $SSH_OPTS "${SSH_TARGET}" bash -s <<'REMOTE_SCRIPT'
cd "$HOME/langgraph-project"
echo "=== Docker Compose Status ==="
docker compose ps
echo ""
echo "=== Health Check ==="
curl -sf http://localhost:8123/health 2>/dev/null && echo "" || echo "API not responding"
echo ""
echo "=== API Status ==="
curl -sf http://localhost:8123/status 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "API not responding"
echo ""
echo "=== Recent Logs (last 15 lines) ==="
docker compose logs --tail 15 --no-color 2>/dev/null
REMOTE_SCRIPT
}

do_logs() {
    log "Fetching logs from ${SSH_TARGET} ..."
    ssh $SSH_OPTS "${SSH_TARGET}" "cd \$HOME/langgraph-project && docker compose logs --tail 50 --no-color"
}

# ── Main ─────────────────────────────────────────────────────
log "Target: ${PREFIX} → ${SSH_USER}@${SSH_HOST}:${SSH_PORT} ${REMOTE_DIR}"

case "$ACTION" in
    --sync-only)
        do_sync
        ;;
    --restart-only)
        do_rebuild
        ;;
    --status)
        do_status
        ;;
    --logs)
        do_logs
        ;;
    deploy)
        do_sync
        echo ""
        do_rebuild
        echo ""
        do_status
        ;;
    *)
        echo "Usage: $0 <prefix> [--sync-only|--restart-only|--status|--logs]"
        exit 1
        ;;
esac
