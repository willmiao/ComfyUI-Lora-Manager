"""Middleware helpers for adjusting Content Security Policy headers."""

from typing import Awaitable, Callable, Dict, List

from aiohttp import web

REMOTE_MEDIA_SOURCES = (
    "https://image.civitai.com",
    "https://img.genur.art",
)


@web.middleware
async def relax_csp_for_remote_media(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
) -> web.StreamResponse:
    """Allow LoRA Manager media previews to load from trusted remote domains.

    When ComfyUI is started with ``--disable-api-nodes`` it injects a restrictive
    ``Content-Security-Policy`` header that blocks remote images and videos. The
    LoRA Manager UI legitimately needs to fetch previews from Civitai and Genur,
    so this middleware augments the existing CSP to whitelist those hosts while
    preserving all other directives.
    """

    response: web.StreamResponse = await handler(request)
    header_value = response.headers.get("Content-Security-Policy")

    if not header_value:
        return response

    directive_order: List[str] = []
    directives: Dict[str, List[str]] = {}

    for raw_directive in header_value.split(";"):
        directive = raw_directive.strip()
        if not directive:
            continue

        parts = directive.split()
        name, values = parts[0], parts[1:]
        if name not in directive_order:
            directive_order.append(name)
        directives[name] = values

    def merge_sources(name: str, sources: List[str], defaults: List[str] | None = None) -> None:
        existing = directives.get(name, list(defaults or []))

        for source in sources:
            if source not in existing:
                existing.append(source)

        directives[name] = existing
        if name not in directive_order:
            directive_order.append(name)

    merge_sources("img-src", list(REMOTE_MEDIA_SOURCES))
    merge_sources("media-src", ["'self'", *REMOTE_MEDIA_SOURCES], defaults=["'self'"])

    updated_header = "; ".join(
        f"{name} {' '.join(directives[name])}".rstrip() for name in directive_order
    )

    response.headers["Content-Security-Policy"] = f"{updated_header};"
    return response
