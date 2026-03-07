"""BaseAgent — Pipeline + ReAct MCP tools + Discord streaming."""
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
            logger.error(f"Discord: {e}")


def _format_deliverable(key, val):
    if isinstance(val, str):
        return val[:1500] + "..." if len(val) > 1500 else val
    elif isinstance(val, dict):
        parts = []
        for k, v in list(val.items())[:10]:
            if isinstance(v, str):
                parts.append(f"**{k}** : {v[:300]}{'...' if len(v) > 300 else ''}")
            elif isinstance(v, list):
                parts.append(f"**{k}** : {len(v)} elements")
            else:
                parts.append(f"**{k}** : {str(v)[:200]}")
        return "\n".join(parts)
    elif isinstance(val, list):
        parts = []
        for item in val[:5]:
            if isinstance(item, dict):
                parts.append("  - " + " | ".join(f"{k}={str(v)[:80]}" for k, v in list(item.items())[:4]))
            else:
                parts.append(f"  - {str(item)[:200]}")
        result = "\n".join(parts)
        if len(val) > 5:
            result += f"\n  ... et {len(val) - 5} de plus"
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
    requires_approval = False

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
        if self._tools is None and self.use_tools:
            try:
                from agents.shared.mcp_client import get_tools_for_agent
                self._tools = get_tools_for_agent(self.agent_id)
                if self._tools:
                    logger.info(f"[{self.agent_id}] {len(self._tools)} MCP tools loaded")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] MCP tools failed: {e}")
                self._tools = []

            # Ajouter le tool ask_human pour la boucle conversationnelle
            try:
                self._tools = list(self._tools or [])
                self._tools.append(self._create_ask_human_tool())
                logger.info(f"[{self.agent_id}] ask_human tool added")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] ask_human tool failed: {e}")

        return self._tools or []

    def _create_ask_human_tool(self):
        """Cree un tool LangChain pour poser des questions aux humains."""
        from langchain_core.tools import tool
        agent_name = self.agent_name

        @tool
        def ask_human(question: str, context: str = "") -> str:
            """Pose une question a l'humain via Discord et attend sa reponse.
            Utilise ce tool quand tu as besoin d'une clarification, d'un choix,
            ou d'une information que seul l'humain peut fournir.
            Args:
                question: La question a poser
                context: Contexte optionnel pour aider l'humain a repondre
            Returns:
                La reponse de l'humain ou un message de timeout
            """
            from agents.shared.agent_conversation import ask_human_sync
            # Recuperer le channel_id depuis les env vars
            channel_id = os.getenv("DISCORD_CHANNEL_COMMANDS", "")
            result = ask_human_sync(agent_name, question, channel_id, context, timeout=300)
            if result["answered"]:
                return f"Reponse de {result['author']}: {result['response']}"
            elif result["timed_out"]:
                return "Pas de reponse (timeout 5 min). Continue avec ton meilleur jugement."
            else:
                return "Erreur de communication. Continue avec ton meilleur jugement."

        return ask_human

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

    # ── Appels LLM ───────────────────────────────────────────────────────────

    def _call_llm(self, instruction, context, previous_results=None):
        from agents.shared.rate_limiter import throttled_invoke
        llm = self.get_llm()
        uc = f"Contexte:\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            ps = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(ps) > 15000:
                ps = ps[:15000] + "\n...(tronque)"
            uc += f"Precedents:\n```json\n{ps}\n```\n\n"
        uc += f"Instruction: {instruction}\n\nReponds UNIQUEMENT en JSON valide."
        msgs = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": uc},
        ]
        r = throttled_invoke(llm, msgs, model=self.model)
        raw = r.content if isinstance(r.content, str) else str(r.content)
        logger.info(f"[{self.agent_id}] LLM: {len(raw)}c")
        return raw

    def _call_llm_with_tools(self, instruction, context, previous_results=None):
        from agents.shared.rate_limiter import throttled_invoke
        tools = self.get_tools()
        if not tools:
            return self._call_llm(instruction, context, previous_results)

        llm = self.get_llm()
        llm_t = llm.bind_tools(tools)

        uc = f"Contexte:\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            ps = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(ps) > 15000:
                ps = ps[:15000] + "\n...(tronque)"
            uc += f"Precedents:\n```json\n{ps}\n```\n\n"
        uc += f"Instruction: {instruction}"

        msgs = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": uc},
        ]

        for iteration in range(10):
            resp = throttled_invoke(llm_t, msgs, model=self.model)
            msgs.append(resp)

            if not resp.tool_calls:
                raw = resp.content if isinstance(resp.content, str) else str(resp.content)
                logger.info(f"[{self.agent_id}] ReAct done — {iteration + 1} iters")
                return raw

            for tc in resp.tool_calls:
                tn, ta = tc["name"], tc["args"]
                logger.info(f"[{self.agent_id}] Tool: {tn}({json.dumps(ta, default=str)[:200]})")

                result = "Tool not found"
                for t in tools:
                    if t.name == tn:
                        try:
                            if hasattr(t, "ainvoke"):
                                import asyncio
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor() as pool:
                                            result = pool.submit(asyncio.run, t.ainvoke(ta)).result()
                                    else:
                                        result = asyncio.run(t.ainvoke(ta))
                                except RuntimeError:
                                    result = asyncio.run(t.ainvoke(ta))
                            else:
                                result = t.invoke(ta)
                            if isinstance(result, (dict, list)):
                                result = json.dumps(result, ensure_ascii=False, default=str)
                            result = str(result)[:5000]
                        except Exception as e:
                            result = f"Tool error: {e}"
                            logger.error(f"[{self.agent_id}] Tool {tn}: {e}")
                        break

                msgs.append(ToolMessage(content=result, tool_call_id=tc["id"]))

        last = msgs[-1]
        logger.warning(f"[{self.agent_id}] ReAct max iters")
        return last.content if hasattr(last, "content") and isinstance(last.content, str) else str(last)

    # ── Modes d'execution ────────────────────────────────────────────────────

    def _run_pipeline(self, state):
        ctx = self.build_context(state)
        ch = self._get_channel_id(state)
        dl = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            sn, ins, ok = step["name"], step["instruction"], step["output_key"]
            logger.info(f"[{self.agent_id}] Pipeline {i}/{len(self.pipeline_steps)}: {sn}")
            _post_to_discord_sync(ch, f"⏳ **{self.agent_name}** — etape {i}/{len(self.pipeline_steps)} : **{sn}**...")

            if self.use_tools:
                raw = self._call_llm_with_tools(ins, ctx, dl if dl else None)
            else:
                raw = self._call_llm(ins, ctx, dl if dl else None)

            try:
                parsed = self.parse_response(raw)
                if ok in parsed:
                    dl[ok] = parsed[ok]
                elif "deliverables" in parsed and ok in parsed["deliverables"]:
                    dl[ok] = parsed["deliverables"][ok]
                else:
                    dl[ok] = parsed
                logger.info(f"[{self.agent_id}] {sn}: OK")
                _post_to_discord_sync(ch, f"✅ **{self.agent_name}** — **{sn}** termine\n\n{_format_deliverable(ok, dl[ok])}")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] {sn} JSON fail: {e}")
                dl[ok] = {"raw": raw[:8000], "parse_error": str(e)[:100]}
                _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** — **{sn}** : output brut preserve.")

        _post_to_discord_sync(ch, f"📋 **{self.agent_name}** — {len(self.pipeline_steps)} etapes terminees ✅")
        return {
            "agent_id": self.agent_id, "status": "complete", "confidence": 0.85,
            "deliverables": dl, "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        ctx = self.build_context(state)
        ch = self._get_channel_id(state)

        if self.use_tools:
            raw = self._call_llm_with_tools(ctx.get("task", "Produis ton livrable."), ctx)
        else:
            raw = self._call_llm(ctx.get("task", "Produis ton livrable."), ctx)

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            output = {
                "agent_id": self.agent_id, "status": "complete", "confidence": 0.6,
                "deliverables": {"raw_output": raw[:8000]}, "parse_note": str(e)[:100],
            }

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()

        s = output.get("status", "unknown")
        d = output.get("deliverables", {})

        if s == "complete":
            msg = f"✅ **{self.agent_name}** termine\n"
            if isinstance(d, dict) and d:
                for k in list(d.keys())[:5]:
                    msg += f"\n**{k}** :\n{_format_deliverable(k, d[k])}\n"
            _post_to_discord_sync(ch, msg)
        elif s == "blocked":
            reason = output.get("error", output.get("deliverables", {}).get("raw_output", "")[:300])
            _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** bloque : {reason[:500]}")
        else:
            _post_to_discord_sync(ch, f"ℹ️ **{self.agent_name}** — status: {s}")

        return output

    # ── Point d'entree ───────────────────────────────────────────────────────

    def __call__(self, state):
        try:
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)}, tools={self.use_tools}")
            output = self._run_pipeline(state) if self.pipeline_steps else self._run_single(state)

            # Human gate — demander validation si configure
            if self.requires_approval and output.get("status") == "complete":
                ch = self._get_channel_id(state)
                logger.info(f"[{self.agent_id}] Requesting human approval...")
                _post_to_discord_sync(ch, f"🔒 **{self.agent_name}** a termine. Validation en attente dans #human-review...")

                try:
                    from agents.shared.human_gate import request_approval_sync
                    deliverables = output.get("deliverables", {})
                    summary = f"{self.agent_name} a produit : {', '.join(deliverables.keys())}"
                    details = ""
                    for k in list(deliverables.keys())[:3]:
                        details += f"**{k}** : {_format_deliverable(k, deliverables[k])[:500]}\n\n"

                    approval = request_approval_sync(
                        agent_name=self.agent_name,
                        summary=summary,
                        details=details,
                        timeout=300,
                    )

                    if approval["approved"]:
                        output["human_approval"] = {"status": "approved", "reviewer": approval["reviewer"]}
                        _post_to_discord_sync(ch, f"✅ **{self.agent_name}** approuve par {approval['reviewer']}")
                        logger.info(f"[{self.agent_id}] Approved by {approval['reviewer']}")
                    elif approval["timed_out"]:
                        output["human_approval"] = {"status": "timeout"}
                        output["status"] = "pending_review"
                        _post_to_discord_sync(ch, f"⏰ **{self.agent_name}** — timeout, en attente de review")
                        logger.warning(f"[{self.agent_id}] Approval timeout")
                    else:
                        output["human_approval"] = {"status": "revision", "feedback": approval["response"], "reviewer": approval["reviewer"]}
                        output["status"] = "revision_requested"
                        _post_to_discord_sync(ch, f"🔄 **{self.agent_name}** — revision demandee par {approval['reviewer']}: {approval['response'][:200]}")
                        logger.info(f"[{self.agent_id}] Revision requested: {approval['response'][:100]}")
                except Exception as e:
                    logger.error(f"[{self.agent_id}] Human gate error: {e}")
                    output["human_approval"] = {"status": "error", "detail": str(e)}

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
            ch = self._get_channel_id(state)
            _post_to_discord_sync(ch, f"❌ **{self.agent_name}** erreur : {str(e)[:300]}")

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = {
                "agent_id": self.agent_id, "status": "blocked",
                "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = ao
            return state
