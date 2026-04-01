import { nextTick } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import LoraRandomizerWidget from '@/components/LoraRandomizerWidget.vue'
import type { LoraEntry, RandomizerConfig } from '@/composables/types'

function createApiMock() {
  const target = new EventTarget()
  return {
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    dispatchEvent: target.dispatchEvent.bind(target)
  }
}

function createDefaultConfig(): RandomizerConfig {
  return {
    count_mode: 'range',
    count_fixed: 3,
    count_min: 2,
    count_max: 5,
    model_strength_min: 0,
    model_strength_max: 1,
    use_same_clip_strength: true,
    clip_strength_min: 0,
    clip_strength_max: 1,
    roll_mode: 'always',
    use_recommended_strength: false,
    recommended_strength_scale_min: 0.5,
    recommended_strength_scale_max: 1
  }
}

describe('LoraRandomizerWidget deferred execution updates', () => {
  it('applies backend loras and last_used only after workflow completion', async () => {
    const initialLoras: LoraEntry[] = [
      {
        name: 'initial.safetensors',
        strength: 0.8,
        clipStrength: 0.8,
        active: true,
        expanded: false,
        locked: false
      }
    ]
    const deferredLoras: LoraEntry[] = [
      {
        name: 'deferred.safetensors',
        strength: 1,
        clipStrength: 1,
        active: true,
        expanded: false,
        locked: false
      }
    ]
    const lorasWidget = { name: 'loras', value: initialLoras }
    const node = {
      id: 101,
      widgets: [lorasWidget],
      onExecuted: vi.fn()
    }
    const widget = {
      value: createDefaultConfig()
    }
    const api = createApiMock()

    const wrapper = shallowMount(LoraRandomizerWidget, {
      props: {
        widget,
        node,
        api
      }
    })

    await nextTick()

    const settingsView = wrapper.findComponent({ name: 'LoraRandomizerSettingsView' })
    expect(settingsView.exists()).toBe(true)
    expect(settingsView.props('lastUsed')).toBeNull()

    ;(node as any).onExecuted({
      loras: deferredLoras,
      last_used: deferredLoras
    })
    await nextTick()

    expect(lorasWidget.value).toEqual(initialLoras)
    expect(settingsView.props('lastUsed')).toBeNull()

    api.dispatchEvent(new Event('execution_success'))
    await nextTick()

    expect(lorasWidget.value).toEqual(deferredLoras)
    expect(settingsView.props('lastUsed')).toEqual(deferredLoras)
  })
})
