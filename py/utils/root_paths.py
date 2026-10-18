"""Path identity helpers for model roots.

ComfyUI hands its model folders over in whatever spelling the host uses --
``os.path.normpath()`` output, which is all backslashes on Windows -- while LoRA
Manager's own root lists and cached model paths are forward-slashed. Comparing
the two spellings as raw strings makes one directory look like two roots, so every
root identity check goes through :func:`normalize_root_identity` (issue #1146).
"""

from __future__ import annotations

import os
import posixpath


def normalize_root_identity(path: str) -> str:
    """Return the comparable identity of a model root path.

    Folds the separator style (``\\`` and ``/`` are both accepted as separators,
    because the host may spell a Windows path either way), redundant and trailing
    separators, and the case where the filesystem does not distinguish it: Windows
    compares whole paths case-insensitively, and every platform folds a drive
    letter (``E:`` == ``e:``). Symlinks are never resolved -- business paths stay
    business paths, matching the rest of the codebase.
    """

    if not isinstance(path, str):
        return ""
    candidate = path.strip()
    if not candidate:
        return ""

    normalized = posixpath.normpath(candidate.replace("\\", "/"))
    if os.name == "nt" or (len(normalized) >= 2 and normalized[1] == ":"):
        return normalized.lower()
    return normalized


def normalize_root_spelling(path: str) -> str:
    """Case-preserving counterpart of :func:`normalize_root_identity`.

    Same separator and redundancy folding, but keeps the original casing. Use it
    to slice a relative part out of a path with offsets computed from the
    identity -- the identity may have folded case, so slicing it directly would
    lose the on-disk spelling.
    """

    if not isinstance(path, str):
        return ""
    candidate = path.strip()
    if not candidate:
        return ""

    return posixpath.normpath(candidate.replace("\\", "/"))
