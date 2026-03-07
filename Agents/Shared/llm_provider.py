"""LLM Provider Factory — Charge les providers depuis config/llm_providers.json."""
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("llm_provider")

CPATHS = [
    os.path.join(os.path.dirname(__file__), "..", "config"),
    os.path.join(os.path.dirname(__file__), "config"),
    os.path.join("/app", "config"),
]

_providers_config = None


def _find_file(filename):
    for b in CPATHS:
        p = os.path.join(os.path.abspath(b), filename)
        if os.path.exists(p):
            return p
    return None


def _load_providers():
    global _providers_config
    if _providers_config is None:
        path = _find_file("llm_providers.json")
        if path:
            with open(path) as f:
                _providers_config = json.load(f)
            logger.info(f"LLM providers loaded: {list(_providers_config.get('providers', {}).keys())}")
        else:
            logger.warning("llm_providers.json not found — using defaults")
            _providers_config = {"providers": {}, "default": "claude-sonnet"}
    return _providers_config


def get_provider_config(provider_name: str) -> dict:
    """Retourne la config d'un provider par son nom."""
    config = _load_providers()
    providers = config.get("providers", {})

    if provider_name in providers:
        return providers[provider_name]

    # Fallback : si le nom est un modele direct (backward compat)
    return {"type": "auto", "model": provider_name}


def get_default_provider() -> str:
    """Retourne le nom du provider par defaut."""
    config = _load_providers()
    return config.get("default", "claude-sonnet")


def list_providers() -> dict:
    """Liste tous les providers disponibles."""
    config = _load_providers()
    return config.get("providers", {})


# ── Factories par type ───────────────────────

def _create_anthropic(model: str, temperature: float, max_tokens: int, env_key: str, **kwargs):
    from langchain_anthropic import ChatAnthropic
    api_key = os.getenv(env_key, "")
    return ChatAnthropic(model=model, temperature=temperature, max_tokens=max_tokens, api_key=api_key if api_key else None)


def _create_openai(model: str, temperature: float, max_tokens: int, env_key: str, base_url: str = None, **kwargs):
    from langchain_openai import ChatOpenAI
    params = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "api_key": os.getenv(env_key, "")}
    if base_url:
        params["base_url"] = base_url
    return ChatOpenAI(**params)


def _create_azure(model: str, temperature: float, max_tokens: int, env_key: str,
                   azure_endpoint: str = None, api_version: str = "2024-02-01",
                   azure_deployment: str = None, **kwargs):
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        azure_deployment=azure_deployment or model,
        api_version=api_version,
        azure_endpoint=azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        api_key=os.getenv(env_key, ""),
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_google(model: str, temperature: float, max_tokens: int, env_key: str, **kwargs):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model, temperature=temperature, max_output_tokens=max_tokens,
        google_api_key=os.getenv(env_key, ""),
    )


def _create_mistral(model: str, temperature: float, max_tokens: int, env_key: str, **kwargs):
    from langchain_mistralai import ChatMistralAI
    return ChatMistralAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""))


def _create_ollama(model: str, temperature: float, max_tokens: int, base_url: str = None, **kwargs):
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=model, temperature=temperature, num_predict=max_tokens,
        base_url=base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )


def _create_groq(model: str, temperature: float, max_tokens: int, env_key: str, **kwargs):
    from langchain_groq import ChatGroq
    return ChatGroq(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""))


def _create_deepseek(model: str, temperature: float, max_tokens: int, env_key: str, **kwargs):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model, temperature=temperature, max_tokens=max_tokens,
        api_key=os.getenv(env_key, ""), base_url="https://api.deepseek.com",
    )


# Registry des factories — extensible
FACTORIES = {
    "anthropic": _create_anthropic,
    "openai": _create_openai,
    "azure": _create_azure,
    "google": _create_google,
    "mistral": _create_mistral,
    "ollama": _create_ollama,
    "groq": _create_groq,
    "deepseek": _create_deepseek,
}


def _detect_type(model: str) -> str:
    """Auto-detecte le type depuis le nom du modele (fallback)."""
    m = model.lower()
    if "claude" in m: return "anthropic"
    if "gpt" in m or "o1-" in m or "o3-" in m: return "openai"
    if "gemini" in m: return "google"
    if "mistral" in m or "mixtral" in m: return "mistral"
    if "deepseek" in m: return "deepseek"
    if "llama" in m or "qwen" in m or "phi" in m: return "ollama"
    return "anthropic"


def create_llm(provider_name: str = None, temperature: float = 0.3, max_tokens: int = 32768):
    """
    Cree une instance LLM depuis le nom du provider (defini dans llm_providers.json).

    Usage:
        llm = create_llm("claude-sonnet")
        llm = create_llm("gpt-4o-azure")
        llm = create_llm("llama3-local")
    """
    if not provider_name:
        provider_name = get_default_provider()

    conf = get_provider_config(provider_name)
    provider_type = conf.get("type", "auto")
    model = conf.get("model", provider_name)

    # Auto-detect si type pas specifie
    if provider_type == "auto":
        provider_type = _detect_type(model)

    factory = FACTORIES.get(provider_type)
    if not factory:
        logger.error(f"Provider type inconnu: {provider_type}. Fallback anthropic.")
        factory = _create_anthropic

    logger.info(f"LLM: {provider_name} -> {provider_type}/{model}")

    # Filtrer les cles deja passees explicitement ou non pertinentes pour la factory
    skip_keys = {"type", "model", "description"}
    extra = {k: v for k, v in conf.items() if k not in skip_keys}

    return factory(model=model, temperature=temperature, max_tokens=max_tokens, **extra)
