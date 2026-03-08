# LangGraph Multi-Agent sur Proxmox

Plateforme multi-agents LangGraph auto-hebergee sur une VM ou un LXC Proxmox, avec PostgreSQL, Redis et communication Discord.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              PROXMOX VE HOST                    │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │     VM ou LXC : langgraph-agents          │  │
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

L'installation se deroule en plusieurs etapes sequentielles. Chaque script est telecharge et execute en une seule commande.

> **Base URL** : `https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/`

---

### Etape 0 — Creer un container sur Proxmox

**Ou** : sur le shell de l'hote Proxmox.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/00-create-lxc.sh)"
```

Ce script cree une VM avec la configuration suivante :

| Parametre | Valeur par defaut  |
|-----------|--------------------|
| Nom       | `langgraph-agents` |
| CPU       | 4 cores            |
| RAM       | 8 Go               |
| Disque    | 30 Go (local-lvm)  |
| Reseau    | `vmbr0`            |

Le VMID est optionnel (defaut : `200`).

**Apres execution** : installer Ubuntu 24.04 via la console VNC de Proxmox, configurer une IP statique, puis se connecter en SSH a la VM.

---


### Etape 1 — Configurer un LXC existant pour Docker

**Ou** : sur le shell de l'hote Proxmox (uniquement si vous utilisez un container LXC au lieu d'une VM).

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/00-configure-lxc.sh)" _ <ID>
```

Ce script configure un container LXC existant pour supporter Docker :
- AppArmor, nesting, cgroup permissions
- Reseau (DHCP)
- Sysctl necessaires pour Docker

**Usage** : `./00-configure-lxc.sh _ <CTID>`

> Si vous utilisez une VM, passez directement a l'etape 1.

---


### Etape 2 — Installer Docker

**Ou** : sur la VM/LXC Ubuntu fraichement installee.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/02-install-docker.sh)"
```

Ce script :
- Met a jour le systeme et installe les outils de base
- Installe Docker Engine + Docker Compose (repo officiel)
- Configure Docker pour la production (logs, overlay2, live-restore)
- Active le firewall UFW (SSH + ports 8123 et 3000 en reseau local)
- Active le `qemu-guest-agent` pour Proxmox

**Important** : se deconnecter et se reconnecter apres execution pour que le groupe `docker` soit pris en compte.

---

### Etape 3 — Installer LangGraph

**Ou** : sur la VM/LXC Ubuntu, apres reconnexion.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/03-install-langgraph.sh)"
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
   Voir la section [Configuration des cles API](#configuration-des-cles-api) ci-dessous.

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

---

### Etape 5 — Installer la couche RAG (pgvector + embeddings)

**Ou** : sur la VM/LXC Ubuntu, apres l'etape 3 (stack Docker en fonctionnement).

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

---

### Etape 6 — Mettre a jour les agents

**Ou** : sur la VM/LXC Ubuntu, apres l'etape 3 (stack Docker en fonctionnement).

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/06-install-agents.sh)"
```

Ce script met a jour les agents LangGraph depuis le depot distant. Il permet de deployer les dernieres versions des agents sans reinstaller toute la stack.

**Apres execution** : relancer les services pour prendre en compte les modifications :

```bash
cd ~/langgraph-project
docker compose up -d --build langgraph-api
```

---

### Etape 13 — Fix thread persistence

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/13-fix-thread-persistence.sh)"
```

Corrige le probleme ou chaque message Discord creait un nouveau `thread_id`, faisant perdre le contexte a l'Orchestrateur entre les messages. Apres ce fix, le `thread_id` est base sur le channel Discord (un projet = un channel ou un thread Discord).

---

### Etape 14 — Installer MCP (Model Context Protocol)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/14-install-mcp.sh)"
```

Installation interactive de serveurs MCP pour les agents :
1. Choisir un agent dans la liste
2. Chercher un serveur MCP dans le registry
3. Configurer les variables d'environnement (reutiliser ou creer un nouveau parametrage)
4. Sauvegarder le mapping agent <-> MCP <-> parametrage

Fichiers generes :
- `config/mcp_servers.json` — serveurs MCP installes (avec parametrages)
- `config/agent_mcp_access.json` — mapping agent -> [mcp_ids]
- `agents/shared/mcp_client.py` — client Python qui lit les configs

---

## Configuration des cles API

### ANTHROPIC_API_KEY (obligatoire — seul cout recurrent)
```
1. Aller sur https://console.anthropic.com
2. Creer un compte (ou se connecter)
3. Menu gauche -> API Keys -> Create Key -> nommer "langgraph-agents"
4. Copier la cle (commence par `sk-ant-api03-...`)
5. Onglet Plans & Billing -> ajouter une carte et mettre un spending limit (ex: 10 EUR/mois pour commencer)
```

### VOYAGE_API_KEY (pour le RAG — quasi gratuit)
```
1. Aller sur https://dash.voyageai.com
2. Creer un compte (gratuit — 50M tokens/mois offerts)
3. Menu API Keys -> Create new API key
4. Copier la cle (commence par `pa-...`)
```


> Alternative 0 EUR : ne pas mettre de cle Voyage et utiliser Ollama en local (voir `EMBEDDING_MODEL=local` dans le script RAG). Necessite un GPU ou accepter des temps plus longs.


### DISCORD_BOT_TOKEN (gratuit)
```
1. Aller sur https://discord.com/developers/applications
2. New Application -> nommer "LangGraph Agent" -> Create
3. Menu gauche -> Bot -> Reset Token -> copier le token
4. Desactiver Public Bot
5. Activer les 3 Privileged Gateway Intents :
   - PRESENCE INTENT
   - SERVER MEMBERS INTENT
   - MESSAGE CONTENT INTENT
6. Menu gauche -> OAuth2 -> URL Generator :
   - Scopes : `bot` + `applications.commands`
   - Bot Permissions : Send Messages, Read Message History, Add Reactions, Embed Links, Attach Files, Use Slash Commands
7. Copier l'URL generee -> ouvrir dans le navigateur -> choisir votre serveur Discord -> Autoriser

**Channel IDs Discord** : Dans Discord -> Parametres utilisateur -> Avances -> activer Mode developpeur. Clic droit sur chaque channel -> Copier l'identifiant du salon.
```

### LANGSMITH_API_KEY (optionnel — gratuit)
```
1. Aller sur https://smith.langchain.com
2. Creer un compte (gratuit — 100K traces/mois)
3. Settings -> API Keys -> Create API Key
4. Copier la cle (commence par `lsv2_pt_...`)
```

### Recapitulatif du .env

```bash
# --- OBLIGATOIRE ---
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx          # console.anthropic.com
LANGGRAPH_API_KEY=lsv2_...                    # Cle API LangGraph (si applicable)

# --- RAG ---
VOYAGE_API_KEY=pa-xxxxx                        # dash.voyageai.com

# --- DISCORD (optionnel) ---
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.xxxxx          # discord.com/developers
DISCORD_CHANNEL_REVIEW=1234567890123456789
DISCORD_CHANNEL_LOGS=1234567890123456789
DISCORD_CHANNEL_COMMANDS=1234567890123456789
DISCORD_GUILD_ID=1234567890123456789

# --- OBSERVABILITE (optionnel) ---
LANGSMITH_API_KEY=lsv2_pt_xxxxx                # smith.langchain.com
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=langgraph-multi-agent

# --- INFRA (ne pas modifier) ---
POSTGRES_DB=langgraph
POSTGRES_USER=langgraph
POSTGRES_PASSWORD=ton-mot-de-passe-ici
REDIS_PASSWORD=ton-mot-de-passe-redis
DATABASE_URI=postgres://langgraph:ton-mot-de-passe-ici@langgraph-postgres:5432/langgraph?sslmode=disable
REDIS_URI=redis://:ton-mot-de-passe-redis@langgraph-redis:6379/0
```

### Structure Discord recommandee

| Channel                | Role                              |
|------------------------|-----------------------------------|
| `#orchestrateur-logs`  | Transitions de phase des agents   |
| `#human-review`        | Validations human-in-the-loop     |
| `#alerts`              | Erreurs et escalades              |
| `#commandes`           | Instructions utilisateur          |
| `#rapports`            | Resumes generes par les agents    |

### Etape 15 — Installer le panneau d'administration web

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/15-install-admin.sh)"
```

Ce script installe une interface web d'administration accessible sur le port **8080** :

- **Secrets (.env)** — Ajouter, modifier, supprimer des variables d'environnement (valeurs masquees)
- **Services MCP** — Catalogue de 20+ serveurs, installation en un clic, activation/desactivation par agent
- **Agents** — CRUD complet, edition du prompt, choix du modele LLM, gestion des acces MCP
- **Scripts** — Boutons start / stop / restart / build avec sortie terminal
- **Git** — Status, historique, pull pour mise a jour, commit des configs

Fichiers deployes :

```
~/langgraph-project/
  Dockerfile.admin
  web/
    server.py
    requirements.txt
    static/
      index.html
      css/style.css
      js/app.js
```

**Apres execution** : acceder a `http://<IP-VM>:8080`

> **Securite** : le port 8080 est expose sans authentification. Pensez a restreindre l'acces via le firewall UFW (`ufw allow from 192.168.1.0/24 to any port 8080`) ou un reverse proxy avec authentification.

---

## Ports exposes

| Service        | Port  | Acces              |
|----------------|-------|---------------------|
| LangGraph API  | 8123  | Reseau local (UFW)  |
| Admin Web      | 8080  | Reseau local (UFW)  |
| PostgreSQL     | 5432  | localhost uniquement |
| Redis          | 6379  | localhost uniquement |


## Install agents
```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/06-install-agents.sh)"
```



## Install services mcp

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/14-install-mcp.sh)"
```


Le flow :
```
🔍 Recherche : github

  3 resultats pour 'github' :
  ────────────────────────────────────────

  1) io.github.modelcontextprotocol/server-github
     Tools to read, search, and manipulate GitHub repositories, issues, PRs...

  2) io.github.someone/github-actions
     Run GitHub Actions workflows...

  3) ...

  Choix : 1

  ═══════════════════════════════════════
  io.github.modelcontextprotocol/server-github
  ═══════════════════════════════════════
  Packages : npm : @modelcontextprotocol/server-github (stdio)
  Variables : GITHUB_PERSONAL_ACCESS_TOKEN

  i) Installer    0) Retour    q) Quitter

  Choix : i

  ✅ server-github installe.
  -> GITHUB_PERSONAL_ACCESS_TOKEN ajoute au .env (a remplir !)

🔍 Recherche : postgres
  ...
```

## mode ReAct

(appel de tools MCP). Les agents sont configurés pour accéder aux MCP, mais le code qui leur permet d'appeler les tools n'est pas encore en place. 

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/15-activate-mcp-tools.sh)"
```

**Ce que ça fait :**

1. **BaseAgent** gagne `_call_llm_with_tools()` — une boucle ReAct où le LLM peut appeler des MCP tools, lire le résultat, et re-appeler (max 20 itérations)
2. **Activation dynamique** — le script lit `config/agent_mcp_access.json` et ajoute `use_tools = True` uniquement sur les agents qui ont des MCP configurés via le script 14
3. **Fallback gracieux** — si un agent a `use_tools = True` mais qu'aucun tool n'est disponible (clé manquante, serveur MCP en panne), il fonctionne comme avant sans tools

Exemple de ce qui se passe quand le Lead Dev reçoit la tâche "crée un repo" avec GitHub MCP :

```
[lead_dev] Start — pipeline=0, tools=True
[lead_dev] 3 MCP tools loaded
[lead_dev] Tool: create_repository({"name":"PerformanceTracker",...})
[lead_dev] Tool: create_or_update_file({"path":"README.md",...})
[lead_dev] ReAct done — 3 iterations
```


## Documentation detaillee

Le fichier [scripts/Infra/langgraph-proxmox-install.md](scripts/Infra/langgraph-proxmox-install.md) contient la methodologie complete d'installation avec les phases supplementaires :
- Observabilite avec Langfuse (self-hosted)
- Securisation et reseau
- Troubleshooting
