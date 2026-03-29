"""LLM Provider Factory — Charge les providers via team_resolver."""
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("llm_provider")

_providers_path = None  # cached path only, not content


def _load_providers():
    """Re-read llm_providers.json on every call for hot-reload support."""
    global _providers_path
    import json
    if _providers_path is None:
        from agents.shared.team_resolver import find_global_file
        _providers_path = find_global_file("llm_providers.json") or ""
    if not _providers_path:
        logger.warning("llm_providers.json not found")
        return {"providers": {}, "default": "claude-sonnet"}
    with open(_providers_path) as f:
        return json.load(f)


def get_provider_config(provider_name: str) -> dict:
    providers = _load_providers().get("providers", {})
    if provider_name in providers:
        return providers[provider_name]
    return {"type": "auto", "model": provider_name}


def get_default_provider() -> str:
    return _load_providers().get("default", "claude-sonnet")


def list_providers() -> dict:
    return _load_providers().get("providers", {})


def _resolve_api_key(env_key: str = "", api_key: str = "", **_kw) -> str:
    """Resolve API key: explicit api_key in config takes priority, then env var."""
    if api_key:
        return api_key
    return os.getenv(env_key, "") if env_key else ""


def _create_anthropic(model, temperature, max_tokens, env_key="", api_key="", **kw):
    from langchain_anthropic import ChatAnthropic
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    src = "config" if api_key else env_key
    logger.info(f"LLM Anthropic: source={src}, key={'***' + k[-4:] if k and len(k) > 4 else 'MISSING'}")
    return ChatAnthropic(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k if k else None)

def _create_openai(model, temperature, max_tokens, env_key="", api_key="", base_url=None, **kw):
    from langchain_openai import ChatOpenAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    p = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "api_key": k}
    if base_url: p["base_url"] = base_url
    return ChatOpenAI(**p)

def _create_azure(model, temperature, max_tokens, env_key="", api_key="", azure_endpoint="", api_version="2024-02-01", azure_deployment=None, **kw):
    from langchain_openai import AzureChatOpenAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return AzureChatOpenAI(azure_deployment=azure_deployment or model, api_version=api_version,
        azure_endpoint=azure_endpoint, api_key=k, temperature=temperature, max_tokens=max_tokens)

def _create_google(model, temperature, max_tokens, env_key="", api_key="", **kw):
    from langchain_google_genai import ChatGoogleGenerativeAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return ChatGoogleGenerativeAI(model=model, temperature=temperature, max_output_tokens=max_tokens, google_api_key=k)

def _create_mistral(model, temperature, max_tokens, env_key="", api_key="", **kw):
    from langchain_mistralai import ChatMistralAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return ChatMistralAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k)

def _create_ollama(model, temperature, max_tokens, base_url=None, **kw):
    from langchain_ollama import ChatOllama
    return ChatOllama(model=model, temperature=temperature, num_predict=max_tokens, base_url=base_url or "http://localhost:11434")

def _create_groq(model, temperature, max_tokens, env_key="", api_key="", **kw):
    from langchain_groq import ChatGroq
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return ChatGroq(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k)

def _create_deepseek(model, temperature, max_tokens, env_key="", api_key="", **kw):
    from langchain_openai import ChatOpenAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k, base_url="https://api.deepseek.com")

def _create_moonshot(model, temperature, max_tokens, env_key="", api_key="", base_url=None, **kw):
    from langchain_openai import ChatOpenAI
    k = _resolve_api_key(env_key=env_key, api_key=api_key)
    return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k, base_url=base_url or "https://api.moonshot.cn/v1")

FACTORIES = {
    "anthropic": _create_anthropic, "openai": _create_openai, "azure": _create_azure,
    "google": _create_google, "mistral": _create_mistral, "ollama": _create_ollama,
    "groq": _create_groq, "deepseek": _create_deepseek, "moonshot": _create_moonshot,
}

def _detect_type(model):
    m = model.lower()
    if "claude" in m: return "anthropic"
    if "gpt" in m or "o1-" in m or "o3-" in m: return "openai"
    if "gemini" in m: return "google"
    if "mistral" in m or "mixtral" in m: return "mistral"
    if "deepseek" in m: return "deepseek"
    if "kimi" in m or "moonshot" in m: return "moonshot"
    if "llama" in m or "qwen" in m or "phi" in m: return "ollama"
    return "anthropic"

def create_llm(provider_name=None, temperature=0.3, max_tokens=32768):
    resolved = provider_name or get_default_provider()
    conf = get_provider_config(resolved)
    provider_type = conf.get("type", "auto")
    model = conf.get("model", resolved)
    if provider_type == "auto": provider_type = _detect_type(model)
    factory = FACTORIES.get(provider_type, _create_anthropic)
    env_key = conf.get("env_key", "")
    logger.info(f"LLM: {resolved} -> {provider_type}/{model} (env_key={env_key})")
    skip = {"type", "model", "description"}
    extra = {k: v for k, v in conf.items() if k not in skip}
    llm = factory(model=model, temperature=temperature, max_tokens=max_tokens, **extra)
    llm._provider_name = resolved
    return llm
