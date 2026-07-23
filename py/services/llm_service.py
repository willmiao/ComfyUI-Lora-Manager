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

# ---------------------------------------------------------------------------
# Model catalog sourced from opencode's maintained model registry.
# maps provider_id -> list of model IDs.
# ---------------------------------------------------------------------------
_MODEL_CATALOG_URL = "https://models.dev/api.json"

# In-memory cache: maps provider slug -> list of model ID strings.
_catalog_cache: Optional[Dict[str, List[str]]] = None

# Per-model max output token limits parsed from the catalog.
# ``{provider_id: {model_id: max_output_tokens}}``.
_model_output_limits: Dict[str, Dict[str, int]] = {}

_CATALOG_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def _load_model_catalog() -> Dict[str, List[str]]:
    """Fetch and parse the model catalog.

    Returns ``{provider_id: [model_id, ...]}`` and also populates
    :data:`_model_output_limits` with per-model ``limit.output`` values
    for use by :func:`_get_model_max_output`.

    The JSON at ``_MODEL_CATALOG_URL`` is a dict keyed by provider slug; each
    value has a ``models`` sub-dict keyed by model ID.  The result is cached
    in memory after the first successful fetch.
    Subsequent calls return the cached data immediately.
    """
    global _catalog_cache, _model_output_limits
    if _catalog_cache is not None:
        return _catalog_cache

    try:
        async with aiohttp.ClientSession(timeout=_CATALOG_TIMEOUT) as session:
            async with session.get(_MODEL_CATALOG_URL) as resp:
                if resp.status != 200:
                    logger.warning("Model catalog returned HTTP %s", resp.status)
                    return _catalog_cache or {}
                data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Failed to fetch model catalog: %s", exc)
        return _catalog_cache or {}

    if not isinstance(data, dict):
        logger.warning("Model catalog is not a dict, got %s", type(data).__name__)
        return _catalog_cache or {}

    result: Dict[str, List[str]] = {}
    output_limits: Dict[str, Dict[str, int]] = {}
    for provider_id, provider_info in data.items():
        if not isinstance(provider_info, dict):
            continue
        models_dict = provider_info.get("models")
        if not isinstance(models_dict, dict):
            continue
        model_ids: List[str] = []
        provider_limits: Dict[str, int] = {}
        for mid, model_info in models_dict.items():
            if not isinstance(mid, str):
                continue
            model_ids.append(mid)
            if isinstance(model_info, dict):
                limit = model_info.get("limit")
                if isinstance(limit, dict):
                    output = limit.get("output")
                    if isinstance(output, (int, float)) and output > 0:
                        provider_limits[mid] = int(output)
        if model_ids:
            result[provider_id] = model_ids
        if provider_limits:
            output_limits[provider_id] = provider_limits

    _catalog_cache = result
    _model_output_limits = output_limits
    logger.debug(
        "Loaded model catalog: %d providers, %d total models "
        "(%d providers have output limits)",
        len(result),
        sum(len(m) for m in result.values()),
        len(output_limits),
    )
    return result


def _get_model_max_output(provider: str, model: str) -> Optional[int]:
    """Return the model's max output token limit from the catalog, or ``None``.

    Returns ``None`` when the provider or model is not found in the catalog
    (e.g. local Ollama models, custom models, or user-typed model names).
    Callers should fall back to a safe default.
    """
    return _model_output_limits.get(provider, {}).get(model)


# Short timeout for Ollama's local API
_OLLAMA_API_TIMEOUT = aiohttp.ClientTimeout(total=8)


async def fetch_ollama_models(api_base: str) -> List[str]:
    """Fetch locally available models from a running Ollama instance.

    Uses Ollama's OpenAI-compatible ``GET {api_base}/models`` endpoint.
    Returns an empty list if Ollama is not reachable (not running).
    """
    url = f"{api_base.rstrip('/')}/models"
    try:
        async with aiohttp.ClientSession(timeout=_OLLAMA_API_TIMEOUT) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.debug("Ollama API returned HTTP %s from %s", resp.status, api_base)
                    return []
                data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        logger.debug("Ollama not reachable at %s: %s", api_base, exc)
        return []

    raw = data.get("data") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []

    return [
        str(entry["id"]) for entry in raw
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]


async def get_provider_model_ids(provider_id: str) -> List[str]:
    """Return the list of known model IDs for *provider_id* from the catalog.

    The catalog is loaded on first call and cached thereafter.  If the
    provider is not found an empty list is returned (never raises).
    """
    catalog = await _load_model_catalog()
    return catalog.get(provider_id, [])


async def get_all_provider_models(
    provider_ids: List[str],
) -> Dict[str, List[str]]:
    """Return model lists for a subset of providers in one call.

    Loads the catalog (cached) and returns only the requested providers.
    Handy for embedding lightweight data into the template context.
    """
    catalog = await _load_model_catalog()
    return {
        pid: catalog.get(pid, [])
        for pid in provider_ids
    }


# Provider preset definitions.
# Each entry contains display metadata and defaults for the UI.
# The key is the internal provider id stored in ``llm_provider``.
# Models are NOT listed here — they come from the opencode model catalog at
# runtime (see :func:`get_provider_model_ids`).
PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "requires_key": True,
    },
    "ollama": {
        "name": "Ollama (local)",
        "api_base": "http://localhost:11434/v1",
        "requires_key": False,
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "requires_key": True,
    },
    "groq": {
        "name": "Groq",
        "api_base": "https://api.groq.com/openai/v1",
        "requires_key": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_base": "https://openrouter.ai/api/v1",
        "requires_key": True,
    },
    "opencode-go": {
        "name": "OpenCode Go",
        "api_base": "https://opencode.ai/zen/go/v1",
        "requires_key": True,
    },
    # "custom" is handled specially (no preset api_base, requires user input)
}

# Legacy lookup derived from PROVIDER_PRESETS for backward compat.
_PROVIDER_DEFAULTS: Dict[str, str] = {
    pid: info["api_base"]
    for pid, info in PROVIDER_PRESETS.items()
    if info.get("api_base")
}

# Request timeout for LLM calls (seconds)
_LLM_TIMEOUT = aiohttp.ClientTimeout(total=120)


class LLMService:
    """Centralized LLM API client.

    All LLM-based enrichment features call through this service so
    that BYOK config, retry logic, and error handling live in one place.
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
                    # Start preloading the model catalog in the background so
                    # the settings UI never blocks on it.  The catalog is
                    # cached after the first fetch (see _load_model_catalog).
                    asyncio.create_task(_load_model_catalog())
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

    @staticmethod
    def _provider_requires_key(provider: str) -> bool:
        """Return ``False`` when the given provider id does not need an API key."""
        preset = PROVIDER_PRESETS.get(provider, {})
        return bool(preset.get("requires_key", True))

    def is_configured(self) -> bool:
        """Return ``True`` when the LLM provider is minimally configured.

        A provider is considered configured when ``llm_model`` is set,
        an API key is configured for providers that require one (e.g.
        Ollama does not), and an API base URL is set for providers that
        have no preset default (e.g. ``custom``).
        """

        cfg = self._get_config()
        has_model = bool(cfg["model"])
        has_key = bool(cfg["api_key"]) or not self._provider_requires_key(cfg["provider"])
        has_base = bool(cfg["api_base"]) or bool(_PROVIDER_DEFAULTS.get(cfg["provider"]))
        return has_model and has_key and has_base

    def _resolve_api_base(self, provider: str, api_base: str) -> str:
        """Resolve the API base URL for the given provider.

        If ``api_base`` is explicitly set (non-empty), it takes priority.
        Otherwise the default from :data:`PROVIDER_PRESETS` is used.
        """

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

        A provider is considered configured when ``llm_model`` is set,
        an API key is configured for providers that require one, and
        an API base URL is set for providers without a preset default.
        """

        cfg = self._get_config()
        has_model = bool(cfg["model"])
        needs_key = self._provider_requires_key(cfg["provider"])
        has_key = bool(cfg["api_key"]) or not needs_key
        has_base = bool(cfg["api_base"]) or bool(_PROVIDER_DEFAULTS.get(cfg["provider"]))
        if not (has_model and has_key and has_base):
            parts = []
            if not has_model:
                parts.append("No LLM model specified")
            if not has_key and needs_key:
                parts.append("No LLM API key configured")
            if not has_base:
                parts.append(
                    f"No API base URL for provider '{cfg['provider']}'"
                )
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
        model_name = model or cfg["model"]

        is_ollama = cfg["provider"] == "ollama"

        if is_ollama:
            # Use Ollama's native /api/chat endpoint which does NOT expose
            # a separate reasoning/thinking field (the model's full output
            # lands directly in message.content).  The OpenAI-compatible
            # endpoint splits thinking into the "reasoning" field, making
            # content empty when thinking consumes all available tokens.
            base = api_base.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            url = f"{base}/api/chat"
        else:
            url = f"{api_base}/chat/completions"

        payload: Dict[str, Any]
        if is_ollama:
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False,
                # Suppress separate thinking trace — thinking still happens
                # internally (accuracy preserved) but output goes directly to
                # message.content instead of being split across content +
                # thinking.  Without this the model can exhaust num_predict
                # on thinking alone and leave content empty.
                "think": False,
                "options": {
                    "temperature": temperature,
                    # 8K context is sufficient for metadata enrichment
                    # (prompt ~2-5K, output ~0.2-1K tokens).  The old 32K
                    # value was excessive for this use case and increased
                    # Ollama VRAM usage unnecessarily.
                    "num_ctx": 8192,
                },
            }
            if response_format is not None:
                payload["format"] = "json"
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens
        else:
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
            }
            if response_format is not None:
                payload["response_format"] = response_format
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens

        if is_ollama:
            logger.info(
                "Ollama request: model=%s num_ctx=%s num_predict=%s format=%s think=%s",
                payload.get("model"),
                payload.get("options", {}).get("num_ctx"),
                payload.get("options", {}).get("num_predict"),
                payload.get("format", "none"),
                payload.get("think"),
            )

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
                if is_ollama:
                    content = (data.get("message") or {}).get("content") or ""
                    usage = {"completion_tokens": data.get("eval_count", 0)}
                    finish_reason = data.get("done_reason", "")
                    if not content:
                        logger.warning(
                            "LLM returned empty content. Provider=ollama, "
                            "done_reason=%s, eval_count=%s",
                            finish_reason,
                            data.get("eval_count", 0),
                        )
                else:
                    content = data["choices"][0]["message"].get("content") or ""
                    usage = data.get("usage", {})
                    if not content:
                        logger.warning(
                            "LLM returned empty content. Full response truncated: %s",
                            json.dumps(data, ensure_ascii=False)[:1000],
                        )
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
        """Call the LLM with ``response_format=json_object`` and return parsed JSON.

        ``max_tokens`` is resolved in this order:
        1. Explicit caller-supplied ``max_tokens``
        2. Per-model ``limit.output`` from the model catalog
        3. A safe default of 4096 (sufficient for metadata enrichment)

        If the response content is empty or not valid JSON, attempts
        :func:`_try_salvage_json` before raising.

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
            LLMResponseError: Empty response or JSON parse failure
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Resolve max_tokens: caller override → catalog lookup → safe default
        if max_tokens is None:
            cfg = self._get_config()
            effective_max = _get_model_max_output(cfg["provider"], cfg["model"])
        else:
            effective_max = max_tokens
        if effective_max is None:
            effective_max = 4096

        # Use json_schema (not json_object) for broader provider compatibility:
        # LM Studio and some other OpenAI-compatible servers reject
        # json_object but accept json_schema.  {"type": "object"} is
        # functionally equivalent — it accepts any JSON object without
        # constraining specific fields.
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "metadata",
                "schema": {"type": "object"},
            },
        }

        try:
            result = await self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                response_format=response_format,
                max_tokens=effective_max,
            )
        except LLMResponseError as e:
            # Only fall back when the provider rejects the response_format
            # type value (e.g. "'response_format.type' must be...").  Avoid
            # catching unrelated 400 errors whose body happens to mention
            # "response_format" (e.g. "model does not support
            # response_format restrictions on this endpoint").
            if "'response_format.type'" not in str(e).lower():
                raise
            logger.info(
                "Provider rejected response_format, retrying without it. "
                "Falling back to prompt-only JSON mode. Error: %s",
                e,
            )
            result = await self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                response_format=None,
                max_tokens=effective_max,
            )

        content = result.get("content", "") or ""
        if not content:
            raise LLMResponseError(
                "LLM returned empty content. "
                f"Raw response: {json.dumps(result)[:500]}"
            )

        try:
            parsed = json.loads(content)
            logger.debug(
                "LLM raw content: %s",
                json.dumps(parsed, ensure_ascii=False)[:2000],
            )
            return parsed
        except (json.JSONDecodeError, TypeError) as exc:
            logger.info(
                "LLM raw response (first 800 chars): %s",
                content[:800],
            )

        # Last resort: attempt to salvage partial/truncated JSON
        salvaged = _try_salvage_json(content)
        if salvaged is not None:
            logger.warning(
                "LLM JSON salvaged from partial content (%d chars raw)",
                len(content),
            )
            return salvaged

        raise LLMResponseError(
            f"LLM response could not be parsed as JSON: {content[:200]}"
        )


def _try_salvage_json(raw: str) -> Dict[str, Any] | None:
    """Attempt to repair and parse a truncated JSON string.

    Handles common truncation patterns:

    * Incomplete string value at the end (``"foo`` → ``"foo"``)
    * Missing closing ``}`` or ``]`` (respecting nesting order)
    * Trailing comma before closing bracket
    * Extra text after the JSON object (e.g. markdown fences)

    Returns the parsed dict on success, ``None`` if repair is impossible.
    """
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown fences if the LLM wrapped the JSON
    if text.startswith("```"):
        end = text.find("\n")
        text = text[end + 1:] if end != -1 else text[3:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Find the first '{' and strip everything before it
    start = text.find("{")
    if start == -1:
        return None
    text = text[start:]

    # Try to close an incomplete string at the end (e.g. ``"https://huggingf``)
    # Pattern: ends mid-string (last quote is open)
    if text.count('"') % 2 == 1:
        text += '"'

    # Ensure trailing commas before closing braces work
    text = _strip_trailing_commas(text)

    # Walk through the text character by character to find unclosed
    # brackets and close them in the correct (LIFO) order.
    # We ignore brackets inside quoted strings.
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            else:
                return None  # Unmatched closer — unrecoverable
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            else:
                return None

    # Close remaining open brackets in reverse order
    for opener in reversed(stack):
        text += "}" if opener == "{" else "]"

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _strip_trailing_commas(text: str) -> str:
    """Remove commas that appear before a closing brace/bracket."""
    import re as _re
    text = _re.sub(r",\s*}", "}", text)
    text = _re.sub(r",\s*]", "]", text)
    return text
