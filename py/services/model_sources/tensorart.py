"""TensorArt model source (link / provenance only).

TensorArt support is intentionally limited to *linking* a model to its
TensorArt page.  Automatic metadata extraction is not possible without a
user session:

* ``tensor.art`` sits behind a Cloudflare managed challenge, so plain
  HTTP clients (aiohttp, requests, curl) receive ``403 "Just a moment..."``.
* Its internal API (``ap-east-1.tensorart.cloud`` / ``cn.tensorart.net``)
  answers every ``/v1/model/*`` route with
  ``{"code":100002,"message":"invalid authorization header"}``.
* The official TAMS API requires an AccessKey/SecretKey pair and request
  signatures, which is a poor fit for a "paste a URL" workflow.

``supports_enrichment`` is therefore ``False``: the agent pipeline skips
these models with an explicit reason instead of failing silently, and the
UI keeps showing the "View on TensorArt" link.  ``tusi.cn`` is TensorArt's
Chinese mirror and is accepted as the same platform.
"""

from __future__ import annotations

import re

from .base import ModelSource

_DOMAINS = r"(?:tensor\.art|tusi\.cn)"

_URL_PATTERN = re.compile(
    rf"https?://(?:www\.)?{_DOMAINS}/models/(?P<id>\d+)"
)

_STRICT_URL_PATTERN = re.compile(
    rf"https?://(?:www\.)?{_DOMAINS}/models/(?P<id>\d+)(?:/[^/?#\s]+)?/?$"
)


class TensorArtSource(ModelSource):
    """TensorArt (``tensor.art``)."""

    platform = "tensorart"
    label = "TensorArt"
    supports_enrichment = False
    supports_download = False
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"https://tensor.art/models/{source_id}"

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        # Unreachable today: enrichment is disabled for this platform.
        return f"https://tensor.art/models/{source_id}"


__all__ = ["TensorArtSource"]
