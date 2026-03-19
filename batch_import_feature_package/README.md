# Batch Import Feature Package (ComfyUI LoRA Manager)

## Purpose
This package contains the **batch import feature** plus the integration fixes needed to make it work end-to-end in an unaltered LoRA Manager repo. It also documents every file changed in this repo for batch import support.

## What Changed In This Repo (Original Files Modified)
These are existing files in the base repo that were modified to make batch import work reliably.

1. `standalone.py`
   - Added import for `BatchImportRoutes`.
   - Registered `BatchImportRoutes.setup_routes(app)` so the batch endpoints are wired in standalone mode.
   - Purpose: makes `/api/lm/recipes/batch/*` endpoints available.

2. `templates/recipes.html`
   - Enabled `{% include 'components/batch_import_modal.html' %}` in `additional_components`.
   - Added the Batch Import button to the **right-side controls** (`.controls-right`) so it is visible and not clipped.
   - Purpose: surfaces the batch import UI and fixes the hidden/partially clipped button.

3. `static/js/recipes.js`
   - Added `BatchImportManager` import.
   - Instantiated it in `RecipeManager` and exposed it via `window.batchImportManager`.
   - Purpose: enables the modal open/close and triggers the API calls.

4. `py/services/server_i18n.py`
   - Extended `ServerI18nManager.get_translation` to accept a **fallback default** argument and handle legacy calls like `t(key, {}, "Default")`.
   - Added defensive handling when the second argument is a string (legacy positional default).
   - Purpose: prevents Jinja templates from crashing when a default string is supplied.

5. `tests/routes/test_recipe_routes.py`
   - Added a smoke test that renders `/loras/recipes` using legacy i18n defaults.
   - Purpose: ensures the i18n fallback behavior prevents server-side template errors.

## New Files Added (Feature Payload)
These files did not exist in the base repo and are included in `new_files/` in this package.

Backend
- `py/services/recipes/batch_import_service.py`
  Core batch import logic. Scans directories or URLs, runs analysis concurrently, and persists recipes.

- `py/routes/handlers/batch_import_handler.py`
  HTTP handlers for `/api/lm/recipes/batch/import-directory` and `/api/lm/recipes/batch/import-urls`.
  Uses an async service getter (fixes the “coroutine has no attribute” error).

- `py/routes/batch_import_route_registrar.py`
  Declarative route definitions and a registrar for batch import endpoints.

- `py/routes/batch_import_routes.py`
  Integration wrapper that builds the batch services and registers routes.
  Passes the service getter **function** (not a coroutine) into the handler.

Frontend
- `static/js/managers/BatchImportManager.js`
  Client-side UI/flow for batch import. Handles modal, tabs, validation, API calls, and result display.

- `templates/components/batch_import_modal.html`
  Modal UI and styles for batch import. The toolbar button lives in `recipes.html`.

Docs
- `docs/BATCH_IMPORT_GUIDE.md`
  User-facing guide for batch import.

- `docs/BATCH_IMPORT_INTEGRATION.md`
  Developer/integration notes and API reference.

Tests
- `tests/services/test_server_i18n.py`
  Verifies fallback behavior for `get_translation` with legacy default parameters.

## How To Install (Automated)
Run the installer from the package directory:

```powershell
python install_batch_import.py "C:\path\to\lora-manager" --backup
```

Options
- `--backup` creates timestamped backups of modified files in the target repo.
- `--dry-run` shows what would change without writing files.

## Manual Wiring (If You Don’t Use The Script)
1. Copy all files under `new_files/` into the target repo, preserving paths.
2. Edit `standalone.py`:
   - Add `from py.routes.batch_import_routes import BatchImportRoutes` near other routes.
   - Register `BatchImportRoutes.setup_routes(app)` with the other route registrations.
3. Edit `templates/recipes.html`:
   - Add `{% include 'components/batch_import_modal.html' %}` in `additional_components`.
   - Add a Batch Import toolbar button under `.controls-right`.
4. Edit `static/js/recipes.js`:
   - Import `BatchImportManager`.
   - Instantiate it after `ImportManager` and expose on `window`.
5. Edit `py/services/server_i18n.py`:
   - Update `get_translation` to accept a fallback default string and legacy positional usage.

## Verification Checklist
- Start the server and open `http://127.0.0.1:9001/loras/recipes`.
- Confirm “Batch Import” button is visible on the right side.
- Open modal, switch tabs, and run a small test import.
- Confirm no server-side template errors and no JS errors in the console.

## Rollback
- Remove new files listed above.
- Revert changes in `standalone.py`, `templates/recipes.html`, `static/js/recipes.js`, and `py/services/server_i18n.py`.
- Restart server.
