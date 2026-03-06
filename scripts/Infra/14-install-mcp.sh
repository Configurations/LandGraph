#!/bin/bash
###############################################################################
# Script 14 : Installation interactive de MCP servers
#
# Interroge le MCP Registry officiel pour trouver et installer des serveurs.
# L'utilisateur cherche par mot-cle, choisit un serveur, et le script
# configure automatiquement la connexion dans LangGraph.
#
# Usage : ./14-install-mcp.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
MCP_REGISTRY="https://registry.modelcontextprotocol.io/v0/servers"
MCP_CONFIG="${PROJECT_DIR}/config/mcp_servers.json"

echo "==========================================="
echo "  Installation interactive MCP"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── Pre-requis ───────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "Installation de Node.js (requis pour les MCP servers npx)..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null
    apt-get install -y nodejs 2>/dev/null
fi

if ! command -v jq &>/dev/null; then
    echo "Installation de jq..."
    apt-get install -y jq 2>/dev/null
fi

source .venv/bin/activate 2>/dev/null || true
pip install -q langchain-mcp-adapters mcp 2>/dev/null
grep -q "langchain-mcp-adapters" requirements.txt 2>/dev/null || echo "langchain-mcp-adapters>=0.2.0" >> requirements.txt

# Creer le fichier de config MCP s'il n'existe pas
mkdir -p config
if [ ! -f "${MCP_CONFIG}" ]; then
    echo '{"servers": {}}' > "${MCP_CONFIG}"
fi

# ── Variables globales ───────────────────────────────────────────────────────
LAST_SEARCH_RESULT=""
LAST_SEARCH_COUNT=0

# ── Fonctions ────────────────────────────────────────────────────────────────

search_servers() {
    local query="$1"
    local result
    result=$(curl -s "${MCP_REGISTRY}?search=${query}&limit=20" 2>/dev/null)

    if [ -z "${result}" ] || ! echo "${result}" | jq -e '.servers' &>/dev/null; then
        echo "  Erreur : impossible de contacter le registry MCP."
        return 1
    fi

    local count
    count=$(echo "${result}" | jq '.servers | length')

    if [ "${count}" -eq 0 ]; then
        echo "  Aucun serveur trouve pour '${query}'."
        return 1
    fi

    echo ""
    echo "  ${count} resultats pour '${query}' :"
    echo "  ────────────────────────────────────────"
    echo ""

    echo "${result}" | jq -r '
        .servers | to_entries[] |
        "  \(.key + 1)) \(.value.server.name // "inconnu")\n     \(.value.server.description // "pas de description" | .[0:100])\n"
    '

    echo "  0) Nouvelle recherche"
    echo "  q) Quitter"
    echo ""

    LAST_SEARCH_RESULT="${result}"
    LAST_SEARCH_COUNT="${count}"
}

get_server_details() {
    local index="$1"
    local server_json
    server_json=$(echo "${LAST_SEARCH_RESULT}" | jq ".servers[${index}]")

    local name description
    name=$(echo "${server_json}" | jq -r '.server.name // "inconnu"')
    description=$(echo "${server_json}" | jq -r '.server.description // "pas de description"')

    echo ""
    echo "  ═══════════════════════════════════════"
    echo "  ${name}"
    echo "  ═══════════════════════════════════════"
    echo "  ${description}" | fold -s -w 70 | sed 's/^/  /'
    echo ""

    # Packages disponibles
    local pkg_count
    pkg_count=$(echo "${server_json}" | jq '.server.packages // [] | length')

    if [ "${pkg_count}" -gt 0 ]; then
        echo "  Packages disponibles :"
        local i
        for i in $(seq 0 $((pkg_count - 1))); do
            local reg_type identifier transport
            reg_type=$(echo "${server_json}" | jq -r ".server.packages[${i}].registryType // \"?\"")
            identifier=$(echo "${server_json}" | jq -r ".server.packages[${i}].identifier // \"?\"")
            transport=$(echo "${server_json}" | jq -r ".server.packages[${i}].transport.type // \"stdio\"")
            echo "    ${reg_type} : ${identifier} (${transport})"
        done
    else
        echo "  Aucun package d'installation detecte."
    fi

    # Variables d'environnement
    local env_vars
    env_vars=$(echo "${server_json}" | jq -r '
        [.server.packages[]?.environmentVariables // [] | .[]] | unique_by(.name) |
        .[] | "    \(.name) — \(.description // "requis")"
    ' 2>/dev/null || true)

    if [ -n "${env_vars}" ]; then
        echo ""
        echo "  Variables d'environnement :"
        echo "${env_vars}"
    fi

    echo ""
    echo "  ────────────────────────────────────────"
    echo "  i) Installer ce serveur"
    echo "  0) Retour aux resultats"
    echo "  q) Quitter"
    echo ""
}

install_server() {
    local index="$1"
    local server_json
    server_json=$(echo "${LAST_SEARCH_RESULT}" | jq ".servers[${index}]")

    local name
    name=$(echo "${server_json}" | jq -r '.server.name // "inconnu"')

    echo ""
    echo "  Installation de ${name}..."

    # Determiner le type de package et la commande
    local reg_type identifier transport
    reg_type=$(echo "${server_json}" | jq -r '.server.packages[0].registryType // "npm"')
    identifier=$(echo "${server_json}" | jq -r '.server.packages[0].identifier // ""')
    transport=$(echo "${server_json}" | jq -r '.server.packages[0].transport.type // "stdio"')

    if [ -z "${identifier}" ]; then
        echo "  ERREUR : pas de package identifie pour ce serveur."
        return 1
    fi

    # Commande selon le type
    local cmd args_json
    if [ "${reg_type}" = "npm" ]; then
        cmd="npx"
        args_json=$(echo "${server_json}" | jq -c '["-y"] + [.server.packages[0].identifier]')
    elif [ "${reg_type}" = "pypi" ]; then
        cmd="uvx"
        args_json=$(echo "${server_json}" | jq -c '[.server.packages[0].identifier]')
    else
        cmd="npx"
        args_json="[\"-y\", \"${identifier}\"]"
    fi

    # Variables d'environnement
    local env_json
    env_json=$(echo "${server_json}" | jq -c '
        [.server.packages[0].environmentVariables // [] | .[]] |
        if length > 0 then
            reduce .[] as $var ({}; . + {($var.name): "A_CONFIGURER"})
        else
            {}
        end
    ' 2>/dev/null || echo '{}')

    # ID simple
    local server_id
    server_id=$(echo "${name}" | sed 's/.*\///' | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//')

    # Ajouter au fichier de config
    local new_entry
    new_entry=$(jq -n \
        --arg cmd "${cmd}" \
        --argjson args "${args_json}" \
        --arg transport "${transport}" \
        --argjson env "${env_json}" \
        --arg name "${name}" \
        '{
            command: $cmd,
            args: $args,
            transport: $transport,
            env: $env,
            name: $name,
            enabled: true
        }')

    local tmp
    tmp=$(mktemp)
    jq --arg id "${server_id}" --argjson entry "${new_entry}" \
        '.servers[$id] = $entry' "${MCP_CONFIG}" > "${tmp}" && mv "${tmp}" "${MCP_CONFIG}"

    echo "  -> ${name} ajoute dans config/mcp_servers.json"
    echo "     ID        : ${server_id}"
    echo "     Commande  : ${cmd} ${identifier}"
    echo "     Transport : ${transport}"

    # Ajouter les variables manquantes au .env
    local env_vars
    env_vars=$(echo "${env_json}" | jq -r 'keys[]' 2>/dev/null || true)
    if [ -n "${env_vars}" ]; then
        echo ""
        echo "  Variables a configurer dans .env :"
        for var in ${env_vars}; do
            if ! grep -q "^${var}=" .env 2>/dev/null; then
                echo "${var}=A_CONFIGURER" >> .env
                echo "    -> ${var} ajoute (a remplir !)"
            else
                echo "    -> ${var} deja present"
            fi
        done
    fi

    echo ""
    echo "  ✅ ${name} installe."
    echo ""
}

show_installed() {
    echo ""
    echo "  Serveurs MCP configures :"
    echo "  ────────────────────────────────────────"

    local count
    count=$(jq '.servers | length' "${MCP_CONFIG}")

    if [ "${count}" -eq 0 ]; then
        echo "  (aucun)"
    else
        jq -r '.servers | to_entries[] |
            "  \(if .value.enabled then "✅" else "❌" end) \(.key) — \(.value.name // .key) [\(.value.transport // "stdio")]"
        ' "${MCP_CONFIG}"
    fi
    echo ""
}

generate_mcp_client() {
    echo "  Generation de agents/shared/mcp_client.py..."

    cat > agents/shared/mcp_client.py << 'PYTHONEOF'
"""MCP Client — Charge les MCP servers depuis config/mcp_servers.json."""
import json, logging, os, asyncio
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "mcp_servers.json"),
    os.path.join("/app", "config", "mcp_servers.json"),
]


def _load_config() -> dict:
    for path in CONFIG_PATHS:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                return json.load(f)
    return {"servers": {}}


def _resolve_env(env_dict: dict) -> dict:
    resolved = {}
    for key, val in env_dict.items():
        env_val = os.getenv(key, val)
        if env_val and env_val != "A_CONFIGURER":
            resolved[key] = env_val
    return resolved


def get_mcp_tools_sync(agent_id: str = None) -> list:
    try:
        loop = asyncio.new_event_loop()
        tools = loop.run_until_complete(_get_tools_async())
        loop.close()
        return tools
    except Exception as e:
        logger.warning(f"MCP tools unavailable: {e}")
        return []


async def _get_tools_async() -> list:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    config = _load_config()
    servers = {}

    for server_id, server_conf in config.get("servers", {}).items():
        if not server_conf.get("enabled", True):
            continue

        env = _resolve_env(server_conf.get("env", {}))
        missing = [k for k, v in server_conf.get("env", {}).items()
                    if not env.get(k)]
        if missing:
            logger.warning(f"MCP {server_id} skip — missing env: {missing}")
            continue

        entry = {
            "command": server_conf["command"],
            "args": server_conf["args"],
            "transport": server_conf.get("transport", "stdio"),
        }
        if env:
            entry["env"] = env
        servers[server_id] = entry

    if not servers:
        return []

    try:
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
        logger.info(f"MCP: {len(tools)} tools from {list(servers.keys())}")
        return tools
    except Exception as e:
        logger.error(f"MCP client error: {e}")
        return []


def get_tools_for_agent(agent_id: str) -> list:
    tools = get_mcp_tools_sync(agent_id)
    try:
        from agents.shared.rag_service import create_rag_tools
        tools.extend(create_rag_tools())
    except ImportError:
        pass
    return tools
PYTHONEOF

    echo "  -> mcp_client.py genere"
}

# ── Boucle principale ────────────────────────────────────────────────────────

echo "  Tapez un mot-cle pour chercher un serveur MCP"
echo "  Exemples : github, notion, postgres, slack, jira, filesystem"
echo ""

show_installed

while true; do
    read -rp "  🔍 Recherche (q pour quitter) : " search_input

    if [ "${search_input}" = "q" ] || [ "${search_input}" = "Q" ]; then
        break
    fi

    if [ -z "${search_input}" ]; then
        continue
    fi

    if ! search_servers "${search_input}"; then
        continue
    fi

    while true; do
        read -rp "  Choix (numero, 0=recherche, q=quitter) : " choice

        if [ "${choice}" = "q" ] || [ "${choice}" = "Q" ]; then
            break 2
        fi

        if [ "${choice}" = "0" ]; then
            break
        fi

        if ! [[ "${choice}" =~ ^[0-9]+$ ]]; then
            echo "  Tapez un numero."
            continue
        fi

        local_index=$((choice - 1))
        if [ "${local_index}" -lt 0 ] || [ "${local_index}" -ge "${LAST_SEARCH_COUNT}" ]; then
            echo "  Numero invalide (1-${LAST_SEARCH_COUNT})."
            continue
        fi

        get_server_details "${local_index}"

        while true; do
            read -rp "  Choix (i=installer, 0=retour, q=quitter) : " detail_choice

            if [ "${detail_choice}" = "q" ] || [ "${detail_choice}" = "Q" ]; then
                break 3
            fi

            if [ "${detail_choice}" = "0" ]; then
                break
            fi

            if [ "${detail_choice}" = "i" ] || [ "${detail_choice}" = "I" ]; then
                install_server "${local_index}"
                show_installed
                break
            fi

            echo "  Tapez i, 0, ou q."
        done
    done
done

# ── Finalisation ─────────────────────────────────────────────────────────────
echo ""

installed_count=$(jq '.servers | length' "${MCP_CONFIG}")

if [ "${installed_count}" -gt 0 ]; then
    echo "  Finalisation..."
    generate_mcp_client

    echo ""
    show_installed

    echo "  Prochaines etapes :"
    echo "  1. Configurez les variables dans .env :"
    echo "     nano ${PROJECT_DIR}/.env"
    echo ""
    echo "  2. Rebuild LangGraph :"
    echo "     cd ${PROJECT_DIR}"
    echo "     docker compose up -d --build langgraph-api"
    echo ""
    echo "  3. Testez dans Discord"
else
    echo "  Aucun serveur installe."
fi

echo ""
echo "==========================================="
