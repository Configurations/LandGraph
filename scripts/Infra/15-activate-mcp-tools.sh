#!/bin/bash
###############################################################################
# Script 15 : Activation du mode ReAct (MCP tools) dans les agents
#
# Met a jour le BaseAgent pour supporter les appels MCP tools en boucle.
# Active use_tools sur les agents qui ont des MCP configures.
#
# Usage : ./15-activate-mcp-tools.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
AGENT_ACCESS="${PROJECT_DIR}/config/agent_mcp_access.json"

echo "==========================================="
echo "  Script 15 : Activation mode ReAct MCP"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Mettre a jour BaseAgent ───────────────────────────────────────────────
echo "[1/3] Mise a jour de BaseAgent (mode ReAct + MCP tools)..."

cat > agents/shared/base_agent.py << 'PYTHON'
"""BaseAgent — Pipeline multi-etapes + mode ReAct avec MCP tools."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import ToolMessage

load_dotenv()
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def _post_to_discord_sync(channel_id, message):
    if not DISCORD_BOT_TOKEN or not channel_id:
        return
    import requests
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}
    for chunk in [message[i:i+1900] for i in range(0, len(message), 1900)]:
        try:
            requests.post(url, headers=headers, json={"content": chunk}, timeout=10)
        except Exception as e:
            logger.error(f"Discord error: {e}")


def _format_deliverable(key, val):
    if isinstance(val, str):
        return val[:1500] + "..." if len(val) > 1500 else val
    elif isinstance(val, dict):
        parts = []
        for k, v in list(val.items())[:10]:
            if isinstance(v, str):
                parts.append(f"**{k}** : {v[:300]}{'...' if len(v)>300 else ''}")
            elif isinstance(v, list):
                parts.append(f"**{k}** : {len(v)} elements")
            else:
                parts.append(f"**{k}** : {str(v)[:200]}")
        return "\n".join(parts)
    elif isinstance(val, list):
        parts = []
        for item in val[:5]:
            if isinstance(item, dict):
                parts.append("  - " + " | ".join(f"{k}={str(v)[:80]}" for k,v in list(item.items())[:4]))
            else:
                parts.append(f"  - {str(item)[:200]}")
        result = "\n".join(parts)
        if len(val) > 5:
            result += f"\n  ... et {len(val)-5} de plus"
        return result
    return str(val)[:500]


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"
    pipeline_steps = []
    use_tools = False

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()
        self._tools = None

    def _load_prompt(self):
        for p in [
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "v1", self.prompt_filename),
            os.path.join("/app", "prompts", "v1", self.prompt_filename),
        ]:
            a = os.path.abspath(p)
            if os.path.exists(a):
                logger.info(f"[{self.agent_id}] Prompt: {a}")
                return open(a).read()
        return f"Tu es {self.agent_name}. JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self):
        return ChatAnthropic(model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)

    def get_tools(self):
        """Charge les tools MCP une seule fois (lazy loading)."""
        if self._tools is None and self.use_tools:
            try:
                from agents.shared.mcp_client import get_tools_for_agent
                self._tools = get_tools_for_agent(self.agent_id)
                if self._tools:
                    logger.info(f"[{self.agent_id}] {len(self._tools)} MCP tools loaded")
                else:
                    logger.info(f"[{self.agent_id}] No MCP tools available")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] MCP tools loading failed: {e}")
                self._tools = []
        return self._tools or []

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"):
            return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg)==2 and msg[0]=="user" and len(msg[1])>20:
                return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c)>20: return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target")==self.agent_id:
                    return a.get("task") or ""
                elif hasattr(a, "target") and a.target==self.agent_id:
                    return a.task or ""
        return ""

    def _get_channel_id(self, state):
        return state.get("_discord_channel_id", "") or os.getenv("DISCORD_CHANNEL_COMMANDS", "")

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {
                k: {"status": v.get("status"), "keys": list(v.get("deliverables",{}).keys())}
                for k,v in o.items() if v.get("status")=="complete"
            },
        }

    def parse_response(self, raw):
        c = raw.strip()
        if "```json" in c: c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c: c = c.split("```")[1].split("```")[0].strip()
        return json.loads(c)

    # ── Appels LLM ───────────────────────────────────────────────────────────

    def _call_llm(self, instruction, context, previous_results=None):
        """Appel LLM simple (sans tools)."""
        llm = self.get_llm()
        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            prev_str = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(prev_str) > 15000:
                prev_str = prev_str[:15000] + "\n... (tronque)"
            user_content += f"Resultats precedents :\n```json\n{prev_str}\n```\n\n"
        user_content += f"Instruction : {instruction}\n\nReponds UNIQUEMENT en JSON valide."
        response = llm.invoke([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars")
        return raw

    def _call_llm_with_tools(self, instruction, context, previous_results=None):
        """Mode ReAct : le LLM peut appeler des MCP tools en boucle."""
        tools = self.get_tools()
        if not tools:
            return self._call_llm(instruction, context, previous_results)

        llm = self.get_llm()
        llm_with_tools = llm.bind_tools(tools)

        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            prev_str = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(prev_str) > 15000:
                prev_str = prev_str[:15000] + "\n... (tronque)"
            user_content += f"Resultats precedents :\n```json\n{prev_str}\n```\n\n"
        user_content += f"Instruction : {instruction}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Boucle ReAct (max 10 iterations)
        for iteration in range(10):
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                raw = response.content if isinstance(response.content, str) else str(response.content)
                logger.info(f"[{self.agent_id}] ReAct done — {iteration+1} iterations")
                return raw

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                logger.info(f"[{self.agent_id}] Tool: {tool_name}({json.dumps(tool_args, default=str)[:200]})")

                result = "Tool not found"
                for tool in tools:
                    if tool.name == tool_name:
                        try:
                            # MCP tools sont async — essayer ainvoke d'abord, fallback sur invoke
                            if hasattr(tool, 'ainvoke'):
                                import asyncio
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor() as pool:
                                            result = pool.submit(asyncio.run, tool.ainvoke(tool_args)).result()
                                    else:
                                        result = asyncio.run(tool.ainvoke(tool_args))
                                except RuntimeError:
                                    result = asyncio.run(tool.ainvoke(tool_args))
                            else:
                                result = tool.invoke(tool_args)
                            if isinstance(result, (dict, list)):
                                result = json.dumps(result, ensure_ascii=False, default=str)
                            result = str(result)[:5000]
                        except Exception as e:
                            result = f"Tool error: {e}"
                            logger.error(f"[{self.agent_id}] Tool {tool_name} error: {e}")
                        break

                messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))

        last = messages[-1]
        raw = last.content if hasattr(last, "content") and isinstance(last.content, str) else str(last)
        logger.warning(f"[{self.agent_id}] ReAct max iterations reached")
        return raw

    # ── Modes d'execution ────────────────────────────────────────────────────

    def _run_pipeline(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)
        deliverables = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            step_name = step["name"]
            instruction = step["instruction"]
            output_key = step["output_key"]

            logger.info(f"[{self.agent_id}] Pipeline {i}/{len(self.pipeline_steps)}: {step_name}")
            _post_to_discord_sync(channel_id,
                f"⏳ **{self.agent_name}** — etape {i}/{len(self.pipeline_steps)} : **{step_name}**...")

            if self.use_tools:
                raw = self._call_llm_with_tools(instruction, context, deliverables if deliverables else None)
            else:
                raw = self._call_llm(instruction, context, deliverables if deliverables else None)

            try:
                parsed = self.parse_response(raw)
                if output_key in parsed:
                    deliverables[output_key] = parsed[output_key]
                elif "deliverables" in parsed and output_key in parsed["deliverables"]:
                    deliverables[output_key] = parsed["deliverables"][output_key]
                else:
                    deliverables[output_key] = parsed
                logger.info(f"[{self.agent_id}] Etape {step_name}: OK")
                formatted = _format_deliverable(output_key, deliverables[output_key])
                _post_to_discord_sync(channel_id,
                    f"✅ **{self.agent_name}** — **{step_name}** termine\n\n{formatted}")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] Etape {step_name} JSON fail: {e}")
                deliverables[output_key] = {"raw": raw[:8000], "parse_error": str(e)[:100]}
                _post_to_discord_sync(channel_id,
                    f"⚠️ **{self.agent_name}** — **{step_name}** : output brut preserve.")

        _post_to_discord_sync(channel_id,
            f"📋 **{self.agent_name}** termine — {len(self.pipeline_steps)} etapes.\n"
            f"Livrables : {', '.join(deliverables.keys())}")

        return {
            "agent_id": self.agent_id, "status": "complete", "confidence": 0.85,
            "deliverables": deliverables,
            "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)
        _post_to_discord_sync(channel_id, f"⏳ **{self.agent_name}** travaille...")

        if self.use_tools:
            raw = self._call_llm_with_tools(context.get("task", "Produis ton livrable."), context)
        else:
            raw = self._call_llm(context.get("task", "Produis ton livrable."), context)

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            output = {"agent_id": self.agent_id, "status": "complete", "confidence": 0.6,
                      "deliverables": {"raw_output": raw[:8000]}, "parse_note": str(e)[:100]}

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()

        status = output.get("status", "unknown")
        conf = output.get("confidence", "N/A")
        deliverables = output.get("deliverables", {})
        msg = f"✅ **{self.agent_name}** — status={status}, confidence={conf}\n"
        if isinstance(deliverables, dict):
            for key in list(deliverables.keys())[:5]:
                msg += f"\n**{key}** :\n{_format_deliverable(key, deliverables[key])}\n"
        _post_to_discord_sync(channel_id, msg)

        return output

    # ── Point d'entree ───────────────────────────────────────────────────────

    def __call__(self, state):
        try:
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)}, tools={self.use_tools}")
            if self.pipeline_steps:
                output = self._run_pipeline(state)
            else:
                output = self._run_single(state)

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = output
            state["agent_outputs"] = ao
            msgs = list(state.get("messages", []))
            msgs.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = msgs
            logger.info(f"[{self.agent_id}] Done — status={output.get('status')}")
            return state
        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
            channel_id = self._get_channel_id(state)
            _post_to_discord_sync(channel_id, f"❌ **{self.agent_name}** erreur : {str(e)[:300]}")
            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = {"agent_id": self.agent_id, "status": "blocked",
                                  "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
            state["agent_outputs"] = ao
            return state
PYTHON

echo "  -> BaseAgent mis a jour (ReAct + MCP tools)"

# ── 2. Activer use_tools dynamiquement sur les agents avec MCP ───────────────
echo "[2/3] Activation use_tools sur les agents..."

if [ ! -f "${AGENT_ACCESS}" ]; then
    echo "  -> Aucun mapping agent_mcp_access.json trouve."
    echo "     Executez d'abord le script 14 pour configurer les MCP."
    echo "     Les agents fonctionneront sans tools pour l'instant."
else
    # Lire les agents qui ont des MCP configures
    AGENTS_WITH_MCP=$(jq -r 'to_entries[] | select(.value | length > 0) | .key' "${AGENT_ACCESS}" 2>/dev/null || true)

    if [ -n "${AGENTS_WITH_MCP}" ]; then
        for agent_id in ${AGENTS_WITH_MCP}; do
            agent_file="${PROJECT_DIR}/agents/${agent_id}.py"
            [ ! -f "${agent_file}" ] && continue

            # Verifier si use_tools est deja present
            if grep -q "use_tools" "${agent_file}" 2>/dev/null; then
                echo "  -> ${agent_id} : use_tools deja present"
            else
                # Ajouter use_tools = True apres prompt_filename
                if grep -q "prompt_filename" "${agent_file}" 2>/dev/null; then
                    sed -i '/prompt_filename/a\    use_tools = True' "${agent_file}"
                    echo "  -> ${agent_id} : use_tools = True active"
                else
                    echo "  -> ${agent_id} : impossible d'ajouter use_tools (pas de prompt_filename)"
                fi
            fi
        done
    else
        echo "  -> Aucun agent avec MCP configure."
        echo "     Executez le script 14 pour associer des MCP aux agents."
    fi
fi

# ── 3. Rebuild ───────────────────────────────────────────────────────────────
echo "[3/3] Rebuild..."

# Ajouter requests au requirements.txt (pour Discord sync POST)
grep -q "^requests" requirements.txt 2>/dev/null || echo "requests>=2.31.0" >> requirements.txt

docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health 2>/dev/null || echo "error")
echo ""
echo "  Health: ${H}"

echo ""
echo "==========================================="
echo "  Mode ReAct MCP active."
echo ""
echo "  Ce qui a change :"
echo "  - BaseAgent supporte les MCP tools (boucle ReAct max 10 iterations)"
echo "  - Les agents avec MCP configures ont use_tools = True"
echo "  - Si un agent a des tools, le LLM peut les appeler avant de repondre"
echo "  - Si aucun tool disponible, l'agent fonctionne comme avant"
echo ""
echo "  Testez dans Discord :"
echo "  'Cree un repo GitHub pour PerformanceTracker'"
echo "==========================================="
