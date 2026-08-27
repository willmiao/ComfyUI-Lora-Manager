"""Pending-delete staging service.

Stages model/recipe deletes into hidden per-root staging directories so a
30-second undo window can restore them before the physical purge runs. The
service is the foundation for the delete-undo feature: every staged batch is
described by a ``manifest.json`` which is the ONLY source of truth.

LOCK HIERARCHY (critical - asyncio.Lock is NOT re-entrant):
``_ops_lock`` is acquired ONLY by stage_model_delete, stage_recipe_delete,
merge_batches, undo and purge_batch. ``purge_expired()`` NEVER acquires it -
it enumerates staging dirs and delegates each batch to ``purge_batch`` (which
locks). The opportunistic ``await self.purge_expired()`` at the start of
stage_*/undo MUST therefore run BEFORE those methods acquire the lock.
"""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    cast,
)

from ..utils.constants import PREVIEW_EXTENSIONS
from ..utils import settings_paths

logger = logging.getLogger(__name__)

# Undo window in seconds before a staged batch becomes purge-eligible.
PENDING_DELETE_TTL_SECONDS = 20
# Hidden staging directory name placed inside each deleted model's own folder
# (sibling of the model artifacts) and under the settings dir for recipes.
PENDING_DELETE_DIR_NAME = ".lm-pending-delete"
# Manifest file name inside every batch directory.
MANIFEST_FILE_NAME = "manifest.json"
# Suffix appended when quarantining malformed/manifest-less batch dirs. The
# quarantine is terminal: never re-renamed, never re-quarantined, never
# deleted by the sweep.
ORPHANED_SUFFIX = ".orphaned"

# Map scanner.model_type (singular) to the manifest page type values.
_MODEL_TYPE_PAGE_MAP = {
    "lora": "loras",
    "checkpoint": "checkpoints",
    "embedding": "embeddings",
}

# Module-level alias so tests can spy on timer task creation without patching
# the global asyncio module.
_create_task = asyncio.create_task


class PendingDeleteService:
    """Stage, undo and purge pending model/recipe deletions.

    Singleton + asyncio.Lock pattern (mirrors py/services/model_scanner.py).
    """

    _instance: Optional["PendingDeleteService"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "PendingDeleteService":
        """Return the lazily initialised singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # Serialises stage/merge/undo/purge_batch. purge_expired never locks.
        self._ops_lock = asyncio.Lock()
        # Track fire-and-forget purge timer tasks to keep them alive and to
        # cancel them on shutdown / singleton reset.
        self._purge_tasks: Set[Any] = set()
        # Roots the service has staged into (in-process). Combined with the
        # ServiceRegistry roots during sweeps so undo/purge work even before
        # every scanner is registered.
        self._known_roots: List[str] = []
        # MODEL batches only; recipe batches live in the fixed settings-dir
        # parent. Registry access is short critical sections; the lock-free
        # reconciliation scan registers concurrently.
        self._known_batch_dirs: Dict[str, str] = {}
        self._registry_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def stage_model_delete(
        self,
        *,
        scanner: Any,
        target_dir: str,
        file_name: str,
        main_extension: Optional[str],
        original_file_path: str,
        cached_entry: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Rename a model's artifacts into a sibling-of-model staging batch.

        The batch dir is created inside the model file's OWN directory
        (``target_dir``), so staging/undo renames stay within one real
        directory - EXDEV is impossible even when the business path traverses
        nested symlinks to other volumes. Returns the batch id, or ``None``
        when the model root cannot be resolved, or staging failed (caller
        falls back to a hard delete).
        """
        # LOCK-FREE section: opportunistic purge must never run while holding
        # the ops lock (the lock is not re-entrant).
        await self._opportunistic_purge()

        async with self._ops_lock:
            batch_dir: Optional[str] = None
            staged_pairs: List[Dict[str, Any]] = []
            try:
                root = self._find_model_root(scanner, original_file_path)
                if not root:
                    logger.warning(
                        "No model root contains %s; skipping staging",
                        original_file_path,
                    )
                    return None

                artifacts = self._enumerate_model_artifacts(
                    target_dir, file_name, main_extension
                )
                if not artifacts:
                    logger.warning(
                        "No existing artifacts for %s; skipping staging",
                        original_file_path,
                    )
                    return None

                batch_id = self._new_batch_id()
                batch_dir = os.path.join(
                    os.path.abspath(target_dir), PENDING_DELETE_DIR_NAME, batch_id
                )
                os.makedirs(batch_dir, exist_ok=True)

                staged_pairs = self._rename_artifacts_into_batch(
                    batch_dir, artifacts, staged_pairs
                )
                # Attach the model snapshot to the MAIN-file entry (the one
                # whose original path is the model file itself, not the
                # metadata/preview sidecars). Merged bulk manifests therefore
                # carry EVERY deleted model's snapshot on its entry; the
                # top-level model_snapshot is kept for backward compatibility
                # and the single-delete path.
                main_abs = os.path.abspath(original_file_path)
                for entry in staged_pairs:
                    if entry.get("original") == main_abs:
                        entry["snapshot"] = cached_entry
                        break
                manifest = self._build_manifest(
                    batch_id=batch_id,
                    kind="model",
                    model_type=self._resolve_model_type(scanner),
                    expires_at=int(time.time()) + PENDING_DELETE_TTL_SECONDS,
                    entries=staged_pairs,
                    model_snapshot=cached_entry,
                )
                self._write_manifest_atomic(batch_dir, manifest)
                self._remember_root(root)
                await self._remember_batch(batch_id, batch_dir)
                # Arm the per-batch purge timer. Safe inside the lock: task
                # creation does not await, and purge_batch re-reads the
                # manifest's expires_at at fire time, so stale timers no-op.
                self._arm_purge_timer(batch_id)
                logger.info(
                    "Staged model delete batch %s with %d file(s): %s",
                    batch_id,
                    len(staged_pairs),
                    staged_pairs[0]["original"] if staged_pairs else None,
                )
                return batch_id
            except OSError as exc:
                logger.warning(
                    "Staging model %s failed: %s; rolling back", original_file_path, exc
                )
                if batch_dir:
                    self._rollback_model_staging(batch_dir, staged_pairs)
                    self._remove_empty_dir(batch_dir)
                return None
            except Exception as exc:  # defensive - never block the delete flow
                logger.warning(
                    "Unexpected error staging model %s: %s", original_file_path, exc
                )
                return None

    async def stage_recipe_delete(
        self,
        *,
        recipe_json_path: str,
        image_path: Optional[str],
        recipe_data: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Copy a recipe JSON (and, when it exists, its image) into staging.

        Returns the batch id, or ``None`` when staging failed. Missing or
        shared preview images are skipped.
        """
        await self._opportunistic_purge()

        async with self._ops_lock:
            batch_dir: Optional[str] = None
            staged_pairs: List[Dict[str, Any]] = []
            try:
                json_path = os.path.abspath(os.path.normpath(recipe_json_path))
                if not os.path.exists(json_path):
                    logger.warning(
                        "Recipe JSON %s does not exist; skipping staging", json_path
                    )
                    return None

                batch_id = self._new_batch_id()
                batch_dir = os.path.join(self._recipe_staging_parent(), batch_id)
                os.makedirs(batch_dir, exist_ok=True)

                staged_pairs = self._copy_recipe_artifacts(
                    batch_dir, json_path, image_path, staged_pairs
                )
                manifest = self._build_manifest(
                    batch_id=batch_id,
                    kind="recipe",
                    model_type=None,
                    expires_at=int(time.time()) + PENDING_DELETE_TTL_SECONDS,
                    entries=staged_pairs,
                    recipe_snapshot=recipe_data,
                )
                self._write_manifest_atomic(batch_dir, manifest)
                self._arm_purge_timer(batch_id)
                logger.info(
                    "Staged recipe delete batch %s with %d file(s): %s",
                    batch_id,
                    len(staged_pairs),
                    staged_pairs[0]["original"] if staged_pairs else None,
                )
                return batch_id
            except OSError as exc:
                logger.warning(
                    "Staging recipe %s failed: %s; rolling back",
                    recipe_json_path,
                    exc,
                )
                if batch_dir:
                    self._rollback_recipe_staging(batch_dir, staged_pairs)
                    self._remove_empty_dir(batch_dir)
                return None
            except Exception as exc:  # defensive - never block the delete flow
                logger.warning(
                    "Unexpected error staging recipe %s: %s", recipe_json_path, exc
                )
                return None

    async def merge_batches(self, batch_ids: Sequence[str]) -> Optional[str]:
        """Merge several batches into the first batch's manifest.

        Winner is ``batch_ids[0]``. Merging is MANIFEST-ONLY: staged files
        are NEVER moved, so the merge is a pure metadata operation with zero
        data IO and is inherently cross-volume safe (no EXDEV, no rollback).
        Every loser's entries are appended to the winner's manifest with
        their ``staged`` paths unchanged (files keep living in the loser's
        own batch dir - the sibling-of-model staging location), each loser
        dir is recorded in the winner manifest's ``merged_sources``, and each
        loser manifest is stamped ``merged_into`` so its own purge timer, a
        post-restart sweep or a direct undo call no-op. ``expires_at`` is
        re-anchored to ``now + TTL`` at merge time and a FRESH purge timer is
        armed for the winner.

        Returns the winner id, or ``None`` when the winner batch cannot be
        resolved (callers then fall back to the ``batch_ids`` array
        contract).
        """
        if not batch_ids:
            return None

        async with self._ops_lock:
            winner_id = batch_ids[0]
            winner_dir = await self._find_batch_dir(winner_id)
            if not winner_dir:
                return None
            winner_manifest = self._read_manifest(winner_dir)
            if winner_manifest is None:
                return None

            # Build the merged manifest in memory: loser entries are appended
            # with their staged paths UNCHANGED - no file moves, no IO, no
            # EXDEV. Loser dirs remain as physical storage until the merged
            # batch is undone or purged.
            merged_sources: List[str] = []
            seen_loser_dirs: Set[str] = set()
            for loser_id in batch_ids[1:]:
                loser_dir = await self._find_batch_dir(loser_id)
                if not loser_dir or os.path.normpath(loser_dir) == os.path.normpath(
                    winner_dir
                ):
                    continue
                loser_abs = os.path.abspath(loser_dir)
                if loser_abs in seen_loser_dirs:
                    continue
                seen_loser_dirs.add(loser_abs)
                loser_manifest = self._read_manifest(loser_dir)
                if loser_manifest is None:
                    # Corrupted loser: leave it for the sweep to quarantine.
                    continue
                for entry in loser_manifest.get("entries") or []:
                    if entry.get("restored"):
                        continue
                    staged_path = entry.get("staged")
                    if not staged_path or not os.path.exists(staged_path):
                        continue
                    winner_manifest["entries"].append(entry)
                merged_sources.append(loser_abs)

            # Re-anchor expiry and persist the merged manifest atomically - it
            # becomes the ONLY source of truth for every merged file, wherever
            # it physically lives.
            winner_manifest["expires_at"] = (
                int(time.time()) + PENDING_DELETE_TTL_SECONDS
            )
            if merged_sources:
                winner_manifest["merged_sources"] = merged_sources
            try:
                self._write_manifest_atomic(winner_dir, winner_manifest)
            except OSError as exc:
                logger.warning(
                    "Failed to write merged manifest for %s: %s",
                    winner_id,
                    exc,
                )
                return None

            # Stamp each loser manifest so its own purge timer / a later sweep
            # / a direct undo call no-op: the winner owns those files from
            # here on. Best-effort coordination; a failed stamp only risks the
            # loser being swept at its own (earlier) expiry after a restart.
            for loser_dir in merged_sources:
                try:
                    self._mark_merged(loser_dir, winner_id)
                except OSError as exc:  # pragma: no cover - best-effort
                    logger.warning(
                        "Failed to mark merged loser %s: %s", loser_dir, exc
                    )

            # Losers are no longer independently managed.
            for loser_dir in merged_sources:
                await self._forget_batch(os.path.basename(loser_dir))
            await self._remember_batch(winner_id, winner_dir)

            # Arm a fresh purge timer for the winner with the re-anchored
            # expiry (the winner's original timer fires at the OLD expiry and
            # no-ops after re-reading the manifest - without this fresh timer
            # an idle server would never purge the merged batch).
            self._arm_purge_timer(winner_id)
            logger.info("Merged batches %s into %s", list(batch_ids), winner_id)
            return winner_id

    async def undo(self, batch_id: str) -> Dict[str, Any]:
        """Restore every staged file of a batch to its original path.

        Raises ``ValueError`` for unknown batches, expired batches ("Undo
        window expired") and occupied target paths ("Target path occupied").
        Restores entries one at a time, persisting the manifest after each, so
        a mid-undo failure leaves a retry-able state.
        """
        await self._opportunistic_purge()

        async with self._ops_lock:
            batch_dir = await self._find_batch_dir(batch_id)
            if not batch_dir:
                raise ValueError(f"Unknown batch id: {batch_id}")
            manifest = self._read_manifest(batch_dir)
            if manifest is None:
                raise ValueError(f"Manifest missing for batch {batch_id}")

            merged_into = manifest.get("merged_into")
            if merged_into:
                # The batch was merged into another batch: its staged files
                # are owned by the winner's manifest. Undo via the winner so
                # the whole merged batch stays consistent.
                raise ValueError(
                    f"Batch {batch_id} was merged into batch {merged_into}; "
                    "undo that batch instead"
                )

            if manifest.get("state") == "restored":
                return self._undo_result(manifest)

            now = time.time()
            expires_at = manifest.get("expires_at")
            if isinstance(expires_at, (int, float)) and expires_at < now:
                raise ValueError("Undo window expired")

            entries = manifest.get("entries") or []

            # Pre-check ALL target paths (except already-restored entries) so
            # an occupied original path protects the new file and leaves the
            # whole batch intact.
            for entry in entries:
                if entry.get("restored"):
                    continue
                original_path = entry.get("original")
                if original_path and os.path.exists(original_path):
                    raise ValueError("Target path occupied")

            for entry in entries:
                if entry.get("restored"):
                    continue
                staged_path = entry.get("staged")
                original_path = entry.get("original")
                if not staged_path or not original_path:
                    entry["restored"] = True
                    continue
                if not os.path.exists(staged_path):
                    # Staged file already gone (purged or manually removed):
                    # treat as restored and finish the rest of the batch.
                    entry["restored"] = True
                    self._write_manifest_atomic(batch_dir, manifest)
                    continue
                self._restore_file(staged_path, original_path)
                entry["restored"] = True
                # Persist after each entry so a mid-undo failure is retry-able.
                self._write_manifest_atomic(batch_dir, manifest)

            manifest["state"] = "restored"
            try:
                self._write_manifest_atomic(batch_dir, manifest)
            except OSError as exc:
                logger.warning(
                    "Failed to mark manifest restored for %s: %s", batch_id, exc
                )

            # Remove the manifest + batch dir only after all entries restored.
            self._remove_manifest(batch_dir)
            self._remove_empty_dir(batch_dir)
            await self._forget_batch(batch_id)
            # Clean up merged loser dirs (their staged files were restored
            # above) and drop them from the registry too.
            for loser_id in self._remove_merged_batch_dirs(manifest):
                await self._forget_batch(loser_id)

            logger.info("Restored pending-delete batch %s", batch_id)
            return self._undo_result(manifest)

    async def purge_expired(self, scan_roots: bool = False) -> int:
        """Purge every expired batch.

        Default (registry-only): iterates a SNAPSHOT of the in-process MODEL
        batch registry plus a shallow check of the fixed recipe staging
        parent - cheap, no tree walk per delete. With ``scan_roots=True``
        (startup sweep only) a reconciliation pass re-discovers every batch
        on disk under the model roots and registers it FIRST, so crash
        leftovers and externally created batches are covered too.

        Lock-free by design: delegates each batch to :meth:`purge_batch`,
        which acquires the ops lock. Never call this while holding the ops
        lock.
        """
        purged = 0
        if scan_roots:
            await self._reconcile_scan_roots()
        # MODEL batches: snapshot so purge_batch can remove entries
        # mid-iteration without a dict-changed-size error.
        batch_ids: List[str] = [
            batch_id for batch_id, _dir in await self._registered_batch_dirs()
        ]
        # RECIPE batches: fixed settings-dir parent, shallow check as before.
        recipe_parent = self._recipe_staging_parent()
        for name in self._list_dir_names(recipe_parent):
            if name.endswith(ORPHANED_SUFFIX):
                # Quarantine is terminal - never re-rename or delete.
                continue
            if name not in batch_ids:
                batch_ids.append(name)
        for batch_id in batch_ids:
            try:
                await self.purge_batch(batch_id)
                purged += 1
            except Exception as exc:  # defensive - sweep must not crash
                logger.warning("Failed to purge batch %s: %s", batch_id, exc)
        return purged

    async def _reconcile_scan_roots(self) -> None:
        """Register every pending-delete batch found under the model roots.

        Runs at startup (``purge_expired(scan_roots=True)``) to re-discover
        batches left over from a previous process or created externally.
        Registers ALL non-orphaned batch dirs regardless of manifest validity:
        malformed/manifest-less dirs must reach ``_purge_batch_dir`` so it can
        QUARANTINE them (preserving the pre-registry sweep semantics). The
        walk only descends into dirs literally named ``.lm-pending-delete``,
        so false positives are structurally limited.

        The filesystem walk itself runs in a worker thread so a large or slow
        library cannot block the event loop at startup; only the (rare) batch
        registration awaits run on the loop.
        """
        roots = await self._get_all_model_roots()
        loop = asyncio.get_event_loop()
        staging_parents = await loop.run_in_executor(
            None,  # Use default thread pool
            self._collect_staging_parents,  # Run the tree walk off the loop
            roots,
        )
        for staging_parent in staging_parents:
            await self._register_batch_candidates(staging_parent)

    def _collect_staging_parents(self, roots: Sequence[str]) -> List[str]:
        """Walk every model root and return its staging-parent dirs.

        Pure synchronous filesystem discovery with no awaits: walks with
        ``followlinks=True, topdown=True``, prunes symlink cycles via a
        per-root ``visited`` realpath set (realpath is used ONLY for this
        dedup set - the returned paths are the unresolved business paths),
        filters out :func:`_is_excluded_dir` dirs, and collects every dir
        named ``.lm-pending-delete`` (including the case where a model root
        itself is one). Results are returned in walk order.
        """
        from .model_scanner import _is_excluded_dir

        staging_parents: List[str] = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            visited: Set[str] = set()
            for dirpath, dirnames, _files in os.walk(
                root, followlinks=True, topdown=True
            ):
                real_dir = os.path.realpath(dirpath)
                if real_dir in visited:
                    # Symlink cycle: prune descent and move on.
                    dirnames[:] = []
                    continue
                visited.add(real_dir)
                if os.path.basename(dirpath) == PENDING_DELETE_DIR_NAME:
                    # The current dir IS a staging parent (reachable only when
                    # a model root itself is one): collect its batches.
                    staging_parents.append(dirpath)
                    dirnames[:] = []
                    continue
                next_dirs: List[str] = []
                for name in dirnames:
                    if name == PENDING_DELETE_DIR_NAME:
                        staging_parents.append(os.path.join(dirpath, name))
                    elif _is_excluded_dir(name):
                        continue
                    else:
                        next_dirs.append(name)
                dirnames[:] = next_dirs
        return staging_parents

    async def _register_batch_candidates(self, staging_parent: str) -> None:
        """Register every non-orphaned batch subdir of a staging parent."""
        for name in self._list_dir_names(staging_parent):
            if name.endswith(ORPHANED_SUFFIX):
                # Quarantine is terminal - never re-register.
                continue
            await self._remember_batch(name, os.path.join(staging_parent, name))

    async def purge_batch(self, batch_id: str) -> None:
        """Purge one batch. Silent no-op for missing/undone/not-yet-expired.

        Missing staged files (already-restored / partially-restored batches)
        are treated as already-purged. A per-file purge failure (locked file)
        skips only that file and keeps the batch dir for the next round.
        """
        async with self._ops_lock:
            batch_dir = await self._find_batch_dir(batch_id)
            if not batch_dir:
                return
            if self._purge_batch_dir(batch_dir):
                # Both purge and quarantine remove the batch dir (quarantine
                # renames it to *.orphaned), so the registry entry is stale.
                await self._forget_batch(batch_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _opportunistic_purge(self) -> None:
        """Fire the opportunistic sweep. Cheap when empty; never locked."""
        try:
            await self.purge_expired()
        except Exception as exc:  # defensive - staging/undo must still proceed
            logger.warning("Opportunistic pending-delete purge failed: %s", exc)

    def _remember_root(self, root: str) -> None:
        """Record a root the service has staged into (in-process registry)."""
        if root and root not in self._known_roots:
            self._known_roots.append(root)

    async def _remember_batch(self, batch_id: str, batch_dir: str) -> None:
        """Register a MODEL batch in the in-process registry (idempotent).

        Short critical section (dict mutation only, no I/O while holding the
        lock) so the lock-free reconciliation scan can register concurrently.
        """
        async with self._registry_lock:
            self._known_batch_dirs[batch_id] = batch_dir

    async def _forget_batch(self, batch_id: str) -> None:
        """Remove a MODEL batch from the in-process registry (idempotent)."""
        async with self._registry_lock:
            self._known_batch_dirs.pop(batch_id, None)

    async def _registered_batch_dirs(self) -> List[Tuple[str, str]]:
        """Return a SNAPSHOT of (batch_id, batch_dir) registry pairs.

        The snapshot lets purge iterate safely while purge_batch removes
        entries mid-loop (no dict-changed-size error).
        """
        async with self._registry_lock:
            return list(self._known_batch_dirs.items())

    def _find_model_root(self, scanner: Any, original_file_path: Optional[str]) -> Optional[str]:
        """Return the configured root containing ``original_file_path``."""
        finder = getattr(scanner, "_find_root_for_file", None)
        if callable(finder):
            try:
                root = cast(Optional[str], finder(original_file_path))
                if root:
                    return os.path.abspath(root)
            except Exception as exc:  # defensive - fall back to roots scan
                logger.debug("_find_root_for_file failed: %s", exc)

        if not original_file_path:
            return None
        roots_getter = getattr(scanner, "get_model_roots", None)
        if not callable(roots_getter):
            return None
        try:
            normalized = os.path.abspath(os.path.normpath(original_file_path))
            for root in cast(Sequence[str], roots_getter()) or []:
                root_abs = os.path.abspath(os.path.normpath(root))
                if normalized == root_abs or normalized.startswith(root_abs + os.sep):
                    return root_abs
        except Exception as exc:  # defensive - never block the delete flow
            logger.debug("get_model_roots fallback failed: %s", exc)
        return None

    def _resolve_model_type(self, scanner: Any) -> Optional[str]:
        raw = getattr(scanner, "model_type", None)
        if not raw:
            return None
        return _MODEL_TYPE_PAGE_MAP.get(raw, raw)

    def _enumerate_model_artifacts(
        self, target_dir: str, file_name: str, main_extension: Optional[str]
    ) -> List[str]:
        """Enumerate existing artifacts exactly like delete_model_artifacts."""
        main_extension = ".safetensors" if main_extension is None else main_extension
        main_file = f"{file_name}{main_extension}" if main_extension else file_name
        patterns = [main_file, f"{file_name}.metadata.json"]
        for ext in PREVIEW_EXTENSIONS:
            patterns.append(f"{file_name}{ext}")

        artifacts: List[str] = []
        for pattern in patterns:
            path = os.path.abspath(os.path.join(target_dir, pattern))
            if os.path.exists(path):
                artifacts.append(path)
        return artifacts

    def _rename_artifacts_into_batch(
        self,
        batch_dir: str,
        artifacts: Sequence[str],
        staged_pairs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Rename artifacts into the batch dir, recording progress per file.

        Progress is appended to ``staged_pairs`` before the next move so a
        mid-way OSError leaves the caller with the already-moved files for
        rollback.
        """
        for original_path in artifacts:
            staged_path = os.path.join(batch_dir, os.path.basename(original_path))
            os.rename(original_path, staged_path)
            staged_pairs.append(
                {
                    "staged": os.path.abspath(staged_path),
                    "original": os.path.abspath(original_path),
                    "restored": False,
                }
            )
        return staged_pairs

    def _copy_recipe_artifacts(
        self,
        batch_dir: str,
        json_path: str,
        image_path: Optional[str],
        staged_pairs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Copy the recipe JSON and, when it exists, the image into the batch."""
        staged_json = os.path.join(batch_dir, os.path.basename(json_path))
        shutil.copy2(json_path, staged_json)
        staged_pairs.append(
            {
                "staged": os.path.abspath(staged_json),
                "original": json_path,
                "restored": False,
            }
        )
        if image_path:
            image_abs = os.path.abspath(os.path.normpath(image_path))
            if os.path.exists(image_abs):
                staged_image = os.path.join(batch_dir, os.path.basename(image_abs))
                shutil.copy2(image_abs, staged_image)
                staged_pairs.append(
                    {
                        "staged": os.path.abspath(staged_image),
                        "original": image_abs,
                        "restored": False,
                    }
                )
        return staged_pairs

    def _restore_file(self, staged_path: str, original_path: str) -> None:
        """Restore a staged file to its original path, tolerating EXDEV.

        ``os.rename`` is atomic and preferred (model staging and most recipe
        restores are same-volume). Recipe staging copies into the settings-dir
        staging parent, which may live on a DIFFERENT filesystem than the
        recipes dir; rename then raises EXDEV. Fall back to ``shutil.copy2`` +
        ``os.remove`` so the bytes are restored and the staged copy removed.
        """
        try:
            os.rename(staged_path, original_path)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copy2(staged_path, original_path)
            os.remove(staged_path)

    def _rollback_model_staging(
        self, batch_dir: str, staged_pairs: Sequence[Dict[str, Any]]
    ) -> None:
        """Rename already-staged files back to their originals."""
        for pair in reversed(list(staged_pairs)):
            staged_path = pair.get("staged")
            original_path = pair.get("original")
            if not staged_path or not original_path:
                continue
            if not os.path.exists(staged_path):
                continue
            try:
                os.rename(staged_path, original_path)
            except OSError as exc:  # pragma: no cover - best-effort rollback
                logger.warning(
                    "Failed to roll back staged file %s -> %s: %s",
                    staged_path,
                    original_path,
                    exc,
                )

    def _rollback_recipe_staging(
        self, batch_dir: str, staged_pairs: Sequence[Dict[str, Any]]
    ) -> None:
        """Remove staged copies (recipe originals were never moved)."""
        for pair in staged_pairs:
            staged_path = pair.get("staged")
            if not staged_path:
                continue
            try:
                if os.path.exists(staged_path):
                    os.remove(staged_path)
            except OSError as exc:  # pragma: no cover - best-effort rollback
                logger.warning(
                    "Failed to remove staged copy %s: %s", staged_path, exc
                )

    def _mark_merged(self, loser_dir: str, winner_id: str) -> None:
        """Stamp ``merged_into`` on a loser manifest (best-effort).

        The stamp makes the loser's own purge timer, post-restart sweeps and
        direct undo calls no-op, so the winner's merged batch stays the only
        owner of the loser's staged files until it is undone or purged.
        """
        loser_manifest = self._read_manifest(loser_dir)
        if loser_manifest is None:
            return
        loser_manifest["merged_into"] = winner_id
        self._write_manifest_atomic(loser_dir, loser_manifest)

    def _remove_merged_batch_dirs(self, manifest: Dict[str, Any]) -> List[str]:
        """Remove merged loser batch dirs once their files were handled.

        Called after a merged batch has been fully undone or purged: each
        loser manifest (stamped ``merged_into``) and its now-empty dir are
        removed so the sweep never quarantines an orphaned staging dir.
        Best-effort - returns the removed batch ids for registry cleanup.
        """
        removed: List[str] = []
        for src in manifest.get("merged_sources") or []:
            if not isinstance(src, str) or not src:
                continue
            self._remove_manifest(src)
            self._remove_empty_dir(src)
            removed.append(os.path.basename(src))
        return removed

    def _purge_batch_dir(self, batch_dir: str) -> bool:
        """Purge one batch dir. Returns True when the batch was purged/removed."""
        if not os.path.isdir(batch_dir):
            return False

        manifest = self._read_manifest(batch_dir)
        if manifest is None:
            # Corrupted or manifest-less batch: quarantine, NEVER delete the
            # staged files (they may be the only copy of the user's data).
            self._quarantine_batch_dir(batch_dir)
            return True

        if manifest.get("merged_into"):
            # Merged into another batch: the winner owns these staged files.
            # The loser's own purge timer / post-restart sweep must not remove
            # them early (the winner re-anchored the merged expiry to give the
            # whole bulk one undo window).
            return False

        if manifest.get("state") == "restored":
            return False

        expires_at = manifest.get("expires_at")
        if not isinstance(expires_at, (int, float)) or expires_at >= time.time():
            # Not yet expired - stale timers from merged-away/undone batches
            # are harmless.
            return False

        entries = manifest.get("entries") or []
        remaining: List[Dict[str, Any]] = []
        for entry in entries:
            staged_path = entry.get("staged")
            if not staged_path or not os.path.exists(staged_path):
                # Missing staged file = already restored / already purged.
                continue
            try:
                os.remove(staged_path)
            except OSError as exc:
                logger.warning(
                    "Skipping locked staged file %s: %s", staged_path, exc
                )
                remaining.append(entry)

        if remaining:
            # Never remove the batch dir past per-file errors; the batch is
            # retried by the next opportunistic purge.
            return False

        self._remove_manifest(batch_dir)
        self._remove_empty_dir(batch_dir)
        self._remove_merged_batch_dirs(manifest)
        return True

    def _quarantine_batch_dir(self, batch_dir: str) -> str:
        """Rename a malformed batch dir to ``<batch_id>.orphaned`` (terminal)."""
        orphaned_dir = f"{batch_dir}{ORPHANED_SUFFIX}"
        if os.path.exists(orphaned_dir):
            orphaned_dir = f"{batch_dir}-{int(time.time())}{ORPHANED_SUFFIX}"
        try:
            os.rename(batch_dir, orphaned_dir)
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("Failed to quarantine %s: %s", batch_dir, exc)
            return batch_dir
        logger.warning(
            "Quarantined malformed/manifest-less pending-delete batch %s",
            os.path.basename(batch_dir),
        )
        return orphaned_dir

    def _build_manifest(
        self,
        *,
        batch_id: str,
        kind: str,
        model_type: Optional[str],
        expires_at: int,
        entries: Sequence[Dict[str, Any]],
        model_snapshot: Any = None,
        recipe_snapshot: Any = None,
    ) -> Dict[str, Any]:
        is_model = kind == "model"
        return {
            "batch_id": batch_id,
            "kind": kind,
            "model_type": model_type if is_model else None,
            "state": "staged",
            "expires_at": int(expires_at),
            "entries": list(entries),
            "model_snapshot": model_snapshot if is_model else None,
            "recipe_snapshot": recipe_snapshot if not is_model else None,
        }

    def _undo_result(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        restored_paths = [
            entry["original"]
            for entry in manifest.get("entries") or []
            if entry.get("restored") and entry.get("original")
        ]
        return {
            "batch_id": manifest.get("batch_id"),
            "kind": manifest.get("kind"),
            "model_type": manifest.get("model_type"),
            "restored": restored_paths,
        }

    def _write_manifest_atomic(
        self, batch_dir: str, manifest: Dict[str, Any]
    ) -> None:
        """Write manifest.json atomically (temp file + os.replace)."""
        manifest_path = os.path.join(batch_dir, MANIFEST_FILE_NAME)
        fd, temp_path = tempfile.mkstemp(
            dir=batch_dir, prefix=".manifest-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False)
            os.replace(temp_path, manifest_path)
        except BaseException:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise

    def _read_manifest(self, batch_dir: str) -> Optional[Dict[str, Any]]:
        manifest_path = os.path.join(batch_dir, MANIFEST_FILE_NAME)
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Corrupted pending-delete manifest at %s: %s", manifest_path, exc
            )
            return None
        if not isinstance(payload, dict):
            logger.warning("Invalid pending-delete manifest at %s", manifest_path)
            return None
        return payload

    def _recipe_staging_parent(self) -> str:
        # Resolve through the module namespace so the conftest settings-dir
        # isolation patch takes effect at call time.
        return os.path.join(
            settings_paths.get_settings_dir(create=True), PENDING_DELETE_DIR_NAME
        )

    async def _get_all_model_roots(self) -> List[str]:
        """Collect every configured model root across all scanner types.

        Combines the in-process staging roots with the ServiceRegistry's
        per-type scanners so sweeps cover every scanner type while undo/purge
        still resolve batches staged before the registry was populated.
        """
        from .service_registry import ServiceRegistry

        roots: List[str] = []
        for root in self._known_roots:
            if root and root not in roots:
                roots.append(root)
        for getter_name in (
            "get_lora_scanner",
            "get_checkpoint_scanner",
            "get_embedding_scanner",
        ):
            getter = getattr(ServiceRegistry, getter_name, None)
            if not callable(getter):
                continue
            try:
                scanner = await cast(Callable[[], Awaitable[Any]], getter)()
            except Exception as exc:  # defensive - keep sweeping other types
                logger.debug(
                    "Failed to resolve %s for purge enumeration: %s",
                    getter_name,
                    exc,
                )
                continue
            if scanner is None:
                continue
            get_roots = getattr(scanner, "get_model_roots", None)
            if not callable(get_roots):
                continue
            try:
                scanner_roots = cast(Sequence[Any], get_roots())
            except Exception as exc:  # defensive
                logger.debug(
                    "get_model_roots failed for %s: %s", getter_name, exc
                )
                continue
            for root in scanner_roots or []:
                if root and root not in roots:
                    roots.append(root)
        return roots

    async def _find_batch_dir(self, batch_id: str) -> Optional[str]:
        """Locate a batch directory.

        Registry lookup first (fast path; stale entries are forgotten when
        their dir vanished); then a targeted scan of the model roots for a
        batch dir named exactly ``batch_id`` under a ``.lm-pending-delete``
        parent (restart / externally created batches; manifest verification
        applies so random uuid-named user dirs are never registered); finally
        the fixed recipe staging parent. Returns ``None`` (404 semantics)
        when not found.
        """
        if not batch_id:
            return None
        # 1) Registry fast path.
        async with self._registry_lock:
            known = self._known_batch_dirs.get(batch_id)
        if known is not None:
            if os.path.isdir(known):
                return known
            await self._forget_batch(batch_id)  # stale entry - dir is gone
        # 2) Targeted scan fallback across the model roots.
        for root in await self._get_all_model_roots():
            if not os.path.isdir(root):
                continue
            candidate = await self._scan_root_for_batch(root, batch_id)
            if candidate is not None:
                await self._remember_batch(batch_id, candidate)
                return candidate
        # 3) Recipe batches: fixed settings-dir parent, shallow check.
        candidate = os.path.join(self._recipe_staging_parent(), batch_id)
        if os.path.isdir(candidate):
            return candidate
        return None

    async def _scan_root_for_batch(self, root: str, batch_id: str) -> Optional[str]:
        """Search one model root for a batch dir named exactly ``batch_id``.

        Walks the root (``followlinks=True``) with a realpath cycle guard,
        looking for ``.lm-pending-delete`` parents whose subdir matches
        ``batch_id`` AND has a parseable manifest. The manifest check prevents
        random uuid-named user dirs from being treated as batches (a batch
        with no parseable manifest cannot be undone anyway).
        """
        from .model_scanner import _is_excluded_dir

        visited: Set[str] = set()
        for dirpath, dirnames, _files in os.walk(root, followlinks=True, topdown=True):
            real_dir = os.path.realpath(dirpath)
            if real_dir in visited:
                # Symlink cycle: prune descent and move on.
                dirnames[:] = []
                continue
            visited.add(real_dir)
            if os.path.basename(dirpath) == PENDING_DELETE_DIR_NAME:
                candidate = os.path.join(dirpath, batch_id)
                if (
                    os.path.isdir(candidate)
                    and self._read_manifest(candidate) is not None
                ):
                    return candidate
                dirnames[:] = []
                continue
            next_dirs: List[str] = []
            for name in dirnames:
                if name == PENDING_DELETE_DIR_NAME:
                    candidate = os.path.join(dirpath, name, batch_id)
                    if (
                        os.path.isdir(candidate)
                        and self._read_manifest(candidate) is not None
                    ):
                        return candidate
                    continue
                if _is_excluded_dir(name):
                    continue
                next_dirs.append(name)
            dirnames[:] = next_dirs
        return None

    def _list_dir_names(self, parent: str) -> List[str]:
        try:
            return [
                name
                for name in os.listdir(parent)
                if os.path.isdir(os.path.join(parent, name))
            ]
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to list staging parent %s: %s", parent, exc)
            return []

    def _remove_manifest(self, batch_dir: str) -> None:
        try:
            os.remove(os.path.join(batch_dir, MANIFEST_FILE_NAME))
        except OSError as exc:  # pragma: no cover - best-effort
            logger.debug("Failed to remove manifest in %s: %s", batch_dir, exc)

    def _remove_empty_dir(self, directory: str) -> None:
        try:
            os.rmdir(directory)
        except OSError as exc:
            logger.debug("Directory %s not empty or missing: %s", directory, exc)

    def _new_batch_id(self) -> str:
        return uuid.uuid4().hex

    def _arm_purge_timer(self, batch_id: str) -> None:
        """Spawn a fire-and-forget purge timer for a batch.

        The timer sleeps until the batch's current expiry and then calls
        purge_batch, which re-reads the manifest's ``expires_at`` at fire time
        so merged-away/undone/not-yet-expired batches are silent no-ops.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        task = _create_task(
            self._purge_batch_after_ttl(batch_id),
            name=f"pending_delete_purge_{batch_id}",
        )
        self._purge_tasks.add(task)
        task.add_done_callback(self._purge_tasks.discard)

    async def _purge_batch_after_ttl(self, batch_id: str) -> None:
        try:
            delay = await self._seconds_until_expiry(batch_id)
            if delay is None:
                return
            await asyncio.sleep(max(0.0, delay))
            await self.purge_batch(batch_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # defensive - a timer must never crash the loop
            logger.warning("Pending-delete purge timer for %s failed: %s", batch_id, exc)

    async def _seconds_until_expiry(self, batch_id: str) -> Optional[float]:
        batch_dir = await self._find_batch_dir(batch_id)
        if not batch_dir:
            return None
        manifest = self._read_manifest(batch_dir)
        if manifest is None:
            return None
        expires_at = manifest.get("expires_at")
        if not isinstance(expires_at, (int, float)):
            return None
        return float(expires_at) - time.time()

    def _cancel_purge_tasks(self) -> None:
        for task in list(self._purge_tasks):
            task.cancel()
        self._purge_tasks.clear()


def _reset_pending_delete_service() -> None:
    """Reset the singleton and cancel in-flight purge timers (tests/shutdown)."""
    instance = PendingDeleteService._instance
    if instance is not None:
        instance._cancel_purge_tasks()
    PendingDeleteService._instance = None


async def get_pending_delete_service() -> PendingDeleteService:
    """Return the lazily initialised global :class:`PendingDeleteService`."""
    return await PendingDeleteService.get_instance()
