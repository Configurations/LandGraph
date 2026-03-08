#!/bin/bash
###############################################################################
# Script 00 : Configuration LXC Proxmox pour Docker
#
# A executer sur l'HOTE PROXMOX (pas dans le container).
# Configure un container LXC pour supporter Docker sans problemes.
#
# Resout :
#   - AppArmor "permission denied"
#   - Network unreachable (pas de DHCP)
#   - Docker sysctl errors
#   - Nesting / cgroup permissions
#
# Usage : ./00-configure-lxc.sh [CTID]
# Exemple : ./00-configure-lxc.sh 110
###############################################################################
set -euo pipefail

CTID="${1:-}"

if [ -z "${CTID}" ]; then
    echo "Usage: $0 <CTID>"
    echo ""
    echo "Containers disponibles :"
    pct list
    exit 1
fi

# Verifier que le container existe
if ! pct status "${CTID}" &>/dev/null; then
    echo "ERREUR : Container ${CTID} introuvable."
    pct list
    exit 1
fi

CONF="/etc/pve/lxc/${CTID}.conf"

echo "==========================================="
echo "  Configuration LXC ${CTID} pour Docker"
echo "==========================================="
echo ""

# ── 1. Arreter le container ──────────────────────────────────────────────────
echo "[1/5] Arret du container ${CTID}..."
pct stop "${CTID}" 2>/dev/null || true
sleep 3
echo "  -> Arrete"

# ── 2. Sauvegarder la config actuelle ────────────────────────────────────────
echo "[2/5] Backup de la configuration..."
cp "${CONF}" "${CONF}.backup.$(date +%Y%m%d%H%M%S)"
echo "  -> Backup : ${CONF}.backup.*"

# ── 3. Lire les parametres existants ─────────────────────────────────────────
echo "[3/5] Lecture des parametres existants..."

# Extraire les valeurs actuelles
ARCH=$(grep "^arch:" "${CONF}" | head -1 || echo "arch: amd64")
CORES=$(grep "^cores:" "${CONF}" | head -1 || echo "cores: 4")
HOSTNAME=$(grep "^hostname:" "${CONF}" | head -1 || echo "hostname: docker-lxc")
MEMORY=$(grep "^memory:" "${CONF}" | head -1 || echo "memory: 8192")
NAMESERVER=$(grep "^nameserver:" "${CONF}" | head -1 || echo "nameserver: 8.8.8.8")
NET0=$(grep "^net0:" "${CONF}" | head -1 || echo "")
OSTYPE=$(grep "^ostype:" "${CONF}" | head -1 || echo "ostype: ubuntu")
ROOTFS=$(grep "^rootfs:" "${CONF}" | head -1 || echo "")
SEARCHDOMAIN=$(grep "^searchdomain:" "${CONF}" | head -1 || echo "searchdomain: 1.1.1.1")
SWAP=$(grep "^swap:" "${CONF}" | head -1 || echo "swap: 1024")

echo "  -> ${HOSTNAME}"
echo "  -> ${CORES}, ${MEMORY}"

# ── 4. Ecrire la configuration propre ────────────────────────────────────────
echo "[4/5] Ecriture de la configuration Docker-ready..."

cat > "${CONF}" << EOF
${ARCH}
${CORES}
features: nesting=1,keyctl=1
${HOSTNAME}
${MEMORY}
${NAMESERVER}
${NET0}
${OSTYPE}
${ROOTFS}
${SEARCHDOMAIN}
${SWAP}
unprivileged: 0

# Docker dans LXC — permissions necessaires
lxc.apparmor.profile: unconfined
lxc.cap.drop:
lxc.mount.auto: proc:rw sys:rw cgroup:rw
lxc.cgroup2.devices.allow: a
lxc.mount.entry: /sys/kernel/security sys/kernel/security none bind,optional 0 0
EOF

echo "  -> Configuration ecrite"
echo ""
echo "  Contenu :"
cat "${CONF}"
echo ""

# ── 5. Demarrer et configurer le reseau interne ─────────────────────────────
echo "[5/5] Demarrage du container..."
pct start "${CTID}"
sleep 5

# Verifier que le container est running
if pct status "${CTID}" | grep -q running; then
    echo "  -> Container demarre"
else
    echo "  -> ERREUR : Container ne demarre pas. Verifiez les logs :"
    echo "     journalctl -xe | grep ${CTID}"
    exit 1
fi

# Configurer le reseau DHCP dans le container (systemd-networkd)
echo ""
echo "  Configuration reseau DHCP..."
pct exec "${CTID}" -- bash -c '
# Creer la config reseau si elle n existe pas
if [ ! -f /etc/systemd/network/20-eth0.network ]; then
    cat > /etc/systemd/network/20-eth0.network << NETEOF
[Match]
Name=eth0

[Network]
DHCP=yes

[DHCP]
UseDNS=yes
UseRoutes=yes
NETEOF
    systemctl restart systemd-networkd
    echo "  -> Config DHCP creee"
else
    echo "  -> Config DHCP deja presente"
fi

# Attendre l IP
sleep 5
IP=$(ip -4 addr show eth0 2>/dev/null | grep inet | awk "{print \$2}" | head -1)
if [ -n "$IP" ]; then
    echo "  -> IP obtenue : $IP"
else
    echo "  -> ATTENTION : pas d IP obtenue. Verifiez le DHCP."
fi

# Tester la connectivite
if ping -c 1 8.8.8.8 &>/dev/null; then
    echo "  -> Internet : OK"
else
    echo "  -> ATTENTION : pas de connectivite internet"
fi
'

# Verifier que Docker fonctionne
echo ""
echo "  Verification Docker..."
if pct exec "${CTID}" -- docker info &>/dev/null 2>&1; then
    echo "  -> Docker : OK"
    
    # Test rapide
    pct exec "${CTID}" -- docker run --rm hello-world &>/dev/null 2>&1 && \
        echo "  -> Docker run : OK" || \
        echo "  -> Docker run : premier lancement peut etre lent"
else
    echo "  -> Docker pas installe ou pas demarre"
    echo "     Installez Docker avec le script 02-install-docker.sh"
fi

echo ""
echo "==========================================="
echo "  Container ${CTID} configure pour Docker."
echo ""
echo "  Résumé des parametres :"
echo "  - unprivileged: 0 (privileged)"
echo "  - nesting + keyctl actives"
echo "  - AppArmor: unconfined"
echo "  - cgroup2: all devices allowed"
echo "  - /sys/kernel/security monte"
echo "  - Reseau: DHCP sur eth0"
echo ""
echo "  Pour entrer dans le container :"
echo "    pct enter ${CTID}"
echo ""
echo "  Pour voir les logs :"
echo "    pct exec ${CTID} -- docker compose ps"
echo "==========================================="
