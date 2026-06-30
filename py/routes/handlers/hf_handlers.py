"""Handlers for Hugging Face model listing and download.

Minimal MVP implementation — uses direct HTTP to the HF API for file
listing and the project's existing aiohttp-based Downloader for
downloading.  No huggingface_hub dependency required.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import aiohttp
from aiohttp import web

from ...config import config
from ...services.downloader import (
    DownloadProgress,
    get_downloader,
)
from ...services.aria2_downloader import Aria2Downloader
from ...services.settings_manager import get_settings_manager
from ...services.service_registry import ServiceRegistry
from ...services.websocket_manager import ws_manager
from ...utils.constants import MODEL_FILE_EXTENSIONS
from ...utils.metadata_manager import MetadataManager
from ...utils.models import LoraMetadata, CheckpointMetadata, EmbeddingMetadata

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_CLASS = LoraMetadata
_DEFAULT_SCANNER_GETTER = "get_lora_scanner"

# Shared aiohttp session for HF API calls (created on first use)
_hf_api_session: aiohttp.ClientSession | None = None


async def _get_hf_api_session() -> aiohttp.ClientSession:
    """Get or create the shared aiohttp session for HF API calls."""
    global _hf_api_session  # needed because we reassign the module-level name
    if _hf_api_session is None or _hf_api_session.closed:
        _hf_api_session = aiohttp.ClientSession(
            headers={"User-Agent": "ComfyUI-LoRA-Manager/1.0"},
            timeout=aiohttp.ClientTimeout(total=30),
        )
    return _hf_api_session


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


async def _save_hf_metadata(dest_path: str, repo: str, model_root: str) -> None:
    """Create a proper .metadata.json and add the model to the scanner cache.

    Uses ``MetadataManager.create_default_metadata()`` which computes the
    SHA256 hash, extracts safetensors header metadata (base_model), and
    produces a fully-populated ``LoraMetadata`` (or ``CheckpointMetadata`` /
    ``EmbeddingMetadata``) object.  We then overlay HF-specific fields and
    register the model in the in-memory scanner cache so it appears
    immediately without a full filesystem walk.
    """
    try:
        hf_url = f"https://huggingface.co/{repo}"
        model_class, scanner_getter_name = _infer_model_type(model_root)

        # 1. Create proper metadata (computes SHA256, reads safetensors headers)
        metadata = await MetadataManager.create_default_metadata(
            dest_path, model_class=model_class
        )
        if metadata is None:
            logger.warning("create_default_metadata returned None for %s", dest_path)
            return

        # 2. Overlay HF-specific fields
        metadata._unknown_fields["hf_url"] = hf_url
        metadata.from_civitai = True  # leave default, don't interfere with CivitAI fetch

        # 3. Save metadata atomically
        await MetadataManager.save_metadata(dest_path, metadata)
        logger.info("Saved HF metadata (with hf_url) for %s", dest_path)

        # 4. Determine relative folder path for cache
        #    model_root is an absolute path; dest_path is under it
        folder = ""
        if os.path.isabs(model_root) and dest_path.startswith(model_root):
            rel = os.path.relpath(os.path.dirname(dest_path), model_root)
            folder = rel.replace(os.sep, "/") if rel != "." else ""

        # 5. Add to scanner cache (same as CivitAI's _execute_download does)
        scanner_getter = getattr(ServiceRegistry, scanner_getter_name, None)
        if scanner_getter is not None:
            scanner = await scanner_getter()
            if scanner is not None:
                metadata_dict = metadata.to_dict()
                metadata_dict["hf_url"] = hf_url
                await scanner.add_model_to_cache(metadata_dict, folder)
                logger.info("Added %s to scanner cache (folder=%s)", dest_path, folder)

    except Exception as exc:
        logger.warning("Failed to save HF metadata for %s: %s", dest_path, exc)


class HfHandler:
    """Handle Hugging Face model browsing and download."""

    async def get_hf_repo_files(self, request: web.Request) -> web.Response:
        """List model-weight files from a HF repo with real file sizes.

        Uses the HF tree API endpoint which returns accurate file sizes
        (including LFS-tracked files), unlike the model info endpoint.
        """
        repo = request.query.get("repo", "").strip()
        if not repo or "/" not in repo:
            return web.json_response(
                {"error": "Missing or invalid 'repo' parameter (expected user/repo)"},
                status=400,
            )

        url = f"https://huggingface.co/api/models/{repo}/tree/main"

        try:
            session = await _get_hf_api_session()
            async with session.get(url) as resp:
                if resp.status == 404:
                    return web.json_response(
                        {"error": f"Repo '{repo}' not found"}, status=404
                    )
                if resp.status != 200:
                    text = await resp.text()
                    return web.json_response(
                        {"error": f"HF API error {resp.status}: {text[:200]}"},
                        status=resp.status,
                    )
                tree: list[dict[str, Any]] = await resp.json()
        except Exception as exc:
            logger.error("Failed to fetch HF repo files: %s", exc)
            return web.json_response({"error": str(exc)}, status=502)

        files: list[dict[str, Any]] = []
        for entry in tree:
            path: str = entry.get("path", "")
            ext = os.path.splitext(path)[1].lower()
            if ext not in MODEL_FILE_EXTENSIONS:
                continue
            size = entry.get("size", 0) or 0
            if size == 0 and "lfs" in entry:
                size = entry["lfs"].get("size", 0) or 0
            files.append({
                "filename": path,
                "size": size,
            })

        files.sort(key=lambda f: f["size"], reverse=True)
        return web.json_response(files)

    async def download_hf_model(self, request: web.Request) -> web.Response:
        """Download a single file from Hugging Face into the model directory.

        POST JSON body::

            {
              "repo": "dx8152/Flux2-Klein-9B-Consistency",
              "filename": "Flux2-Klein-9B-consistency-V2.safetensors",
              "revision": "main",
              "model_root": "loras",
              "relative_path": "",
              "use_default_paths": false,
              "download_id": "optional-batch-id"
            }

        If ``download_id`` is provided, real-time progress (bytes, speed,
        percentage) is broadcast via the WebSocket progress system, matching
        the CivitAI download experience.

        Respects the ``download_backend`` setting (``aria2`` or ``default``).
        """
        try:
            payload: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        repo = (payload.get("repo") or "").strip()
        filename = (payload.get("filename") or "").strip()
        revision = (payload.get("revision") or "main").strip()
        model_root = (payload.get("model_root") or "").strip()
        relative_path = (payload.get("relative_path") or "").strip()
        use_default_paths = bool(payload.get("use_default_paths", False))
        download_id: str | None = payload.get("download_id")

        logger.info(
            "download_hf_model: repo=%s file=%s root=%s download_id=%s",
            repo, filename, model_root, download_id,
        )

        if not repo or not filename:
            return web.json_response(
                {"error": "Missing required fields: 'repo' and 'filename'"}, status=400
            )

        # Determine target directory
        if os.path.isabs(model_root):
            base_dir = model_root
        else:
            base_dir = os.path.join(os.getcwd(), "models", model_root)

        if use_default_paths:
            author, repo_name = repo.split("/", 1)
            target_dir = os.path.join(base_dir, "huggingface", author, repo_name)
        elif relative_path:
            target_dir = os.path.join(base_dir, relative_path)
        else:
            target_dir = base_dir

        os.makedirs(target_dir, exist_ok=True)
        dest_path = os.path.join(target_dir, filename)

        # Check if already exists (simple skip)
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            logger.info("download_hf_model: file already exists, skipping — %s", dest_path)
            return web.json_response({
                "success": True,
                "message": f"File already exists: {dest_path}",
                "path": dest_path,
            })

        # Build HF resolve URL
        resolve_url = (
            f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
        )

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
            aid = download_id or f"hf_{repo}_{filename}"
            try:
                hf_success, hf_result = await aria2.download_file(
                    url=resolve_url,
                    save_path=dest_path,
                    download_id=aid,
                    progress_callback=progress_callback,
                )
                if hf_success:
                    await _save_hf_metadata(dest_path, repo, model_root)
                    return web.json_response({
                        "success": True,
                        "message": f"Downloaded to {dest_path}",
                        "path": dest_path,
                    })
                else:
                    return web.json_response(
                        {"success": False, "error": hf_result or "aria2 download failed"},
                        status=500,
                    )
            except Exception as exc:
                logger.error("HF download (aria2) failed: %s", exc)
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
                await _save_hf_metadata(dest_path, repo, model_root)
                return web.json_response({
                    "success": True,
                    "message": f"Downloaded to {result}",
                    "path": result,
                })
            else:
                return web.json_response(
                    {"success": False, "error": result or "Download failed"},
                    status=500,
                )
        except Exception as exc:
            logger.error("HF download failed: %s", exc)
            return web.json_response(
                {"success": False, "error": str(exc)}, status=500
            )
