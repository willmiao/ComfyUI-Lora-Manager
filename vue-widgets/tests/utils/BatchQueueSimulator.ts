/**
 * BatchQueueSimulator - Simulates ComfyUI's two execution modes
 *
 * ComfyUI has two distinct execution patterns:
 * 1. Batch Queue Mode: ALL beforeQueued calls happen BEFORE any onExecuted calls
 * 2. Sequential Mode: beforeQueued and onExecuted interleave for each prompt
 *
 * This simulator helps test how the widget behaves in both modes.
 */

import type { CyclerConfig } from '@/composables/types'

export interface ExecutionHooks {
  /** Called when a prompt is queued (before execution) */
  beforeQueued: () => void
  /** Called when execution completes with output */
  onExecuted: (output: unknown) => void
}

export interface SimulatorOptions {
  /** Total number of LoRAs in the pool */
  totalCount: number
  /** Function to generate output for each execution */
  generateOutput?: (executionIndex: number, config: CyclerConfig) => unknown
}

/**
 * Creates execution output based on the current state
 */
function defaultGenerateOutput(executionIndex: number, config: CyclerConfig) {
  // Calculate what the next index would be after this execution
  let nextIdx = (config.execution_index ?? config.current_index) + 1
  if (nextIdx > config.total_count) {
    nextIdx = 1
  }

  return {
    next_index: [nextIdx],
    total_count: [config.total_count],
    next_lora_name: [`lora${nextIdx}.safetensors`],
    next_lora_filename: [`lora${nextIdx}.safetensors`],
    current_lora_name: [`lora${config.execution_index ?? config.current_index}.safetensors`],
    current_lora_filename: [`lora${config.execution_index ?? config.current_index}.safetensors`]
  }
}

export class BatchQueueSimulator {
  private executionCount = 0
  private options: Required<SimulatorOptions>

  constructor(options: SimulatorOptions) {
    this.options = {
      totalCount: options.totalCount,
      generateOutput: options.generateOutput ?? defaultGenerateOutput
    }
  }

  /**
   * Reset the simulator state
   */
  reset() {
    this.executionCount = 0
  }

  /**
   * Simulates Batch Queue Mode execution
   *
   * In this mode, ComfyUI queues multiple prompts at once:
   * - ALL beforeQueued() calls happen first (for all prompts in the batch)
   * - THEN all onExecuted() calls happen (as each prompt completes)
   *
   * This is the mode used when queueing multiple prompts from the UI.
   *
   * @param count Number of prompts to simulate
   * @param hooks The widget's execution hooks
   * @param getConfig Function to get current widget config state
   */
  async runBatchQueue(
    count: number,
    hooks: ExecutionHooks,
    getConfig: () => CyclerConfig
  ): Promise<void> {
    // Phase 1: All beforeQueued calls (snapshot configs)
    const snapshotConfigs: CyclerConfig[] = []

    for (let i = 0; i < count; i++) {
      hooks.beforeQueued()
      // Snapshot the config after beforeQueued updates it
      snapshotConfigs.push({ ...getConfig() })
    }

    // Phase 2: All onExecuted calls (in order)
    for (let i = 0; i < count; i++) {
      const config = snapshotConfigs[i]
      const output = this.options.generateOutput(this.executionCount, config)
      hooks.onExecuted(output)
      this.executionCount++
    }
  }

  /**
   * Simulates Sequential Mode execution
   *
   * In this mode, execution is one-at-a-time:
   * - beforeQueued() is called
   * - onExecuted() is called
   * - Then the next prompt's beforeQueued() is called
   * - And so on...
   *
   * This is the mode used in API-driven execution or single prompt queuing.
   *
   * @param count Number of prompts to simulate
   * @param hooks The widget's execution hooks
   * @param getConfig Function to get current widget config state
   */
  async runSequential(
    count: number,
    hooks: ExecutionHooks,
    getConfig: () => CyclerConfig
  ): Promise<void> {
    for (let i = 0; i < count; i++) {
      // Queue the prompt
      hooks.beforeQueued()
      const config = { ...getConfig() }

      // Execute it immediately
      const output = this.options.generateOutput(this.executionCount, config)
      hooks.onExecuted(output)
      this.executionCount++
    }
  }

  /**
   * Simulates a single execution (queue + execute)
   */
  async runSingle(
    hooks: ExecutionHooks,
    getConfig: () => CyclerConfig
  ): Promise<void> {
    return this.runSequential(1, hooks, getConfig)
  }

  /**
   * Simulates interrupted execution (some beforeQueued calls without matching onExecuted)
   *
   * This can happen if the user cancels execution mid-batch.
   *
   * @param queuedCount Number of prompts queued (beforeQueued called)
   * @param executedCount Number of prompts that actually executed
   * @param hooks The widget's execution hooks
   * @param getConfig Function to get current widget config state
   */
  async runInterrupted(
    queuedCount: number,
    executedCount: number,
    hooks: ExecutionHooks,
    getConfig: () => CyclerConfig
  ): Promise<void> {
    if (executedCount > queuedCount) {
      throw new Error('executedCount cannot be greater than queuedCount')
    }

    // Phase 1: All beforeQueued calls
    const snapshotConfigs: CyclerConfig[] = []
    for (let i = 0; i < queuedCount; i++) {
      hooks.beforeQueued()
      snapshotConfigs.push({ ...getConfig() })
    }

    // Phase 2: Only some onExecuted calls
    for (let i = 0; i < executedCount; i++) {
      const config = snapshotConfigs[i]
      const output = this.options.generateOutput(this.executionCount, config)
      hooks.onExecuted(output)
      this.executionCount++
    }
  }
}

/**
 * Helper to create execution hooks from a widget-like object
 */
export function createHooksFromWidget(widget: {
  beforeQueued?: () => void
}, node: {
  onExecuted?: (output: unknown) => void
}): ExecutionHooks {
  return {
    beforeQueued: () => widget.beforeQueued?.(),
    onExecuted: (output) => node.onExecuted?.(output)
  }
}

/**
 * Tracks index history during simulation for assertions
 */
export class IndexTracker {
  public indexHistory: number[] = []
  public repeatHistory: number[] = []
  public pauseHistory: boolean[] = []

  reset() {
    this.indexHistory = []
    this.repeatHistory = []
    this.pauseHistory = []
  }

  record(config: CyclerConfig) {
    this.indexHistory.push(config.current_index)
    this.repeatHistory.push(config.repeat_used)
    this.pauseHistory.push(config.is_paused)
  }

  /**
   * Get the sequence of indices that were actually used for execution
   */
  getExecutionIndices(): number[] {
    return this.indexHistory
  }

  /**
   * Verify that indices cycle correctly through totalCount
   */
  verifyCyclePattern(expectedPattern: number[]): boolean {
    if (this.indexHistory.length !== expectedPattern.length) {
      return false
    }
    return this.indexHistory.every((idx, i) => idx === expectedPattern[i])
  }
}
