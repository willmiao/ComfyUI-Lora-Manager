"""Centralized LLM API client with BYOK (bring-your-own-key) provider support.

Reads provider configuration from :class:`SettingsManager` and makes
OpenAI-compatible ``/chat/completions`` calls.  Supports any provider that
implements the OpenAI Chat Completions API surface area (OpenAI, Ollama,
vLLM, LM Studio, etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from .errors import LLMNotConfiguredError, LLMRateLimitError, LLMResponseError

logger = logging.getLogger(__name__)

# Default API base URLs per provider
_PROVIDER_DEFAULTS: Dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    # "custom" requires an explicit llm_api_base from the user
}

# Request timeout for LLM calls (seconds)
_LLM_TIMEOUT = aiohttp.ClientTimeout(total=120)


class LLMService:
    """Centralized LLM API client.

    All agent skills call LLMs through this service so that BYOK config,
    retry logic, and error handling live in one place.
    """

    _instance: Optional["LLMService"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, settings_service) -> None:
        self._settings = settings_service

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    async def get_instance(cls) -> "LLMService":
        """Return the lazily-initialised global ``LLMService`` instance."""

        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    from .settings_manager import get_settings_manager

                    cls._instance = cls(get_settings_manager())
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the cached singleton — primarily for tests."""

        cls._instance = None

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _get_config(self) -> Dict[str, Any]:
        """Read the current LLM configuration from settings."""

        return {
            "provider": self._settings.get("llm_provider", "openai"),
            "api_key": self._settings.get("llm_api_key", ""),
            "api_base": self._settings.get("llm_api_base", ""),
            "model": self._settings.get("llm_model", ""),
        }

    def is_configured(self) -> bool:
        """Return ``True`` when the LLM provider is minimally configured.

        A provider is considered configured when ``llm_model`` is set and
        (for non-Ollama) an API key is configured.
        """

        cfg = self._get_config()
        has_model = bool(cfg["model"])
        has_key = bool(cfg["api_key"]) or cfg["provider"] == "ollama"
        return has_model and has_key

    def _resolve_api_base(self, provider: str, api_base: str) -> str:
        """Resolve the API base URL for the given provider."""

        if api_base:
            return api_base.rstrip("/")
        return _PROVIDER_DEFAULTS.get(provider, "").rstrip("/")

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        """Build HTTP headers for the LLM API request."""

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _ensure_configured(self) -> Dict[str, Any]:
        """Validate configuration and return it, or raise.

        A provider is considered configured when ``llm_model`` is set and
        (for non-Ollama) an API key is configured.
        """

        cfg = self._get_config()
        has_model = bool(cfg["model"])
        has_key = bool(cfg["api_key"]) or cfg["provider"] == "ollama"
        if not (has_model and has_key):
            parts = []
            if not has_model:
                parts.append("No LLM model specified")
            if not has_key and cfg["provider"] != "ollama":
                parts.append("No LLM API key configured")
            detail = "; ".join(parts) if parts else "LLM provider is not configured"
            raise LLMNotConfiguredError(
                f"{detail}. Configure it in Settings → AI Provider."
            )
        return cfg

    # ------------------------------------------------------------------
    # Core API call
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        *,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        retry_on_rate_limit: bool = True,
    ) -> Dict[str, Any]:
        """Call the configured LLM provider's ``/chat/completions`` endpoint.

        Args:
            messages: OpenAI-format message list
            model: Override the configured model name
            temperature: Sampling temperature
            response_format: Optional ``{"type": "json_object"}`` for structured output
            max_tokens: Optional max output tokens
            retry_on_rate_limit: Retry once after a 429 with backoff

        Returns:
            Dict with ``content`` (str), ``usage`` (dict), ``model`` (str)

        Raises:
            LLMNotConfiguredError: Provider not enabled / missing config
            LLMRateLimitError: Rate limited and retry exhausted
            LLMResponseError: Non-200 response or parse failure
        """

        cfg = self._ensure_configured()
        api_base = self._resolve_api_base(cfg["provider"], cfg["api_base"])
        url = f"{api_base}/chat/completions"
        model_name = model or cfg["model"]

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = self._build_headers(cfg["api_key"])

        attempt = 0
        max_attempts = 2 if retry_on_rate_limit else 1
        while attempt < max_attempts:
            attempt += 1
            try:
                async with aiohttp.ClientSession(timeout=_LLM_TIMEOUT) as session:
                    async with session.post(
                        url, json=payload, headers=headers
                    ) as resp:
                        if resp.status == 429:
                            if attempt < max_attempts:
                                retry_after = float(
                                    resp.headers.get("Retry-After", "5")
                                )
                                logger.warning(
                                    "LLM rate limited, retrying after %.1fs",
                                    retry_after,
                                )
                                await asyncio.sleep(retry_after)
                                continue
                            raise LLMRateLimitError(
                                f"LLM provider rate limited (HTTP 429)",
                                provider=cfg["provider"],
                            )

                        if resp.status != 200:
                            body = await resp.text()
                            raise LLMResponseError(
                                f"LLM API returned HTTP {resp.status}: "
                                f"{body[:500]}"
                            )

                        data = await resp.json()

            except aiohttp.ClientError as exc:
                raise LLMResponseError(f"Network error calling LLM API: {exc}") from exc

            # Parse response
            try:
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {
                    "content": content,
                    "usage": usage,
                    "model": data.get("model", model_name),
                }
            except (KeyError, IndexError) as exc:
                raise LLMResponseError(
                    f"Unexpected LLM response structure: {json.dumps(data)[:500]}"
                ) from exc

        # Should not reach here, but satisfy type checker
        raise LLMRateLimitError("Rate limit retry exhausted", provider=cfg["provider"])

    # ------------------------------------------------------------------
    # Structured output convenience
    # ------------------------------------------------------------------

    async def chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call the LLM and return parsed JSON.

        Sends ``response_format: {"type": "json_object"}`` when the provider
        supports it, and parses the response content as JSON.  If parsing
        fails, retries once with a clarifying system message.

        Args:
            system_prompt: System-level instructions
            user_prompt: User-level query
            model: Override the configured model name
            temperature: Sampling temperature
            max_tokens: Optional max output tokens

        Returns:
            Parsed JSON dict from the LLM response

        Raises:
            LLMNotConfiguredError: Provider not configured
            LLMRateLimitError: Rate limited
            LLMResponseError: JSON parse failure after retry
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # First attempt with JSON mode
        result = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )

        try:
            return json.loads(result["content"])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "LLM JSON parse failed on first attempt: %s. Retrying.", exc
            )

        # Retry with explicit instruction to return valid JSON
        retry_messages = messages + [
            {
                "role": "assistant",
                "content": result["content"],
            },
            {
                "role": "user",
                "content": (
                    "The previous response could not be parsed as JSON. "
                    "Please respond with ONLY a valid JSON object, no "
                    "markdown fences or extra text."
                ),
            },
        ]

        result = await self.chat_completion(
            messages=retry_messages,
            model=model,
            temperature=0.0,  # More deterministic for retry
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )

        try:
            return json.loads(result["content"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMResponseError(
                f"LLM response could not be parsed as JSON after retry: {exc}\n"
                f"Raw content: {result['content'][:500]}"
            ) from exc
