import logging
import os
import shutil
import subprocess
from aiohttp import ClientError
from aiohttp import web
import pytest

from py.routes import update_routes


def _fake_request(body=None, query_params=None):
    from multidict import MultiDict

    q = MultiDict(query_params or {})

    req = type("Req", (), {
        "has_body": body is not None,
        "match_info": {},
        "rel_url": type("U", (), {"query": q})(),
        "query": q,
        "app": {},
    })()

    async def _json():
        return body or {}

    req.json = _json  # pyright: ignore[reportAttributeAccessIssue]
    return req


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

    version, changelog, behind_by, commit_date = await update_routes.UpdateRoutes._get_nightly_version()

    assert version == "main"
    assert changelog == []
    assert behind_by == 0
    assert commit_date == ""
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
        def fetch(self, *args, **kwargs):
            calls.append(("fetch", kwargs))

        def pull(self, *args, **kwargs):
            calls.append(("pull", args))

    class FakeRemotes:
        origin = FakeRemote()

    class FakeCommit:
        hexsha = "abcdef123456"

    class FakeHeads:
        def __getitem__(self, name):
            class Head:
                def checkout(self):
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

    # The fetch must be bounded, same as the bootstrap path.
    fetch_calls = [c for c in calls if c[0] == "fetch"]
    assert fetch_calls[0][1] == {"kill_after_timeout": update_routes._GIT_NETWORK_TIMEOUT}


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
        def fetch(self, *args, **kwargs):
            calls.append(("fetch", kwargs))

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


def _run_git(*args, cwd):
    """Run git in *cwd* with a throwaway identity (CI runners configure none)."""
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_init_git_repo_creates_valid_repo(tmp_path, monkeypatch):
    if not shutil.which("git"):
        pytest.skip("git executable not found")

    # A local repository stands in for the GitHub remote. Everything exercised
    # here is plain git, so a network round trip buys nothing: the old version
    # fetched the real repository (~140 MiB of history), took seconds even on a
    # good connection, and could hang the whole suite on a stalled one.
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _run_git("init", "-b", "main", cwd=upstream)
    (upstream / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (upstream / "README.md").write_text("upstream\n")
    _run_git("add", ".", cwd=upstream)
    _run_git("commit", "-m", "init", cwd=upstream)
    head_sha = _run_git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / ".tracking").write_text("pyproject.toml")
    (plugin_root / "settings.json").write_text('{"some": "value"}')
    preserved_dirs = [
        name for name in update_routes._PRESERVE_DIRS if name != "settings.json"
    ]
    for name in preserved_dirs:
        (plugin_root / name).mkdir()
        (plugin_root / name / "user-file.txt").write_text("keep me")

    monkeypatch.setattr(update_routes, "_GIT_REMOTE_URL", str(upstream))

    success, version = update_routes.UpdateRoutes._init_git_repo(str(plugin_root))

    assert success is True
    assert version == f"main-{head_sha[:7]}"
    assert (plugin_root / ".git").is_dir()
    assert not (plugin_root / ".tracking").exists()
    # Tracked content is checked out from the remote ...
    assert (plugin_root / "pyproject.toml").exists()
    assert (plugin_root / "README.md").exists()
    # ... while user data survives ``git clean -fd``. This is the behaviour that
    # needs a real git binary; asserting the ``-e`` arguments on a fake repo
    # (as the other tests do) cannot prove the files really stay.
    assert (plugin_root / "settings.json").read_text() == '{"some": "value"}'
    for name in preserved_dirs:
        assert (plugin_root / name / "user-file.txt").exists(), f"{name} was cleaned"


def test_init_git_repo_fetch_is_bounded(tmp_path, monkeypatch):
    """The bootstrap fetch must carry a timeout: git has none by default, so a
    stalled connection otherwise hangs the update endpoint forever."""
    fetch_kwargs = {}
    clean_args = ()

    class FakeRemote:
        refs = type("Refs", (), {"main": "refs/heads/main"})()

        def fetch(self, **kwargs):
            fetch_kwargs.update(kwargs)

    class FakeGit:
        def checkout(self, *args, **kwargs):
            pass

        def reset(self, *args, **kwargs):
            pass

        def clean(self, *args, **kwargs):
            nonlocal clean_args
            clean_args = args

    class FakeHead:
        class commit:
            hexsha = "0" * 40

    class FakeRepo:
        git = FakeGit()
        head = FakeHead()

        def create_remote(self, name, url):
            return FakeRemote()

        def create_head(self, *args, **kwargs):
            pass

    class FakeGitModule:
        class Repo:
            @staticmethod
            def init(path):
                return FakeRepo()

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

    success, version = update_routes.UpdateRoutes._init_git_repo(str(tmp_path))

    assert success is True
    assert version == "main-0000000"
    assert fetch_kwargs == {"kill_after_timeout": update_routes._GIT_NETWORK_TIMEOUT}
    for name in update_routes._PRESERVE_DIRS:
        assert name in clean_args, f"{name} missing from git clean excludes (init)"


def test_init_git_repo_reports_failure_instead_of_raising(tmp_path, monkeypatch):
    """A failed fetch surfaces as ``(False, "")``; callers branch on it.

    This is also why the old network-backed test *failed* instead of skipping
    on a bad connection: ``_init_git_repo`` catches its own exceptions, so a
    ``try/except: pytest.skip`` around the call never fires.
    """
    if not shutil.which("git"):
        pytest.skip("git executable not found")

    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    monkeypatch.setattr(
        update_routes, "_GIT_REMOTE_URL", str(tmp_path / "missing-repository")
    )

    assert update_routes.UpdateRoutes._init_git_repo(str(plugin_root)) == (False, "")


@pytest.mark.asyncio
async def test_switch_channel_invalid_channel_returns_error():
    req = _fake_request({"channel": "bad_channel"})
    resp = await update_routes.UpdateRoutes.switch_channel(req)

    data = _raw_body(resp)
    assert not data["success"]
    assert "Invalid channel" in data["error"]


@pytest.mark.asyncio
async def test_switch_channel_to_nightly_without_git_inits_repo(monkeypatch, tmp_path):
    routes_file = tmp_path / "py" / "routes" / "update_routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text("")
    monkeypatch.setattr(update_routes, "__file__", str(routes_file))
    monkeypatch.setattr(update_routes, "ensure_settings_file", lambda logger: str(tmp_path / "settings.json"))
    monkeypatch.setattr(
        update_routes.UpdateRoutes,
        "_init_git_repo",
        staticmethod(lambda plugin_root: (True, "main-fedcba9")),
    )

    req = _fake_request({"channel": "nightly"})
    resp = await update_routes.UpdateRoutes.switch_channel(req)
    data = _raw_body(resp)

    assert data["success"] is True
    assert data["channel"] == "nightly"
    assert data["new_version"] == "main-fedcba9"


@pytest.mark.asyncio
async def test_switch_channel_to_nightly_with_git_calls_git_update(monkeypatch, tmp_path):
    routes_file = tmp_path / "py" / "routes" / "update_routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text("")
    monkeypatch.setattr(update_routes, "__file__", str(routes_file))
    monkeypatch.setattr(update_routes, "ensure_settings_file", lambda logger: str(tmp_path / "settings.json"))

    (tmp_path / ".git").mkdir()

    async def _fake_git_update(*args, **kwargs):
        return True, "main-1111111"

    monkeypatch.setattr(
        update_routes.UpdateRoutes, "_perform_git_update", _fake_git_update
    )

    req = _fake_request({"channel": "nightly"})
    resp = await update_routes.UpdateRoutes.switch_channel(req)
    data = _raw_body(resp)

    assert data["success"] is True
    assert data["channel"] == "nightly"
    assert data["new_version"] == "main-1111111"


@pytest.mark.asyncio
async def test_switch_channel_to_release_with_git_calls_git_update(monkeypatch, tmp_path):
    routes_file = tmp_path / "py" / "routes" / "update_routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text("")
    monkeypatch.setattr(update_routes, "__file__", str(routes_file))
    monkeypatch.setattr(update_routes, "ensure_settings_file", lambda logger: str(tmp_path / "settings.json"))

    (tmp_path / ".git").mkdir()

    async def _fake_git_update(*args, **kwargs):
        return True, "v9.9.9"

    monkeypatch.setattr(
        update_routes.UpdateRoutes, "_perform_git_update", _fake_git_update
    )

    req = _fake_request({"channel": "release"})
    resp = await update_routes.UpdateRoutes.switch_channel(req)
    data = _raw_body(resp)

    assert data["success"] is True
    assert data["channel"] == "release"
    assert data["new_version"] == "v9.9.9"


@pytest.mark.asyncio
async def test_switch_channel_to_release_without_git_still_downloads_zip(monkeypatch, tmp_path):
    routes_file = tmp_path / "py" / "routes" / "update_routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text("")
    monkeypatch.setattr(update_routes, "__file__", str(routes_file))
    monkeypatch.setattr(update_routes, "ensure_settings_file", lambda logger: str(tmp_path / "settings.json"))

    async def _fake_zip(*args, **kwargs):
        return True, "v2.0.0"

    monkeypatch.setattr(
        update_routes.UpdateRoutes, "_download_and_replace_zip", _fake_zip
    )

    req = _fake_request({"channel": "release"})
    resp = await update_routes.UpdateRoutes.switch_channel(req)
    data = _raw_body(resp)

    assert data["success"] is True
    assert data["channel"] == "release"
    assert data["new_version"] == "v2.0.0"


class _NightlyDownloader:
    """Returns a fake main-branch commit AND a compare response."""

    commit_sha = "7777777"
    commit_msg = "test: add nightly feature"
    commit_date = "2026-07-27T12:00:00Z"
    behind_by = 5

    async def make_request(self, method, url, **kwargs):
        if "/compare/" in url:
            return True, {"behind_by": self.behind_by}
        return True, {
            "sha": self.commit_sha,
            "commit": {
                "message": self.commit_msg,
                "committer": {"date": self.commit_date},
            },
        }


@pytest.mark.asyncio
async def test_get_nightly_version_parses_behind_by(monkeypatch):
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(_NightlyDownloader()))

    version, changelog, behind_by, commit_date = await update_routes.UpdateRoutes._get_nightly_version(
        local_hash="abc1234"
    )

    assert version == "main-7777777"
    assert behind_by == 5
    assert commit_date == "2026-07-27"
    assert len(changelog) == 1
    assert changelog[0] == "test: add nightly feature"


class _AheadCompareDownloader:
    """Fake compare API response with status='ahead' (main is ahead of local)."""

    commit_sha = "9999999"
    commit_msg = "latest commit"
    commit_date = "2026-07-28T00:00:00Z"
    ahead_by = 3

    async def make_request(self, method, url, **kwargs):
        if "/compare/" in url:
            return True, {"status": "ahead", "ahead_by": self.ahead_by, "behind_by": 0}
        return True, {
            "sha": self.commit_sha,
            "commit": {
                "message": self.commit_msg,
                "committer": {"date": self.commit_date},
            },
        }


@pytest.mark.asyncio
async def test_get_nightly_version_reads_ahead_by_when_ahead(monkeypatch):
    """compare/{local}...main returns status='ahead' → read ahead_by."""
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(_AheadCompareDownloader()))

    version, changelog, behind_by, commit_date = await update_routes.UpdateRoutes._get_nightly_version(
        local_hash="oldhash"
    )

    assert version == "main-9999999"
    assert behind_by == 3
    assert commit_date == "2026-07-28"


class _DivergedCompareDownloader:
    """Fake compare API response with status='diverged' (both have unique commits)."""

    commit_sha = "aaaaaaa"
    commit_msg = "diverged test"
    commit_date = "2026-07-29T00:00:00Z"

    async def make_request(self, method, url, **kwargs):
        if "/compare/" in url:
            return True, {"status": "diverged", "ahead_by": 5, "behind_by": 2}
        return True, {
            "sha": self.commit_sha,
            "commit": {
                "message": self.commit_msg,
                "committer": {"date": self.commit_date},
            },
        }


@pytest.mark.asyncio
async def test_get_nightly_version_reads_ahead_by_when_diverged(monkeypatch):
    """compare/{local}...main returns status='diverged' → read ahead_by (remote ahead)."""
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(_DivergedCompareDownloader()))

    version, changelog, behind_by, commit_date = await update_routes.UpdateRoutes._get_nightly_version(
        local_hash="divhash"
    )

    assert behind_by == 5


class _CheckUpdatesDownloader:
    """Fake downloader returning both a release list and a nightly commit + compare."""

    commit_sha = "8888888"
    commit_date = "2026-07-28T00:00:00Z"

    async def make_request(self, method, url, **kwargs):
        if "/releases" in url:
            return True, [
                {
                    "tag_name": "v3.0.0",
                    "body": "- Feature A\n- Feature B",
                    "published_at": "2026-07-20T00:00:00Z",
                }
            ]
        if "/compare/" in url:
            return True, {"behind_by": 3}
        return True, {
            "sha": self.commit_sha + "0" * 33,
            "commit": {
                "message": "latest commit",
                "committer": {"date": self.commit_date},
            },
        }


@pytest.mark.asyncio
async def test_check_updates_nightly_response_includes_behind_and_date(monkeypatch, tmp_path):
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(_CheckUpdatesDownloader()))

    monkeypatch.setattr(
        update_routes.UpdateRoutes,
        "_get_local_version",
        staticmethod(lambda: "v1.0.0"),
    )
    monkeypatch.setattr(
        update_routes.UpdateRoutes,
        "_get_git_info",
        staticmethod(lambda: {
            "commit_hash": "abc1234",
            "short_hash": "abc1234",
            "branch": "main",
            "commit_date": "2026-01-01",
        }),
    )

    routes_file = tmp_path / "py" / "routes" / "update_routes.py"
    routes_file.parent.mkdir(parents=True)
    routes_file.write_text("")
    monkeypatch.setattr(update_routes, "__file__", str(routes_file))
    (tmp_path / ".git").mkdir()

    req = _fake_request(query_params={"nightly": "true"})
    resp = await update_routes.UpdateRoutes.check_updates(req)
    data = _raw_body(resp)

    assert data["success"] is True
    assert data["nightly"] is True
    assert data["has_git"] is True
    assert data["behind_by"] == 3
    assert data["commit_date"] == "2026-07-28"
    assert data["latest_version"] == "main-8888888"
    assert isinstance(data["releases"], list)
    assert len(data["releases"]) == 1
    assert data["releases"][0]["version"] == "v3.0.0"


def _raw_body(response):
    import json
    return json.loads(response._body.decode())
