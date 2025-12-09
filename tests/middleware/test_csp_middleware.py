import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from py.middleware.csp_middleware import REMOTE_MEDIA_SOURCES, relax_csp_for_remote_media

DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-src 'self'; "
    "object-src 'self';"
)


def _parse_directives(header: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for raw_directive in header.split(";"):
        directive = raw_directive.strip()
        if not directive:
            continue
        name, *values = directive.split()
        directives[name] = values
    return directives


async def _invoke_middleware(
    path: str, response: web.Response, csp_header: str | None = DEFAULT_CSP
) -> web.Response:
    async def handler(_request: web.Request) -> web.Response:
        if csp_header is not None:
            response.headers["Content-Security-Policy"] = csp_header
        return response

    request = make_mocked_request("GET", path)
    return await relax_csp_for_remote_media(request, handler)


@pytest.mark.asyncio
async def test_relax_csp_appends_remote_sources_and_preserves_existing_directives() -> None:
    response = await _invoke_middleware("/some-path", web.Response())
    header_value = response.headers.get("Content-Security-Policy")
    assert header_value is not None

    directives = _parse_directives(header_value)

    # Existing directives remain intact
    assert directives["script-src"] == ["'self'", "'unsafe-inline'", "'unsafe-eval'", "blob:"]
    assert directives["img-src"][:3] == ["'self'", "data:", "blob:"]

    # Remote media hosts are added once to the relevant directives
    for source in REMOTE_MEDIA_SOURCES:
        assert source in directives["img-src"]

    assert "media-src" in directives
    assert directives["media-src"][0] == "'self'"
    for source in REMOTE_MEDIA_SOURCES:
        assert source in directives["media-src"]


@pytest.mark.asyncio
async def test_relax_csp_no_header_left_untouched() -> None:
    response = await _invoke_middleware("/no-csp", web.Response(), csp_header=None)

    assert "Content-Security-Policy" not in response.headers
    assert response.headers.get("X-Test") is None
