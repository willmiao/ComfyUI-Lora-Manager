import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from py.services.downloader import Downloader


class FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def iter_chunked(self, _chunk_size):
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


class FakeResponse:
    def __init__(self, status, headers, chunks):
        self.status = status
        self.headers = headers
        self.content = FakeStream(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self._get_calls = 0

    def get(self, url, headers=None, allow_redirects=True, proxy=None):  # noqa: D401 - signature mirrors aiohttp
        del url, headers, allow_redirects, proxy
        response_factory = self._responses[self._get_calls]
        self._get_calls += 1
        return response_factory()

    async def close(self):
        return None


def _build_downloader(responses, *, max_retries=0):
    downloader = Downloader()
    downloader.max_retries = max_retries
    downloader.base_delay = 0
    fake_session = FakeSession(responses)
    downloader._session = fake_session
    downloader._session_created_at = datetime.now()
    downloader._proxy_url = None
    return downloader


@pytest.mark.asyncio
async def test_download_file_fails_when_size_mismatch(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()

    responses = [
        lambda: FakeResponse(
            status=200,
            headers={"content-length": "10"},
            chunks=[b"abc"],
        )
    ]

    downloader = _build_downloader(responses)

    success, message = await downloader.download_file("https://example.com/file", str(target_path))

    assert success is False
    assert "mismatch" in message.lower()
    assert not target_path.exists()
    assert not Path(str(target_path) + ".part").exists()


@pytest.mark.asyncio
async def test_download_file_fails_when_zero_bytes(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()

    responses = [
        lambda: FakeResponse(
            status=200,
            headers={"content-length": "0"},
            chunks=[],
        )
    ]

    downloader = _build_downloader(responses)

    success, message = await downloader.download_file("https://example.com/file", str(target_path))

    assert success is False
    assert "empty" in message.lower()
    assert not target_path.exists()
    assert not Path(str(target_path) + ".part").exists()


@pytest.mark.asyncio
async def test_download_file_succeeds_when_sizes_match(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()

    payload = b"abcdef"
    responses = [
        lambda: FakeResponse(
            status=200,
            headers={"content-length": str(len(payload))},
            chunks=[payload],
        )
    ]

    downloader = _build_downloader(responses)

    success, result_path = await downloader.download_file("https://example.com/file", str(target_path))

    assert success is True
    assert Path(result_path).read_bytes() == payload
    assert not Path(str(target_path) + ".part").exists()
