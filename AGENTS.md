# AGENTS.md

This file provides guidance for agentic coding assistants working in this repository.

## Overview

ComfyUI LoRA Manager is a comprehensive LoRA management system for ComfyUI that combines a Python backend with browser-based widgets. It provides model organization, downloading from CivitAI/CivArchive, recipe management, and one-click workflow integration.

## Development Commands

### Backend Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run standalone server (port 8188 by default)
python standalone.py --port 8188

# Run all backend tests
pytest

# Run specific test file
pytest tests/test_recipes.py

# Run specific test function
pytest tests/test_recipes.py::test_function_name

# Run backend tests with coverage
COVERAGE_FILE=coverage/backend/.coverage pytest \
  --cov=py --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json
```

### Frontend Development (LoRA Manager Web UI)

```bash
# Install dependencies (root and Vue widgets)
npm install
cd vue-widgets && npm install && cd ..

npm test                    # Run all tests (JS + Vue)
npm run test:js             # Run JS tests only
npm run test:vue            # Run Vue widget tests only
npm run test:watch          # Watch mode (JS tests only)
npm run test:coverage       # Generate coverage report
```

### Vue Widget Development

```bash
cd vue-widgets
npm install
npm run dev                 # Build in watch mode
npm run build               # Build production bundle
npm run typecheck           # Run TypeScript type checking
npm test                    # Run Vue widget tests
npm run test:watch          # Watch mode
npm run test:coverage       # Generate coverage report
```

### Localization

```bash
# Sync translation keys after UI string updates
python scripts/sync_translation_keys.py
```

Locale files are in `locales/` (en, zh-CN, zh-TW, ja, ko, fr, de, es, ru, he).

After adding keys to `en.json` and syncing, **stop**: the `[TODO: Translate]` placeholders in
the other locales are the expected end state during feature development. Do NOT translate
proactively — translate only when the feature owner explicitly asks (see
`docs/i18n-translation-guidelines.md` §7).

**Before translating anything, read `docs/i18n-translation-guidelines.md`** — it defines the
term conventions (e.g. "Recipe" stays untranslated in French, 配方 in Chinese; model-type and
brand names are never translated), per-locale preferred renderings, placeholder rules, and
the known confusion hot-spots.

## Code Style

### Python

#### Imports & Formatting

- Use `from __future__ import annotations` for forward references
- Group imports: standard library, third-party, local (blank line separated)
- Use `TYPE_CHECKING` guard for type-checking-only imports
- Absolute imports within `py/`: `from ..services import X`
- PEP 8 with 4-space indentation, type hints required

#### Naming Conventions

- Files: `snake_case.py`, Classes: `PascalCase`, Functions/vars: `snake_case`
- Constants: `UPPER_SNAKE_CASE`, Private: `_protected`, `__mangled`

#### Error Handling & Async

- Use `logging.getLogger(__name__)`, define custom exceptions in `py/services/errors.py`
- `async def` for I/O, `@pytest.mark.asyncio` for async tests
- Singleton with `asyncio.Lock`: see `ModelScanner.get_instance()`
- Return `aiohttp.web.json_response` or `web.Response`

### JavaScript/TypeScript

#### Imports & Modules

- ES modules: `import { app } from "../../scripts/app.js"` for ComfyUI
- Vue: `import { ref, computed } from 'vue'`, type imports: `import type { Foo }`
- Export named functions: `export function foo() {}`

#### Naming & Formatting

- camelCase for functions/vars/props, PascalCase for classes
- Constants: `UPPER_SNAKE_CASE`, Files: `snake_case.js` or `kebab-case.js`
- 2-space indentation preferred (follow existing file conventions)
- Vue Single File Components: `<script setup lang="ts">` preferred

#### Widget Development

- Prefer vanilla JS for `web/comfyui/` widgets; avoid framework dependencies (except the Vue widgets in `vue-widgets/`)
- ComfyUI: `app.registerExtension()`, `node.addDOMWidget(name, type, element, options)`
- Event handlers via `addEventListener` or widget callbacks
- Shared utilities: `web/comfyui/utils.js`
- Dual-mode rendering patterns (canvas vs Vue): see `docs/comfyui-dual-mode-widgets.md`

#### Vue Composables Pattern

- Use composition API: `useXxxState(widget)`, return reactive refs and methods
- Guard restoration loops with flag: `let isRestoring = false`
- Build config from state: `const buildConfig = (): Config => { ... }`

## Architecture

### Dual Mode Operation

The system runs in two modes:
- **ComfyUI plugin mode**: Integrates with ComfyUI's PromptServer, uses `folder_paths` for model discovery
- **Standalone mode**: `standalone.py` mocks ComfyUI dependencies, reads paths from `settings.json`
- Detection: `os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"`

### Backend Entry Points

- `__init__.py` — ComfyUI plugin entry: registers nodes via `NODE_CLASS_MAPPINGS`, sets `WEB_DIRECTORY`, calls `LoraManager.add_routes()`
- `standalone.py` — Standalone server: mocks `folder_paths` and node modules, starts aiohttp server
- `py/lora_manager.py` — Main `LoraManager` class that registers all HTTP routes

### Service Layer

- `ServiceRegistry` singleton for DI, services use `get_instance()` classmethod
- `BaseModelService` abstract base → `LoraService`, `CheckpointService`, `EmbeddingService`
- `ModelScanner` base → `LoraScanner`, `CheckpointScanner`, `EmbeddingScanner` for file discovery with hash-based deduplication
- `PersistentModelCache` (SQLite) for metadata persistence
- `MetadataSyncService` — background sync from CivitAI/CivArchive APIs
- `SettingsManager` — settings with schema migration support
- `WebSocketManager` — real-time progress broadcasting
- `ModelServiceFactory` — creates the right service for each model type
- Use cases in `py/services/use_cases/` orchestrate complex business logic (auto-organize, bulk refresh, downloads)
- Separate scanners (discovery) from services (business logic)
- Handlers in `py/routes/handlers/` are pure functions with deps as params

### Model Types & Routes

- API endpoints follow `/loras/*`, `/checkpoints/*`, `/embeddings/*` patterns
- Route registrars organize endpoints by domain: `ModelRouteRegistrar`, `RecipeRouteRegistrar`, etc.
- Request handlers in `py/routes/handlers/` implement route logic
- All routes use aiohttp, return `web.json_response` or `web.Response`

### Recipe System

- Base: `py/recipes/base.py`, Enrichment: `RecipeEnrichmentService` in `py/recipes/enrichment.py`
- Parsers: `py/recipes/parsers/` for PNG metadata, JSON, and workflow formats

### Custom Nodes

- Location: `py/nodes/`, all nodes registered in `__init__.py`
- Each node class has a `NAME` class attribute used as key in `NODE_CLASS_MAPPINGS`
- Standard ComfyUI node pattern: `INPUT_TYPES()` classmethod, `RETURN_TYPES`, `FUNCTION`

### Configuration

- `py/config.py` manages folder paths for models and handles symlink mappings
- Auto-saves paths to `settings.json` in ComfyUI mode

### Frontend UI Architecture

#### 1. LoRA Manager Web UI
- Location: `./static/` (JS/CSS) and `./templates/` (HTML)
- Tech: Vanilla JS + CSS, served by the hosting server (ComfyUI app in plugin mode, `standalone.py` in standalone mode)
- Tests: `tests/frontend/**/*.test.js` (vitest + jsdom)

#### 2. ComfyUI Custom Node Widgets
- Location: `./web/comfyui/` (Vanilla JS) + `./vue-widgets/` (Vue)
- Primary styles: `./web/comfyui/lm_styles.css` (NOT `./static/css/`)
- Vue widgets: Vue 3 + TypeScript + PrimeVue + vue-i18n, e.g. `LoraPoolWidget`, `LoraRandomizerWidget`, `LoraCyclerWidget`, `AutocompleteTextWidget`
- Vue builds to `./web/comfyui/vue-widgets/`; auto-built on ComfyUI startup via `py/vue_widget_builder.py`, typecheck via `vue-tsc`
- Widget registration: `app.registerExtension()` and `getCustomWidgets` hooks; `node.addDOMWidget(...)` embeds HTML in LiteGraph nodes
- See `docs/dom_widget_dev_guide.md` for the DOMWidget development guide

## Testing

### Backend (pytest)

- Config in `pytest.ini`: `--import-mode=importlib`, testpaths=`tests`
- Fixtures in `tests/conftest.py` mock ComfyUI dependencies; use `tmp_path_factory` for isolation
- Markers: `@pytest.mark.asyncio`, `@pytest.mark.no_settings_dir_isolation` (tests needing real settings paths)

### Frontend (vitest)

- Vanilla JS tests: `tests/frontend/**/*.test.js` with jsdom; setup in `tests/frontend/setup.js`
- Vue widget tests: `vue-widgets/tests/**/*.test.ts` with jsdom + `@vue/test-utils`

## Key Integration Points

- **Settings:** Stored in the user config directory (via `platformdirs`) or portable mode (`"use_portable_settings": true`)
- **CivitAI/CivArchive:** API clients for metadata sync and model downloads; CivitAI API key stored in settings
- **Symlinks:** Config scans symlinks to map virtual→physical paths; fingerprinting prevents redundant rescans
- **WebSocket:** Broadcasts real-time progress for downloads, scans, and metadata sync
- **Model scanning flow:** Walk folders → compute hashes → deduplicate → extract safetensors metadata → cache in SQLite → background CivitAI sync → WebSocket broadcast

## Important Notes

- ALWAYS use English for comments (per copilot-instructions.md)
- Run `python scripts/sync_translation_keys.py` after adding UI strings to `locales/en.json`
- Symlinks require normalized paths.
  **Business paths vs real paths**: All stored paths and operation routing use the
  original paths as they appear under configured model roots — symlinks are NOT
  resolved. `os.path.realpath` is only for scanner dedup and the symlink cache.
  Any path passed to `os.remove`/`os.rename`/`shutil.move` or validated by a
  containment check MUST use the business path (i.e. `os.path.abspath`, not
  `realpath`).