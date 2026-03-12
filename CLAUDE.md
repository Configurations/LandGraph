# LandGraph Multi-Agent Platform — Documentation Technique

## Vue d'ensemble

LandGraph est une plateforme multi-agent basée sur **LangGraph** (Python) qui orchestre 13 agents IA spécialisés pour gérer le cycle de vie complet d'un projet logiciel (Discovery → Design → Build → Ship → Iterate). Les agents communiquent via un système de **canaux factorisés** (Discord, Email, extensible Telegram), sont pilotés par un **Orchestrateur IA** guidé par un **Workflow Engine**, et utilisent des **MCP servers** pour interagir avec GitHub, Notion, et d'autres services.

---

## Infrastructure

- **Hôte** : Proxmox LXC 110 (privileged, 8 vCPU, 8GB RAM)
- **OS** : Ubuntu 24
- **Container runtime** : Docker + Docker Compose
- **Données persistantes** : `/opt/langgraph-data/{postgres,redis}/`

### Stack Docker

| Service | Image | Port | Rôle |
|---|---|---|---|
| `langgraph-postgres` | pgvector/pgvector:pg16 | 5432 (local) | BDD principale + pgvector (RAG) |
| `langgraph-redis` | redis:7-alpine | 6379 (local) | Cache + pub/sub |
| `langgraph-api` | Custom (Dockerfile) | **8123** | API FastAPI — gateway + agents |
| `discord-bot` | Custom (Dockerfile.discord) | — | Bot Discord — interface utilisateur |
| `langgraph-admin` | Custom (Dockerfile.admin) | **8080** | Dashboard web administration |
| `openlit-clickhouse` | clickhouse/clickhouse-server:24.4.1 | — | OLAP traces OpenLIT |
| `hitl-console` | Custom (Dockerfile.hitl) | **8090** | Console HITL — validation humaine web |
| `openlit` | ghcr.io/openlit/openlit:latest | **3000** | Observabilité LLM (UI + OTel collector) |

---

## Structure du code

```
langgraph-project/
├── agents/
│   ├── gateway.py              ← API FastAPI v0.6.0 (routing, persistence, parallélisme, auto-dispatch workflow)
│   ├── orchestrator.py         ← Noeud LangGraph — décisions de routing guidées par workflow engine
│   ├── discord_listener.py     ← Bot Discord (!agent, !reset, !new, !status)
│   └── shared/
│       ├── team_resolver.py    ← SOURCE UNIQUE de vérité pour trouver les fichiers (configs, prompts, workflow)
│       ├── channels.py         ← Interface abstraite MessageChannel + implémentations Discord/Email
│       ├── workflow_engine.py  ← Lit workflow.json, valide transitions, gère parallel_groups
│       ├── base_agent.py       ← Classe de base — Pipeline + ReAct + tools + human gate
│       ├── agent_loader.py     ← Charge agents depuis registry JSON (multi-équipes via team_resolver)
│       ├── llm_provider.py     ← Factory multi-provider (9 types, 17 providers)
│       ├── rate_limiter.py     ← Throttling par env_key + retry exponentiel (20 retries)
│       ├── mcp_client.py       ← Lazy install MCP + cache global + locks
│       ├── human_gate.py       ← Validation humaine via canal factorisé (30 min, rappels)
│       ├── agent_conversation.py ← Questions ouvertes aux humains via canal factorisé
│       ├── state.py            ← State LangGraph partagé
│       └── discord_tools.py    ← Helpers Discord (embeds, tools LangChain)
│
├── config/                     ← Dossier de config racine (team_resolver le détecte)
│   ├── teams.json              ← Liste des équipes + channel_mapping
│   ├── llm_providers.json      ← 17 providers LLM + throttling par env_key
│   ├── mcp_servers.json        ← Config des serveurs MCP (global)
│   ├── langgraph.json          ← Config LangGraph
│   ├── Team1/                  ← Dossier de l'équipe (directory depuis teams.json)
│   │   ├── agents_registry.json    ← 13 agents + orchestrator
│   │   ├── agent_mcp_access.json   ← MCP autorisés par agent
│   │   ├── Workflow.json           ← Phases, transitions, parallel_groups, exit_conditions
│   │   ├── orchestrator.md         ← Prompt orchestrateur
│   │   ├── lead_dev.md             ← Prompt Lead Dev
│   │   ├── requirements_analyst.md ← Prompt Analyste
│   │   └── ... (13 fichiers .md)
│   └── Team2/                  ← Autre équipe (même structure)
│
├── hitl/
│   ├── server.py               ← Console HITL FastAPI (port 8090)
│   ├── requirements.txt        ← Deps HITL (fastapi, passlib, httpx, jose)
│   └── static/                 ← Frontend HITL (login, inbox, agents, membres)
│       ├── index.html
│       ├── js/app.js
│       └── css/style.css
├── web/
│   ├── server.py               ← Dashboard admin FastAPI
│   └── static/                 ← Frontend web
├── docker-compose.yml
├── Dockerfile / Dockerfile.discord / Dockerfile.admin
├── .env                        ← Secrets uniquement
├── start.sh / restart.sh / build.sh
└── requirements.txt
```

---

## Résolution des fichiers — team_resolver.py

**Source unique de vérité** pour trouver les fichiers de config, prompts, et workflow. Tous les modules passent par lui.

### Logique

1. Trouve le dossier de config racine (celui qui contient `teams.json`) parmi : `config/`, `/app/config/`
2. Lit `teams.json` pour trouver le `directory` d'une équipe
3. Résout les chemins : `config/<directory>/<fichier>`
4. Fallback global si le fichier n'existe pas dans le dossier de l'équipe

### Modules qui l'utilisent

| Module | Fichiers cherchés via team_resolver |
|---|---|
| `agent_loader.py` | `agents_registry.json`, `agent_mcp_access.json` |
| `base_agent.py` | Prompts `.md` |
| `workflow_engine.py` | `Workflow.json` |
| `orchestrator.py` | `agents_registry.json`, `orchestrator.md` |
| `llm_provider.py` | `llm_providers.json` |
| `rate_limiter.py` | `llm_providers.json` (throttling) |
| `mcp_client.py` | `mcp_servers.json`, `agent_mcp_access.json` |

---

## Canaux de communication — channels.py

Architecture factorisée pour la communication agents ↔ humains.

### Interface MessageChannel

```python
class MessageChannel(ABC):
    async def send(channel_id, message) → bool
    async def ask(channel_id, agent_name, question, timeout) → {answered, response, author, timed_out}
    async def approve(channel_id, agent_name, summary, timeout) → {approved, response, reviewer, timed_out}
    # + wrappers *_sync() automatiques
```

### Implémentations

| Canal | Classe | Envoi | Réception |
|---|---|---|---|
| Discord | `DiscordChannel` | REST API Discord | Polling messages |
| Email | `EmailChannel` | SMTP | IMAP polling |
| Telegram | (à venir) | Bot API | Webhook/polling |

### Utilisation

```python
from agents.shared.channels import get_channel, get_default_channel
ch = get_default_channel()  # lit DEFAULT_CHANNEL dans .env
await ch.send("123456", "Hello")
await ch.approve("123456", "Lead Dev", "PRD validé ?")
```

### Modules branchés sur channels.py

- `gateway.py` → `post_to_channel()` (remplace l'ancien `post_to_discord`)
- `human_gate.py` → délègue à `channels.approve()`
- `agent_conversation.py` → délègue à `channels.ask()`

---

## Workflow Engine — workflow_engine.py

Lit `Workflow.json` depuis le dossier de l'équipe et pilote le cycle de vie du projet.

### Fonctions principales

| Fonction | Rôle |
|---|---|
| `get_agents_to_dispatch(phase, outputs, team)` | Quels agents lancer maintenant ? (respecte parallel_groups + depends_on) |
| `check_phase_complete(phase, outputs, team)` | La phase est-elle terminée ? (agents requis + deliverables) |
| `can_transition(phase, outputs, alerts, team)` | Peut-on passer à la phase suivante ? |
| `get_workflow_status(phase, outputs, team)` | État complet pour l'affichage |

### Parallel Groups

Les agents d'une phase sont organisés en groupes ordonnés (A, B, C). Le groupe B ne démarre qu'après que le groupe A soit complet.

```
Discovery : A = [requirements_analyst, legal_advisor]
Design :    A = [ux_designer, architect, planner]
Build :     A = [lead_dev] → B = [dev_frontend, dev_backend, dev_mobile] → C = [qa_engineer]
```

### Auto-dispatch dans le gateway

Après qu'un groupe termine, le gateway redemande au workflow engine s'il y a un groupe suivant. Chaînage automatique récursif (max 5 niveaux).

```
Groupe A termine → workflow engine : "groupe B suivant" → auto-dispatch B
Groupe B termine → workflow engine : "groupe C suivant" → auto-dispatch C
Groupe C termine → workflow engine : "phase complete" → propose human_gate
```

---

## Agents (13 + Orchestrateur)

Définis dans `config/Team1/agents_registry.json`. Pas de fichiers Python individuels — tout passe par `BaseAgent` + registry.

### Champs du registry

```json
{
  "agents": {
    "orchestrator": {
      "name": "Orchestrateur",
      "llm": "claude-sonnet",
      "temperature": 0.2,
      "max_tokens": 4096,
      "prompt": "orchestrator.md",
      "type": "orchestrator"
    },
    "lead_dev": {
      "name": "Lead Dev",
      "llm": "claude-sonnet",
      "temperature": 0.3,
      "max_tokens": 32768,
      "prompt": "lead_dev.md",
      "type": "single",
      "use_tools": true,
      "requires_approval": false
    }
  }
}
```

### Liste des agents

| Agent | Rôle | Type | Phase |
|---|---|---|---|
| `orchestrator` | Routing intelligent, guidé par workflow engine | orchestrator | Système |
| `requirements_analyst` | PRD, User Stories, MoSCoW | pipeline (3 étapes) | Discovery |
| `legal_advisor` | Audit RGPD, conformité, CGU | pipeline (2 étapes) | Transversal |
| `ux_designer` | Wireframes, mockups, design system | single | Design |
| `architect` | ADRs, C4, OpenAPI specs | single | Design |
| `planner` | Sprint backlog, roadmap, risques | single | Design |
| `lead_dev` | Review, repo, coordination, fait ou délègue | single + tools | Build |
| `dev_frontend_web` | Code React/Next.js/TypeScript | single | Build |
| `dev_backend_api` | Code Python/FastAPI/SQLAlchemy | single | Build |
| `dev_mobile` | Code Flutter/React Native | single | Build |
| `qa_engineer` | Tests E2E, unitaires, validation | single | Build |
| `devops_engineer` | CI/CD, Docker, déploiement | single | Ship |
| `docs_writer` | Documentation, rapports, README | single + tools | Ship |

### Hiérarchie de routing

L'Orchestrateur reçoit le contexte enrichi par le workflow engine :
- `suggested_agents_to_dispatch` : recommandation du workflow
- `phase_complete` / `can_transition` : état de la phase
- Il suit les recommandations du workflow sauf cas particulier

Le Lead Dev est le seul à dispatcher vers les devs (frontend, backend, mobile).

---

## Gateway (gateway.py) — v0.6.0

### Endpoints

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/health` | GET | Health check |
| `/status` | GET | Liste agents + équipes |
| `/invoke` | POST | Appel agent (direct ou orchestré) |
| `/reset` | POST | Purge le state d'un thread |
| `/workflow/status/{thread_id}` | GET | État du workflow pour un thread |

### Flux d'un message

```
Discord message → discord_listener → POST /invoke
  → resolve_agents(channel_id) → team_resolver → team_id
  → load_or_create_state(thread_id, team_id)
  → orchestrator_node(state) ← workflow engine enrichit le contexte
  → decisions → background_tasks.add_task(run_orchestrated)
    → run_agents_parallel (groupe A)
    → auto-dispatch (groupe B, C...) via workflow engine
    → phase complete → human_gate
```

### Thread persistence

- `thread_id = "project-channel-{channel_id}"`
- State sauvegardé dans PostgreSQL via `PostgresSaver`
- Le state contient `_team_id` pour que l'orchestrateur sache quelle équipe
- `!reset` purge le state

---

## LLM Providers (llm_providers.json)

### Types supportés (9)

`anthropic`, `openai`, `azure`, `google`, `mistral`, `ollama`, `groq`, `deepseek`, `moonshot`

### 17 providers pré-configurés

Claude Sonnet/Opus/Haiku, GPT-4o/Mini, Azure GPT-4o, Gemini Flash/Pro, Mistral Large, DeepSeek Chat/Coder, Kimi K2/K2.5, Groq Llama 70B, Ollama Llama3/Codestral/Qwen

### Throttling

- Par `env_key` (même clé API = même compteur)
- Sliding window 60s (RPM + TPM)
- 20 retries avec backoff exponentiel (×2, cap 120s)

### Utilisation par agent

`"llm": "claude-sonnet"` dans le registry. Override via env : `ARCHITECT_LLM=gpt-4o`

---

## MCP (Model Context Protocol)

- 29 serveurs dans le catalogue (`mcp_catalog.csv`)
- Types : `npx` (80%), `uvx` (20%), `python`, `node`, `docker`, `bunx`, `deno`
- Lazy install : premier appel installe globalement, les suivants sont immédiats
- Lock par package (thread-safe, pas deux installs simultanées)
- Config : `mcp_servers.json` (global) + `agent_mcp_access.json` (par équipe)

### MCP SSE Server (agents exposés)

Chaque agent est exposable comme tool MCP via SSE :

- **Endpoint** : `GET /mcp/{team_id}/sse` (port 8123)
- **Auth** : `Authorization: Bearer lg-<payload>.<hmac>` — token HMAC-SHA256 auto-signé
- **Validation** : HMAC check (zéro DB hit) → SHA-256 hash → lookup PostgreSQL (revoked? expired?) → team check
- **Tools exposés** : intersection agents de l'équipe ∩ agents autorisés par la key
- **Table** : `project.mcp_api_keys` (key_hash, name, preview, teams, agents, expires_at, revoked)
- **Gestion** : dashboard admin → onglet Configuration → sous-onglet Sécurité
- **Secret** : `MCP_SECRET` dans `.env` — signe tous les tokens

---

## Multi-équipes (teams.json)

### Structure

```json
{
  "teams": [
    {
      "id": "team1",
      "name": "Team 1",
      "directory": "Team1",
      "discord_channels": []
    }
  ],
  "channel_mapping": {}
}
```

Le `directory` est relatif au dossier de config. `team_resolver` résout : `config/Team1/agents_registry.json`, `config/Team1/Workflow.json`, `config/Team1/lead_dev.md`, etc.

### Isolation

Chaque équipe a son propre registry, workflow, prompts, MCP access, et channel Discord.

---

## Discord — Commandes

| Commande | Effet |
|---|---|
| `!agent <id> <tâche>` | Route directement vers un agent |
| `!a <alias> <tâche>` | Raccourci |
| `!reset` | Purge le state du channel |
| `!new <nom>` | Nouveau contexte projet |
| `!status` | État de la plateforme |

Aliases : `analyste`, `designer`, `ux`, `architecte`, `archi`, `lead`, `frontend`, `front`, `backend`, `back`, `mobile`, `qa`, `test`, `devops`, `ops`, `docs`, `doc`, `avocat`, `legal`

---

## Human Gate & Ask Human

- **Human Gate** : `requires_approval: true` → validation via `channels.approve()` (Discord ou Email)
- **Ask Human** : tool `ask_human(question, context)` → via `channels.ask()`
- Timeout 30 min avec 4 rappels (2, 4, 8, 16 min)
- Gateway timeout 35 min (couvre l'attente humaine)

---

## HITL Console (port 8090)

Console web pour la validation humaine (Human-In-The-Loop). Les utilisateurs répondent aux questions des agents, approuvent/rejettent les demandes, et suivent l'activité en temps réel.

### Authentification

Deux modes d'authentification supportés :

| Mode | `auth_type` | `password_hash` | Flux |
|---|---|---|---|
| **Local** (email/password) | `local` | bcrypt hash | Inscription → rôle `undefined` → validation admin → accès |
| **Google OAuth** | `google` | `NULL` | Sign-in Google → rôle `undefined` → validation admin → accès |

### Rôles utilisateur

| Rôle | Accès |
|---|---|
| `undefined` | Aucun accès — en attente de validation par un administrateur |
| `member` | Accès aux équipes assignées — répondre aux questions |
| `admin` | Accès complet — toutes les équipes + gestion membres |

### Configurer Google OAuth

1. Créer un projet dans [Google Cloud Console](https://console.cloud.google.com/)
2. Activer l'API "Google Identity" (OAuth consent screen)
3. Créer un identifiant OAuth 2.0 (type: Application Web)
   - Ajouter les origines JavaScript autorisées : `https://your-domain.com` (ou `http://localhost:8090` pour le dev)
   - Pas besoin d'URI de redirection (on utilise Google Identity Services, pas le flux OAuth classique)
4. Copier le **Client ID** dans `config/hitl.json` :

```json
{
  "auth": {
    "jwt_expire_hours": 24,
    "allow_registration": true,
    "default_role": "undefined"
  },
  "google_oauth": {
    "enabled": true,
    "client_id": "123456789-xxxxxxxx.apps.googleusercontent.com",
    "client_secret_env": "GOOGLE_CLIENT_SECRET",
    "allowed_domains": ["company.com"]
  }
}
```

- `enabled` : active/désactive le bouton Google sur la page de login
- `client_id` : l'identifiant public Google (non sensible, stocké en JSON)
- `client_secret_env` : nom de la variable d'environnement pour le secret (dans `.env`)
- `allowed_domains` : liste blanche de domaines email autorisés (vide = tous les domaines)

### Flux Google OAuth

```
Utilisateur clique "Sign in with Google"
  → Google Identity Services renvoie un ID token (JWT)
  → POST /api/auth/google {credential: <token>}
  → Backend vérifie le token via googleapis.com/tokeninfo
  → Vérifie audience (client_id) + email_verified + domaine autorisé
  → Si nouvel utilisateur : INSERT avec role='undefined', auth_type='google', password_hash=NULL
  → HTTP 403 "En attente de validation"
  → Admin assigne un rôle (member/admin) + équipes dans le dashboard
  → Utilisateur peut se reconnecter avec Google
```

### Endpoints HITL

| Endpoint | Méthode | Auth | Rôle |
|---|---|---|---|
| `/api/auth/login` | POST | Non | Login email/password |
| `/api/auth/register` | POST | Non | Inscription (rôle `undefined`) |
| `/api/auth/google` | POST | Non | Login Google (ID token) |
| `/api/auth/google/client-id` | GET | Non | Retourne le Client ID (pour le frontend) |
| `/api/auth/me` | GET | JWT | Profil utilisateur courant |
| `/api/teams` | GET | JWT | Équipes de l'utilisateur |
| `/api/teams/{id}/questions` | GET | JWT | Questions HITL (inbox) |
| `/api/questions/{id}/answer` | POST | JWT | Répondre / approuver / rejeter |
| `/api/teams/{id}/members` | GET/POST | JWT | Gestion membres |
| `/api/teams/{id}/ws` | WS | JWT (query) | Notifications temps réel |

### Base de données

```sql
-- Table hitl_users (modifiée)
password_hash TEXT           -- NULL pour les comptes Google
role          TEXT DEFAULT 'undefined'  -- 'undefined' | 'member' | 'admin'
auth_type     TEXT DEFAULT 'local'      -- 'local' | 'google'
```

---

## Dashboard Admin (port 8080)

- FastAPI + HTML/JS statique
- Auth cookie (`WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD`)
- Git : pull (auto-reconfigure remote), commit, status
- `.gitignore` auto-généré au démarrage si absent
- `GIT_USER_EMAIL` / `GIT_USER_NAME` configurables via `.env`

---

## Observabilité

### EventBus interne (`agents/shared/event_bus.py`)
- Bus pub/sub singleton avec ring buffer (2000 events)
- 12 types d'events : agent_start/complete/error, llm_call_start/end, tool_call, pipeline_step_start/end, human_gate_requested/responded, agent_dispatch, phase_transition
- Handlers : Langfuse (si env vars présentes), Webhooks (HMAC-SHA256), Dashboard (via `/events`)

### OpenLIT (port 3000)
- Open-source, self-hosted (2 containers : ClickHouse + OpenLIT)
- Auto-instrumentation LangChain via `openlit.init()` dans le gateway startup
- Collecteur OTel intégré (ports 4317 gRPC, 4318 HTTP)
- UI sur port 3000, données persistées dans `/opt/langgraph-data/openlit*`

---

## Fichiers de configuration

| Fichier | Emplacement | Contenu | Secrets ? |
|---|---|---|---|
| `.env` | Racine projet | Clés API, tokens, passwords | **OUI** |
| `teams.json` | `config/` | Liste équipes + channel_mapping | Non |
| `llm_providers.json` | `config/` | 17 providers + throttling | Non |
| `mcp_servers.json` | `config/` | Serveurs MCP (global) | Non |
| `langgraph.json` | `config/` | Config LangGraph | Non |
| `hitl.json` | `config/` | Auth HITL + Google OAuth (client_id, domaines) | Non |
| `agents_registry.json` | `config/Team1/` | 13 agents + orchestrator | Non |
| `agent_mcp_access.json` | `config/Team1/` | MCP par agent | Non |
| `Workflow.json` | `config/Team1/` | Phases, transitions, rules | Non |
| `*.md` | `config/Team1/` | Prompts des agents | Non |

---

## Variables d'environnement clés

```bash
# Canal par défaut (discord | email)
DEFAULT_CHANNEL=discord

# Discord
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_COMMANDS=...
DISCORD_CHANNEL_REVIEW=...

# Email (si DEFAULT_CHANNEL=email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
IMAP_HOST=imap.gmail.com

# LLM
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...

# Base de données
DATABASE_URI=postgresql://langgraph:...@langgraph-postgres:5432/langgraph
REDIS_URI=redis://:...@langgraph-redis:6379/0

# HITL Console
HITL_JWT_SECRET=...           # Secret JWT (fallback: MCP_SECRET)
HITL_ADMIN_EMAIL=admin@...    # Email admin initial (seed)
HITL_ADMIN_PASSWORD=...       # Password admin initial (seed)
HITL_PUBLIC_URL=https://...   # URL publique HITL (pour les liens de reset)
GOOGLE_CLIENT_SECRET=...      # Secret Google OAuth (si google_oauth.enabled)
```

---

## Scripts d'installation

| Script | Rôle |
|---|---|
| `00-create-lxc.sh` | Création LXC Proxmox + installation complète |
| `00-prepare-existing-lxc4Docker.sh` | Prépare un LXC existant pour Docker |
| `01-install-docker.sh` | Docker Engine + Compose + Caddy reverse proxy |
| `02-install-langgraph.sh` | Infra + code agents + configs équipe (paramètre branche) |
| `03-install-rag.sh` | Couche RAG (pgvector + Voyage AI) |
| `start.sh / stop.sh / restart.sh / build.sh / update.sh` | Gestion des containers + mise à jour |

Le script 02 télécharge tout depuis GitHub : Dockerfiles, code agents (`Agents/Shared/*.py`, `Agents/*.py`), configs globales, et structure d'équipe. Les prompts sont gérés via git pull depuis le dashboard admin.

---

## Projet test : PerformanceTracker

- **Brief** : SaaS suivi performances sportives multi-disciplines
- **Stack** : Flutter Android + FastAPI + PostgreSQL
- **Modèle** : Freemium
- **Repo GitHub** : `gaelgael5/PerformanceTracker`
- **État** : Structure initialisée, Discovery en cours

---

## Terminé ✅

### Infrastructure
1. Infrastructure LXC + Docker (5 containers opérationnels)
2. Volumes mappés sur l'hôte
3. OpenLIT observabilité dans docker-compose (port 3000)
4. Scripts utilitaires + script d'installation unifié (02)

### Agents & Orchestration
5. 13 agents avec registry JSON (zéro fichiers Python individuels)
6. Gateway v0.6.0 : persistence + direct routing + parallélisme + auto-dispatch workflow
7. Thread persistence PostgreSQL + `!reset`
8. Workflow engine — phases, transitions, parallel_groups, auto-dispatch
9. Auto-dispatch groupes séquentiels (A → B → C, max 5 niveaux)
10. Orchestrateur guidé par workflow engine (contexte enrichi)
11. Prompt orchestrateur + Lead Dev (fait ou délègue)
12. team_resolver — source unique de vérité pour les chemins

### LLM & Outils
13. Multi-modèles (llm_providers.json, 17 providers, 9 types)
14. Rate limit throttling multi-provider (20 retries, backoff ×2, cap 120s)
15. MCP lazy install + locks thread-safe (29 serveurs catalogue)
16. Voyage AI billing OK (RAG pgvector)

### Communication
17. Canaux factorisés (Discord + Email, extensible Telegram)
18. Interface Discord user-friendly (formatage, smart split 1900 chars)
19. Human gate via canal factorisé (30 min, 4 rappels)
20. Boucle conversationnelle ask_human via canal factorisé

### Équipes & Dashboard
21. Multi-équipes (teams.json, isolation par channel Discord)
22. Dashboard admin web (port 8080) — auth, git, gestion configs, channels, import/export, monitoring
23. Publication GitHub via Documentaliste
24. EventBus observabilité — bus d'events centralisé (`event_bus.py`) avec ring buffer, Langfuse handler, webhook dispatcher
25. Monitoring dashboard — events temps réel, logs Docker, état containers (start/stop/restart)
26. OpenLIT observabilité externe — auto-instrumentation LangChain, ClickHouse + UI (port 3000)
27. MCP SSE Server — agents exposés comme tools MCP par équipe (`/mcp/{team_id}/sse`), auth HMAC signée + PostgreSQL, gestion API keys dans le dashboard admin

### HITL Console
28. Console HITL web (port 8090) — inbox, agents, membres, WebSocket temps réel
29. Auth locale (email/password) avec inscription en rôle `undefined` (validation admin requise)
30. Auth Google OAuth — Google Identity Services, config via `config/hitl.json`, restriction par domaine
31. Gestion utilisateurs admin — colonne auth_type, rôle `undefined` visible en rouge, validation par l'admin

## À faire 🔧

1. **Publication Notion** — Token MCP 401 à corriger
2. **Tests end-to-end** — Cycle complet Discovery → Ship avec PerformanceTracker
3. **Long-term memory (LangMem)** — Mémoire sémantique cross-thread (chaque thread est isolé actuellement)
4. **Cron jobs** — Tâches planifiées sur le graph
5. **Concurrency control** — Gérer les messages qui arrivent avant la fin du précédent
6. **Inter-team outbound** — Demander une analyse à une équipe étrangère au système (intégrable dans le graph)
7. **Inter-team inbound** — Accepter un entrant de la part d'une équipe étrangère au système (intégrable dans le graph)
