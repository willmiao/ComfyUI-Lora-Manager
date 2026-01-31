/**
 * Vitest test setup file
 * Configures global mocks for ComfyUI modules and browser APIs
 */

import { vi } from 'vitest'

// Mock ComfyUI app module
vi.mock('../../../scripts/app.js', () => ({
  app: {
    graph: {
      _nodes: []
    },
    registerExtension: vi.fn()
  }
}))

// Mock ComfyUI loras_widget module
vi.mock('../loras_widget.js', () => ({
  addLoraCard: vi.fn(),
  removeLoraCard: vi.fn()
}))

// Mock ComfyUI autocomplete module
vi.mock('../autocomplete.js', () => ({
  setupAutocomplete: vi.fn()
}))

// Global fetch mock - exported so tests can access it directly
export const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Helper to reset fetch mock between tests
export function resetFetchMock() {
  mockFetch.mockReset()
  // Re-stub global to ensure it's the same mock
  vi.stubGlobal('fetch', mockFetch)
}

// Helper to setup fetch mock with default success response
export function setupFetchMock(response: unknown = { success: true, loras: [] }) {
  // Ensure we're using the same mock
  mockFetch.mockReset()
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(response)
  })
  vi.stubGlobal('fetch', mockFetch)
  return mockFetch
}

// Helper to setup fetch mock with error response
export function setupFetchErrorMock(error: string = 'Network error') {
  mockFetch.mockReset()
  mockFetch.mockRejectedValue(new Error(error))
  vi.stubGlobal('fetch', mockFetch)
  return mockFetch
}

// Mock btoa for hashing (jsdom should have this, but just in case)
if (typeof global.btoa === 'undefined') {
  vi.stubGlobal('btoa', (str: string) => Buffer.from(str).toString('base64'))
}

// Mock console methods to reduce noise in tests
vi.spyOn(console, 'log').mockImplementation(() => {})
vi.spyOn(console, 'error').mockImplementation(() => {})
vi.spyOn(console, 'warn').mockImplementation(() => {})

// Re-enable console for debugging when needed
export function enableConsole() {
  vi.spyOn(console, 'log').mockRestore()
  vi.spyOn(console, 'error').mockRestore()
  vi.spyOn(console, 'warn').mockRestore()
}
