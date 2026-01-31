/**
 * Unit tests for useLoraCyclerState composable
 *
 * Tests pure state transitions and index calculations in isolation.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useLoraCyclerState } from '@/composables/useLoraCyclerState'
import {
  createMockWidget,
  createMockCyclerConfig,
  createMockPoolConfig
} from '../fixtures/mockConfigs'
import { setupFetchMock, resetFetchMock } from '../setup'

describe('useLoraCyclerState', () => {
  beforeEach(() => {
    resetFetchMock()
  })

  describe('Initial State', () => {
    it('should initialize with default values', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      expect(state.currentIndex.value).toBe(1)
      expect(state.totalCount.value).toBe(0)
      expect(state.poolConfigHash.value).toBe('')
      expect(state.modelStrength.value).toBe(1.0)
      expect(state.clipStrength.value).toBe(1.0)
      expect(state.useCustomClipRange.value).toBe(false)
      expect(state.sortBy.value).toBe('filename')
      expect(state.executionIndex.value).toBeNull()
      expect(state.nextIndex.value).toBeNull()
      expect(state.repeatCount.value).toBe(1)
      expect(state.repeatUsed.value).toBe(0)
      expect(state.displayRepeatUsed.value).toBe(0)
      expect(state.isPaused.value).toBe(false)
    })
  })

  describe('restoreFromConfig', () => {
    it('should restore state from config object', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const config = createMockCyclerConfig({
        current_index: 3,
        total_count: 10,
        model_strength: 0.8,
        clip_strength: 0.6,
        use_same_clip_strength: false,
        repeat_count: 2,
        repeat_used: 1,
        is_paused: true
      })

      state.restoreFromConfig(config)

      expect(state.currentIndex.value).toBe(3)
      expect(state.totalCount.value).toBe(10)
      expect(state.modelStrength.value).toBe(0.8)
      expect(state.clipStrength.value).toBe(0.6)
      expect(state.useCustomClipRange.value).toBe(true) // inverted from use_same_clip_strength
      expect(state.repeatCount.value).toBe(2)
      expect(state.repeatUsed.value).toBe(1)
      expect(state.isPaused.value).toBe(true)
    })

    it('should handle missing optional fields with defaults', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      // Minimal config
      state.restoreFromConfig({
        current_index: 5,
        total_count: 10,
        pool_config_hash: '',
        model_strength: 1.0,
        clip_strength: 1.0,
        use_same_clip_strength: true,
        sort_by: 'filename',
        current_lora_name: '',
        current_lora_filename: '',
        repeat_count: 1,
        repeat_used: 0,
        is_paused: false
      })

      expect(state.currentIndex.value).toBe(5)
      expect(state.repeatCount.value).toBe(1)
      expect(state.isPaused.value).toBe(false)
    })

    it('should not restore execution_index and next_index (transient values)', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      // Set execution indices
      state.executionIndex.value = 2
      state.nextIndex.value = 3

      // Restore from config (these fields in config should be ignored)
      state.restoreFromConfig(createMockCyclerConfig({
        execution_index: 5,
        next_index: 6
      }))

      // Execution indices should remain unchanged
      expect(state.executionIndex.value).toBe(2)
      expect(state.nextIndex.value).toBe(3)
    })
  })

  describe('buildConfig', () => {
    it('should build config object from current state', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.currentIndex.value = 3
      state.totalCount.value = 10
      state.modelStrength.value = 0.8
      state.repeatCount.value = 2
      state.repeatUsed.value = 1
      state.isPaused.value = true

      const config = state.buildConfig()

      expect(config.current_index).toBe(3)
      expect(config.total_count).toBe(10)
      expect(config.model_strength).toBe(0.8)
      expect(config.repeat_count).toBe(2)
      expect(config.repeat_used).toBe(1)
      expect(config.is_paused).toBe(true)
    })
  })

  describe('setIndex', () => {
    it('should set index within valid range', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 10

      state.setIndex(5)
      expect(state.currentIndex.value).toBe(5)

      state.setIndex(1)
      expect(state.currentIndex.value).toBe(1)

      state.setIndex(10)
      expect(state.currentIndex.value).toBe(10)
    })

    it('should not set index outside valid range', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 10
      state.currentIndex.value = 5

      state.setIndex(0)
      expect(state.currentIndex.value).toBe(5) // unchanged

      state.setIndex(11)
      expect(state.currentIndex.value).toBe(5) // unchanged

      state.setIndex(-1)
      expect(state.currentIndex.value).toBe(5) // unchanged
    })
  })

  describe('resetIndex', () => {
    it('should reset index to 1 and clear repeatUsed and displayRepeatUsed', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.currentIndex.value = 5
      state.repeatUsed.value = 2
      state.displayRepeatUsed.value = 2
      state.isPaused.value = true

      state.resetIndex()

      expect(state.currentIndex.value).toBe(1)
      expect(state.repeatUsed.value).toBe(0)
      expect(state.displayRepeatUsed.value).toBe(0)
      expect(state.isPaused.value).toBe(true) // isPaused should NOT be reset
    })
  })

  describe('togglePause', () => {
    it('should toggle pause state', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      expect(state.isPaused.value).toBe(false)

      state.togglePause()
      expect(state.isPaused.value).toBe(true)

      state.togglePause()
      expect(state.isPaused.value).toBe(false)
    })
  })

  describe('generateNextIndex', () => {
    it('should shift indices correctly', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.currentIndex.value = 1
      state.nextIndex.value = 2

      // First call: executionIndex becomes 2 (previous nextIndex), nextIndex becomes 3
      state.generateNextIndex()

      expect(state.executionIndex.value).toBe(2)
      expect(state.nextIndex.value).toBe(3)

      // Second call: executionIndex becomes 3, nextIndex becomes 4
      state.generateNextIndex()

      expect(state.executionIndex.value).toBe(3)
      expect(state.nextIndex.value).toBe(4)
    })

    it('should wrap index from totalCount to 1', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.nextIndex.value = 5 // At the last index

      state.generateNextIndex()

      expect(state.executionIndex.value).toBe(5)
      expect(state.nextIndex.value).toBe(1) // Wrapped to 1
    })

    it('should use currentIndex when nextIndex is null', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.currentIndex.value = 3
      state.nextIndex.value = null

      state.generateNextIndex()

      // executionIndex becomes previous nextIndex (null)
      expect(state.executionIndex.value).toBeNull()
      // nextIndex is calculated from currentIndex (3) -> 4
      expect(state.nextIndex.value).toBe(4)
    })
  })

  describe('initializeNextIndex', () => {
    it('should initialize nextIndex to currentIndex + 1 when null', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.currentIndex.value = 1
      state.nextIndex.value = null

      state.initializeNextIndex()

      expect(state.nextIndex.value).toBe(2)
    })

    it('should wrap nextIndex when currentIndex is at totalCount', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.currentIndex.value = 5
      state.nextIndex.value = null

      state.initializeNextIndex()

      expect(state.nextIndex.value).toBe(1) // Wrapped
    })

    it('should not change nextIndex if already set', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 5
      state.currentIndex.value = 1
      state.nextIndex.value = 4

      state.initializeNextIndex()

      expect(state.nextIndex.value).toBe(4) // Unchanged
    })
  })

  describe('Index Wrapping Edge Cases', () => {
    it('should handle single item pool', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 1
      state.currentIndex.value = 1
      state.nextIndex.value = null

      state.initializeNextIndex()

      expect(state.nextIndex.value).toBe(1) // Wraps back to 1
    })

    it('should handle zero total count gracefully', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.totalCount.value = 0
      state.currentIndex.value = 1
      state.nextIndex.value = null

      state.initializeNextIndex()

      // Should still calculate, even if totalCount is 0
      expect(state.nextIndex.value).toBe(2) // No wrapping since totalCount <= 0
    })
  })

  describe('hashPoolConfig', () => {
    it('should generate consistent hash for same config', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const config1 = createMockPoolConfig()
      const config2 = createMockPoolConfig()

      const hash1 = state.hashPoolConfig(config1)
      const hash2 = state.hashPoolConfig(config2)

      expect(hash1).toBe(hash2)
    })

    it('should generate different hash for different configs', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const config1 = createMockPoolConfig({
        filters: {
          baseModels: ['SD 1.5'],
          tags: { include: [], exclude: [] },
          folders: { include: [], exclude: [] },
          license: { noCreditRequired: false, allowSelling: false }
        }
      })

      const config2 = createMockPoolConfig({
        filters: {
          baseModels: ['SDXL'],
          tags: { include: [], exclude: [] },
          folders: { include: [], exclude: [] },
          license: { noCreditRequired: false, allowSelling: false }
        }
      })

      const hash1 = state.hashPoolConfig(config1)
      const hash2 = state.hashPoolConfig(config2)

      expect(hash1).not.toBe(hash2)
    })

    it('should return empty string for null config', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      expect(state.hashPoolConfig(null)).toBe('')
    })

    it('should return empty string for config without filters', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const config = { version: 1, preview: { matchCount: 0, lastUpdated: 0 } } as any

      expect(state.hashPoolConfig(config)).toBe('')
    })
  })

  describe('Clip Strength Synchronization', () => {
    it('should sync clipStrength with modelStrength when useCustomClipRange is false', async () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.useCustomClipRange.value = false
      state.modelStrength.value = 0.5

      // Wait for Vue reactivity
      await vi.waitFor(() => {
        expect(state.clipStrength.value).toBe(0.5)
      })
    })

    it('should not sync clipStrength when useCustomClipRange is true', async () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.useCustomClipRange.value = true
      state.clipStrength.value = 0.7
      state.modelStrength.value = 0.5

      // clipStrength should remain unchanged
      await vi.waitFor(() => {
        expect(state.clipStrength.value).toBe(0.7)
      })
    })
  })

  describe('Widget Value Synchronization', () => {
    it('should update widget.value when state changes', async () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.currentIndex.value = 3
      state.repeatCount.value = 2

      // Wait for Vue reactivity
      await vi.waitFor(() => {
        expect(widget.value?.current_index).toBe(3)
        expect(widget.value?.repeat_count).toBe(2)
      })
    })
  })

  describe('Repeat Logic State', () => {
    it('should track repeatUsed correctly', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.repeatCount.value = 3
      expect(state.repeatUsed.value).toBe(0)

      state.repeatUsed.value = 1
      expect(state.repeatUsed.value).toBe(1)

      state.repeatUsed.value = 3
      expect(state.repeatUsed.value).toBe(3)
    })
  })

  describe('fetchCyclerList', () => {
    it('should call API and return lora list', async () => {
      const mockLoras = [
        { file_name: 'lora1.safetensors', model_name: 'LoRA 1' },
        { file_name: 'lora2.safetensors', model_name: 'LoRA 2' }
      ]

      setupFetchMock({ success: true, loras: mockLoras })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const result = await state.fetchCyclerList(null)

      expect(result).toEqual(mockLoras)
      expect(state.isLoading.value).toBe(false)
    })

    it('should include pool config filters in request', async () => {
      const mockFetch = setupFetchMock({ success: true, loras: [] })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const poolConfig = createMockPoolConfig()
      await state.fetchCyclerList(poolConfig)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/lm/loras/cycler-list',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('pool_config')
        })
      )
    })

    it('should set isLoading during fetch', async () => {
      let resolvePromise: (value: unknown) => void
      const pendingPromise = new Promise(resolve => {
        resolvePromise = resolve
      })

      // Use mockFetch from setup instead of overriding global
      const { mockFetch } = await import('../setup')
      mockFetch.mockReset()
      mockFetch.mockReturnValue(pendingPromise)

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      const fetchPromise = state.fetchCyclerList(null)

      expect(state.isLoading.value).toBe(true)

      // Resolve the fetch
      resolvePromise!({
        ok: true,
        json: () => Promise.resolve({ success: true, loras: [] })
      })

      await fetchPromise

      expect(state.isLoading.value).toBe(false)
    })
  })

  describe('refreshList', () => {
    it('should update totalCount from API response', async () => {
      const mockLoras = [
        { file_name: 'lora1.safetensors', model_name: 'LoRA 1' },
        { file_name: 'lora2.safetensors', model_name: 'LoRA 2' },
        { file_name: 'lora3.safetensors', model_name: 'LoRA 3' }
      ]

      // Reset and setup fresh mock
      resetFetchMock()
      setupFetchMock({ success: true, loras: mockLoras })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      await state.refreshList(null)

      expect(state.totalCount.value).toBe(3)
    })

    it('should reset index to 1 when pool config hash changes', async () => {
      resetFetchMock()
      setupFetchMock({ success: true, loras: [{ file_name: 'lora1.safetensors', model_name: 'LoRA 1' }] })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      // Set initial state
      state.currentIndex.value = 5
      state.poolConfigHash.value = 'old-hash'

      // Refresh with new config (different hash)
      const newConfig = createMockPoolConfig({
        filters: {
          baseModels: ['SDXL'],
          tags: { include: [], exclude: [] },
          folders: { include: [], exclude: [] },
          license: { noCreditRequired: false, allowSelling: false }
        }
      })

      await state.refreshList(newConfig)

      expect(state.currentIndex.value).toBe(1)
    })

    it('should clamp index when totalCount decreases', async () => {
      // Setup mock first, then create state
      resetFetchMock()
      setupFetchMock({
        success: true,
        loras: [
          { file_name: 'lora1.safetensors', model_name: 'LoRA 1' },
          { file_name: 'lora2.safetensors', model_name: 'LoRA 2' },
          { file_name: 'lora3.safetensors', model_name: 'LoRA 3' }
        ]
      })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      // Set initial state with high index
      state.currentIndex.value = 10
      state.totalCount.value = 10

      await state.refreshList(null)

      expect(state.totalCount.value).toBe(3)
      expect(state.currentIndex.value).toBe(3) // Clamped to max
    })

    it('should update currentLoraName and currentLoraFilename', async () => {
      resetFetchMock()
      setupFetchMock({
        success: true,
        loras: [
          { file_name: 'lora1.safetensors', model_name: 'LoRA 1' },
          { file_name: 'lora2.safetensors', model_name: 'LoRA 2' }
        ]
      })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      // Set totalCount first so setIndex works, then set index
      state.totalCount.value = 2
      state.currentIndex.value = 2

      await state.refreshList(null)

      expect(state.currentLoraFilename.value).toBe('lora2.safetensors')
    })

    it('should handle empty list gracefully', async () => {
      resetFetchMock()
      setupFetchMock({ success: true, loras: [] })

      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)
      state.currentIndex.value = 5
      state.totalCount.value = 5

      await state.refreshList(null)

      expect(state.totalCount.value).toBe(0)
      // When totalCount is 0, Math.max(1, 0) = 1, but if currentIndex > totalCount it gets clamped to max(1, totalCount)
      // Looking at the actual code: Math.max(1, totalCount) where totalCount=0 gives 1
      expect(state.currentIndex.value).toBe(1)
      expect(state.currentLoraName.value).toBe('')
      expect(state.currentLoraFilename.value).toBe('')
    })
  })

  describe('isClipStrengthDisabled computed', () => {
    it('should return true when useCustomClipRange is false', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.useCustomClipRange.value = false
      expect(state.isClipStrengthDisabled.value).toBe(true)
    })

    it('should return false when useCustomClipRange is true', () => {
      const widget = createMockWidget()
      const state = useLoraCyclerState(widget)

      state.useCustomClipRange.value = true
      expect(state.isClipStrengthDisabled.value).toBe(false)
    })
  })
})
