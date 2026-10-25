"""Helpers for keeping ComfyUI's periodic full GC cheap.

ComfyUI runs a full ``gc.collect()`` after every prompt, and the cost of that
collection scales with the number of GC-tracked objects in the process. LoRA
Manager keeps large long-lived caches in memory (one dict per model plus hash
indexes, recipe caches, the i18n trees), so on big libraries every post-prompt
collection walks hundreds of thousands of objects while holding the GIL,
freezing the whole server for seconds (issue #1147).

Freezing those objects once they are hydrated moves them into the permanent
generation, which the collector no longer scans. Incremental cache writes
(downloads, reconciles, metadata syncs) keep adding tracked objects after the
startup freeze, so they schedule a debounced re-freeze once the write burst
settles (issue #1161).
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Settle time before a post-rebuild re-freeze fires. Scanning and the tasks
# chained to it (persistence, enrichment, index builds) keep allocating
# short-lived objects right after a rebuild returns; freezing too early would
# move some of that transient garbage into the permanent generation, where it
# can never be collected.
_REFREEZE_DELAY_SECONDS = 10.0

# Upper bound on idle-guard reschedules. A server running prompts back-to-back
# for longer than this many settle delays simply skips the freeze; the next
# cache mutation schedules a fresh attempt.
_REFREEZE_MAX_RETRIES = 6

_pending_refreeze: Optional[asyncio.TimerHandle] = None


def freeze_long_lived_objects(reason: str) -> None:
    """Move all currently tracked objects into the permanent generation.

    Runs a full collection first so only reachable objects are frozen.
    Best-effort: failures are logged, never raised.
    """
    try:
        debug_logging = logger.isEnabledFor(logging.DEBUG)
        started = time.perf_counter()
        tracked_before = len(gc.get_objects()) if debug_logging else 0
        collected = gc.collect()
        gc.freeze()
        elapsed = time.perf_counter() - started
        if debug_logging:
            logger.debug(
                "LoRA Manager: froze GC-tracked objects after %s "
                "(%d unreachable collected in %.2fs; %d objects tracked before collect)",
                reason,
                collected,
                elapsed,
                tracked_before,
            )
    except Exception:  # pragma: no cover - defensive guard
        logger.warning(
            "LoRA Manager: failed to freeze GC-tracked objects after %s",
            reason,
            exc_info=True,
        )


def _comfyui_queue_is_idle() -> bool:
    """Return True when no prompt is queued or running (or cannot be checked).

    Re-freezing while a prompt executes would move the prompt's transient
    object graph (model tensors included) into the permanent generation,
    where cyclic garbage can never be reclaimed — so scheduled re-freezes
    wait for an idle queue. Standalone mode has no prompt queue and is always
    idle. When the queue state cannot be determined (imports unavailable, or
    the queue does not report an integer count), assume idle: the startup
    freeze already runs under the same unguarded conditions.
    """
    if os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1":
        return True
    try:
        from server import PromptServer  # ComfyUI host module

        instance = getattr(PromptServer, "instance", None)
        queue = getattr(instance, "prompt_queue", None)
        if queue is None:
            return True
        remaining = queue.get_tasks_remaining()
        if not isinstance(remaining, int):
            return True
        return remaining == 0
    except Exception:
        return True


def schedule_refreeze(
    reason: str,
    delay: float = _REFREEZE_DELAY_SECONDS,
    _retries_left: int = _REFREEZE_MAX_RETRIES,
) -> None:
    """Schedule a debounced, idle-guarded re-freeze for after a cache change.

    Cache rebuilds and incremental writes (downloads, reconciles, metadata
    syncs) replace or extend the frozen cache with freshly allocated objects,
    which are GC-tracked again, so ComfyUI's post-prompt gc.collect() gets
    expensive once more. Re-freezing after a short settle delay moves the new
    objects into the permanent generation. Debounced: only the last schedule
    wins. When the timer fires while ComfyUI still has prompts queued or
    running, it reschedules instead of freezing mid-prompt (bounded by
    ``_REFREEZE_MAX_RETRIES``). No-op when no event loop is running.
    """
    global _pending_refreeze
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _pending_refreeze is not None:
        _pending_refreeze.cancel()

    def _fire() -> None:
        global _pending_refreeze
        _pending_refreeze = None
        if _comfyui_queue_is_idle():
            freeze_long_lived_objects(reason)
        elif _retries_left > 0:
            schedule_refreeze(reason, delay, _retries_left - 1)
        else:
            logger.debug(
                "LoRA Manager: skipped GC re-freeze after %s; prompt queue stayed busy",
                reason,
            )

    _pending_refreeze = loop.call_later(delay, _fire)


def schedule_refreeze_after_rebuild(
    reason: str, delay: float = _REFREEZE_DELAY_SECONDS
) -> None:
    """Schedule a debounced re-freeze for after a cache rebuild settles.

    Thin wrapper kept for the original rebuild call sites; equivalent to
    :func:`schedule_refreeze`.
    """
    schedule_refreeze(reason, delay)
