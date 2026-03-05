#!/bin/bash
###############################################################################
# Script 1/3 : Creation de la VM LangGraph sur Proxmox
#
# A executer depuis le shell Proxmox (hote).
# Usage : ./01-proxmox-create-vm.sh [VMID]
###############################################################################
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
VMID=${1:-200}
VM_NAME="langgraph-agents"
CORES=8
MEMORY=16384
DISK_SIZE="30G"
STORAGE="local-lvm"
BRIDGE="vmbr0"
ISO_PATH="local:iso/ubuntu-24.04-live-server-amd64.iso"

echo "==========================================="
echo "  Script 1/3 : Creation VM Proxmox"
echo "==========================================="
echo ""
echo "  VM ID     : ${VMID}"
echo "  Nom       : ${VM_NAME}"
echo "  CPU       : ${CORES} cores"
echo "  RAM       : ${MEMORY} MB"
echo "  Disque    : ${DISK_SIZE}"
echo "  Reseau    : ${BRIDGE}"
echo ""

# ── Verification pre-requis ──────────────────────────────────────────────────
if ! command -v qm &> /dev/null; then
    echo "ERREUR : 'qm' introuvable. Ce script doit etre execute sur l'hote Proxmox."
    exit 1
fi

if qm status "${VMID}" &> /dev/null; then
    echo "ERREUR : La VM ${VMID} existe deja. Choisissez un autre ID ou supprimez-la."
    exit 1
fi

# ── Creation de la VM ────────────────────────────────────────────────────────
echo "[1/3] Creation de la VM..."
qm create "${VMID}" \
  --name "${VM_NAME}" \
  --cores "${CORES}" \
  --memory "${MEMORY}" \
  --machine q35 \
  --bios ovmf \
  --efidisk0 "${STORAGE}:1,efitype=4m,pre-enrolled-keys=1" \
  --scsi0 "${STORAGE}:${DISK_SIZE},iothread=1,discard=on,ssd=1" \
  --scsihw virtio-scsi-single \
  --net0 "virtio,bridge=${BRIDGE}" \
  --ide2 "${ISO_PATH},media=cdrom" \
  --boot 'order=scsi0;ide2' \
  --ostype l26 \
  --cpu host \
  --numa 1 \
  --agent enabled=1 \
  --tags "langgraph,ai-agents,production" \
  --description "LangGraph Multi-Agent Platform"

echo "[2/3] Demarrage de la VM..."
qm start "${VMID}"

echo "[3/3] Attente du demarrage..."
sleep 5

echo ""
echo "==========================================="
echo "  VM ${VMID} creee et demarree."
echo ""
echo "  Prochaines etapes :"
echo "  1. Installer Ubuntu 24.04 via la console VNC Proxmox"
echo "  2. Configurer le reseau (IP statique recommandee)"
echo "  3. Se connecter en SSH a la VM"
echo "  4. Executer le script 02-install-docker.sh"
echo "==========================================="
