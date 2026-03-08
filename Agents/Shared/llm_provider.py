"""LLM Provider Factory — Charge les providers via team_resolver."""
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("llm_provider")

_providers_config = None


def _load_providers():
    global _providers_config
    if _providers_config is None:
        from agents.shared.team_resolver import find_global_file
        import json
        path = find_global_file("llm_providers.json")
        if path:
            with open(path) as f:
                _providers_config = json.load(f)
            logger.info(f"LLM providers loaded: {list(_providers_config.get('providers', {}).keys())}")
        else:
            logger.warning("llm_providers.json not found")
            _providers_config = {"providers": {}, "default": "claude-sonnet"}
    return _providers_config


def get_provider_config(provider_name: str) -> dict:
    providers = _load_providers().get("providers", {})
    if provider_name in providers:
        return providers[provider_name]
    return {"type": "auto", "model": provider_name}


def get_default_provider() -> str:
    return _load_providers().get("default", "claude-sonnet")


def list_providers() -> dict:
    return _load_providers().get("providers", {})


def _create_anthropic(model, temperature, max_tokens, env_key="", **kw):
    from langchain_anthropic import ChatAnthropic
    k = os.getenv(env_key, "")
    return ChatAnthropic(model=model, temperature=temperature, max_tokens=max_tokens, api_key=k if k else None)

def _create_openai(model, temperature, max_tokens, env_key="", base_url=None, **kw):
    from langchain_openai import ChatOpenAI
    p = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "api_key": os.getenv(env_key, "")}
    if base_url: p["base_url"] = base_url
    return ChatOpenAI(**p)

def _create_azure(model, temperature, max_tokens, env_key="", azure_endpoint="", api_version="2024-02-01", azure_deployment=None, **kw):
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(azure_deployment=azure_deployment or model, api_version=api_version,
        azure_endpoint=azure_endpoint, api_key=os.getenv(env_key, ""), temperature=temperature, max_tokens=max_tokens)

def _create_google(model, temperature, max_tokens, env_key="", **kw):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=model, temperature=temperature, max_output_tokens=max_tokens, google_api_key=os.getenv(env_key, ""))

def _create_mistral(model, temperature, max_tokens, env_key="", **kw):
    from langchain_mistralai import ChatMistralAI
    return ChatMistralAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""))

def _create_ollama(model, temperature, max_tokens, base_url=None, **kw):
    from langchain_ollama import ChatOllama
    return ChatOllama(model=model, temperature=temperature, num_predict=max_tokens, base_url=base_url or "http://localhost:11434")

def _create_groq(model, temperature, max_tokens, env_key="", **kw):
    from langchain_groq import ChatGroq
    return ChatGroq(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""))

def _create_deepseek(model, temperature, max_tokens, env_key="", **kw):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""), base_url="https://api.deepseek.com")

def _create_moonshot(model, temperature, max_tokens, env_key="", base_url=None, **kw):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=temperature, max_tokens=max_tokens, api_key=os.getenv(env_key, ""), base_url=base_url or "https://api.moonshot.cn/v1")

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
    if not provider_name: provider_name = get_default_provider()
    conf = get_provider_config(provider_name)
    provider_type = conf.get("type", "auto")
    model = conf.get("model", provider_name)
    if provider_type == "auto": provider_type = _detect_type(model)
    factory = FACTORIES.get(provider_type, _create_anthropic)
    logger.info(f"LLM: {provider_name} -> {provider_type}/{model}")
    skip = {"type", "model", "description"}
    extra = {k: v for k, v in conf.items() if k not in skip}
    return factory(model=model, temperature=temperature, max_tokens=max_tokens, **extra)
