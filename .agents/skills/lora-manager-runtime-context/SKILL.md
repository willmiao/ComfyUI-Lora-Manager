---
name: lora-manager-runtime-context
description: Inspect ComfyUI LoRA Manager runtime configuration and local diagnostic state. Use when debugging LoRA Manager issues that require locating or reading settings.json, active library paths, model metadata JSON sidecars, recipe metadata JSON files, example image folders, SQLite caches, symlink maps, download history, aria2 state, or other cache files under the LoRA Manager user config directory.
---

# LoRA Manager Runtime Context

## Core Rules

- Treat runtime state as local user data. Prefer read-only inspection unless the user explicitly asks for mutation.
- Never print secret-like settings values. Redact keys containing `key`, `token`, `secret`, `password`, `auth`, or `credential`, including `civitai_api_key`.
- Resolve paths from the runtime configuration before guessing. In this environment the settings file is normally `/home/miao/.config/ComfyUI-LoRA-Manager/settings.json`, but portable settings can override this through the repository `settings.json`.
- Use the active library when selecting per-library caches and paths. Read `active_library` from settings; fall back to `default` if missing.
- Normalize and expand `~` before comparing paths. Symlinks are common in this repo.

## Quick Start

Use the bundled helper for a safe first pass:

```bash
python .agents/skills/lora-manager-runtime-context/scripts/inspect_runtime_context.py summary
python .agents/skills/lora-manager-runtime-context/scripts/inspect_runtime_context.py caches
```

The script redacts sensitive settings, opens SQLite databases read-only, and reports inaccessible or locked databases as warnings.

For focused checks:

```bash
python .agents/skills/lora-manager-runtime-context/scripts/inspect_runtime_context.py recipes
python .agents/skills/lora-manager-runtime-context/scripts/inspect_runtime_context.py model --path /path/to/model.safetensors
python .agents/skills/lora-manager-runtime-context/scripts/inspect_runtime_context.py sqlite --db /path/to/cache.sqlite --limit 3
```

## Runtime Path Rules

- Settings directory: use `py/utils/settings_paths.py`. Default platform path is `platformdirs.user_config_dir("ComfyUI-LoRA-Manager", appauthor=False)`.
- Settings file: `<settings_dir>/settings.json`.
- Cache root: `<settings_dir>/cache`.
- Canonical cache files:
  - Model cache: `cache/model/<active_library>.sqlite`.
  - Recipe cache: `cache/recipe/<active_library>.sqlite`.
  - Model update cache: `cache/model_update/<active_library>.sqlite`.
  - Recipe FTS: `cache/fts/recipe_fts.sqlite`.
  - Tag FTS: `cache/fts/tag_fts.sqlite`.
  - Symlink map: `cache/symlink/symlink_map.json`.
  - Download history: `cache/download_history/downloaded_versions.sqlite`.
  - aria2 state: `cache/aria2/downloads.json`.
- Legacy cache locations may exist; prefer canonical paths unless diagnosing migrations.

## Data Location Rules

- Model roots come from `settings.folder_paths` and the active library payload under `settings.libraries[active_library]`.
- Model metadata JSON sidecars live next to the model file as `<model basename>.metadata.json`.
- Recipes root is `settings.recipes_path` when it is a non-empty string. If empty, use the first configured LoRA root plus `/recipes`.
- Recipe JSON files are named `*.recipe.json` under the recipes root and may be nested in folders.
- Example image root is `settings.example_images_path`.
- If multiple libraries are configured, example images are stored under `<example_images_path>/<sanitized_library>/<sha256>/`; otherwise they are under `<example_images_path>/<sha256>/`.

## Useful Cache Tables

- Model cache: `models`, `model_tags`, `hash_index`, `excluded_models`.
- Recipe cache: `recipes`, `cache_metadata`.
- Model update cache: `model_update_status`, `model_update_versions`.
- Tag FTS cache: `tags`, `fts_metadata`, plus FTS internal tables.
- Recipe FTS cache: `recipe_rowid`, `fts_metadata`, plus FTS internal tables.
- Download history: `downloaded_model_versions`.

Prefer querying only counts, schema, and a few sample rows unless the user asks for full output.
