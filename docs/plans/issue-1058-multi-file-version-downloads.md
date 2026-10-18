# Plan: Multi-File Downloads Within a Single CivitAI Model Version

**Issue:** [#1058 — Cannot download multiple file variants from the same model version](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1058)
**Status:** v2 — revised after adversarial review (backend correctness + frontend/tests)
**Scope:** CivitAI/CivArchive downloads of `lora`, `checkpoint`, `embedding` model types. HuggingFace downloads are out of scope (already per-file).

> v2 changelog: incorporated 18 review findings. Key changes vs v1:
> shared file resolver + `resolved_version_id` for the gate (R1); `file_params` normalization at API boundary (R2); D2 hash-matching rule fixed for empty-hash cases (R6/R7); D3 extended to re-point `version_index` on removal (R4); D4 replaced with a child table (R3); `delete_model_version` interaction documented (R5); `ModelVersionsTab` surface added to phase 2 (F6); phase-2 multi-file loop requires a reload-deferred download variant (F7); queue-retry `file_params=NULL` known issue recorded (R9); test-fixture gaps and revised estimates (F10).

---

## 1. Problem Statement

A CivitAI model version can contain multiple downloadable weight files (e.g. fp16/fp32, safetensors/ckpt, different sizes). LoRA Manager already has a working file-selection pipeline (frontend file dialog → `fileParams` → backend file matching), but downloaded state is tracked at the **model-version** level. After any single file of a version is downloaded:

1. The version is marked **In Library** and the file-selection entry point disappears.
2. The backend rejects further download attempts for that version.

There is no way to download the remaining files of the same version through LoRA Manager.

## 2. Current State (verified against code; all references confirmed by review)

### 2.1 Download gating — backend (`py/services/download_manager.py`)

`_execute_original_download` enforces two version-level gates:

- **Library gate, early** (lines 1157–1184, before metadata fetch, fires when `model_version_id` given) and **late** (lines 1350–1376, fires only when `model_version_id is None`): `scanner.check_model_version_exists(version_id)` across lora/checkpoint/embedding scanners → hard error `"Model version already exists in ... library"`.
- **History gate** (lines 1238–1279): when `skip_previously_downloaded_model_versions` setting is on, `_has_been_downloaded(model_type, version_id)` → silent skip. History DB primary key is `(model_type, version_id)` (`py/services/downloaded_version_history_service.py:61`).

File selection works: `file_params {id, type, format, size, fp}` is matched against `version_info.files` (lines 1498–1569), **but only under `if file_params and model_version_id:` (line 1499)** — with `model_id`-only requests the selection silently falls back to the primary file (1571–1619). `file_params` currently carries no file `name` or hash.

### 2.2 Downloaded-state surfacing — backend (`py/routes/handlers/model_handlers.py`)

`get_civitai_versions` (lines 2148–2188) sets per-version `existsLocally` via `cache.version_index.get(version_id)` (plus a single `localPath` from that entry) and `hasBeenDownloaded` via the history service. No per-file granularity.

### 2.3 Frontend blockers (`static/js/managers/DownloadManager.js`)

Three independent gates prevent re-entering the file dialog:

1. **Line 598:** file-select badge rendered only when `modelFiles.length > 1 && !existsLocally`.
2. **Lines 666–681 (`updateNextButtonState`):** Next button disabled with "Already in Library" when `currentVersion.existsLocally`.
3. **Lines 784–787 (`proceedToLocation`):** toast + abort when `currentVersion.existsLocally`.

The badge path (`confirmFileSelection` lines 737–759 → `proceedToLocationContent` → `startDownload` single mode → `executeDownloadWithProgress` → POST `file_params`, `static/js/api/baseModelApi.js:1236–1250`) has **zero** `existsLocally` guards (all 12 occurrences enumerated; none on this path; `import/DownloadManager.js` has none either). The `.exists-locally` CSS class is purely visual (`download-modal.css:496–499`). **Making the badge visible again is sufficient to unlock the flow** for phase 1.

Post-download refresh is clean: the modal closes and `resetAndReload(true)` performs a full library refetch (`DownloadManager.js:1063`); dialog reopen resets state and refetches versions with no client-side cache. No same-session staleness.

### 2.4 Local identity of the downloaded file

`LoraMetadata/CheckpointMetadata/EmbeddingMetadata.from_civitai_info(version_info, file_info, ...)` (`py/utils/models.py:245–369`) persists:

- `sha256` = `file_info.hashes.SHA256` (lowercased, defaults to `""`) — a stable per-file identity;
- `civitai` = the full `version_info` payload (including the `files` list).

Metadata refresh (`metadata_sync_service.py:104–105`) replaces the `civitai` blob wholesale but never overwrites top-level `sha256`; `verify_duplicate_hashes` (481–526) corrects it to the on-disk hash. Top-level-sha256 matching is refresh-robust.

**Caveats (review R6/R7):**
- SHA256 is not guaranteed: CivArchive's transform only sets `hashes` when source data carries it (`civarchive_client.py:185–189`); `from_civitai_info` defaults to `""`.
- Name fallback is unreliable exactly when it matters: local `file_name` is extension-less (`models.py:264`) and `generate_unique_filename` rewrites it with a hash suffix on conflict (`download_manager.py:1125–1136`); checkpoints with `hash_status='pending'` keep empty sha256 until on-demand hashing (`model_scanner.py:1232–1240`).

### 2.5 Version index collision (pre-existing hazard)

`ModelCache.version_index` is single-valued (`model_cache.py:133`: `version_index[version_id] = item`). Two files of the same version in the library → second entry overwrites the first; `remove_from_version_index` (lines 151–181) drops the whole version key when the indexed entry is removed, even if a sibling file remains. ~10 read sites depend on this index (48 grep touch points total; readers include `recipe_scanner.py:2682–2726`, `recipe_format.py:37–40`, `misc_handlers.py:2440–2444`, `model_handlers.py`, `model_scanner.check_model_version_exists:2444`).

Review correction (F3): bulk paths `remove_models` (`model_scanner.py:2376`) and `update_single_model_cache` (`:1689`) call `rebuild_version_index()` right after, so a sibling re-enters the index in those flows — the hazard is narrower than v1 stated, but direct `remove_from_version_index` callers (e.g. `model_scanner.py:1018`) still drop the key, and the user-visible artifact in phase 1 is real: `localPath` in the dialog flips to whichever file was indexed last.

### 2.6 Entry points that send / don't send `file_params` (fully enumerated by review)

**Send `file_params` (user-initiated dialog flows only):** `DownloadManager.js:1611–1639` (single mode). API surface accepting arbitrary JSON `file_params`: GET `/api/lm/download-model-get` (`model_handlers.py:1634–1686`), POST `/api/lm/downloads/queue/add` (`model_handlers.py:1799–1832`).

**Never send `file_params` (keep version-level semantics):** batch download (`DownloadManager.js:1756–1766`; batch also filters out in-library versions at `:1648`), `downloadVersionWithDefaults` (`:1810–1830`), recipe import (`import/DownloadManager.js:269–276`), bulk missing-LoRA (`BulkMissingLoraDownloadManager.js:292–299`), `RecipeModal.js:1728–1736`, `ModelVersionsTab.js:1427`. `web/comfyui/` and `vue-widgets/src` contain **no** download triggers at all (grep-verified). `py/services/use_cases/` has only `download_model_use_case.py` (pass-through).

### 2.7 Paths that do NOT need changes (verified)

- **aria2 pause/resume** (`_resume_restored_aria2_download`, line 754+): resumes from persisted `resume_context`; never re-runs existence gates.
- **`download_coordinator.py:90`**: pure pass-through of `file_params`.
- **Update checker / plugin self-update** (`update_routes.py:496–501`): only closes the history DB handle.
- **History delete semantics**: `mark_as_deleted` sets `is_deleted_override=1` and `has_been_downloaded` then returns False (`downloaded_version_history_service.py:276`) — LM-initiated deletes already reset the history skip.

### 2.8 Related pre-existing issues (record, not necessarily fix)

- **Queue retry drops file selection** (R9): `download_queue_service.retry_from_history` / `retry_all_failed` re-queue with `file_params=NULL` (`download_queue_service.py:705, 758`) although the queue table has a `file_params` column (`:43`) — a retried non-primary download silently reverts to the primary file. Fix alongside phase 1 (small: persist and reuse the column).
- **`delete_model_version`** (`misc_handlers.py:2410–2487`): resolves the file via the single-valued `version_index` (2440–2444), deletes only that one file, and `mark_as_deleted` flags the **entire version** as deleted in history (2479) even when a sibling file remains in the library. See phase 2 item 6.1.5.

## 3. Goals / Non-Goals

**Goals**

- G1: A user can download any not-yet-downloaded file of a version already partially in the library (issue repro steps 6–8).
- G2: True duplicates stay blocked: downloading the *same* file of the same version twice is rejected.
- G3: Per-file downloaded state visible in the file dialog; multiple files selectable and downloadable in one pass.
- G4: No regression for version-level semantics relied on by batch download, recipe missing-LoRA detection, and `skip_previously_downloaded_model_versions`.

**Non-Goals**

- No change to recipe `inLibrary` semantics ("any file of the version present" remains sufficient).
- No change to the update-checker (version-level comparison).
- No primary-key rebuild of the history database.
- HuggingFace download flow untouched.

## 4. Design Decisions

- **D1 — Explicit file selection bypasses the history gate, version-level gates stay for everyone else.** The history skip exists to dedupe automated flows. A user explicitly picking a file is unambiguous intent; the file-level library gate (G2) still prevents real duplicates. **Guard conditions use normalized truthiness** (see D1a). All confirmed `file_params` senders are user-initiated dialog flows (2.6), and LM-initiated deletes already reset history (2.7), so the bypass only affects "downloaded but not LM-deleted" versions with the setting on — intended.
- **D1a — `file_params` normalization at the boundary (R2).** `download-model-get` and `downloads/queue/add` accept arbitrary JSON; `{}` is `not None` but falsy and would bypass gates while downloading the primary file. Normalize `file_params = file_params or None` in the coordinator/handlers, and treat the bypass as active only when a target file id is resolvable.
- **D2 — File identity matching rule (R6/R7):** hash-compare **only when both sides are non-empty** (lowercase SHA256 equality); name-compare when either side is empty. Never let `"" == ""` match. Name fallback caveats from 2.4 apply (renamed files, pending checkpoint hashes) — acceptable residual risk, worst case is a blocked re-download the user can retry after hashing completes.
- **D3 — Cache indexes: additive multi-index + removal re-pointing (R4).** Add `version_files_index: Dict[int, List[dict]]` maintained alongside `version_index` by the same add/remove/rebuild methods; existing readers of `version_index` untouched. Additionally fix `remove_from_version_index`: when the popped entry has a surviving sibling (per the multi-index), re-point `version_index[version_id]` to the sibling instead of dropping the key; same for the `model_id_index` descriptor. This closes the 2.5 hazard for existing readers (`check_model_version_exists`, `existsLocally`, recipe matching) without restructuring anything.
- **D4 — Per-file history via a child table (R3).** v1's additive-column approach is structurally impossible on a `(model_type, version_id)` PK (`ON CONFLICT DO UPDATE` would keep only the last file). Instead add `downloaded_version_files(model_type, version_id, file_id, file_name, downloaded_at, PRIMARY KEY(model_type, version_id, file_id))` — additive, no PK rebuild, honors the Non-Goal. Existing version-level table and queries unchanged. New per-file queries are opt-in. `_initialize_schema` uses `CREATE TABLE IF NOT EXISTS`, so the new table is created for existing DBs without any ALTER.
- **D5 — UI flow reuse, with an extracted inner download function for multi-file (F7).** Phase 1 unlocks the existing badge → file dialog → location → download pipeline. Phase 2 upgrades the dialog to multi-select; iterating `executeDownloadWithProgress` as-is would produce N full library reloads, N toasts, and competing failure-summary modals — so phase 2 extracts a reload-deferred, failure-aggregating inner variant and runs one reload + one summary at the end.

## 5. Implementation — Phase 1 (fix the issue; independently shippable)

### 5.1 Backend — `py/services/download_manager.py`

1. **Normalize `file_params`** at the boundary (D1a): `download_coordinator.schedule_download` and the two API handlers (`model_handlers.py:1649–1666`, `1810–1832`) apply `file_params = file_params or None`.
2. **Extract a shared file resolver** (R1): pull the matching logic at 1498–1569 into `_resolve_target_file(version_info, file_params) -> Optional[dict]`, used by **both** the new gate and the download-selection path. The selection path's condition (line 1499) switches from `model_version_id` to `resolved_version_id` (already computed at 1230–1236 from `version_info.id`), so gate and download always agree on the target file — including the `model_id`-only case.
3. **New helper** `_find_local_file_entry(version_id, target_file) -> Optional[dict]`: iterate the three scanners' cached `raw_data` (NOT `version_index` — single-valued); candidates = entries whose `civitai.id` normalizes to `version_id`; match per D2.
4. **Gate restructure in `_execute_original_download`**:
   - Early scanner gate (1157–1184): add `file_params is None` guard; with normalized `file_params`, defer (file identity not resolvable before metadata fetch).
   - After `version_info` fetch + `resolved_version_id` (~1229): when `file_params` present, resolve target file via the shared resolver; unresolvable → hard error "No matching file" (fail closed, prevents empty-dict bypass). Resolvable → `_find_local_file_entry`; hit → same hard error shape as today with the file name in the message.
   - History gate (1238–1279): add `file_params is None` (D1). Base-model skip (1281–1324) unchanged — still applies.
   - Late gate (1350–1376): add `file_params is None` guard (F2) — the post-fetch file-level check above already covers this case.
   - Nothing between the early gate and the post-fetch point assumes the version is absent (review task 6: only provider selection + metadata fetch; no DB writes; `_persist_aria2_state` runs only when actually downloading at 1659).
5. **Queue retry fix** (2.8, small): persist `file_params` into the queue table on enqueue and reuse it in `retry_from_history` / `retry_all_failed`.
6. Logging: `[download]` lines for file-level allow/block, consistent with existing style.

**Estimated:** ~150–220 LOC + resolver extraction.

### 5.2 Frontend — `static/js/managers/DownloadManager.js`

1. Line 598: drop `&& !existsLocally` from the badge condition (badge shows whenever `modelFiles.length > 1`).
2. `fileParams` construction (1611–1616): add `name: this.selectedFile.name`.
3. Surface the backend "file already in library" hard error as a toast instead of only the batch-summary modal (R10/F12 nit; reuse existing error message field).
4. No changes to `updateNextButtonState` / `proceedToLocation` in phase 1; no template or CSS changes.

**Known phase-1 UX limitations (acknowledged, fixed in phase 2):** with all files downloaded the badge still renders and re-picking a downloaded file fails late (backend error after the location step); `localPath` may point at a sibling file; batch-preview "In Library" badge stays version-level and gives no hint of remaining files.

**Estimated:** ~10–30 LOC (confirmed realistic by review).

### 5.3 Phase 1 tests

Backend — extend `tests/services/test_download_manager_basic.py` (1694 lines; all fixture patterns exist):

- **Fixture gaps to add (F10):** `DummyScanner.get_cached_data()`/`raw_data` stub (~10 lines); `hashes.SHA256` in the metadata-provider payload's `files`.
- Cases: same version + different SHA256 in library + `file_params` → proceeds; same SHA256 → hard error; `file_params=None` + version in library → hard error (unchanged); history-skip on + `file_params` → not skipped; without → skipped (unchanged); empty-dict `file_params` normalized → version-level behavior; `model_id`-only + `file_params` → gate and selection resolve the same file; legacy metadata (empty local sha256) matched by name; target file with empty SHA256 → name fallback, no `""==""` false positive.
- Queue retry: `file_params` survives retry.
- Assert proceed/abort via the existing `_execute_download` mock pattern.

Frontend (`tests/frontend/`): badge renders for multi-file version with `existsLocally=true` (pattern from `downloadManager.history.test.js`).

**Estimated:** ~150–250 LOC (confirmed realistic).

## 6. Implementation — Phase 2 (per-file status + multi-select + index hardening)

### 6.1 Backend

1. **`py/services/model_cache.py`** (D3): add `version_files_index`; maintain in `add_to_version_index` / `remove_from_version_index` / `rebuild_version_index`; removal re-points `version_index[version_id]` (and the `model_id_index` descriptor) to a surviving sibling instead of dropping the key.
2. **`py/services/model_scanner.py`**: expose `get_files_for_version(version_id) -> List[dict]`.
3. **`py/routes/handlers/model_handlers.py` `get_civitai_versions`**: annotate each version with `downloadedFiles: [{fileId, fileName, filePath}]` via `version_files_index` + D2 matching against `version.files`.
4. **`py/services/downloaded_version_history_service.py`** (D4): new child table `downloaded_version_files`; `mark_downloaded` also upserts the child row when `file_id` known; `mark_as_deleted` clears the version's child rows only when no sibling remains in the library; new `get_downloaded_file_ids(model_type, version_id) -> set[int]`. `_record_downloaded_version_history` passes `file_info` through.
5. **`delete_model_version`** (`misc_handlers.py:2410–2487`, R5): resolve **all** local files of the version via `version_files_index`; delete all (current endpoint semantics are version-level) or — if kept per-file — only `mark_as_deleted` when no sibling remains. Decide at implementation time; minimum is documenting current behavior.
6. **`ModelVersionsTab` backend support**: none needed beyond item 3 (`downloadedFiles`); the tab consumes the same versions payload.

### 6.2 Frontend

1. **File dialog multi-select** — change surface (F8): option markup (`DownloadManager.js:712–724`), the single-select click handler (`727–734`), the `input[type="radio"]:checked` selector in `confirmFileSelection` (`738`); template `templates/components/modals/download_modal.html:48–60` (confirm-button label only); CSS `download-modal.css` — checkbox variant of `.file-option-radio input` (595–604) and a **new** `.file-option.disabled` style (does not exist). Files whose id ∈ `downloadedFiles` render disabled with an "In Library" tag.
2. **Mixed-type guard (F8):** multi-select is restricted to files sharing the same routing target (`_isDiffusionModel` is computed once from a single `selectedFile` at 798–803; e.g. "Model" + "UNet" files route to different roots). Disallow mixed-type multi-select (simplest, predictable); single-file selection unchanged.
3. **Multi-file download loop (D5/F7):** extract from `executeDownloadWithProgress` a reload-deferred, no-toast inner function; iterate per selected file with per-file progress; one `resetAndReload(true)` + one aggregated success/failure summary at the end (reuse `showDownloadBatchSummary`).
4. **`updateNextButtonState` / `proceedToLocation`:** for multi-file versions, Next routes into the file dialog; hard block only when *every* weight file is downloaded.
5. **`ModelVersionsTab.js` (F6):** the Download action (`:576` hidden when `isInLibrary`) — for multi-file versions with remaining files, show it and route into the download modal's file dialog; keep hidden when all files present.
6. **Batch preview (F5):** `batch-preview-local-badge` (`:1320`) gains a "partially downloaded" hint for multi-file versions with remaining files.
7. New i18n keys (`modals.download.fileSelection.inLibrary`, `downloadSelected`, partial-download tooltip, etc.) → run `python scripts/sync_translation_keys.py`.

### 6.3 Phase 2 tests

- `model_cache` (`tests/services/test_model_cache.py` already covers add/remove at 44–55): multi-valued index; sibling re-point on removal; rebuild.
- `get_civitai_versions`: `downloadedFiles` correctness (hash match, name fallback, no match, CivArchive no-hash payload).
- History service (`tests/services/test_downloaded_version_history_service.py` uses real SQLite on tmp_path): child-table creation on a legacy DB; per-file record/query; `mark_as_deleted` sibling semantics.
- Frontend: dialog checkbox rendering/disabled state and multi-file confirm — **greenfield behavior coverage** (F10: no existing test exercises `showFileSelectionStep`/`confirmFileSelection`; infra exists, patterns must be built).

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| History-gate bypass (D1) causes unwanted re-downloads in automated flows | Large checkpoint files re-downloaded | Bypass only with normalized, resolvable `file_params` (D1a); all such senders are user-initiated dialog flows (2.6, verified); tests pin batch/recipe/bulk behavior. |
| Empty-hash matching edge cases (R6) | Duplicate download of the same file, or false block | D2 rule: hash only when both non-empty; name otherwise; never `""==""`. Residual risk documented (2.4). |
| Phase-1 late-failure UX (F12) | User picks a downloaded file, fails only after location step | Toast surfacing (5.2.3); phase 2 disables downloaded files up front. |
| Phase-2 index change corrupts existing behavior | Recipe matching, delete flows | Additive index + re-point only; `version_index` read semantics unchanged; `remove_models`/`update_single_model_cache` already rebuild (F3); tests. |
| `delete_model_version` marks whole version deleted while sibling remains (R5) | History wrongly suppresses re-download of the surviving sibling's version | Phase 2 item 6.1.5; documented until then. |
| History child-table migration failure on user installs | Service init crash | `CREATE TABLE IF NOT EXISTS` in `_initialize_schema`; failure degrades to version-level behavior (per-file queries return empty). |
| Batch-preview badge misleading for partial versions (F5) | Minor UX confusion | Acknowledged in phase 1; fixed in phase 2 item 6.2.6. |
| UI confusion: version shows "In Library" while files remain downloadable | Support burden | Phase 2: per-file disabled state + partial-download tooltip. |
| Hash-identical sibling files (repacked content) | Second file blocked | Acceptable: scanner hash dedup already collapses them. |

## 8. Rollout

1. **Commit 1** — `fix(download): allow downloading additional files of an in-library model version (#1058)` → Phase 1 (5.1–5.3).
2. **Commit 2** — `feat(download): per-file download status and multi-file selection (#1058)` → Phase 2 (6.1–6.3).

Phase 1 alone resolves the issue as reported; phase 2 can ship in a later release if review prefers smaller increments.

## 9. Effort Estimate (revised after review)

| Phase | Backend | Frontend | Tests | Risk |
|---|---|---|---|---|
| 1 | ~150–220 LOC (+ queue-retry fix ~30) | ~10–30 LOC | ~150–250 LOC | Low |
| 2 | ~250–350 LOC | ~250–350 LOC (multi-file loop refactor + ModelVersionsTab + batch badge) | ~250–350 LOC (dialog tests greenfield) | Medium |
