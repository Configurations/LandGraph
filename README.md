# LangGraph Multi-Agent Platform

Plateforme multi-agents IA auto-hebergee sur Proxmox (VM ou LXC). 13 agents specialises orchestres par un Workflow Engine pour gerer le cycle de vie complet d'un projet logiciel : Discovery → Design → Build → Ship → Iterate.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    PROXMOX VE HOST                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │         LXC / VM : langgraph-agents                │  │
│  │              Ubuntu 24.04 LTS                      │  │
│  │                                                    │  │
│  │   Docker Compose :                                 │  │
│  │   ├── PostgreSQL 16 + pgvector    (:5432 local)    │  │
│  │   ├── Redis 7                     (:6379 local)    │  │
│  │   ├── LangGraph API (FastAPI)     (:8123)          │  │
│  │   ├── Discord Bot                                  │  │
│  │   ├── Mail Bot                                     │  │
│  │   ├── Admin Dashboard             (:8080)          │  │
│  │   ├── OpenLIT (observabilite)      (:3000)          │  │
│  │   └── OpenLIT ClickHouse          (interne)        │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Donnees : /opt/langgraph-data/{postgres,redis,openlit*}/ │
└──────────────────────────────────────────────────────────┘
```

## Prerequis

- Serveur **Proxmox VE 8.x / 9.x**
- ISO **Ubuntu 24.04 LTS** dans le stockage Proxmox
- Acces SSH a l'hote Proxmox
- Cle API **Anthropic** (Claude) — seul cout recurrent

## Installation

Trois scripts sequentiels. Chaque script se telecharge et s'execute en une commande.

> **Base URL** : `https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/`

### Etape 0 — Creer le container/VM

**Ou** : shell de l'hote Proxmox.

```bash
# Option A — Creer un container LXC (recommande)
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/00-create-lxc.sh)"

# Option B — Configurer un LXC existant pour Docker
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/00-configure-lxc.sh)" _ <CTID>
```

| Parametre | Valeur par defaut  |
|-----------|--------------------|
| Nom       | `langgraph-agents` |
| CPU       | 4 cores            |
| RAM       | 8 Go               |
| Disque    | 30 Go (local-lvm)  |

### Etape 1 — Installer Docker

**Ou** : SSH sur la VM/LXC Ubuntu.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/01-install-docker.sh)"
```

Installe Docker Engine + Compose, configure les logs, active UFW (ports 8123, 8080, 3000 en reseau local). **Se reconnecter apres execution** (groupe docker).

### Etape 2 — Installer LangGraph

**Ou** : SSH sur la VM/LXC, apres reconnexion.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/02-install-langgraph.sh)"
```

Ce script deploie le socle complet :

| Composant | Detail |
|-----------|--------|
| Dockerfiles | API, Discord Bot, Mail Bot, Admin |
| Code Python | 13 agents + orchestrateur + gateway + listeners |
| Configs globales | `teams.json`, `llm_providers.json`, `mcp_servers.json`, `discord.json`, `mail.json` |
| Infra | PostgreSQL 16 + pgvector, Redis 7 |
| Scripts | `start.sh`, `stop.sh`, `restart.sh`, `build.sh` |

**Apres execution** :

1. Configurer le `.env` :
   ```bash
   nano ~/langgraph-project/.env
   ```

2. Lancer la stack :
   ```bash
   cd ~/langgraph-project
   ./start.sh
   ```

3. Creer une equipe et ses agents depuis le dashboard admin : `http://<IP>:8080`

### Etape 3 (optionnel) — RAG

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/03-install-rag.sh)"
```

Ajoute la couche RAG (embeddings Voyage AI + pgvector). Necessite une cle Voyage AI (gratuit 50M tokens/mois).

## Configuration

### Fichiers de configuration (config/)

Tout est dans le dossier `config/`. Pas de config en dur dans le code.

| Fichier | Contenu |
|---------|---------|
| `teams.json` | Liste des equipes, channel mapping |
| `llm_providers.json` | 17 providers LLM (Claude, GPT, Gemini, Ollama...) + throttling |
| `mcp_servers.json` | Serveurs MCP disponibles |
| `discord.json` | Config Discord (prefix, aliases, channels, timeouts) |
| `mail.json` | Config Email (SMTP, IMAP, templates, presets Gmail/Outlook/OVH) |
| `langgraph.json` | Config LangGraph |
| `Team1/` | Dossier equipe : registry, workflow, prompts |

### Fichier .env (secrets uniquement)

```bash
# LLM (obligatoire)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# Discord (secret)
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.xxxxx

# Email (secrets)
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
IMAP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# RAG (optionnel)
VOYAGE_API_KEY=pa-xxxxx

# Infra (generes a l'installation)
POSTGRES_DB=langgraph
POSTGRES_USER=langgraph
POSTGRES_PASSWORD=xxxxx
REDIS_PASSWORD=xxxxx
DATABASE_URI=postgres://langgraph:xxxxx@langgraph-postgres:5432/langgraph?sslmode=disable
REDIS_URI=redis://:xxxxx@langgraph-redis:6379/0

# MCP Server (optionnel)
MCP_SECRET=xxxxx

# Admin
WEB_ADMIN_USERNAME=admin
WEB_ADMIN_PASSWORD=xxxxx
```

> Toute la config non-secrete (hosts, ports, channels, aliases, templates) est dans les fichiers JSON.

### Obtenir les cles API

**Anthropic** (obligatoire) : [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key. Budget recommande : 10 EUR/mois.

**Discord Bot** (gratuit) : [discord.com/developers](https://discord.com/developers/applications) → New Application → Bot → Reset Token. Activer les 3 Privileged Gateway Intents (Presence, Server Members, Message Content). OAuth2 scopes : `bot` + `applications.commands`.

**Voyage AI** (quasi gratuit) : [dash.voyageai.com](https://dash.voyageai.com) → API Keys. 50M tokens/mois gratuits.

**Autres LLM** (optionnel) : OpenAI, Google, Mistral, DeepSeek, Kimi, Groq — ajouter les cles dans `.env` et configurer dans `llm_providers.json`.

## Structure du projet

```
langgraph-project/
├── agents/                         ← Code Python (socle technique)
│   ├── gateway.py                  ← API FastAPI v0.6.0
│   ├── orchestrator.py             ← Decisions de routing (guide par workflow engine)
│   ├── discord_listener.py         ← Bot Discord
│   ├── mail_listener.py            ← Bot Email (IMAP polling)
│   └── shared/
│       ├── team_resolver.py        ← Source unique pour trouver les fichiers
│       ├── channels.py             ← Canaux factorises (Discord, Email, extensible)
│       ├── workflow_engine.py      ← Phases, transitions, parallel groups
│       ├── base_agent.py           ← Classe de base (Pipeline + ReAct + tools)
│       ├── agent_loader.py         ← Chargement dynamique depuis registry JSON
│       ├── llm_provider.py         ← Factory multi-provider (9 types)
│       ├── rate_limiter.py         ← Throttling + retry exponentiel
│       ├── mcp_client.py           ← Lazy install MCP + cache (client)
│       ├── mcp_auth.py            ← Tokens HMAC signes + DB PostgreSQL
│       ├── mcp_server.py          ← MCP SSE server (agents comme tools)
│       ├── event_bus.py            ← Bus d'events + webhooks + observabilite
│       ├── human_gate.py           ← Validation humaine
│       ├── agent_conversation.py   ← Questions aux humains
│       └── state.py                ← State LangGraph partage
│
├── config/                         ← Configuration (socle + equipes)
│   ├── teams.json                  ← Liste des equipes + channel mapping
│   ├── llm_providers.json          ← Providers LLM
│   ├── mcp_servers.json            ← Serveurs MCP
│   ├── discord.json                ← Config Discord
│   ├── mail.json                   ← Config Email
│   ├── webhooks.json               ← Webhooks externes (HMAC-SHA256)
│   ├── langgraph.json              ← Config LangGraph
│   └── Team1/                      ← Equipe (cree depuis le dashboard)
│       ├── agents_registry.json
│       ├── Workflow.json
│       ├── agent_mcp_access.json
│       └── *.md                    ← Prompts des agents
│
├── Shared/Teams/                   ← Templates (modeles d'equipes)
│   ├── DevProject/                 ← Template "Projet de dev"
│   │   ├── agents_registry.json
│   │   ├── Workflow.json
│   │   ├── agent_mcp_access.json
│   │   └── *.md                    ← Prompts pre-configures
│   ├── llm_providers.json          ← Providers partages
│   ├── mcp_servers.json            ← MCP partages
│   └── teams.json
│
├── web/                            ← Dashboard admin
├── docker-compose.yml
├── Dockerfile / Dockerfile.discord / Dockerfile.mail / Dockerfile.admin
├── .env                            ← Secrets uniquement
├── start.sh / stop.sh / restart.sh / build.sh
└── requirements.txt
```

## Templates — Modeles d'equipes

Le dossier `Shared/Teams/` contient des **templates** : des modeles d'equipes pre-configures avec leurs agents, workflow, prompts et MCP.

Quand vous creez une nouvelle equipe depuis le dashboard admin, vous pouvez choisir un template existant comme base. Le template est copie dans `config/<NouvelleEquipe>/` et devient independant — vous pouvez le personnaliser sans affecter le template d'origine.

### Exemple de template : DevProject

Un template pour projet de developpement logiciel (13 agents, 5 phases) est disponible separement dans le depot [Configurations/LandGraph-Templates](https://github.com/Configurations/LandGraph-Templates). Pour l'utiliser, telechargez-le dans `Shared/Teams/DevProject/`.

### Creer son propre template

Depuis le dashboard admin (onglet Templates) ou manuellement :

1. Creer un dossier dans `Shared/Teams/<NomTemplate>/`
2. Y placer `agents_registry.json`, `Workflow.json`, `agent_mcp_access.json`
3. Ajouter les prompts `.md` pour chaque agent
4. Le template apparait dans le dashboard pour les nouvelles equipes

## Workflow Engine

Le workflow est defini dans `Workflow.json` (par equipe) et pilote automatiquement le cycle de vie :

```mermaid
graph TD
    D[Discovery<br/><small>A: analyst + legal</small>]
    DE[Design<br/><small>A: ux + architect + planner</small>]
    B[Build<br/><small>A: lead_dev → B: devs → C: qa</small>]
    S[Ship<br/><small>A: devops + docs</small>]
    I[Iterate]

    D -->|human gate| DE
    DE -->|human gate| B
    B -->|human gate| S
    S --> I
    I -->|cyclique| DE

    style D fill:#6366f1,color:#fff,stroke:#4f46e5
    style DE fill:#818cf8,color:#fff,stroke:#6366f1
    style B fill:#f59e0b,color:#fff,stroke:#d97706
    style S fill:#10b981,color:#fff,stroke:#059669
    style I fill:#71717a,color:#fff,stroke:#52525b
```

Les groupes s'enchainent automatiquement (A termine → B demarre → C demarre). L'humain valide les transitions de phase.

## Canaux de communication

Architecture factorisee — meme interface pour Discord, Email, ou Telegram (a venir).

| Canal | Envoi | Reception | Config |
|-------|-------|-----------|--------|
| Discord | REST API | Bot listener | `discord.json` |
| Email | SMTP | IMAP polling | `mail.json` |

Variable `DEFAULT_CHANNEL` dans `.env` pour choisir le canal principal.

### Commandes (Discord et Email)

| Commande | Effet |
|----------|-------|
| `!agent <id> <tache>` | Route directement vers un agent |
| `!a <alias> <tache>` | Raccourci (ex: `!a lead Cree le repo`) |
| `!reset` | Purge le state du thread |
| `!new <nom>` | Nouveau contexte projet |
| `!status` | Etat de la plateforme |

Par email, les commandes se mettent dans le sujet ou la premiere ligne du body.

## Dashboard Admin (port 8080)

Interface web pour gerer la plateforme sans toucher au code ni aux fichiers. Authentification par cookie (`WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` dans `.env`).

### Onglets

| Onglet | Fonctionnalites |
|--------|-----------------|
| **Secrets** | Gestion du `.env` — ajout, modification, suppression de variables. Valeurs masquees. |
| **MCP** | Catalogue de 29 serveurs MCP. Installation en un clic, activation/desactivation par agent, variables d'environnement requises. |
| **LLM** | Configuration des providers dans `llm_providers.json`. Ajout de providers, choix du modele, test de connexion. |
| **Equipes** | CRUD complet des equipes. Pour chaque equipe : registry des agents, prompts (edition en ligne), workflow (editeur visuel avec validation), MCP access. |
| **Channels** | Configuration Discord (`discord.json`) et Email (`mail.json`) depuis l'interface. Sous-onglets Discord / Mail. |
| **Chat** | Test en direct des providers LLM configures. Choix du modele, temperature, envoi de messages. |
| **Scripts** | Boutons start / stop / restart / build avec sortie terminal en temps reel. |
| **Git** | Status, pull, commit + push. Configuration du remote, credentials. Purge automatique des fichiers sensibles de l'historique. |

### Channels — Discord

- Toggle enabled / disabled
- Prefix des commandes (defaut `!`)
- IDs des channels (commands, review, logs, alerts)
- Guild ID
- Table des aliases (CRUD : ajouter, modifier, supprimer)
- Formatage (longueur max, reactions, split sur newlines)
- Timeouts (API call, human gate, intervalles de rappel)

### Channels — Mail

- Toggle enabled / disabled
- Config SMTP (host, port, TLS/SSL, user, from address, from name)
- Config IMAP (host, port, SSL, user)
- Presets en un clic : Gmail, Outlook, OVH, Infomaniak
- Listener (intervalle de polling, expediteurs autorises, patterns ignores)
- Templates (sujets des mails, instructions de validation, footer)
- Securite (require TLS, verification expediteur, taille max body)

### Equipes — Workflow Editor

- Editeur visuel des phases (drag & drop)
- Configuration des agents par phase (parallel group, required, depends_on, delegated_by)
- Deliverables par phase (agent responsable, required)
- Transitions entre phases (with human gate)
- Regles globales (max agents parallele, QA apres dev)
- Validation automatique : verifie la coherence agents registry ↔ workflow avant sauvegarde

### Acces

```
http://<IP-VM>:8080
```

> **Securite** : restreindre l'acces via UFW (`ufw allow from 192.168.1.0/24 to any port 8080`) ou un reverse proxy avec HTTPS.

## Ports exposes

| Service | Port | Acces |
|---------|------|-------|
| LangGraph API | 8123 | Reseau local |
| Admin Dashboard | 8080 | Reseau local |
| OpenLIT | 3000 | Reseau local |
| OTel gRPC | 4317 | localhost uniquement |
| OTel HTTP | 4318 | localhost uniquement |
| PostgreSQL | 5432 | localhost uniquement |
| Redis | 6379 | localhost uniquement |

## Scripts utilitaires

```bash
./start.sh     # Demarre tous les containers
./stop.sh      # Arrete tous les containers
./restart.sh   # Arrete + demarre
./build.sh     # Rebuild les images + demarre
```

## MCP Server — agents comme tools

Chaque agent LandGraph est exposable comme tool MCP via SSE. Un client MCP externe (Claude Desktop, autre plateforme) peut appeler vos agents directement.

```
Endpoint:  GET http://<IP>:8123/mcp/{team_id}/sse
Auth:      Authorization: Bearer lg-xxxxx.yyyy
```

**Gestion des cles API** : dashboard admin → Equipes → Securite. Les tokens sont signes HMAC-SHA256 (verification sans DB), puis valides en PostgreSQL (revocation, expiration).

**Configuration client** (ex: Claude Desktop) :
```json
{
  "mcpServers": {
    "langgraph": {
      "url": "http://<IP>:8123/mcp/team1/sse",
      "headers": { "Authorization": "Bearer lg-xxxxx.yyyy" }
    }
  }
}
```

Variable requise dans `.env` : `MCP_SECRET=<secret-pour-signer-les-tokens>`

## Observabilite

Deux couches complementaires :

- **EventBus interne** (`event_bus.py`) — bus pub/sub avec ring buffer (2000 events). Alimente le dashboard monitoring, les webhooks externes (HMAC-SHA256), et Langfuse (si configure).
- **OpenLIT** (port 3000) — observabilite LLM externe. Auto-instrumente tous les appels LangChain via OpenTelemetry. UI avec traces, couts, latences. Donnees stockees dans ClickHouse.

Le dashboard admin (onglet Monitoring) affiche les events en temps reel, les logs Docker, et permet de gerer les containers.

## Documentation technique

Le fichier [CLAUDE.md](CLAUDE.md) contient la documentation technique detaillee : architecture interne, flux de donnees, resolution des fichiers, formats JSON, et etat d'avancement du projet.
