"""ModelScope (魔搭社区) model source.

ModelScope exposes the same "model card as README.md" convention as
Hugging Face, including a YAML frontmatter block that often carries
``base_model:`` and ``trigger_words:``.  Three public endpoints are used,
none of which requires an API key for public models:

* ``/models/{owner}/{name}/resolve/{revision}/README.md`` — raw model card
* ``/api/v1/models/{owner}/{name}/repo?Revision=..&FilePath=README.md`` —
  the same content through the API, used as a fallback when the resolve
  URL is unavailable.
* ``/api/v1/models/{owner}/{name}/repo/files?Revision=..`` — the file
  listing backing the download picker.  It reports real sizes for LFS
  files (not the pointer size), so no extra HEAD request is needed.

Downloads go through ``/models/{owner}/{name}/resolve/{revision}/{path}``,
which redirects to a CDN URL carrying a time-limited ``auth_key``.
Requesting the resolve URL fresh on every attempt (which the shared
downloader does, including for resumable Range requests) keeps that key
valid; the CDN URL must never be cached.
"""

from __future__ import annotations

import logging
import re

from .base import (
    ModelSource,
    ModelSourceError,
    fetch_json,
    fetch_text,
    filter_weight_files,
)

logger = logging.getLogger(__name__)

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
    supports_download = True
    default_revision = "master"
    default_subdir = "modelscope"
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"https://modelscope.cn/models/{source_id}"

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        return (
            f"https://modelscope.cn/models/{source_id}/resolve/"
            f"{self.resolve_revision(revision)}"
        )

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

    async def list_files(
        self, source_id: str, revision: str = ""
    ) -> list[dict]:
        """List weight files via the repo files API.

        ``master`` is the only branch name the API accepts — even repos
        imported from Hugging Face are addressed as ``master`` (``main``
        returns 404) — so no fallback probing is done here.
        """

        revision = self.resolve_revision(revision)
        status, payload = await fetch_json(
            "https://modelscope.cn/api/v1/models/"
            f"{source_id}/repo/files?Revision={revision}"
        )

        if status == 404:
            raise ModelSourceError(f"Repository '{source_id}' not found", status=404)
        if status != 200 or not isinstance(payload, dict):
            raise ModelSourceError(
                f"ModelScope API error while listing '{source_id}' (HTTP {status})"
            )

        entries = []
        for entry in (payload.get("Data") or {}).get("Files") or []:
            if not isinstance(entry, dict) or entry.get("Type") != "blob":
                continue
            entries.append((entry.get("Path", ""), entry.get("Size", 0) or 0))

        return filter_weight_files(entries)

    def file_download_url(
        self, source_id: str, filename: str, revision: str = ""
    ) -> str:
        return (
            f"https://modelscope.cn/models/{source_id}/resolve/"
            f"{self.resolve_revision(revision)}/{filename}"
        )

    def page_url_for_file(self, source_id: str, filename: str) -> str:
        return (
            f"https://modelscope.cn/models/{source_id}/file/view/"
            f"{self.default_revision}/{filename}"
        )


__all__ = ["ModelScopeSource"]
