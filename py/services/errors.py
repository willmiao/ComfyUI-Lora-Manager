"""Common service-level exception types."""

from __future__ import annotations

from typing import Optional


class RateLimitError(RuntimeError):
    """Raised when a remote provider rejects a request due to rate limiting."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        provider: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.provider = provider


class ResourceNotFoundError(RuntimeError):
    """Raised when a remote resource is permanently missing."""

    pass

