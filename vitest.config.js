import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/frontend/setup.js'],
    include: [
      'tests/frontend/**/*.test.js'
    ],
    coverage: {
      enabled: process.env.VITEST_COVERAGE === 'true',
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage/frontend'
    }
  }
});
