import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/frontend/setup.js'],
    include: [
      'static/js/**/*.test.js',
      'tests/frontend/**/*.test.js'
    ],
    coverage: {
      enabled: false,
      reportsDirectory: 'coverage/frontend'
    }
  }
});
