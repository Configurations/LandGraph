#!/bin/bash
###############################################################################
# Script 14 : Installation interactive MCP
#
# - Catalogue externe depuis GitHub (config/mcp_catalog.csv)
# - Agents resolus dynamiquement depuis prompts/v1/*.md
# - Recherche par nom en premier
# - Gestion des parametrages .env avec suffixes nommes
#
# Usage : ./14-install-mcp.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
MCP_CONFIG="${PROJECT_DIR}/config/mcp_servers.json"
AGENT_ACCESS="${PROJECT_DIR}/config/agent_mcp_access.json"
ENV_FILE="${PROJECT_DIR}/.env"
CATALOG_FILE="${PROJECT_DIR}/config/mcp_catalog.csv"
CATALOG_URL="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/mcp_catalog.csv"

echo "==========================================="
echo "  Installation interactive MCP"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── Pre-requis ───────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "Installation de Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>/dev/null
    apt-get install -y nodejs 2>/dev/null
fi

command -v jq &>/dev/null || apt-get install -y jq 2>/dev/null

source .venv/bin/activate 2>/dev/null || true
pip install -q langchain-mcp-adapters mcp 2>/dev/null
grep -q "langchain-mcp-adapters" requirements.txt 2>/dev/null || echo "langchain-mcp-adapters>=0.2.0" >> requirements.txt

mkdir -p config
[ ! -f "${MCP_CONFIG}" ] && echo '{"servers": {}}' > "${MCP_CONFIG}"
[ ! -f "${AGENT_ACCESS}" ] && echo '{}' > "${AGENT_ACCESS}"

# ── Telecharger le catalogue ─────────────────────────────────────────────────
echo "  Telechargement du catalogue MCP..."
CATALOG_DOWNLOADED=0
if wget -qO "${CATALOG_FILE}.tmp" "${CATALOG_URL}" 2>/dev/null && [ -s "${CATALOG_FILE}.tmp" ]; then
    mv "${CATALOG_FILE}.tmp" "${CATALOG_FILE}"
    echo "  -> Catalogue telecharge"
    CATALOG_DOWNLOADED=1
else
    rm -f "${CATALOG_FILE}.tmp"
fi

if [ "${CATALOG_DOWNLOADED}" -eq 0 ]; then
    if [ -f "${CATALOG_FILE}" ]; then
        echo "  -> Telechargement echoue, utilisation du cache local"
    else
        echo "  ERREUR : impossible de telecharger le catalogue et aucun cache local."
        exit 1
    fi
fi

# Charger le catalogue (ignorer commentaires et lignes vides)
CATALOG=()
while IFS= read -r line; do
    [[ "${line}" =~ ^#.*$ ]] && continue
    [[ -z "${line}" ]] && continue
    CATALOG+=("${line}")
done < "${CATALOG_FILE}"

echo "  -> ${#CATALOG[@]} serveurs dans le catalogue"

# ── Resoudre les agents dynamiquement ────────────────────────────────────────
echo "  Detection des agents..."
AGENTS=()

for prompt_file in "${PROJECT_DIR}"/prompts/v1/*.md; do
    [ ! -f "${prompt_file}" ] && continue
    agent_id=$(basename "${prompt_file}" .md)

    agent_py="${PROJECT_DIR}/agents/${agent_id}.py"
    agent_name="${agent_id}"

    if [ -f "${agent_py}" ]; then
        found_name=$(grep 'agent_name' "${agent_py}" 2>/dev/null | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)
        if [ -n "${found_name}" ] && [ "${found_name}" != "${agent_id}" ]; then
            agent_name="${found_name}"
        fi
    fi

    # Fallback : humaniser l'id
    if [ "${agent_name}" = "${agent_id}" ]; then
        agent_name=$(echo "${agent_id}" | tr '_' ' ' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')
    fi

    AGENTS+=("${agent_id}|${agent_name}")
done

if [ "${#AGENTS[@]}" -eq 0 ]; then
    echo "  ERREUR : aucun agent trouve dans ${PROJECT_DIR}/prompts/v1/"
    echo "  Executez d'abord le script 06-install-agents.sh"
    exit 1
fi

echo "  -> ${#AGENTS[@]} agents detectes"
echo ""

# ── Variables globales ───────────────────────────────────────────────────────
SELECTED_AGENT_ID=""
SELECTED_AGENT_NAME=""
FILTERED_ENTRIES=()
FILTERED_COUNT=0

# ── Fonctions .env ───────────────────────────────────────────────────────────

env_var_exists() { grep -q "^${1}=" "${ENV_FILE}" 2>/dev/null; }
env_var_get() { grep "^${1}=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d= -f2-; }

env_var_set() {
    local vn="$1" vv="$2"
    if env_var_exists "${vn}"; then
        local tmp; tmp=$(mktemp)
        sed "s|^${vn}=.*|${vn}=${vv}|" "${ENV_FILE}" > "${tmp}" && mv "${tmp}" "${ENV_FILE}"
    else
        echo "${vn}=${vv}" >> "${ENV_FILE}"
    fi
}

# ── Affichage agents ─────────────────────────────────────────────────────────

show_agents() {
    echo "  Choisissez un agent :"
    echo "  ────────────────────────────────────────"
    echo ""

    local i=1
    for agent_entry in "${AGENTS[@]}"; do
        IFS='|' read -r aid aname <<< "${agent_entry}"

        local mcp_list
        mcp_list=$(jq -r --arg id "${aid}" '.[$id] // [] | join(", ")' "${AGENT_ACCESS}" 2>/dev/null)
        local mcp_info=""
        [ -n "${mcp_list}" ] && mcp_info=" [${mcp_list}]"

        printf "  %2d) %-22s%s\n" "${i}" "${aname}" "${mcp_info}"
        i=$((i + 1))
    done

    echo ""
    echo "   0) Voir la config actuelle"
    echo "   q) Quitter"
    echo ""
}

# ── Recherche dans le catalogue ──────────────────────────────────────────────

search_catalog() {
    local query="$1"
    local lower_query
    lower_query=$(echo "${query}" | tr '[:upper:]' '[:lower:]')

    FILTERED_ENTRIES=()
    FILTERED_COUNT=0

    for entry in "${CATALOG[@]}"; do
        IFS='|' read -r mdep mid mlabel mdesc _ _ _ _ <<< "${entry}"

        local lower_label lower_desc lower_id
        lower_label=$(echo "${mlabel}" | tr '[:upper:]' '[:lower:]')
        lower_desc=$(echo "${mdesc}" | tr '[:upper:]' '[:lower:]')
        lower_id=$(echo "${mid}" | tr '[:upper:]' '[:lower:]')

        if [[ "${lower_label}" == *"${lower_query}"* ]] || \
           [[ "${lower_desc}" == *"${lower_query}"* ]] || \
           [[ "${lower_id}" == *"${lower_query}"* ]]; then
            FILTERED_ENTRIES+=("${entry}")
            FILTERED_COUNT=$((FILTERED_COUNT + 1))
        fi
    done

    if [ "${FILTERED_COUNT}" -eq 0 ]; then
        echo ""
        echo "  Aucun resultat pour '${query}'."
        echo "  Essayez : github, postgres, slack, notion, docker, git"
        echo ""
        return 1
    fi

    echo ""
    echo "  ${FILTERED_COUNT} resultat(s) pour '${query}' :"
    echo "  ────────────────────────────────────────"
    echo ""

    local i=1
    for entry in "${FILTERED_ENTRIES[@]}"; do
        IFS='|' read -r mdep mid mlabel mdesc _ _ _ _ <<< "${entry}"

        # Verifier si deja installe pour cet agent
        local installed=""
        if jq -e --arg a "${SELECTED_AGENT_ID}" --arg m "${mid}" \
            '.[$a] // [] | index($m)' "${AGENT_ACCESS}" &>/dev/null 2>&1; then
            installed=" ✅"
        fi

        local dep_badge=""
        [ "${mdep}" = "1" ] && dep_badge=" ⚠️"

        printf "  %2d) %-20s %s%s%s\n" "${i}" "${mlabel}" "${mdesc:0:45}" "${installed}" "${dep_badge}"
        i=$((i + 1))
    done

    echo ""
    echo "   0) Nouvelle recherche"
    echo "   q) Retour aux agents"
    echo ""
}

# ── Config actuelle ──────────────────────────────────────────────────────────

show_config() {
    echo ""
    echo "  ═══ Configuration actuelle ═══"
    echo ""
    echo "  Serveurs MCP :"
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
    echo "  Agents → MCP :"
    local ac
    ac=$(jq 'length' "${AGENT_ACCESS}")
    if [ "${ac}" -eq 0 ]; then
        echo "    (aucun mapping)"
    else
        jq -r 'to_entries[] | "    \(.key) → \(.value | join(", "))"' "${AGENT_ACCESS}"
    fi
    echo ""
}

# ── Configuration variable d'environnement ───────────────────────────────────

configure_env_var() {
    local base_var="$1"
    local var_desc="${2:-Requis}"

    echo ""
    echo "  ┌─ ${base_var}"
    echo "  │  ${var_desc}"

    # Trouver parametrages existants
    local existing=()
    if env_var_exists "${base_var}"; then
        existing+=("defaut|${base_var}")
    fi
    while IFS= read -r line; do
        local vn
        vn=$(echo "${line}" | cut -d= -f1)
        if [[ "${vn}" == "${base_var}_"* ]] && [ "${vn}" != "${base_var}" ]; then
            local sfx="${vn#${base_var}_}"
            existing+=("${sfx}|${vn}")
        fi
    done < <(grep "^${base_var}" "${ENV_FILE}" 2>/dev/null || true)

    if [ "${#existing[@]}" -gt 0 ]; then
        echo "  │"
        echo "  │  Parametrages existants :"

        local idx=1
        for pe in "${existing[@]}"; do
            IFS='|' read -r pname pvar <<< "${pe}"
            local val masked
            val=$(env_var_get "${pvar}")
            if [ "${#val}" -gt 10 ]; then
                masked="${val:0:6}...${val: -4}"
            elif [ -n "${val}" ] && [ "${val}" != "A_CONFIGURER" ]; then
                masked="****"
            else
                masked="(a configurer)"
            fi
            printf "  │    %d) [%s] = %s\n" "${idx}" "${pname}" "${masked}"
            idx=$((idx + 1))
        done

        echo "  │    n) Nouveau parametrage"
        echo "  │"

        while true; do
            read -rp "  │  Choix : " pc
            case "${pc}" in
                n|N)
                    read -rp "  │  Nom du profil (ex: perso, work, test) : " sfx
                    [ -z "${sfx}" ] && echo "  │  Annule." && continue
                    sfx=$(echo "${sfx}" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//')
                    local new_var="${base_var}_${sfx}"
                    if env_var_exists "${new_var}"; then echo "  │  ⚠️  ${new_var} existe deja !"; continue; fi
                    read -rp "  │  Valeur pour ${new_var} : " nv
                    if [ -n "${nv}" ]; then
                        env_var_set "${new_var}" "${nv}"; echo "  │  ✅ ${new_var} cree"
                    else
                        env_var_set "${new_var}" "A_CONFIGURER"; echo "  │  ⚠️  Placeholder cree"
                    fi
                    REPLY_VAR_NAME="${new_var}"; break ;;
                [0-9]*)
                    local pidx=$((pc - 1))
                    if [ "${pidx}" -ge 0 ] && [ "${pidx}" -lt "${#existing[@]}" ]; then
                        IFS='|' read -r _ chosen_var <<< "${existing[${pidx}]}"
                        echo "  │  ✅ Reutilise : ${chosen_var}"
                        REPLY_VAR_NAME="${chosen_var}"; break
                    else echo "  │  Numero invalide."; fi ;;
                *) echo "  │  Tapez un numero ou 'n'." ;;
            esac
        done
    else
        echo "  │"
        read -rp "  │  Valeur : " nv
        if [ -n "${nv}" ]; then
            env_var_set "${base_var}" "${nv}"; echo "  │  ✅ ${base_var} ajoute"
        else
            env_var_set "${base_var}" "A_CONFIGURER"; echo "  │  ⚠️  Placeholder"
        fi
        REPLY_VAR_NAME="${base_var}"
    fi
    echo "  └────────────────────────────"
}

# ── Installation MCP pour un agent ───────────────────────────────────────────

install_mcp_for_agent() {
    local catalog_entry="$1"
    IFS='|' read -r mdep mid mname mdesc mcmd margs mtransport menvs <<< "${catalog_entry}"

    echo ""
    echo "  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ┃  ${mname} → ${SELECTED_AGENT_NAME}"
    echo "  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local args_json
    args_json=$(echo "${margs}" | tr ' ' '\n' | jq -R . | jq -sc .)

    # Variables d'environnement
    local env_mapping="{}"
    REPLY_VAR_NAME=""

    if [ -n "${menvs}" ]; then
        echo ""
        echo "  Configuration des acces :"
        IFS=',' read -ra env_pairs <<< "${menvs}"
        for pair in "${env_pairs[@]}"; do
            IFS=':' read -r var_name var_desc <<< "${pair}"
            [ -z "${var_name}" ] && continue
            configure_env_var "${var_name}" "${var_desc}"
            env_mapping=$(echo "${env_mapping}" | jq --arg k "${var_name}" --arg v "${REPLY_VAR_NAME}" '. + {($k): $v}')
        done
    fi

    # Sauvegarder dans mcp_servers.json (ou reutiliser)
    if jq -e ".servers[\"${mid}\"]" "${MCP_CONFIG}" &>/dev/null; then
        echo "  ℹ️  ${mid} deja configure — mise a jour env."
        local tmp; tmp=$(mktemp)
        jq --arg id "${mid}" --argjson env "${env_mapping}" \
            '.servers[$id].env = $env' "${MCP_CONFIG}" > "${tmp}" && mv "${tmp}" "${MCP_CONFIG}"
    else
        local new_entry
        new_entry=$(jq -n \
            --arg cmd "${mcmd}" --argjson args "${args_json}" \
            --arg transport "${mtransport}" --argjson env "${env_mapping}" \
            --arg name "${mname}" \
            '{command:$cmd,args:$args,transport:$transport,env:$env,name:$name,enabled:true}')
        local tmp; tmp=$(mktemp)
        jq --arg id "${mid}" --argjson entry "${new_entry}" \
            '.servers[$id] = $entry' "${MCP_CONFIG}" > "${tmp}" && mv "${tmp}" "${MCP_CONFIG}"
    fi

    # Mapping agent -> mcp
    local tmp2; tmp2=$(mktemp)
    jq --arg a "${SELECTED_AGENT_ID}" --arg m "${mid}" '
        if .[$a] then
            if (.[$a] | index($m)) then . else .[$a] += [$m] end
        else .[$a] = [$m] end
    ' "${AGENT_ACCESS}" > "${tmp2}" && mv "${tmp2}" "${AGENT_ACCESS}"

    echo ""
    echo "  ✅ ${mname} → ${SELECTED_AGENT_NAME}"
    echo ""
}

# ── Generation mcp_client.py ─────────────────────────────────────────────────

generate_mcp_client() {
    echo "  Generation de agents/shared/mcp_client.py..."

    cat > agents/shared/mcp_client.py << 'PYTHONEOF'
"""MCP Client — Filtre par agent via config/agent_mcp_access.json."""
import json, logging, os, asyncio
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)
BASE = os.path.dirname(__file__)
CPATHS = [os.path.join(BASE,"..","..","config"), os.path.join("/app","config")]

def _find(f):
    for b in CPATHS:
        p = os.path.join(os.path.abspath(b), f)
        if os.path.exists(p): return p
    return None

def _load(f):
    p = _find(f)
    return json.load(open(p)) if p else {}

def _resolve(env):
    r = {}
    for k, vn in env.items():
        v = os.getenv(vn, os.getenv(k, ""))
        if v and v != "A_CONFIGURER": r[k] = v
    return r

def get_mcp_tools_sync(agent_id):
    try:
        loop = asyncio.new_event_loop()
        t = loop.run_until_complete(_get(agent_id)); loop.close(); return t
    except Exception as e:
        logger.warning(f"[{agent_id}] MCP: {e}"); return []

async def _get(agent_id):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    mc, ac = _load("mcp_servers.json"), _load("agent_mcp_access.json")
    allowed = ac.get(agent_id, [])
    if not allowed: return []
    servers = {}
    for sid in allowed:
        sc = mc.get("servers",{}).get(sid)
        if not sc or not sc.get("enabled",True): continue
        env = _resolve(sc.get("env",{}))
        missing = [k for k in sc.get("env",{}) if not env.get(k)]
        if missing: logger.warning(f"[{agent_id}] {sid} skip: {missing}"); continue
        e = {"command":sc["command"],"args":sc["args"],"transport":sc.get("transport","stdio")}
        if env: e["env"] = env
        servers[sid] = e
    if not servers: return []
    try:
        c = MultiServerMCPClient(servers); t = await c.get_tools()
        logger.info(f"[{agent_id}] MCP: {len(t)} tools from {list(servers.keys())}"); return t
    except Exception as e: logger.error(f"[{agent_id}] MCP: {e}"); return []

def get_tools_for_agent(agent_id):
    t = get_mcp_tools_sync(agent_id)
    try:
        from agents.shared.rag_service import create_rag_tools
        t.extend(create_rag_tools())
    except ImportError: pass
    return t
PYTHONEOF
    echo "  -> mcp_client.py genere"
}

# ══════════════════════════════════════════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

while true; do
    echo ""
    show_agents
    read -rp "  Agent (numero, 0=config, q=quitter) : " ac

    [ "${ac}" = "q" ] || [ "${ac}" = "Q" ] && break
    if [ "${ac}" = "0" ]; then show_config; continue; fi
    if ! [[ "${ac}" =~ ^[0-9]+$ ]]; then echo "  Tapez un numero."; continue; fi

    aidx=$((ac - 1))
    if [ "${aidx}" -lt 0 ] || [ "${aidx}" -ge "${#AGENTS[@]}" ]; then
        echo "  Invalide (1-${#AGENTS[@]})."; continue
    fi

    IFS='|' read -r SELECTED_AGENT_ID SELECTED_AGENT_NAME <<< "${AGENTS[${aidx}]}"
    echo ""
    echo "  ✔ ${SELECTED_AGENT_NAME} (${SELECTED_AGENT_ID})"

    # Boucle MCP : recherche d'abord
    while true; do
        echo ""
        read -rp "  🔍 MCP pour ${SELECTED_AGENT_NAME} (q=retour agents) : " sq

        [ "${sq}" = "q" ] || [ "${sq}" = "Q" ] && break
        [ -z "${sq}" ] && continue

        if ! search_catalog "${sq}"; then
            continue
        fi

        # Selection dans les resultats
        while true; do
            read -rp "  Choix (numero, 0=rechercher, q=retour agents) : " mc

            [ "${mc}" = "q" ] || [ "${mc}" = "Q" ] && break 2
            [ "${mc}" = "0" ] && break

            if ! [[ "${mc}" =~ ^[0-9]+$ ]]; then echo "  Tapez un numero."; continue; fi

            midx=$((mc - 1))
            if [ "${midx}" -lt 0 ] || [ "${midx}" -ge "${FILTERED_COUNT}" ]; then
                echo "  Invalide (1-${FILTERED_COUNT})."; continue
            fi

            # Detail
            local_entry="${FILTERED_ENTRIES[${midx}]}"
            IFS='|' read -r sdep sid sname sdesc _ _ _ senvs <<< "${local_entry}"

            echo ""
            echo "  ═══════════════════════════════════════"
            echo "  ${sname} → ${SELECTED_AGENT_NAME}"
            [ "${sdep}" = "1" ] && echo "  ⚠️  DEPRECIE — fonctionne mais remplace par une version plus recente"
            echo "  ═══════════════════════════════════════"
            echo "  ${sdesc}"
            if [ -n "${senvs}" ]; then
                echo "  Variables : $(echo "${senvs}" | tr ',' ', ' | sed 's/:[^,]*//g')"
            fi
            echo ""
            echo "  i) Installer    0) Retour resultats    q) Retour agents"
            echo ""

            read -rp "  Choix : " dc
            case "${dc}" in
                i|I)
                    install_mcp_for_agent "${local_entry}"
                    # Retour a la recherche pour en ajouter d'autres
                    break
                    ;;
                q|Q) break 2 ;;
                *) continue ;;
            esac
        done
    done
done

# ── Finalisation ─────────────────────────────────────────────────────────────
echo ""

installed=$(jq '.servers | length' "${MCP_CONFIG}")
if [ "${installed}" -gt 0 ]; then
    echo "  Finalisation..."
    generate_mcp_client
    show_config
    echo "  Pour appliquer :"
    echo "    cd ${PROJECT_DIR}"
    echo "    docker compose up -d --build langgraph-api"
else
    echo "  Aucune modification."
fi

echo ""
echo "==========================================="
