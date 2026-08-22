import asyncio
from datetime import datetime
from pathlib import Path
from typing import Sequence

import pytest

from py.services.downloader import Downloader


class FakeStream:
    def __init__(self, chunks: Sequence[bytes | tuple[bytes, float]]):
        self._chunks = list(chunks)

    async def read(self, _chunk_size: int) -> bytes:
        if not self._chunks:
            await asyncio.sleep(0)
            return b""

        item = self._chunks.pop(0)
        delay = 0.0
        payload = item

        if isinstance(item, tuple):
            payload = item[0]
            delay = item[1]

        assert isinstance(payload, bytes)
        await asyncio.sleep(delay)
        return payload


class FakeResponse:
    def __init__(
        self,
        status,
        headers,
        chunks,
        *,
        url="https://example.com/file",
        history=None,
    ):
        self.status = status
        self.headers = headers
        self.content = FakeStream(chunks)
        self.url = url
        self.history = history or []
        self.released = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def release(self):
        self.released = True


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self._get_calls = 0
        self.requests = []

    def get(self, url, headers=None, allow_redirects=True, proxy=None):  # noqa: D401 - signature mirrors aiohttp
        self.requests.append(
            {
                "url": url,
                "headers": headers or {},
                "allow_redirects": allow_redirects,
                "proxy": proxy,
            }
        )
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
    downloader._session = fake_session  # pyright: ignore[reportAttributeAccessIssue]
    downloader._session_created_at = datetime.now()
    downloader._proxy_url = None
    async def _noop_create_session():
        downloader._session = fake_session  # pyright: ignore[reportAttributeAccessIssue]
        downloader._session_created_at = datetime.now()
        downloader._proxy_url = None

    downloader._create_session = _noop_create_session  # type: ignore[assignment]
    return downloader


def _session(downloader: Downloader) -> FakeSession:
    """Return the injected fake session, asserting the runtime invariant."""
    session = downloader._session
    assert isinstance(session, FakeSession)
    return session


@pytest.mark.asyncio
async def test_download_file_preserves_incomplete_part_when_size_mismatch(tmp_path):
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
    assert Path(str(target_path) + ".part").read_bytes() == b"abc"


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

    success, result_path = await downloader.download_file(
        "https://example.com/file", str(target_path)
    )

    assert success is True
    assert Path(result_path).read_bytes() == payload
    assert not Path(str(target_path) + ".part").exists()


@pytest.mark.asyncio
async def test_download_file_recovers_from_stall(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()

    payload = b"abcdef"

    responses = [
        lambda: FakeResponse(
            status=200,
            headers={"content-length": str(len(payload))},
            chunks=[(b"abc", 0.0), (b"def", 0.1)],
        ),
        lambda: FakeResponse(
            status=206,
            headers={"content-length": "3", "Content-Range": "bytes 3-5/6"},
            chunks=[(b"def", 0.0)],
        ),
    ]

    downloader = _build_downloader(responses, max_retries=1)
    downloader.stall_timeout = 0.05

    success, result_path = await downloader.download_file(
        "https://example.com/file", str(target_path)
    )

    assert success is True
    assert Path(result_path).read_bytes() == payload
    assert _session(downloader)._get_calls == 2
    assert not Path(str(target_path) + ".part").exists()


@pytest.mark.asyncio
async def test_download_file_resumes_after_incomplete_integrity_check(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()

    responses = [
        lambda: FakeResponse(
            status=200,
            headers={"content-length": "6"},
            chunks=[b"abc"],
        ),
        lambda: FakeResponse(
            status=206,
            headers={"content-length": "3", "Content-Range": "bytes 3-5/6"},
            chunks=[b"def"],
        ),
    ]

    downloader = _build_downloader(responses, max_retries=1)

    success, result_path = await downloader.download_file("https://example.com/file", str(target_path))

    assert success is True
    assert Path(result_path).read_bytes() == b"abcdef"
    assert _session(downloader)._get_calls == 2
    assert _session(downloader).requests[1]["headers"]["Range"] == "bytes=3-"
    assert not Path(str(target_path) + ".part").exists()


@pytest.mark.asyncio
async def test_download_file_retries_redirected_url_when_range_not_honored(tmp_path):
    target_path = tmp_path / "model" / "file.bin"
    target_path.parent.mkdir()
    Path(str(target_path) + ".part").write_bytes(b"abc")

    redirected_url = "https://download.example.com/file.bin"
    first_response = FakeResponse(
        status=200,
        headers={"content-length": "6"},
        chunks=[],
        url=redirected_url,
        history=[object()],
    )

    responses = [
        lambda: first_response,
        lambda: FakeResponse(
            status=206,
            headers={"content-length": "3", "Content-Range": "bytes 3-5/6"},
            chunks=[b"def"],
            url=redirected_url,
        ),
    ]

    downloader = _build_downloader(responses, max_retries=0)

    success, result_path = await downloader.download_file("https://example.com/file", str(target_path))

    assert success is True
    assert Path(result_path).read_bytes() == b"abcdef"
    assert first_response.released is True
    assert _session(downloader).requests[0]["headers"]["Range"] == "bytes=3-"
    assert _session(downloader).requests[1]["url"] == redirected_url
    assert _session(downloader).requests[1]["headers"]["Range"] == "bytes=3-"


@pytest.mark.asyncio
async def test_disable_netrc_auth_ignores_netrc_file(tmp_path, monkeypatch):
    """netrc entries must not be auto-applied as BasicAuth.

    Regression test for "Cannot combine AUTHORIZATION header with AUTH
    argument or credentials encoded in URL": with trust_env=True aiohttp
    loads credentials from netrc files, which conflict with the explicit
    Authorization: Bearer header used for CivitAI requests.
    """
    import aiohttp

    from py.services.downloader import _disable_netrc_auth

    netrc_file = tmp_path / ".netrc"
    netrc_file.write_text("machine civitai.red\nlogin user\npassword pass\n")
    monkeypatch.setenv("NETRC", str(netrc_file))

    async with aiohttp.ClientSession(trust_env=True) as session:
        # Premise: a plain session would pick up the netrc credentials.
        assert session._get_netrc_auth("civitai.red") is not None

        _disable_netrc_auth(session)
        assert session._get_netrc_auth("civitai.red") is None
