"""ModelScope (魔搭社区) model source.

ModelScope exposes the same "model card as README.md" convention as
Hugging Face, including a YAML frontmatter block that often carries
``base_model:`` and ``trigger_words:``.  Four public endpoints are used,
none of which requires an API key for public models:

* ``/models/{owner}/{name}/resolve/{revision}/README.md`` — raw model card
* ``/api/v1/models/{owner}/{name}/repo?Revision=..&FilePath=README.md`` —
  the same content through the API, used as a fallback when the resolve
  URL is unavailable.
* ``/api/v1/models/{owner}/{name}`` — the model-detail payload behind the
  model page.  It carries the author's summary (``Description``), the
  site-curated tags (``OfficialTags``), and, per published version, the
  model filenames (``MuseInfo.versions[].stats.fileList``) together with
  that file's example images (``coverImages``) and trigger words.  See
  :meth:`ModelScopeSource.fetch_model_card_context`.
* ``/api/v1/models/{owner}/{name}/repo/files?Revision=..`` — the file
  listing backing the download picker.  It reports real sizes for LFS
  files (not the pointer size), so no extra HEAD request is needed.

Downloads go through ``/models/{owner}/{name}/resolve/{revision}/{path}``,
which redirects to a CDN URL carrying a time-limited ``auth_key``.
Requesting the resolve URL fresh on every attempt (which the shared
downloader does, including for resumable Range requests) keeps that key
valid; the CDN URL must never be cached.

The README and the detail payload both describe the whole repository rather
than one file, so a per-run ``ModelSourceCache`` keeps them from being read
again for every checkpoint of a collection repository.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Optional

from .base import (
    ModelCardContext,
    ModelSource,
    ModelSourceError,
    fetch_json,
    fetch_text,
    filter_weight_files,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .base import ModelSourceCache

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

    async def fetch_model_card_context(
        self,
        source_id: str,
        filename: str = "",
        *,
        sha256: str = "",
        cache: Optional["ModelSourceCache"] = None,
    ) -> ModelCardContext:
        """Read the model-detail API that backs the ModelScope model page.

        ModelScope splits a model card in two: ``README.md`` holds the
        long-form content, while the author's summary, the site-curated tags,
        and the per-file example images live only here.  AIGC repositories
        frequently ship an auto-generated README ("the contributor provided
        no further description") and put everything useful in ``Description``,
        so enrichment that reads only the README comes back nearly empty.

        The wanted file is identified by its sha256 when the caller knows it
        and by *filename* otherwise; see :func:`_matching_versions`.  The
        images and trigger words returned belong to that exact
        ``.safetensors`` — essential for collection repositories, where every
        checkpoint has its own sample image.

        The detail payload describes the whole repository and is therefore
        shared across every file in it, so it is read through *cache* when the
        caller supplies one; only the per-file selection is redone.
        """

        data = await self._fetch_detail(source_id, cache=cache)
        if data is None:
            return ModelCardContext()
        return _build_card_context(data, filename, sha256)

    async def _fetch_detail(
        self,
        source_id: str,
        *,
        cache: Optional["ModelSourceCache"] = None,
    ) -> Optional[dict[str, Any]]:
        """Fetch (or reuse) the model-detail payload for *source_id*."""

        cache_key = (self.platform, "detail", source_id)
        if cache is not None and cache_key in cache.provider:
            return cache.provider[cache_key]

        status, payload = await fetch_json(
            f"https://modelscope.cn/api/v1/models/{source_id}"
        )
        if status != 200 or not isinstance(payload, dict):
            logger.debug(
                "ModelScope detail API returned HTTP %s for %s", status, source_id
            )
            return None
        data = payload.get("Data")
        if not isinstance(data, dict):
            return None

        if cache is not None:
            cache.provider[cache_key] = data
        return data

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


# ---------------------------------------------------------------------------
# Model-detail API parsing helpers
# ---------------------------------------------------------------------------

#: Trigger-word values that mean "the author left this blank".
_EMPTY_TRIGGER_VALUES = frozenset({"none", "null", "n/a"})


def _clean_text(value: Any) -> str:
    """Return a stripped string for *value*, or ``""`` for anything else."""

    return value.strip() if isinstance(value, str) else ""


def _first_string(value: Any) -> str:
    """Return the first non-empty string in a list, or ``""``."""

    if isinstance(value, list):
        for item in value:
            text = _clean_text(item)
            if text:
                return text
    return ""


def _build_card_context(
    data: dict[str, Any], filename: str, sha256: str = ""
) -> ModelCardContext:
    """Turn a model-detail payload into a :class:`ModelCardContext`.

    Separated from the HTTP fetch so the repository-wide payload can be cached
    across the files of a collection repository while the per-file selection
    is still redone for each one.
    """

    context = ModelCardContext(
        description=_clean_text(data.get("Description")),
        base_model=_first_string(data.get("BaseModel")),
        base_model_aliases=_base_model_aliases(data),
        official_tags=_official_tags(data.get("OfficialTags")),
    )

    versions = _matching_versions(
        data.get("MuseInfo"),
        filename,
        digests=_file_digests(data),
        sha256=sha256,
    )
    if versions:
        context.example_images = _cover_image_urls(versions)
        context.trigger_words = _version_trigger_words(versions)
    return context


def _base_model_aliases(data: dict[str, Any]) -> list[str]:
    """Return the site's own names for the base model.

    ModelScope publishes a link-style id (``krea/Krea-2-Turbo``) plus its
    internal architecture enums (``VisionFoundation: KREA_2``,
    ``SubVisionFoundation: KREA_2_TURBO``).  The enums are the better
    resolution hint because they normalise onto this system's canonical
    vocabulary, so they come first; the owner prefix is also stripped from
    the link-style ids.
    """

    aliases: list[str] = []
    for key in ("VisionFoundation", "SubVisionFoundation"):
        value = _clean_text(data.get(key))
        if value and value not in aliases:
            aliases.append(value)

    base_models = data.get("BaseModel")
    if isinstance(base_models, list):
        for item in base_models:
            text = _clean_text(item)
            leaf = text.rsplit("/", 1)[-1] if text else ""
            if leaf and leaf not in aliases:
                aliases.append(leaf)
    return aliases


def _official_tags(value: Any) -> list[str]:
    """Extract the site-curated tag values from ``OfficialTags``.

    ModelScope's entries are dicts carrying an English ``Tag`` plus a
    ``ChineseName``; the English value is the curated content vocabulary, so
    that is the one surfaced here.
    """

    tags: list[str] = []
    if not isinstance(value, list):
        return tags
    for entry in value:
        if not isinstance(entry, dict):
            continue
        tag = _clean_text(entry.get("Tag"))
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _version_files(version: dict[str, Any]) -> list[str]:
    """Return the model filenames covered by one ``MuseInfo.versions`` entry.

    The listing normally sits in ``stats.fileList``; some payloads only
    carry the same field as a JSON-encoded string under
    ``modelVersion.stats``, so both shapes are accepted.
    """

    stats = version.get("stats")
    files = stats.get("fileList") if isinstance(stats, dict) else None

    if not isinstance(files, list):
        model_version = version.get("modelVersion")
        raw = model_version.get("stats") if isinstance(model_version, dict) else None
        if isinstance(raw, str) and raw.strip():
            try:
                decoded = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                decoded = None
            if isinstance(decoded, dict):
                files = decoded.get("fileList")

    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, str) and item]


def _version_show_name(version: dict[str, Any]) -> str:
    """Return the human-facing version label (e.g. ``c1-st1000``)."""

    model_version = version.get("modelVersion")
    if not isinstance(model_version, dict):
        return ""
    return _clean_text(model_version.get("showName")).lower()


def _file_digests(data: dict[str, Any]) -> dict[str, str]:
    """Return ``basename -> sha256`` for every published weight file.

    ``ModelInfos`` groups the repository's files by kind (``safetensor``,
    …) and records a real sha256 for each, which is what makes it possible to
    recognise a file the user has renamed.
    """

    digests: dict[str, str] = {}
    model_infos = data.get("ModelInfos")
    if not isinstance(model_infos, dict):
        return digests
    for info in model_infos.values():
        files = info.get("files") if isinstance(info, dict) else None
        if not isinstance(files, list):
            continue
        for entry in files:
            if not isinstance(entry, dict):
                continue
            name = _clean_text(entry.get("name"))
            digest = _clean_text(entry.get("sha256"))
            if name and digest:
                digests.setdefault(os.path.basename(name).lower(), digest.lower())
    return digests


def _matching_versions(
    muse_info: Any,
    filename: str,
    *,
    digests: dict[str, str] | None = None,
    sha256: str = "",
) -> list[dict[str, Any]]:
    """Return the ``versions`` entries that publish the wanted model file.

    Strategies, in order:

    1. **sha256** — the file's content hash, looked up through
       :func:`_file_digests`.  This is the only strategy that survives the
       user renaming the weights, which is common once a model is filed away.
    2. **Exact basename** against each version's ``stats.fileList``.
    3. **``showName`` inside the file stem**, which absorbs the naming drift
       ModelScope sometimes applies to uploaded weights.

    A known-but-unmatched hash falls through to the filename strategies
    rather than giving up, in case the local file was re-encoded.  All matches
    are returned so a file re-published across several versions contributes
    all of its example images.  With no *filename* and no *sha256*, only an
    unambiguous single-version repository is used, because a per-file image
    must never be attributed to the wrong file.
    """

    if not isinstance(muse_info, dict):
        return []
    versions = muse_info.get("versions")
    if not isinstance(versions, list):
        return []
    entries = [entry for entry in versions if isinstance(entry, dict)]
    if not entries:
        return []

    target_hash = (sha256 or "").strip().lower()
    if target_hash:
        known = digests or {}
        by_hash: list[dict[str, Any]] = []
        for version in entries:
            for path in _version_files(version):
                if known.get(os.path.basename(path).lower()) == target_hash:
                    by_hash.append(version)
                    break
        if by_hash:
            return by_hash

    if not filename:
        return entries if len(entries) == 1 else []

    target = os.path.basename(filename).strip().lower()
    if not target:
        return []
    stem = os.path.splitext(target)[0]

    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for version in entries:
        files = {os.path.basename(path).lower() for path in _version_files(version)}
        if target in files:
            exact.append(version)
            continue
        show_name = _version_show_name(version)
        if show_name and show_name in stem:
            fuzzy.append(version)

    return exact or fuzzy


def _cover_image_urls(versions: list[dict[str, Any]]) -> list[str]:
    """Collect the example-image URLs published by the given versions."""

    urls: list[str] = []
    for version in versions:
        covers = version.get("coverImages")
        if not isinstance(covers, list):
            continue
        for cover in covers:
            if not isinstance(cover, dict):
                continue
            url = _clean_text(cover.get("url"))
            if url and url not in urls:
                urls.append(url)
    return urls


def _version_trigger_words(versions: list[dict[str, Any]]) -> list[str]:
    """Return the first non-empty trigger-word list across *versions*."""

    for version in versions:
        model_version = version.get("modelVersion")
        raw = (
            model_version.get("triggerWords")
            if isinstance(model_version, dict)
            else None
        )
        words = _parse_trigger_words(raw)
        if words:
            return words
    return []


def _parse_trigger_words(raw: Any) -> list[str]:
    """Decode ModelScope's JSON-encoded trigger-word string list."""

    if isinstance(raw, list):
        candidates = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(decoded, list):
            return []
        candidates = decoded
    else:
        return []

    words: list[str] = []
    for item in candidates:
        word = _clean_text(item)
        if not word or word.lower() in _EMPTY_TRIGGER_VALUES:
            continue
        if word not in words:
            words.append(word)
    return words
