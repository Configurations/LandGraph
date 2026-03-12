"""Tests pour llm_provider.py — factory LLM, detection de type."""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _clear_cache():
    yield
    from agents.shared import llm_provider as lp
    lp._providers_config = None


@pytest.fixture
def _load_providers(tmp_path):
    """Charge le fichier llm_providers.json depuis une fixture."""
    from tests.conftest import SAMPLE_LLM_PROVIDERS
    p = tmp_path / "llm_providers.json"
    p.write_text(json.dumps(SAMPLE_LLM_PROVIDERS))

    # find_global_file est importee dans _load_providers via lazy import
    with patch("Agents.Shared.team_resolver.find_global_file", return_value=str(p)):
        from agents.shared import llm_provider as lp
        lp._providers_config = None
        yield


# ── get_provider_config ──────────────────────────

class TestGetProviderConfig:
    def test_known_provider(self, _load_providers):
        from agents.shared.llm_provider import get_provider_config
        conf = get_provider_config("claude-sonnet")
        assert conf["type"] == "anthropic"
        assert "model" in conf

    def test_unknown_provider(self, _load_providers):
        from agents.shared.llm_provider import get_provider_config
        conf = get_provider_config("unknown-model")
        assert conf["type"] == "auto"
        assert conf["model"] == "unknown-model"


# ── get_default_provider ─────────────────────────

class TestGetDefaultProvider:
    def test_returns_default(self, _load_providers):
        from agents.shared.llm_provider import get_default_provider
        assert get_default_provider() == "claude-sonnet"


# ── list_providers ───────────────────────────────

class TestListProviders:
    def test_returns_all(self, _load_providers):
        from agents.shared.llm_provider import list_providers
        providers = list_providers()
        assert "claude-sonnet" in providers
        assert "gpt-4o" in providers
        assert "ollama-llama3" in providers


# ── _detect_type ─────────────────────────────────

class TestDetectType:
    def test_claude(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("claude-sonnet-4") == "anthropic"

    def test_gpt(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("gpt-4o") == "openai"

    def test_o1(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("o1-mini") == "openai"

    def test_gemini(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("gemini-pro") == "google"

    def test_mistral(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("mistral-large") == "mistral"

    def test_mixtral(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("mixtral-8x7b") == "mistral"

    def test_deepseek(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("deepseek-chat") == "deepseek"

    def test_kimi(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("kimi-k2") == "moonshot"

    def test_moonshot(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("moonshot-v1") == "moonshot"

    def test_llama(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("llama3") == "ollama"

    def test_qwen(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("qwen2") == "ollama"

    def test_fallback_anthropic(self):
        from agents.shared.llm_provider import _detect_type
        assert _detect_type("totally-unknown") == "anthropic"


# ── create_llm ───────────────────────────────────

class TestCreateLlm:
    def test_calls_correct_factory(self, _load_providers):
        mock_llm = MagicMock()
        mock_factory = MagicMock(return_value=mock_llm)
        with patch.dict("Agents.Shared.llm_provider.FACTORIES", {"anthropic": mock_factory}):
            from agents.shared.llm_provider import create_llm
            result = create_llm("claude-sonnet")
            mock_factory.assert_called_once()
            assert result is mock_llm

    def test_auto_detect(self, _load_providers):
        mock_llm = MagicMock()
        mock_factory = MagicMock(return_value=mock_llm)
        with patch.dict("Agents.Shared.llm_provider.FACTORIES", {"openai": mock_factory}):
            from agents.shared.llm_provider import create_llm
            # "unknown-gpt" not in providers -> auto detect -> "gpt" -> openai
            result = create_llm("unknown-gpt-model")
            mock_factory.assert_called_once()

    def test_default_provider_used(self, _load_providers):
        mock_llm = MagicMock()
        mock_factory = MagicMock(return_value=mock_llm)
        with patch.dict("Agents.Shared.llm_provider.FACTORIES", {"anthropic": mock_factory}):
            from agents.shared.llm_provider import create_llm
            result = create_llm()  # Should use default: claude-sonnet
            assert result is mock_llm
