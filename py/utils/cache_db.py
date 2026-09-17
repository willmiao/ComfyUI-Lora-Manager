"""Shared SQLite connection setup for LoRA Manager cache databases.

Cache databases live under the settings directory (``cache/model/<library>.sqlite``,
``cache/recipe/<library>.sqlite``, ``cache/fts/*.sqlite``). With portable mode or a
pinned ``LORA_MANAGER_SETTINGS_DIR`` off, that directory is shared by every ComfyUI
instance on the machine, so two processes can open the same cache file at once.

SQLite serializes writers, but the default ``timeout`` is 5 seconds: a second
instance that writes while the first is mid-transaction fails with "database is
locked". These settings make concurrent access wait instead of failing, and keep
the write path in WAL so readers are never blocked by a writer.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# How long a connection waits for a competing writer before raising.
CONCURRENT_TIMEOUT_SECONDS = 30.0

# PRAGMAs applied to every cache connection.
#
# ``busy_timeout`` mirrors the connection timeout so a busy database is retried
# inside SQLite rather than surfacing as an immediate error. ``synchronous=NORMAL``
# is the documented companion of WAL: still crash-safe, far fewer fsyncs.
_TUNING_PRAGMAS = (
    "PRAGMA busy_timeout = 30000",
    "PRAGMA synchronous = NORMAL",
)


def connect_cache_db(
    path: str,
    *,
    readonly: bool = False,
    uri: bool = False,
    detect_types: int = 0,
    row_factory: Any = None,
) -> sqlite3.Connection:
    """Open a cache database with multi-instance-friendly settings.

    Args:
        path: Database path, or a ``file:`` URI when *uri* is True.
        readonly: Open through a read-only URI. Callers still pass the
            plain path; the ``mode=ro`` suffix is added here. The
            write-oriented tuning pragmas are skipped in that case so a
            read-only connection never attempts to change the file.
        uri: Treat *path* as a SQLite URI.
        detect_types: Forwarded to :func:`sqlite3.connect`.
        row_factory: Optional ``row_factory`` for the connection.

    Returns:
        A configured :class:`sqlite3.Connection`.
    """
    if readonly:
        if not uri and not path.startswith("file:"):
            path = f"file:{path}?mode=ro"
            uri = True

    conn = sqlite3.connect(
        path,
        check_same_thread=False,
        uri=uri,
        detect_types=detect_types,
        timeout=CONCURRENT_TIMEOUT_SECONDS,
    )
    if row_factory is not None:
        conn.row_factory = row_factory

    try:
        for pragma in _TUNING_PRAGMAS:
            # A read-only connection may reject write PRAGMAs; they are not
            # needed there anyway.
            conn.execute(pragma)
    except sqlite3.Error:
        # Tuning is best-effort: a connection that cannot set pragmas still
        # works, just without the concurrency headroom.
        pass

    return conn
