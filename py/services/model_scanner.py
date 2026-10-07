import json
import os
import logging
import asyncio
import threading
import time
import shutil
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Type, Union, cast

from ..utils.models import BaseModelMetadata, autov3_from_civitai_files
from ..config import config
from ..utils.file_utils import find_preview_file, get_preview_extension, calculate_sha256, calculate_autov3
from ..utils.metadata_manager import MetadataManager
from ..utils.sidecar_paths import (
    get_metadata_path,
    get_preview_dir,
    get_sidecar_dir,
    is_centralized,
    resolve_centralized_dir_for_dir,
)
from ..utils.civitai_utils import resolve_license_info
from .model_cache import ModelCache
from .model_hash_index import ModelHashIndex
from .model_lifecycle_service import delete_model_artifacts, _require_path_in_library_roots
from .model_sources import normalize_metadata_source
from .service_registry import ServiceRegistry
from .websocket_manager import ws_manager
from .persistent_model_cache import get_persistent_cache
from .settings_manager import get_settings_manager
from .pending_delete_service import PENDING_DELETE_DIR_NAME, get_pending_delete_service
from .cache_entry_validator import CacheEntryValidator
from .cache_health_monitor import CacheHealthMonitor, CacheHealthStatus

logger = logging.getLogger(__name__)

# Canonical set of weight-file extensions stripped when normalizing model
# names for matching (ModelScanner.find_matching_models and the recipe rematch
# filename key share this set). It is the union of the LoRA scanner set
# ({".safetensors"}) and the Checkpoint scanner set (ComfyUI's
# supported_pt_extensions plus ".gguf") so type-blind lookups (lora +
# checkpoint merged) cover every format either scanner indexes. ".safebin"
# is deliberately absent — no scanner indexes it, so a recipe entry
# "model.safebin" must not be bound to a local "model.safetensors".
WEIGHT_FILE_EXTENSIONS = frozenset(
    {
        ".safetensors",
        ".ckpt",
        ".pt",
        ".pt2",
        ".bin",
        ".pth",
        ".pkl",
        ".sft",
        ".gguf",
    }
)


def _is_excluded_dir(name: str) -> bool:
    """Return True when a directory entry must be skipped during model walks.

    The pending-delete staging directory is excluded so staged files never
    appear in the library as ghost model entries.
    """
    return name == PENDING_DELETE_DIR_NAME


def _is_hidden_relative_path(rel_path: str) -> bool:
    """Return True when any segment of a relative path is a hidden directory."""
    return any(part.startswith(".") for part in rel_path.replace(os.sep, "/").split("/"))


def _file_name_stem(file_path: str) -> str:
    """Return the extension-free file name of a normalized model path.

    ``file_name`` cache/sidecar fields are defined as the on-disk stem, so this
    is the authoritative value to compare stored names against (issue #1112).
    """
    return os.path.splitext(os.path.basename(file_path))[0]


# Maps a scanner model type to the manager page type used in progress
# broadcasts (e.g. 'lora' -> 'loras').
PAGE_TYPE_MAP = {
    'lora': 'loras',
    'checkpoint': 'checkpoints',
    'embedding': 'embeddings',
    'other': 'other',
}

# Case-insensitive cache matching is a Windows-only safety net (NTFS treats
# "Model.txt" and "model.TXT" as the same file). Module-level so the branch can
# be exercised on case-sensitive filesystems in tests.
_CASE_INSENSITIVE_PATHS: bool = os.name == "nt"

# Cadence of walk-phase progress broadcasts during a reconcile.
_WALK_PROGRESS_INTERVAL_SECONDS = 0.5

# Share of the progress bar owned by the reconcile walk. The new-file pass
# takes the rest (50-99) so the bar never jumps backwards between phases.
_WALK_PROGRESS_SHARE = 50

# How many files a walk worker may scan between two progress reports.
_WALK_PROGRESS_REPORT_EVERY = 256


def _new_file_pass_progress(processed: int, total: int) -> int:
    """Bar percentage for the new-file pass (walk share .. 99)."""
    if total <= 0:
        return _WALK_PROGRESS_SHARE
    ratio = min(max(processed / total, 0.0), 1.0)
    return _WALK_PROGRESS_SHARE + min(49, int(ratio * 49))


# Maximum length of a root label in progress messages and menus; the full path
# always stays available in the tooltip.
_ROOT_LABEL_MAX_LENGTH = 40


def _truncate_label(label: str, limit: int = _ROOT_LABEL_MAX_LENGTH) -> str:
    """Middle-truncate an over-long label."""
    if len(label) <= limit:
        return label
    keep = max(limit - 3, 1)
    head = (keep + 1) // 2
    tail = keep - head
    if not tail:
        return f"{label[:head]}..."
    return f"{label[:head]}...{label[-tail:]}"


def _root_path_parts(root: str) -> Tuple[str, List[str]]:
    """Split a root into its drive prefix (Windows) and its path segments."""
    drive, tail = os.path.splitdrive(root)
    normalized = tail.replace("\\", "/").strip("/")
    return drive, [part for part in normalized.split("/") if part]


def _root_display_labels(roots: Sequence[str]) -> Dict[str, str]:
    """Return a unique, human-friendly label for every root in the set.

    The label starts as the last path segment (prefixed with the drive letter on
    Windows, e.g. ``G: loras``) and grows leftwards with **real parent path
    segments** until it is unique inside the set (``usb/loras`` vs
    ``ssd/loras``). Roots that still render identically (Windows case variants,
    a duplicated config entry) get a deterministic numeric suffix.

    Labels are a property of the whole set, so they are computed from the sorted
    root list: the same configuration always yields the same labels, whatever
    order the roots are walked in.
    """
    if not roots:
        return {}

    parts_by_root = {root: _root_path_parts(root) for root in roots}
    depth = {root: (1 if parts_by_root[root][1] else 0) for root in roots}

    def _render(root: str) -> str:
        drive, parts = parts_by_root[root]
        if not parts:
            return drive or root
        take = max(min(depth[root], len(parts)), 1)
        tail = "/".join(parts[len(parts) - take:])
        return f"{drive} {tail}" if drive else tail

    # Grow the depth of colliding labels until they can be told apart.
    while True:
        groups: Dict[str, List[str]] = {}
        for root in roots:
            groups.setdefault(_render(root), []).append(root)
        colliding = [group for group in groups.values() if len(group) > 1]
        if not colliding:
            break
        grew = False
        for group in colliding:
            for root in group:
                if depth[root] < len(parts_by_root[root][1]):
                    depth[root] += 1
                    grew = True
        if not grew:
            break

    labels = {root: _render(root) for root in roots}
    fallback: Dict[str, List[str]] = {}
    for root in sorted(roots):
        fallback.setdefault(labels[root], []).append(root)
    for label, group in fallback.items():
        if len(group) > 1:
            for index, root in enumerate(group, start=1):
                labels[root] = f"{label} ({index})"

    return {root: _truncate_label(label) for root, label in labels.items()}


def _normalized_root_prefix(root: str) -> str:
    """Forward-slash root prefix used to attribute cached paths to a root."""
    prefix = os.path.normpath(root).replace(os.sep, "/")
    if not prefix.endswith("/"):
        prefix += "/"
    return prefix.lower() if _CASE_INSENSITIVE_PATHS else prefix


def _path_matches_prefix(path: str, prefix: str) -> bool:
    """Match a cached business path against a normalized scope prefix."""
    candidate = path.lower() if _CASE_INSENSITIVE_PATHS else path
    return candidate.startswith(prefix)


def _scope_prefix(root: str, folder: Optional[str] = None) -> str:
    """Normalized prefix covering a root, or a folder inside that root."""
    prefix = _normalized_root_prefix(root)
    if folder:
        relative = folder.replace("\\", "/").strip("/")
        if relative:
            if _CASE_INSENSITIVE_PATHS:
                relative = relative.lower()
            prefix = f"{prefix}{relative}/"
    return prefix


def _scope_walk_path(root: str, folder: Optional[str] = None) -> str:
    """Filesystem path a scoped walk starts at (the root itself when unscoped)."""
    if not folder:
        return root
    relative = folder.replace("\\", "/").strip("/")
    if not relative:
        return root
    return os.path.join(root, *relative.split("/"))


@dataclass(frozen=True)
class ReconcileScope:
    """Restrict a reconcile to some of the configured roots and/or a folder.

    ``roots=None`` means "every configured root". ``folder`` is a root-relative
    folder in forward-slash form and applies to each root in the scope.
    """

    roots: Optional[Tuple[str, ...]] = None
    folder: Optional[str] = None


class _UnreachablePaths:
    """Prefixes this reconcile could not read; their entries are never pruned.

    Populated from three sources: a configured root that is not reachable, a
    directory ``os.walk`` failed to enter (permissions, I/O error, a Windows
    junction to an offline drive), and a known first-level symlink whose target
    is not a directory. Cached entries under these prefixes are reported instead
    of removed, so switching a drive off can no longer wipe its models.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prefixes: List[str] = []
        self._details: Dict[str, Dict[str, Any]] = {}

    def add(self, path: str, reason: str) -> None:
        prefix = _normalized_root_prefix(path)
        with self._lock:
            if prefix in self._details:
                return
            self._details[prefix] = {
                'path': path.replace(os.sep, '/'),
                'reason': reason,
                'kept': 0,
            }
            self._prefixes.append(prefix)

    def match(self, cached_path: str) -> Optional[str]:
        """Return the prefix covering ``cached_path``, if any."""
        for prefix in self._prefixes:
            if _path_matches_prefix(cached_path, prefix):
                return prefix
        return None

    def record_kept(self, prefix: str, amount: int = 1) -> None:
        detail = self._details.get(prefix)
        if detail is not None:
            detail['kept'] += amount

    def total_kept(self) -> int:
        return sum(detail['kept'] for detail in self._details.values())

    def count(self) -> int:
        return len(self._details)

    def has_entries(self) -> bool:
        return bool(self._details)

    def payload(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Most affected prefixes first, capped for the progress payload."""
        entries = sorted(
            self._details.values(), key=lambda detail: detail['kept'], reverse=True
        )
        return [dict(entry) for entry in entries[:limit]]


def _count_cached_entries_for_prefixes(
    cached_paths: Set[str], prefixes: Sequence[Tuple[str, str]]
) -> Dict[str, int]:
    """Count cached entries per ``(key, normalized prefix)`` pair.

    Longest prefix wins, so a folder scope counts only the entries inside it.
    Used as the walk-workload weight for progress reporting: the walk itself is
    what discovers the real file count, so the cached entry count is the only
    estimate available up front.
    """
    counts: Dict[str, int] = {key: 0 for key, _prefix in prefixes}
    if not prefixes:
        return counts

    ordered = sorted(prefixes, key=lambda item: len(item[1]), reverse=True)
    case_insensitive = _CASE_INSENSITIVE_PATHS
    for path in cached_paths:
        candidate = path.lower() if case_insensitive else path
        for key, prefix in ordered:
            if candidate.startswith(prefix):
                counts[key] += 1
                break
    return counts


def _count_cached_entries_per_root(
    cached_paths: Set[str], roots: Sequence[str]
) -> Dict[str, int]:
    """Attribute cached entries to model roots (longest prefix wins)."""
    return _count_cached_entries_for_prefixes(
        cached_paths, [(root, _normalized_root_prefix(root)) for root in roots]
    )


def _root_device_key(root: str) -> str:
    """Group key identifying the storage device that holds a root.

    Roots sharing a device must be walked sequentially so directory claims stay
    deterministic (configured order wins), while roots on different devices are
    independent and can be walked by parallel workers.
    """
    drive, _tail = os.path.splitdrive(root)
    if drive:
        return drive.lower()
    try:
        return f"dev:{os.stat(root).st_dev}"
    except OSError:
        return f"path:{os.path.normpath(root)}"


def _group_roots_by_device(roots: Sequence[str]) -> List[List[str]]:
    """Group roots by device, preserving the configured root order.

    Roots on distinct devices cannot alias unless a symlink crosses devices, so
    walking them in parallel cannot disturb the directory-claim order in any
    realistic layout (and even then the realpath alias index keeps the cached
    business path stable).
    """
    groups: Dict[str, List[str]] = {}
    for root in roots:
        groups.setdefault(_root_device_key(root), []).append(root)
    return list(groups.values())


def _build_realpath_index(cached_paths: Set[str]) -> Dict[str, str]:
    """Map realpath -> cached business path (overlapping roots / symlinks)."""
    index: Dict[str, str] = {}
    for cached_path in cached_paths:
        try:
            index.setdefault(os.path.realpath(cached_path), cached_path)
        except Exception:
            continue
    return index


def _build_casefold_index(cached_paths: Set[str]) -> Dict[str, str]:
    """Map lower-cased path -> cached business path (Windows case fallback)."""
    index: Dict[str, str] = {}
    for cached_path in cached_paths:
        index.setdefault(cached_path.lower(), cached_path)
    return index


class _CachedPathLookups:
    """Lazily built path indexes over the cached paths, safe for workers.

    Both indexes are only ever consulted for walk *misses*, so building them on
    first use keeps a no-change refresh free of per-cached-entry realpath work.
    The case-fold index replaces the former linear scan over every cached path,
    which was O(files x cached entries) whenever it was reached.
    """

    def __init__(self, cached_paths: Set[str]) -> None:
        self.cached_paths = cached_paths
        self._lock = threading.Lock()
        self._realpath_index: Optional[Dict[str, str]] = None
        self._casefold_index: Optional[Dict[str, str]] = None

    def match_real_path(self, real_path: str) -> Optional[str]:
        index = self._realpath_index
        if index is None:
            with self._lock:
                if self._realpath_index is None:
                    self._realpath_index = _build_realpath_index(self.cached_paths)
                index = self._realpath_index
        return index.get(real_path)

    def match_casefold_path(self, file_path: str) -> Optional[str]:
        index = self._casefold_index
        if index is None:
            with self._lock:
                if self._casefold_index is None:
                    self._casefold_index = _build_casefold_index(self.cached_paths)
                index = self._casefold_index
        return index.get(file_path.lower())


class _RealDirClaims:
    """Thread-safe claim set for real directory paths.

    Mirrors the historical global ``visited_real_paths`` set: a directory
    reachable through several roots (overlapping roots, symlinked aliases) must
    only be walked once, otherwise the same physical file could end up in the
    library under two business paths.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claimed: Set[str] = set()

    def claim(self, real_path: str) -> bool:
        with self._lock:
            if real_path in self._claimed:
                return False
            self._claimed.add(real_path)
            return True


class _ReconcileWalkTracker:
    """Thread-safe progress bookkeeping for the reconcile walk.

    Per-root progress is weighted by the number of cached entries under that
    root: the walk is what discovers the real file count, so the cached count
    is the only workload estimate available before it runs. Roots with no
    cached entries contribute a single weight unit and are reported only once
    they finish.
    """

    def __init__(
        self,
        roots: Sequence[str],
        expected: Mapping[str, int],
        labels: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._roots: List[str] = list(roots)
        # Callers that already labelled the full configured root set pass those
        # labels in, so the progress line and the refresh menu never disagree on
        # how a root is named.
        resolved = dict(labels) if labels else _root_display_labels(self._roots)
        self._labels = {root: resolved.get(root) or root for root in self._roots}
        self._expected = {
            root: max(int(expected.get(root, 0) or 0), 0) for root in self._roots
        }
        self._weight = {
            root: max(self._expected[root], 1) for root in self._roots
        }
        self._seen = {root: 0 for root in self._roots}
        self._done = {root: False for root in self._roots}
        self._active: Set[str] = set()

    def start_root(self, root: str) -> None:
        with self._lock:
            if root in self._seen:
                self._active.add(root)

    def report(self, root: str, files_seen: int) -> None:
        with self._lock:
            if root in self._seen:
                self._seen[root] = max(int(files_seen), 0)

    def finish_root(self, root: str) -> None:
        with self._lock:
            self._done[root] = True
            self._active.discard(root)

    def snapshot(self) -> Optional[Dict[str, Any]]:
        """Return the current payload extras plus the bar percentage."""
        with self._lock:
            if not self._roots:
                return None

            total_weight = sum(self._weight.values()) or 1
            completed = 0.0
            files_seen = 0
            roots_done = 0
            for root in self._roots:
                files_seen += self._seen[root]
                if self._done[root]:
                    completed += self._weight[root]
                    roots_done += 1
                    continue
                expected = self._expected[root]
                if expected > 0:
                    completed += self._weight[root] * min(
                        self._seen[root] / expected, 0.99
                    )

            active = [root for root in self._roots if root in self._active]
            if active:
                current = max(active, key=lambda root: self._seen[root])
            else:
                current = self._roots[-1]

            expected_total = sum(self._expected.values())
            ratio = min(completed / total_weight, 1.0)
            return {
                'progress': min(_WALK_PROGRESS_SHARE, int(ratio * _WALK_PROGRESS_SHARE)),
                # processed/total feed the client-side ETA; the total is a lower
                # bound and never below the files already seen, so the estimate
                # stays coherent when the library grew since the last scan.
                'processed': files_seen,
                'total': max(expected_total, files_seen),
                'files_seen': files_seen,
                'roots_total': len(self._roots),
                'roots_done': roots_done,
                'active_roots': [self._labels[root] for root in active][:4],
                'current_name': self._labels[current],
            }


@dataclass
class _RootWalkResult:
    """Outcome of walking a single model root (no scanner state touched)."""

    root_path: str
    found_paths: Set[str] = field(default_factory=set)
    stale_paths: List[str] = field(default_factory=list)
    # (business path, real path) pairs for files that are neither cached nor
    # excluded; the caller claims real paths in configured root order.
    new_candidates: List[Tuple[str, str]] = field(default_factory=list)
    discovered_folders: Set[str] = field(default_factory=set)
    files_seen: int = 0
    cancelled: bool = False


def _walk_root_for_reconcile(
    *,
    root_path: str,
    file_extensions: Set[str],
    cached_paths: Set[str],
    path_to_item: Mapping[str, Dict[str, Any]],
    lookups: _CachedPathLookups,
    dir_claims: _RealDirClaims,
    excluded_models: Set[str],
    is_cancelled: Callable[[], bool],
    report_progress: Callable[[int], None],
    walk_path: Optional[str] = None,
    unreachable: Optional[_UnreachablePaths] = None,
) -> _RootWalkResult:
    """Walk one model root and classify every model file found.

    ``walk_path`` defaults to the root itself; a folder scope starts the walk
    deeper but still resolves ``folder``/``file_path`` against ``root_path`` so
    cache entries keep their library-relative shape.

    Runs synchronously (worker thread) and never mutates scanner state: all
    cache updates happen on the event loop once every root has been walked.
    """
    result = _RootWalkResult(root_path=root_path)
    stale_seen: Set[str] = set()
    files_since_report = 0
    walk_start = walk_path or root_path

    def _on_walk_error(error: OSError) -> None:
        """Record a directory the walk could not enter (offline/denied)."""
        filename = getattr(error, 'filename', None)
        if filename and unreachable is not None:
            unreachable.add(str(filename), 'unreadable_dir')

    def mark_stale_if_needed(cached_path: str) -> None:
        """Queue a cached path for file_name repair when it drifted."""
        if cached_path in stale_seen:
            return
        item = path_to_item.get(cached_path)
        if item is None:
            return
        if item.get("file_name") == _file_name_stem(cached_path):
            return
        stale_seen.add(cached_path)
        result.stale_paths.append(cached_path)

    for root, dirnames, files in os.walk(
        walk_start, followlinks=True, onerror=_on_walk_error
    ):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]

        real_root = os.path.realpath(root)
        if not dir_claims.claim(real_root):
            continue

        # Record every visited directory (including empty ones) so the folder
        # tree stays accurate without a live walk.
        rel_dir = os.path.relpath(
            os.path.abspath(root), os.path.abspath(root_path)
        ).replace(os.path.sep, "/")
        if rel_dir != "." and not _is_hidden_relative_path(rel_dir):
            result.discovered_folders.add(rel_dir)

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in file_extensions:
                continue

            result.files_seen += 1
            files_since_report += 1
            if files_since_report >= _WALK_PROGRESS_REPORT_EVERY:
                # A flat library (thousands of files in one directory) would
                # otherwise report nothing until that directory ends.
                files_since_report = 0
                report_progress(result.files_seen)

            # Construct paths exactly as they would be in cache
            file_path = os.path.join(root, file).replace(os.sep, '/')

            if file_path in cached_paths:
                result.found_paths.add(file_path)
                mark_stale_if_needed(file_path)
                continue

            # Only a cache miss needs the physical path, so the realpath
            # syscalls are paid per changed file rather than per file in the
            # library.
            real_file_path = os.path.realpath(os.path.join(root, file))

            cached_real_match = lookups.match_real_path(real_file_path)
            if cached_real_match:
                result.found_paths.add(cached_real_match)
                mark_stale_if_needed(cached_real_match)
                continue

            if file_path in excluded_models:
                continue

            # Windows: a cached path may differ from the walk result only by
            # case. O(1) via the lower-cased index (was a full scan of the
            # cached paths per miss).
            if _CASE_INSENSITIVE_PATHS:
                cached_case_match = lookups.match_casefold_path(file_path)
                if cached_case_match:
                    result.found_paths.add(cached_case_match)
                    mark_stale_if_needed(cached_case_match)
                    continue

            # Not cached yet; the caller claims the real path in root order so
            # a file reachable through several roots is only added once.
            result.new_candidates.append((file_path, real_file_path))

        if files_since_report:
            # Publish per directory so a library spread over many directories
            # reports as it progresses, not only at the end of the walk.
            files_since_report = 0
            report_progress(result.files_seen)

        if is_cancelled():
            result.cancelled = True
            break

    report_progress(result.files_seen)
    return result


def _is_pending_delete_path(path: str) -> bool:
    """Return True when any path component is the pending-delete staging dir."""
    normalized = str(path).replace(os.sep, "/")
    return any(part == PENDING_DELETE_DIR_NAME for part in normalized.split("/"))


@dataclass
class CacheBuildResult:
    """Represents the outcome of scanning model files for cache building."""

    raw_data: List[Dict[str, Any]]
    hash_index: ModelHashIndex
    tags_count: Dict[str, int]
    excluded_models: List[str]
    # Every directory under the model roots (including empty ones) discovered
    # during the scan, or None when the source has no folder information
    # (e.g. a persisted snapshot predating folder recording).
    all_folders: Optional[List[str]] = None

class ModelScanner:
    """Base service for scanning and managing model files"""
    
    _instances = {}  # Dictionary to store instances by class
    _locks = {}  # Dictionary to store locks by class
    
    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for each subclass"""
        if cls not in cls._instances:
            cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]
    
    @classmethod
    def _get_lock(cls):
        """Get or create a lock for this class"""
        if cls not in cls._locks:
            cls._locks[cls] = asyncio.Lock()
        return cls._locks[cls]
    
    @classmethod
    async def get_instance(cls):
        """Get singleton instance with async support"""
        lock = cls._get_lock()
        async with lock:
            if cls not in cls._instances:
                cls._instances[cls] = cls()  # pyright: ignore[reportCallIssue]
            return cls._instances[cls]
    
    def __init__(self, model_type: str, model_class: Type[BaseModelMetadata], file_extensions: Set[str], hash_index: Optional[ModelHashIndex] = None):
        """Initialize the scanner
        
        Args:
            model_type: Type of model (lora, checkpoint, etc.)
            model_class: Class used to create metadata instances
            file_extensions: Set of supported file extensions including the dot (e.g. {'.safetensors'})
            hash_index: Hash index instance (optional)
        """
        # Ensure initialization happens only once per instance
        if hasattr(self, '_initialized'):
            return
            
        self.model_type = model_type
        self.model_class = model_class
        self.file_extensions = file_extensions
        self._cache: Any = None
        self._cache_version: int = 0
        self._hash_index = hash_index or ModelHashIndex()
        self._tags_count = {}  # Dictionary to store tag counts
        self._is_initializing = False  # Flag to track initialization state
        self._excluded_models = []  # List to track excluded models
        self._persistent_cache = get_persistent_cache()
        self._name_display_mode = self._resolve_name_display_mode()
        self._cancel_requested = False  # Flag for cancellation
        self._move_locks: Dict[str, asyncio.Lock] = {}  # Per-source-file move locks
        # Bulk-operation deferral: while _defer_persist_depth > 0,
        # update_single_model_cache() skips the per-call resort/persist and
        # only marks _deferred_persist_pending; the exit of the outermost
        # defer_cache_persist() context finalizes once (see
        # _finalize_deferred_cache_persist).
        self._defer_persist_depth = 0
        self._deferred_persist_pending = False
        self._autov3_backfill_scheduled = False  # One-time AutoV3 backfill trigger per process
        # Summary of the last incremental reconcile (see last_reconcile_summary)
        self._last_reconcile_summary: Optional[Dict[str, Any]] = None
        # Guard against concurrent all-folders backfill walks (cold fallback
        # for persisted snapshots that predate folder recording).
        self._all_folders_backfill_running = False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        self._loop = loop
        self.loop = loop
        self._initialized = True

        # Register this service
        asyncio.create_task(self._register_service())

    @property
    def page_type(self) -> str:
        """Manager page type used in progress broadcasts (e.g. 'loras')."""
        return PAGE_TYPE_MAP.get(self.model_type, self.model_type)

    async def _broadcast_scan_progress(
        self,
        status: str,
        stage: str,
        progress: int,
        full_rebuild: bool,
        **extra: Any,
    ) -> None:
        """Broadcast manual-refresh scan progress on the generic WS channel.

        Best-effort only: broadcast failures must never affect the scan itself.
        """
        payload: Dict[str, Any] = {
            'type': 'scan_progress',
            'status': status,
            'model_type': self.model_type,
            'pageType': self.page_type,
            'stage': stage,
            'full_rebuild': full_rebuild,
            'progress': progress,
        }
        payload.update(extra)
        try:
            await ws_manager.broadcast(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(f"Error broadcasting scan progress for {self.model_type}: {exc}")

    @property
    def cache_version(self) -> int:
        """Monotonic version counter for the in-memory cache.

        Every write path that mutates scanner cache state calls
        :meth:`bump_cache_version`, so consumers (e.g. RecipeScanner) can
        detect when a cached derivation of the raw data is stale. Reads never
        bump.
        """
        return self._cache_version

    def bump_cache_version(self) -> None:
        """Invalidate derived caches by incrementing the cache version.

        Public because external services (model lifecycle, route handlers)
        rewrite scanner raw_data directly and must be able to invalidate it.
        """
        self._cache_version += 1

    def on_library_changed(self, reconcile: bool = False) -> None:
        """Reset caches when the active library changes.

        When ``reconcile`` is True an incremental reconcile runs right after
        the cache is re-hydrated, so newly configured roots are scanned and
        entries for removed roots are purged. Used when scanner-affecting
        settings (e.g. the Other Models toggles) change.
        """
        self._persistent_cache = get_persistent_cache()
        self._cache = None
        self._hash_index = ModelHashIndex()
        self._tags_count = {}
        self._excluded_models = []
        self._is_initializing = False
        self._name_display_mode = self._resolve_name_display_mode()
        self.bump_cache_version()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and not loop.is_closed():
            self._loop = loop
            self.loop = loop
            loop.create_task(self.initialize_in_background(reconcile=reconcile))

    def _resolve_name_display_mode(self) -> str:
        """Return the configured display mode for name sorting."""

        try:
            manager = get_settings_manager()
        except Exception:  # pragma: no cover - fallback to defaults
            return "model_name"

        value = manager.get("model_name_display", "model_name")
        return ModelCache._normalize_display_mode(value)

    async def on_model_name_display_changed(self, display_mode: str) -> None:
        """Handle updates to the model name display preference."""

        normalized = ModelCache._normalize_display_mode(display_mode)
        self._name_display_mode = normalized

        if self._cache is not None:
            await self._cache.update_name_display_mode(normalized)

    async def _register_service(self):
        """Register this instance with the ServiceRegistry"""
        service_name = f"{self.model_type}_scanner"
        await ServiceRegistry.register_service(service_name, self)

    def _slim_civitai_payload(self, civitai: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return a lightweight civitai payload containing only frequently used keys."""
        if not isinstance(civitai, Mapping) or not civitai:
            return None

        slim: Dict[str, Any] = {}
        for key in ('id', 'modelId', 'name'):
            value = civitai.get(key)
            if value not in (None, '', []):
                slim[key] = value

        creator = civitai.get('creator')
        if isinstance(creator, Mapping):
            username = creator.get('username')
            if username:
                slim['creator'] = {'username': username}

        trained_words = civitai.get('trainedWords')
        if trained_words:
            slim['trainedWords'] = list(trained_words) if isinstance(trained_words, list) else trained_words

        civitai_model = civitai.get('model')
        if isinstance(civitai_model, Mapping):
            model_type_value = civitai_model.get('type')
            if model_type_value not in (None, '', []):
                slim['model'] = {'type': model_type_value}

        return slim or None

    def _build_cache_entry(
        self,
        source: Union[BaseModelMetadata, Mapping[str, Any]],
        *,
        folder: Optional[str] = None,
        file_path_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Project metadata into the lightweight cache representation."""
        is_mapping = isinstance(source, Mapping)

        def get_value(key: str, default: Any = None) -> Any:
            if isinstance(source, Mapping):
                return source.get(key, default)

            sentinel = object()
            value = getattr(source, key, sentinel)
            if value is not sentinel:
                return value

            unknown = getattr(source, "_unknown_fields", None)
            if isinstance(unknown, dict) and key in unknown:
                return unknown[key]

            return default

        file_path = file_path_override or get_value('file_path', '') or ''
        normalized_path = file_path.replace('\\', '/')

        folder_value = folder if folder is not None else get_value('folder', '') or ''
        normalized_folder = folder_value.replace('\\', '/')

        tags_value = get_value('tags') or []
        if isinstance(tags_value, list):
            tags_list = list(tags_value)
        elif isinstance(tags_value, (set, tuple)):
            tags_list = list(tags_value)
        else:
            tags_list = []

        preview_url = get_value('preview_url', '') or ''
        if isinstance(preview_url, str):
            preview_url = preview_url.replace('\\', '/')
        else:
            preview_url = ''

        civitai_full = get_value('civitai')
        civitai_slim = self._slim_civitai_payload(civitai_full)
        usage_tips = get_value('usage_tips', '') or ''
        if not isinstance(usage_tips, str):
            usage_tips = str(usage_tips)
        notes = get_value('notes', '') or ''
        if not isinstance(notes, str):
            notes = str(notes)

        # AutoV3 three-state contract: absent key / None = "not checked yet",
        # "" = "checked but unavailable" (never re-read the header), else the
        # 12-char lowercase hex value. A metadata object already follows the
        # contract and is passed through unchanged; a payload dict only carries
        # an explicit checked state when the key is present.
        if is_mapping:
            if 'autov3' in source:
                entry_autov3 = source['autov3'] or ''
            else:
                entry_autov3 = None
        else:
            entry_autov3 = get_value('autov3', None)

        entry: Dict[str, Any] = {
            'file_path': normalized_path,
            # file_name is always stored WITHOUT extension (e.g. "OWSMianne_ANIMA_V1",
            # not "OWSMianne_ANIMA_V1.safetensors"). All upstream population points
            # (MetadataManager, from_civitai_info, download manager, etc.) strip the
            # extension via os.path.splitext before writing. Code consuming this field
            # should match against names that are likewise extension-free.
            'file_name': get_value('file_name', '') or '',
            'model_name': get_value('model_name', '') or '',
            'folder': normalized_folder,
            'size': int(get_value('size', 0) or 0),
            'modified': float(get_value('modified', 0.0) or 0.0),
            'sha256': (get_value('sha256', '') or '').lower(),
            'autov3': entry_autov3,
            'base_model': get_value('base_model', '') or '',
            'preview_url': preview_url,
            'preview_nsfw_level': int(get_value('preview_nsfw_level', 0) or 0),
            'from_civitai': bool(get_value('from_civitai', True)),
            'favorite': bool(get_value('favorite', False)),
            'notes': notes,
            'usage_tips': usage_tips,
            'metadata_source': get_value('metadata_source', None),
            'exclude': bool(get_value('exclude', False)),
            'db_checked': bool(get_value('db_checked', False)),
            'last_checked_at': float(get_value('last_checked_at', 0.0) or 0.0),
            'tags': tags_list,
            'civitai': civitai_slim,
            'civitai_deleted': bool(get_value('civitai_deleted', False)),
            'skip_metadata_refresh': bool(get_value('skip_metadata_refresh', False)),
            # External model source (Hugging Face / ModelScope / TensorArt).
            # `source_url` + `source_platform` are canonical; `hf_url` stays in
            # sync as a legacy alias (normalised below).  `source_model_id` /
            # `source_version_id` are the site-native identity ids version
            # grouping keys off (ModelScope; empty elsewhere).
            'source_platform': get_value('source_platform', '') or '',
            'source_url': get_value('source_url', '') or '',
            'hf_url': get_value('hf_url', '') or '',
            'source_model_id': get_value('source_model_id', '') or '',
            'source_version_id': get_value('source_version_id', '') or '',
        }
        normalize_metadata_source(entry)

        license_source: Dict[str, Any] = {}
        if isinstance(civitai_full, Mapping):
            civitai_model = civitai_full.get('model')
            if isinstance(civitai_model, Mapping):
                for key in (
                    'allowNoCredit',
                    'allowCommercialUse',
                    'allowDerivatives',
                    'allowDifferentLicense',
                ):
                    if key in civitai_model:
                        license_source[key] = civitai_model.get(key)

        for key in (
            'allowNoCredit',
            'allowCommercialUse',
            'allowDerivatives',
            'allowDifferentLicense',
        ):
            if key not in license_source:
                value = get_value(key)
                if value is not None:
                    license_source[key] = value

        _, license_flags = resolve_license_info(license_source or {})
        entry['license_flags'] = license_flags

        # Handle sub_type (new canonical field)
        sub_type = get_value('sub_type', None)
        if sub_type:
            entry['sub_type'] = sub_type
        
        # Handle hash_status for lazy hash calculation (checkpoints)
        hash_status = get_value('hash_status', 'completed')
        if hash_status:
            entry['hash_status'] = hash_status

        return entry

    def _ensure_license_flags(self, entry: Dict[str, Any]) -> None:
        """Ensure cached entries include an integer license flag bitset."""

        if not isinstance(entry, dict):
            return

        license_value = entry.get('license_flags')
        if license_value is not None:
            try:
                entry['license_flags'] = int(license_value)
            except (TypeError, ValueError):
                _, fallback_flags = resolve_license_info({})
                entry['license_flags'] = fallback_flags
            return

        license_source = {
            'allowNoCredit': entry.get('allowNoCredit'),
            'allowCommercialUse': entry.get('allowCommercialUse'),
            'allowDerivatives': entry.get('allowDerivatives'),
            'allowDifferentLicense': entry.get('allowDifferentLicense'),
        }
        civitai_full = entry.get('civitai')
        if isinstance(civitai_full, Mapping):
            civitai_model = civitai_full.get('model')
            if isinstance(civitai_model, Mapping):
                for key in (
                    'allowNoCredit',
                    'allowCommercialUse',
                    'allowDerivatives',
                    'allowDifferentLicense',
                ):
                    if key in civitai_model:
                        license_source[key] = civitai_model.get(key)

        _, license_flags = resolve_license_info(license_source)
        entry['license_flags'] = license_flags

    async def initialize_in_background(self, reconcile: bool = False) -> None:
        """Initialize cache in background using thread pool

        Args:
            reconcile: When True and a persisted snapshot is hydrated, run an
                incremental reconcile afterwards so the cache matches the
                current root configuration.
        """
        try:
            # Set initial empty cache to avoid None reference errors
            if self._cache is None:
                self._cache = ModelCache(
                    raw_data=[],
                    folders=[],
                    name_display_mode=self._name_display_mode,
                )
            
            # Set initializing flag to true
            self._is_initializing = True
            
            # Determine the page type based on model type
            page_type = self.page_type
            
            # First, try to load from cache
            await ws_manager.broadcast_init_progress({
                'stage': 'loading_cache',
                'progress': 0,
                'details': f"Loading {self.model_type} cache...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })

            cache_loaded = await self._load_persisted_cache(page_type)

            if cache_loaded:
                await asyncio.sleep(0)  # Yield control so the UI can process the cache hydration update
                await ws_manager.broadcast_init_progress({
                    'stage': 'finalizing',
                    'progress': 100,
                    'status': 'complete',
                    'details': f"Loaded {len(self._cache.raw_data)} cached {self.model_type} files from disk.",
                    'scanner_type': self.model_type,
                    'pageType': page_type
                })
                logger.info(
                    f"{self.model_type.capitalize()} cache hydrated from persisted snapshot with {len(self._cache.raw_data)} models"
                )
                if reconcile:
                    # Root configuration changed (e.g. Other Models toggles):
                    # pick up newly enabled folders and drop rows for folders
                    # that are no longer managed.
                    await self.get_cached_data(force_refresh=True)
                return

            # Persistent load failed; fall back to a full scan
            await ws_manager.broadcast_init_progress({
                'stage': 'scan_folders',
                'progress': 0,
                'details': f"Scanning {self.model_type} folders...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            # Count files in a separate thread to avoid blocking
            loop = asyncio.get_event_loop()
            total_files = await loop.run_in_executor(
                None,  # Use default thread pool
                self._count_model_files  # Run file counting in thread
            )
            
            await ws_manager.broadcast_init_progress({
                'stage': 'count_models',
                'progress': 1, # Changed from 10 to 1
                'details': f"Found {total_files} {self.model_type} files",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            start_time = time.time()
            
            # Use thread pool to execute CPU-intensive operations with progress reporting
            scan_result: Optional[CacheBuildResult] = await loop.run_in_executor(
                None,  # Use default thread pool
                self._initialize_cache_sync,  # Run synchronous version in thread
                total_files,  # Pass the total file count for progress reporting
                page_type  # Pass the page type for progress reporting
            )

            if scan_result:
                await self._apply_scan_result(scan_result)
                await self._save_persistent_cache(scan_result)
                await self._sync_download_history(scan_result.raw_data, source='scan')

            # Send final progress update
            await ws_manager.broadcast_init_progress({
                'stage': 'finalizing',
                'progress': 99, # Changed from 95 to 99
                'details': f"Finalizing {self.model_type} cache...",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
            logger.info(f"{self.model_type.capitalize()} cache initialized in {time.time() - start_time:.2f} seconds. Found {len(self._cache.raw_data)} models")
            
            # Send completion message
            await asyncio.sleep(0.5)  # Small delay to ensure final progress message is sent
            await ws_manager.broadcast_init_progress({
                'stage': 'finalizing',
                'progress': 100,
                'status': 'complete',
                'details': f"Completed! Found {len(self._cache.raw_data)} {self.model_type} files.",
                'scanner_type': self.model_type,
                'pageType': page_type
            })
            
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error initializing cache in background: {e}")
        finally:
            # Always clear the initializing flag when done
            self._is_initializing = False
    
    async def _load_persisted_cache(self, page_type: str) -> bool:
        """Attempt to hydrate the in-memory cache from the SQLite snapshot.

        The SQLite read and the per-model rebuild (entry adjustment, tag
        counting, validation/repair, hash index reconstruction) run in the
        default executor so the event loop stays responsive; only applying
        the result to shared cache state happens on the loop.
        """
        if not getattr(self, '_persistent_cache', None):
            return False

        loop = asyncio.get_event_loop()
        try:
            rebuilt = await loop.run_in_executor(
                None,
                self._rebuild_persisted_cache
            )
        except FileNotFoundError:
            return False
        except Exception as exc:
            logger.debug("%s Scanner: Could not load persisted cache: %s", self.model_type.capitalize(), exc)
            return False

        if rebuilt is None:
            return False

        scan_result, invalid_entries = rebuilt

        if invalid_entries:
            monitor = CacheHealthMonitor()
            report = monitor.check_health(scan_result.raw_data, auto_repair=True)

            if report.status != CacheHealthStatus.HEALTHY:
                # Broadcast health warning to frontend
                await ws_manager.broadcast_cache_health_warning(report, page_type)
                logger.warning(
                    f"{self.model_type.capitalize()} Scanner: Cache health issue detected - "
                    f"{report.invalid_entries} invalid entries, {report.repaired_entries} repaired"
                )

            # Rebuild tags count from valid entries only
            tags_count = {}
            for item in scan_result.raw_data:
                for tag in item.get('tags') or []:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
            scan_result.tags_count = tags_count

            # Remove invalid entries from hash index
            for invalid_entry in invalid_entries:
                file_path = CacheEntryValidator.get_file_path_safe(invalid_entry)
                sha256 = CacheEntryValidator.get_sha256_safe(invalid_entry)
                if file_path:
                    scan_result.hash_index.remove_by_path(file_path, sha256)

        await self._apply_scan_result(scan_result)
        await self._sync_download_history(scan_result.raw_data, source='scan')

        await ws_manager.broadcast_init_progress({
            'stage': 'loading_cache',
            'progress': 1,
            'details': f"Loaded cached {self.model_type} data from disk",
            'scanner_type': self.model_type,
            'pageType': page_type
        })

        # Schedule the one-time AutoV3 backfill task (at most once per process)
        # so entries loaded from a persisted snapshot that predates autov3 get
        # their checked state computed in the background. The task never blocks
        # or crashes the load path.
        if not self._autov3_backfill_scheduled:
            self._autov3_backfill_scheduled = True
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._run_autov3_backfill())

        return True

    def _rebuild_persisted_cache(self) -> Optional[Tuple[CacheBuildResult, List[Dict[str, Any]]]]:
        """Load the SQLite snapshot and rebuild a ready-to-apply scan result.

        Runs entirely in a worker thread: it must not touch ``self._cache``,
        the websocket manager, or any asyncio primitives. Returns ``None``
        when no usable snapshot exists, otherwise a tuple of the scan result
        (built from validated/repaired entries) and the invalid entries.
        """
        persisted = self._persistent_cache.load_cache(self.model_type)

        if not persisted or not persisted.raw_data:
            return None

        # Drop entries the scanner no longer manages (e.g. an other-model
        # sub_type the user just disabled) before rebuilding the indexes, so
        # hash/autov3 lookups cannot resolve to unmanaged files either.
        kept_items = [
            item
            for item in persisted.raw_data
            if self._should_keep_cached_entry(item)
        ]
        kept_paths = {
            item.get("file_path") for item in kept_items if item.get("file_path")
        }

        hash_index = ModelHashIndex()
        for sha_value, path in persisted.hash_rows:
            if sha_value and path and path in kept_paths:
                hash_index.add_entry(sha_value.lower(), path)

        # Rebuild the AutoV3 index from the persisted autov3_index rows. These
        # cover every known autov3 -> path mapping regardless of whether a
        # sha256 row also exists for the same file.
        for autov3_value, path in persisted.autov3_hash_rows:
            if autov3_value and path and path in kept_paths:
                hash_index.add_autov3(autov3_value.lower(), path)

        tags_count: Dict[str, int] = {}
        adjusted_raw_data: List[Dict[str, Any]] = []
        for item in kept_items:
            # load_cache builds a fresh dict per row, and validate_batch below
            # works on its own per-entry copy when auto_repair=True, so no
            # additional dict copy is needed here.
            adjusted_item = self.adjust_cached_entry(item)
            adjusted_raw_data.append(adjusted_item)

            for tag in adjusted_item.get('tags') or []:
                tags_count[tag] = tags_count.get(tag, 0) + 1

        # Validate cache entries and check health.
        # Always use the validated/repaired entries — even when there are no
        # invalid entries, auto_repair may have filled in missing optional
        # fields (model_name, file_name, folder) with safe defaults on a copied
        # working_entry.  Without this unconditional replacement the repaired
        # copies are discarded and None values propagate to format_response.
        # See issue #730.
        valid_entries, invalid_entries = CacheEntryValidator.validate_batch(
            adjusted_raw_data, auto_repair=True
        )

        # Always use the validated entries (repaired copies)
        scan_result = CacheBuildResult(
            raw_data=valid_entries,
            hash_index=hash_index,
            tags_count=tags_count,
            excluded_models=list(persisted.excluded_models),
            all_folders=list(persisted.all_folders) if persisted.all_folders is not None else None,
        )
        return scan_result, invalid_entries

    async def _run_autov3_backfill(self) -> None:
        """Backfill autov3 for entries loaded from the persisted cache that lack it."""
        try:
            from ..services.autov3_backfill_service import Autov3BackfillService  # lazy import (module created by another unit)
            await Autov3BackfillService.get_instance().backfill(self)
        except Exception as exc:
            logger.warning("AutoV3 backfill failed: %s", exc)

    async def _save_persistent_cache(self, scan_result: CacheBuildResult, *, force: bool = False) -> None:
        if not scan_result or not getattr(self, '_persistent_cache', None):
            return

        if self.is_cancelled() and not force:
            logger.info(
                f"{self.model_type.capitalize()} Scanner: Skipping _save_persistent_cache "
                "after cancellation"
            )
            return

        hash_snapshot = self._build_hash_index_snapshot(scan_result.hash_index)
        autov3_snapshot = self._build_autov3_index_snapshot(scan_result.hash_index)
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self._persistent_cache.save_cache,
                self.model_type,
                list(scan_result.raw_data),
                hash_snapshot,
                list(scan_result.excluded_models),
                autov3_snapshot,
                scan_result.all_folders,
            )
        except Exception as exc:
            logger.warning("%s Scanner: Failed to persist cache: %s", self.model_type.capitalize(), exc)

    def _build_hash_index_snapshot(self, hash_index: Optional[ModelHashIndex]) -> Dict[str, List[str]]:
        snapshot: Dict[str, List[str]] = {}
        if not hash_index:
            return snapshot

        for sha_value, path in getattr(hash_index, '_hash_to_path', {}).items():
            if not sha_value or not path:
                continue
            bucket = snapshot.setdefault(sha_value.lower(), [])
            if path not in bucket:
                bucket.append(path)

        for sha_value, paths in getattr(hash_index, '_duplicate_hashes', {}).items():
            if not sha_value:
                continue
            bucket = snapshot.setdefault(sha_value.lower(), [])
            for path in paths:
                if path and path not in bucket:
                    bucket.append(path)
        return snapshot

    def _build_autov3_index_snapshot(self, hash_index: Optional[ModelHashIndex]) -> Dict[str, List[str]]:
        """Build the autov3 -> [paths] snapshot for the persisted cache."""
        snapshot: Dict[str, List[str]] = {}
        if not hash_index:
            return snapshot

        for autov3_value, path in hash_index.get_all_autov3().items():
            if not autov3_value or not path:
                continue
            bucket = snapshot.setdefault(autov3_value.lower(), [])
            if path not in bucket:
                bucket.append(path)
        return snapshot

    async def _persist_current_cache(self, *, force: bool = False) -> None:
        if self._cache is None or not getattr(self, '_persistent_cache', None):
            return

        snapshot = CacheBuildResult(
            raw_data=list(self._cache.raw_data),
            hash_index=self._hash_index,
            tags_count=dict(self._tags_count),
            excluded_models=list(self._excluded_models),
            all_folders=(
                list(self._cache.all_folders)
                if self._cache.all_folders is not None
                else None
            ),
        )
        await self._save_persistent_cache(snapshot, force=force)
        await self._sync_download_history(snapshot.raw_data, source='scan')
    def _count_model_files(self) -> int:
        """Count all model files with supported extensions in all roots
        
        Returns:
            int: Total number of model files found
        """
        total_files = 0
        visited_real_paths = set()
        
        for root_path in self.get_model_roots():
            if not os.path.exists(root_path):
                continue
                
            def count_recursive(path):
                nonlocal total_files
                try:
                    real_path = os.path.realpath(path)
                    if real_path in visited_real_paths:
                        return
                    visited_real_paths.add(real_path)
                    
                    with os.scandir(path) as it:
                        for entry in it:
                            try:
                                if entry.is_file(follow_symlinks=True):
                                    ext = os.path.splitext(entry.name)[1].lower()
                                    if ext in self.file_extensions:
                                        total_files += 1
                                elif entry.is_dir(follow_symlinks=True):
                                    if _is_excluded_dir(entry.name):
                                        continue
                                    count_recursive(entry.path)
                            except Exception as e:
                                logger.error(f"Error counting files in entry {entry.path}: {e}")
                except Exception as e:
                    logger.error(f"Error counting files in {path}: {e}")
            
            count_recursive(root_path)
        
        return total_files
    
    def _initialize_cache_sync(self, total_files: int = 0, page_type: str = 'loras') -> Optional[CacheBuildResult]:
        """Synchronous version of cache initialization for thread pool execution"""

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)

            last_progress_time = time.time()
            last_progress_percent = 0

            async def progress_callback(processed_files: int, expected_total: int, current_name: str = '') -> None:
                nonlocal last_progress_time, last_progress_percent

                if expected_total <= 0:
                    return

                current_time = time.time()
                progress_percent = min(99, int(1 + (processed_files / expected_total) * 98))

                if progress_percent <= last_progress_percent:
                    return

                if current_time - last_progress_time <= 0.5 and processed_files != expected_total:
                    return

                last_progress_percent = progress_percent
                last_progress_time = current_time

                await ws_manager.broadcast_init_progress({
                    'stage': 'process_models',
                    'progress': progress_percent,
                    'details': f"Processing {self.model_type} files: {processed_files}/{expected_total}",
                    'scanner_type': self.model_type,
                    'pageType': page_type
                })

            return loop.run_until_complete(
                self._gather_model_data(
                    total_files=total_files,
                    progress_callback=progress_callback
                )
            )
        except Exception as e:
            logger.error(f"Error in thread-based {self.model_type} cache initialization: {e}")
            return None
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    async def get_cached_data(
        self,
        force_refresh: bool = False,
        rebuild_cache: bool = False,
        scope: Optional[ReconcileScope] = None,
    ) -> ModelCache:
        """Get cached model data, refresh if needed
        
        Args:
            force_refresh: Whether to refresh the cache
            rebuild_cache: Whether to completely rebuild the cache
            scope: Restrict an incremental reconcile to some roots / a folder
                (ignored by a full rebuild, which always walks everything)
        """
        # If cache is not initialized, return an empty cache
        # Actual initialization should be done via initialize_in_background
        if self._cache is None and not force_refresh:
            return ModelCache(
                raw_data=[],
                folders=[],
                name_display_mode=self._name_display_mode,
            )

        # If force refresh is requested, initialize the cache directly
        if force_refresh:
            if rebuild_cache:
                self._last_reconcile_summary = None
                await self._initialize_cache()
            else:
                self._last_reconcile_summary = await self._reconcile_cache(scope=scope)
        
        return cast(ModelCache, self._cache)

    @property
    def last_reconcile_summary(self) -> Optional[Dict[str, Any]]:
        """Summary of the most recent incremental reconcile (None otherwise).

        Carries the counts the refresh toast reports (added / removed /
        repaired) plus the scan scope and the paths that were left untouched
        because they were unreachable.
        """
        return self._last_reconcile_summary

    def describe_model_roots(self) -> List[Dict[str, Any]]:
        """Describe the configured roots for the refresh scope menu.

        ``models`` is the cached entry count per root (the same attribution the
        walk-progress weights use) and ``reachable`` is a live filesystem check,
        so a switched-off drive shows as offline without touching the cache.
        """
        roots: List[str] = []
        seen: Set[str] = set()
        for root in self.get_model_roots():
            if not root or root in seen:
                continue
            seen.add(root)
            roots.append(root)

        labels = _root_display_labels(roots)
        cached_paths = (
            {item.get('file_path', '') for item in self._cache.raw_data}
            if self._cache is not None
            else set()
        )
        counts = _count_cached_entries_per_root(cached_paths, roots)
        return [
            {
                'path': root.replace(os.sep, '/'),
                'label': labels[root],
                'reachable': os.path.exists(root),
                'models': counts.get(root, 0),
            }
            for root in roots
        ]

    async def _initialize_cache(self) -> None:
        """Initialize or refresh the cache"""
        self._is_initializing = True  # Set flag
        last_progress_percent = 0
        try:
            start_time = time.time()

            await self._broadcast_scan_progress('started', 'scan_folders', 0, True)

            # Manually trigger a symlink rescan during a full rebuild.
            # This ensures that any new symlink mappings are correctly picked up.
            config.rebuild_symlink_cache()

            # Count files in a thread so the event loop stays responsive
            loop = asyncio.get_running_loop()
            total_files = await loop.run_in_executor(None, self._count_model_files)
            await self._broadcast_scan_progress(
                'processing', 'count_models', 1, True,
                processed=0, total=total_files,
            )

            last_progress_time = time.time()

            async def progress_callback(processed_files: int, expected_total: int, current_name: str = '') -> None:
                nonlocal last_progress_time, last_progress_percent

                if expected_total <= 0:
                    return

                current_time = time.time()
                progress_percent = min(99, int(1 + (processed_files / expected_total) * 98))

                if progress_percent <= last_progress_percent:
                    return

                if current_time - last_progress_time <= 0.5 and processed_files != expected_total:
                    return

                last_progress_percent = progress_percent
                last_progress_time = current_time

                await self._broadcast_scan_progress(
                    'processing', 'process_models', progress_percent, True,
                    processed=processed_files, total=expected_total,
                    current_name=current_name,
                )

            # Scan for new data
            scan_result = await self._gather_model_data(
                total_files=total_files,
                progress_callback=progress_callback,
            )
            if not self.is_cancelled():
                await self._broadcast_scan_progress('finalizing', 'finalizing', 99, True)
                await self._apply_scan_result(scan_result)
                await self._save_persistent_cache(scan_result)
                await self._sync_download_history(scan_result.raw_data, source='scan')
                await self._broadcast_scan_progress(
                    'completed', 'finalizing', 100, True,
                    elapsed_seconds=time.time() - start_time,
                )

                logger.info(
                    f"{self.model_type.capitalize()} Scanner: Cache initialization completed in {time.time() - start_time:.2f} seconds, "
                    f"found {len(scan_result.raw_data)} models"
                )
            else:
                await self._broadcast_scan_progress(
                    'cancelled', 'process_models', last_progress_percent, True,
                    elapsed_seconds=time.time() - start_time,
                )
                logger.info(
                    f"{self.model_type.capitalize()} Scanner: Cache initialization cancelled "
                    f"after {time.time() - start_time:.2f} seconds"
                )
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error initializing cache: {e}")
            await self._broadcast_scan_progress(
                'error', 'process_models', last_progress_percent, True,
                error=str(e),
            )
            # Ensure cache is at least an empty structure on error
            if self._cache is None:
                self._cache = ModelCache(
                    raw_data=[],
                    folders=[],
                    name_display_mode=self._name_display_mode,
                )
        finally:
            self._is_initializing = False # Unset flag

    async def _reconcile_cache(self, scope: Optional[ReconcileScope] = None) -> Optional[Dict[str, Any]]:
        """Fast cache reconciliation - only process differences between cache and filesystem.

        ``scope`` restricts the reconcile to some of the configured roots and/or
        a folder inside them: entries outside the scope are neither re-read nor
        removed, so scanning one drive can never touch another. Paths the walk
        could not read are kept and reported instead of being treated as
        deleted. Returns a summary of the run (also broadcast to the UI).
        """
        self.reset_cancellation()
        self._is_initializing = True # Set flag for reconciliation duration
        try:
            start_time = time.time()
            logger.info(f"{self.model_type.capitalize()} Scanner: Starting fast cache reconciliation...")

            await self._broadcast_scan_progress('started', 'reconcile_scan', 0, False)
            
            # Get current cached file paths
            cached_size_before = len(self._cache.raw_data)
            cached_paths = {item['file_path'] for item in self._cache.raw_data}
            path_to_item = {item['file_path']: item for item in self._cache.raw_data}

            # Snapshot the configured roots once for this phase: scope
            # resolution, reachability, symlink relevance and the new-file pass
            # all read from this list.
            configured_roots: List[str] = []
            seen_roots: Set[str] = set()
            for root_path in self.get_model_roots():
                if not root_path or root_path in seen_roots:
                    continue
                seen_roots.add(root_path)
                configured_roots.append(root_path)

            all_labels = _root_display_labels(configured_roots)
            scope_roots = [
                root for root in configured_roots
                if scope is None or scope.roots is None or root in scope.roots
            ]
            scope_folder = scope.folder if scope is not None else None

            # A configured root that is not reachable (drive switched off,
            # unmounted share) is skipped instead of being treated as deleted.
            unreachable = _UnreachablePaths()
            roots: List[str] = []
            skipped_roots: List[Dict[str, Any]] = []
            for root_path in scope_roots:
                if not os.path.exists(root_path):
                    unreachable.add(root_path, 'root_unreachable')
                    skipped_roots.append({
                        'path': root_path.replace(os.sep, '/'),
                        'label': all_labels.get(root_path, root_path),
                        'reason': 'root_unreachable',
                    })
                    continue
                roots.append(root_path)

            self._collect_offline_symlink_prefixes(roots, unreachable)

            # Scope prefixes come from every root the caller asked for (even the
            # unreachable ones) so their entries are recognised as "in scope but
            # unreadable" and reported instead of silently disappearing.
            scope_prefixes = [
                (root, _scope_prefix(root, scope_folder)) for root in scope_roots
            ]
            walk_prefixes = [
                (root, _scope_prefix(root, scope_folder)) for root in roots
            ]

            # Roots on different devices are walked by parallel workers (a cold
            # or slow drive then no longer serializes the others); roots sharing
            # a device stay sequential so directory claims remain deterministic.
            tracker = _ReconcileWalkTracker(
                roots,
                _count_cached_entries_for_prefixes(cached_paths, walk_prefixes),
                labels={root: all_labels.get(root, root) for root in roots},
            )
            walk_results = await self._walk_roots_for_reconcile(
                roots=roots,
                walk_targets={
                    root: _scope_walk_path(root, scope_folder) for root in roots
                },
                tracker=tracker,
                cached_paths=cached_paths,
                path_to_item=path_to_item,
                unreachable=unreachable,
            )

            # Final walk snapshot: the bar reaches the walk share, then the
            # new-file pass continues from there.
            await self._broadcast_walk_progress(tracker)

            if self.is_cancelled():
                logger.info(f"{self.model_type.capitalize()} Scanner: Reconcile scan cancelled")
                await self._broadcast_scan_progress(
                    'cancelled', 'reconcile_scan', 0, False,
                    elapsed_seconds=time.time() - start_time,
                )
                return

            # Merge the per-root results in configured root order: which
            # business path wins a file reachable through several roots (and
            # which cached entry counts as found) must not depend on the order
            # the workers happened to finish in.
            found_paths: Set[str] = set()
            discovered_folders: Set[str] = set()
            # Cached entries whose stored file_name no longer matches the file
            # on disk (e.g. dotted stems truncated by the legacy .civitai_info
            # migration, issue #1112). Repaired in place after the walk; the
            # list stays empty on a clean library, so a no-change reconcile
            # only pays one string compare per cached file.
            stale_paths: List[str] = []
            stale_seen: Set[str] = set()
            new_files: List[str] = []
            discovered_real_files: Set[str] = set()

            for result in walk_results:
                found_paths |= result.found_paths
                discovered_folders |= result.discovered_folders
                for cached_path in result.stale_paths:
                    if cached_path in stale_seen:
                        continue
                    stale_seen.add(cached_path)
                    stale_paths.append(cached_path)

            for result in walk_results:
                for file_path, real_file_path in result.new_candidates:
                    if real_file_path in discovered_real_files:
                        continue
                    discovered_real_files.add(real_file_path)
                    # This is a new file to process
                    new_files.append(file_path)

            # Process new files in batches
            total_added = 0
            if new_files:
                logger.info(f"{self.model_type.capitalize()} Scanner: Found {len(new_files)} new files to process")
                batch_size = 50
                total_new = len(new_files)
                processed_new = 0
                last_progress_time = time.time()
                # Snapshot the roots once: this matches the walk above (which
                # also snapshots them) and avoids a config read per new file.
                model_roots = self.get_model_roots()
                for i in range(0, total_new, batch_size):
                    batch = new_files[i:i+batch_size]
                    for path in batch:
                        logger.info(f"{self.model_type.capitalize()} Scanner: Processing {path}")
                        processed_new += 1
                        try:
                            # Find the appropriate root path for this file
                            root_path = None
                            normalized_path = os.path.normpath(path)
                            for potential_root in model_roots:
                                # Normalize both paths for comparison
                                if normalized_path.startswith(os.path.normpath(potential_root)):
                                    root_path = potential_root
                                    break
                            
                            if root_path:
                                model_data = await self._process_model_file(path, root_path)
                                if model_data:
                                    model_data = self.adjust_cached_entry(dict(model_data))
                                    if not model_data:
                                        continue

                                    # Validate the new entry before adding
                                    validation_result = CacheEntryValidator.validate(
                                        model_data, auto_repair=True
                                    )
                                    if not validation_result.is_valid:
                                        logger.warning(
                                            f"Skipping invalid entry during reconcile: {path}"
                                        )
                                        continue
                                    model_data = validation_result.entry
                                    if model_data is None:
                                        continue

                                    self._ensure_license_flags(model_data)
                                    # Add to cache
                                    self._cache.raw_data.append(model_data)
                                    self._cache.add_to_version_index(model_data)

                                    # Update hash index if available
                                    if 'sha256' in model_data and 'file_path' in model_data:
                                        self._hash_index.add_entry(
                                            model_data['sha256'].lower(),
                                            model_data['file_path'],
                                            model_data.get('autov3') or None
                                        )
                                    
                                    # Update tags count
                                    if 'tags' in model_data and model_data['tags']:
                                        for tag in model_data['tags']:
                                            self._tags_count[tag] = self._tags_count.get(tag, 0) + 1
                                            
                                    total_added += 1
                            else:
                                logger.error(f"Could not determine root path for {path}")
                        except Exception as e:
                            logger.error(f"Error adding {path} to cache: {e}")

                        current_time = time.time()
                        if current_time - last_progress_time > 0.5 or processed_new == total_new:
                            last_progress_time = current_time
                            await self._broadcast_scan_progress(
                                'processing', 'process_new',
                                _new_file_pass_progress(processed_new, total_new), False,
                                processed=processed_new, total=total_new,
                                current_name=os.path.basename(path),
                            )

                        if self.is_cancelled():
                            logger.info(f"{self.model_type.capitalize()} Scanner: Reconcile processing cancelled")
                            await self._broadcast_scan_progress(
                                'cancelled', 'process_new',
                                _new_file_pass_progress(processed_new, total_new), False,
                                elapsed_seconds=time.time() - start_time,
                            )
                            return

            # Repair rows whose file_name drifted from the file on disk. Only
            # mismatching entries are re-read here, so a clean library never
            # touches metadata during a refresh. Each repair goes through the
            # single-row update path: load_metadata() normalizes the sidecar
            # (MetadataManager._normalize_metadata_paths) and
            # _sync_cache_from_metadata_impl() rewrites one targeted SQL delta
            # instead of a full cache save, and the mismatch is gone
            # afterwards, so the work never repeats (issue #1112).
            total_repaired = 0
            if stale_paths:
                logger.info(
                    "%s Scanner: Repairing %d cached entries whose file_name no longer matches the file on disk",
                    self.model_type.capitalize(),
                    len(stale_paths),
                )
                for path in stale_paths:
                    if self.is_cancelled():
                        logger.info(f"{self.model_type.capitalize()} Scanner: Reconcile repair cancelled")
                        break
                    try:
                        metadata, _should_skip = await MetadataManager.load_metadata(
                            path, self.model_class
                        )
                        if metadata is None:
                            # Missing or corrupt sidecar: keep the existing row
                            # so a full rebuild can recreate the metadata from
                            # .civitai.info (or defaults) without losing cached
                            # fields such as tags or civitai data.
                            logger.debug(
                                "%s Scanner: Leaving %s unchanged (no usable metadata to repair from)",
                                self.model_type.capitalize(),
                                path,
                            )
                            continue

                        payload = metadata.to_dict()
                        unknown_fields = getattr(metadata, "_unknown_fields", None)
                        if isinstance(unknown_fields, dict):
                            payload.update(unknown_fields)

                        if await self._sync_cache_from_metadata_impl(path, payload):
                            total_repaired += 1
                    except Exception as exc:
                        logger.warning(
                            "%s Scanner: Failed to repair file_name for %s: %s",
                            self.model_type.capitalize(),
                            path,
                            exc,
                        )

            # Find missing files (in cache but not in filesystem). Only paths
            # inside this scan's scope are candidates, and paths the walk could
            # not read are kept and reported instead of being removed.
            missing_files: Set[str] = set()
            for path in cached_paths - found_paths:
                if not any(
                    _path_matches_prefix(path, prefix)
                    for _root, prefix in scope_prefixes
                ):
                    continue
                unreachable_prefix = unreachable.match(path)
                if unreachable_prefix is not None:
                    unreachable.record_kept(unreachable_prefix)
                    continue
                missing_files.add(path)
            total_removed = 0
            
            if missing_files:
                logger.info(f"{self.model_type.capitalize()} Scanner: Found {len(missing_files)} files to remove from cache")
                
                # Process files to remove
                for path in missing_files:
                    try:
                        model_to_remove = path_to_item[path]

                        self._cache.remove_from_version_index(model_to_remove)

                        # Update tags count
                        for tag in model_to_remove.get('tags', []):
                            if tag in self._tags_count:
                                self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                                if self._tags_count[tag] == 0:
                                    del self._tags_count[tag]
                        
                        # Remove from hash index
                        self._hash_index.remove_by_path(path)
                        total_removed += 1
                    except Exception as e:
                        logger.error(f"Error removing {path} from cache: {e}")
                
                # Update cache data
                self._cache.raw_data = [item for item in self._cache.raw_data if item['file_path'] not in missing_files]
            
            # Defensive integrity pass: drop entries sharing a business path.
            # Duplicates can only be introduced by external code rewriting
            # raw_data directly or by this pass's own appends, so an unchanged
            # filesystem walk over a clean cache has nothing to clean. The size
            # mismatch is an O(1) tell that the snapshot already contained
            # duplicates; skipping the O(N) pass when it is provably clean is
            # what keeps a no-change Refresh cheap.
            if cached_size_before != len(cached_paths) or total_added > 0:
                dedup_removed = 0
                seen_paths: set[str] = set()
                deduped: list[Dict[str, Any]] = []
                for item in reversed(self._cache.raw_data):
                    path = item.get('file_path', '')
                    if path not in seen_paths:
                        seen_paths.add(path)
                        deduped.append(item)
                    else:
                        for tag in item.get('tags', []):
                            if tag in self._tags_count:
                                self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                                if self._tags_count[tag] == 0:
                                    del self._tags_count[tag]
                        dedup_removed += 1
                if dedup_removed > 0:
                    self._cache.raw_data = list(reversed(deduped))
                    total_removed += dedup_removed
            
            # The walk above visited every directory *in scope*, so refresh the
            # recorded folder list (including empty folders) when nothing was
            # left unverified — e.g. an empty folder was created or removed
            # externally. A scoped scan, or one with unreadable paths, can only
            # add to the list: dropping folders this walk never looked at would
            # empty the sidebar for every drive that was not scanned.
            sorted_discovered = sorted(discovered_folders, key=lambda x: x.lower())
            fully_verified = (
                len(roots) == len(configured_roots)
                and scope_folder is None
                and not unreachable.has_entries()
            )
            if fully_verified:
                merged_folders = sorted_discovered
            else:
                merged_folders = sorted(
                    set(self._cache.all_folders or []) | set(sorted_discovered),
                    key=lambda x: x.lower(),
                )
            folders_changed = self._cache.all_folders != merged_folders
            if folders_changed:
                self._cache.all_folders = merged_folders

            # Resort cache if changes were made
            if total_added > 0 or total_removed > 0:
                # Update folders list
                all_folders = set(item.get('folder', '') for item in self._cache.raw_data)
                self._cache.folders = sorted(list(all_folders), key=lambda x: x.lower())

                self._cache.rebuild_version_index()

                # Resort cache
                await self._cache.resort()

                await self._persist_current_cache()
            elif folders_changed:
                await self._persist_current_cache()
                
            summary: Dict[str, Any] = {
                'added': total_added,
                'removed': total_removed,
                'repaired': total_repaired,
                'scanned_roots': [all_labels.get(root, root) for root in roots],
                # A folder scope is named by the folder the user clicked, not by
                # the roots it happens to live under.
                'scope_label': scope_folder or '',
                'skipped_roots': skipped_roots,
                'unavailable_paths': unreachable.payload(),
                'unavailable_paths_total': unreachable.count(),
                'kept_unreachable': unreachable.total_kept(),
            }
            logger.info(
                f"{self.model_type.capitalize()} Scanner: Cache reconciliation completed in "
                f"{time.time() - start_time:.2f} seconds. Added {total_added}, "
                f"removed {total_removed}, repaired {total_repaired} models."
                + (
                    f" Skipped {len(skipped_roots)} unreachable root(s), kept "
                    f"{summary['kept_unreachable']} model(s) under unreadable paths."
                    if skipped_roots or unreachable.has_entries()
                    else ""
                )
            )
            await self._broadcast_scan_progress(
                'completed', 'process_new', 100, False,
                elapsed_seconds=time.time() - start_time,
                **summary,
            )
            return summary
        except Exception as e:
            logger.error(f"{self.model_type.capitalize()} Scanner: Error reconciling cache: {e}", exc_info=True)
            await self._broadcast_scan_progress(
                'error', 'reconcile_scan', 0, False,
                error=str(e),
            )
        finally:
            self._is_initializing = False # Unset flag
            self.bump_cache_version()

    async def _walk_roots_for_reconcile(
        self,
        *,
        roots: List[str],
        walk_targets: Mapping[str, str],
        tracker: _ReconcileWalkTracker,
        cached_paths: Set[str],
        path_to_item: Mapping[str, Dict[str, Any]],
        unreachable: _UnreachablePaths,
    ) -> List[_RootWalkResult]:
        """Walk every root off the event loop and return results in root order.

        One worker per device: cold or slow drives no longer serialize the
        others, and the event loop stays free for the whole walk (previously it
        was re-entered once per directory). Results are re-ordered to the
        configured root order so the merge below is deterministic.
        """
        if not roots:
            return []

        lookups = _CachedPathLookups(cached_paths)
        dir_claims = _RealDirClaims()
        excluded_models = set(self._excluded_models)
        loop = asyncio.get_running_loop()

        monitor = asyncio.create_task(self._monitor_walk_progress(tracker))
        try:
            futures = [
                loop.run_in_executor(
                    None,
                    self._walk_root_group_sync,
                    group,
                    tracker,
                    lookups,
                    dir_claims,
                    excluded_models,
                    path_to_item,
                    walk_targets,
                    unreachable,
                )
                for group in _group_roots_by_device(roots)
            ]
            outcomes = await asyncio.gather(*futures, return_exceptions=True)
        finally:
            monitor.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await monitor

        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome

        by_root: Dict[str, _RootWalkResult] = {}
        for outcome in outcomes:
            for result in cast(List[_RootWalkResult], outcome):
                by_root[result.root_path] = result
        return [by_root[root] for root in roots if root in by_root]

    def _walk_root_group_sync(
        self,
        roots: List[str],
        tracker: _ReconcileWalkTracker,
        lookups: _CachedPathLookups,
        dir_claims: _RealDirClaims,
        excluded_models: Set[str],
        path_to_item: Mapping[str, Dict[str, Any]],
        walk_targets: Mapping[str, str],
        unreachable: _UnreachablePaths,
    ) -> List[_RootWalkResult]:
        """Walk the roots of one device sequentially (worker-thread entry point)."""
        results: List[_RootWalkResult] = []
        for root_path in roots:
            if self.is_cancelled():
                break

            tracker.start_root(root_path)

            def report_progress(files_seen: int, _root: str = root_path) -> None:
                tracker.report(_root, files_seen)

            try:
                result = _walk_root_for_reconcile(
                    root_path=root_path,
                    walk_path=walk_targets.get(root_path, root_path),
                    file_extensions=self.file_extensions,
                    cached_paths=lookups.cached_paths,
                    path_to_item=path_to_item,
                    lookups=lookups,
                    dir_claims=dir_claims,
                    excluded_models=excluded_models,
                    is_cancelled=self.is_cancelled,
                    report_progress=report_progress,
                    unreachable=unreachable,
                )
            finally:
                tracker.finish_root(root_path)

            results.append(result)
            if result.cancelled:
                break
        return results

    def _collect_offline_symlink_prefixes(
        self, roots: Sequence[str], unreachable: _UnreachablePaths
    ) -> None:
        """Flag known first-level symlinks whose target is not a directory.

        ``config`` deliberately tracks only symlinks directly under a root (see
        ``Config._scan_symbolic_links``), so this costs one ``isdir`` per known
        mapping and covers "the linked drive is switched off" for the layouts the
        scanner already knows about. Nested symlinks stay out of scope.
        """
        try:
            mappings = config.iter_path_mappings()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "%s Scanner: symlink map unavailable: %s",
                self.model_type.capitalize(),
                exc,
            )
            return
        if not mappings or not roots:
            return

        root_prefixes = [_normalized_root_prefix(root) for root in roots]
        for target, link in mappings:
            link_prefix = _normalized_root_prefix(link)
            if not any(
                link_prefix == root_prefix
                or _path_matches_prefix(link_prefix, root_prefix)
                for root_prefix in root_prefixes
            ):
                continue
            if os.path.isdir(target):
                continue
            unreachable.add(link, 'symlink_target_offline')

    async def _monitor_walk_progress(self, tracker: _ReconcileWalkTracker) -> None:
        """Broadcast walk progress while the root workers are running."""
        while True:
            await asyncio.sleep(_WALK_PROGRESS_INTERVAL_SECONDS)
            await self._broadcast_walk_progress(tracker)

    async def _broadcast_walk_progress(self, tracker: _ReconcileWalkTracker) -> None:
        """Emit one walk-phase progress message (best effort)."""
        snapshot = tracker.snapshot()
        if not snapshot:
            return
        progress = int(snapshot.pop('progress', 0))
        await self._broadcast_scan_progress(
            'processing', 'reconcile_scan', progress, False, **snapshot
        )

    def is_initializing(self) -> bool:
        """Check if the scanner is currently initializing"""
        return self._is_initializing
    
    def cancel_task(self) -> None:
        """Request cancellation of the current long-running task."""
        self._cancel_requested = True
        logger.info(f"{self.model_type.capitalize()} Scanner: Cancellation requested")

    def reset_cancellation(self) -> None:
        """Reset the cancellation flag."""
        self._cancel_requested = False

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel_requested
    
    def get_model_roots(self) -> List[str]:
        """Get model root directories"""
        raise NotImplementedError("Subclasses must implement get_model_roots")

    async def get_all_folders(self) -> List[str]:
        """Return every known directory under the model roots.

        The directory list (including empty ones) is recorded during cache
        scans and hydrated from the persisted snapshot, so this is a pure
        in-memory read — no filesystem walk ever runs on the event loop
        (walking network roots synchronously used to freeze the whole
        server, see issue #1110). The result is unioned with the
        model-derived folders so it is always a superset of
        ``cache.folders``.

        Cold fallback: when the cache was hydrated from a persisted snapshot
        that predates folder recording (``all_folders is None``), a one-shot
        background walk is scheduled off the event loop to backfill and
        persist the list; until it lands, the models-only folders are
        returned.
        """
        folders: Set[str] = set()
        cache = self._cache
        if cache is not None:
            folders |= {item.get('folder', '') for item in cache.raw_data}
            recorded = getattr(cache, 'all_folders', None)
            if recorded is None:
                self._schedule_all_folders_backfill()
            else:
                folders |= set(recorded)
        else:
            self._schedule_all_folders_backfill()

        return sorted(folders, key=lambda x: x.lower())

    async def add_known_folder(self, folder: str) -> None:
        """Record a folder (and its parents) in the known folder list.

        Called when a directory is created between scans (e.g. via the
        create-folder API) so folder trees reflect it immediately without
        waiting for the next reconciliation. When ``all_folders`` has not
        been recorded yet (legacy snapshot), this is a no-op — the scheduled
        backfill walk discovers the directory from disk instead.
        """
        normalized = folder.replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part]
        if not parts:
            return
        cache = self._cache
        if cache is None:
            return
        recorded = getattr(cache, "all_folders", None)
        if recorded is None:
            return
        known = set(recorded)
        for i in range(1, len(parts) + 1):
            known.add("/".join(parts[:i]))
        updated = sorted(known, key=lambda x: x.lower())
        if updated != list(recorded):
            cache.all_folders = updated
            await self._persist_current_cache()
            self.bump_cache_version()

    async def remove_known_folder(
        self, folder: str, absolute_path: Optional[str] = None
    ) -> None:
        """Forget a folder (and its subtree) that no longer exists on disk.

        Counterpart of :meth:`add_known_folder`, called after a directory is
        removed between scans (e.g. via the delete-folder API) so folder trees
        and the move/download destination pickers stop offering it without a
        full rescan. Ancestors are kept on purpose: every recorded ancestor
        exists on disk in its own right, so only the removed subtree is dropped.

        The recorded folder list is a *union over the model roots*, so an entry
        is dropped only when no root still holds that directory: deleting
        ``<rootA>/test`` must not hide a ``test`` that ``<rootB>`` still has,
        which made the node vanish on the next tree load and reappear after the
        next scan. The cache purge is keyed on the removed directory's absolute
        path when the caller knows it (``absolute_path``); without that, a
        folder deleted in one root would evict the model cards of its
        same-named twin in another root.

        When ``all_folders`` has not been recorded yet (legacy snapshot) only
        the cache purge runs — the scheduled backfill walk rebuilds the folder
        list from disk.
        """
        normalized = folder.replace("\\", "/").strip("/")
        if not normalized:
            return
        cache = self._cache
        if cache is None:
            return

        prefix = f"{normalized}/"

        folders_changed = False
        recorded = getattr(cache, "all_folders", None)
        if recorded is not None:
            removed = [
                entry
                for entry in recorded
                if entry == normalized or entry.startswith(prefix)
            ]
            still_present = await self._folders_present_on_disk(removed)
            updated = [
                entry
                for entry in recorded
                if entry in still_present
                or (entry != normalized and not entry.startswith(prefix))
            ]
            if updated != list(recorded):
                cache.all_folders = updated
                folders_changed = True

        stale_paths = self._folder_cache_purge_paths(cache, normalized, absolute_path)
        if stale_paths:
            # The purge persists the cache — including the already updated
            # all_folders list — and bumps the version itself.
            await self._batch_update_cache_for_deleted_models(stale_paths)
            folders = set(item.get("folder", "") for item in cache.raw_data)
            cache.folders = sorted(folders, key=lambda x: x.lower())
        elif folders_changed:
            await self._persist_current_cache()

        self.bump_cache_version()

    def _folder_cache_purge_paths(
        self, cache: "ModelCache", normalized: str, absolute_path: Optional[str]
    ) -> List[str]:
        """Cache entries that removing *normalized* invalidates.

        With an absolute path the purge is exact: only models that lived inside
        the removed directory. Without one (legacy caller) the relative folder is
        the only handle available, which over-purges same-named folders in other
        roots and is therefore a fallback rather than the norm.
        """
        if absolute_path:
            prefix = f"{str(absolute_path).replace(chr(92), '/').rstrip('/')}/"
            return [
                item.get("file_path")
                for item in (cache.raw_data or [])
                if str(item.get("file_path", "")).replace(chr(92), "/").startswith(prefix)
            ]

        return [
            item.get("file_path")
            for item in (cache.raw_data or [])
            if self._folder_within(item.get("folder", ""), normalized)
        ]

    async def _folders_present_on_disk(self, folders: Sequence[str]) -> Set[str]:
        """Subset of *folders* that at least one model root still holds.

        Folder records are relative, so "does this folder still exist?" is a
        question about every root at once. The check is stat-only and runs off
        the event loop because model roots can live on slow network shares.
        Stand-in scanners without roots report nothing, which preserves the
        caller's previous behaviour.
        """
        candidates = [folder for folder in folders if folder]
        if not candidates:
            return set()

        try:
            roots = self.get_model_roots()
        except NotImplementedError:
            return set()
        if not roots:
            return set()

        return await asyncio.to_thread(self._folders_present_sync, candidates, roots)

    @staticmethod
    def _folders_present_sync(folders: Sequence[str], roots: Sequence[str]) -> Set[str]:
        present: Set[str] = set()
        for folder in folders:
            for root in roots:
                if os.path.isdir(os.path.join(root, folder)):
                    present.add(folder)
                    break
        return present


    @staticmethod
    def _folder_within(candidate: str, target: str) -> bool:
        """Return True when *candidate* is *target* or lives below it."""
        return candidate == target or candidate.startswith(f"{target}/")

    @staticmethod
    def _rekey_path(value: str, old_prefix: str, new_prefix: str) -> str:
        """Move a stored path (or URL) from *old_prefix* onto *new_prefix*."""
        if not value:
            return value
        normalized = value.replace("\\", "/")
        if normalized.startswith(old_prefix):
            return new_prefix + normalized[len(old_prefix):]
        return value

    async def rename_known_folder(
        self,
        previous_folder: str,
        new_folder: str,
        *,
        previous_path: str,
        new_path: str,
    ) -> bool:
        """Re-key folder, cache and metadata records after a directory rename.

        Counterpart of :meth:`add_known_folder` / :meth:`remove_known_folder`.
        A rename keeps every file, so nothing may be dropped: the recorded
        folder list, the affected cache entries (``file_path``/``folder``/
        ``preview_url``), the hash index and the on-disk metadata sidecars are
        all rewritten onto the new prefix. That is what lets a folder full of
        models be renamed without a rescan and without breaking per-model
        bookkeeping.

        Args:
            previous_folder: Library-relative folder name before the rename
            new_folder: Library-relative folder name after the rename
            previous_path: Absolute directory path before the rename
            new_path: Absolute directory path after the rename

        Returns:
            True when any recorded data was rewritten.
        """
        previous = previous_folder.replace("\\", "/").strip("/")
        current = new_folder.replace("\\", "/").strip("/")
        if not previous or not current or previous == current:
            return False

        old_rel_prefix = f"{previous}/"
        new_rel_prefix = f"{current}/"
        old_abs_prefix = f"{str(previous_path).replace(chr(92), '/').rstrip('/')}/"
        new_abs_prefix = f"{str(new_path).replace(chr(92), '/').rstrip('/')}/"

        # Centralized sidecar mode: sidecars/previews live in the mirror tree,
        # not under the renamed model directory, so the mirror subtree must
        # move too and mirror-prefixed preview URLs need their own rekey.
        old_mirror_dir: Optional[str] = None
        new_mirror_dir: Optional[str] = None
        if is_centralized():
            old_mirror_dir = resolve_centralized_dir_for_dir(str(previous_path))
            new_mirror_dir = resolve_centralized_dir_for_dir(str(new_path))
        old_mirror_prefix = (
            f"{old_mirror_dir.replace(chr(92), '/').rstrip('/')}/"
            if old_mirror_dir
            else ""
        )
        new_mirror_prefix = (
            f"{new_mirror_dir.replace(chr(92), '/').rstrip('/')}/"
            if new_mirror_dir
            else ""
        )

        cache = self._cache
        if cache is None:
            return False

        changed = False

        recorded = getattr(cache, "all_folders", None)
        if recorded is not None:
            rekeyed = sorted(
                (
                    self._rekey_folder_name(entry, previous, old_rel_prefix, new_rel_prefix)
                    for entry in recorded
                ),
                key=lambda entry: entry.lower(),
            )
            # The recorded list is a union over the roots, and a same-named
            # folder in another root keeps the old name. Those entries still
            # exist on disk under the old relative path, so re-adding them is
            # what stops the rename from hiding the other root's twin.
            survivors = await self._folders_present_on_disk([
                entry
                for entry in recorded
                if entry == previous or entry.startswith(old_rel_prefix)
            ])
            if survivors:
                rekeyed = sorted(set(rekeyed) | survivors, key=lambda entry: entry.lower())
            if rekeyed != list(recorded):
                cache.all_folders = rekeyed
                changed = True

        excluded = getattr(self, "_excluded_models", None)
        if excluded:
            rekeyed_excluded = [
                self._rekey_path(entry, old_abs_prefix, new_abs_prefix)
                for entry in excluded
            ]
            if rekeyed_excluded != list(excluded):
                self._excluded_models = rekeyed_excluded
                changed = True

        touched: List[Dict[str, Any]] = []
        for item in cache.raw_data or []:
            old_file_path = item.get("file_path", "")
            normalized_old_path = str(old_file_path).replace(chr(92), "/")
            # Only records physically inside the renamed directory. Matching on
            # the relative folder alone would also re-key the same-named folder
            # in another root, whose files never moved.
            if old_file_path and not normalized_old_path.startswith(old_abs_prefix):
                continue

            folder_value = item.get("folder", "") or self._calculate_folder(
                item.get("file_path", "")
            )
            if not self._folder_within(folder_value, previous):
                continue

            if old_file_path:
                cache.remove_from_version_index(item)
                item["file_path"] = self._rekey_path(
                    old_file_path, old_abs_prefix, new_abs_prefix
                )
                hash_value = (item.get("sha256") or "").lower()
                if hash_value:
                    self._hash_index.remove_by_path(old_file_path, hash_value)
                    self._hash_index.add_entry(
                        hash_value, item["file_path"], item.get("autov3") or None
                    )

            item["folder"] = self._rekey_folder_name(
                folder_value, previous, old_rel_prefix, new_rel_prefix
            )
            if item.get("preview_url"):
                item["preview_url"] = self._rekey_path(
                    item["preview_url"], old_abs_prefix, new_abs_prefix
                )
                if old_mirror_prefix:
                    item["preview_url"] = self._rekey_path(
                        item["preview_url"], old_mirror_prefix, new_mirror_prefix
                    )
            touched.append(item)

        if old_mirror_dir and new_mirror_dir and os.path.isdir(old_mirror_dir):
            try:
                os.makedirs(os.path.dirname(new_mirror_dir), exist_ok=True)
                shutil.move(old_mirror_dir, new_mirror_dir)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to move centralized sidecar mirror %s -> %s: %s",
                    old_mirror_dir,
                    new_mirror_dir,
                    exc,
                )

        if touched:
            changed = True
            await self._rewrite_sidecar_paths(touched)
            folders = set(item.get("folder", "") for item in cache.raw_data)
            cache.folders = sorted(folders, key=lambda x: x.lower())
            cache.rebuild_version_index()
            await cache.resort()

        if changed:
            await self._persist_current_cache()

        self.bump_cache_version()
        return changed

    @staticmethod
    def _rekey_folder_name(
        entry: str, previous: str, old_rel_prefix: str, new_rel_prefix: str
    ) -> str:
        """Move a library-relative folder name (and its subtree) under a new name."""
        if entry == previous:
            return new_rel_prefix.rstrip("/")
        if entry.startswith(old_rel_prefix):
            return new_rel_prefix + entry[len(old_rel_prefix):]
        return entry

    async def _rewrite_sidecar_paths(self, entries: List[Dict[str, Any]]) -> None:
        """Point each model's metadata sidecar at its new location.

        In alongside mode sidecars travel with the renamed directory; in
        centralized mode the mirror subtree has already been moved by the
        caller (:meth:`rename_known_folder`). Either way only the recorded
        ``file_path``/``preview_url`` inside them need rewriting. Failures are
        logged and skipped — a stale sidecar is repaired by the next metadata
        refresh, and must not abort the rename.
        """
        for item in entries:
            file_path = item.get("file_path")
            if not file_path:
                continue
            metadata_path = get_metadata_path(file_path)
            if not os.path.exists(metadata_path):
                continue
            try:
                await self._update_metadata_paths(metadata_path, file_path)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to rewrite metadata sidecar %s: %s", metadata_path, exc
                )

    def _find_pending_models_in_sidecar_mirror(self) -> List[Dict[str, Any]]:
        """Mirror-tree counterpart of the alongside pending-hash filesystem scan.

        Centralized mode stores ``.metadata.json`` sidecars in the mirror
        tree, so walking the model folders finds nothing. Each mirror base is
        resolved from a configured model root; a sidecar's recorded
        ``file_path`` locates its model, with a stem-based probe under the
        mapped model root as fallback (mirror path components are sanitized,
        so reverse mapping is best-effort). Orphan sidecars whose model file
        no longer exists are skipped, matching the alongside scan.
        """

        pending_models: List[Dict[str, Any]] = []

        for root_path in self.get_model_roots():
            mirror_base = resolve_centralized_dir_for_dir(root_path)
            if not mirror_base or not os.path.isdir(mirror_base):
                continue

            for dirpath, dirnames, filenames in os.walk(mirror_base):
                dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
                for filename in filenames:
                    if not filename.endswith(".metadata.json"):
                        continue

                    metadata_path = os.path.join(dirpath, filename)
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        # Check if hash is pending
                        hash_status = data.get("hash_status", "completed")
                        sha256 = data.get("sha256", "")

                        if hash_status != "completed" or not sha256:
                            # Find corresponding model file: prefer the
                            # sidecar's recorded path, then probe by stem
                            # under the mapped model root.
                            model_path = None
                            recorded_path = data.get("file_path")
                            if (
                                isinstance(recorded_path, str)
                                and recorded_path
                                and os.path.exists(recorded_path)
                            ):
                                model_path = recorded_path
                            else:
                                model_name = filename.replace(".metadata.json", "")
                                rel_dir = os.path.relpath(dirpath, mirror_base)
                                candidate_dir = (
                                    root_path
                                    if rel_dir == os.curdir
                                    else os.path.join(root_path, rel_dir)
                                )
                                for ext in self.file_extensions:
                                    potential_path = os.path.join(
                                        candidate_dir, model_name + ext
                                    )
                                    if os.path.exists(potential_path):
                                        model_path = potential_path
                                        break

                            if model_path:
                                pending_models.append(
                                    {
                                        "file_path": model_path.replace(os.sep, "/"),
                                        "hash_status": hash_status,
                                        "sha256": sha256,
                                        **{
                                            k: v
                                            for k, v in data.items()
                                            if k
                                            not in [
                                                "file_path",
                                                "hash_status",
                                                "sha256",
                                            ]
                                        },
                                    }
                                )
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(
                            f"Error reading metadata file {metadata_path}: {e}"
                        )
                        continue

        return pending_models

    def _schedule_all_folders_backfill(self) -> None:
        """Kick off a one-shot background folder walk if none is running."""
        if self._all_folders_backfill_running:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._all_folders_backfill_running = True
        loop.create_task(self._run_all_folders_backfill())

    async def _run_all_folders_backfill(self) -> None:
        """Walk the roots in a worker thread, then record and persist the result."""
        try:
            loop = asyncio.get_running_loop()
            folders = await loop.run_in_executor(None, self._walk_all_folders_sync)
            cache = self._cache
            # A scan may have recorded the list while the walk was in flight;
            # prefer the fresher scan data in that case.
            if cache is not None and cache.all_folders is None:
                cache.all_folders = folders
                await self._persist_current_cache()
        except Exception as exc:
            logger.warning(
                "%s Scanner: all-folders backfill failed: %s",
                self.model_type.capitalize(),
                exc,
            )
        finally:
            self._all_folders_backfill_running = False

    def _walk_all_folders_sync(self) -> List[str]:
        """Enumerate every directory under the model roots, live from disk.

        Runs in a worker thread. Hidden directories (any segment starting
        with '.') and the pending-delete staging dir are excluded.
        """
        discovered: Set[str] = set()
        visited_real_paths: Set[str] = set()

        for root_path in self.get_model_roots():
            if not os.path.exists(root_path):
                continue

            for root, dirnames, _files in os.walk(root_path, followlinks=True):
                dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
                # realpath is used only for symlink dedup, never for the
                # recorded path (business paths stay unresolved).
                real_root = os.path.realpath(root)
                if real_root in visited_real_paths:
                    continue
                visited_real_paths.add(real_root)

                rel_dir = os.path.relpath(os.path.abspath(root), os.path.abspath(root_path))
                rel_dir = rel_dir.replace(os.path.sep, "/")
                if rel_dir != "." and not _is_hidden_relative_path(rel_dir):
                    discovered.add(rel_dir)

        return sorted(discovered, key=lambda x: x.lower())
    
    async def _create_default_metadata(self, file_path: str) -> Optional[BaseModelMetadata]:
        """Get model file info and metadata (extensible for different model types)"""
        return await MetadataManager.create_default_metadata(file_path, self.model_class)
    
    def _calculate_folder(self, file_path: str) -> str:
        """Calculate the folder path for a model file"""
        for root in self.get_model_roots():
            if file_path.startswith(root):
                rel_path = os.path.relpath(file_path, root)
                return os.path.dirname(rel_path).replace(os.path.sep, '/')
        return ''

    def adjust_metadata(self, metadata, file_path, root_path):
        """Hook for subclasses: adjust metadata during scanning"""
        return metadata

    def adjust_cached_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Hook for subclasses: adjust entries loaded from the persisted cache."""
        return entry

    def _should_keep_cached_entry(self, entry: Dict[str, Any]) -> bool:
        """Hook for subclasses: decide whether a persisted entry is still managed.

        Entries rejected here are dropped (with their hash/autov3 index rows)
        while hydrating the persisted cache, so a scanner whose configured
        roots shrank does not surface stale models before the next reconcile.
        """
        return True

    def resolve_sub_type_for_path(self, file_path: Optional[str]) -> Optional[str]:
        """Hook for subclasses: resolve the location-derived sub_type for a file.

        Returns ``None`` when the model type has no location-derived sub-types
        (the default), in which case any stored value is left untouched.
        """
        return None

    @staticmethod
    def _normalize_path_value(path: Optional[str]) -> str:
        if not path:
            return ''

        normalized = os.path.normpath(path)
        if normalized == '.':
            return ''

        return normalized.replace('\\', '/')

    def _find_root_for_file(self, file_path: Optional[str]) -> Optional[str]:
        """Return the configured root directory that contains ``file_path``."""

        normalized_path = self._normalize_path_value(file_path)
        if not normalized_path:
            return None

        for root in self.get_model_roots() or []:
            normalized_root = self._normalize_path_value(root)
            if not normalized_root:
                continue

            if (
                normalized_path == normalized_root
                or normalized_path.startswith(f"{normalized_root}/")
            ):
                return root

        return None

    async def _process_model_file(
        self,
        file_path: str,
        root_path: str,
        *,
        hash_index: Optional[ModelHashIndex] = None,
        excluded_models: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Process a single model file and return its metadata"""
        hash_index = hash_index or self._hash_index
        excluded_models = excluded_models if excluded_models is not None else self._excluded_models

        # Belt-and-braces: staged files must never become library entries even
        # if a caller invokes this method directly with a staging path.
        if _is_pending_delete_path(file_path):
            return None

        metadata, should_skip = await MetadataManager.load_metadata(file_path, self.model_class)
    
        if should_skip:
            # Metadata file exists but cannot be parsed - skip this model
            logger.warning(f"Skipping model {file_path} due to corrupted metadata file")
            return None
        
        if metadata is None:
            civitai_info_path = f"{os.path.splitext(file_path)[0]}.civitai.info"
            if os.path.exists(civitai_info_path):
                try:
                    with open(civitai_info_path, 'r', encoding='utf-8') as f:
                        version_info = json.load(f)
                    
                    file_info = next((f for f in version_info.get('files', []) if f.get('primary')), None)
                    if file_info:
                        local_stem = os.path.splitext(os.path.basename(file_path))[0]
                        # from_civitai_info expects an API-shaped file entry and
                        # strips one extension itself, so hand it the real
                        # basename: passing the already extension-free stem made
                        # it cut dotted names at their last dot ("lora-sd1.5-..."
                        # became "lora-sd1", issue #1112).
                        file_info['name'] = os.path.basename(file_path)

                        metadata = cast(Any, self.model_class).from_civitai_info(version_info, file_info, file_path)
                        metadata.preview_url = find_preview_file(local_stem, get_preview_dir(file_path))
                        await MetadataManager.save_metadata(file_path, metadata)
                        logger.info(f"Created metadata from .civitai.info for {file_path} (Reason: .civitai.info was found but .metadata.json was missing)")
                except Exception as e:
                    logger.error(f"Error creating metadata from .civitai.info for {file_path}: {e}")
        else:
            # Check if metadata exists but civitai field is empty - try to restore from civitai.info
            if metadata.civitai is None or metadata.civitai == {}:
                civitai_info_path = f"{os.path.splitext(file_path)[0]}.civitai.info"
                if os.path.exists(civitai_info_path):
                    try:
                        with open(civitai_info_path, 'r', encoding='utf-8') as f:
                            version_info = json.load(f)
                        
                        logger.debug(f"Restoring missing civitai data from .civitai.info for {file_path}")
                        metadata.civitai = version_info
                        
                        # Ensure tags are also updated if they're missing
                        if (not metadata.tags or len(metadata.tags) == 0) and 'model' in version_info:
                            if 'tags' in version_info['model']:
                                metadata.tags = version_info['model']['tags']
                        
                        # Also restore description if missing
                        if (not metadata.modelDescription or metadata.modelDescription == "") and 'model' in version_info:
                            if 'description' in version_info['model']:
                                metadata.modelDescription = version_info['model']['description']
                        
                        # Save the updated metadata
                        await MetadataManager.save_metadata(file_path, metadata)
                        logger.debug(f"Updated metadata with civitai info for {file_path}")
                    except Exception as e:
                        logger.error(f"Error restoring civitai data from .civitai.info for {file_path}: {e}")
            
        if metadata is None:
            metadata = await self._create_default_metadata(file_path)
        
        assert metadata is not None

        # Hook: allow subclasses to adjust metadata
        metadata = self.adjust_metadata(metadata, file_path, root_path)
        
        rel_path = os.path.relpath(file_path, root_path)
        folder = os.path.dirname(rel_path)
        normalized_folder = folder.replace(os.path.sep, '/')

        model_data = self._build_cache_entry(metadata, folder=normalized_folder)

        # Compute SHA256 hash when metadata provided none (e.g., CivitAI API response has empty hashes).
        # Respect hash_status='pending' (set by CheckpointScanner for large models) to defer
        # hash calculation until on-demand — avoids reading entire checkpoint files at startup.
        hash_status = model_data.get('hash_status', '')
        if not model_data.get('sha256') and hash_status != 'pending' and file_path:
            try:
                logger.info(f"Computing SHA256 hash for {file_path} (was empty from metadata)")
                sha256 = await calculate_sha256(file_path)
                if sha256:
                    model_data['sha256'] = sha256.lower()
                    if isinstance(metadata, BaseModelMetadata):
                        metadata.sha256 = sha256.lower()
                    await MetadataManager.save_metadata(file_path, metadata)
            except Exception as e:
                logger.error(f"Failed to compute SHA256 for {file_path}: {e}")

        # AutoV3 resolution: prefer the Civitai AutoV3 reported for the file
        # whose SHA256 matches (authoritative for recipe matching), falling
        # back to the embedded safetensors header hash only for models never
        # checked before (autov3 is None). A checked-unavailable state ('')
        # is only upgraded by Civitai data — the header is never re-read.
        current_autov3 = model_data.get('autov3')
        if current_autov3 in (None, ''):
            try:
                civitai_data = None
                if isinstance(metadata, BaseModelMetadata):
                    civitai_data = metadata.civitai
                elif isinstance(metadata, dict):
                    civitai_data = metadata.get("civitai")
                autov3 = autov3_from_civitai_files(
                    civitai_data, model_data.get("sha256") or ""
                ) or ""
                if not autov3 and current_autov3 is None:
                    autov3 = (calculate_autov3(os.path.realpath(file_path)) or '').lower()
                if autov3 != current_autov3:
                    model_data['autov3'] = autov3
                    if isinstance(metadata, BaseModelMetadata):
                        metadata.autov3 = autov3
                        await MetadataManager.save_metadata(file_path, metadata)
                    elif isinstance(metadata, dict):
                        # Dict payload: JSON null encodes the checked-unavailable state.
                        metadata['autov3'] = autov3 or None
                        await MetadataManager.save_metadata(file_path, metadata)
            except Exception as e:
                logger.error(f"Failed to resolve AutoV3 for {file_path}: {e}")

        # Skip excluded models
        if model_data.get('exclude', False):
            excluded_models.append(model_data['file_path'])
            return None

        return model_data

    async def _apply_scan_result(self, scan_result: CacheBuildResult) -> None:
        """Apply scan results to the cache and associated indexes."""

        if scan_result is None:
            return

        if self.is_cancelled():
            logger.info(
                f"{self.model_type.capitalize()} Scanner: Skipping _apply_scan_result "
                "after cancellation"
            )
            return

        self._hash_index = scan_result.hash_index
        self._tags_count = dict(scan_result.tags_count)
        self._excluded_models = list(scan_result.excluded_models)

        if self._cache is None:
            self._cache = ModelCache(
                raw_data=list(scan_result.raw_data),
                folders=[],
                name_display_mode=self._name_display_mode,
            )
        else:
            self._cache.raw_data = list(scan_result.raw_data)

        if scan_result.all_folders is not None:
            self._cache.all_folders = list(scan_result.all_folders)

        # resort() rebuilds folders and the version index on every path, so a
        # separate rebuild_version_index() call here would be redundant.
        await self._cache.resort()

        self._log_duplicate_filename_summary()

        self.bump_cache_version()

    def _log_duplicate_filename_summary(self) -> None:
        """Log a batched summary of duplicate filename conflicts once per scan."""
        # Duplicate filename detection is only relevant for LoRAs, which use
        # basename-only syntax (<lora:name:strength>). Checkpoints and embeddings
        # use full relative paths for resolution, so conflicts are not ambiguous.
        if self._hash_index is None or self.model_type != "lora":
            return

        # When full path syntax is active, duplicate filenames across subfolders
        # are fully qualified, so there is no ambiguity — skip the warning.
        if get_settings_manager().get("lora_syntax_format", "legacy") == "full":
            return

        duplicates = self._hash_index.get_duplicate_filenames()
        if not duplicates:
            return

        total_files = sum(len(paths) for paths in duplicates.values())
        conflict_count = len(duplicates)
        model_type_label = self.model_type or "model"

        logger.warning(
            "Duplicate filename conflict detected: %d %s filename(s) "
            "are shared by %d files total, causing ambiguity in %s resolution. "
            "Open the Doctor panel to resolve one-click.",
            conflict_count,
            model_type_label,
            total_files,
            model_type_label.capitalize(),
        )

    async def _sync_download_history(
        self,
        raw_data: Sequence[Mapping[str, Any]],
        *,
        source: str,
    ) -> None:
        records: List[Dict[str, Any]] = []
        for item in raw_data or []:
            if not isinstance(item, Mapping):
                continue
            civitai = item.get('civitai')
            if not isinstance(civitai, Mapping):
                continue

            version_id = civitai.get('id')
            if version_id in (None, ''):
                continue

            records.append(
                {
                    'version_id': version_id,
                    'model_id': civitai.get('modelId'),
                    'file_path': item.get('file_path'),
                }
            )

        if not records:
            return

        try:
            history_service = await ServiceRegistry.get_downloaded_version_history_service()
            await history_service.mark_downloaded_bulk(
                self.model_type,
                records,
                source=source,
            )
        except Exception as exc:
            logger.debug(
                "%s Scanner: Failed to sync download history: %s",
                self.model_type.capitalize(),
                exc,
            )

    async def _gather_model_data(
        self,
        *,
        total_files: int = 0,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None
    ) -> CacheBuildResult:
        """Collect metadata for all model files."""

        raw_data: List[Dict[str, Any]] = []
        hash_index = ModelHashIndex()
        tags_count: Dict[str, int] = {}
        excluded_models: List[str] = []
        processed_files = 0
        processed_real_files: Set[str] = set()
        visited_real_dirs: Set[str] = set()
        discovered_folders: Set[str] = set()

        async def handle_progress(current_name: str = '') -> None:
            if progress_callback is None:
                return
            try:
                await progress_callback(processed_files, total_files, current_name)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"Error reporting progress for {self.model_type}: {exc}")

        self.reset_cancellation()

        async def scan_recursive(current_path: str, root_path: str, visited_paths: Set[str]) -> None:
            nonlocal processed_files

            try:
                real_path = os.path.realpath(current_path)
                if real_path in visited_paths or real_path in visited_real_dirs:
                    return
                visited_paths.add(real_path)
                visited_real_dirs.add(real_path)

                with os.scandir(current_path) as iterator:
                    entries = list(iterator)

                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=True):
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext not in self.file_extensions:
                                continue

                            file_path = entry.path.replace(os.sep, "/")
                            real_file_path = os.path.realpath(entry.path)
                            if real_file_path in processed_real_files:
                                continue

                            processed_real_files.add(real_file_path)
                            result = await self._process_model_file(
                                file_path,
                                root_path,
                                hash_index=hash_index,
                                excluded_models=excluded_models
                            )

                            processed_files += 1

                            if result:
                                # Validate the entry before adding
                                validation_result = CacheEntryValidator.validate(
                                    result, auto_repair=True
                                )
                                if not validation_result.is_valid:
                                    logger.warning(
                                        f"Skipping invalid scan result: {file_path}"
                                    )
                                    continue
                                result = validation_result.entry
                                if result is None:
                                    continue

                                self._ensure_license_flags(result)
                                raw_data.append(result)

                                sha_value = result.get('sha256')
                                model_path = result.get('file_path')
                                if sha_value and model_path:
                                    hash_index.add_entry(sha_value.lower(), model_path, result.get('autov3') or None)

                                for tag in result.get('tags') or []:
                                    tags_count[tag] = tags_count.get(tag, 0) + 1

                            await handle_progress(entry.name)
                            await asyncio.sleep(0)
                            if self.is_cancelled():
                                return
                        elif entry.is_dir(follow_symlinks=True):
                            if _is_excluded_dir(entry.name):
                                continue
                            # Record every directory (including empty ones) so
                            # the folder tree can be served without a live walk.
                            rel_dir = os.path.relpath(
                                os.path.abspath(entry.path), os.path.abspath(root_path)
                            ).replace(os.path.sep, "/")
                            if not _is_hidden_relative_path(rel_dir):
                                discovered_folders.add(rel_dir)
                            await scan_recursive(entry.path, root_path, visited_paths)
                    except Exception as entry_error:
                        logger.error(f"Error processing entry {entry.path}: {entry_error}")
            except Exception as scan_error:
                logger.error(f"Error scanning {current_path}: {scan_error}")

            if self.is_cancelled():
                return

        for model_root in self.get_model_roots():
            if not os.path.exists(model_root):
                continue

            await scan_recursive(model_root, model_root, set())

        return CacheBuildResult(
            raw_data=raw_data,
            hash_index=hash_index,
            tags_count=tags_count,
            excluded_models=excluded_models,
            all_folders=sorted(discovered_folders, key=lambda x: x.lower()),
        )

    async def add_model_to_cache(self, metadata_dict: Dict[str, Any], folder: str = '') -> bool:
        """Add a model to the cache

        Args:
            metadata_dict: The model metadata dictionary
            folder: The relative folder path for the model
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self._cache is None:
                await self.get_cached_data()
            assert self._cache is not None

            # Update folder in metadata
            metadata_dict['folder'] = folder
            
            file_path = metadata_dict.get('file_path', '')
            if file_path:
                old_entries = [item for item in self._cache.raw_data if item.get('file_path') == file_path]
                for old_entry in old_entries:
                    for tag in old_entry.get('tags', []):
                        if tag in self._tags_count:
                            self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                            if self._tags_count[tag] == 0:
                                del self._tags_count[tag]
                self._hash_index.remove_by_path(file_path)
                self._cache.raw_data = [item for item in self._cache.raw_data if item.get('file_path') != file_path]

            for tag in metadata_dict.get('tags', []):
                self._tags_count[tag] = self._tags_count.get(tag, 0) + 1

            self._cache.raw_data.append(metadata_dict)

            await self._cache.resort()
            
            # Update the hash index
            self._hash_index.add_entry(
                metadata_dict['sha256'],
                metadata_dict['file_path'],
                metadata_dict.get('autov3') or None,
            )
            await self._persist_current_cache()
            self.bump_cache_version()
            return True
        except Exception as e:
            logger.error(f"Error adding model to cache: {e}")
            return False
    
    async def move_model(self, source_path: str, target_path: str) -> Optional[Dict[str, Any]]:
        """Move a model and its associated files to a new location

        Args:
            source_path: Original file path
            target_path: Target directory path

        Returns:
            Optional[str]: New file path if successful, None if failed
        """
        source_path = source_path.replace(os.sep, '/')
        target_path = target_path.replace(os.sep, '/')

        # Serialize moves per source file: concurrent requests for the same
        # model (auto-organize racing a manual move, duplicate clicks) must
        # not interleave, or the second mover hits a missing source file.
        lock_key = os.path.normcase(os.path.abspath(os.path.normpath(source_path)))
        lock = self._move_locks.setdefault(lock_key, asyncio.Lock())
        try:
            async with lock:
                return await self._move_model_locked(source_path, target_path)
        finally:
            if not lock.locked():
                self._move_locks.pop(lock_key, None)

    async def _move_model_locked(self, source_path: str, target_path: str) -> Optional[Dict[str, Any]]:
        try:
            file_ext = os.path.splitext(source_path)[1]
            
            if not file_ext or file_ext.lower() not in self.file_extensions:
                logger.error(f"Invalid file extension for model: {file_ext}")
                return None
                
            base_name = os.path.splitext(os.path.basename(source_path))[0]
            source_dir = os.path.dirname(source_path)

            _require_path_in_library_roots(source_path, self, label="Source path")
            _require_path_in_library_roots(target_path, self, label="Target path")
            
            os.makedirs(target_path, exist_ok=True)
            
            def get_source_hash():
                return self.get_hash_by_path(source_path)
            
            # Check for filename conflicts and auto-rename if necessary
            from ..utils.models import BaseModelMetadata
            final_filename = BaseModelMetadata.generate_unique_filename(
                target_path, base_name, file_ext, lambda: get_source_hash() or ""
            )
            
            target_file = os.path.join(target_path, final_filename).replace(os.sep, '/')
            final_base_name = os.path.splitext(final_filename)[0]
            
            # Log if filename was changed due to conflict
            if final_filename != f"{base_name}{file_ext}":
                logger.info(f"Renamed {base_name}{file_ext} to {final_filename} to avoid filename conflict")

            # Business paths (abspath, symlinks NOT resolved) per project
            # convention: file mutations must operate on the paths as they
            # appear under the configured model roots.
            move_source = os.path.abspath(source_path)
            move_target = os.path.abspath(target_file)

            if not os.path.exists(move_source):
                # The source is gone — typically a previous move already
                # succeeded but the cache/metadata were left pointing at the
                # old path. Repair that state instead of failing.
                natural_target = os.path.join(target_path, f"{base_name}{file_ext}").replace(os.sep, '/')
                return await self._reconcile_already_moved(source_path, [target_file, natural_target])

            shutil.move(move_source, move_target)
            
            # Move all associated files with the same base name
            source_metadata = None
            moved_metadata_path = None

            # Associated files (sidecar metadata, previews) sit next to the
            # model in alongside mode and in the mirror tree in centralized
            # mode; collect from every directory that holds them.
            source_sidecar_dir = get_sidecar_dir(source_path)
            target_sidecar_dir = get_sidecar_dir(target_file)
            associated_dirs = [(source_dir, target_path)]
            if os.path.normpath(source_sidecar_dir) != os.path.normpath(source_dir):
                associated_dirs.append((source_sidecar_dir, target_sidecar_dir))

            # Find all files with the same base name in the source directories
            files_to_move = []
            metadata_filename = os.path.basename(get_metadata_path(source_path))
            for assoc_source_dir, assoc_target_dir in associated_dirs:
                try:
                    for file in os.listdir(assoc_source_dir):
                        if file.startswith(base_name + ".") and file != os.path.basename(source_path):
                            source_file_path = os.path.join(assoc_source_dir, file)
                            # Generate new filename with the same base name as the model file
                            file_suffix = file[len(base_name):]  # Get the part after base_name (e.g., ".metadata.json", ".preview.png")
                            new_associated_filename = f"{final_base_name}{file_suffix}"
                            target_associated_path = os.path.join(assoc_target_dir, new_associated_filename)

                            # Store metadata file path for special handling
                            if file == metadata_filename:
                                source_metadata = source_file_path
                                moved_metadata_path = target_associated_path
                            else:
                                files_to_move.append((source_file_path, target_associated_path))
                except Exception as e:
                    logger.error(f"Error listing files in {assoc_source_dir}: {e}")

            # Move all associated files
            metadata = None
            for source_file, target_file_path in files_to_move:
                try:
                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                    shutil.move(source_file, target_file_path)
                except Exception as e:
                    logger.error(f"Error moving associated file {source_file}: {e}")

            # Handle metadata file specially to update paths
            if source_metadata and moved_metadata_path and os.path.exists(source_metadata):
                try:
                    os.makedirs(os.path.dirname(moved_metadata_path), exist_ok=True)
                    shutil.move(source_metadata, moved_metadata_path)
                    metadata = await self._update_metadata_paths(moved_metadata_path, target_file)
                except Exception as e:
                    logger.error(f"Error moving metadata file: {e}")
            
            if metadata is not None:
                # sub_type is derived from the model's location (e.g. a file
                # moved from a checkpoints root into a unet root becomes a
                # diffusion_model). Persist the recalculated value into the
                # moved metadata file so later metadata-driven cache syncs
                # do not revert the cache entry to the stale sub_type.
                new_sub_type = self.resolve_sub_type_for_path(target_file)
                if new_sub_type and metadata.get('sub_type') != new_sub_type:
                    metadata['sub_type'] = new_sub_type
                    try:
                        await MetadataManager.save_metadata(moved_metadata_path, metadata)
                    except Exception as e:
                        logger.error(f"Error persisting sub_type for moved model: {e}")

            update_result = await self.update_single_model_cache(source_path, target_file, metadata, recalculate_type=True)
            
            return {
                "new_path": target_file,
                "cache_entry": update_result if isinstance(update_result, dict) else None
            }
            
        except Exception as e:
            logger.error(f"Error moving model: {e}", exc_info=True)
            return None

    async def _reconcile_already_moved(self, source_path: str, target_candidates: List[str]) -> Optional[Dict[str, Any]]:
        """Repair state when a move's source file is already gone.

        A previous move may have relocated the file while the cache/metadata
        still point at the old path (crash mid-move, concurrent request, or
        external tools). If the model is found at its new location, update
        the cache and metadata to match reality instead of failing.
        """
        candidates: List[str] = []
        source_hash = self.get_hash_by_path(source_path)
        if source_hash:
            indexed_path = self.get_path_by_hash(source_hash)
            if indexed_path:
                candidates.append(indexed_path)
        candidates.extend(target_candidates)

        for candidate in candidates:
            if not candidate or os.path.normpath(candidate) == os.path.normpath(source_path):
                continue
            if not os.path.exists(os.path.abspath(candidate)):
                continue

            new_path = candidate.replace(os.sep, '/')
            logger.info(
                f"Move source {source_path} no longer exists; the model is already "
                f"at {new_path}. Reconciling cache and metadata."
            )

            cache = await self.get_cached_data()
            existing_at_target = next((item for item in cache.raw_data if item['file_path'] == new_path), None)
            if existing_at_target is not None:
                # Cache already tracks the moved file (a previous move updated
                # it); just drop the stale source entry without appending a
                # duplicate.
                await self.update_single_model_cache(source_path, new_path, None)
                return {"new_path": new_path, "cache_entry": existing_at_target}

            metadata = None
            metadata_path = get_metadata_path(new_path)
            if os.path.exists(metadata_path):
                metadata = await self._update_metadata_paths(metadata_path, new_path)

            if metadata is None:
                # No sidecar at the new location — reuse the stale cache entry
                # so the model card keeps its data under the corrected path.
                existing_item = next((item for item in cache.raw_data if item['file_path'] == source_path), None)
                if existing_item:
                    metadata = dict(existing_item)
                    metadata['file_path'] = new_path
                    metadata['file_name'] = os.path.splitext(os.path.basename(new_path))[0]

            update_result = await self.update_single_model_cache(source_path, new_path, metadata, recalculate_type=True)
            return {
                "new_path": new_path,
                "cache_entry": update_result if isinstance(update_result, dict) else None,
            }

        logger.error(
            f"Cannot move model: source file not found: {source_path} "
            f"(already moved or deleted outside LoRA Manager?)"
        )
        return None

    async def _update_metadata_paths(self, metadata_path: str, model_path: str) -> Optional[Dict[str, Any]]:
        """Update file paths in metadata file"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            metadata['file_path'] = model_path.replace(os.sep, '/')
            # Update file_name to match the new filename
            metadata['file_name'] = os.path.splitext(os.path.basename(model_path))[0]
            
            if 'preview_url' in metadata and metadata['preview_url']:
                preview_dir = get_preview_dir(model_path)
                # Update preview filename to match the new base name
                new_base_name = os.path.splitext(os.path.basename(model_path))[0]
                preview_ext = get_preview_extension(metadata['preview_url'])
                new_preview_path = os.path.join(preview_dir, f"{new_base_name}{preview_ext}")
                metadata['preview_url'] = new_preview_path.replace(os.sep, '/')
            
            await MetadataManager.save_metadata(metadata_path, metadata)

            return metadata
                
        except Exception as e:
            logger.error(f"Error updating metadata paths: {e}", exc_info=True)
            return None

    @asynccontextmanager
    async def defer_cache_persist(self):
        """Defer heavyweight cache maintenance for a bulk operation.

        While at least one ``defer_cache_persist`` context is active,
        :meth:`update_single_model_cache` performs only the in-memory entry
        swap plus incremental index updates — it skips the full version-index
        rebuild, the natsort resort, and the whole-table SQLite persist plus
        download-history sync that normally run per call. When the outermost
        context exits, the pending maintenance runs **once** (resort, persist,
        download-history sync).

        The final persist is forced: it runs even when the scanner's
        cancellation flag is set or the wrapped block raised, because callers
        use this around operations that already mutated files on disk and the
        cache must not be left diverging from reality.

        Intended for bulk rename/move loops (e.g. the filename-template "Apply
        to Library" flow). Single-shot callers keep the immediate per-call
        behavior by not entering this context.
        """
        self._defer_persist_depth = getattr(self, "_defer_persist_depth", 0) + 1
        try:
            yield
        finally:
            self._defer_persist_depth -= 1
            if self._defer_persist_depth == 0:
                await self._finalize_deferred_cache_persist()

    @property
    def _cache_persist_deferred(self) -> bool:
        """True while cache resort/persist is deferred to a bulk finalize."""
        return getattr(self, "_defer_persist_depth", 0) > 0

    async def _finalize_deferred_cache_persist(self) -> None:
        """Run the resort + persist deferred by ``defer_cache_persist``.

        Best-effort: failures are logged, never raised, so an error here
        cannot mask the outcome of the bulk operation itself (including
        cancellation).
        """
        if not getattr(self, "_deferred_persist_pending", False):
            return
        self._deferred_persist_pending = False
        if self._cache is None:
            return
        try:
            # resort() rebuilds the version index and folder list, so the
            # per-call rebuilds skipped during deferral are covered here.
            await self._cache.resort()
            await self._persist_current_cache(force=True)
            self.bump_cache_version()
        except Exception:
            logger.error(
                "%s Scanner: failed to finalize deferred cache persist",
                self.model_type.capitalize(),
                exc_info=True,
            )

    async def update_single_model_cache(self, original_path: str, new_path: str, metadata: Optional[Dict[str, Any]], recalculate_type: bool = False) -> Union[bool, Dict[str, Any]]:
        """Update cache after a model has been moved or modified.

        Performs the full maintenance chain (version-index rebuild, resort,
        whole-table persist, download-history sync) unless the scanner is
        inside a :meth:`defer_cache_persist` context, in which case only
        the in-memory entry swap and incremental index updates run and the
        heavy chain executes once at context exit.
        """
        deferred = self._cache_persist_deferred
        cache = await self.get_cached_data()

        existing_index: Optional[int] = None
        existing_item = None
        for idx, item in enumerate(cache.raw_data):
            if item['file_path'] == original_path:
                existing_item = item
                existing_index = idx
                break

        if existing_item:
            cache.remove_from_version_index(existing_item)

        if existing_item and 'tags' in existing_item:
            for tag in existing_item.get('tags', []):
                if tag in self._tags_count:
                    self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                    if self._tags_count[tag] == 0:
                        del self._tags_count[tag]
        
        self._hash_index.remove_by_path(original_path)

        if deferred:
            # In-place swap avoids the O(n) list rebuild per renamed file;
            # indexes were already updated incrementally above/below, and the
            # folder recompute happens in the single finalize resort().
            if existing_index is not None:
                cache.raw_data.pop(existing_index)
        else:
            cache.raw_data = [
                item for item in cache.raw_data
                if item['file_path'] != original_path
            ]

        cache_modified = bool(existing_item) or bool(metadata)
        cache_entry: Optional[Dict[str, Any]] = None

        if metadata:
            normalized_new_path = new_path.replace(os.sep, '/')
            if original_path == new_path and existing_item:
                folder_value = existing_item.get('folder', self._calculate_folder(new_path))
            else:
                folder_value = self._calculate_folder(new_path)

            cache_entry = self._build_cache_entry(
                metadata,
                folder=folder_value,
                file_path_override=normalized_new_path,
            )

            # Ensure sha256 is populated even when metadata doesn't have it
            if not cache_entry.get('sha256') and normalized_new_path and os.path.exists(normalized_new_path):
                try:
                    sha256 = await calculate_sha256(normalized_new_path)
                    if sha256:
                        cache_entry['sha256'] = sha256.lower()
                except Exception as e:
                    logger.error(f"Failed to compute SHA256 for {normalized_new_path}: {e}")

            if recalculate_type:
                cache_entry = self.adjust_cached_entry(cache_entry)

            cache.raw_data.append(cache_entry)
            cache.add_to_version_index(cache_entry)

            sha_value = cache_entry.get('sha256')
            if sha_value:
                self._hash_index.add_entry(
                    sha_value.lower(),
                    normalized_new_path,
                    cache_entry.get('autov3') or None,
                )

            if not deferred:
                # O(n) over raw_data; the finalize resort() recomputes the
                # folder list once, so bulk callers skip it per file.
                all_folders = set(item['folder'] for item in cache.raw_data)
                cache.folders = sorted(list(all_folders), key=lambda x: x.lower())

            # The move target may live in directories the last scan never saw;
            # record the destination folder (and its parents) in the known
            # folder list so the folder tree reflects it without a rescan.
            if cache.all_folders is not None and folder_value:
                parts = folder_value.split("/")
                known = set(cache.all_folders)
                for i in range(1, len(parts) + 1):
                    known.add("/".join(parts[:i]))
                cache.all_folders = sorted(known, key=lambda x: x.lower())

            for tag in cache_entry.get('tags', []):
                self._tags_count[tag] = self._tags_count.get(tag, 0) + 1

        if deferred:
            if cache_modified:
                self._deferred_persist_pending = True
                self.bump_cache_version()
        else:
            cache.rebuild_version_index()

            await cache.resort()

            if cache_modified:
                await self._persist_current_cache()
                self.bump_cache_version()

        if metadata and cache_entry is not None:
            return cache_entry
        return True
        
    async def sync_cache_from_metadata(
        self, file_path: str, metadata_dict: Dict[str, Any]
    ) -> bool:
        """Opportunistically sync in-memory and persistent caches from metadata.

        Builds a prospective cache entry from *metadata_dict* (deserialized
        ``.metadata.json`` content) and compares it against the current cache
        entry.  When the two are already identical this method returns
        ``False`` without touching anything — avoiding the overhead of
        ``update_single_model_cache``, which always removes and re-inserts
        the entry, triggers a full resort, and persists via the heavyweight
        ``save_cache()``.

        When differences are detected the update is applied **in-place** with
        targeted operations:

        * The existing ``raw_data`` entry is modified rather than removed and
          re-appended (O(1) instead of O(n)).
        * Tag counts and the hash index are updated incrementally.
        * The version index is rebuilt only for the affected entry.
        * ``resort()`` is called **only** when a sort-relevant field changed
          (``model_name`` / ``file_name`` for name-sort, ``modified`` for
          date-sort, ``size`` for size-sort).
        * The persistent (SQLite) cache receives a targeted single-row update
          via :meth:`PersistentModelCache.update_single_model` rather than a
          full-table ``save_cache()``.

        Returns:
            ``True`` if any cache update was performed, ``False`` if the
            caches were already in sync.

        .. note::

            This is a **best-effort** operation.  Failures are logged but
            never propagated — callers should fire-and-forget via
            :func:`asyncio.create_task`.
        """
        try:
            return await self._sync_cache_from_metadata_impl(
                file_path, metadata_dict
            )
        except Exception:
            logger.warning(
                "sync_cache_from_metadata failed for %s",
                file_path,
                exc_info=True,
            )
            return False

    async def _sync_cache_from_metadata_impl(
        self, file_path: str, metadata_dict: Dict[str, Any]
    ) -> bool:
        cache = await self.get_cached_data()

        # Locate the existing cache entry -----------------------------------
        existing_idx: Optional[int] = None
        existing_entry: Optional[Dict[str, Any]] = None
        for i, item in enumerate(cache.raw_data):
            if item.get("file_path") == file_path:
                existing_entry = item
                existing_idx = i
                break

        # Build the desired entry from metadata ------------------------------
        folder_value = (
            existing_entry.get("folder", "")
            if existing_entry
            else self._calculate_folder(file_path)
        )
        desired_entry = self._build_cache_entry(
            metadata_dict,
            folder=folder_value,
            file_path_override=file_path,
        )

        # Location-derived fields (e.g. the checkpoint sub_type) must be
        # re-resolved from the file path rather than trusting the on-disk
        # metadata snapshot, which may predate a cross-root move.
        desired_entry = self.adjust_cached_entry(desired_entry)

        # Ensure sha256 is populated (defensive — metadata should have it)
        if (
            not desired_entry.get("sha256")
            and file_path
            and os.path.exists(file_path)
        ):
            try:
                sha256 = await calculate_sha256(file_path)
                if sha256:
                    desired_entry["sha256"] = sha256.lower()
            except Exception:
                pass

        # Not in cache at all — delegate to the full update path ------------
        if existing_entry is None:
            result = await self.update_single_model_cache(
                file_path, file_path, metadata_dict
            )
            return bool(result)

        # Compare — skip everything if already in sync -----------------------
        if not self._cache_entries_differ(existing_entry, desired_entry):
            return False

        # Re-validate: the cache may have been replaced concurrently
        # (e.g. by _apply_scan_result).  Use identity check, not equality,
        # so we detect when the raw_data list was swapped out from under us.
        if self._cache is None or not any(
            item is existing_entry for item in self._cache.raw_data
        ):
            return False

        # ---- Differences detected: apply targeted, in-place updates --------

        # Snapshot old values for delta computations
        old_tags = list(existing_entry.get("tags") or [])
        old_sha256: str = existing_entry.get("sha256", "") or ""
        old_model_name: str = existing_entry.get("model_name", "") or ""
        old_file_name: str = existing_entry.get("file_name", "") or ""
        old_modified: float = float(existing_entry.get("modified", 0.0) or 0.0)
        old_size: int = int(existing_entry.get("size", 0) or 0)
        old_civitai = existing_entry.get("civitai")

        # ---- In-place update of the cache entry ----
        existing_entry.clear()
        existing_entry.update(desired_entry)
        self.bump_cache_version()

        # ---- Incremental tag count update ----
        new_tags: set[str] = set(desired_entry.get("tags") or [])
        old_tag_set: set[str] = set(old_tags)
        for tag in old_tag_set - new_tags:
            current = self._tags_count.get(tag, 0)
            if current <= 1:
                self._tags_count.pop(tag, None)
            else:
                self._tags_count[tag] = current - 1
        for tag in new_tags - old_tag_set:
            self._tags_count[tag] = self._tags_count.get(tag, 0) + 1

        # ---- Incremental hash index update ----
        new_sha = (desired_entry.get("sha256", "") or "").lower()
        old_sha = (old_sha256 or "").lower()
        if new_sha != old_sha:
            if old_sha:
                self._hash_index.remove_by_path(file_path)
            if new_sha:
                self._hash_index.add_entry(
                    new_sha,
                    file_path,
                    desired_entry.get('autov3') or None,
                )

        # ---- Incremental version index update ----
        new_civitai = desired_entry.get("civitai")
        if old_civitai != new_civitai:
            temp_old = {
                "file_path": file_path,
                "file_name": old_file_name,
                "civitai": old_civitai,
            }
            cache.remove_from_version_index(temp_old)
            cache.add_to_version_index(existing_entry)

        # ---- Conditional resort (only when sort-key fields changed) ----
        need_resort = False
        _last = cache._last_sort
        sort_key: Optional[str] = _last[0] if _last[0] is not None else None
        if sort_key == "name":
            if (
                old_model_name != desired_entry.get("model_name", "")
                or old_file_name != desired_entry.get("file_name", "")
            ):
                need_resort = True
        elif sort_key == "date":
            if old_modified != float(desired_entry.get("modified", 0.0) or 0.0):
                need_resort = True
        elif sort_key == "size":
            if old_size != int(desired_entry.get("size", 0) or 0):
                need_resort = True

        if need_resort:
            await cache.resort()

        # ---- Targeted SQL update (single row, not full save_cache) ----
        persistent = getattr(self, "_persistent_cache", None)
        if persistent is not None:
            old_item_for_sql: Dict[str, Any] = {
                "file_path": file_path,
                "tags": old_tags,
                "sha256": old_sha256,
            }
            await asyncio.get_event_loop().run_in_executor(
                None,
                persistent.update_single_model,
                self.model_type,
                desired_entry,
                old_item_for_sql,
            )

        return True

    async def update_autov3_for_model(self, model_type: str, file_path: str, autov3: str) -> bool:
        """Persist an AutoV3 hash for a single model (single write path used by the backfill service).

        Locates the in-memory cache entry by ``file_path`` and updates only its
        ``autov3`` field: the in-memory hash index, the SQLite snapshot via
        :meth:`PersistentModelCache.update_single_model`, and the
        ``.metadata.json`` sidecar. sha256, tags, and every other field are
        left untouched, so the persistent delta only ever differs in autov3.

        Returns:
            ``True`` when the entry was found and updated, ``False`` otherwise.
            Never raises — failures are logged and swallowed.
        """
        try:
            if self._cache is None:
                return False

            entry = next(
                (item for item in self._cache.raw_data if item.get('file_path') == file_path),
                None,
            )
            if entry is None:
                return False

            # Normalize once so the memory entry, sidecar, and SQLite row agree.
            autov3 = (autov3 or "").lower()

            # Capture the pre-mutation state so update_single_model only sees
            # an autov3 delta between old and new.
            old_item = dict(entry)

            entry['autov3'] = autov3 or ''

            # Prefer add_entry when a sha256 is known so the sha256 and autov3
            # maps stay in sync; fall back to an autov3-only registration.
            sha_value = entry.get('sha256')
            checked_autov3 = entry.get('autov3') or None
            if sha_value:
                self._hash_index.add_entry(sha_value.lower(), file_path, checked_autov3)
            elif checked_autov3:
                self._hash_index.add_autov3(checked_autov3, file_path)

            persistent = getattr(self, '_persistent_cache', None)
            if persistent is not None:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    persistent.update_single_model,
                    model_type,
                    entry,
                    old_item,
                )

            # Sidecar write-back: JSON null encodes the checked-unavailable
            # state. Skip silently when the sidecar does not exist.
            metadata_path = get_metadata_path(file_path)
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as handle:
                    payload = json.load(handle)
                if not isinstance(payload, dict):
                    payload = {}
                payload['autov3'] = entry['autov3'] or None
                await MetadataManager.save_metadata(metadata_path, payload)

            self.bump_cache_version()
            return True
        except Exception as exc:
            logger.warning("Failed to update AutoV3 for %s: %s", file_path, exc)
            return False

    @staticmethod
    def _cache_entries_differ(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Return ``True`` when two cache-entry dicts differ in any field.

        Tag lists are compared order-insensitively; all other keys use
        standard equality.
        """
        a_tags = sorted(a.get("tags") or [])
        b_tags = sorted(b.get("tags") or [])
        if a_tags != b_tags:
            return True

        all_keys = set(a.keys()) | set(b.keys())
        for key in all_keys:
            if key == "tags":
                continue
            if a.get(key) != b.get(key):
                return True
        return False

    def has_hash(self, sha256: str) -> bool:
        """Check if a model with given hash exists"""
        return self._hash_index.has_hash(sha256.lower())
        
    def get_path_by_hash(self, sha256: str) -> Optional[str]:
        """Get file path for a model by its hash"""
        return self._hash_index.get_path(sha256.lower())
        
    def get_hash_by_path(self, file_path: str) -> Optional[str]:
        """Get hash for a model by its file path"""
        if self._cache is None or not self._cache.raw_data:
            return None
            
        # Iterate through cache data to find matching file path
        for model_data in self._cache.raw_data:
            if model_data.get('file_path') == file_path:
                return model_data.get('sha256')
        
        return None
    
    def get_hash_by_filename(self, filename: str) -> Optional[str]:
        """Get hash for a model by its filename without path"""
        return self._hash_index.get_hash_by_filename(filename)

    # TODO: Adjust this method to use metadata instead of finding the file    
    def get_preview_url_by_hash(self, sha256: str) -> Optional[str]:
        """Get preview static URL for a model by its hash"""
        file_path = self._hash_index.get_path(sha256.lower())
        if not file_path:
            return None

        dir_path = get_preview_dir(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        preview_path = find_preview_file(base_name, dir_path)
        if preview_path:
            return config.get_preview_static_url(preview_path)

        return None
        
    async def get_top_tags(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top tags sorted by count. If limit is 0, return all tags."""
        await self.get_cached_data()
        
        sorted_tags = sorted(
            [{"tag": tag, "count": count} for tag, count in self._tags_count.items()],
            key=lambda x: x['count'],
            reverse=True
        )
        
        if limit == 0:
            return sorted_tags
        return sorted_tags[:limit]

    async def search_tags(
        self, query: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search tags by case-insensitive substring match, sorted by count.

        If query is empty, behaves like get_top_tags (returns top ``limit``
        tags). If limit is 0, all matching tags are returned.
        """
        await self.get_cached_data()

        normalized_query = (query or "").strip().lower()
        if not normalized_query:
            return await self.get_top_tags(limit if limit > 0 else 20)

        matched = [
            {"tag": tag, "count": count}
            for tag, count in self._tags_count.items()
            if normalized_query in tag.lower()
        ]
        matched.sort(key=lambda x: x["count"], reverse=True)

        if limit == 0:
            return matched
        return matched[:limit]

    async def get_base_models(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get base models sorted by count. If limit is 0, return all."""
        cache = await self.get_cached_data()
        
        base_model_counts = {}
        for model in cache.raw_data:
            if 'base_model' in model and model['base_model']:
                base_model = model['base_model']
                base_model_counts[base_model] = base_model_counts.get(base_model, 0) + 1
        
        sorted_models = [{'name': model, 'count': count} for model, count in base_model_counts.items()]
        sorted_models.sort(key=lambda x: x['count'], reverse=True)

        if limit == 0:
            return sorted_models
        return sorted_models[:limit]
        
    @staticmethod
    def find_matching_models(
        raw_data: List[Dict[str, Any]],
        name: str,
        *,
        base_model: Optional[str] = None,
        extensions: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return all cached models matching ``name`` (case-insensitive).

        A name containing a path separator must equal the model's
        folder-relative path; a bare name matches on basename. When
        ``base_model`` is given, confident mismatches are rejected while
        unknowns on either side stay eligible (lenient guard).
        ``extensions`` should be the scanner's own ``file_extensions`` so
        suffix stripping only covers formats the scanner actually indexes;
        when omitted, the shared :data:`WEIGHT_FILE_EXTENSIONS` set is used.
        """
        # Longest first so overlapping suffixes strip correctly.
        exts = sorted(extensions or WEIGHT_FILE_EXTENSIONS, key=len, reverse=True)

        normalized_name = str(name).replace("\\", "/").casefold()
        for ext in exts:
            if normalized_name.endswith(ext):
                normalized_name = normalized_name[: -len(ext)]
                break
        has_path = "/" in normalized_name
        basename = normalized_name.rsplit("/", 1)[-1]

        matches = []
        for model in raw_data:
            file_name = str(model.get("file_name") or "").replace("\\", "/")
            folder = str(model.get("folder") or "").replace("\\", "/").strip("/")
            model_path = f"{folder}/{file_name}" if folder else file_name
            for ext in exts:
                if model_path.casefold().endswith(ext):
                    model_path = model_path[: -len(ext)]
                    break
            if (has_path and model_path.casefold() == normalized_name) or (
                not has_path and model_path.rsplit("/", 1)[-1].casefold() == basename
            ):
                matches.append(model)

        expected_base = str(base_model or "").strip().casefold()
        if expected_base and expected_base != "unknown":
            matches = [
                model
                for model in matches
                if str(model.get("base_model") or "").strip().casefold()
                in ("", "unknown", expected_base)
            ]
        return matches

    async def find_models_by_name(
        self, name: str, *, base_model: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return every cached model matching ``name`` (see ``find_matching_models``)."""
        try:
            cache = await self.get_cached_data()
            return self.find_matching_models(
                cache.raw_data,
                name,
                base_model=base_model,
                extensions=self.file_extensions,
            )
        except Exception as e:
            logger.error(f"Error finding models by name: {e}", exc_info=True)
            return []

    async def get_model_info_by_name(
        self,
        name: str,
        *,
        require_unique: bool = False,
        base_model: Optional[str] = None,
    ):
        """Get model information by name.

        Default mode keeps the legacy first-match/fallback semantics. With
        ``require_unique`` an ambiguous name is a miss, and ``base_model``
        rejects confident base-model mismatches (unknowns stay eligible).
        """
        if require_unique or base_model:
            try:
                matches = await self.find_models_by_name(name, base_model=base_model)
                if require_unique and len(matches) != 1:
                    return None
                return matches[0] if matches else None
            except Exception as e:
                logger.error(f"Error getting model info by name: {e}", exc_info=True)
                return None

        try:
            cache = await self.get_cached_data()

            name_normalized = name.replace("\\", "/")
            name_no_ext = name_normalized
            for ext in (".safetensors", ".ckpt", ".pt", ".bin"):
                if name_no_ext.lower().endswith(ext):
                    name_no_ext = name_no_ext[: -len(ext)]
                    break

            has_path = "/" in name_no_ext
            basename = os.path.basename(name_no_ext) if has_path else name_no_ext
            best_fallback = None

            for model in cache.raw_data:
                file_name = model.get("file_name", "")
                folder = model.get("folder", "")
                file_name_no_ext = file_name
                for ext in (".safetensors", ".ckpt", ".pt", ".bin"):
                    if file_name_no_ext.lower().endswith(ext):
                        file_name_no_ext = file_name_no_ext[: -len(ext)]
                        break
                path_name = f"{folder}/{file_name_no_ext}".replace("\\", "/") if folder else file_name_no_ext

                if name_no_ext == file_name_no_ext or name_no_ext == path_name:
                    return model

                if has_path and file_name_no_ext == basename:
                    if folder and name_no_ext.startswith(folder.replace("\\", "/") + "/"):
                        best_fallback = model
                    elif best_fallback is None:
                        best_fallback = model

            return best_fallback

        except Exception as e:
            logger.error(f"Error getting model info by name: {e}", exc_info=True)
            return None
        
    def get_excluded_models(self) -> List[str]:
        """Get list of excluded model file paths"""
        return self._excluded_models.copy()

    async def update_preview_in_cache(self, file_path: str, preview_url: str, preview_nsfw_level: int) -> bool:
        """Update preview URL in cache for a specific lora
        
        Args:
            file_path: The file path of the lora to update
            preview_url: The new preview URL
            preview_nsfw_level: The NSFW level of the preview
            
        Returns:
            bool: True if the update was successful, False if cache doesn't exist or lora wasn't found
        """
        if self._cache is None:
            return False

        updated = await self._cache.update_preview_url(file_path, preview_url, preview_nsfw_level)
        if updated:
            await self._persist_current_cache()
        return updated

    async def bulk_delete_models(self, file_paths: List[str]) -> Dict[str, Any]:
        """Delete multiple models and update cache in a batch operation
        
        Args:
            file_paths: List of file paths to delete
            
        Returns:
            Dict containing results of the operation
        """
        try:
            if not file_paths:
                return {
                    'success': False,
                    'error': 'No file paths provided for deletion',
                    'results': []
                }
            
            # Keep track of success and failures
            results = []
            total_deleted = 0
            cache_updated = False
            
            # Get cache data
            cache = await self.get_cached_data()
            
            # Track deleted models to update cache once
            deleted_models = []
            
            # Stage each file into the pending-delete staging area and merge
            # all per-file batches into ONE batch for the whole bulk action.
            pending_delete_service = await get_pending_delete_service()
            batch_ids: List[str] = []
            
            for file_path in file_paths:
                if self.is_cancelled():
                    logger.info(f"{self.model_type.capitalize()} Scanner: Bulk delete cancelled by user")
                    break

                try:
                    _require_path_in_library_roots(file_path, self, label="File path")

                    target_dir = os.path.dirname(file_path)
                    base_name = os.path.basename(file_path)
                    file_name, main_extension = os.path.splitext(base_name)

                    # Snapshot the cache entry BEFORE the cache mutation that
                    # runs after the loop - the manifest needs it for undo.
                    cached_entry = None
                    if cache is not None:
                        cached_entry = next(
                            (item for item in cache.raw_data if item.get('file_path') == file_path),
                            None,
                        )

                    batch_id = await pending_delete_service.stage_model_delete(
                        scanner=self,
                        target_dir=target_dir,
                        file_name=file_name,
                        main_extension=main_extension,
                        original_file_path=file_path,
                        cached_entry=cached_entry,
                    )

                    if batch_id is not None:
                        # Artifacts were renamed into staging: the main file is
                        # gone from its original location.
                        batch_ids.append(batch_id)
                        deleted_files = [file_path]
                    else:
                        deleted_files = await delete_model_artifacts(
                            target_dir,
                            file_name,
                            main_extension=main_extension,
                        )
                    
                    if deleted_files:
                        deleted_models.append(file_path)
                        results.append({
                            'file_path': file_path,
                            'success': True,
                            'deleted_files': deleted_files
                        })
                        total_deleted += 1
                    else:
                        results.append({
                            'file_path': file_path,
                            'success': False,
                            'error': 'No files deleted'
                        })
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
                    results.append({
                        'file_path': file_path,
                        'success': False,
                        'error': str(e)
                    })
            
            # Merge every staged per-file batch into ONE undoable batch. On a
            # merge failure (defensive) the response falls back to the
            # constituent batch_ids array so the frontend can undo them
            # sequentially.
            batch_field: Dict[str, Any] = {}
            if batch_ids:
                merged_id = await pending_delete_service.merge_batches(batch_ids)
                if merged_id is not None:
                    batch_field['batch_id'] = merged_id
                else:
                    batch_field['batch_ids'] = list(batch_ids)
            
            # Batch update cache if any models were deleted
            if deleted_models:
                # Update the cache in a batch operation
                cache_updated = await self._batch_update_cache_for_deleted_models(deleted_models)
                
            return {
                'success': True,
                'status': 'cancelled' if self.is_cancelled() else 'success',
                'total_deleted': total_deleted,
                'total_attempted': len(file_paths),
                'cache_updated': cache_updated,
                'results': results,
                **batch_field
            }
            
        except Exception as e:
            logger.error(f"Error in bulk delete: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'results': []
            }
    
    async def _batch_update_cache_for_deleted_models(self, file_paths: List[str]) -> bool:
        """Update cache after multiple models have been deleted
        
        Args:
            file_paths: List of file paths that were deleted
            
        Returns:
            bool: True if cache was updated and saved successfully
        """
        if not file_paths or self._cache is None:
            return False

        if self.is_cancelled():
            logger.info(
                f"{self.model_type.capitalize()} Scanner: Skipping cache update "
                "after cancelled bulk delete"
            )
            return False
            
        try:
            # Get all models that need to be removed from cache
            models_to_remove = [item for item in self._cache.raw_data if item['file_path'] in file_paths]
            
            if not models_to_remove:
                return False
                
            # Update tag counts
            for model in models_to_remove:
                for tag in model.get('tags', []):
                    if tag in self._tags_count:
                        self._tags_count[tag] = max(0, self._tags_count[tag] - 1)
                        if self._tags_count[tag] == 0:
                            del self._tags_count[tag]
            
            # Update hash index
            for model in models_to_remove:
                file_path = model['file_path']
                self._cache.remove_from_version_index(model)
                if hasattr(self, '_hash_index') and self._hash_index:
                    # Get the hash and filename before removal for duplicate checking
                    file_name = os.path.splitext(os.path.basename(file_path))[0]
                    hash_val = model.get('sha256', '').lower()

                    # Remove from hash index
                    self._hash_index.remove_by_path(file_path, hash_val)
                    
                    # Check and clean up duplicates
                    self._cleanup_duplicates_after_removal(hash_val, file_name)
            
            # Update cache data
            self._cache.raw_data = [item for item in self._cache.raw_data if item['file_path'] not in file_paths]

            # Resort cache
            self._cache.rebuild_version_index()
            await self._cache.resort()

            await self._persist_current_cache()

            self.bump_cache_version()

            return True
            
        except Exception as e:
            logger.error(f"Error updating cache after bulk delete: {e}", exc_info=True)
            return False
    
    def _cleanup_duplicates_after_removal(self, hash_val: str, file_name: str) -> None:
        """Clean up duplicate entries in hash index after removing a model
        
        Args:
            hash_val: SHA256 hash of the removed model
            file_name: File name of the removed model without extension
        """
        if not hash_val or not file_name or not hasattr(self, '_hash_index'):
            return
            
        # Clean up hash duplicates if only 0 or 1 entries remain
        if hash_val in self._hash_index._duplicate_hashes:
            if len(self._hash_index._duplicate_hashes[hash_val]) <= 1:
                del self._hash_index._duplicate_hashes[hash_val]
        
        # Clean up filename duplicates if only 0 or 1 entries remain
        if file_name in self._hash_index._duplicate_filenames:
            if len(self._hash_index._duplicate_filenames[file_name]) <= 1:
                del self._hash_index._duplicate_filenames[file_name]

    async def check_model_version_exists(self, model_version_id: int) -> bool:
        """Check if a specific model version exists in the cache

        Args:
            model_version_id: Civitai model version ID

        Returns:
            bool: True if the model version exists, False otherwise
        """
        try:
            normalized_id = int(model_version_id)
        except (TypeError, ValueError):
            return False

        try:
            cache = await self.get_cached_data()
            if not cache:
                return False

            return normalized_id in cache.version_index
        except Exception as e:
            logger.error(f"Error checking model version existence: {e}")
            return False

    async def get_files_for_version(self, model_version_id: int) -> List[Dict[str, Any]]:
        """Get all local file entries for a specific model version (#1058).

        A Civitai model version can have several weight files downloaded;
        unlike the single-valued version_index this returns every entry.

        Args:
            model_version_id: Civitai model version ID

        Returns:
            List[Dict]: Cache entries (may be empty)
        """
        try:
            normalized_id = int(model_version_id)
        except (TypeError, ValueError):
            return []

        try:
            cache = await self.get_cached_data()
            if not cache:
                return []

            getter = getattr(cache, "get_files_by_version_id", None)
            if getter is not None:
                return getter(normalized_id)

            # Fallback for cache implementations without the multi-file index
            entry = cache.version_index.get(normalized_id)
            return [entry] if entry is not None else []
        except Exception as e:
            logger.error(f"Error getting files for model version: {e}")
            return []

    async def get_model_versions_by_id(self, model_id: int) -> List[Dict[str, Any]]:
        """Get all versions of a model by its ID
        
        Args:
            model_id: Civitai model ID
            
        Returns:
            List[Dict]: List of version information dictionaries
        """
        try:
            cache = await self.get_cached_data()
            if not cache:
                return []

            return cache.get_versions_by_model_id(model_id)
        except Exception as e:
            logger.error(f"Error getting model versions: {e}")
            return []
