"""Process-wide, per-destination rate-limit gate for outbound API traffic.

Implements the pacing/gating layer designed in
``docs/plans/issue-1085-rate-limit-design.md``:

- **Reactive gate**: a 429 response arms ``next_allowed_send`` from the
  vendor's ``Retry-After`` (or exponential backoff when the header is
  missing); subsequent requests to the same destination wait out the window.
- **Preemptive pacing**: a minimum inter-request interval per destination
  spaces consecutive sends so bursts never form in the first place.
- **Herd-free**: waiters are serialized through a per-destination lock, so
  each one claims a distinct send slot instead of thousands of coroutines
  waking up together.
- **Bounded**: waits longer than ``rate_limit_max_wait_seconds`` are refused
  by raising :class:`RateLimitError`, leaving the final decision to callers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from .errors import RateLimitError

logger = logging.getLogger(__name__)

DEFAULT_MIN_INTERVAL_SECONDS = 0.75
DEFAULT_MAX_WAIT_SECONDS = 300.0
BASE_BACKOFF_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 1800.0


@dataclass
class _DestinationState:
    """Rate-limit bookkeeping for one destination (hostname)."""

    next_allowed_send: float = 0.0  # time.monotonic() timestamp
    consecutive_429: int = 0
    last_send_at: float = 0.0  # time.monotonic() timestamp
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimitCoordinator:
    """Coordinates outbound request pacing per destination.

    Singleton mirroring :class:`ConnectivityGuard`'s pattern. All waits are
    bounded by the ``rate_limit_max_wait_seconds`` setting; when the required
    wait exceeds the cap, :meth:`wait_for_slot` raises :class:`RateLimitError`
    instead of parking the caller.
    """

    _instance: "RateLimitCoordinator | None" = None
    _instance_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "RateLimitCoordinator":
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._states: Dict[str, _DestinationState] = {}

    # ------------------------------------------------------------------
    # Settings (read live so settings edits apply without a restart)

    @staticmethod
    def _setting(key: str, default):
        try:
            from .settings_manager import get_settings_manager

            return get_settings_manager().get(key, default)
        except Exception:  # pragma: no cover - defensive: settings unavailable
            return default

    @property
    def enabled(self) -> bool:
        return bool(self._setting("rate_limit_gate_enabled", True))

    @property
    def min_interval_seconds(self) -> float:
        try:
            return max(0.0, float(self._setting("rate_limit_min_interval_seconds", DEFAULT_MIN_INTERVAL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_MIN_INTERVAL_SECONDS

    @property
    def max_wait_seconds(self) -> float:
        try:
            return max(0.0, float(self._setting("rate_limit_max_wait_seconds", DEFAULT_MAX_WAIT_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_MAX_WAIT_SECONDS

    # ------------------------------------------------------------------
    # State helpers

    @staticmethod
    def _normalize(destination: Optional[str]) -> str:
        if destination is None or not destination.strip():
            return "__global__"
        return destination.lower().strip()

    def _state_for(self, destination: Optional[str]) -> _DestinationState:
        key = self._normalize(destination)
        if key not in self._states:
            self._states[key] = _DestinationState()
        return self._states[key]

    def reset(self) -> None:
        """Drop all per-destination state. Test seam."""
        self._states.clear()

    def in_cooldown(self, destination: Optional[str] = None) -> bool:
        return self.remaining_seconds(destination) > 0

    def remaining_seconds(self, destination: Optional[str] = None) -> float:
        state = self._state_for(destination)
        return max(0.0, state.next_allowed_send - time.monotonic())

    # ------------------------------------------------------------------
    # Gate operations

    async def wait_for_slot(self, destination: Optional[str] = None) -> None:
        """Block until this caller may send the next request to *destination*.

        Waits for both the rate-limit cooldown (``next_allowed_send``) and the
        minimum inter-request interval (``last_send_at + min_interval``).
        Waiters queue on the per-destination lock, so concurrent callers are
        spaced out instead of stampeding when a cooldown expires.

        Raises:
            RateLimitError: when the required wait exceeds
                ``rate_limit_max_wait_seconds``.
        """
        state = self._state_for(destination)
        deadline = time.monotonic() + self.max_wait_seconds
        async with state.lock:
            now = time.monotonic()
            wake_at = max(
                state.next_allowed_send,
                state.last_send_at + self.min_interval_seconds,
            )
            if wake_at > deadline:
                raise RateLimitError(
                    f"Rate limit wait for '{self._normalize(destination)}' "
                    f"exceeds the {self.max_wait_seconds:.0f}s cap",
                    retry_after=wake_at - now,
                )
            delay = wake_at - now
            if delay > 0:
                logger.debug(
                    "Rate-limit gate: pacing request to '%s' by %.2fs",
                    self._normalize(destination),
                    delay,
                )
                await asyncio.sleep(delay)
            state.last_send_at = time.monotonic()

    def register_rate_limit(
        self,
        destination: Optional[str],
        retry_after: Optional[float] = None,
    ) -> float:
        """Record a 429 for *destination* and arm the cooldown window.

        Honors the vendor's ``Retry-After`` when present; otherwise grows an
        exponential backoff (30s base, doubling per consecutive 429, capped at
        1800s). Returns the cooldown duration in seconds.
        """
        state = self._state_for(destination)
        state.consecutive_429 += 1
        if retry_after is not None and retry_after > 0:
            backoff = min(MAX_BACKOFF_SECONDS, float(retry_after))
        else:
            backoff = min(
                MAX_BACKOFF_SECONDS,
                BASE_BACKOFF_SECONDS * (2 ** (state.consecutive_429 - 1)),
            )
        now = time.monotonic()
        already_cooling = state.next_allowed_send > now
        state.next_allowed_send = max(state.next_allowed_send, now + backoff)
        if already_cooling:
            logger.debug(
                "Rate-limit cooldown for '%s' extended by %.0fs (consecutive_429=%d)",
                self._normalize(destination),
                backoff,
                state.consecutive_429,
            )
        else:
            logger.info(
                "Rate limited by '%s'; pausing requests for %.0fs",
                self._normalize(destination),
                backoff,
            )
        return backoff

    def register_success(self, destination: Optional[str]) -> None:
        """Reset rate-limit state after a successful request.

        A 200 proves the vendor is accepting traffic again, so any armed
        cooldown window is cleared alongside the backoff counter (mirrors
        ``ConnectivityGuard.register_success`` semantics).
        """
        state = self._state_for(destination)
        state.consecutive_429 = 0
        state.next_allowed_send = 0.0
