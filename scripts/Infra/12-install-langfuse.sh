#!/bin/bash
###############################################################################
# Script 12 : Installation Langfuse self-hosted (observabilite)
#
# Deploie Langfuse v3 en Docker Compose a cote de LangGraph.
# Integre le tracing dans les agents via le CallbackHandler.
#
# Usage : ./12-install-langfuse.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 12 : Langfuse Self-Hosted"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Telecharger le docker-compose Langfuse ────────────────────────────────
echo "[1/5] Telechargement du docker-compose Langfuse..."

mkdir -p langfuse
cd langfuse

# Telecharger le docker-compose officiel de Langfuse v3
wget -qO docker-compose.yml https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml

if [ ! -s docker-compose.yml ]; then
    echo "ERREUR : impossible de telecharger le docker-compose Langfuse"
    exit 1
fi

echo "  -> docker-compose.yml telecharge"

# ── 2. Configurer les secrets ────────────────────────────────────────────────
echo "[2/5] Configuration des secrets..."

# Generer des secrets aleatoires
SALT=$(openssl rand -hex 16)
NEXTAUTH_SECRET=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)

cat > .env << EOF
# Langfuse secrets
SALT=${SALT}
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
NEXTAUTH_URL=http://localhost:3000

# Postgres (Langfuse utilise son propre Postgres)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# MinIO
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=miniosecret
EOF

chmod 600 .env
echo "  -> Secrets generes"

# ── 3. Demarrer Langfuse ─────────────────────────────────────────────────────
echo "[3/5] Demarrage de Langfuse..."

docker compose up -d

echo "  -> Attente demarrage (2-3 minutes)..."
sleep 30

# Verifier que langfuse-web est ready
MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker compose logs langfuse-web 2>/dev/null | grep -q "Ready"; then
        echo "  -> Langfuse ready !"
        break
    fi
    sleep 10
    WAITED=$((WAITED + 10))
    echo "  -> Attente... (${WAITED}s)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "  -> ATTENTION : Langfuse prend du temps a demarrer. Verifiez :"
    echo "     cd ${PROJECT_DIR}/langfuse && docker compose logs langfuse-web --tail 20"
fi

# ── 4. Installer le SDK Langfuse dans le venv LangGraph ─────────────────────
echo "[4/5] Installation du SDK Langfuse..."

cd "${PROJECT_DIR}"
source .venv/bin/activate 2>/dev/null || true
pip install -q langfuse 2>/dev/null

# Ajouter au requirements.txt
grep -q "langfuse" requirements.txt || echo "langfuse>=2.0.0" >> requirements.txt

echo "  -> SDK langfuse installe"

# ── 5. Ajouter les variables Langfuse au .env LangGraph ─────────────────────
echo "[5/5] Configuration du tracing Langfuse..."

if ! grep -q "LANGFUSE_HOST" "${PROJECT_DIR}/.env"; then
    cat >> "${PROJECT_DIR}/.env" << 'EOF'

# ── Langfuse (observabilite self-hosted) ─────
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=A_CONFIGURER_APRES_INSCRIPTION
LANGFUSE_SECRET_KEY=A_CONFIGURER_APRES_INSCRIPTION
EOF
    echo "  -> Variables Langfuse ajoutees au .env"
else
    echo "  -> Variables Langfuse deja presentes"
fi

# Ouvrir le port 3000 si UFW est actif
if command -v ufw &> /dev/null && ufw status | grep -q active; then
    ufw allow from 192.168.0.0/16 to any port 3000 comment "Langfuse UI" 2>/dev/null || true
fi

echo ""
echo "==========================================="
echo "  Langfuse installe avec succes."
echo ""
echo "  Interface web : http://192.168.10.67:3000"
echo ""
echo "  Prochaines etapes :"
echo "  1. Ouvrir http://192.168.10.67:3000"
echo "  2. Creer un compte (Sign up)"
echo "  3. Creer un projet 'langgraph-multi-agent'"
echo "  4. Aller dans Settings -> API Keys"
echo "  5. Copier Public Key et Secret Key"
echo "  6. Les mettre dans ${PROJECT_DIR}/.env :"
echo "     LANGFUSE_PUBLIC_KEY=pk-..."
echo "     LANGFUSE_SECRET_KEY=sk-..."
echo "  7. Rebuild LangGraph :"
echo "     cd ${PROJECT_DIR} && docker compose up -d --build langgraph-api"
echo ""
echo "  Gestion Langfuse :"
echo "  cd ${PROJECT_DIR}/langfuse"
echo "  docker compose ps      # statut"
echo "  docker compose logs -f  # logs"
echo "  docker compose down     # arreter"
echo "==========================================="
