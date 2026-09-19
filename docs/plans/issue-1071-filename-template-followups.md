# Plan: Filename Template Follow-ups

**Issue:** [#1071 — Lora Renaming](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1071)
**Status:** Core feature **implemented** (2026-09-19, commit `2bc9860b`,
preceded by the settings-tab split in `327da046`). This document records the
follow-up items deliberately left out of that commit, for a future session.

## What shipped in `2bc9860b`

- Per-model-type `download_filename_templates` setting (empty = keep current
  filename; opt-in). Placeholders: `{model_name}`, `{version_name}`,
  `{base_model}`, `{author}`, `{first_tag}`, `{hash_short}`,
  `{original_name}`.
- `calculate_filename_for_model()` in `py/utils/utils.py` renders the
  template; templates containing path separators are rejected.
- Downloads apply the template post-download
  (`DownloadManager._apply_download_filename_template`); rename conflicts
  keep the original name and never fail the download.
- `ModelLifecycleService.rename_model` records `original_file_name` in the
  `.metadata.json` sidecar (first rename wins via `setdefault`).
- Bulk apply: `GET|POST /api/lm/{prefix}/apply-filename-template`
  (`FilenameTemplateUseCase`, shares the auto-organize lock, WS progress type
  `filename_template_progress`).
- Settings UI: "Filename Templates" subsection in the new **Organization**
  settings tab (`templates/components/modals/settings/organization.html`),
  with validation, live preview, and per-type "Apply to Library Now".

Sandbox E2E verified: rename incl. companion files (previews, sidecars),
metadata pointer updates, `original_file_name` recording, idempotency,
conflict handling (failure counted, batch continues), empty-template no-op,
GET variant.

## Follow-up 1 — Reword the empty-template validation message

**Problem:** the empty-template state currently reads "Valid (keep original
filename)" (`settings.filenameTemplates.validation.keepOriginal` in
`locales/en.json`). "Original" is ambiguous — it reads as "restore the
recorded original name", but the semantics are "leave the current filename
untouched" (empty template = no-op, confirmed in E2E).

**Fix:** reword the `en.json` value, e.g. "Valid (leave files unchanged)",
then re-run `python scripts/sync_translation_keys.py` and retranslate the key
in the 9 non-English locales (see `docs/i18n-translation-guidelines.md` §7 —
the owner explicitly asking for translations is the trigger).

## Follow-up 2 — Bulk revert to recorded original filename

**Problem:** renames record `original_file_name` in each model's
`.metadata.json`, but there is no way to undo in bulk. Restoring today means
renaming each model by hand via the existing single-model rename dialog.
Note: the `{original_name}` template placeholder resolves to the **current**
filename stem (`calculate_filename_for_model` reads `file_path` /
`file_name` from the cache entry), so "set template to `{original_name}` and
apply" is **not** a revert path.

**Suggested shape (smallest change):** add a new placeholder, e.g.
`{recorded_original}`, resolved in `calculate_filename_for_model` from
`model_data.get("original_file_name")` (cache entries need to carry the
field — check whether the scanner cache surfaces sidecar extras; if not,
read it in the use case via the metadata loader). Setting the template to
`{recorded_original}` and running "Apply to Library Now" then reverts the
library. Models never renamed render an empty segment → skipped, which is
the desired behaviour.

Alternative shape: a dedicated revert endpoint + button. More code, clearer
UX; only worth it if the placeholder approach proves too obscure.

**Caveats either way:**
- The revert target may collide with an existing file (a file downloaded
  after the rename may already carry that name) — the existing conflict
  handling (count as failure, keep current name) covers this.
- `original_file_name` only exists for models renamed after `2bc9860b`;
  older renames have no recorded original and must be skipped.

## Follow-up 3 — Cross-page refresh after bulk apply

**Problem:** the settings-modal "Apply to Library Now" button calls
`resetAndReload(true)`, which refreshes only the page type currently open.
Applying the checkpoint template while on the loras page leaves the loras
view refreshed but does not touch the checkpoints page state (same
limitation as the existing bulk auto-organize flow in
`static/js/managers/SettingsManager.js#applyFilenameTemplate`).

**Fix options:** broadcast a generic "library changed" event that every
page's state listens to, or accept the limitation (the other page reloads
its cache on next visit). Low priority.
