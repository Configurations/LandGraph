#!/bin/bash
BRANCH="${1:-main}"
if [[ ! "$BRANCH" =~ ^(dev|uat|main)$ ]]; then
    echo "ERREUR : Branche invalide '${BRANCH}'. Valeurs acceptees : dev, uat, main"
    exit 1
fi

bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/${BRANCH}/scripts/Infra/02-install-langgraph.sh)" _ "${BRANCH}"
