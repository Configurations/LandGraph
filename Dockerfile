FROM python:3.11-slim

WORKDIR /app

# System deps + Node.js (pour MCP servers npx)
RUN for i in 1 2 3; do apt-get update && break || sleep 5; done \
    && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# uv + uvx (pour MCP servers Python)
RUN pip install --no-cache-dir uv

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Agents/ ./agents/
# Linux is case-sensitive: rename Shared → shared to match Python imports
RUN if [ -d /app/agents/Shared ]; then mv /app/agents/Shared /app/agents/shared; fi
COPY config/ ./config/
COPY config/langgraph.json .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agents.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
