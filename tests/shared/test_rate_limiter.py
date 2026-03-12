"""Tests pour rate_limiter.py — logique sliding window + retry."""
import time
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _patch_team_resolver():
    """Empeche les imports team_resolver de toucher le filesystem."""
    with patch("Agents.Shared.rate_limiter.load_dotenv"):
        yield


@pytest.fixture
def throttle():
    """Cree un ProviderThrottle avec des limites connues."""
    with patch("Agents.Shared.rate_limiter._load_throttling", return_value={
        "TEST_KEY": {"rpm": 5, "tpm": 10000},
    }):
        from agents.shared.rate_limiter import ProviderThrottle
        return ProviderThrottle("TEST_KEY")


@pytest.fixture
def throttle_default():
    """Throttle avec limites par defaut (env_key inconnu)."""
    with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}):
        from agents.shared.rate_limiter import ProviderThrottle
        return ProviderThrottle("UNKNOWN_KEY")


# ── Init ─────────────────────────────────────────

class TestThrottleInit:
    def test_known_key_limits(self, throttle):
        assert throttle.limits["rpm"] == 5
        assert throttle.limits["tpm"] == 10000

    def test_unknown_key_defaults(self, throttle_default):
        assert throttle_default.limits["rpm"] == 30
        assert throttle_default.limits["tpm"] == 30000


# ── wait_if_needed ───────────────────────────────

class TestWaitIfNeeded:
    def test_no_wait_under_limit(self, throttle):
        with patch("time.sleep") as mock_sleep:
            throttle.wait_if_needed(100)
            mock_sleep.assert_not_called()

    def test_rpm_limit_triggers_sleep(self, throttle):
        now = time.time()
        # Fill up RPM
        for _ in range(5):
            throttle._request_times.append(now)
            throttle._token_usage.append((now, 100))
        with patch("time.sleep") as mock_sleep, \
             patch("time.time", return_value=now + 1):
            throttle.wait_if_needed(100)
            mock_sleep.assert_called()

    def test_tpm_limit_triggers_sleep(self, throttle):
        now = time.time()
        # Add usage close to TPM limit
        throttle._token_usage.append((now, 9500))
        throttle._request_times.append(now)
        with patch("time.sleep") as mock_sleep:
            throttle.wait_if_needed(1000)
            mock_sleep.assert_called()

    def test_sliding_window_cleanup(self, throttle):
        old = time.time() - 120  # 2 minutes ago, well outside window
        throttle._request_times.append(old)
        throttle._token_usage.append((old, 5000))
        throttle.wait_if_needed(100)
        # Old entries should be cleaned
        assert len([t for t in throttle._request_times if t < time.time() - 60]) == 0


# ── record_usage ─────────────────────────────────

class TestRecordUsage:
    def test_updates_last_entry(self, throttle):
        now = time.time()
        throttle._token_usage.append((now, 1000))
        throttle.record_usage(500)
        assert throttle._token_usage[-1] == (now, 500)

    def test_no_crash_when_empty(self, throttle):
        throttle.record_usage(500)  # Should not raise


# ── get_throttle singleton ───────────────────────

class TestGetThrottle:
    def test_same_key_same_instance(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}):
            from agents.shared.rate_limiter import get_throttle, _throttles
            _throttles.clear()
            t1 = get_throttle("KEY_A")
            t2 = get_throttle("KEY_A")
            assert t1 is t2

    def test_different_keys_different_instances(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}):
            from agents.shared.rate_limiter import get_throttle, _throttles
            _throttles.clear()
            t1 = get_throttle("KEY_A")
            t2 = get_throttle("KEY_B")
            assert t1 is not t2


# ── throttled_invoke ─────────────────────────────

class TestThrottledInvoke:
    def _make_llm(self, response="ok"):
        llm = MagicMock()
        llm.invoke.return_value = response
        return llm

    def test_success(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}), \
             patch("Agents.Shared.rate_limiter._get_env_key_for_provider", return_value="_default"):
            from agents.shared.rate_limiter import throttled_invoke, _throttles
            _throttles.clear()
            llm = self._make_llm("result")
            result = throttled_invoke(llm, ["msg"], provider_name="test")
            assert result == "result"

    def test_rate_limit_retry(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}), \
             patch("Agents.Shared.rate_limiter._get_env_key_for_provider", return_value="_default"), \
             patch("time.sleep"):
            from agents.shared.rate_limiter import throttled_invoke, _throttles
            _throttles.clear()
            llm = MagicMock()
            llm.invoke.side_effect = [Exception("429 rate_limit"), "ok"]
            result = throttled_invoke(llm, ["msg"], provider_name="test")
            assert result == "ok"
            assert llm.invoke.call_count == 2

    def test_non_retryable_raises(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}), \
             patch("Agents.Shared.rate_limiter._get_env_key_for_provider", return_value="_default"):
            from agents.shared.rate_limiter import throttled_invoke, _throttles
            _throttles.clear()
            llm = MagicMock()
            llm.invoke.side_effect = ValueError("bad input")
            with pytest.raises(ValueError, match="bad input"):
                throttled_invoke(llm, ["msg"], provider_name="test")

    def test_max_retries_exceeded(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}), \
             patch("Agents.Shared.rate_limiter._get_env_key_for_provider", return_value="_default"), \
             patch("time.sleep"):
            from agents.shared.rate_limiter import throttled_invoke, MAX_RETRIES, _throttles
            _throttles.clear()
            llm = MagicMock()
            llm.invoke.side_effect = Exception("429 rate_limit")
            with pytest.raises(Exception, match="429"):
                throttled_invoke(llm, ["msg"], provider_name="test")
            assert llm.invoke.call_count == MAX_RETRIES + 1

    def test_records_usage_metadata(self):
        with patch("Agents.Shared.rate_limiter._load_throttling", return_value={}), \
             patch("Agents.Shared.rate_limiter._get_env_key_for_provider", return_value="_default"):
            from agents.shared.rate_limiter import throttled_invoke, _throttles
            _throttles.clear()
            llm = MagicMock()
            response = MagicMock()
            response.usage_metadata.total_tokens = 42
            llm.invoke.return_value = response
            throttled_invoke(llm, ["msg"], provider_name="test")
            # Should not raise — just verify it completes

    def test_backoff_exponential(self):
        from agents.shared.rate_limiter import INITIAL_BACKOFF, BACKOFF_MULTIPLIER, MAX_BACKOFF
        waits = []
        for attempt in range(10):
            w = min(INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt), MAX_BACKOFF)
            waits.append(w)
        assert waits[0] == 5
        assert waits[1] == 10
        assert waits[2] == 20
        assert waits[3] == 40
        assert waits[4] == 80
        assert waits[5] == 120  # capped
        assert waits[6] == 120


# ── _get_env_key_for_provider ────────────────────

class TestGetEnvKeyForProvider:
    def test_known_provider(self, tmp_path):
        from tests.conftest import SAMPLE_LLM_PROVIDERS
        import json
        p = tmp_path / "llm_providers.json"
        p.write_text(json.dumps(SAMPLE_LLM_PROVIDERS))

        with patch("Agents.Shared.team_resolver.find_global_file", return_value=str(p)):
            from agents.shared.rate_limiter import _get_env_key_for_provider
            assert _get_env_key_for_provider("claude-sonnet") == "ANTHROPIC_API_KEY"

    def test_unknown_provider(self, tmp_path):
        from tests.conftest import SAMPLE_LLM_PROVIDERS
        import json
        p = tmp_path / "llm_providers.json"
        p.write_text(json.dumps(SAMPLE_LLM_PROVIDERS))

        with patch("Agents.Shared.team_resolver.find_global_file", return_value=str(p)):
            from agents.shared.rate_limiter import _get_env_key_for_provider
            assert _get_env_key_for_provider("unknown-model") == "_default"

    def test_no_file(self):
        with patch("Agents.Shared.team_resolver.find_global_file", return_value=""):
            from agents.shared.rate_limiter import _get_env_key_for_provider
            assert _get_env_key_for_provider("anything") == "_default"
