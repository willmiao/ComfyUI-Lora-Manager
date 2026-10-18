# pyright: reportImportCycles=false
# Lazy (function-local) imports still count as static edges in basedpyright's
# reportImportCycles, so the ServiceRegistry singleton pattern necessarily forms
# import cycles. Breaking them would require an architectural refactor.
"""Backfill the quantization checked state for models loaded from a persisted snapshot.

The SQLite persistent cache predates the quantization feature, so entries
hydrated from it have a NULL ``quantization`` column (the "not checked yet"
state). This service detects the quantization for each such model — once per
process — and persists it through the scanner's single write path
(:meth:`ModelScanner.update_quantization_for_model`), marking every visited
row so a subsequent run finds nothing left to do.

Three-state contract honored here:

- ``NULL`` (sqlite) / absent (dict)  = not checked yet  → backfill computes it
- ``''`` (sqlite/dict) / JSON null   = checked, no value available → never recompute
- canonical name ("Q4_K_M", "FP8")   = value → never recompute
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import TYPE_CHECKING, Optional

from ..utils.sidecar_paths import get_metadata_path

if TYPE_CHECKING:  # pragma: no cover - type-check only; runtime imports are local
    from .model_scanner import ModelScanner

logger = logging.getLogger(__name__)


def _resolve_quantization(file_path: str) -> str:
    """Resolve the quantization for a model file.

    Content detection (GGUF ``general.file_type`` / safetensors tensor
    dtypes) is authoritative. The Civitai fp8 flag from the sidecar is only
    a fallback for files whose content detection is inconclusive. Returns
    ``''`` when neither yields a value.
    """
    from ..utils.gguf_utils import detect_quantization  # local import avoids cycles

    quantization = detect_quantization(file_path)
    if quantization:
        return quantization
    try:
        metadata_path = get_metadata_path(file_path)
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                from ..utils.models import quantization_from_civitai_files  # local import avoids cycles

                sha256 = (payload.get("sha256") or "").lower()
                civitai_quantization = quantization_from_civitai_files(payload.get("civitai"), sha256)
                if civitai_quantization:
                    return civitai_quantization
    except Exception:
        pass
    return ""


class QuantizationBackfillService:
    """Detect and persist quantization for models missing a checked state."""

    _instance: Optional["QuantizationBackfillService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        # Re-entrancy guard per model type: scanners for different model types
        # initialize concurrently (lora_manager.py), so a global guard would
        # silently skip every type but the first to start. Each model type
        # runs its own backfill; a duplicate trigger for the same type no-ops.
        self._running_types: set[str] = set()

    @classmethod
    def get_instance(cls) -> "QuantizationBackfillService":
        """Return the process-wide singleton instance."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def backfill(self, scanner: "ModelScanner") -> int:
        """Detect quantization for every un-checked model of ``scanner.model_type``.

        Each candidate file is read once via
        :func:`~py.utils.gguf_utils.detect_quantization` (cheap: header only)
        and the result is persisted through
        ``scanner.update_quantization_for_model``. Files that no longer exist
        on disk are skipped — they are intentionally NOT marked, because
        scanner cleanup removes the stale row later.

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

            persistent = getattr(scanner, "_persistent_cache", None) or get_persistent_cache()
            paths = persistent.get_models_missing_quantization(model_type)

            loop = asyncio.get_running_loop()
            count = 0
            for path in paths:
                # A file that no longer exists must not be marked; scanner
                # cleanup removes the stale row later. The existence check and
                # detection run in the executor so the loop stays responsive
                # to API requests while the backfill iterates a large library.
                if not await loop.run_in_executor(None, os.path.exists, path):
                    continue
                quantization = await loop.run_in_executor(None, _resolve_quantization, path)
                if await scanner.update_quantization_for_model(model_type, path, quantization):
                    count += 1

            if paths:
                logger.info(
                    "Quantization backfill: updated %d/%d models for %s",
                    count,
                    len(paths),
                    model_type,
                )
            else:
                # Steady state after the first run: nothing left to backfill.
                logger.debug("Quantization backfill: nothing to process for %s", model_type)
            return count
        except Exception as exc:
            logger.warning(
                "Quantization backfill failed for %s: %s",
                getattr(scanner, "model_type", "?"),
                exc,
            )
            return 0
        finally:
            self._running_types.discard(model_type)
