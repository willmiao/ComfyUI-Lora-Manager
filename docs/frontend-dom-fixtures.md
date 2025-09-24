# Frontend DOM Fixture Strategy

This guide outlines how to reproduce the markup emitted by the Django templates while running Vitest in jsdom.  The aim is to make it straightforward to write integration-style unit tests for managers and UI helpers without having to duplicate template fragments inline.

## Loading Template Markup

Vitest executes inside Node, so we can read the same HTML templates that ship with the extension:

1. Use the helper utilities from `tests/frontend/utils/domFixtures.js` to read files under the `templates/` directory.
2. Mount the returned markup into `document.body` (or any custom container) before importing the module under test so its query selectors resolve correctly.

```js
import { renderTemplate } from '../utils/domFixtures.js'; // adjust the relative path to your spec

beforeEach(() => {
  renderTemplate('loras.html', {
    dataset: { page: 'loras' }
  });
});
```

The helper ensures the dataset is applied to the container, which mirrors how Django sets `data-page` in production.

## Working with Partial Components

Many features are implemented as template partials located under `templates/components/`.  When a test only needs a fragment (for example, the progress panel or context menu markup), load the component file directly:

```js
const container = renderTemplate('components/progress_panel.html');

const progressPanel = container.querySelector('#progress-panel');
```

This pattern avoids hand-written fixture strings and keeps the tests aligned with the actual markup.

## Resetting Between Tests

The shared Vitest setup clears `document.body` and storage APIs before each test.  If a suite adds additional DOM nodes outside of the body or needs to reset custom attributes mid-test, use `resetDom()` exported from `domFixtures.js`.

```js
import { resetDom } from '../utils/domFixtures.js';

afterEach(() => {
  resetDom();
});
```

## Future Enhancements

- Provide typed helpers for injecting mock script tags (e.g., replicating ComfyUI globals).
- Compose higher-level fixtures that mimic specific pages (loras, checkpoints, recipes) once those managers receive dedicated suites.
