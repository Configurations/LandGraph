#!/bin/bash
###############################################################################
# Script 00 : Creation / Configuration LXC Proxmox pour Docker
#
# A executer sur l'HOTE PROXMOX (pas dans le container).
#
# Deux modes automatiques :
#   - Si le container N'EXISTE PAS  -> creation + configuration Docker
#   - Si le container EXISTE DEJA   -> reconfiguration Docker (avec backup)
#
# Resout :
#   - AppArmor "permission denied"
#   - Network unreachable (pas de DHCP)
#   - Docker sysctl errors
#   - Nesting / cgroup permissions
#   - UID/GID remapping (unprivileged -> privileged)
#
# Usage : ./00-create-lxc.sh [CTID]
# Exemple : ./00-create-lxc.sh 200
#
# Pre-requis (creation uniquement) : un template Ubuntu dans le storage local.
#   pveam update
#   pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
###############################################################################
set -euo pipefail

# ── Configuration par defaut ─────────────────────────────────────────────────
CTID="${1:-}"
CT_NAME="langgraph-agents"
CORES=4
MEMORY=8192
SWAP=1024
DISK_SIZE=30
STORAGE="local-lvm"
BRIDGE="vmbr0"

if [ -z "${CTID}" ]; then
    echo "Usage: $0 <CTID>"
    echo ""
    echo "Containers disponibles :"
    pct list
    exit 1
fi

CONF="/etc/pve/lxc/${CTID}.conf"

# ══════════════════════════════════════════════════════════════════════════════
# Detecter le mode : CREATION ou RECONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
if pct status "${CTID}" &>/dev/null; then
    MODE="reconfigure"
    echo "==========================================="
    echo "  Container ${CTID} detecte -> RECONFIGURATION"
    echo "==========================================="
else
    MODE="create"
    echo "==========================================="
    echo "  Container ${CTID} inexistant -> CREATION"
    echo "==========================================="
fi
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# MODE CREATION
# ══════════════════════════════════════════════════════════════════════════════
if [ "${MODE}" = "create" ]; then

    # ── Detecter le template Ubuntu ──────────────────────────────────────────
    TEMPLATE=$(pveam list local 2>/dev/null | grep -i "ubuntu-24" | awk '{print $1}' | head -1)
    [ -z "${TEMPLATE}" ] && TEMPLATE=$(pveam list local 2>/dev/null | grep -i "ubuntu-22" | awk '{print $1}' | head -1)
    [ -z "${TEMPLATE}" ] && TEMPLATE=$(pveam list local 2>/dev/null | grep -i "ubuntu" | awk '{print $1}' | head -1)

    if [ -z "${TEMPLATE}" ]; then
        echo "ERREUR : Aucun template Ubuntu trouve."
        echo ""
        echo "Templates disponibles :"
        pveam list local
        echo ""
        echo "Pour telecharger Ubuntu 24.04 :"
        echo "  pveam update"
        echo "  pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
        exit 1
    fi

    echo "  CT ID     : ${CTID}"
    echo "  Nom       : ${CT_NAME}"
    echo "  CPU       : ${CORES} cores"
    echo "  RAM       : ${MEMORY} MB"
    echo "  Swap      : ${SWAP} MB"
    echo "  Disque    : ${DISK_SIZE}G"
    echo "  Reseau    : ${BRIDGE}"
    echo "  Template  : ${TEMPLATE}"
    echo ""

    # ── Creer le container (directement privileged) ──────────────────────────
    echo "[1/4] Creation du container LXC..."
    pct create "${CTID}" "${TEMPLATE}" \
      --hostname "${CT_NAME}" \
      --cores "${CORES}" \
      --memory "${MEMORY}" \
      --swap "${SWAP}" \
      --rootfs "${STORAGE}:${DISK_SIZE}" \
      --net0 "name=eth0,bridge=${BRIDGE},firewall=1,ip=dhcp,type=veth" \
      --nameserver "8.8.8.8" \
      --searchdomain "1.1.1.1" \
      --ostype ubuntu \
      --unprivileged 0 \
      --features "nesting=1,keyctl=1" \
      --tags "langgraph,ai-agents,production" \
      --description "LangGraph Multi-Agent Platform"
    echo "  -> Container cree"

    # ── Ajouter la config Docker ─────────────────────────────────────────────
    echo "[2/4] Ajout de la configuration Docker-ready..."
    cat >> "${CONF}" << 'EOF'

# Docker dans LXC — permissions necessaires
lxc.apparmor.profile: unconfined
lxc.cap.drop:
lxc.mount.auto: proc:rw sys:rw cgroup:rw
lxc.cgroup2.devices.allow: a
lxc.mount.entry: /sys/kernel/security sys/kernel/security none bind,optional 0 0
EOF
    echo "  -> Configuration Docker ajoutee"

    STEP_START=3
    STEP_TOTAL=4

# ══════════════════════════════════════════════════════════════════════════════
# MODE RECONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
else

    # ── Detecter si conversion unprivileged -> privileged ────────────────────
    WAS_UNPRIVILEGED=0
    if grep -q "^unprivileged: 1" "${CONF}" 2>/dev/null; then
        WAS_UNPRIVILEGED=1
        echo "  [!] Container actuellement unprivileged -> sera converti en privileged"
        echo "      Les UIDs/GIDs du filesystem seront corriges automatiquement."
        echo ""
    fi

    # ── Arreter le container ─────────────────────────────────────────────────
    echo "[1/6] Arret du container ${CTID}..."
    pct stop "${CTID}" 2>/dev/null || true
    sleep 3
    echo "  -> Arrete"

    # ── Backup ───────────────────────────────────────────────────────────────
    echo "[2/6] Backup de la configuration..."
    cp "${CONF}" "${CONF}.backup.$(date +%Y%m%d%H%M%S)"
    echo "  -> Backup : ${CONF}.backup.*"

    # ── Lire les parametres existants ────────────────────────────────────────
    echo "[3/6] Lecture des parametres existants..."
    ARCH=$(grep "^arch:" "${CONF}" | head -1 || echo "arch: amd64")
    CORES_CONF=$(grep "^cores:" "${CONF}" | head -1 || echo "cores: 4")
    HOSTNAME_CONF=$(grep "^hostname:" "${CONF}" | head -1 || echo "hostname: docker-lxc")
    MEMORY_CONF=$(grep "^memory:" "${CONF}" | head -1 || echo "memory: 8192")
    NAMESERVER=$(grep "^nameserver:" "${CONF}" | head -1 || echo "nameserver: 8.8.8.8")
    NET0=$(grep "^net0:" "${CONF}" | head -1 || echo "")
    OSTYPE=$(grep "^ostype:" "${CONF}" | head -1 || echo "ostype: ubuntu")
    ROOTFS=$(grep "^rootfs:" "${CONF}" | head -1 || echo "")
    SEARCHDOMAIN=$(grep "^searchdomain:" "${CONF}" | head -1 || echo "searchdomain: 1.1.1.1")
    SWAP_CONF=$(grep "^swap:" "${CONF}" | head -1 || echo "swap: 1024")
    echo "  -> ${HOSTNAME_CONF}"
    echo "  -> ${CORES_CONF}, ${MEMORY_CONF}"

    # ── Remapping UIDs si necessaire ─────────────────────────────────────────
    if [ "${WAS_UNPRIVILEGED}" -eq 1 ]; then
        echo "[4/6] Correction des UIDs/GIDs (unprivileged -> privileged)..."

        # Monter le filesystem du container
        pct mount "${CTID}" 2>&1 || true
        MOUNTPOINT="/var/lib/lxc/${CTID}/rootfs"

        if [ ! -d "${MOUNTPOINT}" ]; then
            echo "  -> ERREUR : impossible de trouver le rootfs monte sur ${MOUNTPOINT}"
            echo "     Verifiez manuellement : pct mount ${CTID}"
            exit 1
        fi

        echo "  -> Rootfs monte sur : ${MOUNTPOINT}"

        COUNT_UID=$(find "${MOUNTPOINT}" -uid 100000 2>/dev/null | head -100 | wc -l)
        echo "  -> Fichiers avec UID 100000 detectes : ${COUNT_UID}+"

        if [ "${COUNT_UID}" -gt 0 ]; then
            echo "  -> Remapping UIDs 100000-165535 vers 0-65535..."
            cd "${MOUNTPOINT}"
            find . -wholename ./proc -prune -o -wholename ./sys -prune -o -print0 2>/dev/null | \
            while IFS= read -r -d '' file; do
                FUID=$(stat -c '%u' "$file" 2>/dev/null) || continue
                FGID=$(stat -c '%g' "$file" 2>/dev/null) || continue
                NEW_UID="${FUID}"
                NEW_GID="${FGID}"
                if [ "${FUID}" -ge 100000 ] && [ "${FUID}" -le 165535 ]; then
                    NEW_UID=$((FUID - 100000))
                fi
                if [ "${FGID}" -ge 100000 ] && [ "${FGID}" -le 165535 ]; then
                    NEW_GID=$((FGID - 100000))
                fi
                if [ "${NEW_UID}" != "${FUID}" ] || [ "${NEW_GID}" != "${FGID}" ]; then
                    chown -h "${NEW_UID}:${NEW_GID}" "$file" 2>/dev/null || true
                fi
            done
            cd /
            echo "  -> Remapping termine"
        else
            echo "  -> Pas de remapping necessaire (UIDs deja corrects)"
        fi

        pct unmount "${CTID}"
        echo "  -> Rootfs demonte"
    else
        echo "[4/6] Deja privileged, skip remapping UIDs."
    fi

    # ── Ecrire la configuration Docker-ready ─────────────────────────────────
    echo "[5/6] Ecriture de la configuration Docker-ready..."
    cat > "${CONF}" << EOF
${ARCH}
${CORES_CONF}
features: nesting=1,keyctl=1
${HOSTNAME_CONF}
${MEMORY_CONF}
${NAMESERVER}
${NET0}
${OSTYPE}
${ROOTFS}
${SEARCHDOMAIN}
${SWAP_CONF}
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

    STEP_START=6
    STEP_TOTAL=6
fi

# ══════════════════════════════════════════════════════════════════════════════
# COMMUN : Demarrage + configuration reseau
# ══════════════════════════════════════════════════════════════════════════════

echo "[${STEP_START}/${STEP_TOTAL}] Demarrage du container..."
pct start "${CTID}"
sleep 5

if pct status "${CTID}" | grep -q running; then
    echo "  -> Container demarre"
else
    echo "  -> ERREUR : Container ne demarre pas. Verifiez les logs :"
    echo "     journalctl -xe | grep ${CTID}"
    exit 1
fi

# ── Configuration reseau DHCP ────────────────────────────────────────────────
echo ""
echo "  Configuration reseau DHCP..."
pct exec "${CTID}" -- bash -c '
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

sleep 5
IP=$(ip -4 addr show eth0 2>/dev/null | grep inet | awk "{print \$2}" | head -1)
if [ -n "$IP" ]; then
    echo "  -> IP obtenue : $IP"
else
    echo "  -> ATTENTION : pas d IP obtenue. Verifiez le DHCP."
fi

if ping -c 1 8.8.8.8 &>/dev/null; then
    echo "  -> Internet : OK"
else
    echo "  -> ATTENTION : pas de connectivite internet"
fi
'

# ── Verification Docker ─────────────────────────────────────────────────────
echo ""
echo "  Verification Docker..."
if pct exec "${CTID}" -- docker info &>/dev/null 2>&1; then
    echo "  -> Docker : OK"
    pct exec "${CTID}" -- docker run --rm hello-world &>/dev/null 2>&1 && \
        echo "  -> Docker run : OK" || \
        echo "  -> Docker run : premier lancement peut etre lent"
else
    echo "  -> Docker pas encore installe"
    echo "     Executer le script 02-install-docker.sh dans le container"
fi

# ── Resume ───────────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
echo "  Container ${CTID} pret pour Docker."
echo ""
echo "  Mode        : ${MODE}"
echo "  Resume :"
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
echo "  Prochaine etape :"
echo "    Executer 02-install-docker.sh dans le container"
echo "==========================================="