"""EventBus — Observabilite centralisee pour ag.flow.

Pattern pub/sub : les composants emettent des events, les handlers les consomment.
Handlers inclus : Langfuse (si configure), Webhooks (si configure), ring buffer (toujours).

Usage :
    from agents.shared.event_bus import bus, Event
    bus.emit(Event("agent_start", agent_id="architect", thread_id="t1", team_id="default"))
"""
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger("event_bus")

# ── Event types ───────────────────────────────────
# agent_start, agent_complete, agent_error
# llm_call_start, llm_call_end
# tool_call
# pipeline_step_start, pipeline_step_end
# human_gate_requested, human_gate_responded
# phase_transition
# agent_dispatch


class Event:
    """Evenement observable."""
    __slots__ = ("event_type", "agent_id", "thread_id", "team_id", "data", "timestamp")

    def __init__(self, event_type: str, *, agent_id: str = "", thread_id: str = "",
                 team_id: str = "", data: dict | None = None):
        self.event_type = event_type
        self.agent_id = agent_id
        self.thread_id = thread_id
        self.team_id = team_id
        self.data = data or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event": self.event_type,
            "agent_id": self.agent_id,
            "thread_id": self.thread_id,
            "team_id": self.team_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class EventBus:
    """Bus d'evenements singleton avec ring buffer et handlers."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = cls()
                    inst._auto_register_handlers()
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        self._handlers: dict[str, list] = {}  # event_type -> [handler_fn]
        self._buffer: deque[Event] = deque(maxlen=2000)

    # ── API publique ──────────────────────────────

    def on(self, event_type: str, handler):
        """Abonne un handler. event_type='*' pour tout recevoir."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(f"Handler registered: {handler.__name__} on '{event_type}'")

    def off(self, event_type: str, handler):
        """Desabonne un handler."""
        lst = self._handlers.get(event_type, [])
        if handler in lst:
            lst.remove(handler)

    def emit(self, event: Event):
        """Emet un event — notifie tous les handlers concernes."""
        self._buffer.append(event)

        # Handlers specifiques au type
        for h in self._handlers.get(event.event_type, []):
            try:
                h(event)
            except Exception as e:
                logger.error(f"Handler error ({h.__name__}) on {event.event_type}: {e}")

        # Handlers wildcard
        for h in self._handlers.get("*", []):
            try:
                h(event)
            except Exception as e:
                logger.error(f"Wildcard handler error ({h.__name__}): {e}")

    def recent(self, n: int = 100, event_type: str = "", agent_id: str = "",
               thread_id: str = "") -> list[dict]:
        """Retourne les N derniers events (filtrables)."""
        events = list(self._buffer)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        if thread_id:
            events = [e for e in events if e.thread_id == thread_id]
        return [e.to_dict() for e in events[-n:]]

    def clear(self):
        """Vide le buffer."""
        self._buffer.clear()

    # ── Auto-registration ─────────────────────────

    def _auto_register_handlers(self):
        """Enregistre automatiquement les handlers disponibles."""
        self._register_langfuse()
        self._register_webhooks()

    def _register_langfuse(self):
        """Langfuse tracing is now handled by CallbackHandler in langfuse_setup.py.
        This event_bus handler is disabled — kept as placeholder for future custom events."""
        logger.info("Langfuse: event_bus handler disabled (tracing via CallbackHandler)")
        return
        # Legacy code below — kept for reference but not executed
        try:  # noqa
            pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
            sk = os.getenv("LANGFUSE_SECRET_KEY", "")
            host = os.getenv("LANGFUSE_HOST", "")
            from langfuse import Langfuse
            client = Langfuse(public_key=pk, secret_key=sk, host=host or "http://localhost:3000")

            # State pour tracker les traces/spans en cours
            _traces = {}  # thread_id:agent_id -> trace
            _spans = {}   # thread_id:agent_id -> span
            _lock = threading.Lock()

            def _trace_key(event: Event) -> str:
                return f"{event.thread_id}:{event.agent_id}"

            def on_agent_start(event: Event):
                key = _trace_key(event)
                trace = client.trace(
                    name=f"agent:{event.agent_id}",
                    metadata={"team_id": event.team_id, "thread_id": event.thread_id},
                    tags=[event.team_id, event.agent_id],
                )
                with _lock:
                    _traces[key] = trace

            def on_agent_complete(event: Event):
                key = _trace_key(event)
                with _lock:
                    trace = _traces.pop(key, None)
                if trace:
                    trace.update(
                        output=event.data.get("status", "complete"),
                        metadata={"deliverables": list(event.data.get("deliverables", {}).keys())},
                    )

            def on_agent_error(event: Event):
                key = _trace_key(event)
                with _lock:
                    trace = _traces.pop(key, None)
                if trace:
                    trace.update(output=f"error: {event.data.get('error', '?')}", level="ERROR")

            def on_llm_start(event: Event):
                key = _trace_key(event)
                with _lock:
                    trace = _traces.get(key)
                if trace:
                    span = trace.span(
                        name=f"llm:{event.data.get('provider', '?')}",
                        input=event.data.get("messages_count", 0),
                        metadata={"model": event.data.get("model", "?")},
                    )
                    with _lock:
                        _spans[key] = span

            def on_llm_end(event: Event):
                key = _trace_key(event)
                with _lock:
                    span = _spans.pop(key, None)
                if span:
                    gen = span.generation(
                        name="llm_call",
                        model=event.data.get("model", "?"),
                        usage={
                            "input": event.data.get("input_tokens", 0),
                            "output": event.data.get("output_tokens", 0),
                            "total": event.data.get("total_tokens", 0),
                        },
                        output=f"{event.data.get('output_chars', 0)} chars",
                    )
                    span.end()

            def on_tool_call(event: Event):
                key = _trace_key(event)
                with _lock:
                    trace = _traces.get(key)
                if trace:
                    trace.span(
                        name=f"tool:{event.data.get('tool_name', '?')}",
                        input=event.data.get("args", ""),
                        output=event.data.get("result_length", 0),
                    ).end()

            self.on("agent_start", on_agent_start)
            self.on("agent_complete", on_agent_complete)
            self.on("agent_error", on_agent_error)
            self.on("llm_call_start", on_llm_start)
            self.on("llm_call_end", on_llm_end)
            self.on("tool_call", on_tool_call)
            logger.info("Langfuse: 6 handlers registered")

        except ImportError:
            logger.warning("Langfuse: package not installed (pip install langfuse)")
        except Exception as e:
            logger.error(f"Langfuse: init failed: {e}")

    def _register_webhooks(self):
        """Enregistre le handler webhooks si config presente."""
        try:
            from agents.shared.team_resolver import find_global_file
            path = find_global_file("webhooks.json")
            if not path:
                logger.info("Webhooks: no webhooks.json found")
                return
            with open(path) as f:
                config = json.load(f)
            webhooks = [w for w in config.get("webhooks", []) if w.get("enabled", True)]
            if not webhooks:
                logger.info("Webhooks: none enabled")
                return
        except Exception as e:
            logger.info(f"Webhooks: config error: {e}")
            return

        import hashlib
        import hmac

        def on_event(event: Event):
            """Dispatch vers les webhooks concernes."""
            import requests
            for wh in webhooks:
                events_filter = wh.get("events", ["*"])
                if "*" not in events_filter and event.event_type not in events_filter:
                    continue
                url = wh.get("url", "")
                if not url:
                    continue
                payload = json.dumps(event.to_dict(), default=str)
                headers = dict(wh.get("headers", {}))
                headers["Content-Type"] = "application/json"
                headers["X-AgFlow-Event"] = event.event_type

                # Signature HMAC si secret configure
                secret = wh.get("secret", "")
                if secret:
                    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
                    headers["X-AgFlow-Signature"] = f"sha256={sig}"

                try:
                    r = requests.post(url, data=payload, headers=headers, timeout=10)
                    if r.status_code >= 400:
                        logger.warning(f"Webhook {wh.get('id','?')} -> {r.status_code}")
                except Exception as e:
                    logger.error(f"Webhook {wh.get('id','?')} error: {e}")

        self.on("*", on_event)
        logger.info(f"Webhooks: {len(webhooks)} webhook(s) registered")


# ── Singleton global ──────────────────────────────
bus = EventBus.get()
