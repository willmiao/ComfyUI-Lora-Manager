import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '/extensions/ComfyUI-Lora-Manager/lora_node_adapters.js': fileURLToPath(
        new URL('./web/comfyui/lora_node_adapters.js', import.meta.url)
      ),
      '../../scripts/app.js': fileURLToPath(
        new URL('./scripts/app.js', import.meta.url)
      )
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['tests/frontend/setup.js'],
    include: [
      'tests/frontend/**/*.test.js',
      'tests/frontend/**/*.test.ts'
    ],
    coverage: {
      enabled: process.env.VITEST_COVERAGE === 'true',
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: 'coverage/frontend'
    }
  }
});
