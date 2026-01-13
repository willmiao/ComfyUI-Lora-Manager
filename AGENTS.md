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
  --cov=py \
  --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json
```

### Frontend Development

```bash
# Install frontend dependencies
npm install

# Run frontend tests
npm test

# Run frontend tests in watch mode
npm run test:watch

# Run frontend tests with coverage
npm run test:coverage
```

## Python Code Style

### Imports

- Use `from __future__ import annotations` for forward references in type hints
- Group imports: standard library, third-party, local (separated by blank lines)
- Use absolute imports within `py/` package: `from ..services import X`
- Mock ComfyUI dependencies in tests using `tests/conftest.py` patterns

### Formatting & Types

- PEP 8 with 4-space indentation
- Type hints required for function signatures and class attributes
- Use `TYPE_CHECKING` guard for type-checking-only imports
- Prefer dataclasses for simple data containers
- Use `Optional[T]` for nullable types, `Union[T, None]` only when necessary

### Naming Conventions

- Files: `snake_case.py` (e.g., `model_scanner.py`, `lora_service.py`)
- Classes: `PascalCase` (e.g., `ModelScanner`, `LoraService`)
- Functions/variables: `snake_case` (e.g., `get_instance`, `model_type`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `VALID_LORA_TYPES`)
- Private members: `_single_underscore` (protected), `__double_underscore` (name-mangled)

### Error Handling

- Use `logging.getLogger(__name__)` for module-level loggers
- Define custom exceptions in `py/services/errors.py`
- Use `asyncio.Lock` for thread-safe singleton patterns
- Raise specific exceptions with descriptive messages
- Log errors at appropriate levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### Async Patterns

- Use `async def` for I/O-bound operations
- Mark async tests with `@pytest.mark.asyncio`
- Use `async with` for context managers
- Singleton pattern with class-level locks: see `ModelScanner.get_instance()`
- Use `aiohttp.web.Response` for HTTP responses

### Testing Patterns

- Use `pytest` with `--import-mode=importlib`
- Fixtures in `tests/conftest.py` handle ComfyUI mocking
- Use `@pytest.mark.no_settings_dir_isolation` for tests needing real paths
- Test files: `tests/test_*.py`
- Use `tmp_path_factory` for temporary directory isolation

## JavaScript Code Style

### Imports & Modules

- ES modules with `import`/`export`
- Use `import { app } from "../../scripts/app.js"` for ComfyUI integration
- Export named functions/classes: `export function foo() {}`
- Widget files use `*_widget.js` suffix

### Naming & Formatting

- camelCase for functions, variables, object properties
- PascalCase for classes/constructors
- Constants: `UPPER_SNAKE_CASE` (e.g., `CONVERTED_TYPE`)
- Files: `snake_case.js` or `kebab-case.js`
- 2-space indentation preferred (follow existing file conventions)

### Widget Development

- Use `app.registerExtension()` to register ComfyUI extensions
- Use `node.addDOMWidget(name, type, element, options)` for custom widgets
- Event handlers attached via `addEventListener` or widget callbacks
- See `web/comfyui/utils.js` for shared utilities

## Architecture Patterns

### Service Layer

- Use `ServiceRegistry` singleton for dependency injection
- Services follow singleton pattern via `get_instance()` class method
- Separate scanners (discovery) from services (business logic)
- Handlers in `py/routes/handlers/` implement route logic

### Model Types

- BaseModelService is abstract base for LoRA, Checkpoint, Embedding services
- ModelScanner provides file discovery and hash-based deduplication
- Persistent cache in SQLite via `PersistentModelCache`
- Metadata sync from CivitAI/CivArchive via `MetadataSyncService`

### Routes & Handlers

- Route registrars organize endpoints by domain: `ModelRouteRegistrar`, etc.
- Handlers are pure functions taking dependencies as parameters
- Use `WebSocketManager` for real-time progress updates
- Return `aiohttp.web.json_response` or `web.Response`

### Recipe System

- Base metadata in `py/recipes/base.py`
- Enrichment adds model metadata: `RecipeEnrichmentService`
- Parsers for different formats in `py/recipes/parsers/`

## Important Notes

- Always use English for comments (per copilot-instructions.md)
- Dual mode: ComfyUI plugin (uses folder_paths) vs standalone (reads settings.json)
- Detection: `os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"`
- Settings auto-saved in user directory or portable mode
- WebSocket broadcasts for real-time updates (downloads, scans)
- Symlink handling requires normalized paths
- API endpoints follow `/loras/*`, `/checkpoints/*`, `/embeddings/*` patterns
- Run `python scripts/sync_translation_keys.py` after UI string updates

## Frontend UI Architecture

This project has two distinct UI systems:

### 1. Standalone Lora Manager Web UI
- Location: `./static/` and `./templates/`
- Purpose: Full-featured web application for managing LoRA models
- Tech stack: Vanilla JS + CSS, served by the standalone server
- Development: Uses npm for frontend testing (`npm test`, `npm run test:watch`, etc.)

### 2. ComfyUI Custom Node Widgets
- Location: `./web/comfyui/`
- Purpose: Widgets and UI logic that ComfyUI loads as custom node extensions
- Tech stack: Vanilla JS + Vue.js widgets (in `./vue-widgets/` and built to `./web/comfyui/vue-widgets/`)
- Widget styling: Primary styles in `./web/comfyui/lm_styles.css` (NOT `./static/css/`)
- Development: No npm build step for these widgets (Vue widgets use build system)

### Widget Development Guidelines
- Use `app.registerExtension()` to register ComfyUI extensions (ComfyUI integration layer)
- Use `node.addDOMWidget()` for custom DOM widgets
- Widget styles should follow the patterns in `./web/comfyui/lm_styles.css`
  - Selected state: `rgba(66, 153, 225, 0.3)` background, `rgba(66, 153, 225, 0.6)` border
  - Hover state: `rgba(66, 153, 225, 0.2)` background
  - Color palette matches the Lora Manager accent color (blue #4299e1)
  - Use oklch() for color values when possible (defined in `./static/css/base.css`)
- Vue widget components are in `./vue-widgets/src/components/` and built to `./web/comfyui/vue-widgets/`
- When modifying widget styles, check `./web/comfyui/lm_styles.css` for consistency with other ComfyUI widgets

