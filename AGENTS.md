# AGENTS.md

This file provides guidance for agentic coding assistants working in this repository.

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
  --cov-report=xml:coverage/backend/coverage.xml
```

### Frontend Development (Standalone Web UI)

```bash
npm install
npm test                    # Run all tests (JS + Vue)
npm run test:js             # Run JS tests only
npm run test:watch          # Watch mode
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

## Python Code Style

### Imports & Formatting

- Use `from __future__ import annotations` for forward references
- Group imports: standard library, third-party, local (blank line separated)
- Absolute imports within `py/`: `from ..services import X`
- PEP 8 with 4-space indentation, type hints required

### Naming Conventions

- Files: `snake_case.py`, Classes: `PascalCase`, Functions/vars: `snake_case`
- Constants: `UPPER_SNAKE_CASE`, Private: `_protected`, `__mangled`

### Error Handling & Async

- Use `logging.getLogger(__name__)`, define custom exceptions in `py/services/errors.py`
- `async def` for I/O, `@pytest.mark.asyncio` for async tests
- Singleton with `asyncio.Lock`: see `ModelScanner.get_instance()`
- Return `aiohttp.web.json_response` or `web.Response`

### Testing

- `pytest` with `--import-mode=importlib`
- Fixtures in `tests/conftest.py`, use `tmp_path_factory` for isolation
- Mark tests needing real paths: `@pytest.mark.no_settings_dir_isolation`
- Mock ComfyUI dependencies via conftest patterns

## JavaScript/TypeScript Code Style

### Imports & Modules

- ES modules: `import { app } from "../../scripts/app.js"` for ComfyUI
- Vue: `import { ref, computed } from 'vue'`, type imports: `import type { Foo }`
- Export named functions: `export function foo() {}`

### Naming & Formatting

- camelCase for functions/vars/props, PascalCase for classes
- Constants: `UPPER_SNAKE_CASE`, Files: `snake_case.js` or `kebab-case.js`
- 2-space indentation preferred (follow existing file conventions)
- Vue Single File Components: `<script setup lang="ts">` preferred

### Widget Development

- ComfyUI: `app.registerExtension()`, `node.addDOMWidget(name, type, element, options)`
- Event handlers via `addEventListener` or widget callbacks
- Shared utilities: `web/comfyui/utils.js`

### Vue Composables Pattern

- Use composition API: `useXxxState(widget)`, return reactive refs and methods
- Guard restoration loops with flag: `let isRestoring = false`
- Build config from state: `const buildConfig = (): Config => { ... }`

## Architecture Patterns

### Service Layer

- `ServiceRegistry` singleton for DI, services use `get_instance()` classmethod
- Separate scanners (discovery) from services (business logic)
- Handlers in `py/routes/handlers/` are pure functions with deps as params

### Model Types & Routes

- `BaseModelService` base for LoRA, Checkpoint, Embedding
- `ModelScanner` for file discovery, hash deduplication
- `PersistentModelCache` (SQLite) for persistence
- Route registrars: `ModelRouteRegistrar`, endpoints: `/loras/*`, `/checkpoints/*`, `/embeddings/*`
- WebSocket via `WebSocketManager` for real-time updates

### Recipe System

- Base: `py/recipes/base.py`, Enrichment: `RecipeEnrichmentService`
- Parsers: `py/recipes/parsers/`

## Important Notes

- ALWAYS use English for comments (per copilot-instructions.md)
- Dual mode: ComfyUI plugin (folder_paths) vs standalone (settings.json)
- Detection: `os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"`
- Run `python scripts/sync_translation_keys.py` after UI string updates
- Symlinks require normalized paths

## Frontend UI Architecture

### 1. Standalone Web UI
- Location: `./static/` and `./templates/`
- Tech: Vanilla JS + CSS, served by standalone server
- Tests via npm in root directory

### 2. ComfyUI Custom Node Widgets
- Location: `./web/comfyui/` (Vanilla JS) + `./vue-widgets/` (Vue)
- Primary styles: `./web/comfyui/lm_styles.css` (NOT `./static/css/`)
- Vue builds to `./web/comfyui/vue-widgets/`, typecheck via `vue-tsc`
