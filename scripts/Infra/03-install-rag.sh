#!/bin/bash
###############################################################################
# Script 03 : Installation de la couche RAG (pgvector + embeddings)
#
# A executer depuis la VM Ubuntu (apres le script 02).
# Prerequis : PostgreSQL + pgvector deja en fonctionnement (docker compose up)
#
# Usage : ./03-install-rag.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 03 : Installation couche RAG"
echo "  (pgvector + embeddings)"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────────────────────────────────────
cd "${PROJECT_DIR}"

if [ ! -f .env ]; then
    echo "ERREUR : .env introuvable. Executez d'abord 02-install-langgraph.sh"
    exit 1
fi

if ! docker compose ps langgraph-postgres 2>/dev/null | grep -q healthy; then
    echo "ERREUR : PostgreSQL n'est pas running/healthy."
    echo "Lancez d'abord : cd ${PROJECT_DIR} && docker compose up -d"
    exit 1
fi

# ── 1. Ajouter VOYAGE_API_KEY au .env ───────────────────────────────────────
echo "[1/6] Configuration du .env..."
if ! grep -q "VOYAGE_API_KEY" .env; then
    cat >> .env << 'EOF'

# ── Embeddings (RAG) ────────────────────────
VOYAGE_API_KEY=pa-VOTRE-CLE-VOYAGE-AI
# Alternative gratuite : mettre EMBEDDING_MODEL=local (necessite Ollama)
EMBEDDING_MODEL=voyage-3-large
EOF
    echo "  -> Variables RAG ajoutees au .env"
    echo "  -> PENSEZ A REMPLACER VOYAGE_API_KEY par votre vraie cle !"
    echo "     (https://dash.voyageai.com -> API Keys)"
else
    echo "  -> Variables RAG deja presentes dans .env"
fi

# ── 2. Schema RAG dans PostgreSQL ────────────────────────────────────────────
echo "[2/6] Creation du schema RAG dans PostgreSQL..."

DB_USER=$(grep POSTGRES_USER .env | cut -d= -f2)
DB_NAME=$(grep POSTGRES_DB .env | cut -d= -f2)

docker exec -i langgraph-postgres psql -U "${DB_USER}" -d "${DB_NAME}" << 'SQL'

-- ══════════════════════════════════════════════
-- Schema RAG (pgvector) — memoire partagee
-- ══════════════════════════════════════════════
CREATE SCHEMA IF NOT EXISTS rag;

-- Verifier que l'extension vector est active
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table principale des documents indexes
-- Chaque livrable d'agent est decoupe en chunks et embede ici
CREATE TABLE IF NOT EXISTS rag.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Contenu
    content TEXT NOT NULL,
    embedding vector(1024),

    -- Metadonnees de tracabilite
    source_type VARCHAR(50) NOT NULL,
    source_agent VARCHAR(50) NOT NULL,
    source_id UUID,
    project_name VARCHAR(200),
    phase VARCHAR(50),

    -- Metadonnees techniques
    chunk_index INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 1,
    file_path VARCHAR(500),
    language VARCHAR(20) DEFAULT 'fr',

    -- Metadonnees custom (flexible)
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index vectoriel HNSW pour la recherche de similarite
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON rag.documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- Index pour les filtres frequents
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON rag.documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_source_agent ON rag.documents(source_agent);
CREATE INDEX IF NOT EXISTS idx_documents_phase ON rag.documents(phase);
CREATE INDEX IF NOT EXISTS idx_documents_project ON rag.documents(project_name);
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON rag.documents USING gin(metadata);

-- ── Fonction de recherche de similarite ─────

CREATE OR REPLACE FUNCTION rag.search_similar(
    query_embedding vector(1024),
    match_count INTEGER DEFAULT 5,
    filter_source_type VARCHAR DEFAULT NULL,
    filter_phase VARCHAR DEFAULT NULL,
    filter_agent VARCHAR DEFAULT NULL,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    source_type VARCHAR,
    source_agent VARCHAR,
    phase VARCHAR,
    metadata JSONB,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.content,
        d.source_type,
        d.source_agent,
        d.phase,
        d.metadata,
        (1 - (d.embedding <=> query_embedding))::FLOAT AS similarity
    FROM rag.documents d
    WHERE
        (filter_source_type IS NULL OR d.source_type = filter_source_type)
        AND (filter_phase IS NULL OR d.phase = filter_phase)
        AND (filter_agent IS NULL OR d.source_agent = filter_agent)
        AND (1 - (d.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- ── Fonction de nettoyage avant re-indexation ─

CREATE OR REPLACE FUNCTION rag.upsert_document_chunks(
    p_source_id UUID,
    p_source_type VARCHAR,
    p_source_agent VARCHAR
)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM rag.documents
    WHERE source_id = p_source_id
      AND source_type = p_source_type
      AND source_agent = p_source_agent;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

SQL

echo "  -> Schema rag.documents cree"
echo "  -> Index HNSW cree"
echo "  -> Fonctions search_similar et upsert_document_chunks creees"

# ── 3. Service RAG Python ────────────────────────────────────────────────────
echo "[3/6] Creation du service RAG (agents/shared/rag_service.py)..."

mkdir -p "${PROJECT_DIR}/agents/shared"

cat > "${PROJECT_DIR}/agents/shared/rag_service.py" << 'PYTHON'
"""
Service RAG centralise — utilise par tous les agents.
Stocke et recupere les embeddings via PostgreSQL + pgvector.
"""
import os
import uuid
from typing import Optional
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URI = os.getenv("DATABASE_URI")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3-large")
EMBEDDING_DIM = 1024


# ── Embedding client ─────────────────────────

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Genere les embeddings pour une liste de textes.
    Utilise Voyage AI par defaut, ou un modele local si configure.
    """
    if EMBEDDING_MODEL == "local":
        import requests
        embeddings = []
        for text in texts:
            resp = requests.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
            )
            embeddings.append(resp.json()["embedding"])
        return embeddings
    else:
        import voyageai
        client = voyageai.Client(api_key=VOYAGE_API_KEY)
        result = client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
        return result.embeddings


def get_query_embedding(query: str) -> list[float]:
    """Embedding optimise pour les requetes de recherche."""
    if EMBEDDING_MODEL == "local":
        return get_embeddings([query])[0]
    else:
        import voyageai
        client = voyageai.Client(api_key=VOYAGE_API_KEY)
        result = client.embed([query], model=EMBEDDING_MODEL, input_type="query")
        return result.embeddings[0]


# ── Chunking ─────────────────────────────────

def chunk_text(text: str, max_tokens: int = 512, overlap: int = 50) -> list[str]:
    """
    Decoupe un texte en chunks avec overlap.
    Split par paragraphes, puis regroupe pour ne pas depasser max_tokens.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Estimation grossiere : 1 token ~ 4 chars
        if len(current_chunk + para) / 4 > max_tokens and current_chunk:
            chunks.append(current_chunk.strip())
            # Overlap : garder la fin du chunk precedent
            words = current_chunk.split()
            overlap_text = " ".join(words[-overlap:]) if len(words) > overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


# ── Indexation ───────────────────────────────

@dataclass
class DocumentMetadata:
    source_type: str       # prd, adr, code, user_story, test_report, legal, mockup, doc
    source_agent: str      # orchestrator, analyst, architect, lead_dev, etc.
    source_id: Optional[str] = None
    project_name: Optional[str] = None
    phase: Optional[str] = None
    file_path: Optional[str] = None
    language: str = "fr"
    extra: Optional[dict] = field(default_factory=dict)


def index_document(content: str, metadata: DocumentMetadata, db_uri: str = None) -> int:
    """
    Indexe un document dans pgvector.
    Le texte est decoupe en chunks, chaque chunk est embede et stocke.
    Retourne le nombre de chunks indexes.
    """
    uri = db_uri or DATABASE_URI
    source_id = metadata.source_id or str(uuid.uuid4())

    # Decouper en chunks
    chunks = chunk_text(content)

    # Generer les embeddings (batch)
    embeddings = get_embeddings(chunks)

    with psycopg.connect(uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Supprimer les anciens chunks si re-indexation
            cur.execute(
                "SELECT rag.upsert_document_chunks(%s::uuid, %s, %s)",
                (source_id, metadata.source_type, metadata.source_agent),
            )

            # Inserer les nouveaux chunks
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                cur.execute(
                    """
                    INSERT INTO rag.documents
                    (content, embedding, source_type, source_agent, source_id,
                     project_name, phase, chunk_index, total_chunks,
                     file_path, language, metadata)
                    VALUES (%s, %s::vector, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        chunk,
                        str(embedding),
                        metadata.source_type,
                        metadata.source_agent,
                        source_id,
                        metadata.project_name,
                        metadata.phase,
                        i,
                        len(chunks),
                        metadata.file_path,
                        metadata.language,
                        psycopg.types.json.Json(metadata.extra or {}),
                    ),
                )

    return len(chunks)


# ── Retrieval ────────────────────────────────

@dataclass
class SearchResult:
    content: str
    source_type: str
    source_agent: str
    phase: str
    metadata: dict
    similarity: float


def search(
    query: str,
    top_k: int = 5,
    source_type: Optional[str] = None,
    phase: Optional[str] = None,
    agent: Optional[str] = None,
    min_similarity: float = 0.7,
    db_uri: str = None,
) -> list[SearchResult]:
    """
    Recherche semantique dans la base RAG.
    Supporte le filtrage par type de source, phase et agent.
    """
    uri = db_uri or DATABASE_URI
    query_emb = get_query_embedding(query)

    with psycopg.connect(uri, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rag.search_similar(%s::vector, %s, %s, %s, %s, %s)",
                (str(query_emb), top_k, source_type, phase, agent, min_similarity),
            )
            rows = cur.fetchall()

    return [
        SearchResult(
            content=row["content"],
            source_type=row["source_type"],
            source_agent=row["source_agent"],
            phase=row["phase"] or "",
            metadata=row["metadata"] or {},
            similarity=row["similarity"],
        )
        for row in rows
    ]


# ── Tools LangGraph ──────────────────────────

def create_rag_tools():
    """
    Retourne des tools LangChain utilisables par les agents LangGraph.
    """
    from langchain_core.tools import tool

    @tool
    def rag_search(
        query: str,
        source_type: str = None,
        top_k: int = 5,
    ) -> str:
        """
        Recherche dans la memoire projet. Utilise cette tool AVANT de produire
        un livrable pour recuperer le contexte pertinent.
        source_type: prd | adr | code | user_story | test_report | legal | mockup | doc
        """
        results = search(query, top_k=top_k, source_type=source_type)
        if not results:
            return "Aucun resultat trouve dans la memoire projet."

        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(
                f"[{i}] ({r.source_type} | {r.source_agent} | sim: {r.similarity:.2f})\n"
                f"{r.content[:500]}"
            )
        return "\n\n---\n\n".join(formatted)

    @tool
    def rag_index(
        content: str,
        source_type: str,
        source_agent: str,
        phase: str = None,
    ) -> str:
        """
        Indexe un nouveau livrable dans la memoire projet.
        Appeler APRES avoir produit un livrable final.
        source_type: prd | adr | code | user_story | test_report | legal | mockup | doc
        """
        meta = DocumentMetadata(
            source_type=source_type,
            source_agent=source_agent,
            phase=phase,
        )
        count = index_document(content, meta)
        return f"Document indexe : {count} chunks dans la memoire projet."

    return [rag_search, rag_index]
PYTHON

# S'assurer qu'il y a un __init__.py dans shared
touch "${PROJECT_DIR}/agents/shared/__init__.py"

echo "  -> rag_service.py cree dans agents/shared/"

# ── 4. Installer les dependances Python ──────────────────────────────────────
echo "[4/6] Installation des dependances Python..."
source "${PROJECT_DIR}/.venv/bin/activate"
pip install -q voyageai tiktoken langchain-core 2>/dev/null
echo "  -> voyageai, tiktoken installes"

# ── 5. Mettre a jour requirements.txt ────────────────────────────────────────
echo "[5/6] Mise a jour de requirements.txt..."
if ! grep -q "voyageai" "${PROJECT_DIR}/requirements.txt"; then
    cat >> "${PROJECT_DIR}/requirements.txt" << 'TXT'
voyageai>=0.3.0
tiktoken>=0.7.0
TXT
    echo "  -> requirements.txt mis a jour"
else
    echo "  -> requirements.txt deja a jour"
fi

# ── 6. Test de validation ────────────────────────────────────────────────────
echo "[6/6] Test de validation du RAG..."
echo ""

# Verifier que le schema existe
TABLES=$(docker exec langgraph-postgres psql -U "${DB_USER}" -d "${DB_NAME}" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='rag';")
TABLES=$(echo "${TABLES}" | tr -d ' ')

if [ "${TABLES}" -ge 1 ]; then
    echo "  -> Schema RAG : OK (${TABLES} table(s))"
else
    echo "  -> ERREUR : Schema RAG non cree"
    exit 1
fi

# Verifier les fonctions
FUNCS=$(docker exec langgraph-postgres psql -U "${DB_USER}" -d "${DB_NAME}" -t -c \
    "SELECT count(*) FROM information_schema.routines WHERE routine_schema='rag';")
FUNCS=$(echo "${FUNCS}" | tr -d ' ')

if [ "${FUNCS}" -ge 2 ]; then
    echo "  -> Fonctions RAG : OK (${FUNCS} fonction(s))"
else
    echo "  -> ERREUR : Fonctions RAG non creees"
    exit 1
fi

# Verifier l'index HNSW
INDEXES=$(docker exec langgraph-postgres psql -U "${DB_USER}" -d "${DB_NAME}" -t -c \
    "SELECT count(*) FROM pg_indexes WHERE schemaname='rag' AND indexdef LIKE '%hnsw%';")
INDEXES=$(echo "${INDEXES}" | tr -d ' ')

if [ "${INDEXES}" -ge 1 ]; then
    echo "  -> Index HNSW : OK"
else
    echo "  -> ATTENTION : Index HNSW non detecte (sera cree au premier INSERT)"
fi

# Test Python (index + search) si VOYAGE_API_KEY est configuree
VOYAGE_KEY=$(grep VOYAGE_API_KEY .env | cut -d= -f2)
if [ "${VOYAGE_KEY}" != "pa-VOTRE-CLE-VOYAGE-AI" ] && [ -n "${VOYAGE_KEY}" ]; then
    echo ""
    echo "  Test d'indexation et de recherche..."

    DB_PASS=$(grep POSTGRES_PASSWORD .env | cut -d= -f2)
    DATABASE_URI="postgres://langgraph:${DB_PASS}@localhost:5432/langgraph?sslmode=disable" \
    python3 << 'PYTEST'
import os
from agents.shared.rag_service import index_document, search, DocumentMetadata

db_uri = os.getenv("DATABASE_URI")

# Indexer un document test
meta = DocumentMetadata(
    source_type="prd",
    source_agent="analyst",
    project_name="test-rag",
    phase="discovery",
)
count = index_document(
    "L'application doit permettre aux utilisateurs de creer un compte, "
    "se connecter avec email et mot de passe ou OAuth Google, "
    "et gerer leur profil avec photo, bio et preferences. "
    "Le systeme doit supporter l'authentification a deux facteurs (2FA) "
    "et la recuperation de mot de passe par email.",
    meta,
    db_uri=db_uri,
)
print(f"    Indexe : {count} chunk(s)")

# Rechercher
results = search("authentification utilisateur", top_k=3, db_uri=db_uri)
if results:
    for r in results:
        print(f"    Trouve : [{r.source_type}] sim={r.similarity:.2f} — {r.content[:80]}...")
    print("")
    print("  -> Test RAG : OK")
else:
    print("  -> ATTENTION : Aucun resultat (verifiez la cle Voyage AI)")
PYTEST

else
    echo ""
    echo "  -> Test Python ignore (VOYAGE_API_KEY non configuree)"
    echo "     Configurez-la dans .env puis testez manuellement :"
    echo "     cd ${PROJECT_DIR} && source .venv/bin/activate"
    echo "     DB_PASS=\$(grep POSTGRES_PASSWORD .env | cut -d= -f2)"
    echo "     DATABASE_URI=\"postgres://langgraph:\${DB_PASS}@localhost:5432/langgraph?sslmode=disable\" \\"
    echo "     python -c \"from agents.shared.rag_service import search; print('RAG OK')\""
fi

echo ""
echo "==========================================="
echo "  Couche RAG installee avec succes."
echo ""
echo "  Ce qui a ete cree :"
echo "  - Schema PostgreSQL : rag.documents"
echo "  - Index HNSW pour recherche vectorielle"
echo "  - Fonctions : search_similar, upsert_document_chunks"
echo "  - Service Python : agents/shared/rag_service.py"
echo "  - Tools LangGraph : rag_search, rag_index"
echo ""
echo "  Prochaines etapes :"
echo "  1. Si pas fait, ajoutez votre VOYAGE_API_KEY dans .env"
echo "     nano ${PROJECT_DIR}/.env"
echo ""
echo "  2. Pour tester manuellement :"
echo "     cd ${PROJECT_DIR}"
echo "     source .venv/bin/activate"
echo "     DB_PASS=\$(grep POSTGRES_PASSWORD .env | cut -d= -f2)"
echo "     DATABASE_URI=\"postgres://langgraph:\${DB_PASS}@localhost:5432/langgraph?sslmode=disable\" \\"
echo "     python -c \""
echo "       from agents.shared.rag_service import index_document, search, DocumentMetadata"
echo "       meta = DocumentMetadata(source_type='test', source_agent='manual')"
echo "       index_document('Mon premier document de test', meta)"
echo "       results = search('document test')"
echo "       print(f'Resultats: {len(results)}')"
echo "     \""
echo ""
echo "  3. Rebuild l'image Docker pour inclure le RAG :"
echo "     docker compose up -d --build langgraph-api"
echo ""
echo "  Matrice agent <-> RAG :"
echo "  - Analyste    : indexe PRDs, cherche historique"
echo "  - Designer    : indexe mockups, cherche guidelines"
echo "  - Architecte  : indexe ADRs, cherche specs"
echo "  - Lead Dev    : cherche archi + maquettes"
echo "  - QA          : cherche criteres d'acceptation"
echo "  - Avocat      : cherche base juridique + licences"
echo "  - Documentaliste : cherche tout (coherence)"
echo "==========================================="
