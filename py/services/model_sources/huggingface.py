"""Hugging Face model source."""

from __future__ import annotations

import re

from .base import ModelSource, fetch_text

#: Lenient — used to normalise URLs already stored in metadata; tolerates
#: sub-paths such as ``/resolve/main/model.safetensors``.
_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?huggingface\.co/(?P<id>[^/?#\s]+/[^/?#\s]+)"
)

#: Strict — validates what the user pasted into the "link model" dialog.
_STRICT_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?huggingface\.co/(?P<id>[^/?#\s]+/[^/?#\s]+)/?$"
)


class HuggingFaceSource(ModelSource):
    """Hugging Face Hub (``huggingface.co``)."""

    platform = "huggingface"
    label = "Hugging Face"
    supports_enrichment = True
    supports_download = True
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"https://huggingface.co/{source_id}"

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        return f"https://huggingface.co/{source_id}/resolve/{revision or 'main'}"

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch ``README.md`` from Hugging Face (tries ``main``, then ``master``)."""

        for branch in ("main", "master"):
            text = await fetch_text(
                f"https://huggingface.co/{source_id}/raw/{branch}/README.md"
            )
            if text:
                return text
        return ""


__all__ = ["HuggingFaceSource"]
