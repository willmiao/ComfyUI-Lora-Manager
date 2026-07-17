/**
 * Tests for LoraInfoWidget — tab switching, lazy description loading,
 * state serialization roundtrip, and activeTab persistence.
 */

import { nextTick } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import LoraInfoWidget from '@/components/LoraInfoWidget.vue'
import { setupFetchMock, resetFetchMock } from '../setup'

// ── Helpers ──

function createMockFetchApi(overrides: {
  response?: unknown
  ok?: boolean
  error?: string
} = {}) {
  const { response = { success: true, metadata: {} }, ok = true } = overrides
  return vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(response),
  })
}

function createMockToast() {
  return { add: vi.fn() }
}

function createMockWidget(value?: unknown) {
  type PendingInfo = { name: string; notes: string; filePath: string; activeTab?: string } | null
  const widget = {
    serializeValue: (async () => null) as () => Promise<unknown>,
    value: (value ?? undefined) as unknown,
    onSetValue: undefined as unknown as ((v: unknown) => void),
    _setLoraInfo: undefined as unknown as (data: Record<string, unknown> | null) => void,
    __pendingLoraInfo: undefined as unknown as PendingInfo | undefined,
  }
  return widget
}

interface MountOptions {
  initialValue?: Record<string, unknown>
}

type TestWidget = ReturnType<typeof createMockWidget>

function mountWidget(options: MountOptions = {}) {
  const fetchApi = createMockFetchApi()
  const widget = createMockWidget(options.initialValue)
  const node = { id: 1 }
  const app = { extensionManager: { toast: createMockToast() } }

  const wrapper = shallowMount(LoraInfoWidget, {
    props: { widget, node, api: { fetchApi }, app },
  })

  return { wrapper, widget: widget as TestWidget, fetchApi, app }
}

// ── Tests ──

describe('LoraInfoWidget', () => {
  beforeEach(() => {
    setupFetchMock()
  })

  afterEach(() => {
    resetFetchMock()
  })

  describe('initial state', () => {
    it('shows placeholder when no LoRA is selected', () => {
      const { wrapper } = mountWidget()
      expect(wrapper.text()).toContain('No LoRA selected')
    })

    it('shows Notes tab by default when LoRA is set', async () => {
      const { wrapper, widget } = mountWidget()
      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      expect(wrapper.text()).toContain('test.safetensors')
      expect(wrapper.find('.notes-tab').isVisible()).toBe(true)
      expect(wrapper.find('.description-tab').isVisible()).toBe(false)
    })
  })

  describe('tab switching', () => {
    it('switches to Description tab and back to Notes', async () => {
      const { wrapper, widget } = mountWidget()
      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      const tabs = wrapper.findAll('.lora-info-tab')

      // Click Description tab
      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()

      expect(tabs[1].classes()).toContain('active')
      expect(wrapper.text()).toContain('No description available')

      // Switch back to Notes
      const notesTab = wrapper.findAll('.lora-info-tab-input')[0]
      await notesTab.setValue('notes')
      await nextTick()

      expect(tabs[0].classes()).toContain('active')
      expect(wrapper.text()).toContain('test.safetensors')
    })
  })

  describe('description lazy loading', () => {
    it('fetches metadata when Description tab is activated', async () => {
      const fetchApi = createMockFetchApi({
        response: {
          success: true,
          metadata: {
            description: '<p>Version desc</p>',
            model: { description: '<p>Model desc</p>' },
          },
        },
      })
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      // Switch to Description tab
      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick() // flush async fetch

      expect(fetchApi).toHaveBeenCalledWith(
        expect.stringContaining('/lm/loras/metadata'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(wrapper.html()).toContain('Version desc')
      expect(wrapper.html()).toContain('Model desc')
    })

    it('shows loading state while fetching', async () => {
      // Use a never-resolving promise to simulate loading
      const fetchApi = vi.fn().mockReturnValue(new Promise(() => {}))
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()

      expect(wrapper.text()).toContain('Loading description')
    })

    it('shows error state when fetch fails', async () => {
      const fetchApi = vi.fn().mockRejectedValue(new Error('Network error'))
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick()

      expect(wrapper.text()).toContain('Failed to load description')
    })

    it('shows empty state when metadata has no descriptions', async () => {
      const fetchApi = createMockFetchApi({
        response: {
          success: true,
          metadata: {
            description: '',
            model: {},
          },
        },
      })
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick()

      expect(wrapper.text()).toContain('No description available')
    })

    it('caches description and does not re-fetch on second activation', async () => {
      const fetchApi = createMockFetchApi({
        response: {
          success: true,
          metadata: {
            description: '<p>Version desc</p>',
            model: { description: '<p>Model desc</p>' },
          },
        },
      })
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      // First activation
      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick()

      expect(fetchApi).toHaveBeenCalledTimes(1)

      // Switch away and back
      const notesTab = wrapper.findAll('.lora-info-tab-input')[0]
      await notesTab.setValue('notes')
      await nextTick()
      await descriptionTab.setValue('description')
      await nextTick()

      // Should NOT have called fetch again
      expect(fetchApi).toHaveBeenCalledTimes(1)
    })

    it('re-fetches when LoRA selection changes', async () => {
      const fetchApi = createMockFetchApi({
        response: {
          success: true,
          metadata: {
            description: '<p>Version desc</p>',
            model: { description: '<p>Model desc</p>' },
          },
        },
      })
      const widget = createMockWidget()
      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      widget._setLoraInfo!({ name: 'first.safetensors', notes: '', filePath: '/path/first.safetensors' })
      await nextTick()

      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick()

      expect(fetchApi).toHaveBeenCalledTimes(1)

      // Select a different LoRA — resets description state
      widget._setLoraInfo!({ name: 'second.safetensors', notes: '', filePath: '/path/second.safetensors' })
      await nextTick()

      // Should show loading again (not cached)
      await descriptionTab.setValue('description')
      await nextTick()
      await nextTick()

      expect(fetchApi).toHaveBeenCalledTimes(2)
    })
  })

  describe('serialization roundtrip', () => {
    it('serializeValue includes activeTab', async () => {
      const { wrapper, widget } = mountWidget()
      widget._setLoraInfo!({ name: 'test.safetensors', notes: 'my notes', filePath: '/path/test.safetensors' })
      await nextTick()

      // Switch to Description tab
      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()

      const serialized = await widget.serializeValue!()
      expect(serialized).toMatchObject({
        name: 'test.safetensors',
        notes: 'my notes',
        filePath: '/path/test.safetensors',
        activeTab: 'description',
      })
    })

    it('onSetValue restores activeTab from workflow value', async () => {
      const { wrapper } = mountWidget({
        initialValue: {
          name: 'saved.safetensors',
          notes: 'saved notes',
          filePath: '/path/saved.safetensors',
          activeTab: 'description',
        },
      })

      await nextTick()

      // Description tab should be visible (activeTab restored to 'description')
      expect(wrapper.find('.description-tab').isVisible()).toBe(true)
      expect(wrapper.text()).toContain('saved.safetensors')
    })

    it('defaults to notes tab when activeTab is missing in saved value', async () => {
      const { wrapper } = mountWidget({
        initialValue: {
          name: 'legacy.safetensors',
          notes: 'legacy notes',
          filePath: '/path/legacy.safetensors',
          // No activeTab — legacy workflow
        },
      })

      await nextTick()

      expect(wrapper.find('.notes-tab').isVisible()).toBe(true)
    })
  })

  describe('_setLoraInfo race condition guard', () => {
    it('consumes __pendingLoraInfo pushed before mount', async () => {
      const widget = createMockWidget()
      widget.__pendingLoraInfo = {
        name: 'pending.safetensors',
        notes: 'pending notes',
        filePath: '/path/pending.safetensors',
      }

      const wrapper = shallowMount(LoraInfoWidget, {
        props: {
          widget,
          node: { id: 1 },
          api: { fetchApi: createMockFetchApi() },
          app: { extensionManager: { toast: createMockToast() } },
        },
      })

      await nextTick()

      expect(widget.__pendingLoraInfo).toBeUndefined()
      expect(wrapper.text()).toContain('pending.safetensors')
    })

    it('preserves activeTab when _setLoraInfo called with null (deselection)', async () => {
      const { wrapper, widget } = mountWidget()
      widget._setLoraInfo!({ name: 'test.safetensors', notes: '', filePath: '/path/test.safetensors' })
      await nextTick()

      // Switch to Description tab
      const descriptionTab = wrapper.findAll('.lora-info-tab-input')[1]
      await descriptionTab.setValue('description')
      await nextTick()

      // Deselect — template shows placeholder (no tab bar rendered)
      widget._setLoraInfo!(null)
      await nextTick()

      // Placeholder shown
      expect(wrapper.text()).toContain('No LoRA selected')

      // Re-select — activeTab should still be 'description'
      widget._setLoraInfo!({ name: 'second.safetensors', notes: '', filePath: '/path/second.safetensors' })
      await nextTick()

      const tabs = wrapper.findAll('.lora-info-tab')
      expect(tabs[1].classes()).toContain('active')
    })
  })
})
