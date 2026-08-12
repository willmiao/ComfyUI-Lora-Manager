"""Handler for the pending-delete undo endpoint.

Restores a staged delete batch (models or recipes) via
``PendingDeleteService.undo`` and then repairs the affected library caches:
the model cache entry is restored from the manifest's ``model_snapshot``
(including the version index and hash index), tag counts are re-incremented,
and the recipe cache is re-populated via ``RecipeScanner.add_recipe``.

The per-type scanner is resolved from the manifest's ``model_type`` page value
through the SAME ServiceRegistry getters the model route registrars use
(lora/checkpoint/embedding) - never a hardcoded lora scanner.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, cast

from aiohttp import web

from ...services.pending_delete_service import get_pending_delete_service
from .model_handlers import _broadcast_models_changed

logger = logging.getLogger(__name__)

# Manifest ``model_type`` page values -> ServiceRegistry scanner getter names.
# The model route registrars resolve per-type scanners via these getters
# (lora_routes / checkpoint_routes / embedding_routes); undo must do the same
# so the CORRECT cache is restored for the deleted model's type.
_MODEL_TYPE_GETTER_NAMES: Dict[str, str] = {
    "loras": "get_lora_scanner",
    "checkpoints": "get_checkpoint_scanner",
    "embeddings": "get_embedding_scanner",
}

# Staged batch ids are ``uuid.uuid4().hex`` (32 lowercase hex chars). The id is
# joined into filesystem paths by ``_find_batch_dir``, so reject anything that
# does not match this exact shape (blocks path-traversal via batch_id).
_BATCH_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class PendingDeleteHandler:
    """Handle undo requests for staged model/recipe deletions."""

    def __init__(
        self,
        *,
        service_factory: Callable[[], Awaitable[Any]] = get_pending_delete_service,
        scanner_getter: Optional[Callable[[str], Awaitable[Any]]] = None,
        recipe_scanner_getter: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> None:
        self._service_factory: Callable[[], Awaitable[Any]] = service_factory
        self._scanner_getter: Callable[[str], Awaitable[Any]] = (
            scanner_getter or self._resolve_scanner
        )
        self._recipe_scanner_getter: Callable[[], Awaitable[Any]] = (
            recipe_scanner_getter or self._resolve_recipe_scanner
        )

    @staticmethod
    async def _resolve_scanner(model_type: str) -> Any:
        """Resolve the per-type scanner for a manifest ``model_type``.

        The getter is looked up on the ServiceRegistry module namespace at call
        time so tests (and the registry stubs) can patch it.
        """
        from ...services import service_registry

        getter_name = _MODEL_TYPE_GETTER_NAMES.get(model_type)
        if getter_name is None:
            raise ValueError(f"Unknown model type: {model_type}")
        getter = getattr(service_registry.ServiceRegistry, getter_name, None)
        if not callable(getter):
            raise ValueError(f"No scanner getter for model type: {model_type}")
        scanner = await cast(Callable[[], Awaitable[Any]], getter)()
        if scanner is None:
            raise ValueError(f"No scanner registered for model type: {model_type}")
        return scanner

    @staticmethod
    async def _resolve_recipe_scanner() -> Any:
        """Resolve the recipe scanner via the ServiceRegistry module namespace."""
        from ...services import service_registry

        getter = getattr(service_registry.ServiceRegistry, "get_recipe_scanner", None)
        if not callable(getter):
            raise ValueError("Recipe scanner getter unavailable")
        scanner = await cast(Callable[[], Awaitable[Any]], getter)()
        if scanner is None:
            raise ValueError("No recipe scanner registered")
        return scanner

    async def undo_delete(self, request: web.Request) -> web.Response:
        """Restore a staged batch and its library cache entry.

        Body: ``{"batch_id": str}``. On success returns
        ``{"success": True, "restored": [<original paths>], "kind": kind}``.
        Expired/unknown batches and occupied target paths -> 404.
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"}, status=400
            )
        if not isinstance(data, dict):
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"}, status=400
            )
        batch_id = data.get("batch_id")
        if not batch_id or not isinstance(batch_id, str):
            return web.json_response(
                {"success": False, "error": "batch_id is required"}, status=400
            )
        if not _BATCH_ID_RE.fullmatch(batch_id):
            # batch_id is joined into a path by _find_batch_dir - restrict to
            # the exact staged-id shape so traversal payloads get 400.
            return web.json_response(
                {"success": False, "error": "Invalid batch_id"}, status=400
            )

        service = await self._service_factory()
        try:
            # Read the manifest BEFORE undo: undo() removes the batch dir.
            manifest = await self._read_staged_manifest(service, batch_id)
            result = await service.undo(batch_id)
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=404)
        except Exception as exc:
            logger.error("Unexpected error undoing batch %s: %s", batch_id, exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

        kind = result.get("kind")
        try:
            if kind == "model":
                if manifest is not None:
                    await self._restore_model_cache(manifest)
                else:
                    # undo() raises when the manifest is missing, so this only
                    # happens defensively - files are restored regardless.
                    logger.warning(
                        "Manifest missing after undo of %s; skipping cache restore",
                        batch_id,
                    )
                _broadcast_models_changed()
            elif kind == "recipe":
                # Recipe undo is client-refresh only: re-add to the scanner
                # cache, no models_changed broadcast.
                if manifest is not None:
                    await self._restore_recipe_cache(result, manifest)
                else:
                    logger.warning(
                        "Manifest missing after undo of %s; skipping cache restore",
                        batch_id,
                    )
        except Exception as exc:
            # Files are already restored; only the cache restoration failed.
            logger.error(
                "Cache restoration failed after undo of %s: %s",
                batch_id,
                exc,
                exc_info=True,
            )
            return web.json_response({"success": False, "error": str(exc)}, status=500)

        return web.json_response(
            {
                "success": True,
                "restored": result.get("restored", []),
                "kind": kind,
            }
        )

    @staticmethod
    async def _read_staged_manifest(
        service: Any, batch_id: str
    ) -> Optional[Dict[str, Any]]:
        """Locate and read the batch manifest while it still exists on disk."""
        batch_dir = await service._find_batch_dir(batch_id)
        if not batch_dir:
            return None
        manifest_path = os.path.join(batch_dir, "manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Failed to read manifest for batch %s: %s", batch_id, exc)
            return None
        return payload if isinstance(payload, dict) else None

    async def _restore_model_cache(self, manifest: Dict[str, Any]) -> None:
        """Re-add every deleted model's cache entry from the manifest.

        Each main-file entry carries the deleted model's ``snapshot`` (added at
        stage time), so a merged bulk manifest holds ALL snapshots - undo must
        restore every one, not just the top-level winner's. Old-format
        manifests without entry snapshots fall back to the top-level
        ``model_snapshot`` (backward compat / single-delete path).
        """
        model_type = manifest.get("model_type")
        if not model_type or not isinstance(model_type, str):
            raise ValueError(f"Manifest carries no model_type: {manifest.get('batch_id')}")
        scanner = await self._scanner_getter(model_type)

        # Collect one snapshot per distinct file_path from the entry snapshots.
        snapshots: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for entry in manifest.get("entries") or []:
            snapshot = entry.get("snapshot")
            if not isinstance(snapshot, dict):
                continue
            file_path = snapshot.get("file_path")
            if not file_path or not isinstance(file_path, str):
                continue
            if file_path in seen:
                continue
            seen.add(file_path)
            snapshots.append(snapshot)

        if not snapshots:
            # Backward compat: pre-F3 manifests carry only the top-level
            # model_snapshot (single-delete path, unchanged behavior).
            top = manifest.get("model_snapshot")
            if isinstance(top, dict) and top.get("file_path"):
                snapshots = [top]
            else:
                logger.warning(
                    "Manifest %s has no restorable model snapshot; skipping cache restore",
                    manifest.get("batch_id"),
                )
                return

        cache = await scanner.get_cached_data()
        if cache is None:
            logger.warning(
                "Scanner cache unavailable for %s; skipping cache restore", model_type
            )
            return

        for snapshot in snapshots:
            file_path = str(snapshot["file_path"])
            # A rescan between delete and undo may have re-added a stale entry
            # for this path - drop it so exactly one (the snapshot) remains.
            cache.raw_data = [
                item for item in cache.raw_data if item.get("file_path") != file_path
            ]

            # Restore tag counts (mirror of the bulk-delete decrement in
            # _batch_update_cache_for_deleted_models: undo re-increments).
            tags = snapshot.get("tags")
            if isinstance(tags, list):
                for tag in tags:
                    if not isinstance(tag, str) or not tag:
                        continue
                    scanner._tags_count[tag] = scanner._tags_count.get(tag, 0) + 1

            cache.raw_data.append(dict(snapshot))

            # Re-register the path in the hash index (add_entry guards a
            # missing sha256 internally; still guard defensively here).
            sha256 = snapshot.get("sha256") or ""
            autov3 = snapshot.get("autov3")
            hash_index = getattr(scanner, "_hash_index", None)
            if hash_index is not None and sha256 and file_path:
                hash_index.add_entry(sha256, file_path, autov3)

        # Follow the bulk-delete cache-update pattern ONCE after all entries,
        # including the explicit version-index rebuild so the version index
        # does not go stale.
        cache.rebuild_version_index()
        await cache.resort()

        scanner.bump_cache_version()

        persist = getattr(scanner, "_persist_current_cache", None)
        if callable(persist):
            result = persist()
            if inspect.isawaitable(result):
                await result

    async def _restore_recipe_cache(
        self, result: Dict[str, Any], manifest: Dict[str, Any]
    ) -> None:
        """Re-add a restored recipe via ``RecipeScanner.add_recipe``.

        The recipe JSON embeds the full recipe_data (incl. id/file_path);
        ``add_recipe`` only READS the ``_json_path_map`` so the forced frontend
        refresh self-heals any transient path-map gap.
        """
        restored = result.get("restored") or []
        json_path = next(
            (p for p in restored if isinstance(p, str) and p.endswith(".json")),
            None,
        )
        if not json_path or not os.path.exists(json_path):
            # Defensive fallback to the manifest's recipe_snapshot file_path.
            snapshot = manifest.get("recipe_snapshot") or {}
            fallback = snapshot.get("file_path")
            if fallback and os.path.exists(fallback):
                json_path = fallback
            else:
                logger.warning(
                    "Restored recipe JSON not found in %s; skipping cache restore",
                    restored,
                )
                return
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                recipe_data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load restored recipe JSON %s: %s", json_path, exc)
            return
        if not isinstance(recipe_data, dict):
            return
        recipe_scanner = await self._recipe_scanner_getter()
        await recipe_scanner.add_recipe(recipe_data)


__all__ = ["PendingDeleteHandler"]
