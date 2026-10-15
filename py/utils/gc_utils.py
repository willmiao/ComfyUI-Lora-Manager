"""Helpers for keeping ComfyUI's periodic full GC cheap.

ComfyUI runs a full ``gc.collect()`` after every prompt, and the cost of that
collection scales with the number of GC-tracked objects in the process. LoRA
Manager keeps large long-lived caches in memory (one dict per model plus hash
indexes, recipe caches, the i18n trees), so on big libraries every post-prompt
collection walks hundreds of thousands of objects while holding the GIL,
freezing the whole server for seconds (issue #1147).

Freezing those objects once they are hydrated moves them into the permanent
generation, which the collector no longer scans.
"""

from __future__ import annotations

import gc
import logging

logger = logging.getLogger(__name__)


def freeze_long_lived_objects(reason: str) -> None:
    """Move all currently tracked objects into the permanent generation.

    Runs a full collection first so only reachable objects are frozen.
    Best-effort: failures are logged, never raised.
    """
    try:
        collected = gc.collect()
        gc.freeze()
        logger.debug(
            "LoRA Manager: froze GC-tracked objects after %s (%d unreachable collected)",
            reason,
            collected,
        )
    except Exception:  # pragma: no cover - defensive guard
        logger.warning(
            "LoRA Manager: failed to freeze GC-tracked objects after %s",
            reason,
            exc_info=True,
        )
