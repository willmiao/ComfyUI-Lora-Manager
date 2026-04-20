"""In-memory connectivity guard to suppress repeated network retries when offline."""

from __future__ import annotations

import asyncio
import errno
import logging
import socket
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
        self.online = True
        self.failure_count = 0
        self.cooldown_until: datetime | None = None
        self.base_backoff_seconds = 30
        self.max_backoff_seconds = 300
        self.failure_threshold = 3

    def _now(self) -> datetime:
        return datetime.now()

    def in_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return self._now() < self.cooldown_until

    def cooldown_remaining_seconds(self) -> float:
        if self.cooldown_until is None:
            return 0.0
        return max(0.0, (self.cooldown_until - self._now()).total_seconds())

    def should_block_request(self) -> bool:
        return self.in_cooldown()

    def register_success(self) -> None:
        was_offline = (not self.online) or self.cooldown_until is not None
        self.online = True
        self.failure_count = 0
        self.cooldown_until = None
        if was_offline:
            logger.info("Connectivity restored; requests resumed.")

    def register_network_failure(self, exc: Exception) -> None:
        self.online = False
        self.failure_count += 1

        if self.failure_count < self.failure_threshold:
            logger.debug(
                "Network failure tracked (%d/%d): %s",
                self.failure_count,
                self.failure_threshold,
                exc,
            )
            return

        retry_step = self.failure_count - self.failure_threshold
        backoff = min(
            self.max_backoff_seconds,
            self.base_backoff_seconds * (2**retry_step),
        )
        should_log_warning = not self.in_cooldown()
        self.cooldown_until = self._now() + timedelta(seconds=backoff)

        if should_log_warning:
            logger.warning(
                "Connectivity offline; enter cooldown for %ss after %d network failures.",
                int(backoff),
                self.failure_count,
            )
        else:
            logger.debug(
                "Cooldown still active; failure_count=%d, backoff=%ss.",
                self.failure_count,
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

