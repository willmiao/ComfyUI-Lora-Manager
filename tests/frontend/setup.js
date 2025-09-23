import { afterEach, beforeEach } from 'vitest';

beforeEach(() => {
  // Ensure storage is clean before each test to avoid cross-test pollution
  localStorage.clear();
  sessionStorage.clear();

  // Reset DOM state for modules that rely on body attributes
  document.body.innerHTML = '';
  document.body.dataset.page = '';
});

afterEach(() => {
  // Clean any dynamically attached globals by tests
  delete document.body.dataset.page;
});
