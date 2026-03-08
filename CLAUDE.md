# LandGraph Multi-Agent Platform — Documentation Technique

## Vue d'ensemble

LandGraph est une plateforme multi-agent basée sur **LangGraph** (Python) qui orchestre 13 agents IA spécialisés pour gérer le cycle de vie complet d'un projet logiciel (Discovery → Design → Build → Ship → Iterate). Les agents communiquent via **Discord**, sont pilotés par un **Orchestrateur IA**, et utilisent des **MCP servers** pour interagir avec GitHub, Notion, et d'autres services.

---

## Infrastructure

- **Hôte** : Proxmox LXC 110 (privileged, 8 vCPU, 8GB RAM)
- **OS** : Ubuntu 24
- **Container runtime** : Docker + Docker Compose
- **Données persistantes** : `/opt/langgraph-data/{postgres,redis,langfuse-*}/`

### Stack Docker

| Service | Image | Port | Rôle |
|---|---|---|---|
| `langgraph-postgres` | pgvector/pgvector:pg16 | 5432 (local) | BDD principale + pgvector (RAG) |
| `langgraph-redis` | redis:7-alpine | 6379 (local) | Cache + pub/sub |
| `langgraph-api` | Custom (Dockerfile) | **8123** | API FastAPI — gateway + agents |
| `discord-bot` | Custom (Dockerfile.discord) | — | Bot Discord — interface utilisateur |
| `langgraph-admin` | Custom (Dockerfile.admin) | **8080** | Dashboard web administration |
| `langfuse-web` | langfuse/langfuse:3 | **3000** | Observabilité LLM (UI + API) |
| `langfuse-worker` | langfuse/langfuse-worker:3 | — | Worker async Langfuse |
| `langfuse-postgres` | postgres:16-alpine | — | BDD Langfuse (isolée) |
| `langfuse-clickhouse` | clickhouse/clickhouse-server | — | OLAP traces |
| `langfuse-redis` | redis:7-alpine | — | Cache Langfuse |
| `langfuse-minio` | minio/minio | 9090 | Blob storage |

---

## Structure du code

```
langgraph-project/
├── agents/
│   ├── gateway.py              ← API FastAPI v0.6.0 (routing, persistence, parallélisme)
│   ├── orchestrator.py         ← Noeud LangGraph — décisions de routing
│   ├── discord_listener.py     ← Bot Discord (!agent, !reset, !new, !status)
│   └── shared/
│       ├── base_agent.py       ← Classe de base — Pipeline + ReAct + tools + human gate
│       ├── agent_loader.py     ← Charge agents depuis registry JSON (multi-équipes)
│       ├── llm_provider.py     ← Factory multi-provider (Claude, GPT, Azure, Ollama, Kimi...)
│       ├── rate_limiter.py     ← Throttling par env_key + retry exponentiel (20 retries)
│       ├── mcp_client.py       ← Lazy install MCP + cache global + locks
│       ├── human_gate.py       ← Validation humaine via Discord (30 min, rappels)
│       ├── agent_conversation.py ← Questions ouvertes aux humains via Discord
│       ├── state.py            ← State LangGraph partagé
│       └── discord_tools.py    ← Helpers Discord
│
├── Configs/
│   ├── init.sql                ← Init PostgreSQL
│   ├── llm_providers.json      ← 17 providers LLM + throttling par env_key
│   ├── mcp_servers.json        ← Config des serveurs MCP
│   ├── teams.json              ← Multi-équipes (isolation par channel Discord)
│   └── team1/                  ← Prompts de l'équipe par défaut
│       ├── agents_registry.json    ← Définition des 13 agents (équipe default)
│       ├── agent_mcp_access.json   ← MCP autorisés par agent
│       ├── orchestrator.md         ← Prompt orchestrateur (routing intelligent)
│       ├── lead_dev.md             ← Lead Dev (fait ou délègue)
│       ├── requirements_analyst.md ← Analyste (PRD, User Stories, MoSCoW)
│       └── ... (13 fichiers .md, un par agent)
│
├── Shared/Teams/team_project/  ← Exemple d'équipe isolée
│   ├── teams.json              ← Config multi-équipes
│   ├── mcp_servers.json        ← Config des serveurs MCP
│   └── prompts/
│       ├── agents_registry.json    ← Définition des agents de cette équipe
│       ├── agent_mcp_access.json   ← MCP autorisés par agent
│       ├── orchestrator.md         ← Prompt orchestrateur
│       ├── lead_dev.md             ← Lead Dev
│       ├── requirements_analyst.md ← Analyste
│       └── ... (fichiers .md par agent)
│
├── web/
│   ├── server.py               ← Dashboard admin FastAPI
│   └── static/                 ← Frontend web
├── docker-compose.yml
├── Dockerfile                  ← Image langgraph-api
├── Dockerfile.discord          ← Image discord-bot
├── Dockerfile.admin            ← Image dashboard admin
├── .env                        ← Secrets (clés API, tokens)
├── start.sh / restart.sh / build.sh  ← Scripts utilitaires
└── requirements.txt
```

---

## Agents (13)

Définis dans `config/agents_registry.json`. Pas de fichiers Python individuels — tout passe par `BaseAgent` + registry.

### Champs du registry

```json
{
  "agents": {
    "agent_id": {
      "name": "Nom Affichable",
      "llm": "claude-sonnet",          // ref vers llm_providers.json
      "temperature": 0.3,
      "max_tokens": 32768,
      "prompt": "agent_id.md",         // fichier dans prompts/v1/
      "type": "pipeline | single",
      "use_tools": true,
      "requires_approval": false,
      "pipeline_steps": [...]           // si type=pipeline
    }
  }
}
```

### Liste des agents

| Agent | Rôle | Type | Phase |
|---|---|---|---|
| `requirements_analyst` | PRD, User Stories, MoSCoW | pipeline (3 étapes) | Discovery |
| `legal_advisor` | Audit RGPD, conformité, CGU | pipeline (2 étapes) | Transversal |
| `ux_designer` | Wireframes, mockups, design system | single | Design |
| `architect` | ADRs, C4, OpenAPI specs | single | Design |
| `planner` | Sprint backlog, roadmap, risques | single | Design |
| `lead_dev` | Review, repo, coordination, délégation | single + tools | Build |
| `dev_frontend_web` | Code React/Next.js/TypeScript | single | Build |
| `dev_backend_api` | Code Python/FastAPI/SQLAlchemy | single | Build |
| `dev_mobile` | Code Flutter/React Native | single | Build |
| `qa_engineer` | Tests E2E, unitaires, validation | single | Build |
| `devops_engineer` | CI/CD, Docker, déploiement | single | Ship |
| `docs_writer` | Documentation, rapports, README | single + tools | Ship |

### Hiérarchie de routing (Orchestrateur)

```
Demande globale/vague    → requirements_analyst (clarifie)
Demande technique        → lead_dev (décompose, fait ou délègue aux devs)
Demande spécialisée      → directement au spécialiste
Brief projet complet     → requirements_analyst + legal_advisor (Discovery)
```

Le Lead Dev est le seul à pouvoir dispatcher vers `dev_frontend_web`, `dev_backend_api`, `dev_mobile`. L'Orchestrateur ne les appelle jamais directement.

---

## Gateway (gateway.py) — v0.6.0

### Endpoints

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/health` | GET | Health check |
| `/status` | GET | Liste agents + équipes |
| `/invoke` | POST | Appel agent (direct ou orchestré) |
| `/reset` | POST | Purge le state d'un thread |

### Modes d'invocation

1. **Direct** (`!agent <id> <tâche>`) — bypass l'orchestrateur, 1 seul agent
2. **Orchestré** (message normal) — l'Orchestrateur analyse et route

### Thread persistence

- `thread_id = "project-channel-{channel_id}"`
- State sauvegardé dans PostgreSQL via `PostgresSaver`
- Le contexte survit entre les messages
- `!reset` purge le state d'un channel

### Parallélisme

- `asyncio.gather` pour les agents en parallèle
- Timeout 35 min par agent (couvre les 30 min d'attente humaine)

---

## LLM Providers (llm_providers.json)

### Architecture

```
llm_providers.json          → Définit les services IA disponibles
  ├── providers: {}         → Nom, type, modèle, env_key, URLs
  ├── throttling: {}        → Limites RPM/TPM par env_key
  └── default: "..."        → Provider par défaut
```

### Types supportés

| Type | Provider | Factory |
|---|---|---|
| `anthropic` | Claude | `ChatAnthropic` |
| `openai` | OpenAI | `ChatOpenAI` |
| `azure` | Azure OpenAI | `AzureChatOpenAI` |
| `google` | Gemini | `ChatGoogleGenerativeAI` |
| `mistral` | Mistral | `ChatMistralAI` |
| `ollama` | Ollama (local) | `ChatOllama` |
| `groq` | Groq | `ChatGroq` |
| `deepseek` | DeepSeek | `ChatOpenAI` (compat) |
| `moonshot` | Kimi K2/K2.5 | `ChatOpenAI` (compat) |

### Throttling

- Par `env_key` (même clé API = même compteur)
- Sliding window 60s (RPM + TPM)
- 20 retries avec backoff exponentiel (×2, cap 120s)
- Config dans `llm_providers.json > throttling`

### Utilisation par agent

Dans `agents_registry.json` :
```json
"architect": { "llm": "claude-opus", ... }
"dev_backend_api": { "llm": "azure-gpt4o", ... }
```

Override via `.env` : `ARCHITECT_LLM=gpt-4o`

---

## MCP (Model Context Protocol)

### Lazy install

- Premier appel : `npm install -g <package>` ou `uv tool install <package>`
- Appels suivants : déjà installé, démarrage immédiat
- Lock par package (thread-safe)

### Config

- `config/mcp_servers.json` — définition des serveurs MCP
- `config/agent_mcp_access.json` — quels agents ont accès à quels MCP
- Auto-détection `use_tools` : si un agent a des MCP configurés, `use_tools=True`

### Serveurs actifs

GitHub, Notion, Git, Fetch + RAG (pgvector/Voyage AI)

---

## Human Gate & Ask Human

### Human Gate (validation)

- `requires_approval: true` dans le registry
- Poste dans `#human-review` après l'output de l'agent
- Réponses : `approve`, `revise <commentaire>`, `reject`
- Timeout 30 min avec 4 rappels (2, 4, 8, 16 min)
- Rappels : juste "attend toujours une réponse (question posée à HH:MM)"

### Ask Human (question ouverte)

- Tool `ask_human(question, context)` disponible pour tous les agents avec tools
- Le LLM décide quand poser une question
- Même timeout 30 min avec rappels
- Timeout → "Continue avec ton meilleur jugement"

---

## Multi-équipes (teams.json)

### Concept

Chaque équipe est isolée avec :
- Son propre `agents_registry.json`
- Ses propres prompts
- Son propre channel Discord
- Son propre state (thread isolé)

### Configuration

```json
{
  "teams": {
    "default": {
      "name": "Equipe Produit",
      "agents_registry": "agents_registry.json",
      "llm_providers": "llm_providers.json",
      "prompts_dir": "v1",
      "discord_channels": ["ID_CHANNEL"],
      "mcp_access": "agent_mcp_access.json"
    }
  },
  "channel_mapping": {
    "ID_CHANNEL": "default"
  }
}
```

### Convention d'ID

`^[a-z0-9][a-z0-9_-]*$` — lowercase, pas d'espaces ni caractères spéciaux.

---

## Discord — Commandes

| Commande | Effet |
|---|---|
| `!agent <id> <tâche>` | Route directement vers un agent |
| `!a <alias> <tâche>` | Raccourci (ex: `!a lead Cree le repo`) |
| `!reset` | Purge le state du channel |
| `!new <nom>` | Nouveau contexte projet |
| `!status` | État de la plateforme |

### Aliases

`analyste`, `designer`, `ux`, `architecte`, `archi`, `lead`, `frontend`, `front`, `backend`, `back`, `mobile`, `qa`, `test`, `devops`, `ops`, `docs`, `doc`, `avocat`, `legal`

---

## Formatage Discord

- Messages découpés intelligemment à 1900 chars (coupe sur les sauts de ligne)
- Booléens groupés : `✅ Api Contract · ❌ Merge Conflicts · Files: 0`
- Structures imbriquées : `▸ Repository Structure :` avec indentation
- Profondeur max 2 niveaux pour éviter le spam

---

## RAG (Retrieval Augmented Generation)

- **Embeddings** : Voyage AI (`voyage-3-large`)
- **Vector store** : pgvector dans PostgreSQL
- **Tools** : `rag_search(query, source_type, top_k)` et `rag_index(content)`
- Chaque agent peut chercher dans le RAG et y indexer ses livrables

---

## Dashboard Admin (port 8080)

- FastAPI + HTML/JS statique
- Auth cookie (`WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` dans `.env`)
- Gestion : agents, LLM providers, MCP, équipes, prompts, .env
- Git : pull, commit, status (credentials configurables dans l'UI)
- Scripts : start, restart, build
- Chat LLM intégré pour tester les providers

---

## Observabilité — Langfuse (port 3000)

- Open-source, self-hosted
- Trace chaque appel LLM : prompt, réponse, tokens, latence
- Remplace LangSmith (pas de dépendance cloud)
- Intégration via callback handler dans `base_agent.py`

---

## Fichiers de configuration — Résumé

| Fichier | Contenu | Secrets ? |
|---|---|---|
| `.env` | Clés API, tokens, passwords | **OUI** |
| `config/agents_registry.json` | Définition des agents | Non |
| `config/llm_providers.json` | Providers LLM + throttling | Non |
| `config/teams.json` | Multi-équipes | Non |
| `config/agent_mcp_access.json` | MCP par agent | Non |
| `config/mcp_servers.json` | Serveurs MCP | Non |
| `prompts/v1/*.md` | Prompts des agents | Non |

---

## Scripts d'installation

| Script | Rôle |
|---|---|
| `00-configure-lxc.sh` | Config LXC Proxmox |
| `01-proxmox-create-vm.sh` | Création VM |
| `02-install-docker.sh` | Installation Docker |
| `03-install-langgraph.sh` | Déploiement stack Docker + téléchargement configs |
| `05-install-rag.sh` | Installation RAG pgvector |
| `06-install-agents.sh` | Installation agents + prompts + Discord |
| `14-install-mcp.sh` | Installation MCP (interactif, 29 serveurs) |

---

## Projet test : PerformanceTracker

- **Brief** : SaaS suivi performances sportives multi-disciplines
- **Stack** : Flutter Android + FastAPI + PostgreSQL
- **Modèle** : Freemium (gratuit limité + premium)
- **Repo GitHub** : `gaelgael5/PerformanceTracker`
- **État** : Structure initialisée, Discovery en cours (PRD + Audit juridique)

---

## Points d'attention

1. **Rate limit Anthropic** : 30K TPM (Tier 1). Le throttling est configuré dans `llm_providers.json`. Éviter plus de 2 agents en parallèle.
2. **Notion MCP** : Token API à vérifier (`ntn_...`). L'agent utilise `API-post-search`, `API-post-page`.
3. **Le Lead Dev** utilise `gaelgael5` comme owner GitHub (pas `gaelbeard`).
4. **Les outputs `blocked`** sont filtrés du contexte pour ne pas empoisonner les futurs appels.
5. **Le gateway timeout** est 35 min pour couvrir les 30 min d'attente humaine.

---

## TODO — Tâches restantes

### Terminé ✅
1. Infrastructure LXC + Docker opérationnelle
2. 13 agents avec registry JSON (zéro fichiers Python individuels)
3. Gateway v0.6.0 : persistence + direct routing + parallélisme réel
4. Thread persistence PostgreSQL + commande `!reset`
5. MCP lazy install + locks thread-safe
6. Rate limit throttling multi-provider (20 retries, backoff ×2, cap 120s)
7. Human gate Discord (30 min, 4 rappels)
8. Boucle conversationnelle ask_human (30 min, rappels)
9. Interface Discord user-friendly (formatage, smart split 1900 chars)
10. Volumes mappés sur l'hôte (`/opt/langgraph-data/`)
11. Voyage AI billing OK (RAG pgvector)
12. Support multi-modèles (llm_providers.json, 17 providers, 9 types)
13. Multi-équipes (teams.json, isolation par channel Discord)
14. Prompt orchestrateur amélioré (routing intelligent par type de demande)
15. Prompt Lead Dev (fait ou délègue)
16. Publication GitHub via Documentaliste (testé, fonctionne)
17. Dashboard admin web (port 8080) avec auth, git, gestion configs
18. Langfuse ajouté au docker-compose (port 3000)
19. Scripts utilitaires (start.sh, restart.sh, build.sh)

### En cours / À faire 🔧
20. **Transition de phases** — Discovery → Design → Build → Ship. L'orchestrateur a les règles mais le mécanisme de human gate pour les transitions n'est pas testé end-to-end.
21. **Publication Notion** — Le MCP Notion retourne 401 (token invalide). À corriger : vérifier le token sur https://developers.notion.com/, re-tester avec `!agent docs`.
22. **Délégation Lead Dev → sous-agents** — Le Lead Dev retourne `status: delegating` mais le gateway ne détecte pas encore ce status pour lancer automatiquement les sous-agents ciblés. À implémenter dans `gateway.py`.
23. **Intégration Langfuse** — Les containers sont dans le docker-compose mais le callback handler n'est pas encore branché dans `base_agent.py`. À ajouter : `LangfuseCallbackHandler` dans `get_llm()` ou `_call_llm()`.
24. **Dashboard web — features manquantes** :
    - Visualisation des logs agents en temps réel
    - Gestion des équipes (créer, modifier, supprimer) — partiellement fait, bug sur fichier teams.json vide corrigé
    - Monitoring des threads actifs et leur state
25. **Communication email** — Alternative à Discord (SMTP ou API comme SendGrid/Mailgun) pour les notifications et le human gate.
26. **Tests end-to-end** — Tester un cycle complet Discovery → Design → Build avec le projet PerformanceTracker.
27. **Structure Shared/Teams/** — La nouvelle arborescence avec `Shared/Teams/team_project/` n'est pas encore implémentée dans `agent_loader.py`. Le loader lit actuellement `config/` uniquement.
