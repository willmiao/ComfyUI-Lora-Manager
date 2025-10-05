import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from py.middleware.cache_middleware import cache_control


async def invoke_middleware(path: str, response: web.Response) -> web.Response:
    async def handler(_request: web.Request) -> web.Response:
        return response

    request = make_mocked_request("GET", path)
    return await cache_control(request, handler)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/static/app.js",
        "/assets/styles/site.css",
        "/data/index.json",
    ],
)
async def test_static_files_force_no_cache(path: str) -> None:
    response = await invoke_middleware(path, web.Response())

    assert response.headers["Cache-Control"] == "no-cache"


@pytest.mark.asyncio
async def test_non_media_paths_leave_headers_untouched() -> None:
    base_headers = {"X-Source": "handler"}
    response = await invoke_middleware(
        "/api/data", web.Response(headers=base_headers)
    )

    assert "Cache-Control" not in response.headers
    assert response.headers["X-Source"] == "handler"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, expected",
    [
        (200, "public, max-age=86400"),
        (404, "public, max-age=3600"),
        (302, "no-cache"),
    ],
)
async def test_media_responses_set_expected_cache_control(status: int, expected: str) -> None:
    response = await invoke_middleware(
        "/images/sample.png", web.Response(status=status)
    )

    assert response.headers.get("Cache-Control") == expected


@pytest.mark.asyncio
async def test_existing_cache_control_header_preserved() -> None:
    response = await invoke_middleware(
        "/images/custom.jpg",
        web.Response(headers={"Cache-Control": "public, max-age=999"}),
    )

    assert response.headers["Cache-Control"] == "public, max-age=999"
