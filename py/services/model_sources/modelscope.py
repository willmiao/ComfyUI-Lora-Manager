"""ModelScope (魔搭社区) model source.

ModelScope exposes the same "model card as README.md" convention as
Hugging Face, including a YAML frontmatter block that often carries
``base_model:`` and ``trigger_words:``.  Two public endpoints are used,
neither of which requires an API key for public models:

* ``/models/{owner}/{name}/resolve/{revision}/README.md`` — raw model card
* ``/api/v1/models/{owner}/{name}/repo?Revision=..&FilePath=README.md`` —
  the same content through the API, used as a fallback when the resolve
  URL is unavailable.
"""

from __future__ import annotations

import re

from .base import ModelSource, fetch_text

_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?modelscope\.(?:cn|com)/models/(?P<id>[^/?#\s]+/[^/?#\s]+)"
)

#: Trailing view segments the site appends to a model URL; accepted verbatim
#: when the user pastes a browser tab URL.
_VIEW_SEGMENTS = r"(?:summary|files|model-file|readme|community|evaluation)?"

_STRICT_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?modelscope\.(?:cn|com)/models/(?P<id>[^/?#\s]+/[^/?#\s]+)"
    rf"/?{_VIEW_SEGMENTS}/?$"
)

#: ``master`` is ModelScope's default branch; ``main`` is tried as a fallback
#: for repos imported from Hugging Face.
_REVISIONS = ("master", "main")


class ModelScopeSource(ModelSource):
    """ModelScope (``modelscope.cn``)."""

    platform = "modelscope"
    label = "ModelScope"
    supports_enrichment = True
    supports_download = False
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"https://modelscope.cn/models/{source_id}"

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        return f"https://modelscope.cn/models/{source_id}/resolve/{revision or 'master'}"

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch the model card, preferring the raw resolve URL."""

        for revision in _REVISIONS:
            text = await fetch_text(
                f"https://modelscope.cn/models/{source_id}/resolve/{revision}/README.md"
            )
            if text:
                return text

        # Fallback: the repo API proxies the same file and is reachable in
        # environments where the CDN resolve host is blocked.
        for revision in _REVISIONS:
            text = await fetch_text(
                "https://modelscope.cn/api/v1/models/"
                f"{source_id}/repo?Revision={revision}&FilePath=README.md"
            )
            if text:
                return text
        return ""


__all__ = ["ModelScopeSource"]
