# Repository Guidelines

## Project Structure & Module Organization
ComfyUI LoRA Manager pairs a Python backend with lightweight browser scripts. Backend modules live in `py/`, organized by responsibility: HTTP entry points under `routes/`, feature logic in `services/`, reusable helpers within `utils/`, and custom nodes in `nodes/`. Front-end widgets that extend the ComfyUI interface sit in `web/comfyui/`, while static images and templates are in `static/` and `templates/`. Shared localization files are stored in `locales/`, with workflow examples under `example_workflows/`. Tests currently reside alongside the source (`test_i18n.py`) until a dedicated `tests/` folder is introduced.

## Build, Test, and Development Commands
Install dependencies with `pip install -r requirements.txt` from the repo root. Launch the standalone server for iterative work via `python standalone.py --port 8188`; ComfyUI users can also load the extension directly through ComfyUI's custom node manager. Run backend checks with `python -m pytest test_i18n.py`, and target new test files explicitly (e.g. `python -m pytest tests/test_recipes.py` once added). Use `python scripts/sync_translation_keys.py` to reconcile locale keys after updating UI strings.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation and descriptive snake_case module/function names, mirroring files such as `py/services/settings_manager.py`. Classes remain PascalCase, constants UPPER_SNAKE_CASE, and loggers retrieved via `logging.getLogger(__name__)`. Prefer explicit type hints for new public APIs and docstrings that clarify side effects. JavaScript in `web/comfyui/` is modern ES modules; keep imports relative, favor camelCase functions, and mirror existing file suffixes like `_widget.js` for UI components.

## Testing Guidelines
Extend pytest coverage by co-locating tests near the code under test or in `tests/` with names like `test_<feature>.py`. When introducing new routes or services, add regression cases that mock ComfyUI dependencies (see the standalone mocking helpers in `standalone.py`). Prioritize deterministic fixtures for filesystem interactions and ensure translations include coverage when adding new locale keys. Always run `python -m pytest` before submitting work.

## Commit & Pull Request Guidelines
Commits follow the conventional pattern seen in `git log` (`feat(scope):`, `fix(scope):`, `chore(scope):`). Keep messages imperative and scoped to a single change. Pull requests should summarize the problem, detail the solution, list manual test evidence, and link any GitHub issues. Include UI screenshots or GIFs when front-end behavior changes, and call out migration steps (e.g., settings updates) in the PR description.

## Configuration & Localization Tips
Sample configuration defaults live in `settings.json.example`; copy it to `settings.json` and adjust model directories before running the standalone server. Whenever you add UI text, update `locales/<lang>.json` and run the translation sync script. Store reference assets in `civitai/` or `docs/` rather than mixing them with production templates, keeping the runtime folders (`static/`, `templates/`) deploy-ready.
