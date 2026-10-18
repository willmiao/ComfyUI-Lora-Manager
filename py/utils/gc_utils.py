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

import asyncio
import gc
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Settle time before a post-rebuild re-freeze fires. Scanning and the tasks
# chained to it (persistence, enrichment, index builds) keep allocating
# short-lived objects right after a rebuild returns; freezing too early would
# move some of that transient garbage into the permanent generation, where it
# can never be collected.
_REFREEZE_DELAY_SECONDS = 10.0

_pending_refreeze: Optional[asyncio.TimerHandle] = None


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


def schedule_refreeze_after_rebuild(
    reason: str, delay: float = _REFREEZE_DELAY_SECONDS
) -> None:
    """Schedule a debounced re-freeze for after a cache rebuild settles.

    A full rebuild replaces the frozen cache with newly allocated objects,
    which are GC-tracked again, so ComfyUI's post-prompt gc.collect() gets
    expensive once more. Re-freezing after a short settle delay moves the new
    cache into the permanent generation. Debounced: a library switch re-init
    fires this once per scanner, and only the last schedule wins. No-op when
    no event loop is running.
    """
    global _pending_refreeze
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _pending_refreeze is not None:
        _pending_refreeze.cancel()
    _pending_refreeze = loop.call_later(delay, freeze_long_lived_objects, reason)
