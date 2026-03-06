# LangGraph Multi-Agent sur Proxmox

Plateforme multi-agents LangGraph auto-hebergee sur une VM Proxmox, avec PostgreSQL, Redis et communication Discord.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              PROXMOX VE HOST                    │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │         VM: langgraph-agents              │  │
│  │         Ubuntu 24.04 LTS                  │  │
│  │                                           │  │
│  │   Docker Compose Stack :                  │  │
│  │   ├── PostgreSQL 16 + pgvector (:5432)    │  │
│  │   ├── Redis 7 (:6379)                     │  │
│  │   ├── LangGraph API (:8123)               │  │
│  │   └── Discord Bot                         │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Prerequis

- Serveur **Proxmox VE 8.x / 9.x**
- ISO **Ubuntu 24.04 LTS** disponible dans le stockage Proxmox (`local:iso/`)
- Acces SSH a l'hote Proxmox
- Cle API **Anthropic** (pour Claude)
- *(Optionnel)* Bot Discord cree sur [discord.com/developers](https://discord.com/developers/applications)

## Installation

L'installation se deroule en 5 etapes sequentielles. Chaque script est telecharge et execute en une seule commande.

### Etape 1 — Creer la VM sur Proxmox

**Ou** : sur le shell de l'hote Proxmox.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/01-proxmox-create-vm.sh)"
```

Ce script cree une VM avec la configuration suivante :

| Parametre | Valeur par defaut |
|-----------|-------------------|
| Nom       | `langgraph-agents` |
| CPU       | 8 cores            |
| RAM       | 16 Go              |
| Disque    | 100 Go (local-lvm) |
| Reseau    | `vmbr0`            |

Le VMID est optionnel (defaut : `200`).

**Apres execution** : installer Ubuntu 24.04 via la console VNC de Proxmox, configurer une IP statique, puis se connecter en SSH a la VM.

### Etape 2 — Installer Docker

**Ou** : sur la VM Ubuntu fraichement installee.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/02-install-docker.sh?token=GHSAT0AAAAAADWAJ3NGWZAILIQANVLMLJDE2NJXVWA)"
```

Ce script :
- Met a jour le systeme et installe les outils de base
- Installe Docker Engine + Docker Compose (repo officiel)
- Configure Docker pour la production (logs, overlay2, live-restore)
- Active le firewall UFW (SSH + ports 8123 et 3000 en reseau local)
- Active le `qemu-guest-agent` pour Proxmox

**Important** : se deconnecter et se reconnecter apres execution pour que le groupe `docker` soit pris en compte.

### Etape 3 — Installer LangGraph

**Ou** : sur la VM Ubuntu, apres reconnexion.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/03-install-langgraph.sh?token=GHSAT0AAAAAADWAJ3NHUEXBVJCBAGZ6QULY2NJX2HQ)"
```

Ce script cree le projet dans `~/langgraph-project/` avec :
- Un fichier `.env` a completer avec vos cles API
- PostgreSQL 16 + pgvector et Redis 7 via Docker Compose
- Un Dockerfile pour le serveur LangGraph API
- Un agent orchestrateur minimal de test
- Un environnement Python virtualenv local

**Apres execution** :

1. Editer le `.env` avec vos vraies cles :
   ```bash
   nano ~/langgraph-project/.env
   ```

🔑 **ANTHROPIC_API_KEY (obligatoire — seul coût récurrent)**

Aller sur https://console.anthropic.com
Créer un compte (ou se connecter)
Menu gauche → API Keys
Cliquer Create Key → nommer "langgraph-agents"
Copier la clé (commence par sk-ant-api03-...)
Onglet Plans & Billing → ajouter une carte bancaire et mettre un spending limit (ex: 10€/mois pour commencer)


🧠 **VOYAGE_API_KEY (pour le RAG — quasi gratuit)**

Aller sur https://dash.voyageai.com
Créer un compte (gratuit — 50M tokens/mois offerts)
Menu API Keys → Create new API key
Copier la clé (commence par pa-...)


Alternative 0€ : ne pas mettre de clé Voyage et utiliser Ollama en local (voir le EMBEDDING_MODEL=local dans le script RAG). Mais il faut un GPU ou accepter que ce soit plus lent.


🤖 **DISCORD_BOT_TOKEN (gratuit)**

Aller sur https://discord.com/developers/applications
Se connecter avec son compte Discord
Cliquer New Application → nommer "LangGraph Agent" → Create
Menu gauche → Bot
Cliquer Reset Token → Yes, do it! → copier le token
Sur la même page, désactiver Public Bot
Activer les 3 Privileged Gateway Intents :

PRESENCE INTENT ✅
SERVER MEMBERS INTENT ✅
MESSAGE CONTENT INTENT ✅

Menu gauche → OAuth2 → URL Generator

Scopes : cocher bot + applications.commands
Bot Permissions : cocher Send Messages, Read Message History, Add Reactions, Embed Links, Attach Files, Use Slash Commands


Copier l'URL générée en bas → ouvrir dans le navigateur → choisir ton serveur Discord → Autoriser

Les Channel IDs Discord

Dans Discord, aller dans Paramètres utilisateur (roue dentée) → Avancés → activer Mode développeur
Créer tes channels sur ton serveur (#orchestrateur-logs, #human-review, #alerts, #commandes)
Clic droit sur chaque channel → Copier l'identifiant du salon
C'est un nombre comme 1234567890123456789 — le coller dans le .env


📊 LANGSMITH_API_KEY (optionnel — gratuit)

Aller sur https://smith.langchain.com
Créer un compte (gratuit — 100K traces/mois)
Menu → Settings → API Keys → Create API Key
Copier la clé (commence par lsv2_pt_...)


Récapitulatif de ton .env
```
# ─── OBLIGATOIRE ──────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx          # console.anthropic.com → API Keys

# ─── RAG ──────────────────────────────────────
VOYAGE_API_KEY=pa-xxxxx                        # dash.voyageai.com → API Keys

# ─── DISCORD (optionnel) ─────────────────────
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.xxxxx          # discord.com/developers → Bot → Reset Token
DISCORD_CHANNEL_REVIEW=1234567890123456789     # clic droit channel → Copier l'identifiant
DISCORD_CHANNEL_LOGS=1234567890123456789
DISCORD_CHANNEL_COMMANDS=1234567890123456789
DISCORD_GUILD_ID=1234567890123456789           # clic droit sur le nom du serveur → Copier l'identifiant

# ─── OBSERVABILITÉ (optionnel) ───────────────
LANGSMITH_API_KEY=lsv2_pt_xxxxx                # smith.langchain.com → Settings → API Keys
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=langgraph-multi-agent

# ─── INFRA (ne pas modifier) ─────────────────
POSTGRES_DB=langgraph
POSTGRES_USER=langgraph
POSTGRES_PASSWORD=ton-mot-de-passe-ici         # choisis-en un solide
REDIS_PASSWORD=ton-mot-de-passe-redis
DATABASE_URI=postgres://langgraph:ton-mot-de-passe-ici@langgraph-postgres:5432/langgraph?sslmode=disable
REDIS_URI=redis://:ton-mot-de-passe-redis@langgraph-redis:6379/0
```

2. Tester l'agent orchestrateur :
   ```bash
   cd ~/langgraph-project
   source .venv/bin/activate
   python agents/orchestrator.py
   ```

3. Lancer la stack complete :
   ```bash
   docker compose up -d
   ```

### Etape 4 — Installer le bot Discord (optionnel)

**Ou** : sur la VM Ubuntu, apres l'etape 3.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/04-install-discord.sh?token=GHSAT0AAAAAADWAJ3NHTJLXVLDJCRNX5AKM2NJX3EA)"
```

**Prerequis** : avoir cree un bot Discord sur le [portail developpeur](https://discord.com/developers/applications) avec les permissions suivantes :
- Scopes : `bot`, `applications.commands`
- Permissions : Send Messages, Read Message History, Add Reactions, Embed Links, Attach Files, Use Slash Commands
- Activer **MESSAGE CONTENT INTENT**

Ce script :
- Ajoute les variables Discord dans le `.env`
- Cree les outils MCP Discord (`discord_tools.py`) pour le human-in-the-loop
- Cree le listener Discord qui forward les commandes vers LangGraph
- Ajoute le service `discord-bot` dans le `docker-compose.yml`

**Structure Discord recommandee** :

| Channel                | Role                              |
|------------------------|-----------------------------------|
| `#orchestrateur-logs`  | Transitions de phase des agents   |
| `#human-review`        | Validations human-in-the-loop     |
| `#alerts`              | Erreurs et escalades              |
| `#commandes`           | Instructions utilisateur          |
| `#rapports`            | Resumes generes par les agents    |

### Etape 5 — Installer la couche RAG (pgvector + embeddings)

**Ou** : sur la VM Ubuntu, apres l'etape 3 (stack Docker en fonctionnement).

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/05-install-rag.sh)"
```

**Prerequis** : PostgreSQL + pgvector doit etre running/healthy (`docker compose up -d`).

Ce script :
- Ajoute les variables d'embeddings (Voyage AI) dans le `.env`
- Cree le schema `rag.documents` dans PostgreSQL avec index HNSW
- Cree les fonctions SQL `search_similar` et `upsert_document_chunks`
- Genere le service Python `agents/shared/rag_service.py` (chunking, indexation, recherche)
- Fournit des tools LangGraph (`rag_search`, `rag_index`) utilisables par tous les agents
- Installe les dependances Python (voyageai, tiktoken)

**Apres execution** :

1. Configurer votre cle Voyage AI dans le `.env` :
   ```bash
   nano ~/langgraph-project/.env
   ```
   (Obtenez une cle sur [dash.voyageai.com](https://dash.voyageai.com))

2. Rebuild l'image Docker pour inclure le RAG :
   ```bash
   docker compose up -d --build langgraph-api
   ```

## Ports exposes

| Service        | Port  | Acces              |
|----------------|-------|---------------------|
| LangGraph API  | 8123  | Reseau local (UFW)  |
| PostgreSQL     | 5432  | localhost uniquement |
| Redis          | 6379  | localhost uniquement |

## Documentation detaillee

Le fichier [scripts/Infra/langgraph-proxmox-install.md](scripts/Infra/langgraph-proxmox-install.md) contient la methodologie complete d'installation avec les phases supplementaires :
- Observabilite avec Langfuse (self-hosted)
- Securisation et reseau
- Troubleshooting

