/**
 * Test fixtures for LoRA Cycler testing
 */

import type { CyclerConfig, LoraPoolConfig } from '@/composables/types'
import type { CyclerLoraItem } from '@/composables/useLoraCyclerState'

/**
 * Creates a default CyclerConfig for testing
 */
export function createMockCyclerConfig(overrides: Partial<CyclerConfig> = {}): CyclerConfig {
  return {
    current_index: 1,
    total_count: 5,
    pool_config_hash: '',
    model_strength: 1.0,
    clip_strength: 1.0,
    use_same_clip_strength: true,
    sort_by: 'filename',
    current_lora_name: 'lora1.safetensors',
    current_lora_filename: 'lora1.safetensors',
    execution_index: null,
    next_index: null,
    repeat_count: 1,
    repeat_used: 0,
    is_paused: false,
    ...overrides
  }
}

/**
 * Creates a mock LoraPoolConfig for testing
 */
export function createMockPoolConfig(overrides: Partial<LoraPoolConfig> = {}): LoraPoolConfig {
  return {
    version: 1,
    filters: {
      baseModels: ['SD 1.5'],
      tags: { include: [], exclude: [] },
      folders: { include: [], exclude: [] },
      license: {
        noCreditRequired: false,
        allowSelling: false
      }
    },
    preview: { matchCount: 10, lastUpdated: Date.now() },
    ...overrides
  }
}

/**
 * Creates a list of mock LoRA items for testing
 */
export function createMockLoraList(count: number = 5): CyclerLoraItem[] {
  return Array.from({ length: count }, (_, i) => ({
    file_name: `lora${i + 1}.safetensors`,
    model_name: `LoRA Model ${i + 1}`
  }))
}

/**
 * Creates a mock widget object for testing useLoraCyclerState
 */
export function createMockWidget(initialValue?: CyclerConfig) {
  return {
    value: initialValue,
    callback: undefined as ((v: CyclerConfig) => void) | undefined
  }
}

/**
 * Creates a mock node object for testing component integration
 */
export function createMockNode(options: {
  id?: number
  poolConfig?: LoraPoolConfig | null
} = {}) {
  const { id = 1, poolConfig = null } = options
  return {
    id,
    inputs: [],
    widgets: [],
    graph: null,
    getPoolConfig: () => poolConfig,
    onExecuted: undefined as ((output: unknown) => void) | undefined
  }
}

/**
 * Creates mock execution output from the backend
 */
export function createMockExecutionOutput(options: {
  nextIndex?: number
  totalCount?: number
  nextLoraName?: string
  nextLoraFilename?: string
  currentLoraName?: string
  currentLoraFilename?: string
} = {}) {
  const {
    nextIndex = 2,
    totalCount = 5,
    nextLoraName = 'lora2.safetensors',
    nextLoraFilename = 'lora2.safetensors',
    currentLoraName = 'lora1.safetensors',
    currentLoraFilename = 'lora1.safetensors'
  } = options

  return {
    next_index: [nextIndex],
    total_count: [totalCount],
    next_lora_name: [nextLoraName],
    next_lora_filename: [nextLoraFilename],
    current_lora_name: [currentLoraName],
    current_lora_filename: [currentLoraFilename]
  }
}

/**
 * Sample LoRA lists for specific test scenarios
 */
export const SAMPLE_LORA_LISTS = {
  // 3 LoRAs for simple cycling tests
  small: createMockLoraList(3),

  // 5 LoRAs for standard tests
  medium: createMockLoraList(5),

  // 10 LoRAs for larger tests
  large: createMockLoraList(10),

  // Empty list for edge case testing
  empty: [] as CyclerLoraItem[],

  // Single LoRA for edge case testing
  single: createMockLoraList(1)
}

/**
 * Sample pool configs for testing
 */
export const SAMPLE_POOL_CONFIGS = {
  // Default SD 1.5 filter
  sd15: createMockPoolConfig({
    filters: {
      baseModels: ['SD 1.5'],
      tags: { include: [], exclude: [] },
      folders: { include: [], exclude: [] },
      license: { noCreditRequired: false, allowSelling: false }
    }
  }),

  // SDXL filter
  sdxl: createMockPoolConfig({
    filters: {
      baseModels: ['SDXL'],
      tags: { include: [], exclude: [] },
      folders: { include: [], exclude: [] },
      license: { noCreditRequired: false, allowSelling: false }
    }
  }),

  // Filter with tags
  withTags: createMockPoolConfig({
    filters: {
      baseModels: ['SD 1.5'],
      tags: { include: ['anime', 'style'], exclude: ['realistic'] },
      folders: { include: [], exclude: [] },
      license: { noCreditRequired: false, allowSelling: false }
    }
  }),

  // Empty/null config
  empty: null as LoraPoolConfig | null
}
