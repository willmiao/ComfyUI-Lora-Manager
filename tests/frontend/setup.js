import { afterEach, beforeEach } from 'vitest';
import { resetDom } from './utils/domFixtures.js';

beforeEach(() => {
  // Ensure storage is clean before each test to avoid cross-test pollution
  localStorage.clear();
  sessionStorage.clear();

  // Reset DOM state for modules that rely on body attributes
  resetDom();
});

afterEach(() => {
  // Clean any dynamically attached globals by tests
  resetDom();
});
