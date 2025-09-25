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

    version, changelog = await update_routes.UpdateRoutes._get_remote_version()

    assert version == "v0.0.0"
    assert changelog == []
    assert "Failed to fetch GitHub release" in caplog.text
    assert "Cannot connect to host" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.asyncio
async def test_get_remote_version_network_error_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(update_routes, "get_downloader", lambda: _stub_downloader(RaisingDownloader()))

    version, changelog = await update_routes.UpdateRoutes._get_remote_version()

    assert version == "v0.0.0"
    assert changelog == []
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
