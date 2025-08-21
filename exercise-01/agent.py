"""
agent.py — Clean reference implementation for Exercise 01: "LLM Weather Agent"

This module demonstrates a production-minded refactor of a tiny service that:
1) Fetches structured weather data from an HTTP API, and
2) Asks an LLM to produce a friendly, short answer.

Key improvements vs. the BAD version:
- Separation of concerns (Config, LLMClient, WeatherClient, WeatherAgent).
- Robust HTTP behavior (timeouts, raise_for_status, typed exception handling).
- Safer request building (query params; no string concatenation).
- Env-driven configuration (no hardcoded secrets/URLs).
- Simple TTL cache with injectable clock for testability.
- Structured logging and minimal payload validation.
- Clear type hints and docstrings to aid maintenance and interviews.

Intended interview use:
- Reviewers can assess structure, quality, and scalability considerations.
- Candidates can propose tests (happy-path, timeouts, cache hits, payload validation).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Callable
import os
import time
import json
import logging
import requests

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the agent.

    Values are read from environment variables with safe defaults,
    so the same binary can be used across environments (dev/stage/prod).

    Env vars:
        LLM_URL: Base URL for the LLM chat API.
        LLM_MODEL: Default LLM model name.
        LLM_API_KEY: API key for the LLM provider (Bearer token).
        WEATHER_URL: Base URL for weather API (expects `city` and `units` params).
        HTTP_TIMEOUT_S: Per-request timeout in seconds (float).
        CACHE_TTL_S: Cache time-to-live in seconds (int).
        LLM_MAX_RETRIES: Max retry attempts for transient LLM errors (int).
        LLM_BACKOFF_S: Base backoff in seconds; multiplied by attempt number (float).
    """

    llm_url: str = os.getenv("LLM_URL", "https://api.example-llm.com/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "mistral-small")
    api_key: str = os.getenv("LLM_API_KEY", "")
    weather_url: str = os.getenv("WEATHER_URL", "http://api.weather.internal/current")
    timeout_s: float = float(os.getenv("HTTP_TIMEOUT_S", "3.0"))
    ttl_s: int = int(os.getenv("CACHE_TTL_S", "60"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    backoff_s: float = float(os.getenv("LLM_BACKOFF_S", "0.3"))


class InMemoryTTLCache:
    """Minimal TTL cache for small-scale scenarios.

    This cache is intentionally simple (no eviction policy, no size limit) to
    keep the focus on interface boundaries and correctness. For production,
    consider a shared cache (Redis/Memcached) and stampede protection.

    Args:
        ttl_s: Time-to-live in seconds.
        now_fn: Injectable time function, useful for deterministic tests.
    """

    def __init__(self, ttl_s: int, now_fn: Callable[[], float] = time.time):
        self.ttl_s = ttl_s
        self._now = now_fn
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Return a cached value if fresh; otherwise None.

        Args:
            key: Cache key.

        Returns:
            The cached value if not expired; None otherwise.
        """
        hit = self._store.get(key)
        if not hit:
            return None
        ts, val = hit
        if self._now() - ts < self.ttl_s:
            return val
        return None

    def set(self, key: str, val: Any) -> None:
        """Insert or replace a value under the given key.

        Args:
            key: Cache key.
            val: Value to store.
        """
        self._store[key] = (self._now(), val)


class LLMClient:
    """Thin HTTP client for an LLM chat-completions API."""

    def __init__(self, cfg: Config):
        """Initialize the client.

        Args:
            cfg: Runtime configuration containing endpoint, model, API key, etc.
        """
        self.cfg = cfg
        if not self.cfg.api_key:
            logger.warning("missing_api_key")

    def chat(self, prompt: str, temperature: float = 0.7) -> str:
        """Call the LLM to obtain a chat completion.

        Implements basic resilience for transient transport errors and validates
        the minimal expected response shape.

        Args:
            prompt: The user prompt to send.
            temperature: Sampling temperature.

        Returns:
            The LLM-generated text content.

        Raises:
            requests.exceptions.HTTPError: Non-2xx response.
            RuntimeError: Exceeded retry budget for transient failures.
            ValueError/KeyError: Unexpected payload shape.
        """
        payload = {
            "model": self.cfg.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"}

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                resp = requests.post(
                    self.cfg.llm_url,
                    headers=headers,
                    json=payload,
                    timeout=self.cfg.timeout_s,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return str(content)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning("llm_transient_error attempt=%s err=%s", attempt, e)
                time.sleep(self.cfg.backoff_s * attempt)
            except requests.exceptions.HTTPError as e:
                logger.error(
                    "llm_http_error status=%s body=%s",
                    getattr(e.response, "status_code", None),
                    getattr(e.response, "text", None),
                )
                raise
            except (ValueError, KeyError) as e:
                logger.error("llm_bad_payload err=%s", e)
                raise

        raise RuntimeError("LLM unavailable after retries")


class WeatherClient:
    """HTTP client for a simple weather endpoint returning structured JSON."""

    def __init__(self, cfg: Config):
        """Initialize the client.

        Args:
            cfg: Runtime configuration with weather URL and timeouts.
        """
        self.cfg = cfg

    def fetch(self, city: str, units: str = "metric") -> Dict[str, Any]:
        """Fetch current weather for a city.

        Uses query parameters (not string concatenation) to avoid injection-like risks.

        Args:
            city: City name (non-empty after stripping).
            units: "metric" or "imperial" (caller is responsible for validation).

        Returns:
            A dict with at least keys: {"temp": <number>, "desc": <str>}.

        Raises:
            requests.exceptions.RequestException: Network/HTTP errors.
            ValueError: Malformed JSON or unexpected payload shape.
        """
        try:
            r = requests.get(
                self.cfg.weather_url,
                params={"city": city, "units": units},
                timeout=self.cfg.timeout_s,
            )
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.RequestException as e:
            logger.error("weather_http_error city=%s units=%s err=%s", city, units, e)
            raise
        except ValueError as e:
            logger.error("weather_json_error city=%s units=%s err=%s", city, units, e)
            raise

        if not isinstance(data, dict) or "temp" not in data or "desc" not in data:
            logger.error("weather_unexpected_payload city=%s payload=%s", city, data)
            raise ValueError("Unexpected weather payload")
        return data


class WeatherAgent:
    """High-level orchestrator that combines Weather and LLM calls with caching."""

    def __init__(
        self,
        cfg: Config,
        llm: LLMClient,
        weather: WeatherClient,
        cache: Optional[InMemoryTTLCache] = None,
    ):
        """Build an agent with injected dependencies (easy to test/mutate).

        Args:
            cfg: Runtime configuration.
            llm: LLM client instance.
            weather: Weather API client.
            cache: Optional TTL cache (defaults to in-memory).
        """
        self.cfg = cfg
        self.llm = llm
        self.weather = weather
        self.cache = cache or InMemoryTTLCache(cfg.ttl_s)

    def _cache_key(self, city: str, units: str) -> str:
        """Create a stable cache key.

        Args:
            city: City name.
            units: Units name.

        Returns:
            A composite cache key including both city and units.
        """
        return f"{city}:{units}"

    def answer(self, city: str, units: str = "metric") -> str:
        """Produce a short, friendly weather answer using the LLM.

        Flow:
          1) Validate `city`.
          2) Try cache by (city, units).
          3) Fetch structured weather.
          4) Prompt the LLM.
          5) Cache and return the answer.

        Args:
            city: City name (will be stripped; must not be empty).
            units: Either "metric" or "imperial".

        Returns:
            A short, user-friendly text describing current weather.

        Raises:
            Any exception bubbling up from WeatherClient/LLMClient in error scenarios.
        """
        city = (city or "").strip()
        if not city:
            return "Please provide a valid city."

        key = self._cache_key(city, units)
        cached = self.cache.get(key)
        if cached:
            logger.debug("cache_hit key=%s", key)
            return cached

        w = self.weather.fetch(city, units)
        prompt = (
            "Give a friendly 1-2 sentence weather update.\n"
            f"City: {city}\n"
            f"Temp (°{'C' if units == 'metric' else 'F'}): {w['temp']}\n"
            f"Description: {w['desc']}\n"
        )
        text = self.llm.chat(prompt)
        self.cache.set(key, text)
        return text


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """HTTP-like handler entrypoint (framework-agnostic shape).

    This function demonstrates how the agent could be wired in a simple HTTP
    handler: it reads query params, delegates to the agent, and returns a
    structured response with status and body.

    Args:
        event: A dict with at least `query` → { "city": ..., "units": ... }.

    Returns:
        Dict with keys:
            - "status": HTTP-like status code (int).
            - "body": Response text (str) or error message.

    Notes:
        - In a real service, consider parsing/validating inputs with a schema
          (e.g., Pydantic) and converting exceptions into normalized error
          objects with distinct error codes.
    """
    cfg = Config()
    agent = WeatherAgent(cfg, LLMClient(cfg), WeatherClient(cfg))
    query = event.get("query", {})
    city = str(query.get("city", "")).strip()
    units = str(query.get("units", "metric"))
    try:
        answer = agent.answer(city, units)
        return {"status": 200, "body": answer}
    except Exception:
        logger.exception("handler_error city=%s units=%s", city, units)
        return {"status": 502, "body": "Upstream service error"}


if __name__ == "__main__":
    # Tiny manual check (not a substitute for tests).
    print(handler({"query": {"city": "Istanbul"}}))
