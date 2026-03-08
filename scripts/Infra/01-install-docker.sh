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
echo "[1/5] Mise a jour du systeme..."
apt-get update -qq
apt-get upgrade -y -qq
echo "  -> OK"

# ── 2. Outils de base ───────────────────────────────────────────────────────
echo "[2/5] Installation des outils de base..."
apt-get install -y -qq \
  curl wget git vim htop tmux \
  ca-certificates gnupg lsb-release \
  python3 python3-pip python3-venv \
  openssh-server
echo "  -> OK"

# ── 3. Ajout du repo Docker ─────────────────────────────────────────────────
echo "[3/5] Ajout du depot Docker officiel..."
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
echo "[4/5] Installation de Docker Engine..."
apt-get update -qq
apt-get install -y -qq \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
echo "  -> OK"

# ── 5. Configuration Docker production ──────────────────────────────────────
echo "[5/5] Configuration Docker pour la production..."
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
echo "  Docker installe avec succes dans le LXC."
echo ""
echo "  Prochaine etape :"
echo "  Executer le script 02-install-langgraph.sh"
echo "==========================================="
