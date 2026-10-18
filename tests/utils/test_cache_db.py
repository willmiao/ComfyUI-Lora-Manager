"""Tests for the shared cache SQLite connection settings (:mod:`py.utils.cache_db`).

Two LoRA Manager processes can share one settings directory, so cache
connections must tolerate a competing writer instead of failing immediately
with "database is locked".
"""

from __future__ import annotations

import sqlite3
import threading
import time

from py.utils.cache_db import CONCURRENT_TIMEOUT_SECONDS, connect_cache_db


def test_busy_timeout_pragma_is_applied(tmp_path):
    """The connection must retry inside SQLite, not just at connect() time."""
    conn = connect_cache_db(str(tmp_path / "cache.sqlite"))
    try:
        value = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()
    assert value == int(CONCURRENT_TIMEOUT_SECONDS * 1000)


def test_waiting_writer_succeeds_after_competing_writer_commits(tmp_path):
    """A blocked writer waits for the lock instead of raising."""
    db_path = str(tmp_path / "cache.sqlite")

    holder = connect_cache_db(db_path)
    holder.execute("CREATE TABLE t (v INTEGER)")
    holder.commit()
    holder.execute("BEGIN IMMEDIATE")

    def release_after_delay() -> None:
        time.sleep(0.5)
        holder.commit()

    releaser = threading.Thread(target=release_after_delay)
    releaser.start()
    try:
        waiter = connect_cache_db(db_path)
        try:
            # Under the old 5s default this still worked, but an immediate
            # failure is what low-timeout connections produced; assert the
            # write lands rather than propagating "database is locked".
            waiter.execute("INSERT INTO t VALUES (1)")
            waiter.commit()
        finally:
            waiter.close()
    finally:
        releaser.join()
        holder.close()

    check = connect_cache_db(db_path)
    try:
        assert check.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        check.close()


def test_readwrite_connection_uses_row_factory(tmp_path):
    conn = connect_cache_db(str(tmp_path / "cache.sqlite"), row_factory=sqlite3.Row)
    try:
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (7)")
        conn.commit()
        row = conn.execute("SELECT v FROM t").fetchone()
        assert row["v"] == 7
    finally:
        conn.close()


def test_readonly_connection_reads_without_writing(tmp_path):
    db_path = str(tmp_path / "cache.sqlite")
    writer = connect_cache_db(db_path)
    writer.execute("CREATE TABLE t (v INTEGER)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()
    writer.close()

    conn = connect_cache_db(db_path, readonly=True)
    try:
        assert conn.execute("SELECT v FROM t").fetchone()[0] == 1
    finally:
        conn.close()


def test_readonly_connection_rejects_writes(tmp_path):
    db_path = str(tmp_path / "cache.sqlite")
    writer = connect_cache_db(db_path)
    writer.execute("CREATE TABLE t (v INTEGER)")
    writer.commit()
    writer.close()

    conn = connect_cache_db(db_path, readonly=True)
    try:
        try:
            conn.execute("INSERT INTO t VALUES (1)")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        else:  # pragma: no cover - would mean mode=ro was not applied
            raise AssertionError("read-only connection accepted a write")
    finally:
        conn.close()
