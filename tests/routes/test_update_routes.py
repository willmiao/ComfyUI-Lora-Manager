import logging
from aiohttp import ClientError
import pytest

from py.routes import update_routes


class OfflineDownloader:
    async def make_request(self, *_, **__):
        return False, "Cannot connect to host"


class RaisingDownloader:
    async def make_request(self, *_, **__):
        raise ClientError("offline")


async def _stub_downloader(instance):
    return instance


@pytest.mark.asyncio
async def test_get_remote_version_offline_logs_without_traceback(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(OfflineDownloader()))

    version, changelog, releases = await update_routes.UpdateRoutes._get_remote_version()

    assert version == "v0.0.0"
    assert changelog == []
    assert releases == []
    assert "Failed to fetch GitHub releases" in caplog.text
    assert "Cannot connect to host" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.asyncio
async def test_get_remote_version_network_error_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(RaisingDownloader()))

    version, changelog, releases = await update_routes.UpdateRoutes._get_remote_version()

    assert version == "v0.0.0"
    assert changelog == []
    assert releases == []
    assert "Unable to reach GitHub for release info" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.asyncio
async def test_get_nightly_version_network_error_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(RaisingDownloader()))

    version, changelog = await update_routes.UpdateRoutes._get_nightly_version()

    assert version == "main"
    assert changelog == []
    assert "Unable to reach GitHub for nightly version" in caplog.text
    assert "Traceback" not in caplog.text


def test_clean_excludes_covers_user_data_dirs():
    """git clean must receive -e excludes for every user-managed dir."""
    excludes = update_routes._clean_excludes()
    assert "-e" in excludes  # at least one exclude flag present
    for name in update_routes._PRESERVE_DIRS:
        assert name in excludes
        assert f"{name}/**" in excludes


@pytest.mark.asyncio
async def test_perform_git_update_preserves_user_dirs(monkeypatch, tmp_path):
    """``git clean`` must be called with -e excludes for user data dirs.

    Regression test for portable-mode updates wiping wildcards/, stats/,
    backups/, etc. because ``git clean -fd`` removed untracked, non-ignored
    directories.
    """
    calls = []

    class FakeGit:
        def reset(self, *args, **kwargs):
            calls.append(("reset", args))

        def clean(self, *args, **kwargs):
            calls.append(("clean", args))

        def checkout(self, *args, **kwargs):
            calls.append(("checkout", args))

    class FakeRemote:
        def fetch(self):
            calls.append(("fetch", ()))

        def pull(self, *args, **kwargs):
            calls.append(("pull", args))

    class FakeRemotes:
        origin = FakeRemote()

    class FakeCommit:
        hexsha = "abcdef123456"

    class FakeHeads:
        def __getitem__(self, name):
            class Head:
                def checkout(self_inner):
                    calls.append(("head-checkout", (name,)))
            return Head()

    class FakeBranches:
        names = ["main"]

        def __iter__(self):
            class B:
                name = "main"
            return iter([B()])

    class FakeRepo:
        def __init__(self, path):
            calls.append(("repo", (path,)))

        git = FakeGit()
        remotes = FakeRemotes()
        head = type("H", (), {"commit": FakeCommit()})()
        branches = FakeBranches()
        heads = FakeHeads()

        def create_head(self, name, ref):
            calls.append(("create_head", (name, ref)))

    class FakeGitModule:
        class Repo:
            def __new__(cls, path):
                return FakeRepo(path)

        class exc:
            class GitError(Exception):
                pass

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "git":
            return FakeGitModule
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    success, version = await update_routes.UpdateRoutes._perform_git_update(
        str(tmp_path), nightly=True
    )

    assert success is True
    clean_calls = [c for c in calls if c[0] == "clean"]
    assert len(clean_calls) == 1
    clean_args = clean_calls[0][1]
    # Every preserved dir must be excluded via -e
    for name in update_routes._PRESERVE_DIRS:
        assert name in clean_args, f"{name} missing from git clean excludes"
        assert f"{name}/**" in clean_args, f"{name}/** missing from git clean excludes"
        # Ensure there's an -e before each name occurrence
        idx = clean_args.index(name)
        assert clean_args[idx - 1] == "-e"


@pytest.mark.asyncio
async def test_perform_git_update_stable_preserves_user_dirs(monkeypatch, tmp_path):
    """Stable (tag) update path must also pass -e excludes to git clean."""
    calls = []

    class FakeGit:
        def reset(self, *args, **kwargs):
            calls.append(("reset", args))

        def clean(self, *args, **kwargs):
            calls.append(("clean", args))

        def checkout(self, *args, **kwargs):
            calls.append(("checkout", args))

    class FakeRemote:
        def fetch(self):
            calls.append(("fetch", ()))

    class FakeRemotes:
        origin = FakeRemote()

    class FakeCommit:
        committed_datetime = "2026-01-01"

    class FakeTag:
        name = "v9.9.9"
        commit = FakeCommit()

    class FakeRepo:
        def __init__(self, path):
            calls.append(("repo", (path,)))

        git = FakeGit()
        remotes = FakeRemotes()
        tags = [FakeTag()]

    class FakeGitModule:
        class Repo:
            def __new__(cls, path):
                return FakeRepo(path)

        class exc:
            class GitError(Exception):
                pass

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "git":
            return FakeGitModule
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    success, version = await update_routes.UpdateRoutes._perform_git_update(
        str(tmp_path), nightly=False
    )

    assert success is True
    assert version == "v9.9.9"
    clean_calls = [c for c in calls if c[0] == "clean"]
    assert len(clean_calls) == 1
    clean_args = clean_calls[0][1]
    for name in update_routes._PRESERVE_DIRS:
        assert name in clean_args, f"{name} missing from git clean excludes (stable)"
