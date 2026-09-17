"""Tests for the cross-process advisory lock (:mod:`py.utils.file_lock`)."""

from __future__ import annotations

import os
import time

import pytest

from py.utils.file_lock import (
    CrossProcessLock,
    FileLockUnavailable,
    exclusive_lock,
    lock_path_for,
)


def test_lock_path_is_a_sibling_of_the_resource(tmp_path):
    db_path = str(tmp_path / "recipe" / "default.sqlite")
    lock_path = lock_path_for(db_path)

    assert os.path.dirname(lock_path) == os.path.dirname(db_path)
    assert os.path.basename(lock_path) == ".default.sqlite.lock"


def test_acquire_and_release_round_trip(tmp_path):
    lock = exclusive_lock(str(tmp_path / "cache.sqlite"))

    assert lock.acquire() is True
    lock.release()
    # Releasing twice must be safe.
    lock.release()
    # ...and the lock is reusable afterwards.
    assert lock.acquire() is True
    lock.release()


def test_second_lock_holder_waits_until_release(tmp_path):
    """A held lock blocks a competing holder for the same resource."""
    db_path = str(tmp_path / "cache.sqlite")
    first = exclusive_lock(db_path)
    second = CrossProcessLock(lock_path_for(db_path), timeout=0.2)

    assert first.acquire() is True
    try:
        started = time.monotonic()
        assert second.acquire() is False
        # It must have waited for the timeout rather than failing instantly.
        assert time.monotonic() - started >= 0.15
    finally:
        first.release()

    # Once released, the contender gets the lock.
    assert second.acquire() is True
    second.release()


def test_context_manager_releases_on_exception(tmp_path):
    lock = exclusive_lock(str(tmp_path / "cache.sqlite"))
    contender = CrossProcessLock(lock.path, timeout=0.2)

    with pytest.raises(RuntimeError):
        with lock:
            raise RuntimeError("boom")

    assert contender.acquire() is True
    contender.release()


def test_lock_file_is_not_deleted(tmp_path):
    """Deleting the lock file would let a second process lock a fresh inode."""
    lock = exclusive_lock(str(tmp_path / "cache.sqlite"))
    assert lock.acquire() is True
    lock.release()

    assert os.path.exists(lock.path)


def test_unsupported_platform_degrades_gracefully(tmp_path, monkeypatch):
    """Without a platform primitive the lock reports failure instead of raising."""
    import py.utils.file_lock as file_lock_module

    monkeypatch.setattr(file_lock_module, "fcntl", None)
    monkeypatch.setattr(file_lock_module, "msvcrt", None)

    lock = exclusive_lock(str(tmp_path / "cache.sqlite"))
    assert lock.acquire() is False
    # Callers use it as a context manager and continue without the lock.
    with exclusive_lock(str(tmp_path / "cache.sqlite")):
        pass


def test_file_lock_unavailable_is_exported():
    assert issubclass(FileLockUnavailable, RuntimeError)


def test_save_cache_creates_lock_next_to_database(tmp_path):
    """The recipe cache write path actually takes the cross-process lock."""
    from py.services.persistent_recipe_cache import PersistentRecipeCache

    db_path = tmp_path / "recipe_cache.sqlite"
    cache = PersistentRecipeCache(db_path=str(db_path))
    assert cache.save_cache([{"id": "r1", "title": "One"}], {"r1": "/tmp/r1.json"})

    assert os.path.exists(lock_path_for(str(db_path)))


def test_save_cache_releases_lock_after_write(tmp_path):
    """A second writer must not be blocked once the first has finished."""
    from py.services.persistent_recipe_cache import PersistentRecipeCache

    db_path = tmp_path / "recipe_cache.sqlite"
    cache = PersistentRecipeCache(db_path=str(db_path))
    cache.save_cache([{"id": "r1", "title": "One"}], {"r1": "/tmp/r1.json"})

    contender = CrossProcessLock(lock_path_for(str(db_path)), timeout=0.2)
    assert contender.acquire() is True
    contender.release()
