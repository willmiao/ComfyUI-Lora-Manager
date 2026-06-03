#!/usr/bin/env python3
"""
Restore original filenames by removing leftover 4-char hash suffixes.

When LoRA Manager's old duplicate filename resolver ran, it appended
``-{first4ofSHA256}`` to duplicate filenames, e.g.::

    my_lora.safetensors  →  my_lora-a3f7.safetensors

With full-path LoRA syntax now available (``<lora:subfolder/name:1.0>``),
these suffixes are unnecessary.  This script detects such files and, with
your confirmation, restores their original names.

The same suffix pattern is also used by the download conflict handler
(``{name}-{hash}.{ext}``).  To avoid false positives, this script skips
any file whose original name already exists in the same directory — those
were likely added by a download conflict, not the old resolver.

Usage::

    # Detect only (dry-run, default)
    python scripts/restore_suffixed_filenames.py

    # Detect + restore (with confirmation prompt)
    python scripts/restore_suffixed_filenames.py --apply

After restoring filenames, run **Rebuild Cache** in the LoRA Manager
Doctor panel to refresh the model cache.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

APP_NAME = "ComfyUI-LoRA-Manager"
MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
PREVIEW_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp4", ".webm", ".mov",
}

# Matches filenames like "my_lora-a3f7.safetensors"
# Groups: (base_name, 4-char-hex, extension)
_SUFFIX_RE = re.compile(r"^(.+)-([0-9a-f]{4})(\.[^.]+)$")


# ── helpers (copied from migrate_legacy_metadata.py for consistency) ──────────


def resolve_settings_path() -> Path:
    repo_root = Path(__file__).parent.parent.resolve()
    portable = repo_root / "settings.json"
    if portable.exists():
        payload = _load_json(portable)
        if isinstance(payload, dict) and payload.get("use_portable_settings") is True:
            return portable

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _expand_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _normalize_path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_expand_path(value)] if value else []
    if isinstance(value, list):
        return [_expand_path(item) for item in value if isinstance(item, str) and item]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def get_model_roots(settings: dict[str, Any]) -> dict[str, list[str]]:
    """Extract model folder roots from LoRA Manager settings.

    Returns ``{model_type: [path, ...]}`` where *model_type* is one of
    ``loras``, ``checkpoints``, ``embeddings``, ``unet``, etc.

    Both primary (``folder_paths``) and extra (``extra_folder_paths``)
    paths are included.  Extra paths can be configured via the UI at
    Settings → Model Libraries → Extra Folder Paths.
    """
    roots: dict[str, list[str]] = {}
    active_library = settings.get("active_library") or "default"
    sources = [settings]
    library = settings.get("libraries", {}).get(active_library)
    if isinstance(library, dict):
        sources.insert(0, library)
    for source in sources:
        # Primary folder paths.
        folder_paths = source.get("folder_paths")
        if isinstance(folder_paths, dict):
            for key, value in folder_paths.items():
                roots.setdefault(key, []).extend(_normalize_path_list(value))
        # Extra folder paths (Settings → Model Libraries → Extra Folder Paths).
        extra_folder_paths = source.get("extra_folder_paths")
        if isinstance(extra_folder_paths, dict):
            for key, value in extra_folder_paths.items():
                roots.setdefault(key, []).extend(_normalize_path_list(value))
    for default_key, folder_key in (
        ("default_lora_root", "loras"),
        ("default_checkpoint_root", "checkpoints"),
        ("default_unet_root", "unet"),
        ("default_embedding_root", "embeddings"),
    ):
        value = settings.get(default_key)
        if isinstance(value, str) and value:
            roots.setdefault(folder_key, []).append(_expand_path(value))
    return {key: _dedupe(values) for key, values in roots.items()}


def find_model_files(directory: Path) -> list[Path]:
    """Recursively find all model files in *directory*."""
    files: list[Path] = []
    for ext in MODEL_EXTENSIONS:
        files.extend(directory.rglob(f"*{ext}"))
    return files


# ── core detection logic ──────────────────────────────────────────────────────


def check_file(path: Path) -> tuple[str, str, str] | None:
    """If *path* matches the suffix pattern, return ``(base_name, hex, ext)``.

    Returns ``None`` when:
    * The filename does not match the pattern, or
    * The original name (without the suffix) already exists in the same
      directory (likely a download-conflict rename, not a doctor rename).
    """
    match = _SUFFIX_RE.match(path.name)
    if not match:
        return None

    base_name = match.group(1)
    hex_part = match.group(2)
    extension = match.group(3)
    orig_name = base_name + extension
    orig_path = path.with_name(orig_name)

    # Safety: skip if the original name already exists.
    if orig_path.exists():
        return None

    return base_name, hex_part, extension


def scan_roots(
    roots: dict[str, list[str]],
) -> dict[str, list[tuple[Path, str, str, str]]]:
    """Scan all model roots and return detected files grouped by model type.

    Returns ``{model_type: [(full_path, base_name, hex, ext), ...]}``.
    """
    results: dict[str, list[tuple[Path, str, str, str]]] = {}

    for model_type, root_list in roots.items():
        type_results: list[tuple[Path, str, str, str]] = []
        for root in root_list:
            root_path = Path(root)
            if not root_path.is_dir():
                continue
            for model_file in find_model_files(root_path):
                match = check_file(model_file)
                if match:
                    type_results.append((model_file, *match))
        if type_results:
            results[model_type] = type_results

    return results


def rename_file(
    path: Path, base_name: str, extension: str, dry_run: bool
) -> bool:
    """Rename *path* to ``{base_name}{extension}``.

    Also renames sidecar files (``.metadata.json``, ``.civitai.info``) and
    preview images.  Returns ``True`` on success.
    """
    new_path = path.with_name(base_name + extension)
    old_stem = path.with_suffix("")  # /dir/base_name-hex  (no ext)
    new_stem = new_path.with_suffix("")  # /dir/base_name  (no ext)

    if dry_run:
        logger.info("  would rename:  %s", path.name)
        logger.info("             ->  %s", new_path.name)
        return True

    try:
        os.rename(path, new_path)
    except OSError as exc:
        logger.error("  FAILED to rename %s: %s", path.name, exc)
        return False

    # Rename sidecar metadata files.
    for suffix in (".metadata.json", ".civitai.info"):
        old_sidecar = old_stem.with_name(old_stem.name + suffix)
        new_sidecar = new_stem.with_name(new_stem.name + suffix)
        if old_sidecar.exists():
            try:
                os.rename(old_sidecar, new_sidecar)
            except OSError as exc:
                logger.warning("  could not rename sidecar %s: %s", old_sidecar.name, exc)

    # Rename preview images.
    for preview_ext in PREVIEW_EXTENSIONS:
        old_preview = old_stem.with_name(old_stem.name + preview_ext)
        new_preview = new_stem.with_name(new_stem.name + preview_ext)
        if old_preview.exists():
            try:
                os.rename(old_preview, new_preview)
            except OSError as exc:
                logger.warning("  could not rename preview %s: %s", old_preview.name, exc)

    logger.info("  renamed: %s  ->  %s", path.name, new_path.name)
    return True


# ── report helpers ────────────────────────────────────────────────────────────


def print_report(results: dict[str, list[tuple[Path, str, str, str]]]) -> int:
    """Print a human-readable report of detected files.  Returns total count."""
    if not results:
        logger.info("No leftover suffixed filenames detected.")
        return 0

    total = 0
    for model_type in sorted(results):
        entries = results[model_type]
        total += len(entries)
        label = model_type.capitalize()
        logger.info("")
        logger.info("─" * 50)
        logger.info("  %s  (%d file(s))", label, len(entries))
        logger.info("─" * 50)
        for path, base_name, hex_part, ext in sorted(entries):
            logger.info("  %s  →  %s%s", path.name, base_name, ext)

    logger.info("")
    logger.info("=" * 50)
    logger.info("  Total: %d file(s) with leftover suffixes.", total)
    logger.info("=" * 50)
    return total


def prompt_user(count: int) -> bool:
    """Ask the user whether to proceed with the rename."""
    try:
        answer = input(
            f"\nRestore {count} file(s) to their original names? [y/N] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect and restore model filenames that have leftover "
            "4-character hash suffixes from the old conflict resolver."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/restore_suffixed_filenames.py\n"
            "  python scripts/restore_suffixed_filenames.py --apply\n"
            "  python scripts/restore_suffixed_filenames.py --apply --yes\n"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files (with confirmation prompt unless --yes is given)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt (implies --apply)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect only — show what would be renamed without making changes",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve settings.
    settings_path = resolve_settings_path()
    logger.info("Settings: %s", settings_path)
    settings = _load_json(settings_path)
    if not settings:
        logger.error("Could not load settings.json.  Is LoRA Manager configured?")
        return 1

    roots = get_model_roots(settings)
    if not roots:
        logger.error("No model folders found in settings.")
        return 1

    # Log which roots are being scanned.
    for model_type, root_list in roots.items():
        for root in root_list:
            logger.info("Scanning %s: %s", model_type, root)

    # Detect.
    results = scan_roots(roots)
    total = print_report(results)

    if total == 0:
        return 0

    # Determine mode.
    dry_run = not args.apply and not args.yes

    if dry_run:
        logger.info("\n[Dry-run mode — no files modified]")
        logger.info("Run with --apply to restore filenames.")
        return 0

    # Confirm unless --yes.
    if not args.yes:
        if not prompt_user(total):
            logger.info("Aborted.")
            return 0

    # Rename.
    logger.info("")
    success = 0
    fail = 0
    for model_type in sorted(results):
        entries = results[model_type]
        logger.info("")
        logger.info("─" * 50)
        logger.info("  Restoring %s  (%d file(s))", model_type, len(entries))
        logger.info("─" * 50)
        for path, base_name, hex_part, ext in sorted(entries):
            ok = rename_file(path, base_name, ext, dry_run=False)
            if ok:
                success += 1
            else:
                fail += 1

    logger.info("")
    logger.info("=" * 50)
    logger.info("  Done: %d restored, %d failed.", success, fail)
    logger.info("=" * 50)
    logger.info("")
    logger.info("  ⚠  Please run Rebuild Cache in the LoRA Manager")
    logger.info("     Doctor panel to refresh the model cache.")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
