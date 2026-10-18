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
