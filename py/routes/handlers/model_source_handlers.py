"""Handlers for external model sources: linking, file listing and downloads.

Covers every site registered in :mod:`py.services.model_sources`.  The module
was Hugging Face only (``hf_handlers.py`` / ``HfHandler``) until ModelScope
downloads were added; the per-site differences now live in the providers, so
this file has no platform branches beyond the capability lookups.

The historical route paths (``/api/lm/set-hf-url``, ``/api/lm/hf-repo-files``,
``/api/lm/download-hf-model``) are still registered as aliases of the generic
handlers, so existing callers keep working.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from aiohttp import web

from ...config import config
from ...services.downloader import (
    DownloadProgress,
    get_downloader,
)
from ...services.aria2_downloader import Aria2Downloader
from ...services.model_sources import (
    ModelSourceError,
    SourceRef,
    detect_source,
    get_download_source,
    hydrate_from_source,
    is_valid_source_id,
    list_sources,
    normalize_metadata_source,
)
from ...services.settings_manager import get_settings_manager
from ...services.service_registry import ServiceRegistry
from ...services.websocket_manager import ws_manager
from ...utils.metadata_manager import MetadataManager
from ...utils.models import LoraMetadata, CheckpointMetadata, EmbeddingMetadata

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_CLASS = LoraMetadata
_DEFAULT_SCANNER_GETTER = "get_lora_scanner"


def _infer_model_type(model_root: str) -> tuple[Any, str]:
    """Determine model class and scanner by matching ``model_root`` against the
    configured root paths for each model type (from ``Config``).

    The ``model_root`` value comes from the frontend's model-root dropdown,
    which is populated from the current page's scanner roots.  By checking
    which scanner's root list it belongs to, we avoid fragile heuristics
    like substring-matching path names.
    """
    norm = os.path.normpath(model_root).replace(os.sep, "/")

    # LoRA roots
    for p in (config.loras_roots or []) + (config.extra_loras_roots or []):
        if os.path.normpath(p).replace(os.sep, "/") == norm:
            return LoraMetadata, "get_lora_scanner"

    # Checkpoint / UNet roots
    for p in (
        (config.checkpoints_roots or [])
        + (config.extra_checkpoints_roots or [])
        + (config.unet_roots or [])
        + (config.extra_unet_roots or [])
    ):
        if os.path.normpath(p).replace(os.sep, "/") == norm:
            return CheckpointMetadata, "get_checkpoint_scanner"

    # Embedding roots
    for p in (config.embeddings_roots or []) + (config.extra_embeddings_roots or []):
        if os.path.normpath(p).replace(os.sep, "/") == norm:
            return EmbeddingMetadata, "get_embedding_scanner"

    # Fallback — should not happen in normal use
    logger.warning(
        "Could not determine model type for root '%s'; defaulting to LoRA",
        model_root,
    )
    return _DEFAULT_MODEL_CLASS, _DEFAULT_SCANNER_GETTER


async def _report_phase(
    download_id: str | None, stage: str, platform: str = ""
) -> None:
    """Tell the progress UI which post-transfer stage is running.

    A download's byte counter stops the moment the last byte lands, but the
    backend still has to index the file and read the model site's API.  Without
    this the bar sits at 100% reporting "0 B/s" and the download looks stuck for
    several seconds.  *stage* is machine-readable — the UI localises it — and
    *platform* lets it name the site the metadata comes from.
    """

    if not download_id:
        return
    try:
        await ws_manager.broadcast_download_progress(
            download_id,
            {
                "status": "metadata",
                "stage": stage,
                "platform": platform,
                "progress": 100,
            },
        )
    except Exception as exc:  # pragma: no cover - progress must never be fatal
        logger.debug("Failed to report the '%s' phase: %s", stage, exc)


async def _save_source_metadata(
    dest_path: str, ref: SourceRef, model_root: str, *, download_id: str | None = None
) -> None:
    """Create a proper .metadata.json and add the model to the scanner cache.

    The metadata is created through the owning scanner rather than
    ``MetadataManager.create_default_metadata()``, because that is the only
    factory that knows when hashing must be deferred: ``CheckpointScanner`` and
    ``OtherScanner`` deliberately record ``hash_status="pending"`` with an empty
    ``sha256`` for their multi-GB files, and the generic helper would read a
    10 GB checkpoint end to end *inside the download request*.  Scanners for the
    small types delegate straight back to it, so nothing changes for them.

    The external-source fields are then overlaid and the model is registered in
    the in-memory scanner cache so it appears immediately without a full
    filesystem walk.

    Finally the site's own published metadata is applied (see
    :func:`~py.services.model_sources.hydration.hydrate_from_source`), so a
    ModelScope or Hugging Face download lands with the same populated model
    card a CivitAI download produces instead of a bare filename and hash.

    Both post-transfer stages are reported through *download_id* when the UI is
    watching one, because neither advances the byte counter.
    """
    try:
        model_class, scanner_getter_name = _infer_model_type(model_root)

        scanner = None
        scanner_getter = getattr(ServiceRegistry, scanner_getter_name, None)
        if scanner_getter is not None:
            scanner = await scanner_getter()

        # 1. Create proper metadata (reads safetensors headers; hashes only for
        #    the model types whose scanner does not defer it)
        await _report_phase(download_id, "indexing", ref.platform)
        create_metadata = getattr(scanner, "_create_default_metadata", None)
        if create_metadata is not None:
            metadata = await create_metadata(dest_path)
        else:
            metadata = await MetadataManager.create_default_metadata(
                dest_path, model_class=model_class
            )
        if metadata is None:
            logger.warning("create_default_metadata returned None for %s", dest_path)
            return

        # 2. Overlay the external-source fields (`hf_url` is written by
        #    normalisation for Hugging Face only)
        fields = metadata._unknown_fields
        fields["source_url"] = ref.url
        fields["source_platform"] = ref.platform
        if ref.platform == "huggingface":
            fields["hf_url"] = ref.url
        metadata.from_civitai = False  # externally-sourced models are not from CivitAI

        # 3. Save metadata atomically
        await MetadataManager.save_metadata(dest_path, metadata)
        logger.info(
            "Saved %s metadata (source=%s, hash_status=%s) for %s",
            ref.platform, ref.url, getattr(metadata, "hash_status", "?"), dest_path,
        )

        # 4. Determine relative folder path for cache
        #    model_root is an absolute path; dest_path is under it
        folder = ""
        if os.path.isabs(model_root) and dest_path.startswith(model_root):
            rel = os.path.relpath(os.path.dirname(dest_path), model_root)
            folder = rel.replace(os.sep, "/") if rel != "." else ""

        # 5. Add to scanner cache (same as CivitAI's _execute_download does)
        if scanner is not None:
            metadata_dict = normalize_metadata_source(metadata.to_dict())
            await scanner.add_model_to_cache(metadata_dict, folder)
            logger.info("Added %s to scanner cache (folder=%s)", dest_path, folder)

        # 6. Top up from the site's public API. Runs last so the scanner-cache
        #    refresh it performs lands on the entry created above. It never
        #    raises and never fails the download.
        await _report_phase(download_id, "source", ref.platform)
        await hydrate_from_source(dest_path, ref=ref)

    except Exception as exc:
        logger.warning("Failed to save source metadata for %s: %s", dest_path, exc)


def _find_matching_root(dest_dir: str) -> str | None:
    """Walk up *dest_dir* to find which configured scanner root it belongs to."""
    norm = os.path.normpath(dest_dir).replace(os.sep, "/")
    all_roots = []
    for root_list in (
        config.loras_roots or [],
        config.extra_loras_roots or [],
        config.checkpoints_roots or [],
        config.extra_checkpoints_roots or [],
        config.unet_roots or [],
        config.extra_unet_roots or [],
        config.embeddings_roots or [],
        config.extra_embeddings_roots or [],
    ):
        all_roots.extend([os.path.normpath(p).replace(os.sep, "/") for p in root_list])
    # Find the longest matching prefix
    match: str | None = None
    for root in all_roots:
        if norm.startswith(root):
            if match is None or len(root) > len(match):
                match = root
    return match


async def _add_to_scanner_cache(dest_path: str, metadata: dict[str, Any]) -> None:
    model_dir = os.path.dirname(dest_path)
    model_root = _find_matching_root(model_dir)
    if not model_root:
        raise ValueError(f"File path {dest_path} is not within any configured scanner root")
    scanner_getter_name = _infer_model_type(model_root)[1]
    scanner_getter = getattr(ServiceRegistry, scanner_getter_name, None)
    if scanner_getter is None:
        raise RuntimeError(f"Scanner getter '{scanner_getter_name}' not found in ServiceRegistry")
    scanner = await scanner_getter()
    if scanner is None:
        raise RuntimeError(f"Scanner '{scanner_getter_name}' returned None")
    await scanner.update_single_model_cache(dest_path, dest_path, metadata)


def _unsupported_platform_error(platform: str) -> web.Response:
    supported = ", ".join(source.label for source in list_sources() if source.supports_download)
    return web.json_response(
        {"error": f"'{platform}' does not support downloads. Supported: {supported}"},
        status=400,
    )


class ModelSourceHandler:
    """Handle external model browsing, linking and downloads."""

    async def get_model_sources(self, request: web.Request) -> web.Response:
        """List the external model sites the UI can link a model to.

        Used by the "Link Model" dialog to validate URLs client-side, to
        explain which sites support AI metadata enrichment, and to pick the
        right download endpoint/revision.
        """

        return web.json_response([
            {
                "platform": source.platform,
                "label": source.label,
                "supports_enrichment": source.supports_enrichment,
                "supports_download": source.supports_download,
                "default_revision": source.default_revision,
                "example_url": source.canonical_url(
                    "user/repo" if source.platform != "tensorart" else "827823520299086029"
                ),
            }
            for source in list_sources()
        ])

    async def set_hf_url(self, request: web.Request) -> web.Response:
        """Link a model file to its page on an external model site.

        Accepts ``source_url`` (preferred) or the legacy ``hf_url`` / ``url``
        payload key.  Every registered site is recognised and the platform is
        stored alongside the canonical URL.  TensorArt models can be linked and
        browsed, but not AI-enriched.

        The route path keeps its historical ``set-hf-url`` name.
        """

        try:
            payload: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"success": False, "error": "Invalid JSON"}, status=400)

        file_path = (payload.get("file_path") or "").strip()
        raw_url = (
            payload.get("source_url")
            or payload.get("hf_url")
            or payload.get("url")
            or ""
        )
        source_url = raw_url.strip() if isinstance(raw_url, str) else ""

        if not file_path or not source_url:
            return web.json_response(
                {
                    "success": False,
                    "error": "Missing required fields: 'file_path' and 'source_url'",
                },
                status=400,
            )

        ref = detect_source(source_url, strict=True)
        if ref is None:
            return web.json_response(
                {
                    "success": False,
                    "error": (
                        "Unsupported model URL. Supported formats: "
                        + ", ".join(
                            f"{s.label} ({s.canonical_url('user/repo')})"
                            if s.platform != "tensorart"
                            else f"{s.label} (https://tensor.art/models/<id>)"
                            for s in list_sources()
                        )
                    ),
                },
                status=400,
            )

        if not os.path.isfile(file_path):
            return web.json_response(
                {"success": False, "error": f"File not found: {file_path}"},
                status=404,
            )

        model_root = _find_matching_root(os.path.dirname(file_path))
        if not model_root:
            return web.json_response(
                {
                    "success": False,
                    "error": "File is not within any configured model directory. Cannot link to a model source.",
                },
                status=400,
            )

        try:
            existing = await MetadataManager.load_metadata_payload(file_path)

            already_linked = (
                (existing.get("source_url") or "").strip() == ref.url
                and (existing.get("source_platform") or "").strip().lower()
                == ref.platform
            ) or (
                not existing.get("source_url")
                and ref.platform == "huggingface"
                and (existing.get("hf_url") or "").strip() == ref.url
            )
            if already_linked:
                return web.json_response({
                    "success": True,
                    "message": "source_url already set",
                    "source_url": ref.url,
                    "source_platform": ref.platform,
                    "hf_url": ref.url if ref.platform == "huggingface" else "",
                })

            existing["source_url"] = ref.url
            existing["source_platform"] = ref.platform
            if ref.platform == "huggingface":
                existing["hf_url"] = ref.url
            else:
                existing.pop("hf_url", None)
            normalize_metadata_source(existing)

            # NOTE: deliberately do NOT touch `from_civitai` here. It records
            # where the metadata came from, and the UI must show the CivitAI
            # link whenever CivitAI data is present — linking an external
            # source must not hide it (#1094). Source provenance is tracked
            # via `source_platform` / `source_url`.
            await MetadataManager.save_metadata(file_path, existing)

            await _add_to_scanner_cache(file_path, existing)

            logger.info(
                "Linked %s to %s source (%s)", file_path, ref.platform, ref.url
            )
            return web.json_response({
                "success": True,
                "message": f"Linked to {ref.url}",
                "source_url": ref.url,
                "source_platform": ref.platform,
                "hf_url": existing.get("hf_url", ""),
            })
        except Exception as exc:
            logger.error("Failed to link %s to a model source: %s", file_path, exc)
            return web.json_response(
                {"success": False, "error": str(exc)},
                status=500,
            )

    async def list_model_source_files(self, request: web.Request) -> web.Response:
        """List the downloadable weight files of an external repository.

        Query params: ``platform``, ``repo`` (``owner/name``), ``revision``
        (optional; each site has its own default branch).

        Returns a JSON array of ``{"filename", "size"}``, largest first —
        the same shape the Hugging Face endpoint has always returned.
        """

        platform = (request.query.get("platform") or "").strip()
        repo = (request.query.get("repo") or "").strip()
        revision = (request.query.get("revision") or "").strip()

        source = get_download_source(platform)
        if source is None:
            return _unsupported_platform_error(platform)
        if not is_valid_source_id(repo):
            return web.json_response(
                {"error": "Missing or invalid 'repo' parameter (expected owner/name)"},
                status=400,
            )

        try:
            files = await source.list_files(repo, revision)
        except ModelSourceError as exc:
            return web.json_response({"error": str(exc)}, status=exc.status)
        except Exception as exc:
            logger.error("Failed to list %s files in %s: %s", platform, repo, exc)
            return web.json_response({"error": str(exc)}, status=502)

        return web.json_response(files)

    async def download_model_source(self, request: web.Request) -> web.Response:
        """Download a single file from an external repository.

        POST JSON body::

            {
              "platform": "modelscope",
              "repo": "owner/name",
              "filename": "subdir/model.safetensors",
              "revision": "master",
              "model_root": "loras",
              "relative_path": "",
              "use_default_paths": false,
              "download_id": "optional-batch-id"
            }

        ``platform`` defaults to ``huggingface`` when omitted, which keeps the
        legacy ``/api/lm/download-hf-model`` payload working unchanged.

        If ``download_id`` is provided, real-time progress (bytes, speed,
        percentage) is broadcast via the WebSocket progress system.

        Respects the ``download_backend`` setting (``aria2`` or ``default``).
        """
        try:
            payload: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        platform = (payload.get("platform") or "huggingface").strip()
        repo = (payload.get("repo") or "").strip()
        filename = (payload.get("filename") or "").strip()
        revision = (payload.get("revision") or "").strip()
        model_root = (payload.get("model_root") or "").strip()
        relative_path = (payload.get("relative_path") or "").strip()
        use_default_paths = bool(payload.get("use_default_paths", False))
        download_id: str | None = payload.get("download_id")

        logger.info(
            "download_model_source: platform=%s repo=%s file=%s root=%s download_id=%s",
            platform, repo, filename, model_root, download_id,
        )

        source = get_download_source(platform)
        if source is None:
            return _unsupported_platform_error(platform)

        if not repo or not filename:
            return web.json_response(
                {"error": "Missing required fields: 'repo' and 'filename'"}, status=400
            )

        # `owner/name` only; the components become path segments below.
        if not is_valid_source_id(repo):
            return web.json_response({"error": f"Invalid repo format: {repo}"}, status=400)
        owner, repo_name = repo.split("/", 1)

        # Validate filename — must not contain path traversal
        if ".." in filename:
            return web.json_response({"error": "Invalid filename"}, status=400)

        # Validate relative_path — must not be absolute or escape base directory
        if relative_path:
            if os.path.isabs(relative_path):
                return web.json_response({"error": "relative_path must not be absolute"}, status=400)
            if ".." in relative_path.split("/") or "\\" in relative_path:
                return web.json_response({"error": "Invalid relative_path"}, status=400)

        # Use model_root directly as the base directory — same approach as
        # CivitAI's download path (download_manager.py).  No realpath, no
        # allowed-roots validation, no path-traversal check; those are
        # unnecessary when the frontend sends the path from its own dropdown
        # (populated from scanner roots).  Using the "business path" directly
        # keeps dest_path consistent with scanner roots so that later folder
        # derivation (in _save_source_metadata) works correctly.
        if os.path.isabs(model_root):
            base_dir = os.path.normpath(model_root)
        else:
            base_dir = os.path.normpath(os.path.join(os.getcwd(), "models", model_root))

        if use_default_paths:
            target_dir = os.path.join(base_dir, source.default_subdir, owner, repo_name)
        elif relative_path:
            target_dir = os.path.join(base_dir, relative_path)
        else:
            target_dir = base_dir

        # Strip the repository sub-directory — "diffusion_models/xxx.safetensors"
        # is a repository convention, not meaningful for local storage.
        file_base = os.path.basename(filename)

        os.makedirs(target_dir, exist_ok=True)
        dest_path = os.path.join(target_dir, file_base)

        # Built per request: sites that redirect to a CDN hand out a
        # time-limited token in the redirect, so the URL must never be cached.
        resolve_url = source.file_download_url(repo, filename, revision)
        ref = SourceRef(
            platform=source.platform, source_id=repo, url=source.canonical_url(repo)
        )

        # Check if already exists (simple skip)
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            logger.info("download_model_source: file already exists, skipping — %s", dest_path)
            # The sidecar may predate the source metadata being fetched, or may
            # have been deleted, so top it up instead of skipping past it.
            # Hydration no-ops when there is no sidecar to update.
            await _report_phase(download_id, "source", source.platform)
            await hydrate_from_source(dest_path, ref=ref)
            return web.json_response({
                "success": True,
                "message": f"File already exists: {dest_path}",
                "path": dest_path,
            })

        # Set up progress callback if download_id is provided
        progress_callback = None
        if download_id:

            async def _progress_callback(
                progress: float | DownloadProgress,
                snapshot: DownloadProgress | None = None,
            ) -> None:
                percent = 0.0
                metrics = snapshot if isinstance(snapshot, DownloadProgress) else None

                if isinstance(progress, DownloadProgress):
                    percent = progress.percent_complete
                    metrics = progress
                elif isinstance(snapshot, DownloadProgress):
                    percent = snapshot.percent_complete
                else:
                    percent = float(progress)

                broadcast: dict[str, Any] = {
                    "status": "progress",
                    "progress": round(percent),
                }
                if metrics:
                    broadcast["bytes_downloaded"] = metrics.bytes_downloaded
                    broadcast["total_bytes"] = metrics.total_bytes
                    broadcast["bytes_per_second"] = metrics.bytes_per_second

                await ws_manager.broadcast_download_progress(download_id, broadcast)

            progress_callback = _progress_callback

        # Respect download backend setting (aria2 vs default)
        download_backend = (
            get_settings_manager().get("download_backend", "default")
        )

        if download_backend == "aria2":
            aria2 = await Aria2Downloader.get_instance()
            aid = download_id or f"{source.platform}_{repo}_{filename}"
            try:
                ok, result = await aria2.download_file(
                    url=resolve_url,
                    save_path=dest_path,
                    download_id=aid,
                    progress_callback=progress_callback,
                )
                if ok:
                    await _save_source_metadata(
                        dest_path, ref, model_root, download_id=download_id
                    )
                    return web.json_response({
                        "success": True,
                        "message": f"Downloaded to {dest_path}",
                        "path": dest_path,
                    })
                return web.json_response(
                    {"success": False, "error": result or "aria2 download failed"},
                    status=500,
                )
            except Exception as exc:
                logger.error("%s download (aria2) failed: %s", platform, exc)
                return web.json_response(
                    {"success": False, "error": str(exc)}, status=500
                )

        # Default: use built-in aiohttp Downloader
        downloader = await get_downloader()
        try:
            success, result = await downloader.download_file(
                url=resolve_url,
                save_path=dest_path,
                use_auth=False,
                allow_resume=True,
                progress_callback=progress_callback,
            )
            if success:
                await _save_source_metadata(
                    dest_path, ref, model_root, download_id=download_id
                )
                return web.json_response({
                    "success": True,
                    "message": f"Downloaded to {result}",
                    "path": result,
                })
            return web.json_response(
                {"success": False, "error": result or "Download failed"},
                status=500,
            )
        except Exception as exc:
            logger.error("%s download failed: %s", platform, exc)
            return web.json_response(
                {"success": False, "error": str(exc)}, status=500
            )
