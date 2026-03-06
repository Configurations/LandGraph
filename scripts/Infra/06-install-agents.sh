#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph (equipe complete)
# VERSION CONSOLIDEE (integre fix 07 gateway + 08 context + max_tokens)
#
# A executer depuis la VM Ubuntu (apres les scripts 03 et 05).
# Usage : ./06-install-agents.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 6 : Installation des agents"
echo "  (version consolidee)"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"
[ ! -f .env ] && echo "ERREUR : .env introuvable." && exit 1

# ── 1. Structure ─────────────────────────────
echo "[1/8] Structure..."
mkdir -p agents/shared prompts/v1
touch agents/__init__.py agents/shared/__init__.py

# ── 2. Prompts ───────────────────────────────
echo "[2/8] Telechargement des prompts..."
PROMPTS=(orchestrator requirements_analyst ux_designer architect planner lead_dev dev_frontend_web dev_backend_api dev_mobile qa_engineer devops_engineer docs_writer legal_advisor)
DL=0
for name in "${PROMPTS[@]}"; do
    T="prompts/v1/${name}.md"
    if wget -qO "$T" "${REPO_RAW}/prompts/${name}.md" 2>/dev/null && [ -s "$T" ]; then
        DL=$((DL+1))
    elif wget -qO "$T" "${REPO_RAW}/prompts/v1/${name}.md" 2>/dev/null && [ -s "$T" ]; then
        DL=$((DL+1))
    else
        echo "Tu es ${name}, agent LangGraph. Reponds en JSON: {agent_id, status, confidence, deliverables}." > "$T"
    fi
done
echo "  -> ${DL}/${#PROMPTS[@]} prompts"

# ── 3. shared/state.py ──────────────────────
echo "[3/8] ProjectState..."
cat > agents/shared/state.py << 'PY'
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
class ProjectState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    project_id: str
    project_phase: str
    project_metadata: dict
    agent_outputs: dict
    current_assignments: dict
    decision_history: list
    blockers: list
    legal_alerts: list
    qa_verdict: dict
    deploy_status: dict
    human_feedback_log: list
    notifications_log: list
PY

# ── 4. shared/base_agent.py ─────────────────
echo "[4/8] BaseAgent (avec extract_brief/task)..."
cat > agents/shared/base_agent.py << 'PY'
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
load_dotenv()
logger = logging.getLogger(__name__)

class BaseAgent:
    agent_id = "base"; agent_name = "Base"; default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3; default_max_tokens = 16384; prompt_filename = "base.md"

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()

    def _load_prompt(self):
        for p in [os.path.join(os.path.dirname(__file__),"..","..", "prompts","v1",self.prompt_filename), os.path.join("/app","prompts","v1",self.prompt_filename)]:
            a = os.path.abspath(p)
            if os.path.exists(a):
                logger.info(f"[{self.agent_id}] Prompt: {a}")
                return open(a).read()
        return f"Tu es {self.agent_name}. JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self):
        return ChatAnthropic(model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"): return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg)==2 and msg[0]=="user" and len(msg[1])>20: return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c)>20: return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target")==self.agent_id: return a.get("task") or ""
                elif hasattr(a, "target") and a.target==self.agent_id: return a.task or ""
        return ""

    def build_context(self, state):
        return {"project_phase": state.get("project_phase"), "project_metadata": state.get("project_metadata",{}),
                "brief": self._extract_brief(state), "task": self._extract_task(state),
                "existing_outputs": list(state.get("agent_outputs",{}).keys())}

    def parse_response(self, raw):
        c = raw.strip()
        if "```json" in c: c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c: c = c.split("```")[1].split("```")[0].strip()
        return json.loads(c)

    def __call__(self, state):
        try:
            ctx = self.build_context(state); llm = self.get_llm()
            logger.info(f"[{self.agent_id}] LLM call — brief:{len(ctx.get('brief',''))}c task:{ctx.get('task','')[:80]}")
            r = llm.invoke([{"role":"system","content":self.system_prompt},
                {"role":"user","content":f"Contexte:\n```json\n{json.dumps(ctx,indent=2,default=str)}\n```\nTache: {ctx.get('task','Produire tes livrables')}\nReponds en JSON valide."}])
            raw = r.content if isinstance(r.content, str) else str(r.content)
            logger.info(f"[{self.agent_id}] Response: {len(raw)}c")
            try: output = self.parse_response(raw)
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] JSON fail: {e}")
                output = {"agent_id":self.agent_id,"status":"complete","confidence":0.6,
                          "deliverables":{"raw_output":raw[:8000]},"parse_note":str(e)[:100]}
            output["agent_id"]=self.agent_id; output["timestamp"]=datetime.now(timezone.utc).isoformat()
            ao = dict(state.get("agent_outputs",{})); ao[self.agent_id]=output; state["agent_outputs"]=ao
            msgs = list(state.get("messages",[])); msgs.append(("assistant",f"[{self.agent_id}] status={output.get('status')}")); state["messages"]=msgs
            logger.info(f"[{self.agent_id}] status={output.get('status')} conf={output.get('confidence')}")
            return state
        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
            ao = dict(state.get("agent_outputs",{}))
            ao[self.agent_id]={"agent_id":self.agent_id,"status":"blocked","error":str(e),"timestamp":datetime.now(timezone.utc).isoformat()}
            state["agent_outputs"]=ao; return state
PY

echo "  -> Modules partages crees"
# ── 5. Agents specialistes ───────────────────
echo "[5/8] Agents specialistes..."

for AGENT_DEF in \
  "requirements_analyst:Analyste:0.3:16384:requirements_analyst.md" \
  "ux_designer:Designer UX:0.4:16384:ux_designer.md" \
  "architect:Architecte:0.2:16384:architect.md" \
  "planner:Planificateur:0.2:16384:planner.md" \
  "lead_dev:Lead Dev:0.2:8192:lead_dev.md" \
  "dev_frontend_web:Dev Frontend Web:0.2:16384:dev_frontend_web.md" \
  "dev_backend_api:Dev Backend API:0.2:16384:dev_backend_api.md" \
  "dev_mobile:Dev Mobile:0.2:16384:dev_mobile.md" \
  "qa_engineer:QA Engineer:0.2:16384:qa_engineer.md" \
  "devops_engineer:DevOps Engineer:0.2:16384:devops_engineer.md" \
  "docs_writer:Documentaliste:0.3:16384:docs_writer.md" \
  "legal_advisor:Avocat:0.2:16384:legal_advisor.md"; do

  IFS=':' read -r AID ANAME ATEMP AMAX APROMPT <<< "${AGENT_DEF}"

  # Determiner les reads specifiques par agent
  case "${AID}" in
    requirements_analyst)
      READS='{"project_phase":state.get("project_phase","discovery"),"project_metadata":state.get("project_metadata",{}),"brief":self._extract_brief(state),"task":self._extract_task(state),"existing_outputs":list(state.get("agent_outputs",{}).keys())}' ;;
    ux_designer)
      READS='{**self._base_ctx(state),"prd":o.get("requirements_analyst",{}).get("deliverables",{}).get("prd"),"user_stories":o.get("requirements_analyst",{}).get("deliverables",{}).get("user_stories")}' ;;
    *)
      READS='self._base_ctx(state)' ;;
  esac

  cat > "agents/${AID}.py" << PYEOF
"""${ANAME}"""
from agents.shared.base_agent import BaseAgent

class Agent(BaseAgent):
    agent_id = "${AID}"
    agent_name = "${ANAME}"
    default_temperature = ${ATEMP}
    default_max_tokens = ${AMAX}
    prompt_filename = "${APROMPT}"

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {k: {"status": v.get("status"), "deliverables_keys": list(v.get("deliverables", {}).keys())} for k, v in o.items() if v.get("status") == "complete"},
        }

agent = Agent()
PYEOF
done

echo "  -> 12 agents crees"

# ── 6. Orchestrateur ─────────────────────────
echo "[6/8] Orchestrateur..."
if wget -qO agents/orchestrator.py "${REPO_RAW}/prompts/orchestrator.py" 2>/dev/null && [ -s agents/orchestrator.py ]; then
    echo "  -> telecharge"
else
    echo "  -> conserve (local)"
fi

# ── 7. Gateway multi-agent ───────────────────
echo "[7/8] Gateway multi-agent..."

cat > agents/gateway.py << 'PY'
"""FastAPI Gateway — Graphe multi-agent complet."""
import json,logging,os
from datetime import datetime,timezone
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
load_dotenv()
logger=logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
app=FastAPI(title="LangGraph Multi-Agent API",version="0.3.0")

from agents.requirements_analyst import agent as a1
from agents.ux_designer import agent as a2
from agents.architect import agent as a3
from agents.planner import agent as a4
from agents.lead_dev import agent as a5
from agents.dev_frontend_web import agent as a6
from agents.dev_backend_api import agent as a7
from agents.dev_mobile import agent as a8
from agents.qa_engineer import agent as a9
from agents.devops_engineer import agent as a10
from agents.docs_writer import agent as a11
from agents.legal_advisor import agent as a12
from agents.orchestrator import orchestrator_node,route_after_orchestrator
from langgraph.graph import StateGraph,END
from langgraph.checkpoint.postgres import PostgresSaver

AGENT_MAP={"requirements_analyst":a1,"ux_designer":a2,"architect":a3,"planner":a4,
    "lead_dev":a5,"dev_frontend_web":a6,"dev_backend_api":a7,"dev_mobile":a8,
    "qa_engineer":a9,"devops_engineer":a10,"docs_writer":a11,"legal_advisor":a12}

def human_gate_node(state):
    logger.info("HUMAN GATE — auto approve")
    f=list(state.get("human_feedback_log",[])); f.append({"timestamp":datetime.now(timezone.utc).isoformat(),"response":"approve","source":"auto"})
    state["human_feedback_log"]=f; return state

def build_graph():
    g=StateGraph(dict); g.add_node("orchestrator",orchestrator_node); g.add_node("human_gate",human_gate_node)
    for aid,ac in AGENT_MAP.items(): g.add_node(aid,ac)
    g.set_entry_point("orchestrator")
    rm={aid:aid for aid in AGENT_MAP}; rm.update({"human_gate":"human_gate","orchestrator":"orchestrator","end":END})
    g.add_conditional_edges("orchestrator",route_after_orchestrator,rm)
    for aid in AGENT_MAP: g.add_edge(aid,"orchestrator")
    g.add_edge("human_gate","orchestrator"); return g

GRAPH=None
def get_graph():
    global GRAPH
    if not GRAPH:
        c=psycopg.connect(os.getenv("DATABASE_URI"),autocommit=True); cp=PostgresSaver(c); cp.setup()
        GRAPH=build_graph().compile(checkpointer=cp); logger.info("Graph ready — %d agents",len(AGENT_MAP)+1)
    return GRAPH

@app.get("/health")
async def health(): return {"status":"ok","service":"langgraph-multi-agent","version":"0.3.0"}

@app.get("/status")
async def status(): return {"agents":list(AGENT_MAP)+["orchestrator"],"total_agents":len(AGENT_MAP)+1}

class InvokeReq(BaseModel):
    messages:list[dict]; thread_id:str="default"; project_id:str="default"
class InvokeRes(BaseModel):
    output:str; thread_id:str; decisions:list=[]; agent_outputs:dict={}

@app.post("/invoke",response_model=InvokeRes)
async def invoke(req:InvokeReq):
    try:
        g=get_graph(); cfg={"configurable":{"thread_id":req.thread_id}}
        msgs=[(m.get("role","user"),m.get("content","")) for m in req.messages]
        r=g.invoke({"messages":msgs,"project_id":req.project_id,"project_phase":"discovery",
            "project_metadata":{},"agent_outputs":{},"legal_alerts":[],"decision_history":[],
            "current_assignments":{},"blockers":[],"human_feedback_log":[],"notifications_log":[]},cfg)
        decs=r.get("decision_history",[]); aos=r.get("agent_outputs",{}); parts=[]
        for i,d in enumerate(decs,1):
            parts.append(f"[Orchestrateur] Decision {i}: {d.get('decision_type')} (conf:{d.get('confidence')})\n{d.get('reasoning','')[:300]}")
            for a in d.get("actions",[]):
                t=(a.get("target") or ""); tk=(a.get("task") or "")[:200]
                if a.get("action")=="dispatch_agent" and t: parts.append(f"  -> {t}: {tk}")
        for aid,o in aos.items():
            parts.append(f"\n[{aid}] status={o.get('status')}, conf={o.get('confidence','N/A')}")
            dl=o.get("deliverables",{})
            if isinstance(dl,dict):
                for k in list(dl.keys())[:5]:
                    v=dl[k]
                    if isinstance(v,str): v=v[:300]+"..." if len(v)>300 else v
                    elif isinstance(v,(dict,list)): s=json.dumps(v,ensure_ascii=False,default=str); v=s[:300]+"..." if len(s)>300 else s
                    parts.append(f"  {k}: {v}")
        return InvokeRes(output="\n\n".join(parts) if parts else "En attente.",thread_id=req.thread_id,
            decisions=decs,agent_outputs={k:{"status":v.get("status"),"agent_id":k} for k,v in aos.items()})
    except Exception as e:
        logger.error(f"Invoke error: {e}",exc_info=True); raise HTTPException(500,str(e))

@app.on_event("startup")
async def startup():
    try: get_graph(); logger.info("Gateway ready")
    except Exception as e: logger.error(f"Init error: {e}")
PY

echo "  -> gateway.py installe"

# ── 8. Dockerfile + rebuild + validation ─────
echo "[8/8] Rebuild et validation..."

grep -q "COPY prompts/" Dockerfile 2>/dev/null || sed -i '/COPY config\//a COPY prompts/ ./prompts/' Dockerfile

docker compose up -d --build langgraph-api
sleep 12

AC=$(ls -1 agents/*.py 2>/dev/null | grep -v __init__ | grep -v gateway | wc -l)
PC=$(ls -1 prompts/v1/*.md 2>/dev/null | wc -l)
echo "  Agents: ${AC} | Prompts: ${PC}"

H=$(curl -s http://localhost:8123/health 2>/dev/null || echo error)
S=$(curl -s http://localhost:8123/status 2>/dev/null || echo '{}')
NA=$(echo "$S" | python3 -c "import sys,json;print(json.load(sys.stdin).get('total_agents',0))" 2>/dev/null || echo 0)
echo "  Health: ${H}"
echo "  API Agents: ${NA}"

echo ""
echo "  ┌─────────────────────────────────────────────────┐"
echo "  │ 🎯 Orchestrateur    │ 📋 Analyste              │"
echo "  │ 🎨 Designer UX      │ 🏗️ Architecte            │"
echo "  │ 📅 Planificateur    │ ⚡ Lead Dev              │"
echo "  │   🌐 Frontend Web   │   🔧 Backend API         │"
echo "  │   📱 Mobile         │ 🔍 QA Engineer           │"
echo "  │ 🚀 DevOps           │ 📝 Documentaliste        │"
echo "  │ ⚖️ Avocat            │                          │"
echo "  └─────────────────────────────────────────────────┘"
echo ""
echo "  Testez : Discord #commandes ou curl localhost:8123/invoke"
echo "==========================================="
