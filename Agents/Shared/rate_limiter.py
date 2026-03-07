"""Rate Limiter — Throttling generique multi-provider avec retry exponential backoff."""
import logging
import os
import threading
import time
from collections import deque
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("rate_limiter")

# ── Configuration par provider ───────────────
# Format : {provider: {"rpm": requests_per_minute, "tpm": tokens_per_minute}}
# Configurable via env vars : RATELIMIT_<PROVIDER>_RPM, RATELIMIT_<PROVIDER>_TPM

DEFAULT_LIMITS = {
    "anthropic": {"rpm": 25, "tpm": 25000},     # Tier 1 conservateur
    "openai": {"rpm": 60, "tpm": 60000},
    "google": {"rpm": 60, "tpm": 60000},
    "mistral": {"rpm": 60, "tpm": 60000},
    "groq": {"rpm": 30, "tpm": 30000},
    "ollama": {"rpm": 999, "tpm": 999999},       # Local, pas de limite
    "deepseek": {"rpm": 60, "tpm": 60000},
    "default": {"rpm": 30, "tpm": 30000},
}

# Retry config
MAX_RETRIES = 3
INITIAL_BACKOFF = 5      # secondes
BACKOFF_MULTIPLIER = 2   # exponentiel


def _get_limits(provider: str) -> dict:
    """Charge les limites depuis env vars ou defaults."""
    p = provider.upper()
    rpm = int(os.getenv(f"RATELIMIT_{p}_RPM", DEFAULT_LIMITS.get(provider, DEFAULT_LIMITS["default"])["rpm"]))
    tpm = int(os.getenv(f"RATELIMIT_{p}_TPM", DEFAULT_LIMITS.get(provider, DEFAULT_LIMITS["default"])["tpm"]))
    return {"rpm": rpm, "tpm": tpm}


class ProviderThrottle:
    """Throttle pour un provider — sliding window RPM + TPM."""

    def __init__(self, provider: str):
        self.provider = provider
        self.limits = _get_limits(provider)
        self._lock = threading.Lock()
        self._request_times = deque()     # timestamps des requetes (sliding window 60s)
        self._token_usage = deque()       # (timestamp, token_count) pairs
        logger.info(f"Throttle [{provider}]: RPM={self.limits['rpm']}, TPM={self.limits['tpm']}")

    def wait_if_needed(self, estimated_tokens: int = 1000):
        """Bloque si on depasse les limites. Retourne quand c'est safe."""
        with self._lock:
            now = time.time()
            window = now - 60

            # Nettoyer les entrees hors fenetre
            while self._request_times and self._request_times[0] < window:
                self._request_times.popleft()
            while self._token_usage and self._token_usage[0][0] < window:
                self._token_usage.popleft()

            # Verifier RPM
            current_rpm = len(self._request_times)
            if current_rpm >= self.limits["rpm"]:
                oldest = self._request_times[0]
                wait_time = 60 - (now - oldest) + 1
                logger.info(f"Throttle [{self.provider}]: RPM limit ({current_rpm}/{self.limits['rpm']}), waiting {wait_time:.1f}s")
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
                # Re-nettoyer apres attente
                now = time.time()
                window = now - 60
                while self._request_times and self._request_times[0] < window:
                    self._request_times.popleft()

            # Verifier TPM
            current_tpm = sum(t[1] for t in self._token_usage)
            if current_tpm + estimated_tokens > self.limits["tpm"]:
                if self._token_usage:
                    oldest = self._token_usage[0][0]
                    wait_time = 60 - (now - oldest) + 1
                else:
                    wait_time = 5
                logger.info(f"Throttle [{self.provider}]: TPM limit ({current_tpm}/{self.limits['tpm']}), waiting {wait_time:.1f}s")
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()

            # Enregistrer cette requete
            self._request_times.append(time.time())
            self._token_usage.append((time.time(), estimated_tokens))

    def record_usage(self, actual_tokens: int):
        """Met a jour l'usage reel apres la requete (corrige l'estimation)."""
        with self._lock:
            if self._token_usage:
                # Remplacer la derniere estimation par l'usage reel
                ts, _ = self._token_usage.pop()
                self._token_usage.append((ts, actual_tokens))


# ── Singleton par provider ───────────────────
_throttles = {}
_throttles_lock = threading.Lock()


def get_throttle(provider: str) -> ProviderThrottle:
    """Retourne le throttle pour un provider (singleton)."""
    with _throttles_lock:
        if provider not in _throttles:
            _throttles[provider] = ProviderThrottle(provider)
        return _throttles[provider]


def detect_provider(model: str) -> str:
    """Detecte le provider depuis le nom du modele."""
    model_lower = model.lower()
    if "claude" in model_lower or "anthropic" in model_lower:
        return "anthropic"
    elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
        return "openai"
    elif "gemini" in model_lower:
        return "google"
    elif "mistral" in model_lower or "mixtral" in model_lower:
        return "mistral"
    elif "llama" in model_lower or "groq" in model_lower:
        return "groq"
    elif "deepseek" in model_lower:
        return "deepseek"
    elif "ollama" in model_lower:
        return "ollama"
    return "default"


def throttled_invoke(llm, messages, model: str = "", estimated_tokens: int = 1000):
    """
    Appel LLM avec throttling + retry exponential backoff.

    Usage:
        response = throttled_invoke(llm, messages, model="claude-sonnet-4-5-20250929")
    """
    provider = detect_provider(model or getattr(llm, "model", "default"))
    throttle = get_throttle(provider)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        # Attendre si necessaire
        throttle.wait_if_needed(estimated_tokens)

        try:
            response = llm.invoke(messages)

            # Enregistrer l'usage reel si disponible
            if hasattr(response, "usage_metadata"):
                total = getattr(response.usage_metadata, "total_tokens", estimated_tokens)
                throttle.record_usage(total)

            return response

        except Exception as e:
            error_str = str(e)
            last_error = e

            # Rate limit error — retry avec backoff
            if "rate_limit" in error_str.lower() or "429" in error_str:
                wait = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt)
                logger.warning(f"Throttle [{provider}]: Rate limit hit (attempt {attempt + 1}/{MAX_RETRIES + 1}), backoff {wait}s")
                time.sleep(wait)
                continue

            # Overloaded — retry avec backoff
            if "overloaded" in error_str.lower() or "529" in error_str:
                wait = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt)
                logger.warning(f"Throttle [{provider}]: Overloaded (attempt {attempt + 1}/{MAX_RETRIES + 1}), backoff {wait}s")
                time.sleep(wait)
                continue

            # Autre erreur — ne pas retry
            raise

    # Toutes les tentatives echouees
    raise last_error
