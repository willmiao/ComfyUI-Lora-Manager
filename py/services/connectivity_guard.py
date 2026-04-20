"""In-memory connectivity guard to suppress repeated network retries when offline."""

from __future__ import annotations

import asyncio
import errno
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

OFFLINE_COOLDOWN_ERROR = "offline_cooldown"
OFFLINE_FRIENDLY_MESSAGE = "Network offline, will retry automatically later"


def is_offline_cooldown_error(value: Any) -> bool:
    """Return True when a response payload represents guard short-circuit."""
    return isinstance(value, str) and value == OFFLINE_COOLDOWN_ERROR


def is_expected_offline_error(value: Any) -> bool:
    """Return True when payload is an expected offline-related result."""
    if is_offline_cooldown_error(value):
        return True
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return "network offline" in normalized or "offline" in normalized


class ConnectivityGuard:
    """Tracks network failures and gates outbound requests during cooldown."""

    _instance: "ConnectivityGuard | None" = None
    _instance_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "ConnectivityGuard":
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._default_destination = "__global__"
        self._destination_states: dict[str, _DestinationState] = {
            self._default_destination: _DestinationState()
        }
        self.base_backoff_seconds = 30
        self.max_backoff_seconds = 300
        self.failure_threshold = 3

    @property
    def online(self) -> bool:
        return self._state_for_destination(None).online

    @online.setter
    def online(self, value: bool) -> None:
        self._state_for_destination(None).online = value

    @property
    def failure_count(self) -> int:
        return self._state_for_destination(None).failure_count

    @failure_count.setter
    def failure_count(self, value: int) -> None:
        self._state_for_destination(None).failure_count = value

    @property
    def cooldown_until(self) -> datetime | None:
        return self._state_for_destination(None).cooldown_until

    @cooldown_until.setter
    def cooldown_until(self, value: datetime | None) -> None:
        self._state_for_destination(None).cooldown_until = value

    def _now(self) -> datetime:
        return datetime.now()

    def _normalize_destination(self, destination: str | None) -> str:
        if destination is None or not destination.strip():
            return self._default_destination
        return destination.lower().strip()

    def _state_for_destination(self, destination: str | None) -> "_DestinationState":
        destination_key = self._normalize_destination(destination)
        if destination_key not in self._destination_states:
            self._destination_states[destination_key] = _DestinationState()
        return self._destination_states[destination_key]

    def in_cooldown(self, destination: str | None = None) -> bool:
        state = self._state_for_destination(destination)
        if state.cooldown_until is None:
            return False
        return self._now() < state.cooldown_until

    def cooldown_remaining_seconds(self, destination: str | None = None) -> float:
        state = self._state_for_destination(destination)
        if state.cooldown_until is None:
            return 0.0
        return max(0.0, (state.cooldown_until - self._now()).total_seconds())

    def should_block_request(self, destination: str | None = None) -> bool:
        return self.in_cooldown(destination)

    def register_success(self, destination: str | None = None) -> None:
        destination_key = self._normalize_destination(destination)
        state = self._state_for_destination(destination_key)
        was_offline = (not state.online) or state.cooldown_until is not None
        state.online = True
        state.failure_count = 0
        state.cooldown_until = None
        if was_offline:
            logger.info(
                "Connectivity restored for destination '%s'; requests resumed.",
                destination_key,
            )

    def register_network_failure(
        self, exc: Exception, destination: str | None = None
    ) -> None:
        destination_key = self._normalize_destination(destination)
        state = self._state_for_destination(destination_key)
        state.online = False
        state.failure_count += 1

        if state.failure_count < self.failure_threshold:
            logger.debug(
                "Network failure tracked for destination '%s' (%d/%d): %s",
                destination_key,
                state.failure_count,
                self.failure_threshold,
                exc,
            )
            return

        retry_step = state.failure_count - self.failure_threshold
        backoff = min(
            self.max_backoff_seconds,
            self.base_backoff_seconds * (2**retry_step),
        )
        should_log_warning = not self.in_cooldown(destination_key)
        state.cooldown_until = self._now() + timedelta(seconds=backoff)

        if should_log_warning:
            logger.warning(
                "Connectivity offline for destination '%s'; enter cooldown for %ss after %d network failures.",
                destination_key,
                int(backoff),
                state.failure_count,
            )
        else:
            logger.debug(
                "Cooldown still active for destination '%s'; failure_count=%d, backoff=%ss.",
                destination_key,
                state.failure_count,
                int(backoff),
            )

    @staticmethod
    def is_network_unreachable_error(exc: Exception) -> bool:
        """Return whether the exception should count as connectivity failure."""
        if isinstance(exc, asyncio.CancelledError):
            return False

        if isinstance(
            exc,
            (
                asyncio.TimeoutError,
                TimeoutError,
                ConnectionRefusedError,
                socket.gaierror,
                aiohttp.ServerTimeoutError,
                aiohttp.ConnectionTimeoutError,
                aiohttp.ClientConnectorError,
                aiohttp.ClientConnectionError,
            ),
        ):
            return True

        if isinstance(exc, OSError) and exc.errno in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ETIMEDOUT,
            errno.ECONNREFUSED,
        }:
            return True

        return False


@dataclass
class _DestinationState:
    online: bool = True
    failure_count: int = 0
    cooldown_until: datetime | None = None
