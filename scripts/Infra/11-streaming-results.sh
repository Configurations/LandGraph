#!/bin/bash
###############################################################################
# Script 11 : Streaming des resultats — chaque etape poste dans Discord
#
# Probleme : les resultats arrivent en un seul bloc a la fin, tronques.
# Fix : chaque etape du pipeline poste dans Discord des qu'elle termine.
#
# Usage : ./11-streaming-results.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 11 : Streaming resultats Discord"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. BaseAgent avec notification par etape ─────────────────────────────────
echo "[1/2] Mise a jour BaseAgent (notification par etape)..."

cat > agents/shared/base_agent.py << 'PYTHON'
"""BaseAgent — Pipeline multi-etapes avec notification Discord par etape."""
import json, logging, os, asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
import aiohttp

load_dotenv()
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def _post_to_discord_sync(channel_id: str, message: str):
    """Post synchrone vers Discord (pour les agents qui tournent dans des threads)."""
    if not DISCORD_BOT_TOKEN or not channel_id:
        return

    import requests
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)]
    for chunk in chunks:
        try:
            resp = requests.post(url, headers=headers, json={"content": chunk}, timeout=10)
            if resp.status_code not in (200, 201):
                logger.error(f"Discord POST failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Discord error: {e}")


def _format_deliverable(key: str, val) -> str:
    """Formate un livrable pour Discord (lisible, pas trop long)."""
    if isinstance(val, str):
        return val[:1500] + "..." if len(val) > 1500 else val
    elif isinstance(val, dict):
        # Essayer un affichage cle par cle
        parts = []
        for k, v in val.items():
            if isinstance(v, str):
                parts.append(f"**{k}** : {v[:300]}{'...' if len(v) > 300 else ''}")
            elif isinstance(v, list):
                parts.append(f"**{k}** : {len(v)} elements")
            elif isinstance(v, dict):
                parts.append(f"**{k}** : {json.dumps(v, ensure_ascii=False, default=str)[:300]}...")
            else:
                parts.append(f"**{k}** : {v}")
        return "\n".join(parts[:10])
    elif isinstance(val, list):
        if len(val) == 0:
            return "(vide)"
        # Afficher les premiers elements
        parts = []
        for item in val[:5]:
            if isinstance(item, dict):
                summary = " | ".join(f"{k}={str(v)[:80]}" for k, v in list(item.items())[:4])
                parts.append(f"  - {summary}")
            else:
                parts.append(f"  - {str(item)[:200]}")
        result = "\n".join(parts)
        if len(val) > 5:
            result += f"\n  ... et {len(val) - 5} de plus"
        return result
    else:
        return str(val)[:500]


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"
    pipeline_steps = []

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()

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

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"):
            return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "user" and len(msg[1]) > 20:
                return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c) > 20:
                    return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target") == self.agent_id:
                    return a.get("task") or ""
                elif hasattr(a, "target") and a.target == self.agent_id:
                    return a.task or ""
        return ""

    def _get_channel_id(self, state):
        """Recupere le channel Discord depuis le state ou les env vars."""
        return state.get("_discord_channel_id", "") or os.getenv("DISCORD_CHANNEL_COMMANDS", "") or os.getenv("DISCORD_CHANNEL_LOGS", "")

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {
                k: {"status": v.get("status"), "keys": list(v.get("deliverables", {}).keys())}
                for k, v in o.items() if v.get("status") == "complete"
            },
        }

    def parse_response(self, raw):
        c = raw.strip()
        if "```json" in c:
            c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c:
            c = c.split("```")[1].split("```")[0].strip()
        return json.loads(c)

    def _call_llm(self, instruction, context, previous_results=None):
        llm = self.get_llm()
        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            # Limiter la taille des resultats precedents pour ne pas depasser le context window
            prev_str = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(prev_str) > 15000:
                prev_str = prev_str[:15000] + "\n... (tronque pour le context window)"
            user_content += f"Resultats des etapes precedentes :\n```json\n{prev_str}\n```\n\n"
        user_content += f"Instruction : {instruction}\n\nReponds UNIQUEMENT en JSON valide."
        response = llm.invoke([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars")
        return raw

    def _run_pipeline(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)
        deliverables = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            step_name = step["name"]
            instruction = step["instruction"]
            output_key = step["output_key"]

            logger.info(f"[{self.agent_id}] Pipeline {i}/{len(self.pipeline_steps)}: {step_name}")

            # Notifier Discord que l'etape demarre
            _post_to_discord_sync(channel_id,
                f"⏳ **{self.agent_name}** — etape {i}/{len(self.pipeline_steps)} : **{step_name}**...")

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

                # Poster le resultat de cette etape dans Discord
                formatted = _format_deliverable(output_key, deliverables[output_key])
                _post_to_discord_sync(channel_id,
                    f"✅ **{self.agent_name}** — **{step_name}** termine\n\n{formatted}")

            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] Etape {step_name} JSON fail: {e}")
                deliverables[output_key] = {"raw": raw[:8000], "parse_error": str(e)[:100]}

                _post_to_discord_sync(channel_id,
                    f"⚠️ **{self.agent_name}** — **{step_name}** : reponse trop longue, output brut preserve.")

        # Resume final
        _post_to_discord_sync(channel_id,
            f"📋 **{self.agent_name}** termine — {len(self.pipeline_steps)} etapes completees.\n"
            f"Livrables : {', '.join(deliverables.keys())}")

        return {
            "agent_id": self.agent_id,
            "status": "complete",
            "confidence": 0.85,
            "deliverables": deliverables,
            "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)

        _post_to_discord_sync(channel_id, f"⏳ **{self.agent_name}** travaille...")

        raw = self._call_llm(context.get("task", "Produis ton livrable."), context)

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_id}] JSON fail: {e}")
            output = {
                "agent_id": self.agent_id, "status": "complete", "confidence": 0.6,
                "deliverables": {"raw_output": raw[:8000]}, "parse_note": str(e)[:100],
            }

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Poster le resultat dans Discord
        status = output.get("status", "unknown")
        conf = output.get("confidence", "N/A")
        deliverables = output.get("deliverables", {})

        msg = f"✅ **{self.agent_name}** termine — status={status}, confidence={conf}\n"
        if isinstance(deliverables, dict):
            for key in list(deliverables.keys())[:5]:
                formatted = _format_deliverable(key, deliverables[key])
                msg += f"\n**{key}** :\n{formatted}\n"

        _post_to_discord_sync(channel_id, msg)

        return output

    def __call__(self, state):
        try:
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)} steps")

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
            ao[self.agent_id] = {
                "agent_id": self.agent_id, "status": "blocked",
                "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = ao
            return state
PYTHON

echo "  -> base_agent.py mis a jour (notification Discord par etape)"

# ── 2. Mettre a jour le gateway pour passer le channel_id dans le state ──────
echo "[2/2] Mise a jour gateway (channel_id dans le state)..."

# Ajouter requests au requirements.txt s'il n'y est pas
grep -q "^requests" requirements.txt || echo "requests>=2.31.0" >> requirements.txt

# Modifier le gateway pour passer le channel_id dans le state des agents
cat > /tmp/gateway_patch.py << 'PATCH'
import re

with open("agents/gateway.py", "r") as f:
    content = f.read()

# Ajouter _discord_channel_id dans le state passe aux agents
old = 'background_tasks.add_task(\n                run_agents_background,'
new = 'result["_discord_channel_id"] = channel_id\n            background_tasks.add_task(\n                run_agents_background,'

if "_discord_channel_id" not in content:
    content = content.replace(
        'background_tasks.add_task(\n                run_agents_background,',
        'result["_discord_channel_id"] = channel_id\n            background_tasks.add_task(\n                run_agents_background,',
    )

    # Aussi simplifier run_agents_background puisque les agents postent eux-memes
    # Remplacer la notification de fin de l'agent par rien (l'agent le fait deja)
    content = content.replace(
        '            # Notifier Discord que l\'agent demarre\n            await post_to_discord(\n                channel_id,\n                f"⏳ **{agent_id}** commence son travail...\\nTache : {task[:200]}"\n            )\n',
        ''
    )

    # Simplifier le resultat (l'agent poste deja)
    old_block = '''            # Formater le resultat pour Discord
            result_msg = f"✅ **{agent_id}** termine — status={status}, confidence={confidence}\\n"

            deliverables = agent_output.get("deliverables", {})
            if isinstance(deliverables, dict):
                result_msg += f"Livrables : {', '.join(deliverables.keys())}\\n"

                for key, val in list(deliverables.items())[:3]:
                    if isinstance(val, str):
                        preview = val[:500] + "..." if len(val) > 500 else val
                    elif isinstance(val, (dict, list)):
                        preview = json.dumps(val, ensure_ascii=False, default=str)[:500] + "..."
                    else:
                        preview = str(val)[:500]
                    result_msg += f"\\n**{key}** :\\n{preview}\\n"

            # Poster dans Discord
            await post_to_discord(channel_id, result_msg)'''

    if old_block in content:
        content = content.replace(old_block, '            # L\'agent poste deja ses resultats dans Discord via BaseAgent')

    with open("agents/gateway.py", "w") as f:
        f.write(content)
    print("Gateway patched")
else:
    print("Gateway already patched")
PATCH

python3 /tmp/gateway_patch.py 2>/dev/null || echo "  -> Patch gateway manuel necessaire (voir ci-dessous)"
rm -f /tmp/gateway_patch.py

echo "  -> Gateway mis a jour"

# ── Rebuild ──────────────────────────────────
echo ""
echo "Rebuild..."
docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health)
echo "Health: ${H}"

echo ""
echo "==========================================="
echo "  Streaming resultats installe."
echo ""
echo "  Comportement :"
echo "  1. Brief -> Orchestrateur repond en 5-10s"
echo "  2. Analyste etape 1/3 PRD -> poste dans Discord"
echo "  3. Analyste etape 2/3 User Stories -> poste"
echo "  4. Analyste etape 3/3 MoSCoW -> poste"
echo "  5. Analyste resume final -> poste"
echo "  6. Avocat etape 1/2 Audit -> poste"
echo "  7. Avocat etape 2/2 Alertes -> poste"
echo "  8. Resume phase Discovery -> poste"
echo "==========================================="
