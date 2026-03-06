# Méthodologie d'Installation — LangGraph Multi-Agent sur Proxmox

> **Version** : 1.1 — Mars 2026  
> **Cible** : Serveur Proxmox VE 8.x / 9.x  
> **Architecture** : LangGraph Self-Hosted (Standalone Container) + Discord MCP  
> **Auteur** : Généré par Claude — à adapter à votre repo `Configurations/Proxmox`

---

## Table des matières

1. [Vue d'ensemble de l'architecture](#1-vue-densemble)
2. [Prérequis matériels et logiciels](#2-prérequis)
3. [Phase 1 — Création de la VM sur Proxmox](#3-phase-1)
4. [Phase 2 — Socle système (Docker + dépendances)](#4-phase-2)
5. [Phase 3 — Infrastructure de données (PostgreSQL + Redis)](#5-phase-3)
6. [Phase 4 — Installation de LangGraph](#6-phase-4)
7. [Phase 5 — Premier agent (Hello World)](#7-phase-5)
8. [Phase 6 — Observabilité (Langfuse self-hosted)](#8-phase-6)
9. [Phase 7 — Discord MCP (communication agents ↔ humain)](#9-phase-7-discord)
10. [Phase 8 — Couche RAG (pgvector + embeddings)](#10-phase-8-rag)
11. [Phase 9 — Sécurisation et réseau](#11-phase-9)
12. [Phase 10 — Intégration dans votre repo Proxmox](#12-phase-10)
13. [Arborescence finale](#13-arborescence)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                    PROXMOX VE HOST                          │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              VM: langgraph-agents                      │ │
│  │              Ubuntu 24.04 LTS / Debian 12              │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │              Docker Compose Stack                 │  │ │
│  │  │                                                  │  │ │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │ │
│  │  │  │ Postgres │  │  Redis   │  │  LangGraph   │  │  │ │
│  │  │  │   16     │  │   7.x    │  │    API       │  │  │ │
│  │  │  │ +pgvector│  │          │  │  (agents)    │  │  │ │
│  │  │  └──────────┘  └──────────┘  └──────┬───────┘  │  │ │
│  │  │                                      │          │  │ │
│  │  │  ┌──────────────┐  ┌────────────────┐│          │  │ │
│  │  │  │   Langfuse   │  │  Discord MCP  ││          │  │ │
│  │  │  │ (observabil.)│  │  Server + Bot ├┘          │  │ │
│  │  │  └──────────────┘  └───────┬────────┘          │  │ │
│  │  └────────────────────────────│────────────────────┘  │ │
│  └───────────────────────────────│────────────────────────┘ │
└──────────────────────────────────│──────────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │   Discord API   │
                          │  (cloud, 0€)    │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
               #human-review  #agent-logs  #commandes
                    │              │              │
                    └──────────────┴──────────────┘
                           Votre serveur Discord
```

**Pourquoi une VM et pas un LXC ?**  
LangGraph tourne dans Docker, qui nécessite un runtime complet. Bien qu'il soit possible de faire tourner Docker dans un LXC privilégié, une VM offre une isolation plus propre, un support complet de `cgroups v2`, et évite les problèmes de `nesting`. Pour un workload de production multi-agents, la VM est le choix recommandé.

---

## 2. Prérequis

### Matériel (VM)

| Ressource   | Minimum      | Recommandé        | Notes                                    |
|-------------|-------------|--------------------|-----------------------------------------|
| vCPU        | 4           | 8                  | LangGraph API + Postgres + Redis        |
| RAM         | 8 Go        | 16 Go             | Les agents consomment de la RAM via les contextes LLM |
| Disque      | 40 Go       | 100 Go SSD/NVMe   | Postgres + logs + artifacts             |
| Réseau      | vmbr0       | vmbr0 + VLAN dédié | Isoler le trafic agents si multi-tenant |

### Logiciel

| Composant        | Version       | Rôle                                  |
|------------------|---------------|---------------------------------------|
| Proxmox VE       | 8.x / 9.x    | Hyperviseur                          |
| Ubuntu Server    | 24.04 LTS     | OS de la VM (alternative : Debian 12)|
| Docker Engine    | 27.x+        | Runtime des containers               |
| Docker Compose   | v2.x         | Orchestration des services            |
| Python           | 3.11+        | LangGraph + agents                   |
| Git              | 2.x          | Versioning des configs et prompts    |

### Comptes et clés API

- **Anthropic API Key** — pour Claude Sonnet/Opus (les LLMs des agents)
- **LangSmith API Key** (optionnel) — pour le tracing managé (gratuit jusqu'à 100K nodes/mois)
- **GitHub Personal Access Token** — si MCP GitHub est utilisé
- **Discord Bot Token** — pour la communication agents ↔ humain (gratuit, voir Phase 7)

---

## 3. Phase 1 — Création de la VM sur Proxmox

### 3.1 Via l'interface web Proxmox

1. Télécharger l'ISO Ubuntu 24.04 LTS dans le stockage local de Proxmox
2. Créer la VM avec les paramètres suivants :

```
VM ID       : 200 (ou selon votre convention)
Name        : langgraph-agents
OS Type     : Linux 6.x - 2.6 Kernel
Machine     : q35
BIOS        : OVMF (UEFI)
CPU         : host (8 cores)
RAM         : 16384 MB
Disk        : 100 GB (virtio-scsi, SSD/NVMe storage)
Network     : vmbr0, model virtio
```

### 3.2 Via CLI (pour votre repo d'automatisation)

```bash
# Créer la VM depuis le shell Proxmox
qm create 200 \
  --name langgraph-agents \
  --cores 8 \
  --memory 16384 \
  --machine q35 \
  --bios ovmf \
  --efidisk0 local-lvm:1,efitype=4m,pre-enrolled-keys=1 \
  --scsi0 local-lvm:100,iothread=1,discard=on,ssd=1 \
  --scsihw virtio-scsi-single \
  --net0 virtio,bridge=vmbr0 \
  --ide2 local:iso/ubuntu-24.04-live-server-amd64.iso,media=cdrom \
  --boot order=scsi0;ide2 \
  --ostype l26 \
  --cpu host \
  --numa 1 \
  --agent enabled=1

# Démarrer la VM
qm start 200
```

### 3.3 Post-installation Ubuntu

Après l'installation de base d'Ubuntu :

```bash
# Mettre à jour le système
sudo apt update && sudo apt upgrade -y

# Installer les outils de base
sudo apt install -y \
  curl wget git vim htop tmux \
  ca-certificates gnupg lsb-release \
  ufw fail2ban qemu-guest-agent \
  python3 python3-pip python3-venv

# Activer le guest agent pour Proxmox
sudo systemctl enable --now qemu-guest-agent

# Configurer le hostname
sudo hostnamectl set-hostname langgraph-agents

# Configurer une IP statique (adapter à votre réseau)
# /etc/netplan/00-installer-config.yaml
```

---

## 4. Phase 2 — Socle Docker

### 4.1 Installer Docker Engine

```bash
# Ajouter le repo Docker officiel
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER

# Vérifier
docker --version
docker compose version
```

### 4.2 Configurer Docker pour la production

```bash
# /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {"base": "172.20.0.0/16", "size": 24}
  ],
  "storage-driver": "overlay2",
  "live-restore": true
}
EOF

sudo systemctl restart docker
```

---

## 5. Phase 3 — Infrastructure de données

### 5.1 Structure du projet

```bash
# Créer l'arborescence du projet
mkdir -p ~/langgraph-project/{agents,config,data,scripts}
cd ~/langgraph-project
```

### 5.2 Fichier d'environnement

```bash
# ~/langgraph-project/.env
cat > .env << 'EOF'
# ─── LLM ──────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-VOTRE-CLE-ICI

# ─── LangSmith (optionnel, pour le tracing) ─
LANGSMITH_API_KEY=lsv2-VOTRE-CLE-ICI
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=langgraph-multi-agent

# ─── PostgreSQL ────────────────────────────
POSTGRES_DB=langgraph
POSTGRES_USER=langgraph
POSTGRES_PASSWORD=CHANGEZ-MOI-EN-PROD

# ─── Redis ─────────────────────────────────
REDIS_PASSWORD=CHANGEZ-MOI-AUSSI

# ─── LangGraph ─────────────────────────────
DATABASE_URI=postgres://langgraph:CHANGEZ-MOI-EN-PROD@langgraph-postgres:5432/langgraph?sslmode=disable
REDIS_URI=redis://:CHANGEZ-MOI-AUSSI@langgraph-redis:6379/0

# ─── Discord MCP ───────────────────────────
DISCORD_BOT_TOKEN=VOTRE-TOKEN-BOT-DISCORD
DISCORD_CHANNEL_REVIEW=ID-DU-CHANNEL-HUMAN-REVIEW
DISCORD_CHANNEL_LOGS=ID-DU-CHANNEL-AGENT-LOGS
DISCORD_CHANNEL_COMMANDS=ID-DU-CHANNEL-COMMANDES
DISCORD_GUILD_ID=ID-DE-VOTRE-SERVEUR
EOF

chmod 600 .env
```

### 5.3 Docker Compose — Services de base

```bash
# ~/langgraph-project/docker-compose.infra.yml
cat > docker-compose.infra.yml << 'YAML'
version: "3.9"

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local

networks:
  langgraph-net:
    driver: bridge

services:
  # ── PostgreSQL 16 + pgvector ───────────────
  langgraph-postgres:
    image: pgvector/pgvector:pg16
    container_name: langgraph-postgres
    restart: unless-stopped
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./config/init.sql:/docker-entrypoint-initdb.d/init.sql
    command:
      - postgres
      - -c
      - shared_preload_libraries=vector
      - -c
      - max_connections=200
      - -c
      - shared_buffers=256MB
      - -c
      - effective_cache_size=1GB
      - -c
      - work_mem=16MB
    healthcheck:
      test: pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
    networks:
      - langgraph-net

  # ── Redis 7 ────────────────────────────────
  langgraph-redis:
    image: redis:7-alpine
    container_name: langgraph-redis
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: redis-cli -a ${REDIS_PASSWORD} ping
      interval: 5s
      timeout: 2s
      retries: 5
    networks:
      - langgraph-net
YAML
```

### 5.4 Script d'initialisation PostgreSQL

```bash
# ~/langgraph-project/config/init.sql
cat > config/init.sql << 'SQL'
-- Extensions pour LangGraph + RAG
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schema pour les artefacts projet
CREATE SCHEMA IF NOT EXISTS project;

-- Table de métadonnées des agents
CREATE TABLE IF NOT EXISTS project.agent_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    system_prompt_version VARCHAR(50),
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table des artefacts produits par les agents
CREATE TABLE IF NOT EXISTS project.artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES project.agent_registry(id),
    artifact_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    phase VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour les recherches fréquentes
CREATE INDEX IF NOT EXISTS idx_artifacts_agent ON project.artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_phase ON project.artifacts(phase);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON project.artifacts(artifact_type);
SQL
```

### 5.5 Lancer l'infrastructure

```bash
cd ~/langgraph-project

# Démarrer Postgres + Redis
docker compose -f docker-compose.infra.yml up -d

# Vérifier que tout est healthy
docker compose -f docker-compose.infra.yml ps

# Tester la connexion Postgres
docker exec -it langgraph-postgres psql -U langgraph -d langgraph -c "SELECT 1;"

# Tester Redis
docker exec -it langgraph-redis redis-cli -a $(grep REDIS_PASSWORD .env | cut -d= -f2) ping
```

---

## 6. Phase 4 — Installation de LangGraph

### 6.1 Environnement Python

```bash
# Créer un venv dédié
cd ~/langgraph-project
python3 -m venv .venv
source .venv/bin/activate

# Installer LangGraph + dépendances
pip install --upgrade pip

pip install \
  langgraph \
  langgraph-checkpoint-postgres \
  langchain-anthropic \
  langchain-core \
  langsmith \
  anthropic \
  pydantic \
  psycopg[binary] \
  psycopg-pool \
  redis \
  python-dotenv \
  fastapi \
  uvicorn
```

### 6.2 Configuration LangGraph

```bash
# ~/langgraph-project/langgraph.json
cat > langgraph.json << 'JSON'
{
  "dependencies": ["."],
  "graphs": {
    "orchestrator": "./agents/orchestrator.py:graph"
  },
  "env": ".env"
}
JSON
```

### 6.3 Option A — Exécution directe (développement)

```bash
source .venv/bin/activate

# Lancer le graphe en mode dev
cd ~/langgraph-project
python agents/orchestrator.py
```

### 6.4 Option B — Container Docker (production)

```bash
# ~/langgraph-project/Dockerfile
cat > Dockerfile << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code des agents
COPY agents/ ./agents/
COPY config/ ./config/
COPY langgraph.json .

# Healthcheck
COPY scripts/healthcheck.py /healthcheck.py

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agents.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE

# requirements.txt
cat > requirements.txt << 'TXT'
langgraph>=0.3.0
langgraph-checkpoint-postgres>=2.0.0
langchain-anthropic>=0.3.0
langchain-core>=0.3.0
langsmith>=0.2.0
anthropic>=0.40.0
pydantic>=2.0
psycopg[binary]>=3.2.0
psycopg-pool>=3.2.0
redis>=5.0.0
python-dotenv>=1.0.0
fastapi>=0.115.0
uvicorn>=0.32.0
discord.py>=2.4.0
aiohttp>=3.10.0
TXT
```

### 6.5 Docker Compose — Stack complète

```bash
# ~/langgraph-project/docker-compose.yml
cat > docker-compose.yml << 'YAML'
version: "3.9"

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local

networks:
  langgraph-net:
    driver: bridge

services:
  # ── PostgreSQL 16 + pgvector ───────────────
  langgraph-postgres:
    image: pgvector/pgvector:pg16
    container_name: langgraph-postgres
    restart: unless-stopped
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./config/init.sql:/docker-entrypoint-initdb.d/init.sql
    command:
      - postgres
      - -c
      - shared_preload_libraries=vector
      - -c
      - max_connections=200
    healthcheck:
      test: pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
    networks:
      - langgraph-net

  # ── Redis 7 ────────────────────────────────
  langgraph-redis:
    image: redis:7-alpine
    container_name: langgraph-redis
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: redis-cli -a ${REDIS_PASSWORD} ping
      interval: 5s
      timeout: 2s
      retries: 5
    networks:
      - langgraph-net

  # ── LangGraph Agent Server ─────────────────
  langgraph-api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: langgraph-api
    restart: unless-stopped
    ports:
      - "127.0.0.1:8123:8000"
    depends_on:
      langgraph-postgres:
        condition: service_healthy
      langgraph-redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URI: ${DATABASE_URI}
      REDIS_URI: ${REDIS_URI}
    volumes:
      - ./agents:/app/agents
      - ./config:/app/config
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - langgraph-net
YAML
```

---

## 7. Phase 5 — Premier agent (validation)

### 7.1 Agent minimal de test

```bash
# ~/langgraph-project/agents/orchestrator.py
cat > agents/orchestrator.py << 'PYTHON'
"""
Orchestrateur minimal — valide que LangGraph + Anthropic + Postgres fonctionnent.
"""
import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_anthropic import ChatAnthropic
from psycopg_pool import ConnectionPool

load_dotenv()

# ── State ────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    phase: str

# ── LLM ──────────────────────────────────────
llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",
    max_tokens=2000,
    temperature=0.3,
)

# ── Nodes ────────────────────────────────────
def orchestrator(state: AgentState) -> dict:
    """Le noeud orchestrateur analyse et répond."""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    """Décide si on continue ou on s'arrête."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

# ── Graph ────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("orchestrator", orchestrator)
workflow.set_entry_point("orchestrator")
workflow.add_conditional_edges(
    "orchestrator",
    should_continue,
    {"continue": "orchestrator", "end": END},
)

# ── Compile avec checkpoint Postgres ─────────
DB_URI = os.getenv("DATABASE_URI")

def get_graph():
    """Factory pour obtenir le graphe compilé."""
    pool = ConnectionPool(conninfo=DB_URI)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return workflow.compile(checkpointer=checkpointer)

# ── Test direct ──────────────────────────────
if __name__ == "__main__":
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-001"}}

    result = graph.invoke(
        {
            "messages": [("user", "Dis-moi bonjour et confirme que tu es opérationnel.")],
            "phase": "test",
        },
        config,
    )

    print("\n✅ Réponse de l'agent :")
    print(result["messages"][-1].content)
    print("\n✅ LangGraph est opérationnel sur Proxmox !")
PYTHON
```

### 7.2 Exécuter le test

```bash
cd ~/langgraph-project
source .venv/bin/activate

# S'assurer que l'infra tourne
docker compose -f docker-compose.infra.yml up -d

# Exécuter l'agent de test
python agents/orchestrator.py
```

**Résultat attendu :**
```
✅ Réponse de l'agent :
Bonjour ! Je suis opérationnel et prêt à travailler. [...]

✅ LangGraph est opérationnel sur Proxmox !
```

---

## 8. Phase 6 — Observabilité (Langfuse self-hosted)

Alternative open-source à LangSmith, entièrement self-hosted.

### 8.1 Docker Compose Langfuse

```bash
# ~/langgraph-project/docker-compose.observability.yml
cat > docker-compose.observability.yml << 'YAML'
version: "3.9"

services:
  langfuse-web:
    image: langfuse/langfuse:latest
    container_name: langfuse-web
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@langgraph-postgres:5432/langfuse
      NEXTAUTH_SECRET: CHANGEZ-CE-SECRET-DE-32-CHARS-MIN
      NEXTAUTH_URL: http://localhost:3000
      SALT: CHANGEZ-CE-SALT-AUSSI
    depends_on:
      langgraph-postgres:
        condition: service_healthy
    networks:
      - langgraph-net

networks:
  langgraph-net:
    external: true
    name: langgraph-project_langgraph-net
YAML
```

### 8.2 Intégrer Langfuse dans les agents

```python
# Dans agents/orchestrator.py, ajouter :
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler(
    public_key="pk-...",      # Depuis l'UI Langfuse
    secret_key="sk-...",
    host="http://localhost:3000",
)

# Passer le callback au graphe
result = graph.invoke(input_data, config={"callbacks": [langfuse_handler]})
```

---

## 9. Phase 7 — Discord MCP (communication agents ↔ humain)

Discord sert d'interface entre vous et vos agents : notifications, validations human-in-the-loop, commandes en langage naturel, et logs en temps réel. **Coût : 0€.**

### 9.1 Créer le bot Discord

1. Aller sur https://discord.com/developers/applications
2. Cliquer **New Application** → nommer `LangGraph Agent`
3. Onglet **Bot** → cliquer **Reset Token** → copier le token dans `.env`
4. Désactiver **Public Bot** (seul vous pouvez l'ajouter)
5. Activer les **Privileged Gateway Intents** :
   - `MESSAGE CONTENT INTENT` ✅
   - `SERVER MEMBERS INTENT` ✅
   - `PRESENCE INTENT` ✅
6. Onglet **OAuth2** → **URL Generator** :
   - Scopes : `bot`, `applications.commands`
   - Bot Permissions : `Send Messages`, `Read Message History`, `Manage Threads`, `Add Reactions`, `Embed Links`, `Attach Files`, `Use Slash Commands`
7. Copier l'URL générée → ouvrir dans le navigateur → ajouter à votre serveur

### 9.2 Structurer le serveur Discord

Créez cette structure de channels sur votre serveur :

```
📁 🤖 AGENTS LANGGRAPH
   #orchestrateur-logs      → Transitions de phase, décisions de routing
   #human-review             → Demandes de validation (l'agent attend votre réponse)
   #alerts                   → Erreurs, escalades, seuils de confiance bas

📁 📊 PROJET
   #requirements             → PRDs et user stories pour review
   #architecture             → ADRs et diagrammes
   #deployments              → Statuts CI/CD et déploiements

📁 💬 CONTRÔLE
   #commandes                → Vous envoyez des instructions aux agents
   #rapports                 → Résumés quotidiens / hebdomadaires
```

### 9.3 Installer le Discord MCP Server

**Option A — MCP Agent Communication (recommandé pour le human-in-the-loop)**

```bash
# Installer globalement
npm install -g mcp-discord-agent-comm

# Ou utiliser directement via npx (pas d'installation)
npx mcp-discord-agent-comm
```

Ce serveur MCP expose deux capacités essentielles :
- `send_message` — l'agent envoie un message (notification, log, rapport)
- `send_message` avec `expect_reply: true` — l'agent envoie et **attend votre réponse** (human gate)

**Option B — Discord MCP complet (management avancé du serveur)**

```bash
# Pour un contrôle total (120+ outils Discord API)
npm install -g @ncodelife/discord-mcp-server

# Lancer avec le token
npx @ncodelife/discord-mcp-server@latest --token $DISCORD_BOT_TOKEN
```

### 9.4 Intégrer Discord dans les agents LangGraph

```bash
# ~/langgraph-project/agents/shared/discord_tools.py
cat > agents/shared/discord_tools.py << 'PYTHON'
"""
Discord MCP tools pour la communication agents ↔ humain.
Utilisé par tous les agents pour les notifications et le human-in-the-loop.
"""
import os
import asyncio
import discord
from discord import Intents, Client
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_REVIEW = int(os.getenv("DISCORD_CHANNEL_REVIEW", "0"))
CHANNEL_LOGS = int(os.getenv("DISCORD_CHANNEL_LOGS", "0"))
CHANNEL_ALERTS = int(os.getenv("DISCORD_CHANNEL_ALERTS", "0"))

# ── Client Discord (singleton) ──────────────
intents = Intents.default()
intents.message_content = True
client = Client(intents=intents)

_client_ready = asyncio.Event()

@client.event
async def on_ready():
    print(f"🤖 Discord bot connecté : {client.user}")
    _client_ready.set()


# ── Fonctions utilitaires ────────────────────

async def send_notification(channel_id: int, message: str, embed: dict = None):
    """Envoie une notification sans attendre de réponse."""
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    if embed:
        discord_embed = discord.Embed(
            title=embed.get("title", ""),
            description=embed.get("description", ""),
            color=embed.get("color", 0x6366F1),
        )
        for field in embed.get("fields", []):
            discord_embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False),
            )
        await channel.send(content=message, embed=discord_embed)
    else:
        await channel.send(content=message)


async def request_human_approval(
    channel_id: int,
    agent_name: str,
    question: str,
    context: str = "",
    timeout: int = 300,
) -> dict:
    """
    Envoie une demande de validation et attend la réponse humaine.
    Retourne: {"approved": bool, "response": str, "timed_out": bool}
    """
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    # Construire le message de demande
    embed = discord.Embed(
        title=f"🚦 Validation requise — {agent_name}",
        description=question,
        color=0xF59E0B,  # Orange/amber
    )
    if context:
        embed.add_field(name="Contexte", value=context[:1024], inline=False)
    embed.add_field(
        name="Actions",
        value="Répondre `approve` ✅ ou `revise` 🔄 (+ commentaire optionnel)",
        inline=False,
    )
    embed.set_footer(text=f"⏳ Timeout: {timeout}s — sans réponse = escalade")

    msg = await channel.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("🔄")

    # Attendre la réponse
    def check(m):
        return (
            m.channel.id == channel_id
            and not m.author.bot
            and m.reference is not None
            and m.reference.message_id == msg.id
        ) or (
            m.channel.id == channel_id
            and not m.author.bot
            and m.content.lower().startswith(("approve", "revise"))
        )

    try:
        reply = await client.wait_for("message", check=check, timeout=timeout)
        content = reply.content.lower().strip()
        approved = content.startswith("approve") or content == "ok" or content == "yes"
        return {
            "approved": approved,
            "response": reply.content,
            "timed_out": False,
            "reviewer": str(reply.author),
        }
    except asyncio.TimeoutError:
        await channel.send(f"⏰ **Timeout** — pas de réponse pour `{agent_name}`. Escalade automatique.")
        return {
            "approved": False,
            "response": "",
            "timed_out": True,
            "reviewer": None,
        }


async def send_alert(message: str, severity: str = "warning"):
    """Envoie une alerte dans le channel #alerts."""
    colors = {"info": 0x6366F1, "warning": 0xF59E0B, "error": 0xF43F5E, "critical": 0xFF0000}
    icons = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}

    embed = discord.Embed(
        title=f"{icons.get(severity, '⚠️')} Alerte — {severity.upper()}",
        description=message,
        color=colors.get(severity, 0xF59E0B),
    )
    await send_notification(CHANNEL_ALERTS, "", embed=embed)


async def send_phase_transition(from_phase: str, to_phase: str, details: str = ""):
    """Log une transition de phase dans #orchestrateur-logs."""
    embed = discord.Embed(
        title="🔄 Transition de phase",
        description=f"**{from_phase}** → **{to_phase}**",
        color=0x10B981,
    )
    if details:
        embed.add_field(name="Détails", value=details[:1024], inline=False)
    await send_notification(CHANNEL_LOGS, "", embed=embed)


# ── Intégration LangGraph ────────────────────

def create_discord_tools_for_langgraph():
    """
    Retourne des tools LangChain utilisables dans les agents LangGraph.
    """
    from langchain_core.tools import tool

    @tool
    def notify_discord(channel: str, message: str) -> str:
        """Envoie une notification Discord. channel: 'logs' | 'review' | 'alerts'"""
        channel_map = {
            "logs": CHANNEL_LOGS,
            "review": CHANNEL_REVIEW,
            "alerts": CHANNEL_ALERTS,
        }
        channel_id = channel_map.get(channel, CHANNEL_LOGS)
        asyncio.run_coroutine_threadsafe(
            send_notification(channel_id, message), client.loop
        )
        return f"Message envoyé dans #{channel}"

    @tool
    def request_approval(question: str, context: str = "") -> dict:
        """Demande une validation humaine via Discord. Bloque jusqu'à réponse."""
        future = asyncio.run_coroutine_threadsafe(
            request_human_approval(
                CHANNEL_REVIEW,
                agent_name="Agent",
                question=question,
                context=context,
            ),
            client.loop,
        )
        return future.result(timeout=600)

    return [notify_discord, request_approval]


# ── Démarrage du bot (dans un thread séparé) ─
import threading

def start_discord_bot():
    """Lance le bot Discord dans un thread background."""
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(client.start(BOT_TOKEN))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return client
PYTHON
```

### 9.5 Utiliser Discord dans le human gate de l'orchestrateur

```python
# Modifier agents/orchestrator.py — ajouter le human gate Discord

from agents.shared.discord_tools import (
    start_discord_bot,
    request_human_approval,
    send_phase_transition,
    send_alert,
    CHANNEL_REVIEW,
)

# Démarrer le bot au lancement
discord_client = start_discord_bot()

async def human_gate_node(state: ProjectState) -> dict:
    """
    Checkpoint humain via Discord.
    L'agent poste dans #human-review et attend 'approve' ou 'revise'.
    """
    phase = state.get("phase", "unknown")
    
    # Notifier la transition
    await send_phase_transition(
        from_phase=phase,
        to_phase="human_review",
        details=f"En attente de validation pour la phase: {phase}"
    )
    
    # Escalade si confiance basse
    if state.get("confidence", 1.0) < 0.7:
        await send_alert(
            f"Confiance basse ({state['confidence']:.0%}) sur la phase `{phase}`. "
            f"Review manuelle recommandée.",
            severity="warning"
        )
    
    # Demander la validation
    result = await request_human_approval(
        channel_id=CHANNEL_REVIEW,
        agent_name="Orchestrateur",
        question=f"La phase **{phase}** est terminée. Valider pour passer à la suite ?",
        context=f"Confiance: {state.get('confidence', 1.0):.0%}",
        timeout=600,  # 10 minutes
    )
    
    if result["timed_out"]:
        return {"human_feedback": "timeout", "phase": phase}
    elif result["approved"]:
        return {"human_feedback": "approve"}
    else:
        return {"human_feedback": "revise"}
```

### 9.6 Docker Compose — Ajouter le bot Discord

Ajouter ce service dans `docker-compose.yml` :

```yaml
  # ── Discord Bot (MCP Agent Communication) ───
  discord-bot:
    build:
      context: .
      dockerfile: Dockerfile.discord
    container_name: langgraph-discord
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      langgraph-api:
        condition: service_healthy
    networks:
      - langgraph-net
```

```bash
# ~/langgraph-project/Dockerfile.discord
cat > Dockerfile.discord << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    discord.py>=2.4.0 \
    python-dotenv>=1.0.0 \
    langchain-core>=0.3.0

COPY agents/shared/discord_tools.py ./agents/shared/discord_tools.py
COPY agents/discord_listener.py ./agents/discord_listener.py

CMD ["python", "agents/discord_listener.py"]
DOCKERFILE
```

### 9.7 Listener Discord — recevoir des commandes

```bash
# ~/langgraph-project/agents/discord_listener.py
cat > agents/discord_listener.py << 'PYTHON'
"""
Discord Listener — reçoit les commandes utilisateur depuis Discord
et les forward vers le graphe LangGraph.
"""
import os
import asyncio
import discord
from discord import Intents
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_COMMANDS = int(os.getenv("DISCORD_CHANNEL_COMMANDS", "0"))
CHANNEL_LOGS = int(os.getenv("DISCORD_CHANNEL_LOGS", "0"))

intents = Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"🤖 Discord listener connecté : {client.user}")
    channel = client.get_channel(CHANNEL_LOGS)
    if channel:
        embed = discord.Embed(
            title="🟢 Système en ligne",
            description="LangGraph Multi-Agent est opérationnel.",
            color=0x10B981,
        )
        embed.add_field(name="Agents", value="8 agents disponibles", inline=True)
        embed.add_field(name="Status", value="Ready", inline=True)
        await channel.send(embed=embed)


@client.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author.bot:
        return

    # Réagir uniquement dans #commandes
    if message.channel.id != CHANNEL_COMMANDS:
        return

    content = message.content.strip()
    if not content:
        return

    # Accusé de réception
    await message.add_reaction("⏳")

    try:
        # Ici, forward vers l'API LangGraph
        # Option 1 : appel HTTP vers FastAPI gateway
        # Option 2 : invocation directe du graphe
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://langgraph-api:8000/invoke",
                json={
                    "messages": [{"role": "user", "content": content}],
                    "thread_id": f"discord-{message.author.id}",
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    reply = data.get("output", "Tâche reçue et en cours de traitement.")
                    await message.reply(reply[:2000])  # Discord limit
                    await message.remove_reaction("⏳", client.user)
                    await message.add_reaction("✅")
                else:
                    await message.reply(f"❌ Erreur API: {resp.status}")
                    await message.remove_reaction("⏳", client.user)
                    await message.add_reaction("❌")

    except Exception as e:
        await message.reply(f"❌ Erreur: {str(e)[:200]}")
        await message.remove_reaction("⏳", client.user)
        await message.add_reaction("❌")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
PYTHON
```

### 9.8 Tester l'intégration Discord

```bash
# 1. S'assurer que le .env contient les tokens Discord
grep DISCORD .env

# 2. Tester le bot en standalone
cd ~/langgraph-project
source .venv/bin/activate
pip install discord.py aiohttp
python agents/discord_listener.py

# 3. Dans Discord, aller dans #commandes et taper :
#    "Bonjour, quel est le statut du projet ?"
# → Le bot devrait réagir avec ⏳ puis répondre
```

---

## 10. Phase 8 — Couche RAG (pgvector + embeddings)

> **Script** : `05-install-rag.sh`
> **Prérequis** : Phase 3 terminée, stack Docker running (`docker compose up -d`)

### 10.1 Objectif

Donner une **mémoire partagée** à tous les agents. Chaque livrable produit (PRD, ADR, code, user stories…) est découpé en chunks, transformé en vecteur via un modèle d'embeddings, et stocké dans PostgreSQL/pgvector. Les agents peuvent ensuite faire une recherche sémantique avant de produire leur propre livrable.

```
Agent Analyste ──► index_document() ──► pgvector (rag.documents)
                                              │
Agent Architecte ──► search() ◄───────────────┘
```

### 10.2 Installation rapide

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main/scripts/Infra/05-install-rag.sh)"
```

### 10.3 Ce que fait le script

| Étape | Action |
|-------|--------|
| 1/6 | Ajoute `VOYAGE_API_KEY` et `EMBEDDING_MODEL` dans `.env` |
| 2/6 | Crée le schema SQL `rag` avec la table `rag.documents` (vector 1024 dims) |
| 3/6 | Génère `agents/shared/rag_service.py` (chunking, indexation, recherche) |
| 4/6 | Installe les dépendances Python (`voyageai`, `tiktoken`) |
| 5/6 | Met à jour `requirements.txt` |
| 6/6 | Valide le schema, les index et les fonctions SQL |

### 10.4 Schema PostgreSQL

Le script crée le schema `rag` avec la table principale :

```sql
CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    embedding vector(1024),          -- Voyage AI (1024 dims)

    -- Traçabilité
    source_type VARCHAR(50) NOT NULL, -- prd, adr, code, user_story, test_report, legal, mockup, doc
    source_agent VARCHAR(50) NOT NULL, -- orchestrator, analyst, architect, lead_dev, etc.
    source_id UUID,
    project_name VARCHAR(200),
    phase VARCHAR(50),

    -- Technique
    chunk_index INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 1,
    file_path VARCHAR(500),
    language VARCHAR(20) DEFAULT 'fr',
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index HNSW pour recherche de similarité cosinus
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON rag.documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);
```

**Fonctions SQL créées :**

| Fonction | Rôle |
|----------|------|
| `rag.search_similar()` | Recherche les N documents les plus proches d'un vecteur, avec filtres optionnels (source_type, phase, agent) et seuil de similarité |
| `rag.upsert_document_chunks()` | Supprime les anciens chunks d'un document avant ré-indexation |

### 10.5 Service Python — `rag_service.py`

Le fichier `agents/shared/rag_service.py` expose les fonctions principales :

```python
from agents.shared.rag_service import (
    index_document,     # Indexe un document (chunking + embedding + INSERT)
    search,             # Recherche sémantique avec filtres
    create_rag_tools,   # Retourne des tools LangChain (rag_search, rag_index)
    DocumentMetadata,   # Dataclass pour les métadonnées
)
```

**Modèles d'embeddings supportés :**

| Modèle | Config `.env` | Dimensions | Notes |
|--------|--------------|------------|-------|
| Voyage AI `voyage-3-large` | `EMBEDDING_MODEL=voyage-3-large` | 1024 | Par défaut, nécessite `VOYAGE_API_KEY` |
| Local (Ollama) | `EMBEDDING_MODEL=local` | Variable | Gratuit, nécessite Ollama + `nomic-embed-text` |

### 10.6 Utilisation dans les agents

Chaque agent peut utiliser les tools RAG directement :

```python
from agents.shared.rag_service import create_rag_tools

# Dans la définition de l'agent LangGraph
tools = create_rag_tools()  # [rag_search, rag_index]
```

**Matrice agent ↔ RAG :**

| Agent | Indexe | Recherche |
|-------|--------|-----------|
| Analyste | PRDs, user stories | Historique projet, besoins similaires |
| Designer | Mockups, guidelines | Specs fonctionnelles |
| Architecte | ADRs, schémas | Specs, contraintes techniques |
| Lead Dev | Code, implémentations | Architecture, maquettes |
| QA | Rapports de tests | Critères d'acceptation |
| Avocat | Analyses juridiques | Base juridique, licences |
| Documentaliste | Documentation finale | Tout (cohérence globale) |

### 10.7 Configuration post-installation

```bash
# 1. Ajouter votre clé Voyage AI
nano ~/langgraph-project/.env
# → Remplacer VOYAGE_API_KEY=pa-VOTRE-CLE-VOYAGE-AI par votre vraie clé
#   (https://dash.voyageai.com → API Keys)

# 2. Tester manuellement
cd ~/langgraph-project
source .venv/bin/activate
DB_PASS=$(grep POSTGRES_PASSWORD .env | cut -d= -f2)
DATABASE_URI="postgres://langgraph:${DB_PASS}@localhost:5432/langgraph?sslmode=disable" \
python -c "
from agents.shared.rag_service import index_document, search, DocumentMetadata
meta = DocumentMetadata(source_type='test', source_agent='manual')
index_document('Mon premier document de test', meta)
results = search('document test')
print(f'Résultats: {len(results)}')
"

# 3. Rebuild l'image Docker pour inclure le RAG
docker compose up -d --build langgraph-api
```

---

## 11. Phase 9 — Sécurisation

### 11.1 Firewall (UFW)

```bash
# Politique par défaut
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH
sudo ufw allow 22/tcp

# API LangGraph (uniquement réseau local)
sudo ufw allow from 192.168.1.0/24 to any port 8123

# Langfuse UI (uniquement réseau local)
sudo ufw allow from 192.168.1.0/24 to any port 3000

# Activer
sudo ufw enable
```

### 11.2 Reverse proxy (Caddy — optionnel)

```bash
# Si vous voulez exposer via HTTPS
sudo apt install -y caddy

# /etc/caddy/Caddyfile
cat > /etc/caddy/Caddyfile << 'CADDY'
langgraph.votredomaine.local {
    reverse_proxy localhost:8123
    tls internal
}

langfuse.votredomaine.local {
    reverse_proxy localhost:3000
    tls internal
}
CADDY

sudo systemctl reload caddy
```

### 11.3 Gestion des secrets

```bash
# Ne JAMAIS committer le .env
echo ".env" >> .gitignore
echo "*.key" >> .gitignore

# Optionnel : chiffrer les secrets avec SOPS + age
# https://github.com/getsops/sops
```

---

## 12. Phase 10 — Intégration repo Proxmox

### 12.1 Structure recommandée pour votre repo

Ajoutez un dossier dans votre repo `Configurations/Proxmox` :

```
Configurations/Proxmox/
├── ...vos scripts existants...
│
└── vms/
    └── langgraph-agents/
        ├── README.md                     # Ce document
        ├── create-vm.sh                  # Script de création de la VM
        ├── provision.sh                  # Script d'installation post-boot
        │
        ├── docker/
        │   ├── docker-compose.yml        # Stack complète
        │   ├── docker-compose.infra.yml  # Infra seule (dev)
        │   ├── docker-compose.observability.yml
        │   ├── Dockerfile                # Image des agents
        │   ├── Dockerfile.discord        # Image bot Discord
        │   └── .env.example              # Template (sans secrets)
        │
        ├── config/
        │   ├── init.sql                  # Schema Postgres
        │   ├── daemon.json               # Config Docker
        │   └── Caddyfile                 # Reverse proxy
        │
        ├── agents/                       # Code des agents
        │   ├── orchestrator.py
        │   ├── requirements_agent.py
        │   ├── developer_agent.py
        │   ├── discord_listener.py       # Bot Discord listener
        │   ├── shared/
        │   │   ├── discord_tools.py      # Discord MCP tools
        │   │   └── ...
        │   └── ...
        │
        ├── prompts/                      # System prompts versionnés
        │   ├── v1/
        │   │   ├── orchestrator.md
        │   │   ├── requirements.md
        │   │   └── developer.md
        │   └── v2/
        │       └── ...
        │
        └── scripts/
            ├── backup.sh                 # Backup Postgres + Redis
            ├── update.sh                 # Mise à jour des agents
            └── healthcheck.py            # Vérification de santé
```

### 12.2 Script de création de VM automatisé

```bash
# Configurations/Proxmox/vms/langgraph-agents/create-vm.sh
#!/bin/bash
set -euo pipefail

# ── Configuration ────────────────────────────
VMID=${1:-200}
VM_NAME="langgraph-agents"
CORES=8
MEMORY=16384
DISK_SIZE="100G"
STORAGE="local-lvm"
BRIDGE="vmbr0"
ISO_PATH="local:iso/ubuntu-24.04-live-server-amd64.iso"

echo "🚀 Création de la VM ${VM_NAME} (ID: ${VMID})..."

qm create ${VMID} \
  --name ${VM_NAME} \
  --cores ${CORES} \
  --memory ${MEMORY} \
  --machine q35 \
  --bios ovmf \
  --efidisk0 ${STORAGE}:1,efitype=4m,pre-enrolled-keys=1 \
  --scsi0 ${STORAGE}:${DISK_SIZE},iothread=1,discard=on,ssd=1 \
  --scsihw virtio-scsi-single \
  --net0 virtio,bridge=${BRIDGE} \
  --ide2 ${ISO_PATH},media=cdrom \
  --boot order=scsi0\;ide2 \
  --ostype l26 \
  --cpu host \
  --numa 1 \
  --agent enabled=1 \
  --tags langgraph,ai-agents,production \
  --description "LangGraph Multi-Agent Platform - voir repo Configurations/Proxmox"

echo "✅ VM ${VMID} créée. Démarrer avec : qm start ${VMID}"
```

### 12.3 Script de provisioning post-installation

```bash
# Configurations/Proxmox/vms/langgraph-agents/provision.sh
#!/bin/bash
set -euo pipefail

echo "═══════════════════════════════════════════"
echo "  LangGraph Multi-Agent — Provisioning"
echo "═══════════════════════════════════════════"

# ── 1. Système ────────────────────────────────
echo "📦 [1/5] Mise à jour système..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  curl wget git vim htop tmux \
  ca-certificates gnupg lsb-release \
  ufw fail2ban qemu-guest-agent \
  python3 python3-pip python3-venv

# ── 2. Docker ─────────────────────────────────
echo "🐳 [2/5] Installation Docker..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER

# ── 3. Projet ─────────────────────────────────
echo "📂 [3/5] Setup du projet LangGraph..."
mkdir -p ~/langgraph-project/{agents,config,data,scripts,prompts}

# ── 4. Python ─────────────────────────────────
echo "🐍 [4/5] Environnement Python..."
cd ~/langgraph-project
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install \
  langgraph langgraph-checkpoint-postgres \
  langchain-anthropic langchain-core langsmith \
  anthropic pydantic psycopg[binary] psycopg-pool \
  redis python-dotenv fastapi uvicorn \
  discord.py aiohttp

# ── 5. Firewall ────────────────────────────────
echo "🔒 [5/5] Configuration firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow from 192.168.1.0/24 to any port 8123
sudo ufw allow from 192.168.1.0/24 to any port 3000
sudo ufw --force enable

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Provisioning terminé !"
echo ""
echo "  Prochaines étapes :"
echo "  1. Copier le .env : cp .env.example .env"
echo "  2. Remplir les clés API dans .env"
echo "  3. Lancer l'infra : docker compose -f docker-compose.infra.yml up -d"
echo "  4. Tester : python agents/orchestrator.py"
echo "═══════════════════════════════════════════"
```

### 12.4 Script de backup

```bash
# Configurations/Proxmox/vms/langgraph-agents/scripts/backup.sh
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/home/$USER/langgraph-project/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p ${BACKUP_DIR}

echo "💾 Backup PostgreSQL..."
docker exec langgraph-postgres pg_dump \
  -U langgraph -d langgraph \
  --format=custom \
  > "${BACKUP_DIR}/postgres_${DATE}.dump"

echo "💾 Backup Redis..."
docker exec langgraph-redis redis-cli \
  -a $(grep REDIS_PASSWORD ~/langgraph-project/.env | cut -d= -f2) \
  BGSAVE
sleep 2
docker cp langgraph-redis:/data/appendonly.aof \
  "${BACKUP_DIR}/redis_${DATE}.aof"

echo "💾 Backup des prompts et configs..."
tar -czf "${BACKUP_DIR}/config_${DATE}.tar.gz" \
  -C ~/langgraph-project \
  agents/ config/ prompts/ langgraph.json

# Rotation : garder les 7 derniers
ls -t ${BACKUP_DIR}/postgres_*.dump | tail -n +8 | xargs -r rm
ls -t ${BACKUP_DIR}/redis_*.aof | tail -n +8 | xargs -r rm
ls -t ${BACKUP_DIR}/config_*.tar.gz | tail -n +8 | xargs -r rm

echo "✅ Backup terminé : ${BACKUP_DIR}/*_${DATE}.*"
```

---

## 13. Arborescence finale

```
~/langgraph-project/
├── .env                          # Secrets (NON commité)
├── .env.example                  # Template sans secrets
├── .gitignore
├── docker-compose.yml            # Stack complète (prod)
├── docker-compose.infra.yml      # Postgres + Redis seuls (dev)
├── docker-compose.observability.yml
├── Dockerfile                    # Image agents LangGraph
├── Dockerfile.discord            # Image bot Discord
├── requirements.txt
├── langgraph.json                # Config LangGraph CLI
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py           # Meta-agent PM
│   ├── requirements_agent.py     # Analyste
│   ├── architect_agent.py        # Architecte
│   ├── developer_agent.py        # Développeur
│   ├── qa_agent.py               # QA
│   ├── devops_agent.py           # DevOps
│   ├── docs_agent.py             # Documentaliste
│   ├── discord_listener.py       # Bot Discord (écoute #commandes)
│   ├── gateway.py                # FastAPI entry point
│   └── shared/
│       ├── state.py              # ProjectState (Pydantic)
│       ├── memory.py             # RAG / Vector store utils
│       ├── discord_tools.py      # Discord MCP tools (notify, approve, alert)
│       └── tools.py              # MCP tool definitions
│
├── prompts/                      # System prompts versionnés
│   └── v1/
│       ├── orchestrator.md
│       ├── requirements.md
│       └── ...
│
├── config/
│   ├── init.sql                  # Schema Postgres
│   ├── daemon.json               # Docker daemon config
│   └── Caddyfile                 # Reverse proxy
│
├── scripts/
│   ├── backup.sh
│   ├── update.sh
│   └── healthcheck.py
│
└── data/
    └── backups/                  # Backups locaux
```

---

## 14. Troubleshooting

| Problème | Cause probable | Solution |
|----------|---------------|----------|
| `connection refused` sur Postgres | Container pas encore healthy | `docker compose logs langgraph-postgres` — vérifier le healthcheck |
| `ANTHROPIC_API_KEY not set` | `.env` mal chargé | Vérifier que `python-dotenv` est installé et que le path est correct |
| Agent timeout | Context window trop large | Réduire `max_tokens`, utiliser Sonnet au lieu d'Opus pour les tâches simples |
| `pgvector extension not found` | Image Postgres sans pgvector | Utiliser `pgvector/pgvector:pg16` et non `postgres:16` |
| Redis `NOAUTH` | Mot de passe Redis manquant dans l'URI | Vérifier format : `redis://:PASSWORD@host:6379/0` |
| Docker permission denied | User pas dans le groupe docker | `sudo usermod -aG docker $USER` puis re-login |
| VM lente sur Proxmox | CPU type non-host | Vérifier `--cpu host` dans la config VM |
| LangSmith traces manquantes | Tracing pas activé | `LANGCHAIN_TRACING_V2=true` dans `.env` |
| Bot Discord ne se connecte pas | Token invalide ou intents manquants | Vérifier `DISCORD_BOT_TOKEN` dans `.env` + activer les Privileged Intents dans le Developer Portal |
| Bot Discord ne répond pas dans #commandes | Mauvais channel ID | Vérifier `DISCORD_CHANNEL_COMMANDS` — c'est l'ID numérique, pas le nom |
| Discord `Forbidden 403` | Permissions bot insuffisantes | Re-inviter le bot avec les permissions correctes (Send Messages, Read History, etc.) |
| `MESSAGE_CONTENT` intent error | Intent non activé | Aller dans Discord Developer Portal → Bot → activer `MESSAGE CONTENT INTENT` |
| Human gate timeout (Discord) | Personne n'a répondu à temps | Augmenter le `timeout` dans `request_human_approval()` ou configurer une action par défaut |

---

## Checklist de déploiement

- [ ] VM créée sur Proxmox avec les bonnes specs
- [ ] Ubuntu installé et mis à jour
- [ ] Docker + Docker Compose installés
- [ ] PostgreSQL + pgvector opérationnels
- [ ] Redis opérationnel
- [ ] `.env` configuré avec les clés API
- [ ] Agent de test (`orchestrator.py`) fonctionne
- [ ] Langfuse accessible (optionnel)
- [ ] Bot Discord créé (Developer Portal) avec les bons intents
- [ ] Serveur Discord structuré (channels agents, review, commandes)
- [ ] Bot Discord connecté et répond dans #commandes
- [ ] Human gate fonctionne (approve/revise dans #human-review)
- [ ] Firewall configuré
- [ ] Backup automatisé (cron)
- [ ] Scripts ajoutés au repo `Configurations/Proxmox`