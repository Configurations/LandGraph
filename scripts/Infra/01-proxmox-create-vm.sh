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
#   - UID/GID remapping quand on passe de unprivileged a privileged
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

# ── Detecter si le container est actuellement unprivileged ────────────────────
WAS_UNPRIVILEGED=0
if grep -q "^unprivileged: 1" "${CONF}" 2>/dev/null; then
    WAS_UNPRIVILEGED=1
    echo "  [!] Container actuellement unprivileged -> sera converti en privileged"
    echo "      Les UIDs/GIDs du filesystem seront corriges automatiquement."
    echo ""
fi

# ── 1. Arreter le container ──────────────────────────────────────────────────
echo "[1/6] Arret du container ${CTID}..."
pct stop "${CTID}" 2>/dev/null || true
sleep 3
echo "  -> Arrete"

# ── 2. Sauvegarder la config actuelle ────────────────────────────────────────
echo "[2/6] Backup de la configuration..."
cp "${CONF}" "${CONF}.backup.$(date +%Y%m%d%H%M%S)"
echo "  -> Backup : ${CONF}.backup.*"

# ── 3. Lire les parametres existants ─────────────────────────────────────────
echo "[3/6] Lecture des parametres existants..."

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

# ── 4. Corriger les UIDs/GIDs si conversion unprivileged -> privileged ───────
if [ "${WAS_UNPRIVILEGED}" -eq 1 ]; then
    echo "[4/6] Correction des UIDs/GIDs (unprivileged -> privileged)..."

    # Monter le filesystem du container
    MOUNTPOINT=$(pct mount "${CTID}" 2>&1 | grep -oP 'mounted CT \d+ successfully on \K.*' || true)

    # Si pct mount ne retourne pas le chemin, essayer le chemin par defaut
    if [ -z "${MOUNTPOINT}" ]; then
        # pct mount affiche le chemin sur stderr ou stdout selon la version
        pct unmount "${CTID}" 2>/dev/null || true
        pct mount "${CTID}"
        MOUNTPOINT="/var/lib/lxc/${CTID}/rootfs"
    fi

    if [ ! -d "${MOUNTPOINT}" ]; then
        echo "  -> ERREUR : impossible de trouver le rootfs monte."
        echo "     Essayez manuellement : pct mount ${CTID}"
        exit 1
    fi

    echo "  -> Rootfs monte sur : ${MOUNTPOINT}"

    # Compter les fichiers a corriger (pour info)
    COUNT_UID=$(find "${MOUNTPOINT}" -uid 100000 2>/dev/null | head -100 | wc -l)
    echo "  -> Fichiers avec UID 100000 detectes : ${COUNT_UID}+ "

    if [ "${COUNT_UID}" -gt 0 ]; then
        echo "  -> Remapping UIDs 100000-165535 vers 0-65535..."

        # Remapper tous les UIDs/GIDs decales par le namespace unprivileged
        # L'offset standard est 100000
        cd "${MOUNTPOINT}"

        # Methode robuste : parcourir tous les fichiers et decaler
        find . -wholename ./proc -prune -o -wholename ./sys -prune -o -print0 2>/dev/null | \
        while IFS= read -r -d '' file; do
            # Lire UID/GID actuels
            FUID=$(stat -c '%u' "$file" 2>/dev/null) || continue
            FGID=$(stat -c '%g' "$file" 2>/dev/null) || continue

            NEW_UID="${FUID}"
            NEW_GID="${FGID}"

            # Decaler si dans la plage 100000-165535
            if [ "${FUID}" -ge 100000 ] && [ "${FUID}" -le 165535 ]; then
                NEW_UID=$((FUID - 100000))
            fi
            if [ "${FGID}" -ge 100000 ] && [ "${FGID}" -le 165535 ]; then
                NEW_GID=$((FGID - 100000))
            fi

            # Appliquer si changement necessaire
            if [ "${NEW_UID}" != "${FUID}" ] || [ "${NEW_GID}" != "${FGID}" ]; then
                chown -h "${NEW_UID}:${NEW_GID}" "$file" 2>/dev/null || true
            fi
        done

        cd /
        echo "  -> Remapping termine"
    else
        echo "  -> Pas de remapping necessaire (UIDs deja corrects)"
    fi

    # Demonter
    pct unmount "${CTID}"
    echo "  -> Rootfs demonte"
else
    echo "[4/6] Pas de conversion unprivileged -> privileged, skip remapping UIDs."
fi

# ── 5. Ecrire la configuration propre ────────────────────────────────────────
echo "[5/6] Ecriture de la configuration Docker-ready..."

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

# ── 6. Demarrer et configurer le reseau interne ─────────────────────────────
echo "[6/6] Demarrage du container..."
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
echo "  Resume des parametres :"
echo "  - unprivileged: 0 (privileged)"
echo "  - nesting + keyctl actives"
echo "  - AppArmor: unconfined"
echo "  - cgroup2: all devices allowed"
echo "  - /sys/kernel/security monte"
echo "  - Reseau: DHCP sur eth0"
if [ "${WAS_UNPRIVILEGED}" -eq 1 ]; then
echo "  - UIDs/GIDs: remappe de 100000+ vers 0+"
fi
echo ""
echo "  Pour entrer dans le container :"
echo "    pct enter ${CTID}"
echo ""
echo "  Pour voir les logs :"
echo "    pct exec ${CTID} -- docker compose ps"
echo "==========================================="