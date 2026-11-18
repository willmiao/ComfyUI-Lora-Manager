# Plan: Filename Template Follow-ups

**Issue:** [#1071 — Lora Renaming](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1071)
**Status:** Core feature **implemented** (2026-09-19, commit `2bc9860b`,
preceded by the settings-tab split in `327da046`). Follow-ups 1 and 2 were
resolved together on 2026-09-19 by redefining the empty template as
"revert to recorded original filename" (see below). Follow-up 3 remains open.

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

## Follow-ups 1 & 2 — RESOLVED: empty template = revert to recorded original

Follow-up 1 asked to reword the ambiguous "Valid (keep original filename)"
empty-template message; Follow-up 2 asked for a bulk revert to the recorded
`original_file_name`. Both were resolved by a single semantic change: **an
empty template now means "restore the recorded original filename"** instead of
"leave the current filename untouched".

Rationale: for never-renamed models a revert is a no-op (no recorded
original), for renamed models it restores the pre-rename name, and new
downloads with an empty template keep the download name as before — so the
two contexts (download path and bulk apply) share one coherent meaning, and
no separate revert feature or `{recorded_original}` placeholder is needed.

Implemented changes:

- `FilenameTemplateUseCase._process_model`: an empty template now resolves
  the target name from the sidecar's `original_file_name` via the injected
  `metadata_loader` (default `load_local_metadata`); models without a
  recorded original or whose original matches the current name are skipped.
  Cache entries do not project `original_file_name`, so the sidecar is read
  per model.
- `SettingsManager.js`: removed the empty-template early return and the
  apply-button disable (`updateFilenameTemplateApplyButton` deleted — the
  button is now always enabled). The browser-native `confirm()` was replaced
  with `filenameTemplateConfirmModal`
  (`templates/components/modals/confirm_modals.html`), a **self-managed**
  modal (like `DirectoryPickerModal`, NOT registered with ModalManager):
  ModalManager's "close current modal on open" behavior would kill the
  settings modal underneath. It stacks via `z-index: 10010`
  (`delete-modal.css`), handles ESC in capture phase with
  `stopPropagation`, and shows apply vs revert wording
  (`modals.filenameTemplateConfirm.titleApply` / `titleRevert` /
  `revertButton`; messages reuse `settings.filenameTemplates.confirmApply` /
  `confirmRevert`).
- `locales/en.json`: reworded `help` / `applyHelp`, replaced
  `validation.keepOriginal` with `validation.restoreOriginal`
  ("Valid (empty template restores original filenames)"), added
  `confirmRevert`, removed the now-unused `emptyTemplateInfo`. Other locales
  re-synced with `[TODO: Translate]` placeholders — retranslation waits for
  the feature owner's request per `docs/i18n-translation-guidelines.md` §7.
- Tests: revert / no-record-skip / same-name-skip cases in
  `tests/services/test_use_cases.py`; modal confirm-and-revert and
  cancel paths in
  `tests/frontend/managers/settingsManager.filenameTemplates.test.js`.

Sandbox E2E verified (standalone server, sandboxed settings + library under
`/tmp`, 2026-09-19): template apply renames and records
`original_file_name`; empty-template apply reverts to the recorded name;
revert target occupied by a newer file counts as failure and keeps the
current name; models without a recorded original are skipped;
apply → revert → re-apply cycles repeat cleanly.

Standing caveats (unchanged):

- The revert target may collide with an existing file — the existing conflict
  handling (count as failure, keep current name) covers this.
- `original_file_name` only exists for models renamed after `2bc9860b`;
  older renames have no recorded original and are skipped.
- `original_file_name` is kept (not cleared) after a revert, so
  apply → revert → re-apply stays repeatable.

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

**Decision (2026-11-18): accepted, not implemented.** The manager UI is a
multi-page app (each page is its own document load, `templates/loras.html`
etc.), so visiting the other page refetches its models; the only stale window
is a back/forward-cache restore, where a manual refresh fixes it. The
`models_changed` WebSocket broadcast already exists but is consumed only by
the ComfyUI graph-page widget (`web/comfyui/loras_widget_utils.js`), not by
the manager UI. Wiring a cross-page refresh therefore means adding a new
broadcast consumer to every page's state for a cosmetic, self-healing case —
not worth the regression surface. Scoped applies are unaffected because they
run on the page whose models they rename.

## Follow-up 4 — Folder/selection-scoped apply (implemented 2026-11-18)

**Problem:** the only way to apply the filename template was the library-wide
"Apply to Library Now" per model type. Users with a handful of random
alphanumeric filenames had to rename the whole library (or rename files one by
one from the edit modal) to fix a few files.

**Design:** reuse the auto-organize scoping pattern — the same `file_paths`
narrowing plus a new `folder_paths` narrowing, with a dry run so the
confirmation quotes real counts.

Backend (`apply-filename-template`, POST body or GET query for the extension):

- `file_paths`: selected model files (existing).
- `folder_paths`: absolute directories, recursive, validated with
  `_require_path_in_library_roots` (business-path space, abspath not realpath).
  The UI passes every directory that a merged sidebar folder resolves to, so a
  folder that exists under several roots is covered. An explicitly empty list
  raises instead of silently widening to the whole library; a folder outside
  the roots returns 400.
- `dry_run`: computes the same targets without renaming, no progress events and
  no `models-changed` broadcast. The plan lands in `planned_moves`
  (`{model, from, to}`), and `AutoOrganizeResult.to_dict()` labels it
  "Filename template dry run".
- Both scopes may be combined (intersection); no scope keeps the old
  library-wide behaviour.

Frontend entry points, both sharing `buildFilenameTemplateConfirmation()`
(`static/js/utils/filenameTemplateScope.js`) and the generic
`showConfirmationModal()`:

- Bulk selection: Organize section → "Apply Filename Template to Selected"
  (`BulkManager.applyFilenameTemplateToSelectedModels`), enabled only for
  loras/checkpoints/embeddings — the model types with a template editor.
- Sidebar folder context menu: "Apply filename template to this folder"
  (`SidebarManager.applyFilenameTemplateToFolder`), recursive over the folder
  and its subfolders. Hidden on pages without a template (recipes,
  other, workflows).
- Both dry-run first, show totals (`success`/`skipped`/`failures`), and adapt
  the wording when the template is empty (scoped apply would restore recorded
  original filenames).

Verification: backend unit tests for folder scope (recursive, prefix-sharing
sibling excluded), outside-root rejection, empty-scope rejection and dry-run
plan; route tests for POST/GET `folder_paths`, `dry_run` (no progress/no
broadcast) and 400 mapping; frontend tests for the API client (preview body,
scoped apply bodies, the `{count}`-only success toast), the bulk flow (preview →
confirm → apply, cancel, nothing-to-rename) and the folder flow (multi-candidate
resolution, cancel, gating). Full pytest (4645 passed) and the full JS suite
(2223 tests) pass. All 18 new keys are translated in the 9 non-English locales;
the two scope strings are only used in the "Applying ... to {type}" progress
sentence, which is why ru/de use the case that fits that preposition.

Caveats: the recursive folder scope can still rename a large subtree if the
user points at a library root; the dry-run counts are what makes that visible.
Follow-up 3 does not affect these scoped paths: both entry points run on the
page of the model type they rename, so the page refreshes itself.
