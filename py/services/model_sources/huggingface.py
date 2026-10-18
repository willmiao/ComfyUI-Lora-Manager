"""Hugging Face model source."""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from .base import (
    ModelSource,
    ModelSourceError,
    SourceRef,
    fetch_json,
    fetch_text,
    filter_weight_files,
)

logger = logging.getLogger(__name__)

#: Lenient — used to normalise URLs already stored in metadata; tolerates
#: sub-paths such as ``/resolve/main/model.safetensors``.
_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?huggingface\.co/(?P<id>[^/?#\s]+/[^/?#\s]+)"
)

#: Strict — validates what the user pasted into the "link model" dialog.
_STRICT_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?huggingface\.co/(?P<id>[^/?#\s]+/[^/?#\s]+)/?$"
)


def _hf_token() -> str:
    """Return the configured Hugging Face access token, or ``""``."""

    try:
        from ..settings_manager import get_settings_manager

        token = get_settings_manager().get("huggingface_api_key", "")
    except Exception:  # pragma: no cover - settings must never break downloads
        return ""
    return token.strip() if isinstance(token, str) else ""


class HuggingFaceSource(ModelSource):
    """Hugging Face Hub (``huggingface.co``)."""

    platform = "huggingface"
    label = "Hugging Face"
    supports_enrichment = True
    supports_download = True
    default_revision = "main"
    default_subdir = "huggingface"
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"https://huggingface.co/{source_id}"

    def group_key(self, ref: SourceRef, item: Mapping[str, Any]) -> Optional[str]:
        """Hugging Face models never auto-group.

        A repository is not a model identity — collection repos host many
        unrelated models — and the Hub exposes no site-native published-model
        id, so there is no reliable key to group by.
        """

        return None

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        return f"https://huggingface.co/{source_id}/resolve/{self.resolve_revision(revision)}"

    def auth_headers(self) -> dict[str, str]:
        """Bearer header for gated/private repositories, when a token is set."""

        token = _hf_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch ``README.md`` from Hugging Face (tries ``main``, then ``master``)."""

        headers = self.auth_headers()
        for branch in ("main", "master"):
            text = await fetch_text(
                f"https://huggingface.co/{source_id}/raw/{branch}/README.md",
                headers=headers,
            )
            if text:
                return text
        return ""

    async def list_files(
        self, source_id: str, revision: str = ""
    ) -> list[dict]:
        """List weight files via the Hub tree API.

        The tree endpoint (rather than the model-info endpoint) is used
        because it reports accurate sizes for LFS-tracked files.
        """

        revision = self.resolve_revision(revision)
        status, payload = await fetch_json(
            f"https://huggingface.co/api/models/{source_id}/tree/{revision}",
            headers=self.auth_headers(),
        )

        if status == 404:
            raise ModelSourceError(f"Repository '{source_id}' not found", status=404)
        if status in (401, 403):
            if _hf_token():
                raise ModelSourceError(
                    f"Access to '{source_id}' was denied (HTTP {status}). For a gated "
                    "repository you must accept its terms on the Hugging Face page, "
                    "and the configured token needs read permission for it.",
                    status=403,
                )
            raise ModelSourceError(
                f"'{source_id}' requires a Hugging Face access token (gated or "
                "private repository). Configure one in Settings → Hugging Face "
                "Access Token, and accept the repository's terms on its page.",
                status=401,
            )
        if status != 200 or not isinstance(payload, list):
            raise ModelSourceError(
                f"Hugging Face API error while listing '{source_id}' (HTTP {status})"
            )

        entries = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path", "")
            size = entry.get("size", 0) or 0
            if not size and isinstance(entry.get("lfs"), dict):
                size = entry["lfs"].get("size", 0) or 0
            entries.append((path, size))

        return filter_weight_files(entries)

    def file_download_url(
        self, source_id: str, filename: str, revision: str = ""
    ) -> str:
        return (
            f"https://huggingface.co/{source_id}/resolve/"
            f"{self.resolve_revision(revision)}/{filename}"
        )

    def page_url_for_file(self, source_id: str, filename: str) -> str:
        return (
            f"https://huggingface.co/{source_id}/blob/{self.default_revision}/{filename}"
        )


__all__ = ["HuggingFaceSource"]
