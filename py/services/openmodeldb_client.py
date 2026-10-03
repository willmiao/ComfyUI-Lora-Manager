"""Client for the OpenModelDB bulk JSON API.

OpenModelDB (https://openmodeldb.info) is a static catalogue of upscaler
models. It exposes no per-model or by-hash endpoint — only bulk JSON dumps
(``/api/v1/models.json`` and friends), so this client downloads the dumps
once, caches them on disk with a TTL, honors ETag/Last-Modified on refresh,
and builds an in-memory SHA256 -> model index for read-only metadata lookups.

Every catalogue resource carries a ``sha256`` and a byte ``size``, which is
what makes hash-based matching against local files possible. Lookups degrade
gracefully: when the catalogue cannot be fetched (offline, upstream failure)
the stale disk cache is used, and if there is no cache at all the lookup
reports "not found" so the metadata fallback chain simply moves on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .downloader import get_downloader
from .errors import RateLimitError
from ..utils.cache_paths import get_cache_base_dir
from ..utils.constants import MODEL_FILE_EXTENSIONS

logger = logging.getLogger(__name__)

OPENMODELDB_API_BASE = "https://openmodeldb.info/api/v1"
OPENMODELDB_SITE_BASE = "https://openmodeldb.info"

#: Value emitted as ``source`` in the synthesized version dict; the metadata
#: sync service persists it as the model's ``metadata_source``.
METADATA_SOURCE_VALUE = "openmodeldb"

#: Hosts whose URLs serve an HTML interstitial page instead of the raw file
#: bytes. Downloading from them would silently save a web page as ``.pth``
#: (the download flow does not verify the sha256 afterwards), so the model
#: source layer rejects them with a manual-download hint. Kept deliberately
#: small and explicit.
HTML_GATEWAY_HOSTS = frozenset({"mediafire.com", "mega.nz", "drive.google.com"})


def is_html_gateway_url(url: str) -> bool:
    """Return ``True`` when *url* points at a known HTML-gateway host."""

    if not isinstance(url, str) or not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(host == g or host.endswith(f".{g}") for g in HTML_GATEWAY_HOSTS)


def _is_ephemeral_viewer_url(url: str) -> bool:
    """Return ``True`` for imgdiff.net session URLs.

    Paired comparisons are hosted as ephemeral imgdiff viewer sessions
    (``/api/image.php?id=...``) that expire shortly after the site build;
    they 404 when used as an ``<img>`` source and must never be emitted as a
    displayable image URL.
    """

    return isinstance(url, str) and "imgdiff.net/api/" in url

#: Bulk dumps consumed by the client. Only ``models`` is strictly required;
#: the rest resolve ids to human-readable names and degrade to raw ids.
_DUMP_NAMES = ("models", "users", "tags", "architectures")

#: How long a fetched catalogue is considered fresh before a revalidation
#: request is made. The site only changes when it is rebuilt (hours to days),
#: so a daily TTL avoids re-downloading the ~1.4MB models dump on every
#: lookup while still picking up new models reasonably fast.
CACHE_TTL_SECONDS = 24 * 60 * 60

_META_FILENAME = "_meta.json"


class OpenModelDBClient:
    """Hash-lookup client over a locally cached OpenModelDB catalogue dump."""

    _instance: Optional["OpenModelDBClient"] = None
    _instance_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "OpenModelDBClient":
        """Get the singleton instance of OpenModelDBClient."""
        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()

                # Register this client as a metadata provider (mirrors the
                # CivitAI/CivArchive client bootstrap).
                from .model_metadata_provider import (
                    ModelMetadataProviderManager,
                    OpenModelDBModelMetadataProvider,
                )

                provider_manager = await ModelMetadataProviderManager.get_instance()
                provider_manager.register_provider(
                    "openmodeldb",
                    OpenModelDBModelMetadataProvider(cls._instance),
                    False,
                )

            return cls._instance

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        # Guard re-initialization for the singleton pattern.
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._cache_dir_override = cache_dir
        self._ttl_seconds = ttl_seconds

        self._models: Dict[str, Dict[str, Any]] = {}
        self._users: Dict[str, Dict[str, Any]] = {}
        self._tags: Dict[str, Dict[str, Any]] = {}
        self._architectures: Dict[str, Dict[str, Any]] = {}
        # sha256 (lowercase) -> (model_id, model entry, matching resource)
        self._index: Dict[str, Tuple[str, Dict[str, Any], Dict[str, Any]]] = {}
        self._loaded_at: float = 0.0
        self._load_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_model_by_hash(
        self, model_hash: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Find an upscaler model by SHA256 hash.

        Returns a CivitAI-shaped version dict (same contract as the other
        metadata providers) or ``(None, reason)``.
        """
        if not model_hash or not isinstance(model_hash, str):
            return None, "Model not found"

        try:
            loaded = await self._ensure_loaded()
        except RateLimitError:
            raise
        except Exception as exc:
            logger.error("OpenModelDB lookup failed for %s: %s", model_hash[:10], exc)
            return None, str(exc)

        if not loaded:
            return None, "OpenModelDB catalogue unavailable"

        hit = self._index.get(model_hash.lower())
        if hit is None:
            return None, "Model not found"

        model_id, model_entry, resource = hit
        return self._to_civitai_version(model_id, model_entry, resource), None

    async def catalogue_ready(self) -> bool:
        """Return ``True`` when the catalogue is loaded (or loadable)."""

        try:
            return await self._ensure_loaded()
        except RateLimitError:
            raise
        except Exception as exc:
            logger.error("OpenModelDB catalogue load failed: %s", exc)
            return False

    async def get_model_entry(
        self, model_id: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Return ``(model_id, catalogue entry)`` for *model_id*, or ``None``.

        Loads the catalogue on first use; an unavailable catalogue and an
        unknown id both yield ``None`` (callers that need to distinguish the
        two can check :meth:`catalogue_ready` first).
        """
        if not model_id or not isinstance(model_id, str):
            return None
        if not await self.catalogue_ready():
            return None
        entry = self._models.get(model_id)
        if not isinstance(entry, dict):
            return None
        return model_id, entry

    def find_resource_by_filename(
        self, model_id: str, entry: Dict[str, Any], filename: str
    ) -> Optional[Dict[str, Any]]:
        """Match a resource by its derived filename (see :meth:`resource_filename`)."""
        target = (filename or "").strip().lower()
        if not target:
            return None
        for resource in entry.get("resources") or []:
            if not isinstance(resource, dict):
                continue
            if self.resource_filename(model_id, resource).lower() == target:
                return resource
        return None

    @staticmethod
    def resource_filename(model_id: str, resource: Dict[str, Any]) -> str:
        """Derive the local filename for a catalogue resource.

        The download URL's basename is not authoritative — mirrors like
        mediafire put the real filename mid-path
        (``/file/<key>/90s_Sonic_2x.pth/file``) and folder links (mega.nz)
        have no filename at all.  Strategy: the first URL path segment whose
        extension is a known model format, else ``{model_id}.{type}`` (the
        catalogue's ``type`` field is authoritative).
        """
        urls = resource.get("urls")
        for url in urls if isinstance(urls, list) else []:
            if not isinstance(url, str):
                continue
            path = url.split("?", 1)[0].split("#", 1)[0]
            for segment in path.split("/"):
                if os.path.splitext(segment)[1].lower() in MODEL_FILE_EXTENSIONS:
                    return segment
        resource_type = str(resource.get("type") or "").lower()
        extension = (
            resource_type if resource_type in {"pth", "safetensors", "onnx"} else "bin"
        )
        return f"{model_id}.{extension}"

    @staticmethod
    def primary_url(resource: Dict[str, Any]) -> str:
        """Return the resource's primary download URL.

        Only the first URL is used: additional entries are mirrors that may
        need site-specific handling (e.g. mega.nz) and are never tried
        automatically.
        """
        urls = resource.get("urls")
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url.startswith("http"):
                    return url
        return ""

    @staticmethod
    def direct_url(resource: Dict[str, Any]) -> str:
        """Return the first URL that serves raw bytes, or ``""``.

        HTML-gateway hosts (mediafire, mega.nz, drive.google.com — see
        :data:`HTML_GATEWAY_HOSTS`) serve an interstitial page instead of the
        file, so they are skipped here and reported to the user instead.
        """
        urls = resource.get("urls")
        if isinstance(urls, list):
            for url in urls:
                if (
                    isinstance(url, str)
                    and url.startswith("http")
                    and not is_html_gateway_url(url)
                ):
                    return url
        return ""

    @staticmethod
    def _absolutize(url: str) -> str:
        """Turn a site-relative path (``/thumbs/...``) into an absolute URL."""

        if isinstance(url, str) and url.startswith("/"):
            return f"{OPENMODELDB_SITE_BASE}{url}"
        return url

    def _paired_display_url(self, image: Dict[str, Any]) -> str:
        """Return the displayable URL for a paired comparison image.

        Prefers the site-hosted thumbnail: the ``LR``/``SR`` originals are
        frequently ephemeral imgdiff session URLs that 404 outside the
        viewer.  Falls back to the SR (then LR) original only when it is not
        one of those session URLs.
        """
        thumbnail = image.get("thumbnail")
        if isinstance(thumbnail, str) and thumbnail:
            return self._absolutize(thumbnail)
        for key in ("SR", "LR"):
            original = image.get(key)
            if (
                isinstance(original, str)
                and original
                and not _is_ephemeral_viewer_url(original)
            ):
                return original
        return ""

    def _model_preview_url(self, entry: Dict[str, Any]) -> str:
        """Return the model-level thumbnail URL, mirroring the site's own
        ``getPreviewImage`` precedence (paired → SR, standalone → url)."""
        thumbnail = entry.get("thumbnail")
        if not isinstance(thumbnail, dict):
            return ""
        if thumbnail.get("type") == "paired":
            url = thumbnail.get("SR") or thumbnail.get("LR")
        else:
            url = thumbnail.get("url")
        if isinstance(url, str) and url:
            return self._absolutize(url)
        return ""

    def example_image_urls(self, entry: Dict[str, Any]) -> List[str]:
        """Return displayable example-image URLs, model thumbnail first.

        Never contains ephemeral imgdiff session URLs; standalone images keep
        their direct URLs (regular image hosts are hotlinkable).
        """
        urls: List[str] = []
        lead = self._model_preview_url(entry)
        if lead:
            urls.append(lead)
        for image in entry.get("images") or []:
            if not isinstance(image, dict):
                continue
            if image.get("type") == "paired":
                url = self._paired_display_url(image)
            else:
                url = image.get("url")
            if isinstance(url, str) and url and url not in urls:
                urls.append(url)
        return urls

    # ------------------------------------------------------------------
    # Catalogue loading
    # ------------------------------------------------------------------

    async def _ensure_loaded(self) -> bool:
        """Ensure the in-memory index is built, refreshing stale caches."""
        async with self._load_lock:
            if self._index and (time.monotonic() - self._loaded_at) < self._ttl_seconds:
                return True

            meta = self._read_meta()
            fetched_at = float(meta.get("fetched_at") or 0.0)
            disk_fresh = (
                fetched_at > 0
                and (time.time() - fetched_at) < self._ttl_seconds
                and all(os.path.exists(self._dump_path(name)) for name in _DUMP_NAMES)
            )

            if disk_fresh:
                if self._load_from_disk():
                    return True
                # Corrupt disk cache: fall through to a network refresh.

            if await self._refresh_from_network(meta):
                return True

            # Network failed or was blocked: fall back to whatever is on disk,
            # however stale — old metadata beats none.
            if fetched_at > 0 and self._load_from_disk():
                logger.info("Using stale OpenModelDB cache (network refresh failed)")
                return True

            return False

    def _load_from_disk(self) -> bool:
        """Load all dumps from the disk cache and rebuild the index."""
        payloads: Dict[str, Dict[str, Any]] = {}
        for name in _DUMP_NAMES:
            path = self._dump_path(name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except FileNotFoundError:
                if name == "models":
                    return False
                data = {}
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to read OpenModelDB cache %s: %s", path, exc)
                if name == "models":
                    return False
                data = {}
            payloads[name] = data if isinstance(data, dict) else {}

        if not payloads["models"]:
            return False

        self._install_payloads(payloads)
        return True

    async def _refresh_from_network(self, meta: Dict[str, Any]) -> bool:
        """Revalidate cached dumps against the site and rebuild the index.

        Honors ETag/Last-Modified via a HEAD probe: an unchanged dump keeps
        its cached body, so a TTL expiry without upstream changes costs one
        tiny request per dump instead of a full download.
        """
        payloads: Dict[str, Dict[str, Any]] = {}
        etags: Dict[str, str] = dict(meta.get("etags") or {})
        last_modified: Dict[str, str] = dict(meta.get("last_modified") or {})

        for name in _DUMP_NAMES:
            payload, etag, modified = await self._fetch_dump(
                name,
                known_etag=etags.get(name) or "",
                known_last_modified=last_modified.get(name) or "",
            )
            if payload is None:
                if name == "models":
                    return False
                payload = {}
            payloads[name] = payload
            if etag:
                etags[name] = etag
            if modified:
                last_modified[name] = modified

        self._install_payloads(payloads)
        self._write_cache(payloads, etags, last_modified)
        return True

    async def _fetch_dump(
        self,
        name: str,
        *,
        known_etag: str,
        known_last_modified: str,
    ) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """Fetch one dump, returning ``(body, etag, last_modified)``.

        ``body`` is ``None`` when the fetch failed and there is no usable
        cached copy. When the HEAD probe shows the resource unchanged, the
        cached body is returned without a full download.
        """
        url = f"{OPENMODELDB_API_BASE}/{name}.json"
        disk_path = self._dump_path(name)
        have_cached = os.path.exists(disk_path)

        downloader = await get_downloader()

        head_etag = ""
        head_modified = ""
        try:
            head_ok, head_headers = await downloader.get_response_headers(url)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("OpenModelDB HEAD probe failed for %s: %s", url, exc)
            head_ok, head_headers = False, {}

        if head_ok and isinstance(head_headers, dict):
            # aiohttp headers are case-insensitive; plain dicts in tests are not.
            head_etag = str(head_headers.get("ETag") or head_headers.get("etag") or "")
            head_modified = str(
                head_headers.get("Last-Modified") or head_headers.get("last-modified") or ""
            )

        if (
            have_cached
            and known_etag
            and head_etag
            and head_etag == known_etag
        ):
            cached = self._read_dump_file(disk_path)
            if cached is not None:
                logger.debug("OpenModelDB %s unchanged (etag match); using cache", name)
                return cached, known_etag, known_last_modified or head_modified

        success, payload = await downloader.make_request("GET", url, use_auth=False)
        if isinstance(payload, RateLimitError):
            raise payload
        if not success or not isinstance(payload, dict):
            logger.warning(
                "OpenModelDB %s fetch failed: %s",
                name,
                payload if isinstance(payload, str) else "unexpected payload",
            )
            if have_cached:
                cached = self._read_dump_file(disk_path)
                if cached is not None:
                    return cached, known_etag, known_last_modified
            return None, known_etag, known_last_modified

        return payload, head_etag or known_etag, head_modified or known_last_modified

    # ------------------------------------------------------------------
    # Index and transformation
    # ------------------------------------------------------------------

    def _install_payloads(self, payloads: Dict[str, Dict[str, Any]]) -> None:
        """Install dump payloads and rebuild the sha256 index."""
        self._models = payloads.get("models") or {}
        self._users = payloads.get("users") or {}
        self._tags = payloads.get("tags") or {}
        self._architectures = payloads.get("architectures") or {}
        self._index = self._build_index(self._models)
        self._loaded_at = time.monotonic()
        logger.debug(
            "OpenModelDB catalogue loaded: %d models, %d indexed hashes",
            len(self._models),
            len(self._index),
        )

    @staticmethod
    def _build_index(
        models: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        """Build the sha256 -> (model_id, model entry, resource) index."""
        index: Dict[str, Tuple[str, Dict[str, Any], Dict[str, Any]]] = {}
        for model_id, entry in models.items():
            if not isinstance(entry, dict):
                continue
            resources = entry.get("resources")
            if not isinstance(resources, list):
                continue
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                sha256 = resource.get("sha256")
                if not isinstance(sha256, str) or not sha256:
                    continue
                # First writer wins: duplicate hashes across catalogue entries
                # are ambiguous and cannot be disambiguated locally.
                index.setdefault(sha256.lower(), (model_id, entry, resource))
        return index

    def _resolve_authors(self, entry: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Resolve the author field to a display name plus the raw user ids."""
        raw = entry.get("author")
        author_ids = raw if isinstance(raw, list) else [raw]
        ids = [str(a) for a in author_ids if isinstance(a, str) and a]
        names: List[str] = []
        for author_id in ids:
            user = self._users.get(author_id)
            name = user.get("name") if isinstance(user, dict) else None
            names.append(name if isinstance(name, str) and name else author_id)
        return ", ".join(names), ids

    def _resolve_tags(self, entry: Dict[str, Any]) -> List[str]:
        """Resolve tag ids to their display names."""
        raw_tags = entry.get("tags")
        if not isinstance(raw_tags, list):
            return []
        resolved: List[str] = []
        for tag_id in raw_tags:
            if not isinstance(tag_id, str) or not tag_id:
                continue
            tag = self._tags.get(tag_id)
            name = tag.get("name") if isinstance(tag, dict) else None
            resolved.append(name if isinstance(name, str) and name else tag_id)
        return resolved

    def _resolve_architecture_name(self, entry: Dict[str, Any]) -> str:
        """Resolve the architecture id to its display name."""
        arch_id = entry.get("architecture")
        if not isinstance(arch_id, str) or not arch_id:
            return ""
        arch = self._architectures.get(arch_id)
        if isinstance(arch, dict):
            name = arch.get("name")
            if isinstance(name, str) and name:
                return name
        return arch_id

    @staticmethod
    def _resource_format(resource: Dict[str, Any]) -> str:
        """Map an OpenModelDB resource type to a CivitAI file metadata format."""
        resource_type = str(resource.get("type") or "").lower()
        if resource_type == "safetensors":
            return "SafeTensor"
        if resource_type in ("pth", "pt", "ckpt"):
            return "PickleTensor"
        return "Other"

    def _to_civitai_version(
        self,
        model_id: str,
        entry: Dict[str, Any],
        matched_resource: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Map an OpenModelDB catalogue entry to a CivitAI-shaped version dict.

        Follows the same contract as the CivArchive/SQLite providers so the
        metadata sync service can merge it unchanged. Numeric ``id``/``modelId``
        are deliberately omitted: OpenModelDB ids are strings, and consumers
        treat a missing ``modelId`` as "not a CivitAI model" (no CivitAI page
        link, no update checks).
        """
        author_display, author_ids = self._resolve_authors(entry)
        tags = self._resolve_tags(entry)
        architecture_id = entry.get("architecture")
        architecture_name = self._resolve_architecture_name(entry)
        description = entry.get("description")
        license_name = entry.get("license")
        page_url = f"{OPENMODELDB_SITE_BASE}/models/{model_id}"

        files: List[Dict[str, Any]] = []
        resources = entry.get("resources")
        for resource in resources if isinstance(resources, list) else []:
            if not isinstance(resource, dict):
                continue
            # The displayable download URL prefers a direct-bytes mirror when
            # one exists; the filename is derived (never the raw URL basename,
            # which mediafire-style mirrors leave as "file").
            download_url = self.direct_url(resource) or self.primary_url(resource)
            sha256 = resource.get("sha256")
            size_bytes = resource.get("size")
            files.append(
                {
                    "name": self.resource_filename(model_id, resource),
                    "type": "Model",
                    "sizeKB": (size_bytes / 1024.0)
                    if isinstance(size_bytes, (int, float))
                    else 0,
                    "downloadUrl": download_url,
                    "primary": resource is matched_resource,
                    "hashes": {"SHA256": str(sha256).upper()} if sha256 else {},
                    "metadata": {"format": self._resource_format(resource)},
                }
            )

        images: List[Dict[str, Any]] = []
        # The model-level thumbnail is the site's own preview pick and larger
        # than the per-image small thumbs; the card preview derives from
        # images[0], so it leads the list.
        lead = self._model_preview_url(entry)
        if lead:
            images.append({"url": lead, "nsfwLevel": 1, "type": "image"})
        raw_images = entry.get("images")
        for image in raw_images if isinstance(raw_images, list) else []:
            if not isinstance(image, dict):
                continue
            paired = image.get("type") == "paired"
            # Paired entries show the upscaled (SR) result as the preview.
            url = self._paired_display_url(image) if paired else image.get("url")
            if not isinstance(url, str) or not url:
                continue
            if any(existing["url"] == url for existing in images):
                continue
            mapped: Dict[str, Any] = {"url": url, "nsfwLevel": 1, "type": "image"}
            thumbnail = image.get("thumbnail")
            if isinstance(thumbnail, str) and thumbnail:
                thumbnail_url = self._absolutize(thumbnail)
                if thumbnail_url != url:
                    mapped["thumbnailUrl"] = thumbnail_url
            meta: Dict[str, Any] = {}
            if paired:
                comparison = image.get("SR") or image.get("LR")
                if (
                    isinstance(comparison, str)
                    and comparison
                    and comparison != url
                    and _is_ephemeral_viewer_url(comparison)
                ):
                    # Ephemeral imgdiff viewer session, kept for reference
                    # only — it 404s outside the session and is never
                    # displayable.
                    meta["comparisonUrl"] = comparison
            caption = image.get("caption")
            if isinstance(caption, str) and caption:
                meta["caption"] = caption
            if meta:
                mapped["meta"] = meta
            images.append(mapped)

        return {
            "name": entry.get("name") or model_id,
            # Upscalers are not tied to a diffusion base model.
            "baseModel": "Other",
            "description": description or "",
            "publishedAt": entry.get("date"),
            "trainedWords": [],
            "model": {
                "name": entry.get("name") or model_id,
                "type": "Upscaler",
                "nsfw": False,
                "description": description,
                "tags": tags,
                "license": license_name or "",
            },
            "creator": {"username": author_display, "image": None},
            "files": files,
            "images": images,
            "source": METADATA_SOURCE_VALUE,
            # OpenModelDB-native provenance, kept inside the persisted payload
            # so the UI can link to the model page in a later phase.
            "openmodeldb": {
                "id": model_id,
                "url": page_url,
                "authors": author_ids,
                "architecture": architecture_id or "",
                "architectureName": architecture_name,
                "scale": entry.get("scale"),
                "inputChannels": entry.get("inputChannels"),
                "outputChannels": entry.get("outputChannels"),
                "size": entry.get("size") or [],
                "license": license_name or "",
                "date": entry.get("date"),
            },
        }

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _cache_dir(self) -> str:
        base = self._cache_dir_override or os.path.join(
            get_cache_base_dir(), "openmodeldb"
        )
        os.makedirs(base, exist_ok=True)
        return base

    def _dump_path(self, name: str) -> str:
        return os.path.join(self._cache_dir(), f"{name}.json")

    def _meta_path(self) -> str:
        return os.path.join(self._cache_dir(), _META_FILENAME)

    def _read_meta(self) -> Dict[str, Any]:
        try:
            with open(self._meta_path(), "r", encoding="utf-8") as handle:
                meta = json.load(handle)
            return meta if isinstance(meta, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read OpenModelDB cache meta: %s", exc)
            return {}

    def _read_dump_file(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read OpenModelDB cache %s: %s", path, exc)
            return None

    def _write_cache(
        self,
        payloads: Dict[str, Dict[str, Any]],
        etags: Dict[str, str],
        last_modified: Dict[str, str],
    ) -> None:
        for name, payload in payloads.items():
            path = self._dump_path(name)
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
            except OSError as exc:
                logger.warning("Failed to write OpenModelDB cache %s: %s", path, exc)

        meta = {
            "fetched_at": time.time(),
            "etags": etags,
            "last_modified": last_modified,
        }
        try:
            with open(self._meta_path(), "w", encoding="utf-8") as handle:
                json.dump(meta, handle, indent=2)
        except OSError as exc:
            logger.warning("Failed to write OpenModelDB cache meta: %s", exc)
