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


class DownloadRateLimitError(RateLimitError):
    """Raised when a file download is rejected with HTTP 429.

    Carries the vendor's ``Retry-After`` hint (when present) and the target
    host so the download manager can build the structured rate-limit result
    the download queue contract expects.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: Optional[float] = None,
        host: Optional[str] = None,
    ) -> None:
        super().__init__(message, retry_after=retry_after)
        self.host = host


class ResourceNotFoundError(RuntimeError):
    """Raised when a remote resource is permanently missing."""

    pass


class LLMNotConfiguredError(RuntimeError):
    """Raised when an LLM-dependent operation is attempted but no provider is configured."""

    pass


class LLMRateLimitError(RateLimitError):
    """Raised when the LLM provider rejects a request due to rate limiting."""

    pass


class LLMResponseError(RuntimeError):
    """Raised when the LLM returns an unparseable or schema-invalid response."""

    pass

