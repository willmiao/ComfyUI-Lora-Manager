"""Helpers for generating URLs that survive reverse-proxy subpath mounts."""

from __future__ import annotations


def relative_root_prefix(request_path: str) -> str:
    """Return the relative prefix ("", "../", ...) that takes a manager page
    back to the mount root.

    Templates reference assets and pages with relative URLs (e.g.
    ``{{ rel_prefix }}loras_static/...``) so the browser keeps whatever
    subpath a reverse proxy (llama-swap, SwarmUI, ...) mounted ComfyUI under.
    The backend only ever sees the stripped path, so the depth of the page
    route is all that matters: "/loras" -> "", "/loras/recipes" -> "../".
    """

    segments = [segment for segment in request_path.split("/") if segment]
    return "../" * max(len(segments) - 1, 0)
