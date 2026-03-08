#!/bin/bash
###############################################################################
# Script 2/3 : Installation de Docker sur la VM Ubuntu
#
# A executer depuis la VM Ubuntu (apres installation de l'OS).
# Usage : ./02-install-docker.sh
###############################################################################
set -euo pipefail

echo "==========================================="
echo "  Script 2/3 : Installation Docker"
echo "==========================================="
echo ""

# ── 1. Mise a jour systeme ───────────────────────────────────────────────────
echo "[1/6] Mise a jour du systeme..."
sudo apt update && sudo apt upgrade -y

# ── 2. Outils de base ───────────────────────────────────────────────────────
echo "[2/6] Installation des outils de base..."
sudo apt install -y \
  curl wget git vim htop tmux \
  ca-certificates gnupg lsb-release \
  ufw fail2ban qemu-guest-agent \
  python3 python3-pip python3-venv

# Activer le guest agent Proxmox
sudo systemctl enable --now qemu-guest-agent

# Configurer le hostname
sudo hostnamectl set-hostname langgraph-agents

# ── 3. Ajout du repo Docker ─────────────────────────────────────────────────
echo "[3/6] Ajout du depot Docker officiel..."
sudo install -m 0755 -d /etc/apt/keyrings

if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
      sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
fi

echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# ── 4. Installation Docker ──────────────────────────────────────────────────
echo "[4/6] Installation de Docker Engine..."
sudo apt update
sudo apt install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Ajouter l'utilisateur courant au groupe docker
sudo usermod -aG docker "$USER"

# ── 5. Configuration Docker production ──────────────────────────────────────
echo "[5/6] Configuration Docker pour la production..."
sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
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

sudo systemctl restart docker

# ── 6. Verification ─────────────────────────────────────────────────────────
echo "[6/6] Verification de l'installation..."
echo ""
echo "  Docker Engine : $(docker --version)"
echo "  Compose       : $(docker compose version)"
echo ""

# ── 7. Firewall de base ─────────────────────────────────────────────────────
echo "[bonus] Configuration du firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
# API LangGraph - reseau local uniquement
sudo ufw allow from 192.168.1.0/24 to any port 8123
# Langfuse UI - reseau local uniquement
sudo ufw allow from 192.168.1.0/24 to any port 3000
sudo ufw --force enable

echo ""
echo "==========================================="
echo "  Docker installe avec succes."
echo ""
echo "  IMPORTANT : Deconnectez-vous et"
echo "  reconnectez-vous pour que le groupe"
echo "  'docker' soit pris en compte."
echo ""
echo "  Prochaine etape :"
echo "  Executer le script 03-install-langgraph.sh"
echo "==========================================="
