/**
 * The widget defers its display update until the whole workflow finishes: the
 * index it shows at rest is the LoRA the next run will load. Downstream
 * TriggerWord Toggle nodes have to be refreshed at that same moment, otherwise
 * their word list keeps describing the previous LoRA and the node runs with a
 * stale set.
 */

import { nextTick } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoraCyclerWidget from '@/components/LoraCyclerWidget.vue'
import { createMockCyclerConfig } from '../fixtures/mockConfigs'
import { mockFetch, resetFetchMock } from '../setup'

function jsonResponse(payload: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
}

function createApi() {
  const target = new EventTarget()
  return {
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    dispatchEvent: target.dispatchEvent.bind(target)
  }
}

describe('LoraCyclerWidget trigger word sync', () => {
  let wrapper: ReturnType<typeof shallowMount> | undefined
  let widget: any

  beforeEach(() => {
    vi.useFakeTimers()
    resetFetchMock()
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/loras/cycler-list')) {
        return jsonResponse({
          success: true,
          loras: [
            { file_name: 'lora1.safetensors', model_name: 'LoRA 1', file_path: '/loras/lora1.safetensors' },
            { file_name: 'lora2.safetensors', model_name: 'LoRA 2', file_path: '/loras/lora2.safetensors' }
          ]
        })
      }
      return jsonResponse({})
    })
  })

  afterEach(() => {
    widget?.onRemoveCleanup?.()
    wrapper?.unmount()
    wrapper = undefined
    widget = undefined
    vi.useRealTimers()
  })

  it('refreshes downstream toggles once the next LoRA is on display', async () => {
    const saved = createMockCyclerConfig({
      total_count: 2,
      current_index: 1,
      current_lora_name: 'lora1.safetensors',
      current_lora_filename: 'lora1.safetensors'
    })
    widget = { value: saved }
    const node: any = { id: 1, widgets: [] }
    const api = createApi()
    const syncTriggerWords = vi.fn()

    wrapper = shallowMount(LoraCyclerWidget, {
      props: { widget, node, api, syncTriggerWords }
    })
    await flushPromises()

    widget.beforeQueued()
    node.onExecuted({
      next_index: 2,
      next_lora_name: 'lora2.safetensors',
      next_lora_filename: 'lora2.safetensors',
      current_lora_name: 'lora1.safetensors',
      current_lora_filename: 'lora1.safetensors'
    })

    // The display only moves when the workflow completes.
    expect(syncTriggerWords).not.toHaveBeenCalled()

    api.dispatchEvent(new Event('execution_success'))
    await nextTick()

    expect(syncTriggerWords).toHaveBeenCalledTimes(1)
    expect(syncTriggerWords).toHaveBeenCalledWith(node)
  })
})
