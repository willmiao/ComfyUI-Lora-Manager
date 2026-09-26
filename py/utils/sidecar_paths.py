"""Resolution of sidecar metadata and preview storage paths.

All code that needs the on-disk location of a model's ``.metadata.json``
sidecar or preview assets MUST go through these helpers instead of deriving
paths inline (``splitext(model_path)[0] + ".metadata.json"`` and friends).

Two storage modes are supported, selected by the ``sidecar_storage_mode``
setting:

- ``alongside`` (default): sidecars and previews live next to the model
  file, the historical layout other tools may rely on.
- ``centralized``: sidecars and previews live under a configurable root
  (``sidecar_storage_path`` setting, default ``<settings_dir>/sidecars``),
  mirroring the library-relative directory structure:
  ``<root>/<library>/<root_basename-roothash>/<rel_dir>/<name>.metadata.json``.

All helpers are pure path computations: no directory scans and no file I/O
on the hot path. Settings lookups go through ``SettingsManager.get`` (a dict
read); config roots come from the already-initialized ``config`` singleton.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

METADATA_SUFFIX = ".metadata.json"

STORAGE_MODE_ALONGSIDE = "alongside"
STORAGE_MODE_CENTRALIZED = "centralized"

_VALID_MODES = frozenset({STORAGE_MODE_ALONGSIDE, STORAGE_MODE_CENTRALIZED})


def _get_settings_value(key: str, default=None):
    """Read a setting defensively; never fail path resolution on settings errors."""

    try:
        from ..services.settings_manager import get_settings_manager

        value = get_settings_manager().get(key)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("sidecar_paths: settings lookup for %r failed: %s", key, exc)
        return default
    return default if value is None else value


def get_storage_mode() -> str:
    """Return the active sidecar storage mode (``alongside`` unless configured)."""

    mode = _get_settings_value("sidecar_storage_mode", STORAGE_MODE_ALONGSIDE)
    if mode not in _VALID_MODES:
        return STORAGE_MODE_ALONGSIDE
    return mode


def is_centralized() -> bool:
    """Return True when centralized sidecar storage is active and resolvable."""

    return get_storage_mode() == STORAGE_MODE_CENTRALIZED and bool(get_sidecar_root())


def _resolve_root_from_settings() -> str:
    """Resolve the configured/default centralized root, ignoring the active mode."""

    configured = _get_settings_value("sidecar_storage_path", "")
    if configured and isinstance(configured, str):
        root = os.path.abspath(os.path.expanduser(configured.strip()))
        if root:
            return root

    # Default: <settings_dir>/sidecars
    try:
        from .settings_paths import get_settings_dir

        return os.path.join(get_settings_dir(), "sidecars")
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("sidecar_paths: cannot resolve default sidecar root: %s", exc)
        return ""


def get_sidecar_root() -> str:
    """Return the absolute root directory for centralized sidecar storage.

    Empty string when centralized storage is not usable (mode alongside or an
    unresolvable configured path).
    """

    if get_storage_mode() != STORAGE_MODE_CENTRALIZED:
        return ""

    return _resolve_root_from_settings()


def get_configured_sidecar_root() -> str:
    """Return the centralized sidecar root regardless of the active mode.

    Unlike :func:`get_sidecar_root`, this resolves the configured
    ``sidecar_storage_path`` (or the ``<settings_dir>/sidecars`` default) even
    when the storage mode is ``alongside``. Migration tooling needs both
    layouts at once and must not depend on which mode is currently active.
    """

    return _resolve_root_from_settings()


def sanitize_path_component(name: str) -> str:
    """Return a filesystem-safe single path component."""

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name or "")
    return safe or "_"


def _iter_model_roots() -> List[str]:
    """Return every configured model root for the active library."""

    try:
        from ..config import config
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("sidecar_paths: config unavailable: %s", exc)
        return []

    roots: List[str] = []
    for attr in (
        "loras_roots",
        "base_models_roots",
        "embeddings_roots",
        "other_roots",
        "extra_loras_roots",
        "extra_checkpoints_roots",
        "extra_unet_roots",
        "extra_embeddings_roots",
    ):
        value = getattr(config, attr, None)
        if value:
            roots.extend(value)
    return roots


def _normalize_for_match(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def root_mirror_component(root_path: str) -> str:
    """Return the mirror path component identifying a model root.

    ``<sanitized basename>-<hash>`` where the hash is a short digest of the
    normalized absolute root path. Two roots sharing a basename (e.g.
    ``/mnt/a/loras`` and ``/mnt/b/loras``) would otherwise map to the same
    mirror directory and overwrite each other's sidecars.
    """

    normalized = _normalize_for_match(root_path)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{sanitize_path_component(os.path.basename(normalized))}-{digest}"


def resolve_centralized_dir(model_path: str) -> Optional[str]:
    """Return the centralized mirror directory for ``model_path``.

    The mirror layout is
    ``<sidecar_root>/<library>/<root_basename-roothash>/<rel_dir>``
    where ``rel_dir`` is the model's directory relative to the model root that
    contains it. The longest matching root wins so nested roots resolve to the
    most specific mirror. Returns ``None`` when centralized storage is inactive
    or the path is not under any configured model root.
    """

    return resolve_centralized_dir_for_dir(
        os.path.dirname(_normalize_for_match(model_path))
    )


def resolve_centralized_dir_for_dir(
    model_dir: str, *, sidecar_root: Optional[str] = None
) -> Optional[str]:
    """Return the centralized mirror directory for a model *directory*.

    Same layout as :func:`resolve_centralized_dir`, but accepts the directory
    itself. Used by folder-level operations (folder rename, mirror-tree walks)
    that have no model file path to derive from. Passing a configured model
    root returns the mirror base for that root.

    ``sidecar_root`` overrides the root lookup; pass
    :func:`get_configured_sidecar_root` to resolve mirror paths independently
    of the active storage mode (migration tooling).
    """

    root = sidecar_root if sidecar_root is not None else get_sidecar_root()
    if not root:
        return None

    normalized_dir = _normalize_for_match(model_dir)

    best_root: Optional[str] = None
    for candidate in _iter_model_roots():
        if not candidate:
            continue
        normalized = _normalize_for_match(candidate)
        if normalized_dir == normalized or normalized_dir.startswith(normalized + os.sep):
            if best_root is None or len(normalized) > len(best_root):
                best_root = normalized

    if best_root is None:
        return None

    try:
        from ..services.settings_manager import get_settings_manager

        library = get_settings_manager().get_active_library_name() or "default"
    except Exception:  # pragma: no cover - defensive fallback
        library = "default"

    rel_dir = os.path.relpath(normalized_dir, best_root)
    parts = [root, sanitize_path_component(library), root_mirror_component(best_root)]
    if rel_dir and rel_dir != os.curdir:
        parts.extend(sanitize_path_component(part) for part in rel_dir.split(os.sep) if part not in ("", os.curdir))
    return os.path.join(*parts)


def get_sidecar_dir(model_path: str) -> str:
    """Return the directory holding the model's sidecar/preview assets.

    Centralized mode falls back to the model's own directory (with a warning)
    when the path lies outside every configured model root.
    """

    if get_storage_mode() == STORAGE_MODE_CENTRALIZED:
        mirror = resolve_centralized_dir(model_path)
        if mirror:
            return mirror
        logger.warning(
            "sidecar_paths: %s is outside configured model roots; storing sidecar alongside",
            model_path,
        )
    return os.path.dirname(os.path.abspath(model_path))


def get_metadata_path(model_path: str) -> str:
    """Return the ``.metadata.json`` sidecar path for a model file."""

    base_name = os.path.splitext(os.path.basename(model_path))[0] + METADATA_SUFFIX
    return os.path.join(get_sidecar_dir(model_path), base_name)


def is_metadata_path(path: str) -> bool:
    """Return True when ``path`` already points at a metadata sidecar file."""

    return path.endswith(METADATA_SUFFIX)


def resolve_metadata_path(path: str) -> str:
    """Accept either a model path or a sidecar path and return the sidecar path."""

    if is_metadata_path(path):
        return path
    return get_metadata_path(path)


def get_preview_dir(model_path: str) -> str:
    """Return the directory holding the model's preview assets."""

    return get_sidecar_dir(model_path)
