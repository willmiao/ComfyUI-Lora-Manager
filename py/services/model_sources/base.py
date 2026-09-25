"""Base types for the external model-source provider abstraction.

A *model source* is a third-party site that hosts model files and a model
card (README) describing them — Hugging Face, ModelScope, TensorArt, and
whatever gets added later.  Everything the rest of the codebase needs to
know about such a site is expressed by :class:`ModelSource`:

* how to recognise one of its URLs (:meth:`ModelSource.parse`)
* the canonical page URL for a source id (:meth:`ModelSource.canonical_url`)
* how to fetch the model card (:meth:`ModelSource.fetch_model_card`)
* how to fetch the extras that live *outside* the README
  (:meth:`ModelSource.fetch_model_card_context`)
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
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

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
    "modelscope-ai": "msai",
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


@dataclass
class ModelCardContext:
    """Site-specific extras that accompany a model's README model card.

    A model card is not always just ``README.md``.  ModelScope, for example,
    keeps the author's summary, the site-curated tags, and the per-file
    example images in its model-detail API rather than in the repository.
    Sources with no such extras return an empty context (the default), so
    every field here must be treated as optional by callers.
    """

    description: str = ""
    """Author-written summary shown on the model page, outside the README."""

    model_name: str = ""
    """Site-published display name for the repository.

    Sites publish this next to the repository id (ModelScope's ``Name``).
    It is what a CivitAI download would store as the model's name, so the
    card never has to fall back to the local filename.
    """

    model_name_localized: str = ""
    """Site-published localized name (ModelScope's ``ChineseName``)."""

    version_name: str = ""
    """Site-published label for the requested file's version.

    Resolved per file, like :attr:`example_images`: a repository publishes
    one label per checkpoint (ModelScope's ``modelVersion.showName``).
    """

    license: str = ""
    """License the site records for the repository."""

    model_type: str = ""
    """Site-reported model type, e.g. ModelScope's ``AigcType`` (``LoRA``)."""

    base_model: str = ""
    """Base model as reported by the site (possibly a site-local id)."""

    base_model_aliases: list[str] = field(default_factory=list)
    """Other names the site uses for the same base model.

    Sites often publish both a link-style id (``krea/Krea-2-Turbo``) and an
    internal architecture enum (``KREA_2``).  The enum usually normalises
    cleanly onto this system's canonical vocabulary, so it is the better
    resolution hint for :mod:`py.services.agent.base_model_resolver`.
    """

    official_tags: list[str] = field(default_factory=list)
    """Content tags curated by the site itself."""

    example_images: list[str] = field(default_factory=list)
    """Absolute URLs of example images for the requested model file."""

    trigger_words: list[str] = field(default_factory=list)
    """Trigger words the site records for the requested model file."""

    source_model_id: str = ""
    """Site-native id of the *published model* the requested file belongs to.

    Sites whose repository is not a model identity publish a separate,
    stable id per model (ModelScope's ``modelVersion.modelId`` — identical
    across every version of one published model, different between the
    models of a collection repository).  It is the version-grouping key,
    persisted on the sidecar as ``source_model_id``.
    """

    source_version_id: str = ""
    """Site-native id of the published version the requested file belongs to
    (ModelScope's ``modelVersion.id``), persisted as ``source_version_id``."""

    def is_empty(self) -> bool:
        """Return ``True`` when the site contributed nothing extra."""

        return not any(
            (
                self.description,
                self.model_name,
                self.model_name_localized,
                self.version_name,
                self.license,
                self.model_type,
                self.base_model,
                self.base_model_aliases,
                self.official_tags,
                self.example_images,
                self.trigger_words,
                self.source_model_id,
                self.source_version_id,
            )
        )


class ModelSourceError(Exception):
    """Raised when a model source cannot satisfy a request.

    Carries the HTTP status the API handler should answer with, so the
    handlers stay free of per-site error mapping.
    """

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


class ModelSourceCache:
    """Per-run memo shared between the agent pipeline and a model source.

    A collection repository publishes many model files under a single source
    id, so enriching each file re-fetches the same README and the same
    repository metadata.  One cache is created per enrichment run and thrown
    away afterwards: nothing is retained across runs (a model card can change
    at any time), and download URLs are never routed through it.
    """

    def __init__(self) -> None:
        #: Provider-agnostic: ``"<platform>:<source_id>"`` → raw README text.
        self.readmes: Dict[str, str] = {}
        #: Provider-owned scratch space.  Keys must be namespaced by the
        #: provider (``(platform, kind, source_id)``) so two providers can
        #: never collide.  Only successful results should be stored, so a
        #: transient failure is still retried for the next file.
        self.provider: Dict[Any, Any] = {}


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


async def fetch_text(
    url: str, *, timeout: int = HTTP_TIMEOUT, headers: Optional[Dict[str, str]] = None
) -> str:
    """Fetch *url* and return its body as text, or ``""`` on any failure.

    Network problems are expected (offline installs, rate limits, dead
    repos) and must never bubble up into the pipeline, so every error is
    logged at debug level and normalised to an empty string.
    """

    try:
        request_headers = {"User-Agent": USER_AGENT}
        if headers:
            request_headers.update(headers)
        async with aiohttp.ClientSession(
            headers=request_headers,
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
    url: str, *, timeout: int = HTTP_TIMEOUT, headers: Optional[Dict[str, str]] = None
) -> tuple[int, Any]:
    """Fetch *url* and return ``(status, parsed_body)``.

    Unlike :func:`fetch_text` this reports the status, because callers such as
    the file-listing endpoints need to distinguish "repo not found" (404) from
    a transport failure.  ``parsed_body`` is ``None`` when the response is not
    JSON or the request failed outright (status ``0``).
    """

    try:
        request_headers = {"User-Agent": USER_AGENT}
        if headers:
            request_headers.update(headers)
        async with aiohttp.ClientSession(
            headers=request_headers,
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

    def group_key(self, ref: SourceRef, item: Mapping[str, Any]) -> Optional[str]:
        """Return the version-group key for the model described by *item*.

        The default groups by source id (``{prefix}:{owner}/{repo}``), which
        is only correct when the source id already identifies a single
        published model.  Sources whose repository hosts many unrelated
        models override this: they either derive the key from a site-native
        model identity recorded in *item* (ModelScope's ``source_model_id``)
        or return ``None`` when the platform has no reliable model identity
        at all (Hugging Face), leaving the model ungrouped.
        """

        prefix = GROUP_PREFIXES.get(self.platform, self.platform)
        return f"{prefix}:{ref.source_id}"

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch the raw model card (README) markdown for *source_id*."""

        return ""

    async def fetch_model_card_context(
        self,
        source_id: str,
        filename: str = "",
        *,
        sha256: str = "",
        cache: Optional["ModelSourceCache"] = None,
    ) -> ModelCardContext:
        """Return the card extras the site keeps outside the README.

        *filename* is the model file's basename (no directory) and *sha256*
        its content hash; between them they select the right entry when a
        repository holds several models.  A site that records per-file hashes
        should prefer *sha256*, because it is the only identifier that
        survives the user renaming the weights.

        *cache* is an optional per-run memo (see :class:`ModelSourceCache`)
        that lets a provider avoid re-fetching repository-wide data for every
        file in a collection repository.

        Sites whose model card is fully described by :meth:`fetch_model_card`
        need no override and inherit this empty context.

        Implementations must never raise: enrichment treats a missing
        context as "the site had nothing extra to say".
        """

        return ModelCardContext()

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

    def auth_headers(self) -> Dict[str, str]:
        """Extra request headers this site needs for API and file downloads.

        Empty by default; sites with gated/private content (Hugging Face)
        override it to attach the user's access token when one is configured.
        """

        return {}

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
    "ModelCardContext",
    "ModelSource",
    "ModelSourceCache",
    "ModelSourceError",
    "SourceRef",
    "USER_AGENT",
    "clean_source_url",
    "fetch_json",
    "fetch_text",
    "filter_weight_files",
    "is_valid_source_id",
]
