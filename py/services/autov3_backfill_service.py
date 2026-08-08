# pyright: reportImportCycles=false
# Lazy (function-local) imports still count as static edges in basedpyright's
# reportImportCycles, so the ServiceRegistry singleton pattern necessarily forms
# import cycles. Breaking them would require an architectural refactor.
"""Backfill the AutoV3 checked state for models loaded from a persisted snapshot.

The SQLite persistent cache predates the AutoV3 feature, so entries hydrated
from it have a NULL ``autov3`` column (the "not checked yet" state). This
service computes the embedded AutoV3 hash for each such model — once per
process — and persists it through the scanner's single write path
(:meth:`ModelScanner.update_autov3_for_model`), marking every visited row so a
subsequent run finds nothing left to do.

Three-state contract honored here:

- ``NULL`` (sqlite) / absent (dict)  = not checked yet  → backfill computes it
- ``''`` (sqlite/dict) / JSON null   = checked, no value available → never recompute
- 12-char lowercase hex              = value → never recompute
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - type-check only; runtime imports are local
    from .model_scanner import ModelScanner

logger = logging.getLogger(__name__)


def _resolve_autov3(file_path: str) -> str:
    """Resolve the AutoV3 hash for a model file.

    Prefers the Civitai AutoV3 reported for the file whose SHA256 matches
    (the authoritative value for recipe matching); falls back to the embedded
    safetensors header hash. Returns ``''`` when neither is available.
    """
    try:
        metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                from ..utils.models import autov3_from_civitai_files  # local import avoids cycles

                sha256 = (payload.get("sha256") or "").lower()
                civitai_autov3 = autov3_from_civitai_files(payload.get("civitai"), sha256)
                if civitai_autov3:
                    return civitai_autov3
    except Exception:
        pass
    from ..utils.file_utils import calculate_autov3  # local import avoids cycles

    return calculate_autov3(file_path) or ""


class Autov3BackfillService:
    """Compute and persist AutoV3 hashes for models missing a checked state."""

    _instance: Optional["Autov3BackfillService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        # Re-entrancy guard per model type: scanners for different model types
        # initialize concurrently (lora_manager.py), so a global guard would
        # silently skip every type but the first to start. Each model type
        # runs its own backfill; a duplicate trigger for the same type no-ops.
        self._running_types: set[str] = set()

    @classmethod
    def get_instance(cls) -> "Autov3BackfillService":
        """Return the process-wide singleton instance."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def backfill(self, scanner: "ModelScanner") -> int:
        """Compute AutoV3 for every un-checked model of ``scanner.model_type``.

        Each candidate file is read once via :func:`~py.utils.file_utils.calculate_autov3`
        (cheap: safetensors header only) and the result is persisted through
        ``scanner.update_autov3_for_model``. Files that no longer exist on
        disk are skipped — they are intentionally NOT marked, because scanner
        cleanup removes the stale row later.

        Returns:
            The number of models successfully updated. Never raises; on any
            failure a warning is logged and ``0`` is returned. A duplicate
            trigger for a model type that is already being backfilled returns
            ``0`` immediately; different model types run concurrently.
        """
        model_type = scanner.model_type
        if model_type in self._running_types:
            return 0
        self._running_types.add(model_type)
        try:
            # Local imports avoid import cycles at module load time.
            from .persistent_model_cache import get_persistent_cache
            from ..utils.file_utils import calculate_autov3

            persistent = getattr(scanner, "_persistent_cache", None) or get_persistent_cache()
            paths = persistent.get_models_missing_autov3(model_type)

            loop = asyncio.get_running_loop()
            count = 0
            for path in paths:
                # A file that no longer exists must not be marked; scanner
                # cleanup removes the stale row later. The existence check and
                # hash resolution run in the executor so the loop stays
                # responsive to API requests while the backfill iterates a
                # large library.
                if not await loop.run_in_executor(None, os.path.exists, path):
                    continue
                autov3 = await loop.run_in_executor(None, _resolve_autov3, path)
                if await scanner.update_autov3_for_model(model_type, path, autov3):
                    count += 1

            if paths:
                logger.info(
                    "AutoV3 backfill: updated %d/%d models for %s",
                    count,
                    len(paths),
                    model_type,
                )
            else:
                # Steady state after the first run: nothing left to backfill.
                logger.debug("AutoV3 backfill: nothing to process for %s", model_type)
            return count
        except Exception as exc:
            logger.warning(
                "AutoV3 backfill failed for %s: %s",
                getattr(scanner, "model_type", "?"),
                exc,
            )
            return 0
        finally:
            self._running_types.discard(model_type)
