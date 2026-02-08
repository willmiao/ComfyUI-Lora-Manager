# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ComfyUI LoRA Manager is a comprehensive LoRA management system for ComfyUI that combines a Python backend with browser-based widgets. It provides model organization, downloading from CivitAI/CivArchive, recipe management, and one-click workflow integration.

## Development Commands

### Backend

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run standalone server (port 8188 by default)
python standalone.py --port 8188

# Run all backend tests
pytest

# Run specific test file or function
pytest tests/test_recipes.py
pytest tests/test_recipes.py::test_function_name

# Run backend tests with coverage
COVERAGE_FILE=coverage/backend/.coverage pytest \
  --cov=py \
  --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json
```

### Frontend

There are three test suites run by `npm test`: vanilla JS tests (vitest at root) and Vue widget tests (`vue-widgets/` vitest).

```bash
npm install
cd vue-widgets && npm install && cd ..

# Run all frontend tests (JS + Vue)
npm test

# Run only vanilla JS tests
npm run test:js

# Run only Vue widget tests
npm run test:vue

# Watch mode (JS tests only)
npm run test:watch

# Frontend coverage
npm run test:coverage

# Build Vue widgets (output to web/comfyui/vue-widgets/)
cd vue-widgets && npm run build

# Vue widget dev mode (watch + rebuild)
cd vue-widgets && npm run dev

# Typecheck Vue widgets
cd vue-widgets && npm run typecheck
```

### Localization

```bash
# Sync translation keys after UI string updates
python scripts/sync_translation_keys.py
```

Locale files are in `locales/` (en, zh-CN, zh-TW, ja, ko, fr, de, es, ru, he).

## Architecture

### Dual Mode Operation

The system runs in two modes:
- **ComfyUI plugin mode**: Integrates with ComfyUI's PromptServer, uses `folder_paths` for model discovery
- **Standalone mode**: `standalone.py` mocks ComfyUI dependencies, reads paths from `settings.json`
- Detection: `os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"`

### Backend (Python)

**Entry points:**
- `__init__.py` — ComfyUI plugin entry: registers nodes via `NODE_CLASS_MAPPINGS`, sets `WEB_DIRECTORY`, calls `LoraManager.add_routes()`
- `standalone.py` — Standalone server: mocks `folder_paths` and node modules, starts aiohttp server
- `py/lora_manager.py` — Main `LoraManager` class that registers all HTTP routes

**Service layer** (`py/services/`):
- `ServiceRegistry` singleton for dependency injection; services follow `get_instance()` singleton pattern
- `BaseModelService` abstract base → `LoraService`, `CheckpointService`, `EmbeddingService`
- `ModelScanner` base → `LoraScanner`, `CheckpointScanner`, `EmbeddingScanner` for file discovery with hash-based deduplication
- `PersistentModelCache` — SQLite-based metadata cache
- `MetadataSyncService` — Background sync from CivitAI/CivArchive APIs
- `SettingsManager` — Settings with schema migration support
- `WebSocketManager` — Real-time progress broadcasting
- `ModelServiceFactory` — Creates the right service for each model type
- Use cases in `py/services/use_cases/` orchestrate complex business logic (auto-organize, bulk refresh, downloads)

**Routes** (`py/routes/`):
- Route registrars organize endpoints by domain: `ModelRouteRegistrar`, `RecipeRouteRegistrar`, etc.
- Request handlers in `py/routes/handlers/` implement route logic
- API endpoints follow `/loras/*`, `/checkpoints/*`, `/embeddings/*` patterns
- All routes use aiohttp, return `web.json_response` or `web.Response`

**Recipe system** (`py/recipes/`):
- `base.py` — Recipe metadata structure
- `enrichment.py` — Enriches recipes with model metadata
- `parsers/` — Parsers for PNG metadata, JSON, and workflow formats

**Custom nodes** (`py/nodes/`):
- Each node class has a `NAME` class attribute used as key in `NODE_CLASS_MAPPINGS`
- Standard ComfyUI node pattern: `INPUT_TYPES()` classmethod, `RETURN_TYPES`, `FUNCTION`
- All nodes registered in `__init__.py`

**Configuration** (`py/config.py`):
- Manages folder paths for models, handles symlink mappings
- Auto-saves paths to settings.json in ComfyUI mode

### Frontend — Two Distinct UI Systems

#### 1. Standalone Manager Web UI
- **Location:** `static/` (JS/CSS) and `templates/` (HTML)
- **Tech:** Vanilla JS + CSS, served by standalone server
- **Structure:** `static/js/core.js` (shared), `loras.js`, `checkpoints.js`, `embeddings.js`, `recipes.js`, `statistics.js`
- **Tests:** `tests/frontend/**/*.test.js` (vitest + jsdom)

#### 2. ComfyUI Custom Node Widgets
- **Vanilla JS widgets:** `web/comfyui/*.js` — ES modules extending ComfyUI's LiteGraph UI
  - `loras_widget.js` / `loras_widget_events.js` — Main LoRA selection widget
  - `autocomplete.js` — Trigger word and embedding autocomplete
  - `preview_tooltip.js` — Model card preview tooltips
  - `top_menu_extension.js` — "Launch LoRA Manager" menu item
  - `utils.js` — Shared utilities and API helpers
  - Widget styling in `web/comfyui/lm_styles.css` (NOT `static/css/`)
- **Vue widgets:** `vue-widgets/src/` → built to `web/comfyui/vue-widgets/`
  - Vue 3 + TypeScript + PrimeVue + vue-i18n
  - Vite build with CSS-injected-by-JS plugin
  - Components: `LoraPoolWidget`, `LoraRandomizerWidget`, `LoraCyclerWidget`, `AutocompleteTextWidget`
  - Auto-built on ComfyUI startup via `py/vue_widget_builder.py`
  - Tests: `vue-widgets/tests/**/*.test.ts` (vitest)

**Widget registration pattern:**
- Widgets use `app.registerExtension()` and `getCustomWidgets` hooks
- `node.addDOMWidget(name, type, element, options)` embeds HTML in LiteGraph nodes
- See `docs/dom_widget_dev_guide.md` for DOMWidget development guide

## Code Style

**Python:**
- PEP 8, 4-space indentation, English comments only
- Use `from __future__ import annotations` for forward references
- Use `TYPE_CHECKING` guard for type-checking-only imports
- Loggers via `logging.getLogger(__name__)`
- Custom exceptions in `py/services/errors.py`
- Async patterns: `async def` for I/O, `@pytest.mark.asyncio` for async tests
- Singleton pattern with class-level `asyncio.Lock` (see `ModelScanner.get_instance()`)

**JavaScript:**
- ES modules, camelCase functions/variables, PascalCase classes
- Widget files use `*_widget.js` suffix
- Prefer vanilla JS for `web/comfyui/` widgets, avoid framework dependencies (except Vue widgets)

## Testing

**Backend (pytest):**
- Config in `pytest.ini`: `--import-mode=importlib`, testpaths=`tests`
- Fixtures in `tests/conftest.py` handle ComfyUI dependency mocking
- Markers: `@pytest.mark.asyncio`, `@pytest.mark.no_settings_dir_isolation`
- Uses `tmp_path_factory` for directory isolation

**Frontend (vitest):**
- Vanilla JS tests: `tests/frontend/**/*.test.js` with jsdom
- Vue widget tests: `vue-widgets/tests/**/*.test.ts` with jsdom + @vue/test-utils
- Setup in `tests/frontend/setup.js`

## Key Integration Points

- **Settings:** Stored in user directory (via `platformdirs`) or portable mode (`"use_portable_settings": true`)
- **CivitAI/CivArchive:** API clients for metadata sync and model downloads; CivitAI API key in settings
- **Symlink handling:** Config scans symlinks to map virtual→physical paths; fingerprinting prevents redundant rescans
- **WebSocket:** Broadcasts real-time progress for downloads, scans, and metadata sync
- **Model scanning flow:** Walk folders → compute hashes → deduplicate → extract safetensors metadata → cache in SQLite → background CivitAI sync → WebSocket broadcast
