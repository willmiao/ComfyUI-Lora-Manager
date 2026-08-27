# Recipe Rematch/Repair E2E — Fixtures, Fresh State, Known Gaps

Specialized guidance for recipe rematch/repair E2E runs, extracted from the SKILL.md
main flow. Read the SKILL.md SANDBOX section first — everything here assumes a
sandboxed run.

## Fixture Rules (validated by the task-8 E2E)

Seed the **sandboxed** `recipes_path` with hand-written fixture recipes:

1. **Filename constraint**: each file MUST be named `f"{id}.recipe.json"` **and** the
   in-JSON `id` field MUST equal the filename. Discovery accepts any `*.recipe.json`,
   but persistence resolves the path via `get_recipe_json_path` and
   `_save_recipe_persistently` returns `False` on a mismatch → the fixture would be
   counted as an error.
   - `recipe-a.recipe.json` → in-JSON `"id": "recipe-a"`
2. **File format**: mirror an existing recipe JSON — top-level `id`, `file_path`,
   `title`, `loras`, `fingerprint`, `gen_params`; lora entries per the persistence
   conventions (`hash`, `file_name`, `modelVersionId`, `isDeleted`, ...).
3. **Companion image**: each recipe needs an image (e.g. a `.webp` generated with PIL)
   referenced by `file_path`, used for EXIF verification
   (`ExifUtils.append_recipe_metadata` writes a `"Recipe metadata: ..."` marker; a
   freshly generated `.webp` with no marker is the clean "untouched" control).
4. **autov3 three-state contract**: for L3 (autov3-only, renamed-file) fixtures the
   local model's `.metadata.json` sidecar MUST have the `autov3` key **ABSENT** (the
   "unchecked" state), NOT `""` — `""` is the TERMINAL "checked but unavailable" state
   that L3 deliberately skips. The scanner computes + persists `autov3` from the file
   header during the normal library scan (`model_scanner.py` `_process_model_file`), so
   the live L3 match resolves through the local autov3/hash cache; the
   computed-autov3 branch for unchecked items is covered by the unit suite.
5. **Fixture design for a rematch run** (mirrors the task-8 E2E):
   - `recipe-a`: lora entry `isDeleted=True`, `hash` = 12-char autov3 computed from the
     local model (`calculate_autov3`, `py/utils/file_utils.py`), whose local model file
     was RENAMED after the recipe was written so `file_name` differs (proves L3 match
     without filename).
   - `recipe-b`: parser-convention checkpoint entry (uses `id`, no `modelVersionId`)
     matching a local checkpoint via L2 — the local checkpoint's `.metadata.json` MUST
     carry civitai version data with that `id` so `version_index` contains it (L2
     cannot match otherwise).
   - `recipe-c`: healthy recipe (no deleted entries) → must remain untouched.

The scanner computes and persists model hashes during the library scan, so the sandbox
model dirs just need the model files + `.metadata.json` sidecars. With
`--settings-path`, all derived data lands under the sandbox settings dir (`cache/`,
`backups/`, `logs/`, `stats/`, `wildcards/`), and NO `cache/` appears in the repo root.

## Fresh State Between Entry-Point Runs

Each entry point (global / per-recipe / selection-bulk) must start from the same
deleted state. Between runs (keep a pristine copy in `<sandbox>/recipes-before/`):

```bash
# 1. Reset fixtures to the before-state snapshot
cp <sandbox>/recipes-before/*.recipe.json <sandbox>/recipes/
# 2. Clear the recipe/FTS caches (with --settings-path these live under the sandbox
#    settings dir, NOT <repo-root>/cache)
rm -f <sandbox>/settings/cache/recipe/*.sqlite
rm -rf <sandbox>/settings/cache/fts/*
# 3. Restart the server (fresh process, fresh scan)
python .agents/skills/lora-manager-e2e/scripts/start_server.py \
  --port {PORT} --settings-path <sandbox>/settings --restart --wait --timeout 30 --detach
# 4. Re-verify the server is listening + reload the browser page
```

## Cancellation Testing (KNOWN GAP)

Testing the rematch-cancel path E2E requires a run long enough to cancel mid-flight. A
tiny 3-recipe fixture set completes in **seconds** — too fast to reliably cancel. The
cancel path is currently **unit-covered only** (`rematch_all_recipes` cancellation
tests); do not block an E2E run on cancel-path verification. If you must attempt it,
you would need an artificially large/deferred fixture set to create a cancellable
window — treat this as a research task, not part of the standard E2E.
