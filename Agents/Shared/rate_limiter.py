"""Rate Limiter — Throttling par env_key via team_resolver."""
import json
import logging
import os
import threading
import time
from collections import deque
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("rate_limiter")

MAX_RETRIES = 20
INITIAL_BACKOFF = 5
BACKOFF_MULTIPLIER = 2
MAX_BACKOFF = 120

_throttling_config = None


def _load_throttling():
    global _throttling_config
    if _throttling_config is None:
        from agents.shared.team_resolver import find_global_file
        path = find_global_file("llm_providers.json")
        if path:
            with open(path) as f:
                data = json.load(f)
            _throttling_config = data.get("throttling", {})
            logger.info(f"Throttling loaded: {list(_throttling_config.keys())}")
        else:
            _throttling_config = {}
    return _throttling_config


def _get_limits(env_key: str) -> dict:
    config = _load_throttling()
    return config.get(env_key, {"rpm": 30, "tpm": 30000})


def _get_env_key_for_provider(provider_name: str) -> str:
    from agents.shared.team_resolver import find_global_file
    path = find_global_file("llm_providers.json")
    if not path:
        return "_default"
    with open(path) as f:
        data = json.load(f)
    providers = data.get("providers", {})
    if provider_name in providers:
        return providers[provider_name].get("env_key", "_default")
    for pid, conf in providers.items():
        if conf.get("model") == provider_name or conf.get("type") == provider_name:
            return conf.get("env_key", "_default")
    return "_default"


class ProviderThrottle:
    def __init__(self, env_key: str):
        self.env_key = env_key
        self.limits = _get_limits(env_key)
        self._lock = threading.Lock()
        self._request_times = deque()
        self._token_usage = deque()
        logger.info(f"Throttle [{env_key}]: RPM={self.limits['rpm']}, TPM={self.limits['tpm']}")

    def wait_if_needed(self, estimated_tokens: int = 1000):
        with self._lock:
            now = time.time()
            window = now - 60
            while self._request_times and self._request_times[0] < window:
                self._request_times.popleft()
            while self._token_usage and self._token_usage[0][0] < window:
                self._token_usage.popleft()
            current_rpm = len(self._request_times)
            if current_rpm >= self.limits["rpm"]:
                oldest = self._request_times[0]
                wait_time = 60 - (now - oldest) + 1
                logger.info(f"Throttle [{self.env_key}]: RPM limit, wait {wait_time:.1f}s")
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
                now = time.time()
                while self._request_times and self._request_times[0] < now - 60:
                    self._request_times.popleft()
            current_tpm = sum(t[1] for t in self._token_usage)
            if current_tpm + estimated_tokens > self.limits["tpm"]:
                wait_time = (60 - (now - self._token_usage[0][0]) + 1) if self._token_usage else 5
                logger.info(f"Throttle [{self.env_key}]: TPM limit, wait {wait_time:.1f}s")
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
            self._request_times.append(time.time())
            self._token_usage.append((time.time(), estimated_tokens))

    def record_usage(self, actual_tokens: int):
        with self._lock:
            if self._token_usage:
                ts, _ = self._token_usage.pop()
                self._token_usage.append((ts, actual_tokens))


_throttles = {}
_throttles_lock = threading.Lock()


def get_throttle(env_key: str) -> ProviderThrottle:
    with _throttles_lock:
        if env_key not in _throttles:
            _throttles[env_key] = ProviderThrottle(env_key)
        return _throttles[env_key]


def throttled_invoke(llm, messages, provider_name: str = "", model: str = "", estimated_tokens: int = 1000, callbacks: list | None = None):
    env_key = "_default"
    if provider_name:
        env_key = _get_env_key_for_provider(provider_name)
    elif model:
        env_key = _get_env_key_for_provider(model)

    throttle = get_throttle(env_key)
    last_error = None
    invoke_kwargs = {"config": {"callbacks": callbacks}} if callbacks else {}

    for attempt in range(MAX_RETRIES + 1):
        throttle.wait_if_needed(estimated_tokens)
        try:
            response = llm.invoke(messages, **invoke_kwargs)
            if hasattr(response, "usage_metadata"):
                total = getattr(response.usage_metadata, "total_tokens", estimated_tokens)
                throttle.record_usage(total)
            return response
        except Exception as e:
            error_str = str(e)
            last_error = e
            if "rate_limit" in error_str.lower() or "429" in error_str:
                wait = min(INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt), MAX_BACKOFF)
                logger.warning(f"Throttle [{env_key}]: Rate limit (attempt {attempt + 1}/{MAX_RETRIES + 1}), backoff {wait}s")
                time.sleep(wait)
                continue
            if "overloaded" in error_str.lower() or "529" in error_str:
                wait = min(INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt), MAX_BACKOFF)
                logger.warning(f"Throttle [{env_key}]: Overloaded (attempt {attempt + 1}/{MAX_RETRIES + 1}), backoff {wait}s")
                time.sleep(wait)
                continue
            raise
    raise last_error
