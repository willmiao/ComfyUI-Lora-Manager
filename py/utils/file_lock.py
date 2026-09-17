"""Cross-process advisory locking for shared LoRA Manager state.

Two LoRA Manager processes (the ComfyUI plugin and a standalone server, or two
ComfyUI installs pointed at the same settings directory) can open the same cache
database. SQLite serializes individual statements, but it cannot make a
read-modify-write *sequence* atomic across processes: two full-table cache
replacements can interleave so that one process's snapshot overwrites the
other's.

This module provides a small advisory file lock for those sequences. It is
deliberately non-fatal: if locking is unavailable or the wait times out, callers
keep working with SQLite's own ``busy_timeout`` as the fallback.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# How long to wait for another process to release the lock before giving up.
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.05

# Windows byte-range locks; fcntl.flock on POSIX.
try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # pragma: no cover - Windows only
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class FileLockUnavailable(RuntimeError):
    """Raised when the lock could not be acquired within the timeout."""


def lock_path_for(db_path: str) -> str:
    """Return the sibling lock file path used for *db_path*."""
    absolute = os.path.abspath(db_path)
    directory = os.path.dirname(absolute)
    if not directory:
        raise ValueError(f"Cannot derive a lock directory from {db_path!r}")
    return os.path.join(directory, f".{os.path.basename(absolute)}.lock")


class CrossProcessLock:
    """A best-effort advisory lock backed by a lock file.

    The lock file is a sibling of the guarded resource and is never deleted:
    unlinking it would let a second process create a fresh inode and lock that
    instead, defeating mutual exclusion.
    """

    def __init__(self, path: str, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS):
        self.path = path
        self.timeout = timeout
        self._handle = None

    def acquire(self) -> bool:
        """Try to take the lock, waiting up to ``timeout`` seconds.

        Returns:
            True when the lock is held (including when another lock is already
            held by *this* process — the calls are not reentrant, so callers must
            not nest them). False when locking is unsupported or timed out; the
            caller should proceed and rely on the SQLite busy timeout instead.
        """
        if fcntl is None and msvcrt is None:  # pragma: no cover - exotic platform
            return False

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            handle = open(self.path, "a+b")
        except OSError as exc:
            logger.debug("Could not open lock file %s: %s", self.path, exc)
            return False

        deadline = time.monotonic() + max(0.0, self.timeout)
        while True:
            if self._try_lock(handle):
                self._handle = handle
                return True
            if time.monotonic() >= deadline:
                handle.close()
                return False
            time.sleep(_POLL_INTERVAL_SECONDS)

    def release(self) -> None:
        """Release the lock if held. Safe to call more than once."""
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            self._unlock(handle)
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to release lock %s: %s", self.path, exc)
        finally:
            try:
                handle.close()
            except OSError:  # pragma: no cover - defensive
                pass

    def __enter__(self) -> "CrossProcessLock":
        self.acquire()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.release()

    # -- platform primitives -------------------------------------------------

    def _try_lock(self, handle) -> bool:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                return False
        if msvcrt is not None:  # pragma: no cover - Windows
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        return False

    def _unlock(self, handle) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return
        if msvcrt is not None:  # pragma: no cover - Windows
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def exclusive_lock(db_path: str, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS):
    """Return a :class:`CrossProcessLock` for the database at *db_path*."""
    return CrossProcessLock(lock_path_for(db_path), timeout=timeout)
