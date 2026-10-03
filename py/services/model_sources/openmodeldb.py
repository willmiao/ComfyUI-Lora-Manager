"""OpenModelDB model source (upscaler catalogue).

OpenModelDB (https://openmodeldb.info) is a static catalogue of upscaler
models.  Unlike the repository-based sources (Hugging Face, ModelScope) a
model id here is a flat token (``4x-UltraSharp``) that *is* the published
model identity: there is no owner/repo split, no revision, and no README.
Everything the source needs — the resource download URLs, sizes, sha256
hashes, tags and example images — comes from the site's bulk JSON dumps via
:class:`~py.services.openmodeldb_client.OpenModelDBClient`, which caches the
catalogue on disk, so every method below is a local lookup once warmed.

Only PyTorch resources (``.pth`` / ``.safetensors``) are listed for download:
``.onnx`` is not a loadable weight format for the supported model types (see
:data:`py.utils.constants.MODEL_FILE_EXTENSIONS`).  Resources can carry
mirror URLs; only the primary URL is ever used (see
:meth:`OpenModelDBClient.primary_url`).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

from .base import (
    ModelCardContext,
    ModelSource,
    ModelSourceCache,
    ModelSourceError,
    filter_weight_files,
)
from ..openmodeldb_client import OPENMODELDB_SITE_BASE, OpenModelDBClient

logger = logging.getLogger(__name__)

#: Model ids are flat tokens (``4x-UltraSharp``), usable as a path segment.
_SOURCE_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")

_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?openmodeldb\.info/models/(?P<id>[A-Za-z0-9_][A-Za-z0-9_.\-]*)"
)
_STRICT_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?openmodeldb\.info/models/(?P<id>[A-Za-z0-9_][A-Za-z0-9_.\-]*)/?$"
)

#: Resource platforms whose files ComfyUI can load.
_DOWNLOADABLE_PLATFORMS = frozenset({"pytorch"})


class OpenModelDBSource(ModelSource):
    """OpenModelDB (``openmodeldb.info``)."""

    platform = "openmodeldb"
    label = "OpenModelDB"
    supports_enrichment = True
    supports_download = True
    default_revision = ""
    default_subdir = "openmodeldb"
    example_source_id = "4x-UltraSharp"
    url_pattern = _URL_PATTERN
    strict_url_pattern = _STRICT_URL_PATTERN

    def canonical_url(self, source_id: str) -> str:
        return f"{OPENMODELDB_SITE_BASE}/models/{source_id}"

    def is_valid_source_id(self, source_id: str) -> bool:
        """OpenModelDB ids are flat tokens, not ``owner/name`` repositories."""

        return bool(isinstance(source_id, str) and _SOURCE_ID.match(source_id))

    def default_subdir_parts(self, source_id: str) -> tuple[str, ...]:
        """Flat catalogue: there is no owner/repo split to mirror on disk."""

        return (self.default_subdir,)

    async def fetch_model_card_context(
        self,
        source_id: str,
        filename: str = "",
        *,
        sha256: str = "",
        cache: Optional["ModelSourceCache"] = None,
    ) -> ModelCardContext:
        """Build the card extras from the cached catalogue entry.

        OpenModelDB has no README; the catalogue entry itself carries the
        description, license, tags and example images, so the context is the
        whole card.  The catalogue is bulk-loaded and disk-cached, so no
        per-run memo is needed.
        """

        try:
            client = await OpenModelDBClient.get_instance()
            found = await client.get_model_entry(source_id)
        except Exception as exc:  # never break enrichment on a lookup fault
            logger.debug("OpenModelDB context lookup failed for %s: %s", source_id, exc)
            return ModelCardContext()
        if found is None:
            return ModelCardContext()
        entry = found[1]

        scale = entry.get("scale")
        arch_name = client._resolve_architecture_name(entry)
        # e.g. "ESRGAN 4x" — closest thing upscalers have to a base model,
        # recorded as a hint rather than a canonical base-model name.
        base_hint = (
            f"{arch_name} {scale}x".strip()
            if arch_name and isinstance(scale, (int, float))
            else arch_name
        )
        description = entry.get("description")

        return ModelCardContext(
            description=description if isinstance(description, str) else "",
            model_name=entry.get("name") or source_id,
            license=entry.get("license") or "",
            model_type="Upscaler",
            base_model_aliases=[base_hint] if base_hint else [],
            official_tags=client._resolve_tags(entry),
            example_images=client.example_image_urls(entry),
            source_model_id=source_id,
        )

    async def list_files(
        self, source_id: str, revision: str = ""
    ) -> list[dict[str, Any]]:
        """List the entry's directly downloadable PyTorch resources.

        Resources whose only mirrors are HTML-gateway hosts (mediafire,
        mega.nz, drive.google.com) are skipped: they serve a web page, not
        the file bytes.  When every resource is mirror-only this raises a
        manual-download hint instead of returning an empty list, which the
        download dialog would otherwise misreport as "no model files".
        """

        client = await OpenModelDBClient.get_instance()
        entry = await self._require_entry(client, source_id)

        saw_mirror_only = False
        entries = []
        for resource in entry.get("resources") or []:
            if not isinstance(resource, dict):
                continue
            if str(resource.get("platform") or "").lower() not in _DOWNLOADABLE_PLATFORMS:
                continue
            url = client.direct_url(resource)
            if not url:
                saw_mirror_only = True
                continue
            size = resource.get("size")
            entries.append(
                (
                    client.resource_filename(source_id, resource),
                    size if isinstance(size, (int, float)) else 0,
                )
            )

        if not entries and saw_mirror_only:
            raise ModelSourceError(
                f"None of this model's mirrors support direct download; "
                f"download it manually from {self.canonical_url(source_id)}",
                status=400,
            )

        return filter_weight_files(entries)

    async def resolve_download_url(
        self, source_id: str, filename: str, revision: str = ""
    ) -> str:
        """Resolve the direct download URL of one resource by filename."""

        client = await OpenModelDBClient.get_instance()
        entry = await self._require_entry(client, source_id)

        resource = client.find_resource_by_filename(
            source_id, entry, os.path.basename(filename)
        )
        if resource is None:
            raise ModelSourceError(
                f"'{filename}' is not a downloadable resource of '{source_id}'",
                status=404,
            )
        url = client.direct_url(resource)
        if not url:
            host = urlparse(client.primary_url(resource)).netloc or "this mirror"
            raise ModelSourceError(
                f"This mirror ({host}) requires manual download from "
                f"{self.canonical_url(source_id)}",
                status=400,
            )
        return url

    async def _require_entry(
        self, client: OpenModelDBClient, source_id: str
    ) -> dict[str, Any]:
        """Return the catalogue entry, raising a mapped error otherwise."""

        if not await client.catalogue_ready():
            raise ModelSourceError("OpenModelDB catalogue unavailable", status=502)
        found = await client.get_model_entry(source_id)
        if found is None:
            raise ModelSourceError(
                f"Model '{source_id}' not found on OpenModelDB", status=404
            )
        return found[1]


__all__ = ["OpenModelDBSource"]
