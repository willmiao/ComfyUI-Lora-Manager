"""Base types for the external model-source provider abstraction.

A *model source* is a third-party site that hosts model files and a model
card (README) describing them — Hugging Face, ModelScope, TensorArt, and
whatever gets added later.  Everything the rest of the codebase needs to
know about such a site is expressed by :class:`ModelSource`:

* how to recognise one of its URLs (:meth:`ModelSource.parse`)
* the canonical page URL for a source id (:meth:`ModelSource.canonical_url`)
* how to fetch the model card (:meth:`ModelSource.fetch_model_card`)
* how to turn repository-relative asset paths into absolute URLs
  (:meth:`ModelSource.asset_base_url`)
* which capabilities the site actually supports
  (``supports_enrichment`` / ``supports_download``)

Keeping this in one place means the agent pipeline, the scanners, and the
HTTP handlers never need site-specific branching.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import aiohttp

from ...utils.constants import MODEL_FILE_EXTENSIONS

logger = logging.getLogger(__name__)

#: Shared HTTP timeout for model-card fetches.
HTTP_TIMEOUT = 30

#: User agent used for all model-source HTTP requests.
USER_AGENT = "ComfyUI-LoRA-Manager/1.0"

#: Platform → short prefix used when building version-group keys.
#: ``huggingface`` keeps the historical ``hf:`` prefix for backward
#: compatibility with already-cached group keys.
GROUP_PREFIXES: dict[str, str] = {
    "huggingface": "hf",
    "modelscope": "ms",
    "tensorart": "ta",
}


@dataclass(frozen=True)
class SourceRef:
    """A parsed reference to a model hosted on an external site."""

    platform: str
    """Canonical platform id, e.g. ``"huggingface"``."""

    source_id: str
    """Site-specific identity, e.g. ``"user/repo"`` or ``"827823520299086029"``."""

    url: str
    """Canonical URL of the model page."""


class ModelSourceError(Exception):
    """Raised when a model source cannot satisfy a request.

    Carries the HTTP status the API handler should answer with, so the
    handlers stay free of per-site error mapping.
    """

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


#: Repository ids are always exactly ``owner/name``. Components may contain
#: dots (``black-forest-labs/FLUX.1-dev``) but must not be empty, ``.`` / ``..``,
#: or start with a dot - the id is used as a path segment on disk.
_SOURCE_ID_COMPONENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


def is_valid_source_id(source_id: str) -> bool:
    """Return ``True`` when *source_id* is a safe ``owner/name`` repository id."""

    if not source_id or not isinstance(source_id, str) or source_id.count("/") != 1:
        return False
    owner, name = source_id.split("/", 1)
    return all(
        part and part not in (".", "..") and _SOURCE_ID_COMPONENT.match(part)
        for part in (owner, name)
    )


async def fetch_text(url: str, *, timeout: int = HTTP_TIMEOUT) -> str:
    """Fetch *url* and return its body as text, or ``""`` on any failure.

    Network problems are expected (offline installs, rate limits, dead
    repos) and must never bubble up into the pipeline, so every error is
    logged at debug level and normalised to an empty string.
    """

    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.debug("Fetch %s returned HTTP %s", url, resp.status)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.debug("Failed to fetch %s: %s", url, exc)
    return ""


async def fetch_json(
    url: str, *, timeout: int = HTTP_TIMEOUT
) -> tuple[int, Any]:
    """Fetch *url* and return ``(status, parsed_body)``.

    Unlike :func:`fetch_text` this reports the status, because callers such as
    the file-listing endpoints need to distinguish "repo not found" (404) from
    a transport failure.  ``parsed_body`` is ``None`` when the response is not
    JSON or the request failed outright (status ``0``).
    """

    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return resp.status, None
                try:
                    return resp.status, await resp.json(content_type=None)
                except Exception:
                    return resp.status, None
    except Exception as exc:  # pragma: no cover - network dependent
        logger.debug("Failed to fetch %s: %s", url, exc)
        return 0, None


class ModelSource:
    """Description and I/O for one external model hosting site."""

    #: Canonical platform id stored in metadata.
    platform: str = ""

    #: Human-readable name used in UI copy and prompts.
    label: str = ""

    #: Whether the agent skill can fetch a model card and run AI extraction.
    supports_enrichment: bool = False

    #: Whether models can be downloaded directly from this site.
    supports_download: bool = False

    #: Branch used when the caller does not pass an explicit revision.
    default_revision: str = ""

    #: Sub-directory the "use default paths" template places downloads in.
    default_subdir: str = ""

    #: Lenient pattern used to recognise URLs already stored in metadata.
    #: Captures the site-specific source id in group ``id``.
    url_pattern: re.Pattern[str] | None = None

    #: Strict pattern used to validate user input.  Must match the whole URL.
    strict_url_pattern: re.Pattern[str] | None = None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse(self, url: str, *, strict: bool = False) -> Optional[str]:
        """Return the source id contained in *url*, or ``None``.

        With ``strict=True`` the URL must match this site's canonical shape
        exactly (used when validating what a user pasted); with
        ``strict=False`` sub-paths such as ``/resolve/main/file.bin`` are
        tolerated (used when normalising already-stored values).
        """

        if not url or not isinstance(url, str):
            return None
        candidate = url.strip()
        if not candidate:
            return None
        pattern = self.strict_url_pattern if strict else self.url_pattern
        if pattern is None:
            return None
        match = pattern.match(candidate)
        return match.group("id") if match else None

    def ref(self, url: str, *, strict: bool = False) -> Optional[SourceRef]:
        """Return a :class:`SourceRef` for *url*, or ``None`` if not ours."""

        source_id = self.parse(url, strict=strict)
        if not source_id:
            return None
        return SourceRef(
            platform=self.platform,
            source_id=source_id,
            url=self.canonical_url(source_id),
        )

    # ------------------------------------------------------------------
    # URLs and content
    # ------------------------------------------------------------------

    def canonical_url(self, source_id: str) -> str:
        """Return the canonical model-page URL for *source_id*."""

        raise NotImplementedError

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        """Base URL used to resolve repository-relative asset paths."""

        return ""

    def group_key(self, source_id: str) -> str:
        """Return the version-group key for *source_id*."""

        prefix = GROUP_PREFIXES.get(self.platform, self.platform)
        return f"{prefix}:{source_id}"

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch the raw model card (README) markdown for *source_id*."""

        return ""

    # ------------------------------------------------------------------
    # Download support
    # ------------------------------------------------------------------

    async def list_files(
        self, source_id: str, revision: str = ""
    ) -> list[dict[str, Any]]:
        """List downloadable weight files in *source_id*.

        Returns ``[{"filename": <repo-relative path>, "size": <bytes>}]``,
        largest first, filtered to :data:`MODEL_FILE_EXTENSIONS`.  Sites
        without download support return an empty list.

        Raises :class:`ModelSourceError` when the repository cannot be read,
        so the handler can surface "not found" separately from a transport
        failure.
        """

        return []

    def file_download_url(
        self, source_id: str, filename: str, revision: str = ""
    ) -> str:
        """Return the direct (redirecting) download URL for one file."""

        raise ModelSourceError(
            f"{self.label or self.platform} does not support downloads", status=400
        )

    def resolve_revision(self, revision: str = "") -> str:
        """Return *revision*, falling back to this site's default branch."""

        return revision or self.default_revision

    def page_url_for_file(self, source_id: str, filename: str) -> str:
        """Return the human-facing page for *filename* inside *source_id*."""

        return self.canonical_url(source_id)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ModelSource {self.platform}>"


def clean_source_url(url: Any) -> str:
    """Normalise a stored source URL value into a stripped string."""

    if not isinstance(url, str):
        return ""
    return url.strip()


def filter_weight_files(entries: Iterable[tuple[str, int]]) -> list[dict[str, Any]]:
    """Keep model-weight files from ``(path, size)`` pairs, largest first.

    Every site lists a lot more than weights (READMEs, configs, tokenizers,
    …); the download picker only ever wants the files ComfyUI can load, which
    is exactly :data:`MODEL_FILE_EXTENSIONS`.
    """

    files = [
        {"filename": path, "size": int(size or 0)}
        for path, size in entries
        if path and os.path.splitext(path)[1].lower() in MODEL_FILE_EXTENSIONS
    ]
    files.sort(key=lambda entry: entry["size"], reverse=True)
    return files


__all__ = [
    "GROUP_PREFIXES",
    "HTTP_TIMEOUT",
    "ModelSource",
    "ModelSourceError",
    "SourceRef",
    "USER_AGENT",
    "clean_source_url",
    "fetch_json",
    "fetch_text",
    "filter_weight_files",
    "is_valid_source_id",
]
