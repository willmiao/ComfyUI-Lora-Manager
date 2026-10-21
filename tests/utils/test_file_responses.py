import asyncio
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py.utils.file_responses import ChunkedFileResponse, platform_file_response_class


def test_platform_file_response_class_selects_by_platform(monkeypatch):
    monkeypatch.setattr("py.utils.file_responses.sys.platform", "win32")
    assert platform_file_response_class() is ChunkedFileResponse

    monkeypatch.setattr("py.utils.file_responses.sys.platform", "linux")
    assert platform_file_response_class() is web.FileResponse


async def test_chunked_file_response_serves_full_and_range_without_sendfile(tmp_path):
    payload = bytes(range(256)) * 8192  # 2 MB, several 1 MB chunks
    target = tmp_path / "clip.mp4"
    target.write_bytes(payload)

    app = web.Application()

    async def serve_file(request):
        return ChunkedFileResponse(path=target)

    app.router.add_get("/file", serve_file)

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        with patch.object(
            asyncio.BaseEventLoop, "sendfile", side_effect=AssertionError("native sendfile used")
        ):
            full = await client.get("/file")
            part = await client.get("/file", headers={"Range": "bytes=100-199"})

            assert full.status == 200
            assert await full.read() == payload
            assert part.status == 206
            assert await part.read() == payload[100:200]
    finally:
        await client.close()
