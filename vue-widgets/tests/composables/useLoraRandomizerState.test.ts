/**
 * Unit tests for useLoraRandomizerState composable
 *
 * Focuses on the seed-chain lifecycle: a manual roll replaces the displayed
 * loras out-of-band, so the stale seeds must be dropped or the next queue
 * regenerates the previous seeded roll instead of what the widget shows.
 */

import { describe, it, expect } from 'vitest'
import { useLoraRandomizerState } from '@/composables/useLoraRandomizerState'

const createMockWidget = () => ({ value: null as any })

describe('useLoraRandomizerState', () => {
  it('generateNewSeed shifts next_seed into execution_seed', () => {
    const state = useLoraRandomizerState(createMockWidget())
    state.initializeNextSeed()
    const firstNext = state.nextSeed.value
    expect(firstNext).not.toBeNull()

    state.generateNewSeed()
    expect(state.executionSeed.value).toBe(firstNext)
    expect(state.nextSeed.value).not.toBeNull()
    expect(state.nextSeed.value).not.toBe(firstNext)
  })

  it('resetSeeds clears both seeds so the next queue uses the displayed loras', () => {
    const state = useLoraRandomizerState(createMockWidget())
    state.initializeNextSeed()
    state.generateNewSeed()
    expect(state.executionSeed.value).not.toBeNull()

    state.resetSeeds()
    expect(state.executionSeed.value).toBeNull()
    expect(state.nextSeed.value).toBeNull()

    // After a reset, initializeNextSeed behaves like a first execution:
    // execution_seed stays null (backend executes the widget loras).
    state.initializeNextSeed()
    expect(state.executionSeed.value).toBeNull()
    expect(state.nextSeed.value).not.toBeNull()
  })
})
