"""Tests pour event_bus.py — pub/sub, ring buffer, filtres."""
import pytest
from agents.shared.event_bus import Event, EventBus


@pytest.fixture
def bus():
    """Instance fraiche (pas le singleton)."""
    return EventBus()


# ── Event ────────────────────────────────────────

class TestEvent:
    def test_to_dict(self):
        e = Event("agent_start", agent_id="arch", thread_id="t1", team_id="team1")
        d = e.to_dict()
        assert d["event"] == "agent_start"
        assert d["agent_id"] == "arch"
        assert d["thread_id"] == "t1"
        assert d["team_id"] == "team1"
        assert "timestamp" in d

    def test_timestamp_iso(self):
        e = Event("test")
        assert "T" in e.timestamp  # ISO format

    def test_default_data_empty(self):
        e = Event("test")
        assert e.data == {}

    def test_custom_data(self):
        e = Event("test", data={"key": "value"})
        assert e.data["key"] == "value"


# ── EventBus.on / emit ──────────────────────────

class TestEmit:
    def test_handler_called(self, bus):
        received = []
        bus.on("agent_start", lambda e: received.append(e))
        bus.emit(Event("agent_start", agent_id="test"))
        assert len(received) == 1
        assert received[0].agent_id == "test"

    def test_wildcard_handler(self, bus):
        received = []
        bus.on("*", lambda e: received.append(e))
        bus.emit(Event("agent_start"))
        bus.emit(Event("agent_complete"))
        assert len(received) == 2

    def test_specific_and_wildcard_both_called(self, bus):
        specific = []
        wildcard = []
        bus.on("agent_start", lambda e: specific.append(e))
        bus.on("*", lambda e: wildcard.append(e))
        bus.emit(Event("agent_start"))
        assert len(specific) == 1
        assert len(wildcard) == 1

    def test_handler_for_different_type_not_called(self, bus):
        received = []
        bus.on("agent_start", lambda e: received.append(e))
        bus.emit(Event("agent_complete"))
        assert len(received) == 0

    def test_handler_error_does_not_crash(self, bus):
        def bad_handler(e):
            raise ValueError("boom")

        bus.on("test", bad_handler)
        bus.emit(Event("test"))  # Should not raise


# ── EventBus.off ─────────────────────────────────

class TestOff:
    def test_removes_handler(self, bus):
        received = []
        handler = lambda e: received.append(e)
        bus.on("test", handler)
        bus.off("test", handler)
        bus.emit(Event("test"))
        assert len(received) == 0

    def test_off_nonexistent_no_crash(self, bus):
        bus.off("test", lambda e: None)  # Should not raise


# ── Ring buffer ──────────────────────────────────

class TestBuffer:
    def test_stores_events(self, bus):
        bus.emit(Event("test"))
        assert len(bus._buffer) == 1

    def test_maxlen_2000(self, bus):
        for i in range(2500):
            bus.emit(Event("test", data={"i": i}))
        assert len(bus._buffer) == 2000

    def test_clear(self, bus):
        bus.emit(Event("test"))
        bus.clear()
        assert len(bus._buffer) == 0


# ── recent ───────────────────────────────────────

class TestRecent:
    def test_default_100(self, bus):
        for _ in range(150):
            bus.emit(Event("test"))
        assert len(bus.recent()) == 100

    def test_custom_n(self, bus):
        for _ in range(20):
            bus.emit(Event("test"))
        assert len(bus.recent(n=5)) == 5

    def test_filter_by_type(self, bus):
        bus.emit(Event("agent_start"))
        bus.emit(Event("agent_complete"))
        bus.emit(Event("agent_start"))
        result = bus.recent(event_type="agent_start")
        assert len(result) == 2

    def test_filter_by_agent(self, bus):
        bus.emit(Event("test", agent_id="a1"))
        bus.emit(Event("test", agent_id="a2"))
        result = bus.recent(agent_id="a1")
        assert len(result) == 1

    def test_filter_by_thread(self, bus):
        bus.emit(Event("test", thread_id="t1"))
        bus.emit(Event("test", thread_id="t2"))
        result = bus.recent(thread_id="t1")
        assert len(result) == 1

    def test_returns_dicts(self, bus):
        bus.emit(Event("test"))
        result = bus.recent()
        assert isinstance(result[0], dict)
        assert "event" in result[0]


# ── Singleton ────────────────────────────────────

class TestSingleton:
    def test_get_returns_same(self):
        EventBus._instance = None
        b1 = EventBus.get()
        b2 = EventBus.get()
        assert b1 is b2
        EventBus._instance = None  # cleanup
