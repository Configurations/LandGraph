#!/bin/bash
###############################################################################
# Script 14 : Installation interactive MCP — Agent + Service + Parametrage
#
# Flow :
#   1. Choisir un agent dans la liste
#   2. Chercher un serveur MCP dans le registry
#   3. Configurer les variables d'environnement :
#      - Si le service est deja configure : reutiliser ou creer un nouveau
#      - Nouveau parametrage = suffixe personnalise (ex: _PERSO, _WORK)
#   4. Sauvegarder le mapping agent <-> MCP <-> parametrage
#
# Fichiers generes :
#   config/mcp_servers.json    — serveurs MCP installes (avec parametrages)
#   config/agent_mcp_access.json — mapping agent -> [mcp_ids]
#   agents/shared/mcp_client.py — client Python qui lit les configs
#
# Usage : ./14-install-mcp.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
MCP_REGISTRY="https://registry.modelcontextprotocol.io/v0/servers"
MCP_CONFIG="${PROJECT_DIR}/config/mcp_servers.json"
AGENT_ACCESS="${PROJECT_DIR}/config/agent_mcp_access.json"
ENV_FILE="${PROJECT_DIR}/.env"

echo "==========================================="
echo "  Installation interactive MCP"
echo "  Agent → Service → Parametrage"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── Pre-requis ───────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "Installation de Node.js..."
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

mkdir -p config
[ ! -f "${MCP_CONFIG}" ] && echo '{"servers": {}}' > "${MCP_CONFIG}"
[ ! -f "${AGENT_ACCESS}" ] && echo '{}' > "${AGENT_ACCESS}"

# ── Liste des agents ─────────────────────────────────────────────────────────
AGENTS=(
    "orchestrator:Orchestrateur:Routing et coordination"
    "requirements_analyst:Analyste:PRD, user stories, MoSCoW"
    "ux_designer:Designer UX:Wireframes, design system"
    "architect:Architecte:ADRs, schemas, specs techniques"
    "planner:Planificateur:Sprints, estimations, roadmap"
    "lead_dev:Lead Dev:Supervision dev, code review, PRs"
    "dev_frontend_web:Dev Frontend:Code React/Vue, composants UI"
    "dev_backend_api:Dev Backend:APIs, migrations, logique metier"
    "dev_mobile:Dev Mobile:Flutter, React Native, mobile"
    "qa_engineer:QA Engineer:Tests, validation, rapports qualite"
    "devops_engineer:DevOps:CI/CD, Docker, infra, monitoring"
    "docs_writer:Documentaliste:README, guides, changelogs"
    "legal_advisor:Avocat:RGPD, licences, conformite"
)

# ── Variables globales ───────────────────────────────────────────────────────
LAST_SEARCH_RESULT=""
LAST_SEARCH_COUNT=0
SELECTED_AGENT_ID=""
SELECTED_AGENT_NAME=""

# ── Fonctions .env ───────────────────────────────────────────────────────────

env_var_exists() {
    grep -q "^${1}=" "${ENV_FILE}" 2>/dev/null
}

env_var_get() {
    grep "^${1}=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-
}

env_var_set() {
    local var_name="$1"
    local var_value="$2"
    if env_var_exists "${var_name}"; then
        local tmp
        tmp=$(mktemp)
        sed "s|^${var_name}=.*|${var_name}=${var_value}|" "${ENV_FILE}" > "${tmp}" && mv "${tmp}" "${ENV_FILE}"
    else
        echo "${var_name}=${var_value}" >> "${ENV_FILE}"
    fi
}

# Trouver les parametrages existants pour une variable de base
# Ex: GITHUB_PERSONAL_ACCESS_TOKEN -> trouve _PERSO, _WORK, etc.
find_existing_profiles() {
    local base_var="$1"
    local profiles=()

    # Le nom de base (sans suffixe)
    if env_var_exists "${base_var}"; then
        profiles+=("(defaut)")
    fi

    # Chercher les suffixes
    while IFS= read -r line; do
        local var_name
        var_name=$(echo "${line}" | cut -d= -f1)
        if [[ "${var_name}" == "${base_var}_"* ]] && [ "${var_name}" != "${base_var}" ]; then
            local suffix="${var_name#${base_var}_}"
            profiles+=("${suffix}")
        fi
    done < "${ENV_FILE}"

    echo "${profiles[@]}"
}

# ── Fonctions affichage ──────────────────────────────────────────────────────

show_agents() {
    echo "  Choisissez un agent :"
    echo "  ────────────────────────────────────────"
    echo ""

    local i=1
    for agent_def in "${AGENTS[@]}"; do
        IFS=':' read -r aid aname adesc <<< "${agent_def}"

        # Compter les MCP deja associes
        local mcp_count
        mcp_count=$(jq -r --arg id "${aid}" '.[$id] // [] | length' "${AGENT_ACCESS}" 2>/dev/null || echo "0")

        local mcp_info=""
        if [ "${mcp_count}" -gt 0 ]; then
            local mcp_list
            mcp_list=$(jq -r --arg id "${aid}" '.[$id] // [] | join(", ")' "${AGENT_ACCESS}" 2>/dev/null)
            mcp_info=" [MCP: ${mcp_list}]"
        fi

        printf "  %2d) %-18s %s%s\n" "${i}" "${aname}" "${adesc}" "${mcp_info}"
        i=$((i + 1))
    done

    echo ""
    echo "   0) Voir la config actuelle"
    echo "   q) Quitter"
    echo ""
}

show_config() {
    echo ""
    echo "  ═══ Configuration actuelle ═══"
    echo ""

    echo "  Serveurs MCP installes :"
    local srv_count
    srv_count=$(jq '.servers | length' "${MCP_CONFIG}")
    if [ "${srv_count}" -eq 0 ]; then
        echo "    (aucun)"
    else
        jq -r '.servers | to_entries[] |
            "    \(if .value.enabled then "✅" else "❌" end) \(.key) — \(.value.name // .key)"
        ' "${MCP_CONFIG}"
    fi

    echo ""
    echo "  Mapping agents → MCP :"
    local agent_count
    agent_count=$(jq 'length' "${AGENT_ACCESS}")
    if [ "${agent_count}" -eq 0 ]; then
        echo "    (aucun mapping)"
    else
        jq -r 'to_entries[] | "    \(.key) → \(.value | join(", "))"' "${AGENT_ACCESS}"
    fi
    echo ""
}

# ── Fonctions MCP Registry ──────────────────────────────────────────────────

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
        "  \(.key + 1)) \(.value.server.name // "inconnu")\n     \(.value.server.description // "" | .[0:100])\n"
    '

    echo "  0) Nouvelle recherche"
    echo "  q) Retour au choix de l'agent"
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
    description=$(echo "${server_json}" | jq -r '.server.description // ""')

    echo ""
    echo "  ═══════════════════════════════════════"
    echo "  ${name}"
    echo "  Pour : ${SELECTED_AGENT_NAME}"
    echo "  ═══════════════════════════════════════"
    echo "${description}" | fold -s -w 70 | sed 's/^/  /'
    echo ""

    local pkg_count
    pkg_count=$(echo "${server_json}" | jq '.server.packages // [] | length')

    if [ "${pkg_count}" -gt 0 ]; then
        echo "  Packages :"
        local i
        for i in $(seq 0 $((pkg_count - 1))); do
            local reg_type identifier transport
            reg_type=$(echo "${server_json}" | jq -r ".server.packages[${i}].registryType // \"?\"")
            identifier=$(echo "${server_json}" | jq -r ".server.packages[${i}].identifier // \"?\"")
            transport=$(echo "${server_json}" | jq -r ".server.packages[${i}].transport.type // \"stdio\"")
            echo "    ${reg_type} : ${identifier} (${transport})"
        done
    fi

    local env_info
    env_info=$(echo "${server_json}" | jq -r '
        [.server.packages[]?.environmentVariables // [] | .[]] | unique_by(.name) |
        .[] | "    \(.name) — \(.description // "requis")"
    ' 2>/dev/null || true)

    if [ -n "${env_info}" ]; then
        echo ""
        echo "  Variables requises :"
        echo "${env_info}"
    fi

    echo ""
    echo "  i) Installer pour ${SELECTED_AGENT_NAME}"
    echo "  0) Retour    q) Menu principal"
    echo ""
}

# ── Installation avec gestion du parametrage ─────────────────────────────────

configure_env_var() {
    # Configure une variable d'environnement avec gestion des profils
    # Args: var_name, var_description
    # Retourne le nom final de la variable via REPLY_VAR_NAME
    local base_var="$1"
    local var_desc="${2:-Requis}"

    echo ""
    echo "  ┌─ ${base_var}"
    echo "  │  ${var_desc}"

    # Chercher les parametrages existants
    local existing=()
    if env_var_exists "${base_var}"; then
        existing+=("defaut")
    fi

    while IFS= read -r line; do
        local vn
        vn=$(echo "${line}" | cut -d= -f1)
        if [[ "${vn}" == "${base_var}_"* ]] && [ "${vn}" != "${base_var}" ]; then
            local sfx="${vn#${base_var}_}"
            existing+=("${sfx}")
        fi
    done < <(grep "^${base_var}" "${ENV_FILE}" 2>/dev/null || true)

    if [ "${#existing[@]}" -gt 0 ]; then
        echo "  │"
        echo "  │  Parametrages existants :"

        local idx=1
        for profile in "${existing[@]}"; do
            local full_var="${base_var}"
            [ "${profile}" != "defaut" ] && full_var="${base_var}_${profile}"

            local val
            val=$(env_var_get "${full_var}")
            local masked
            if [ "${#val}" -gt 10 ]; then
                masked="${val:0:6}...${val: -4}"
            elif [ -n "${val}" ]; then
                masked="****"
            else
                masked="(vide)"
            fi

            printf "  │    %d) [%s] = %s\n" "${idx}" "${profile}" "${masked}"
            idx=$((idx + 1))
        done

        echo "  │    n) Nouveau parametrage"
        echo "  │"

        while true; do
            read -rp "  │  Choix : " profile_choice

            case "${profile_choice}" in
                n|N)
                    read -rp "  │  Nom du profil (ex: perso, work, test) : " suffix_name

                    if [ -z "${suffix_name}" ]; then
                        echo "  │  Nom vide, annule."
                        continue
                    fi

                    suffix_name=$(echo "${suffix_name}" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//')
                    local new_var="${base_var}_${suffix_name}"

                    if env_var_exists "${new_var}"; then
                        echo "  │  ⚠️  ${new_var} existe deja !"
                        continue
                    fi

                    read -rp "  │  Valeur pour ${new_var} : " new_value
                    if [ -n "${new_value}" ]; then
                        env_var_set "${new_var}" "${new_value}"
                        echo "  │  ✅ ${new_var} cree"
                    else
                        env_var_set "${new_var}" "A_CONFIGURER"
                        echo "  │  ⚠️  ${new_var} cree (placeholder)"
                    fi

                    REPLY_VAR_NAME="${new_var}"
                    break
                    ;;

                [0-9]*)
                    local pidx=$((profile_choice - 1))
                    if [ "${pidx}" -ge 0 ] && [ "${pidx}" -lt "${#existing[@]}" ]; then
                        local chosen_profile="${existing[${pidx}]}"
                        local chosen_var="${base_var}"
                        [ "${chosen_profile}" != "defaut" ] && chosen_var="${base_var}_${chosen_profile}"

                        echo "  │  ✅ Reutilise : ${chosen_var}"
                        REPLY_VAR_NAME="${chosen_var}"
                        break
                    else
                        echo "  │  Numero invalide."
                    fi
                    ;;

                *)
                    echo "  │  Tapez un numero ou 'n'."
                    ;;
            esac
        done
    else
        # Pas de parametrage existant — saisie directe
        echo "  │"
        read -rp "  │  Valeur : " new_value
        if [ -n "${new_value}" ]; then
            env_var_set "${base_var}" "${new_value}"
            echo "  │  ✅ ${base_var} ajoute"
        else
            env_var_set "${base_var}" "A_CONFIGURER"
            echo "  │  ⚠️  Placeholder ajoute (pensez a le remplir)"
        fi
        REPLY_VAR_NAME="${base_var}"
    fi

    echo "  └────────────────────────────"
}

install_server_for_agent() {
    local index="$1"
    local server_json
    server_json=$(echo "${LAST_SEARCH_RESULT}" | jq ".servers[${index}]")

    local name
    name=$(echo "${server_json}" | jq -r '.server.name // "inconnu"')

    echo ""
    echo "  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ┃  ${name}"
    echo "  ┃  → pour ${SELECTED_AGENT_NAME} (${SELECTED_AGENT_ID})"
    echo "  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Package info
    local reg_type identifier transport
    reg_type=$(echo "${server_json}" | jq -r '.server.packages[0].registryType // "npm"')
    identifier=$(echo "${server_json}" | jq -r '.server.packages[0].identifier // ""')
    transport=$(echo "${server_json}" | jq -r '.server.packages[0].transport.type // "stdio"')

    if [ -z "${identifier}" ]; then
        echo "  ERREUR : pas de package identifie."
        return 1
    fi

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

    # ── Variables d'environnement ────────────────────────────────────────────
    local env_list
    env_list=$(echo "${server_json}" | jq -r '
        [.server.packages[]?.environmentVariables // [] | .[]] | unique_by(.name) |
        .[] | "\(.name)|\(.description // "Requis")"
    ' 2>/dev/null || true)

    local env_mapping="{}"
    REPLY_VAR_NAME=""

    if [ -n "${env_list}" ]; then
        echo ""
        echo "  Configuration des acces :"

        while IFS='|' read -r var_name var_desc; do
            [ -z "${var_name}" ] && continue

            configure_env_var "${var_name}" "${var_desc}"

            # REPLY_VAR_NAME contient le nom final de la variable
            env_mapping=$(echo "${env_mapping}" | jq --arg k "${var_name}" --arg v "${REPLY_VAR_NAME}" '. + {($k): $v}')

        done <<< "${env_list}"
    fi

    # ── ID du serveur ────────────────────────────────────────────────────────
    local server_id
    server_id=$(echo "${name}" | sed 's/.*\///' | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//')

    # Verifier doublon
    if jq -e ".servers[\"${server_id}\"]" "${MCP_CONFIG}" &>/dev/null; then
        echo ""
        echo "  ⚠️  ${server_id} existe deja."
        read -rp "  Ecraser la configuration ? (o/n) : " overwrite
        if [ "${overwrite}" != "o" ] && [ "${overwrite}" != "O" ]; then
            echo "  Conservation de l'existant."
            # Ajouter quand meme le mapping agent -> mcp
            add_agent_mapping "${server_id}"
            return 0
        fi
    fi

    # ── Sauvegarder dans mcp_servers.json ────────────────────────────────────
    local new_entry
    new_entry=$(jq -n \
        --arg cmd "${cmd}" \
        --argjson args "${args_json}" \
        --arg transport "${transport}" \
        --argjson env "${env_mapping}" \
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

    # ── Ajouter le mapping agent -> mcp ──────────────────────────────────────
    add_agent_mapping "${server_id}"

    echo ""
    echo "  ✅ ${name} configure pour ${SELECTED_AGENT_NAME}"
    echo "     ID        : ${server_id}"
    echo "     Commande  : ${cmd} ${identifier}"
    echo "     Transport : ${transport}"
    echo ""
}

add_agent_mapping() {
    local server_id="$1"
    local tmp
    tmp=$(mktemp)

    # Ajouter le server_id dans la liste de l'agent (sans doublon)
    jq --arg agent "${SELECTED_AGENT_ID}" --arg mcp "${server_id}" '
        if .[$agent] then
            if (.[$agent] | index($mcp)) then .
            else .[$agent] += [$mcp]
            end
        else
            .[$agent] = [$mcp]
        end
    ' "${AGENT_ACCESS}" > "${tmp}" && mv "${tmp}" "${AGENT_ACCESS}"
}

# ── Generation du mcp_client.py ──────────────────────────────────────────────

generate_mcp_client() {
    echo "  Generation de agents/shared/mcp_client.py..."

    cat > agents/shared/mcp_client.py << 'PYTHONEOF'
"""MCP Client — Charge les configs depuis mcp_servers.json et agent_mcp_access.json."""
import json, logging, os, asyncio
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE = os.path.dirname(__file__)
CONFIG_PATHS = [
    os.path.join(BASE, "..", "..", "config"),
    os.path.join("/app", "config"),
]


def _find_config(filename):
    for base in CONFIG_PATHS:
        path = os.path.join(os.path.abspath(base), filename)
        if os.path.exists(path):
            return path
    return None


def _load_json(filename):
    path = _find_config(filename)
    if path:
        with open(path) as f:
            return json.load(f)
    return {}


def _resolve_env(env_dict):
    """Resout les variables — chaque valeur est le nom reel de la var dans .env."""
    resolved = {}
    for key, var_name in env_dict.items():
        val = os.getenv(var_name, "")
        if not val:
            val = os.getenv(key, "")
        if val and val != "A_CONFIGURER":
            resolved[key] = val
    return resolved


def get_mcp_tools_sync(agent_id: str) -> list:
    try:
        loop = asyncio.new_event_loop()
        tools = loop.run_until_complete(_get_tools_async(agent_id))
        loop.close()
        return tools
    except Exception as e:
        logger.warning(f"[{agent_id}] MCP tools unavailable: {e}")
        return []


async def _get_tools_async(agent_id: str) -> list:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    mcp_config = _load_json("mcp_servers.json")
    agent_access = _load_json("agent_mcp_access.json")

    # Quels MCP cet agent peut utiliser
    allowed = agent_access.get(agent_id, [])
    if not allowed:
        return []

    servers = {}
    for server_id in allowed:
        server_conf = mcp_config.get("servers", {}).get(server_id)
        if not server_conf or not server_conf.get("enabled", True):
            continue

        env = _resolve_env(server_conf.get("env", {}))

        # Verifier les vars requises
        missing = [k for k in server_conf.get("env", {}) if not env.get(k)]
        if missing:
            logger.warning(f"[{agent_id}] MCP {server_id} skip — missing: {missing}")
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
        logger.info(f"[{agent_id}] MCP: {len(tools)} tools from {list(servers.keys())}")
        return tools
    except Exception as e:
        logger.error(f"[{agent_id}] MCP error: {e}")
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

    echo "  -> mcp_client.py genere (filtre par agent)"
}

# ══════════════════════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

while true; do
    echo ""
    show_agents
    read -rp "  Agent (numero, 0=config, q=quitter) : " agent_choice

    [ "${agent_choice}" = "q" ] || [ "${agent_choice}" = "Q" ] && break

    if [ "${agent_choice}" = "0" ]; then
        show_config
        continue
    fi

    if ! [[ "${agent_choice}" =~ ^[0-9]+$ ]]; then
        echo "  Tapez un numero."
        continue
    fi

    local_idx=$((agent_choice - 1))
    if [ "${local_idx}" -lt 0 ] || [ "${local_idx}" -ge "${#AGENTS[@]}" ]; then
        echo "  Numero invalide (1-${#AGENTS[@]})."
        continue
    fi

    # Extraire l'agent selectionne
    IFS=':' read -r SELECTED_AGENT_ID SELECTED_AGENT_NAME _ <<< "${AGENTS[${local_idx}]}"

    echo ""
    echo "  ✔ Agent selectionne : ${SELECTED_AGENT_NAME} (${SELECTED_AGENT_ID})"
    echo ""

    # Boucle de recherche MCP pour cet agent
    while true; do
        read -rp "  🔍 MCP pour ${SELECTED_AGENT_NAME} (q=retour) : " search_input

        [ "${search_input}" = "q" ] || [ "${search_input}" = "Q" ] && break
        [ -z "${search_input}" ] && continue

        if ! search_servers "${search_input}"; then
            continue
        fi

        while true; do
            read -rp "  Choix (numero, 0=recherche, q=retour agent) : " mcp_choice

            [ "${mcp_choice}" = "q" ] || [ "${mcp_choice}" = "Q" ] && break 2
            [ "${mcp_choice}" = "0" ] && break

            if ! [[ "${mcp_choice}" =~ ^[0-9]+$ ]]; then
                echo "  Tapez un numero."
                continue
            fi

            mcp_idx=$((mcp_choice - 1))
            if [ "${mcp_idx}" -lt 0 ] || [ "${mcp_idx}" -ge "${LAST_SEARCH_COUNT}" ]; then
                echo "  Numero invalide (1-${LAST_SEARCH_COUNT})."
                continue
            fi

            get_server_details "${mcp_idx}"

            while true; do
                read -rp "  Choix (i=installer, 0=retour, q=menu) : " detail_choice

                [ "${detail_choice}" = "q" ] || [ "${detail_choice}" = "Q" ] && break 3
                [ "${detail_choice}" = "0" ] && break

                if [ "${detail_choice}" = "i" ] || [ "${detail_choice}" = "I" ]; then
                    install_server_for_agent "${mcp_idx}"

                    echo "  Ajouter un autre MCP pour ${SELECTED_AGENT_NAME} ?"
                    read -rp "  (o=oui, n=retour agents) : " more
                    [ "${more}" = "n" ] || [ "${more}" = "N" ] && break 3
                    break 2  # Retour a la recherche MCP
                fi

                echo "  Tapez i, 0, ou q."
            done
        done
    done
done

# ── Finalisation ─────────────────────────────────────────────────────────────
echo ""

installed_count=$(jq '.servers | length' "${MCP_CONFIG}")
mapping_count=$(jq 'length' "${AGENT_ACCESS}")

if [ "${installed_count}" -gt 0 ] || [ "${mapping_count}" -gt 0 ]; then
    echo "  Finalisation..."
    generate_mcp_client

    show_config

    echo "  Fichiers generes :"
    echo "    ${MCP_CONFIG}"
    echo "    ${AGENT_ACCESS}"
    echo "    agents/shared/mcp_client.py"
    echo "    ${ENV_FILE}"
    echo ""
    echo "  Pour appliquer :"
    echo "    cd ${PROJECT_DIR}"
    echo "    docker compose up -d --build langgraph-api"
else
    echo "  Aucune modification."
fi

echo ""
echo "==========================================="
