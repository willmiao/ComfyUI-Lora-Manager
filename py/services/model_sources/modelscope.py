"""ModelScope (魔搭社区) model sources.

ModelScope exposes the same "model card as README.md" convention as
Hugging Face, including a YAML frontmatter block that often carries
``base_model:`` and ``trigger_words:``.  Four public endpoints are used,
none of which requires an API key for public models:

* ``/models/{owner}/{name}/resolve/{revision}/README.md`` — raw model card
* ``/api/v1/models/{owner}/{name}/repo?Revision=..&FilePath=README.md`` —
  the same content through the API, used as a fallback when the resolve
  URL is unavailable.
* ``/api/v1/models/{owner}/{name}`` — the model-detail payload behind the
  model page.  It carries the repository's display name (``Name`` /
  ``ChineseName``), the author's summary (``Description``), the license, the
  AIGC type, the site tags (``OfficialTags``, falling back to ``Tags``), and,
  per published version, the model filenames
  (``MuseInfo.versions[].stats.fileList``) together with that version's label
  (``modelVersion.showName``), example images (``coverImages``) and trigger
  words.  See :meth:`ModelScopeSource.fetch_model_card_context`.
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

Two deployments are served by this module.  ``modelscope.cn`` (with
``modelscope.com`` as a redirect alias) and ``modelscope.ai`` are *separate
catalogues*, not mirrors, so they are registered as distinct sources:
:class:`ModelScopeSource` and :class:`ModelScopeIntlSource`.  Every URL either
class builds is derived from its ``base_url``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional

from .base import (
    GROUP_PREFIXES,
    ModelCardContext,
    ModelSource,
    ModelSourceError,
    SourceRef,
    clean_source_url,
    fetch_json,
    fetch_text,
    filter_weight_files,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .base import ModelSourceCache

logger = logging.getLogger(__name__)

#: ModelScope runs two independent catalogues.  ``modelscope.com`` is a
#: redirect alias of the mainland site, but ``modelscope.ai`` is the
#: *international* deployment with its own repository catalogue — a repository
#: published on one is routinely absent from the other (``referall13/EM1``
#: exists only on ``.ai``, ``jj3550945163/Krea-2-LORA`` only on ``.cn``).  The
#: host therefore decides which site, API and CDN a model belongs to, and the
#: two deployments are registered as separate sources rather than folded into
#: one id.
_MAINLAND_HOSTS = r"modelscope\.(?:cn|com)"
_INTERNATIONAL_HOSTS = r"modelscope\.ai"

#: Trailing view segments the site appends to a model URL; accepted verbatim
#: when the user pastes a browser tab URL.
_VIEW_SEGMENTS = r"(?:summary|files|model-file|readme|community|evaluation)?"


def _url_patterns(hosts: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Build the lenient and strict model-URL patterns for *hosts*."""

    body = rf"https?://(?:www\.)?(?:{hosts})/models/(?P<id>[^/?#\s]+/[^/?#\s]+)"
    return re.compile(body), re.compile(rf"{body}/?{_VIEW_SEGMENTS}/?$")


#: ``master`` is ModelScope's default branch; ``main`` is tried as a fallback
#: for repos imported from Hugging Face.
_REVISIONS = ("master", "main")


class ModelScopeSource(ModelSource):
    """ModelScope's mainland site (``modelscope.cn``).

    ``modelscope.com`` is accepted as an alias of it.  The international
    deployment is :class:`ModelScopeIntlSource`; everything below is written in
    terms of ``base_url`` so both share one implementation.
    """

    platform = "modelscope"
    label = "ModelScope"
    supports_enrichment = True
    supports_download = True
    default_revision = "master"
    default_subdir = "modelscope"

    #: Origin every outgoing URL is built from.
    base_url = "https://modelscope.cn"

    url_pattern, strict_url_pattern = _url_patterns(_MAINLAND_HOSTS)

    def canonical_url(self, source_id: str) -> str:
        return f"{self.base_url}/models/{source_id}"

    def group_key(self, ref: SourceRef, item: Mapping[str, Any]) -> Optional[str]:
        """Group by ModelScope's published-model id, never by repository.

        A collection repository hosts many unrelated published models, so
        the repo id is not a version-group identity.  Only models whose
        metadata carries the site-native ``source_model_id`` (recorded at
        enrichment time from ``MuseInfo.versions[].modelVersion.modelId``)
        group together; unenriched models stay standalone.
        """

        model_id = clean_source_url(item.get("source_model_id"))
        if not model_id:
            return None
        prefix = GROUP_PREFIXES.get(self.platform, self.platform)
        return f"{prefix}:{model_id}"

    def asset_base_url(self, source_id: str, revision: str = "") -> str:
        return (
            f"{self.base_url}/models/{source_id}/resolve/"
            f"{self.resolve_revision(revision)}"
        )

    async def fetch_model_card(self, source_id: str) -> str:
        """Fetch the model card, preferring the raw resolve URL."""

        for revision in _REVISIONS:
            text = await fetch_text(
                f"{self.base_url}/models/{source_id}/resolve/{revision}/README.md"
            )
            if text:
                return text

        # Fallback: the repo API proxies the same file and is reachable in
        # environments where the CDN resolve host is blocked.
        for revision in _REVISIONS:
            text = await fetch_text(
                f"{self.base_url}/api/v1/models/"
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
            f"{self.base_url}/api/v1/models/{source_id}"
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
            f"{self.base_url}/api/v1/models/"
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
            f"{self.base_url}/models/{source_id}/resolve/"
            f"{self.resolve_revision(revision)}/{filename}"
        )

    def page_url_for_file(self, source_id: str, filename: str) -> str:
        return (
            f"{self.base_url}/models/{source_id}/file/view/"
            f"{self.default_revision}/{filename}"
        )


class ModelScopeIntlSource(ModelScopeSource):
    """ModelScope's international site (``modelscope.ai``).

    A separate catalogue rather than a mirror, so it is registered under its
    own platform id: the two deployments must not share a version group, a
    "use default paths" directory, or a stored ``source_url``.  The detail API,
    the file listing, the resolve URLs and the CDN redirect all behave exactly
    like the mainland site, which is why every URL here is derived from
    :attr:`base_url` instead of being duplicated.
    """

    platform = "modelscope-ai"
    label = "ModelScope (International)"
    default_subdir = "modelscope-ai"
    base_url = "https://www.modelscope.ai"

    url_pattern, strict_url_pattern = _url_patterns(_INTERNATIONAL_HOSTS)


__all__ = ["ModelScopeIntlSource", "ModelScopeSource"]


# ---------------------------------------------------------------------------
# Model-detail API parsing helpers
# ---------------------------------------------------------------------------

#: Trigger-word values that mean "the author left this blank".
_EMPTY_TRIGGER_VALUES = frozenset({"none", "null", "n/a"})

#: Repository tags that only restate what the model *is* (its library, task or
#: framework) rather than what it depicts.  ModelScope mixes both into the
#: plain ``Tags`` list, and a card tagged "lora" or "text-to-image" is noise.
_GENERIC_TAGS = frozenset(
    {
        "any-to-any",
        "checkpoint",
        "controlnet",
        "diffusers",
        "embedding",
        "image-text-to-text",
        "image-to-image",
        "image-to-video",
        "lora",
        "lycoris",
        "onnx",
        "pytorch",
        "safetensors",
        "tensorflow",
        "text-to-image",
        "text-to-speech",
        "text-to-video",
        "textual-inversion",
        "vae",
    }
)


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
        model_name=_clean_text(data.get("Name")),
        model_name_localized=_clean_text(data.get("ChineseName")),
        license=_clean_text(data.get("License")),
        model_type=_clean_text(data.get("AigcType")),
        base_model=_first_string(data.get("BaseModel")),
        base_model_aliases=_base_model_aliases(data),
        official_tags=_official_tags(data),
    )

    versions = _matching_versions(
        data.get("MuseInfo"),
        filename,
        digests=_file_digests(data),
        sha256=sha256,
    )
    if versions:
        context.version_name = _version_label(versions)
        context.example_images = _cover_image_urls(versions)
        context.trigger_words = _version_trigger_words(versions)
        context.source_model_id, context.source_version_id = _version_identity(
            versions
        )
    return context


def _version_identity(versions: list[dict[str, Any]]) -> tuple[str, str]:
    """Return the site-native ``(model id, version id)`` of the first match.

    ``modelVersion.modelId`` is identical across every version of one
    published model and differs between the models of a collection
    repository, which makes it the version-grouping identity;
    ``modelVersion.id`` identifies the version itself.  Both are ints in
    the payload and are stored as strings.
    """

    for version in versions:
        model_version = version.get("modelVersion")
        if not isinstance(model_version, dict):
            continue
        model_id = model_version.get("modelId")
        version_id = model_version.get("id")
        if model_id is None and version_id is None:
            continue
        return (
            str(model_id) if model_id is not None else "",
            str(version_id) if version_id is not None else "",
        )
    return "", ""


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


def _official_tags(data: dict[str, Any]) -> list[str]:
    """Return the content tags the site publishes for the repository.

    ``OfficialTags`` is ModelScope's curated content vocabulary and is
    preferred whenever it is populated.  Plenty of AIGC repositories leave it
    empty and carry only the plain ``Tags`` list, which mixes content tags with
    framework and task categories; those categories are dropped so a card is
    not handed "lora" and "text-to-image" as if they described the model.
    """

    curated = _dedupe(_tag_values(data.get("OfficialTags")))
    if curated:
        return curated

    generic = set(_GENERIC_TAGS)
    for value in (
        data.get("AigcType"),
        data.get("Libraries"),
        data.get("Frameworks"),
    ):
        for item in value if isinstance(value, list) else [value]:
            text = _clean_text(item).lower()
            if text:
                generic.add(text)

    return _dedupe(
        tag for tag in _tag_values(data.get("Tags")) if tag.lower() not in generic
    )


def _tag_values(value: Any) -> list[str]:
    """Return the tag strings from either shape ModelScope publishes.

    ``OfficialTags`` is a list of ``{"Tag": ..., "ChineseName": ...}`` dicts
    carrying an English value; the plain ``Tags`` list is already strings.
    """

    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for entry in value:
        tag = _clean_text(entry.get("Tag") if isinstance(entry, dict) else entry)
        if tag:
            tags.append(tag)
    return tags


def _dedupe(values: Iterable[str]) -> list[str]:
    """Drop empties and repeats, keeping the first spelling seen."""

    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


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


def _version_label(versions: list[dict[str, Any]]) -> str:
    """Return the first published version label, preserving its spelling.

    Unlike :func:`_version_show_name` this is for display, so the label is
    not lowercased.
    """

    for version in versions:
        model_version = version.get("modelVersion")
        if not isinstance(model_version, dict):
            continue
        label = _clean_text(model_version.get("showName"))
        if label:
            return label
    return ""


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
