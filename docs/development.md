# Development and Testing

User documentation lives in the [project Wiki](https://github.com/willmiao/ComfyUI-Lora-Manager/wiki). This page covers local development and verification for contributors working with the source code.

## Backend setup

Install runtime and development dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run all backend tests:

```bash
pytest
```

Run one file or test:

```bash
pytest tests/test_recipes.py
pytest tests/test_recipes.py::test_function_name
```

Generate backend coverage reports:

```bash
COVERAGE_FILE=coverage/backend/.coverage pytest \
  --cov=py \
  --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json
```

HTML, XML, and JSON reports are written under `coverage/backend/`.

## Frontend setup

Install root and Vue widget dependencies:

```bash
npm install
cd vue-widgets
npm install
cd ..
```

Run all frontend tests or only one suite:

```bash
npm test
npm run test:js
npm run test:vue
```

Generate frontend coverage:

```bash
npm run test:coverage
```

## Vue widgets

From `vue-widgets/`:

```bash
npm run build
npm run typecheck
npm test
```

Use `npm run dev` for watch-mode builds during widget development. Production output is written to `web/comfyui/vue-widgets/`.

## Localization

After adding user-facing strings to `locales/en.json`, synchronize translation keys:

```bash
python scripts/sync_translation_keys.py
```

Keep the maintained JSON layout. New untranslated values in other locales are expected to remain `[TODO: Translate]` placeholders until the feature owner requests translations.

## Documentation ownership

- `README.md` is the project landing page and quick-start summary.
- The Wiki is the canonical source for complete user guides, FAQs, and troubleshooting.
- In-app Help and contextual settings links point to those Wiki guides rather than duplicating them.
- `docs/` contains versioned technical references, node integration contracts, architecture notes, and development plans.

When moving or renaming a Wiki page, update README links, `templates/components/modals/help_modal.html`, contextual settings links, Wiki `Home.md`, and Wiki `_Sidebar.md` together.
