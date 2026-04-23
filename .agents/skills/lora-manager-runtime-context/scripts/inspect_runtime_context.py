#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

SECRET_PATTERN = re.compile(r"(key|token|secret|password|auth|credential)", re.IGNORECASE)
APP_NAME = "ComfyUI-LoRA-Manager"
CACHE_SQLITE = {
    "model": ("model", "{library}.sqlite"),
    "recipe": ("recipe", "{library}.sqlite"),
    "model_update": ("model_update", "{library}.sqlite"),
    "recipe_fts": ("fts", "recipe_fts.sqlite"),
    "tag_fts": ("fts", "tag_fts.sqlite"),
    "download_history": ("download_history", "downloaded_versions.sqlite"),
}
CACHE_JSON = {
    "symlink": ("symlink", "symlink_map.json"),
    "aria2": ("aria2", "downloads.json"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect LoRA Manager runtime state read-only.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary", help="Print redacted settings and resolved paths.")
    subparsers.add_parser("caches", help="Print cache paths and SQLite table summaries.")
    subparsers.add_parser("recipes", help="Print resolved recipes root and recipe JSON count.")

    model_parser = subparsers.add_parser("model", help="Inspect a model metadata sidecar path.")
    model_parser.add_argument("--path", required=True, help="Path to a model file or metadata JSON file.")

    sqlite_parser = subparsers.add_parser("sqlite", help="Inspect a SQLite database read-only.")
    sqlite_parser.add_argument("--db", required=True, help="Path to the SQLite database.")
    sqlite_parser.add_argument("--limit", type=int, default=3, help="Rows to sample from each user table.")

    args = parser.parse_args()
    context = build_context()

    if args.command == "summary":
        print_json(summary_payload(context))
    elif args.command == "caches":
        print_json(caches_payload(context))
    elif args.command == "recipes":
        print_json(recipes_payload(context))
    elif args.command == "model":
        print_json(model_payload(args.path))
    elif args.command == "sqlite":
        print_json(sqlite_payload(Path(args.db).expanduser(), args.limit))
    return 0


def build_context() -> dict[str, Any]:
    settings_path = resolve_settings_path()
    settings = load_json(settings_path)
    settings_dir = settings_path.parent
    active_library = settings.get("active_library") or "default"
    safe_library = sanitize_library_name(str(active_library))
    cache_root = settings_dir / "cache"
    return {
        "settings_path": str(settings_path),
        "settings_dir": str(settings_dir),
        "settings": settings,
        "active_library": active_library,
        "safe_library": safe_library,
        "cache_root": str(cache_root),
        "cache_paths": resolve_cache_paths(cache_root, safe_library),
    }


def resolve_settings_path() -> Path:
    repo_root = find_repo_root()
    portable = repo_root / "settings.json"
    if portable.exists():
        payload = load_json(portable)
        if isinstance(payload, dict) and payload.get("use_portable_settings") is True:
            return portable

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "py").is_dir() and (parent / "standalone.py").exists():
            return parent
    return Path.cwd()


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid JSON: {exc}"}
    except OSError as exc:
        return {"_error": f"unreadable: {exc}"}
    return payload if isinstance(payload, dict) else {"_error": "JSON root is not an object"}


def resolve_cache_paths(cache_root: Path, library: str) -> dict[str, str]:
    paths: dict[str, str] = {}
    for name, (subdir, filename) in CACHE_SQLITE.items():
        paths[name] = str(cache_root / subdir / filename.format(library=library))
    for name, (subdir, filename) in CACHE_JSON.items():
        paths[name] = str(cache_root / subdir / filename)
    return paths


def summary_payload(context: dict[str, Any]) -> dict[str, Any]:
    settings = context["settings"]
    return {
        "settings_path": context["settings_path"],
        "settings_dir": context["settings_dir"],
        "active_library": context["active_library"],
        "settings": redact(settings),
        "model_roots": model_roots(settings, context["active_library"]),
        "recipes_root": str(resolve_recipes_root(settings, context["active_library"]) or ""),
        "example_images": example_images_payload(settings, context["active_library"]),
        "cache_root": context["cache_root"],
        "cache_paths": context["cache_paths"],
    }


def caches_payload(context: dict[str, Any]) -> dict[str, Any]:
    caches: dict[str, Any] = {}
    for name, path_string in context["cache_paths"].items():
        path = Path(path_string)
        item: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else None,
        }
        if path.suffix == ".sqlite":
            item["sqlite"] = sqlite_payload(path, limit=0)
        elif path.suffix == ".json":
            item["json"] = json_file_summary(path)
        caches[name] = item
    return {"active_library": context["active_library"], "caches": caches}


def recipes_payload(context: dict[str, Any]) -> dict[str, Any]:
    root = resolve_recipes_root(context["settings"], context["active_library"])
    files: list[str] = []
    if root and root.exists():
        files = [str(path) for path in sorted(root.rglob("*.recipe.json"))[:20]]
    return {
        "recipes_root": str(root or ""),
        "exists": bool(root and root.exists()),
        "recipe_json_count": count_recipe_files(root),
        "sample_recipe_json": files,
        "recipe_cache": context["cache_paths"].get("recipe"),
    }


def model_payload(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    metadata_path = path if path.name.endswith(".metadata.json") else path.with_suffix(".metadata.json")
    payload = {
        "input_path": str(path),
        "metadata_path": str(metadata_path),
        "model_exists": path.exists(),
        "metadata_exists": metadata_path.exists(),
    }
    if metadata_path.exists():
        data = load_json(metadata_path)
        payload["metadata_summary"] = redact(summarize_value(data))
    return payload


def sqlite_payload(path: Path, limit: int = 3, allow_copy: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "tables": {}}
    if not path.exists():
        return result
    try:
        conn = connect_sqlite_readonly(path)
    except sqlite3.Error as exc:
        result["error"] = str(exc)
        return result
    try:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        for table_row in table_rows:
            table = table_row["name"]
            columns = [
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
            ]
            table_info: dict[str, Any] = {"columns": columns}
            try:
                table_info["count"] = conn.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table)}"
                ).fetchone()[0]
            except sqlite3.Error as exc:
                table_info["count_error"] = str(exc)
            if limit > 0 and columns and not is_internal_sqlite_table(table):
                try:
                    rows = conn.execute(
                        f"SELECT * FROM {quote_identifier(table)} LIMIT ?", (limit,)
                    ).fetchall()
                    table_info["sample"] = [redact(dict(row)) for row in rows]
                except sqlite3.Error as exc:
                    table_info["sample_error"] = str(exc)
            result["tables"][table] = table_info
    except sqlite3.Error as exc:
        fallback = sqlite_copy_payload(path, limit, str(exc)) if allow_copy else None
        if fallback is not None:
            result.update(fallback)
        else:
            result["error"] = str(exc)
    finally:
        conn.close()
    return result


def connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    errors: list[str] = []
    for query in ("mode=ro", "mode=ro&immutable=1"):
        try:
            conn = sqlite3.connect(f"file:{path}?{query}", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:
            errors.append(f"{query}: {exc}")
    raise sqlite3.OperationalError("; ".join(errors))


def sqlite_copy_payload(path: Path, limit: int, original_error: str) -> dict[str, Any] | None:
    try:
        with tempfile.TemporaryDirectory(prefix="lm-cache-inspect-") as temp_dir:
            copy_path = Path(temp_dir) / path.name
            shutil.copy2(path, copy_path)
            payload = sqlite_payload(copy_path, limit, allow_copy=False)
            payload["path"] = str(path)
            payload["inspected_copy"] = True
            payload["original_error"] = original_error
            return payload
    except Exception:
        return None


def json_file_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    data = load_json(path)
    return {"exists": True, "summary": redact(summarize_value(data))}


def model_roots(settings: dict[str, Any], active_library: str) -> dict[str, list[str]]:
    roots: dict[str, list[str]] = {}
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


def resolve_recipes_root(settings: dict[str, Any], active_library: str) -> Path | None:
    recipes_path = settings.get("recipes_path")
    library = settings.get("libraries", {}).get(active_library)
    if isinstance(library, dict) and isinstance(library.get("recipes_path"), str):
        recipes_path = library["recipes_path"] or recipes_path
    if isinstance(recipes_path, str) and recipes_path.strip():
        return Path(expand_path(recipes_path.strip()))
    lora_roots = model_roots(settings, active_library).get("loras") or []
    return Path(lora_roots[0]) / "recipes" if lora_roots else None


def example_images_payload(settings: dict[str, Any], active_library: str) -> dict[str, Any]:
    root = settings.get("example_images_path") or ""
    libraries = settings.get("libraries")
    library_count = len(libraries) if isinstance(libraries, dict) else 0
    scoped = library_count > 1
    root_path = Path(expand_path(root)) if isinstance(root, str) and root else None
    library_root = root_path / sanitize_library_name(active_library) if root_path and scoped else root_path
    return {
        "root": str(root_path or ""),
        "uses_library_scoped_folders": scoped,
        "library_root": str(library_root or ""),
    }


def count_recipe_files(root: Path | None) -> int:
    if not root or not root.exists():
        return 0
    return sum(1 for _ in root.rglob("*.recipe.json"))


def normalize_path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [expand_path(value)] if value else []
    if isinstance(value, list):
        return [expand_path(item) for item in value if isinstance(item, str) and item]
    return []


def expand_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def sanitize_library_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name or "default")
    return safe or "default"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def redact(value: Any, key: str = "") -> Any:
    if key and SECRET_PATTERN.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def summarize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: summarize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return {
            "type": "array",
            "length": len(value),
            "first": summarize_value(value[0]) if value else None,
        }
    return value


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def is_internal_sqlite_table(table: str) -> bool:
    return table.startswith("sqlite_") or table.endswith(("_data", "_idx", "_docsize", "_config", "_content"))


def print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
