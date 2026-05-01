#!/usr/bin/env python3
"""
Migrate metadata from old sidecar JSON format to LoRA Manager's metadata.json format.

This script automatically discovers model folders from LoRA Manager's settings.json,
finds JSON files with the same basename as model files (e.g., `model.json` for
`model.safetensors`), and migrates their content to the corresponding `.metadata.json` files.

Fields migrated:
- "activation text" → civitai.trainedWords (array of trigger words)
- "preferred weight" → usage_tips.strength (LoRA only, skipped for Checkpoint)
- "notes" → notes (user-defined notes)

Supported model types: LoRA, Checkpoint

Usage:
    python scripts/migrate_legacy_metadata.py [--dry-run] [--verbose]

The script will:
1. Read settings.json to find all configured model folders
2. Recursively scan for model files (.safetensors, .ckpt, .pt, .pth, .bin)
3. Find corresponding legacy metadata JSON files
4. Migrate data to .metadata.json files
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
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

APP_NAME = "ComfyUI-LoRA-Manager"
MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
SECRET_PATTERN = re.compile(r"(key|token|secret|password|auth|credential)", re.IGNORECASE)


def resolve_settings_path() -> Path:
    repo_root = Path(__file__).parent.parent.resolve()
    portable = repo_root / "settings.json"
    if portable.exists():
        payload = load_json(portable)
        if isinstance(payload, dict) and payload.get("use_portable_settings") is True:
            return portable

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in {path}: {exc}")
        return {}
    except OSError as exc:
        logger.error(f"Cannot read {path}: {exc}")
        return {}


def expand_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def normalize_path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [expand_path(value)] if value else []
    if isinstance(value, list):
        return [expand_path(item) for item in value if isinstance(item, str) and item]
    return []


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def get_model_roots(settings: dict[str, Any]) -> dict[str, list[str]]:
    roots: dict[str, list[str]] = {}
    active_library = settings.get("active_library") or "default"
    sources = [settings]
    library = settings.get("libraries", {}).get(active_library)
    if isinstance(library, dict):
        sources.insert(0, library)
    for source in sources:
        folder_paths = source.get("folder_paths")
        if isinstance(folder_paths, dict):
            for key, value in folder_paths.items():
                roots.setdefault(key, []).extend(normalize_path_list(value))
    for default_key, folder_key in (
        ("default_lora_root", "loras"),
        ("default_checkpoint_root", "checkpoints"),
        ("default_embedding_root", "embeddings"),
        ("default_unet_root", "unet"),
    ):
        value = settings.get(default_key)
        if isinstance(value, str) and value:
            roots.setdefault(folder_key, []).append(expand_path(value))
    return {key: dedupe(values) for key, values in roots.items()}


def find_model_files(directory: Path) -> list[Path]:
    model_files = []
    for ext in MODEL_EXTENSIONS:
        model_files.extend(directory.rglob(f"*{ext}"))
    return model_files


def find_legacy_metadata(model_path: Path) -> Path | None:
    base_name = model_path.stem
    legacy_path = model_path.with_name(f"{base_name}.json")
    if legacy_path.exists() and legacy_path.is_file():
        return legacy_path
    return None


def load_legacy_metadata(legacy_path: Path) -> dict[str, Any] | None:
    try:
        with open(legacy_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in legacy file {legacy_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading legacy file {legacy_path}: {e}")
        return None


def load_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in metadata file {metadata_path}: {e}. Starting fresh.")
        return {}
    except Exception as e:
        logger.error(f"Error reading metadata file {metadata_path}: {e}")
        return {}


def save_metadata(metadata_path: Path, data: dict[str, Any], dry_run: bool = False) -> bool:
    if dry_run:
        logger.info(f"[DRY RUN] Would save metadata to: {metadata_path}")
        return True
    temp_path = metadata_path.with_suffix(".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, metadata_path)
        return True
    except Exception as e:
        logger.error(f"Error saving metadata to {metadata_path}: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return False


def migrate_metadata(
    legacy_data: dict[str, Any],
    existing_metadata: dict[str, Any],
    model_type: str
) -> dict[str, Any] | None:
    metadata = existing_metadata.copy()
    changes_made = False
    if "civitai" not in metadata:
        metadata["civitai"] = {}
    activation_text = legacy_data.get("activation text")
    if activation_text and isinstance(activation_text, str):
        trigger_words = [
            word.strip()
            for word in activation_text.replace("\n", ",").split(",")
            if word.strip()
        ]
        if trigger_words:
            existing_trained = metadata["civitai"].get("trainedWords", [])
            if not isinstance(existing_trained, list):
                existing_trained = []
            merged = list(dict.fromkeys(existing_trained + trigger_words))
            if merged != existing_trained:
                metadata["civitai"]["trainedWords"] = merged
                changes_made = True
                logger.debug(f"  Migrated activation text: {trigger_words}")
    if model_type == "lora":
        preferred_weight = legacy_data.get("preferred weight")
        if preferred_weight is not None:
            try:
                weight_value = float(preferred_weight)
                usage_tips_str = metadata.get("usage_tips", "{}")
                if isinstance(usage_tips_str, str):
                    try:
                        usage_tips = json.loads(usage_tips_str)
                    except json.JSONDecodeError:
                        usage_tips = {}
                elif isinstance(usage_tips_str, dict):
                    usage_tips = usage_tips_str
                else:
                    usage_tips = {}
                if "strength" not in usage_tips:
                    usage_tips["strength"] = weight_value
                    metadata["usage_tips"] = json.dumps(usage_tips, ensure_ascii=False)
                    changes_made = True
                    logger.debug(f"  Migrated preferred weight: {weight_value}")
            except (ValueError, TypeError) as e:
                logger.warning(f"  Could not parse preferred weight '{preferred_weight}': {e}")
    else:
        if legacy_data.get("preferred weight") is not None:
            logger.debug("  Skipping 'preferred weight' for non-LoRA model")
    notes = legacy_data.get("notes")
    if notes and isinstance(notes, str) and notes.strip():
        existing_notes = metadata.get("notes", "")
        if not existing_notes:
            metadata["notes"] = notes.strip()
            changes_made = True
            logger.debug("  Migrated notes")
        elif notes.strip() not in existing_notes:
            metadata["notes"] = f"{existing_notes}\n\n{notes.strip()}".strip()
            changes_made = True
            logger.debug("  Appended notes")
    return metadata if changes_made else None


def process_model(model_path: Path, model_type: str, dry_run: bool = False) -> bool:
    legacy_path = find_legacy_metadata(model_path)
    if not legacy_path:
        return True
    logger.info(f"Processing: {model_path.name} ({model_type})")
    logger.info(f"  Found legacy metadata: {legacy_path.name}")
    legacy_data = load_legacy_metadata(legacy_path)
    if legacy_data is None:
        return False
    metadata_path = model_path.with_suffix(".metadata.json")
    existing_metadata = load_metadata(metadata_path)
    migrated = migrate_metadata(legacy_data, existing_metadata, model_type)
    if migrated is None:
        logger.info("  No changes needed (fields already exist or no migratable data)")
        return True
    if save_metadata(metadata_path, migrated, dry_run):
        logger.info(f"  ✓ Successfully migrated metadata to: {metadata_path.name}")
        return True
    else:
        logger.error("  ✗ Failed to save metadata")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy metadata JSON files to LoRA Manager's metadata.json format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migrate_legacy_metadata.py
  python scripts/migrate_legacy_metadata.py --dry-run
  python scripts/migrate_legacy_metadata.py --verbose
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying any files"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    settings_path = resolve_settings_path()
    logger.info(f"Using settings: {settings_path}")
    settings = load_json(settings_path)
    if not settings:
        logger.error("Could not load settings.json. Please ensure LoRA Manager is configured.")
        return 1
    roots = get_model_roots(settings)
    if not roots:
        logger.error("No model folders configured in settings.json.")
        return 1
    lora_roots = roots.get("loras", [])
    checkpoint_roots = roots.get("checkpoints", []) + roots.get("unet", [])
    all_roots = []
    for root_list in [lora_roots, checkpoint_roots]:
        for root in root_list:
            path = Path(root)
            if path.exists() and path.is_dir():
                all_roots.append((path, "lora" if root in lora_roots else "checkpoint"))
    if not all_roots:
        logger.error("No valid model folders found.")
        return 1
    logger.info(f"Found {len(lora_roots)} LoRA root(s), {len(checkpoint_roots)} Checkpoint root(s)")
    processed = 0
    migrated = 0
    errors = 0
    skipped = 0
    lora_count = 0
    checkpoint_count = 0
    for root_path, model_type in all_roots:
        logger.info(f"Scanning: {root_path} ({model_type})")
        model_files = find_model_files(root_path)
        logger.debug(f"  Found {len(model_files)} model files")
        for model_path in model_files:
            legacy_path = find_legacy_metadata(model_path)
            if not legacy_path:
                skipped += 1
                continue
            processed += 1
            if process_model(model_path, model_type, dry_run=args.dry_run):
                migrated += 1
                if model_type == "lora":
                    lora_count += 1
                else:
                    checkpoint_count += 1
            else:
                errors += 1
    logger.info("\n" + "=" * 50)
    logger.info("Migration Summary:")
    logger.info(f"  Models with legacy metadata: {processed}")
    logger.info(f"  Successfully migrated: {migrated}")
    logger.info(f"    - LoRA models: {lora_count}")
    logger.info(f"    - Checkpoint models: {checkpoint_count}")
    logger.info(f"  Errors: {errors}")
    logger.info(f"  Skipped (no legacy file): {skipped}")
    if args.dry_run:
        logger.info("\n  [DRY RUN MODE - No files were modified]")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
