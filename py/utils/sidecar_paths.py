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
  mirroring each model root's directory structure::

      <sidecar_root>/<root_component>/<rel_dir>/<name>.metadata.json

  ``<root_component>`` identifies the model root and **survives the root being
  moved or renamed**. It starts as the deterministic ``<sanitized
  basename>-<path digest>`` (so pre-existing mirrors, and mirrors left behind
  by a relocated sidecar root, still resolve) and is then pinned in
  ``<sidecar_root>/.lm-sidecar-roots.json`` together with the root's last
  known path and a few sample subdirectories. Re-anchoring a remembered
  identity to a new path keeps every sidecar under it usable; computing a new
  name instead would strand them and silently rebuild default metadata
  (losing favorites, notes, tags).

Hot-path behaviour: path resolution is a settings read plus a dict lookup.
The persistent map is loaded and reconciled lazily, at most once per change
of the configured model-root set, and only when centralized storage is
actually in use (``get_sidecar_dir`` short-circuits in alongside mode), so
default installs never read, write, or scan anything new. The root map file
and its directory are only created when there is something to remember.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

METADATA_SUFFIX = ".metadata.json"

STORAGE_MODE_ALONGSIDE = "alongside"
STORAGE_MODE_CENTRALIZED = "centralized"

_VALID_MODES = frozenset({STORAGE_MODE_ALONGSIDE, STORAGE_MODE_CENTRALIZED})

# Persistent root-identity map, stored inside the sidecar root so it travels
# with the mirror tree it describes.
ROOT_MAP_FILENAME = ".lm-sidecar-roots.json"
_ROOT_MAP_VERSION = 1

# Bounds for the re-anchor heuristic and the deferred sample persistence.
_MAX_SAMPLE_REL_DIRS = 16
_MAX_MATCH_PROBES = 64
_SAMPLE_SAVE_INTERVAL_SECONDS = 30.0

# Mirror directory names are ``<sanitized basename>-<8 hex>``; the suffix is a
# root id (or the legacy path digest) and is what distinguishes a component
# directory from a pre-identity-map library prefix directory.
_COMPONENT_PATTERN = re.compile(r"^.+-(?:[0-9a-f]{8})$")


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


def _installation_root() -> str:
    """Return the plugin installation directory (repository root)."""

    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _path_contains(base: str, path: str) -> bool:
    """Containment check tolerant of symlinked installs (custom_nodes links)."""

    for candidate in (os.path.abspath(path), os.path.realpath(path)):
        normalized = os.path.normcase(os.path.normpath(candidate))
        for root_variant in (os.path.abspath(base), os.path.realpath(base)):
            root_normalized = os.path.normcase(os.path.normpath(root_variant))
            if (
                normalized == root_normalized
                or normalized.startswith(root_normalized + os.sep)
            ):
                return True
    return False


def describe_sidecar_root() -> dict:
    """Describe the effective centralized sidecar root for UI display.

    ``inside_repo`` flags the portable-mode hazard: when settings live in the
    repository, the default root lands inside the plugin folder, where a
    reinstall or ``git clean`` would silently delete every sidecar.
    """

    configured = _get_settings_value("sidecar_storage_path", "")
    is_default = not (isinstance(configured, str) and configured.strip())
    root = _resolve_root_from_settings()
    return {
        "root": root,
        "is_default": is_default,
        "inside_repo": bool(root) and _path_contains(_installation_root(), root),
    }


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
    """Normalize a path for identity comparisons.

    Business paths are preserved (no ``realpath``): symlinks are not resolved,
    matching the rest of the codebase.
    """

    return os.path.normpath(os.path.abspath(path))


def _normalized_roots(raw_roots: Iterable[str]) -> Tuple[str, ...]:
    """Return the deduplicated, normalized, order-stable model roots."""

    seen: Dict[str, None] = {}
    for candidate in raw_roots:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        seen.setdefault(_normalize_for_match(candidate), None)
    return tuple(seen)


def _best_root_for(
    normalized_dir: str, normalized_roots: Tuple[str, ...]
) -> Optional[str]:
    """Return the most specific configured root containing ``normalized_dir``."""

    best: Optional[str] = None
    for normalized in normalized_roots:
        if normalized_dir == normalized or normalized_dir.startswith(
            normalized + os.sep
        ):
            if best is None or len(normalized) > len(best):
                best = normalized
    return best


class _RootMapState:
    """In-memory view of one sidecar root's identity map."""

    __slots__ = (
        "signature",
        "components",
        "root_ids",
        "entries",
        "unmatched",
        "loaded",
        "dirty_samples",
        "last_save",
        "persist_disabled",
    )

    def __init__(self) -> None:
        self.signature: Tuple[str, ...] = ()
        self.components: Dict[str, str] = {}
        self.root_ids: Dict[str, str] = {}
        self.entries: Dict[str, Dict[str, object]] = {}
        self.unmatched: List[str] = []
        self.loaded = False
        self.dirty_samples = False
        self.last_save = 0.0
        self.persist_disabled = False


_ROOT_MAPS: Dict[str, _RootMapState] = {}
_ROOT_MAPS_LOCK = threading.RLock()


def reset_root_map_cache() -> None:
    """Forget every cached root-identity map (tests, storage relocation)."""

    with _ROOT_MAPS_LOCK:
        _ROOT_MAPS.clear()


def _root_map_path(sidecar_root: str) -> str:
    return os.path.join(sidecar_root, ROOT_MAP_FILENAME)


def _load_root_map(sidecar_root: str) -> Dict[str, Dict[str, object]]:
    """Read the persistent map; unreadable or malformed files degrade to empty."""

    path = _root_map_path(sidecar_root)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("sidecar_paths: ignoring unreadable root map %s: %s", path, exc)
        return {}

    if not isinstance(payload, dict):
        return {}
    raw_roots = payload.get("roots")
    if not isinstance(raw_roots, dict):
        return {}

    entries: Dict[str, Dict[str, object]] = {}
    for root_id, raw_entry in raw_roots.items():
        if not isinstance(root_id, str) or not root_id:
            continue
        if not isinstance(raw_entry, dict):
            continue
        component = raw_entry.get("component")
        if not isinstance(component, str) or not component:
            continue
        samples = raw_entry.get("sample_rel_dirs")
        entries[root_id] = {
            "component": component,
            "basename": raw_entry.get("basename") or "",
            "last_path": raw_entry.get("last_path") or "",
            "sample_rel_dirs": (
                [item for item in samples if isinstance(item, str)][
                    :_MAX_SAMPLE_REL_DIRS
                ]
                if isinstance(samples, list)
                else []
            ),
        }
    return entries


def _persistable(sidecar_root: str) -> bool:
    """Return True when the root map could realistically be written.

    Walks up to the nearest existing ancestor (the sidecar root itself is
    created lazily, alongside the first sidecar) and checks write access. Used
    to decide whether identities can be remembered across restarts: when they
    cannot, resolution falls back to the deterministic path-derived component
    rather than handing out identifiers that would be forgotten.
    """

    probe = os.path.abspath(sidecar_root)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return bool(probe) and os.access(probe, os.W_OK)


def _write_root_map(sidecar_root: str, entries: Dict[str, Dict[str, object]]) -> bool:
    """Atomically persist ``entries`` as the root map for ``sidecar_root``."""

    path = _root_map_path(sidecar_root)
    # Snapshot before serializing: sample directories are appended from the
    # resolution path, which is not serialized with the map lock.
    payload = {
        "version": _ROOT_MAP_VERSION,
        "roots": {
            root_id: {
                "component": entry.get("component", ""),
                "basename": entry.get("basename", ""),
                "last_path": entry.get("last_path", ""),
                "sample_rel_dirs": list(entry.get("sample_rel_dirs") or []),
            }
            for root_id, entry in entries.items()
        },
    }
    temp_path = f"{path}.tmp"
    try:
        os.makedirs(sidecar_root, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except OSError as exc:
        logger.warning("sidecar_paths: cannot persist the root map %s: %s", path, exc)
        return False
    return True


def _save_root_map(sidecar_root: str, state: _RootMapState) -> bool:
    """Persist a reconciled state; disables persistence when it cannot write."""

    if state.persist_disabled:
        return False

    if not _write_root_map(sidecar_root, state.entries):
        state.persist_disabled = True
        logger.warning(
            "sidecar_paths: mirror directory names fall back to path-derived "
            "components for %s",
            sidecar_root,
        )
        return False
    state.dirty_samples = False
    state.last_save = time.monotonic()
    return True


def relocate_root_map(source_root: str, destination_root: str) -> bool:
    """Carry the root map from a relocated sidecar root to its destination.

    Call this after the mirror tree itself has been moved. Entries recorded
    under ``source_root`` win over any identity the destination picked up on
    its own: resolving against the new sidecar path *before* the relocation
    writes a map that names mirrors after the current model-root path, while
    the directories actually being moved are still named after the pinned
    identity. Destination-only entries are preserved, and the source file is
    always removed so the emptied tree can be pruned.

    Returns False only when a source map existed but could not be written to
    the destination — the caller must surface that, since the moved metadata
    would otherwise be unreachable. Cached state is dropped either way so the
    next resolution reloads the merged map.
    """

    source_path = _root_map_path(source_root)
    source_entries = _load_root_map(source_root)

    with _ROOT_MAPS_LOCK:
        if source_entries:
            destination_path = _root_map_path(destination_root)
            merged: Dict[str, Dict[str, object]] = {}
            if os.path.exists(destination_path):
                merged.update(_load_root_map(destination_root))
            source_paths = {
                _normalize_for_match(str(entry["last_path"]))
                for entry in source_entries.values()
                if entry.get("last_path")
            }
            preserved = {
                root_id: entry
                for root_id, entry in merged.items()
                if not entry.get("last_path")
                or _normalize_for_match(str(entry.get("last_path"))) not in source_paths
            }
            preserved.update(source_entries)
            if not _write_root_map(destination_root, preserved):
                return False

        if os.path.exists(source_path):
            try:
                os.remove(source_path)
            except OSError as exc:  # pragma: no cover - defensive cleanup
                logger.debug(
                    "sidecar_paths: cannot remove relocated root map %s: %s",
                    source_path,
                    exc,
                )

    reset_root_map_cache()
    return True


def _new_root_id() -> str:
    return uuid.uuid4().hex[:8]


def _legacy_component(root_path: str) -> str:
    """Return the deterministic path-derived component for a root.

    ``<sanitized basename>-<digest of the normalized absolute path>``. This is
    both the name mirrors created by older builds already use and the initial
    identity for a newly seen root, so a mirror is found again even when the
    root map is missing. Once an identity is recorded, the map keeps the name
    pinned across root moves.
    """

    normalized = _normalize_for_match(root_path)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{sanitize_path_component(os.path.basename(normalized))}-{digest}"


def _list_component_dirs(sidecar_root: str) -> Set[str]:
    """Return the mirror component directories present under ``sidecar_root``.

    Components are normally immediate children. Pre-identity-map builds nested
    them one level deeper under a library name
    (``<sidecar_root>/<library>/<component>``); those are reported as
    ``<library>/<component>`` so the legacy layout keeps resolving — the legacy
    prefix is treated purely as part of the component name and is never
    interpreted as a library.
    """

    try:
        names = os.listdir(sidecar_root)
    except OSError:
        return set()

    components: Set[str] = set()
    unqualified: List[str] = []
    for name in names:
        if name == ROOT_MAP_FILENAME or name.endswith(".tmp"):
            continue
        if not os.path.isdir(os.path.join(sidecar_root, name)):
            continue
        if _looks_like_component(name):
            components.add(name)
        else:
            unqualified.append(name)

    for prefix in unqualified:
        try:
            nested = os.listdir(os.path.join(sidecar_root, prefix))
        except OSError:
            continue
        for name in nested:
            if not _looks_like_component(name):
                continue
            if os.path.isdir(os.path.join(sidecar_root, prefix, name)):
                components.add(f"{prefix}/{name}")
    return components


def _looks_like_component(name: str) -> bool:
    """True for ``<basename>-<8 hex>`` mirror directory names."""

    return bool(_COMPONENT_PATTERN.match(name))


def _subdir_names(directory: str) -> Set[str]:
    """Sanitized names of ``directory``'s immediate subdirectories (bounded)."""

    names: Set[str] = set()
    try:
        with os.scandir(directory) as iterator:
            for index, dir_entry in enumerate(iterator):
                if index >= _MAX_MATCH_PROBES:
                    break
                try:
                    if dir_entry.is_dir():
                        names.add(sanitize_path_component(dir_entry.name))
                except OSError:
                    continue
    except OSError:
        return set()
    return names


def _mirror_dir_overlap(sidecar_root: str, component: str, root: str) -> int:
    """Count sibling directories shared by a mirror component and a root.

    Last-resort signal for re-anchoring when the entry carries no recorded
    sample directories (e.g. the map was lost): both sides are sanitized the
    same way, so renamed-but-similar layouts still overlap.
    """

    if not component:
        return 0
    mirror_names = _subdir_names(os.path.join(sidecar_root, component))
    if not mirror_names:
        return 0
    root_names = _subdir_names(root)
    if not root_names:
        return 0
    return len(mirror_names & root_names)


def _match_score(sidecar_root: str, entry: Dict[str, object], root: str) -> int:
    """Score how likely ``entry`` describes the mirror of ``root``."""

    score = 0
    if str(entry.get("basename") or "") == os.path.basename(root):
        score += 2

    samples = entry.get("sample_rel_dirs") or []
    if isinstance(samples, list):
        for rel in samples[:_MAX_MATCH_PROBES]:
            if not isinstance(rel, str) or not rel:
                continue
            parts = [part for part in rel.split("/") if part not in ("", ".")]
            if parts and os.path.isdir(os.path.join(root, *parts)):
                score += 1
        if not samples:
            score += _mirror_dir_overlap(
                sidecar_root, str(entry.get("component") or ""), root
            )
    return score


def _rank_scores(
    assignments: List[Tuple[int, str, str]],
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int], Dict[str, int]]:
    """Return (best/runner-up score per entry id, best/runner-up per root)."""

    best_id: Dict[str, int] = {}
    runner_id: Dict[str, int] = {}
    best_root: Dict[str, int] = {}
    runner_root: Dict[str, int] = {}
    for score, root_id, root in assignments:
        if score > best_id.get(root_id, 0):
            runner_id[root_id] = best_id.get(root_id, 0)
            best_id[root_id] = score
        elif score > runner_id.get(root_id, 0):
            runner_id[root_id] = score
        if score > best_root.get(root, 0):
            runner_root[root] = best_root.get(root, 0)
            best_root[root] = score
        elif score > runner_root.get(root, 0):
            runner_root[root] = score
    return best_id, runner_id, best_root, runner_root


def _due_for_sample_save(state: _RootMapState, now: float) -> bool:
    return now - state.last_save >= _SAMPLE_SAVE_INTERVAL_SECONDS


def _reconcile_root_map(
    sidecar_root: str,
    normalized_roots: Tuple[str, ...],
    state: _RootMapState,
) -> None:
    """Match remembered root identities against the configured roots.

    Order of preference per root: the identity previously recorded for the
    same path, then a deterministic path-derived component already on disk
    (pre-identity-map installs), then an orphaned identity re-anchored by
    basename/sample-directory scoring, then a unique unclaimed component whose
    name matches, and finally a brand-new identity.
    """

    entries = (
        state.entries
        if state.loaded and state.entries
        else _load_root_map(sidecar_root)
    )
    # Copy so partial mutation cannot leak between reconciliation attempts.
    entries = {root_id: dict(entry) for root_id, entry in entries.items()}

    on_disk = _list_component_dirs(sidecar_root)
    persistable = _persistable(sidecar_root)
    if not persistable:
        state.persist_disabled = True

    components: Dict[str, str] = {}
    root_ids: Dict[str, str] = {}
    claimed: Set[str] = set()
    changed = False

    by_path: Dict[str, str] = {}
    for root_id, entry in entries.items():
        last_path = entry.get("last_path")
        if isinstance(last_path, str) and last_path.strip():
            by_path.setdefault(_normalize_for_match(last_path), root_id)

    # 1. Same path as last time: reuse the remembered identity verbatim.
    pending: List[str] = []
    for root in normalized_roots:
        root_id = by_path.get(root)
        if root_id is not None:
            component = str(entries[root_id]["component"])
            if component not in claimed:
                components[root] = component
                root_ids[root] = root_id
                claimed.add(component)
                continue
        pending.append(root)

    if not persistable:
        # Identities created here could never be remembered; keep the layout
        # deterministic instead of stranding sidecars on the next restart.
        for root in normalized_roots:
            components.setdefault(root, _legacy_component(root))
        state.entries = {}
        state.root_ids = {}
        state.components = components
        state.unmatched = sorted(
            component for component in on_disk if component not in set(components.values())
        )
        state.signature = normalized_roots
        state.loaded = True
        _warn_unmatched(sidecar_root, state.unmatched)
        return

    # 2. Adopt a deterministic path-derived component already on disk. Older
    # builds nested it under the library name, hence the last-segment match.
    still_pending: List[str] = []
    for root in pending:
        legacy = _legacy_component(root)
        matches = [
            component
            for component in on_disk
            if component == legacy
            or component.rsplit("/", 1)[-1] == legacy
        ]
        component = matches[0] if len(matches) == 1 and matches[0] not in claimed else None
        if component is not None:
            root_id = _new_root_id()
            entries[root_id] = {
                "component": component,
                "basename": os.path.basename(root),
                "last_path": root,
                "sample_rel_dirs": [],
            }
            components[root] = component
            root_ids[root] = root_id
            claimed.add(component)
            changed = True
        else:
            still_pending.append(root)

    # 3. Re-anchor identities whose recorded path no longer exists.
    configured = set(normalized_roots)
    assignments: List[Tuple[int, str, str]] = []
    for root_id, entry in entries.items():
        last_path = str(entry.get("last_path") or "")
        component = str(entry["component"])
        if not last_path.strip() or component in claimed:
            continue
        if _normalize_for_match(last_path) in configured:
            continue
        for root in still_pending:
            score = _match_score(sidecar_root, entry, root)
            if score > 0:
                assignments.append((score, root_id, root))

    if assignments:
        best_id, runner_id, best_root, runner_root = _rank_scores(assignments)
        assignments.sort(key=lambda item: (-item[0], item[1], item[2]))
        used_ids: Set[str] = set()
        used_roots: Set[str] = set()
        for score, root_id, root in assignments:
            if root_id in used_ids or root in used_roots:
                continue
            # Never guess: the pair must be the unique best on both sides.
            if score < best_id[root_id] or score < best_root[root]:
                continue
            if runner_id.get(root_id, 0) == score or runner_root.get(root, 0) == score:
                continue
            entries[root_id]["last_path"] = root
            components[root] = str(entries[root_id]["component"])
            root_ids[root] = root_id
            claimed.add(str(entries[root_id]["component"]))
            used_ids.add(root_id)
            used_roots.add(root)
            changed = True
        still_pending = [root for root in still_pending if root not in used_roots]

    # 4/5. Remaining roots: adopt a uniquely matching unclaimed component,
    # otherwise mint a fresh identity.
    referenced = {str(entry["component"]) for entry in entries.values()}
    free_components = [
        component
        for component in on_disk
        if component not in claimed and component not in referenced
    ]
    for root in still_pending:
        prefix = sanitize_path_component(os.path.basename(root)) + "-"
        candidates = [
            component
            for component in free_components
            if component.rsplit("/", 1)[-1].startswith(prefix)
        ]
        # Default to the deterministic path-derived name. It is stable across
        # restarts even if the map is lost, and it matches what a sidecar-root
        # relocation or a mirror created by an older build already used; the
        # map only overrides it later, to keep the name across a root move.
        component = (
            candidates[0] if len(candidates) == 1 else _legacy_component(root)
        )
        if len(candidates) == 1:
            free_components.remove(component)
        root_id = _new_root_id()
        entries[root_id] = {
            "component": component,
            "basename": os.path.basename(root),
            "last_path": root,
            "sample_rel_dirs": [],
        }
        components[root] = component
        root_ids[root] = root_id
        claimed.add(component)
        changed = True

    state.entries = entries
    state.components = components
    state.root_ids = root_ids
    state.unmatched = sorted(
        component for component in on_disk if component not in claimed
    )
    state.signature = normalized_roots
    state.loaded = True

    _warn_unmatched(sidecar_root, state.unmatched)

    if changed and not _save_root_map(sidecar_root, state):
        _degrade_to_legacy(state, normalized_roots)


def _warn_unmatched(sidecar_root: str, unmatched: List[str]) -> None:
    """Surface mirror directories no configured root claims (never silent)."""

    if not unmatched:
        return
    preview = ", ".join(unmatched[:5])
    logger.warning(
        "sidecar_paths: %d mirrored sidecar dir(s) under %s are not linked to any "
        "configured model root (%s%s). Their metadata stays on disk but is not "
        "used until the model root is restored or re-anchored.",
        len(unmatched),
        sidecar_root,
        preview,
        ", ..." if len(unmatched) > 5 else "",
    )


def _degrade_to_legacy(state: _RootMapState, normalized_roots: Tuple[str, ...]) -> None:
    """Fall back to deterministic components after a failed persist."""

    state.components = {root: _legacy_component(root) for root in normalized_roots}
    state.root_ids = {}
    state.entries = {}
    state.unmatched = []
    state.dirty_samples = False
    state.persist_disabled = True


def _ensure_root_map(
    sidecar_root: str, normalized_roots: Tuple[str, ...]
) -> _RootMapState:
    """Return the reconciled identity map, reusing the cached one when current."""

    key = _normalize_for_match(sidecar_root)
    state = _ROOT_MAPS.get(key)
    if state is not None and state.loaded and state.signature == normalized_roots:
        return state

    with _ROOT_MAPS_LOCK:
        state = _ROOT_MAPS.get(key)
        if state is not None and state.loaded and state.signature == normalized_roots:
            return state
        if state is None:
            state = _RootMapState()
            _ROOT_MAPS[key] = state
        _reconcile_root_map(sidecar_root, normalized_roots, state)
        return state


def _component_for(
    best_root: str,
    sidecar_root: str,
    normalized_roots: Tuple[str, ...],
    rel_dir: str,
) -> Optional[str]:
    """Return the pinned mirror component for ``best_root``."""

    state = _ensure_root_map(sidecar_root, normalized_roots)
    if not state.components.get(best_root):
        return _legacy_component(best_root)
    _record_sample(sidecar_root, state, best_root, rel_dir)
    # Re-read: a failed sample persist degrades the state to deterministic
    # names, and this call must agree with every later one.
    return state.components.get(best_root) or _legacy_component(best_root)


def _record_sample(
    sidecar_root: str, state: _RootMapState, root: str, rel_dir: str
) -> None:
    """Remember a root-relative directory to make future re-anchoring precise."""

    root_id = state.root_ids.get(root)
    if not root_id:
        return
    entry = state.entries.get(root_id)
    if entry is None:
        return

    normalized = (rel_dir or "").replace(os.sep, "/").strip("/")
    if not normalized or normalized == ".":
        return

    samples = entry.get("sample_rel_dirs")
    if not isinstance(samples, list):
        samples = []
        entry["sample_rel_dirs"] = samples
    if normalized in samples or len(samples) >= _MAX_SAMPLE_REL_DIRS:
        return

    samples.append(normalized)
    state.dirty_samples = True
    if state.persist_disabled or not _due_for_sample_save(state, time.monotonic()):
        return
    with _ROOT_MAPS_LOCK:
        if state.persist_disabled or not _due_for_sample_save(state, time.monotonic()):
            return
        if not _save_root_map(sidecar_root, state):
            _degrade_to_legacy(state, state.signature)


def root_mirror_component(root_path: str, *, sidecar_root: Optional[str] = None) -> str:
    """Return the mirror component identifying a model root.

    The deterministic ``<sanitized basename>-<path digest>`` until the root map
    pins a different name for it — which happens only when a remembered root
    was moved or renamed and had to be re-anchored. Two roots sharing a
    basename always get distinct components, so their mirrors cannot collide.
    """

    resolved_root = sidecar_root if sidecar_root is not None else get_configured_sidecar_root()
    normalized = _normalize_for_match(root_path)
    if not resolved_root:
        return _legacy_component(normalized)
    state = _ensure_root_map(resolved_root, _normalized_roots(_iter_model_roots()))
    return state.components.get(normalized) or _legacy_component(normalized)


def resolve_centralized_dir(model_path: str) -> Optional[str]:
    """Return the centralized mirror directory for ``model_path``.

    The mirror layout is ``<sidecar_root>/<root_component>/<rel_dir>`` where
    ``rel_dir`` is the model's directory relative to the model root that
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
    normalized_roots = _normalized_roots(_iter_model_roots())
    best_root = _best_root_for(normalized_dir, normalized_roots)
    if best_root is None:
        return None

    rel_dir = os.path.relpath(normalized_dir, best_root)
    component = _component_for(best_root, root, normalized_roots, rel_dir)
    if not component:
        return None

    parts = [root, component]
    if rel_dir and rel_dir != os.curdir:
        parts.extend(
            sanitize_path_component(part)
            for part in rel_dir.split(os.sep)
            if part not in ("", os.curdir)
        )
    return os.path.join(*parts)


def get_unmatched_sidecar_components() -> List[Dict[str, str]]:
    """Describe mirrored sidecar directories no configured root claims.

    Empty unless centralized storage is active. Used by diagnostics to surface
    metadata stranded by a moved model root (see :func:`_warn_unmatched`).
    """

    sidecar_root = get_sidecar_root()
    if not sidecar_root:
        return []

    state = _ensure_root_map(sidecar_root, _normalized_roots(_iter_model_roots()))
    by_component: Dict[str, Dict[str, object]] = {}
    for entry in state.entries.values():
        by_component.setdefault(str(entry.get("component") or ""), entry)

    unmatched: List[Dict[str, str]] = []
    for component in state.unmatched:
        entry = by_component.get(component) or {}
        unmatched.append(
            {
                "component": component,
                "basename": str(entry.get("basename") or ""),
                "last_path": str(entry.get("last_path") or ""),
            }
        )
    return unmatched


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
