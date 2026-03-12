#!/bin/bash
###############################################################################
# Script 01 : Installation de Docker dans un Container LXC
#
# A executer DANS le container LXC (en tant que root).
# Adapte pour LXC privileged (pas de sudo, pas de qemu-guest-agent).
#
# Usage depuis l'hote Proxmox :
#   pct exec <CTID> -- bash -c "$(wget -qLO - <URL>)"
#
# Ou depuis l'interieur du container :
#   bash -c "$(wget -qLO - <URL>)"
###############################################################################
set -euo pipefail

echo "==========================================="
echo "  Installation Docker (LXC)"
echo "==========================================="
echo ""

# ── Verifier qu'on est root ──────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo "ERREUR : Ce script doit etre execute en tant que root."
    echo "         Pas de sudo dans un LXC — connectez-vous en root."
    exit 1
fi

# ── 1. Mise a jour systeme ───────────────────────────────────────────────────
echo "[1/6] Mise a jour du systeme..."
apt-get update -qq
apt-get upgrade -y -qq
echo "  -> OK"

# ── 2. Outils de base ───────────────────────────────────────────────────────
echo "[2/6] Installation des outils de base..."
apt-get install -y -qq \
  curl wget git vim htop tmux \
  ca-certificates gnupg lsb-release \
  python3 python3-pip python3-venv \
  openssh-server
echo "  -> OK"

# ── 3. Ajout du repo Docker ─────────────────────────────────────────────────
echo "[3/6] Ajout du depot Docker officiel..."
install -m 0755 -d /etc/apt/keyrings

if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
fi

echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "  -> OK"

# ── 4. Installation Docker ──────────────────────────────────────────────────
echo "[4/6] Installation de Docker Engine..."
apt-get update -qq
apt-get install -y -qq \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
echo "  -> OK"

# ── 5. Configuration Docker production ──────────────────────────────────────
echo "[5/6] Configuration Docker pour la production..."
mkdir -p /etc/docker

tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {"base": "172.20.0.0/16", "size": 24}
  ],
  "storage-driver": "overlay2",
  "live-restore": true
}
EOF

systemctl enable docker
systemctl restart docker
echo "  -> OK"

# ── 6. Caddy reverse proxy (TLS interne) ─────────────────────────────────────
echo "[6/6] Installation de Caddy (reverse proxy)..."
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
apt-get update -qq
apt-get install -y -qq caddy

# Generate Caddyfile — multi-host reverse proxy (HTTP)
# Le SSL est gere par Cloudflare Tunnel en front — pas besoin de TLS ici.
cat > /etc/caddy/Caddyfile << 'CADDYEOF'
# ── LandGraph Reverse Proxy ──────────────────────────
# Caddy ecoute en HTTP sur le port 80.
# Cloudflare Tunnel gere le SSL cote navigateur.
#
# Pour ajouter un domaine : dupliquer un bloc @xxx / handle @xxx
# et relancer : systemctl reload caddy

:80 {
    @admin host admin.langgraph.yoops.org
    handle @admin {
        reverse_proxy localhost:8080
    }

    @hitl host hitl.langgraph.yoops.org
    handle @hitl {
        reverse_proxy localhost:8090
    }

    @api host api.langgraph.yoops.org
    handle @api {
        reverse_proxy localhost:8123
    }

    @openlit host openlit.langgraph.yoops.org
    handle @openlit {
        reverse_proxy localhost:3000
    }

    handle {
        respond "Not found" 404
    }
}
CADDYEOF

systemctl enable caddy
systemctl restart caddy
echo "  -> Caddy installe et configure"

# ── Verification ─────────────────────────────────────────────────────────────
echo ""
echo "  Verification..."
echo ""

if docker info &>/dev/null; then
    echo "  Docker Engine : $(docker --version)"
    echo "  Compose       : $(docker compose version)"
    echo ""

    # Test rapide
    if docker run --rm hello-world &>/dev/null; then
        echo "  Docker run    : OK"
    else
        echo "  Docker run    : echec (premier lancement peut etre lent)"
    fi
else
    echo "  ERREUR : Docker ne repond pas."
    echo "  Verifiez : systemctl status docker"
    exit 1
fi

echo ""
echo "==========================================="
echo "  Docker + Caddy installes dans le LXC."
echo ""
echo "  Caddy ecoute sur :80 (HTTP — SSL gere par Cloudflare Tunnel)."
echo "  Domaines configures :"
echo "    admin.langgraph.yoops.org  -> localhost:8080"
echo "    hitl.langgraph.yoops.org   -> localhost:8090"
echo "    api.langgraph.yoops.org    -> localhost:8123"
echo "    openlit.langgraph.yoops.org -> localhost:3000"
echo ""
echo "  Prochaine etape :"
echo "  1. Executer le script 02-install-langgraph.sh"
echo "  2. Configurer le tunnel Cloudflare (service: http://<IP>:80)"
echo "==========================================="
