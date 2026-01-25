import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import LoraPoolWidget from '@/components/LoraPoolWidget.vue'
import LoraRandomizerWidget from '@/components/LoraRandomizerWidget.vue'
import LoraCyclerWidget from '@/components/LoraCyclerWidget.vue'
import JsonDisplayWidget from '@/components/JsonDisplayWidget.vue'
import AutocompleteTextWidget from '@/components/AutocompleteTextWidget.vue'
import type { LoraPoolConfig, LegacyLoraPoolConfig, RandomizerConfig, CyclerConfig } from './composables/types'
import {
  setupModeChangeHandler,
  createModeChangeCallback,
  LORA_PROVIDER_NODE_TYPES
} from './mode-change-handler'

const LORA_POOL_WIDGET_MIN_WIDTH = 500
const LORA_POOL_WIDGET_MIN_HEIGHT = 400
const LORA_RANDOMIZER_WIDGET_MIN_WIDTH = 500
const LORA_RANDOMIZER_WIDGET_MIN_HEIGHT = 448
const LORA_RANDOMIZER_WIDGET_MAX_HEIGHT = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
const LORA_CYCLER_WIDGET_MIN_WIDTH = 380
const LORA_CYCLER_WIDGET_MIN_HEIGHT = 314
const LORA_CYCLER_WIDGET_MAX_HEIGHT = LORA_CYCLER_WIDGET_MIN_HEIGHT
const JSON_DISPLAY_WIDGET_MIN_WIDTH = 300
const JSON_DISPLAY_WIDGET_MIN_HEIGHT = 200
const AUTOCOMPLETE_TEXT_WIDGET_MIN_HEIGHT = 60
const AUTOCOMPLETE_TEXT_WIDGET_MAX_HEIGHT = 100

// @ts-ignore - ComfyUI external module
import { app } from '../../../scripts/app.js'
// @ts-ignore
import { getPoolConfigFromConnectedNode, getActiveLorasFromNode, updateConnectedTriggerWords, updateDownstreamLoaders } from '../../web/comfyui/utils.js'

function forwardMiddleMouseToCanvas(container: HTMLElement) {
  if (!container) return

  container.addEventListener('pointerdown', (event) => {
    if (event.button === 1) {
      const canvas = app.canvas
      if (canvas && typeof canvas.processMouseDown === 'function') {
        canvas.processMouseDown(event)
      }
    }
  })

  container.addEventListener('pointermove', (event) => {
    if ((event.buttons & 4) === 4) {
      const canvas = app.canvas
      if (canvas && typeof canvas.processMouseMove === 'function') {
        canvas.processMouseMove(event)
      }
    }
  })

  container.addEventListener('pointerup', (event) => {
    if (event.button === 1) {
      const canvas = app.canvas
      if (canvas && typeof canvas.processMouseUp === 'function') {
        canvas.processMouseUp(event)
      }
    }
  })
}

const vueApps = new Map<number, VueApp>()

// Cache for dynamically loaded addLorasWidget module
let addLorasWidgetCache: any = null

// @ts-ignore
function createLoraPoolWidget(node) {
  const container = document.createElement('div')
  container.id = `lora-pool-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue: LoraPoolConfig | LegacyLoraPoolConfig | undefined

  const widget = node.addDOMWidget(
    'pool_config',
    'LORA_POOL_CONFIG',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: LoraPoolConfig | LegacyLoraPoolConfig) {
        internalValue = v
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: true,
      // Per dev guide: providing getMinHeight via options allows the system to
      // skip expensive DOM measurements during rendering loop, improving performance
      getMinHeight() {
        return LORA_POOL_WIDGET_MIN_HEIGHT
      }
    }
  )

  widget.updateConfig = (v: LoraPoolConfig) => {
    internalValue = v
  }

  const vueApp = createApp(LoraPoolWidget, {
    widget,
    node
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  vueApps.set(node.id, vueApp)

  widget.computeLayoutSize = () => {
    const minWidth = LORA_POOL_WIDGET_MIN_WIDTH
    const minHeight = LORA_POOL_WIDGET_MIN_HEIGHT

    return { minHeight, minWidth }
  }

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id)
    }
  }

  return { widget }
}

// @ts-ignore
function createLoraRandomizerWidget(node) {
  const container = document.createElement('div')
  container.id = `lora-randomizer-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue: RandomizerConfig | undefined

  const widget = node.addDOMWidget(
    'randomizer_config',
    'RANDOMIZER_CONFIG',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: RandomizerConfig) {
        internalValue = v
        console.log('randomizer widget value update: ', internalValue)
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: true,
      getMinHeight() {
        return LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
      }
    }
  )

  widget.updateConfig = (v: RandomizerConfig) => {
    internalValue = v
  }

  // Add method to get pool config from connected node
  node.getPoolConfig = () => getPoolConfigFromConnectedNode(node)

  // Handle roll event from Vue component
  widget.onRoll = (randomLoras: any[]) => {
    // Find the loras widget on this node and update it
    const lorasWidget = node.widgets.find((w: any) => w.name === 'loras')
    if (lorasWidget) {
      lorasWidget.value = randomLoras
    }
  }

  const vueApp = createApp(LoraRandomizerWidget, {
    widget,
    node
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  vueApps.set(node.id + 10000, vueApp) // Offset to avoid collision with pool widget

  widget.computeLayoutSize = () => {
    const minWidth = LORA_RANDOMIZER_WIDGET_MIN_WIDTH
    const minHeight = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
    const maxHeight = LORA_RANDOMIZER_WIDGET_MAX_HEIGHT

    return { minHeight, minWidth, maxHeight }
  }

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id + 10000)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id + 10000)
    }
  }

  return { widget }
}

// @ts-ignore
function createLoraCyclerWidget(node) {
  const container = document.createElement('div')
  container.id = `lora-cycler-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue: CyclerConfig | undefined

  const widget = node.addDOMWidget(
    'cycler_config',
    'CYCLER_CONFIG',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: CyclerConfig) {
        const oldFilename = internalValue?.current_lora_filename
        internalValue = v
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
        // Update downstream loaders when the active LoRA filename changes
        if (oldFilename !== v?.current_lora_filename) {
          updateDownstreamLoaders(node)
        }
      },
      serialize: true,
      getMinHeight() {
        return LORA_CYCLER_WIDGET_MIN_HEIGHT
      }
    }
  )

  widget.updateConfig = (v: CyclerConfig) => {
    const oldFilename = internalValue?.current_lora_filename
    internalValue = v
    // Update downstream loaders when the active LoRA filename changes
    if (oldFilename !== v?.current_lora_filename) {
      updateDownstreamLoaders(node)
    }
  }

  // Add method to get pool config from connected node
  node.getPoolConfig = () => getPoolConfigFromConnectedNode(node)

  const vueApp = createApp(LoraCyclerWidget, {
    widget,
    node
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  vueApps.set(node.id + 30000, vueApp) // Offset to avoid collision with other widgets

  widget.computeLayoutSize = () => {
    const minWidth = LORA_CYCLER_WIDGET_MIN_WIDTH
    const minHeight = LORA_CYCLER_WIDGET_MIN_HEIGHT
    const maxHeight = LORA_CYCLER_WIDGET_MAX_HEIGHT

    return { minHeight, minWidth, maxHeight }
  }

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id + 30000)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id + 30000)
    }
  }

  return { widget }
}

// @ts-ignore
function createJsonDisplayWidget(node) {
  const container = document.createElement('div')
  container.id = `json-display-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue: Record<string, unknown> | undefined

  const widget = node.addDOMWidget(
    'metadata',
    'JSON_DISPLAY',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: Record<string, unknown>) {
        internalValue = v
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: false, // Display-only widget - don't save metadata in workflows
      getMinHeight() {
        return JSON_DISPLAY_WIDGET_MIN_HEIGHT
      }
    }
  )

  const vueApp = createApp(JsonDisplayWidget, {
    widget,
    node
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  vueApps.set(node.id + 20000, vueApp) // Offset to avoid collision with other widgets

  widget.computeLayoutSize = () => {
    const minWidth = JSON_DISPLAY_WIDGET_MIN_WIDTH
    const minHeight = JSON_DISPLAY_WIDGET_MIN_HEIGHT

    return { minHeight, minWidth }
  }

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id + 20000)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id + 20000)
    }
  }

  return { widget }
}

// Store nodeData options per widget type for autocomplete widgets
const widgetInputOptions: Map<string, { placeholder?: string }> = new Map()

// Listen for Vue DOM mode setting changes and dispatch custom event
const initVueDomModeListener = () => {
  if (app.ui?.settings?.addEventListener) {
    app.ui.settings.addEventListener('Comfy.VueNodes.Enabled.change', () => {
      // Use requestAnimationFrame to ensure the setting value has been updated
      // before we read it (the event may fire before internal state updates)
      requestAnimationFrame(() => {
        const isVueDomMode = app.ui?.settings?.getSettingValue?.('Comfy.VueNodes.Enabled') ?? false
        // Dispatch custom event for Vue components to listen to
        document.dispatchEvent(new CustomEvent('lora-manager:vue-mode-change', {
          detail: { isVueDomMode }
        }))
      })
    })
  }
}

// Initialize listener when app is ready
if (app.ui?.settings) {
  initVueDomModeListener()
} else {
  // Defer until app is ready
  const checkAppReady = setInterval(() => {
    if (app.ui?.settings) {
      initVueDomModeListener()
      clearInterval(checkAppReady)
    }
  }, 100)
}

// Factory function for creating autocomplete text widgets
// @ts-ignore
function createAutocompleteTextWidgetFactory(
  node: any,
  widgetName: string,
  modelType: 'loras' | 'embeddings' | 'prompt',
  inputOptions: { placeholder?: string } = {}
) {
  const container = document.createElement('div')
  container.id = `autocomplete-text-widget-${node.id}-${widgetName}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue = ''

  const widget = node.addDOMWidget(
    widgetName,
    `AUTOCOMPLETE_TEXT_${modelType.toUpperCase()}`,
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: string) {
        internalValue = v ?? ''
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: true,
      getMinHeight() {
        return AUTOCOMPLETE_TEXT_WIDGET_MIN_HEIGHT
      },
      ...(modelType === 'loras' && {
        getMaxHeight() {
          return AUTOCOMPLETE_TEXT_WIDGET_MAX_HEIGHT
        }
      })
    }
  )

  // Get spellcheck setting from ComfyUI settings (default: false)
  const spellcheck = app.ui?.settings?.getSettingValue?.('Comfy.TextareaWidget.Spellcheck') ?? false

  const vueApp = createApp(AutocompleteTextWidget, {
    widget,
    node,
    modelType,
    placeholder: inputOptions.placeholder || widgetName,
    showPreview: true,
    spellcheck
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  // Use a unique key combining node.id and widget name to avoid collisions
  const appKey = node.id * 100000 + widgetName.charCodeAt(0)
  vueApps.set(appKey, vueApp)

  widget.onRemove = () => {
    const vueApp = vueApps.get(appKey)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(appKey)
    }
  }

  return { widget }
}

app.registerExtension({
  name: 'LoraManager.VueWidgets',

    getCustomWidgets() {
    return {
      // @ts-ignore
      LORA_POOL_CONFIG(node) {
        return createLoraPoolWidget(node)
      },
      // @ts-ignore
      RANDOMIZER_CONFIG(node) {
        return createLoraRandomizerWidget(node)
      },
      // @ts-ignore
      CYCLER_CONFIG(node) {
        return createLoraCyclerWidget(node)
      },
      // @ts-ignore
      async LORAS(node: any) {
        if (!addLorasWidgetCache) {
          // @ts-ignore
          const module = await import(/* @vite-ignore */ '../loras_widget.js')
          addLorasWidgetCache = module.addLorasWidget
        }
        // Check if this is a randomizer node to enable lock buttons
        const isRandomizerNode = node.comfyClass === 'Lora Randomizer (LoraManager)'

        // For randomizer nodes, add a callback to update connected trigger words
        const callback = isRandomizerNode ? () => {
          updateDownstreamLoaders(node)
        } : null

        return addLorasWidgetCache(node, 'loras', { isRandomizerNode }, callback)
      },
      // Autocomplete text widget for LoRAs (used by Lora Loader, Lora Stacker, WanVideo Lora Select)
      // @ts-ignore
      AUTOCOMPLETE_TEXT_LORAS(node) {
        const options = widgetInputOptions.get(`${node.comfyClass}:text`) || {}
        return createAutocompleteTextWidgetFactory(node, 'text', 'loras', options)
      },
      // Autocomplete text widget for embeddings (used by Prompt node)
      // @ts-ignore
      AUTOCOMPLETE_TEXT_EMBEDDINGS(node) {
        const options = widgetInputOptions.get(`${node.comfyClass}:text`) || {}
        return createAutocompleteTextWidgetFactory(node, 'text', 'embeddings', options)
      },
      // Autocomplete text widget for prompt (supports both embeddings and custom words)
      // @ts-ignore
      AUTOCOMPLETE_TEXT_PROMPT(node) {
        const options = widgetInputOptions.get(`${node.comfyClass}:text`) || {}
        return createAutocompleteTextWidgetFactory(node, 'text', 'prompt', options)
      }
    }
  },

  // Add display-only widget to Debug Metadata node
  // Register mode change handlers for LoRA provider nodes
  // Extract and store input options for autocomplete widgets
  // @ts-ignore
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const comfyClass = nodeType.comfyClass

    // Extract and store input options for autocomplete widgets
    const inputs = { ...nodeData.input?.required, ...nodeData.input?.optional }
    for (const [inputName, inputDef] of Object.entries(inputs)) {
      // @ts-ignore
      if (Array.isArray(inputDef) && typeof inputDef[0] === 'string' && inputDef[0].startsWith('AUTOCOMPLETE_TEXT_')) {
        // @ts-ignore
        const options = inputDef[1] || {}
        widgetInputOptions.set(`${nodeData.name}:${inputName}`, options)
      }
    }

    // Register mode change handlers for LoRA provider nodes
    if (LORA_PROVIDER_NODE_TYPES.includes(comfyClass)) {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated

      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments)

        // Create node-specific callback for Lora Stacker (updates direct trigger toggles)
        const nodeSpecificCallback = comfyClass === "Lora Stacker (LoraManager)"
          ? (activeLoraNames: Set<string>) => updateConnectedTriggerWords(this, activeLoraNames)
          : undefined

        // Create and set up the mode change handler
        const onModeChange = createModeChangeCallback(this, updateDownstreamLoaders, nodeSpecificCallback)
        setupModeChangeHandler(this, onModeChange)
      }
    }

    // Add the JSON display widget to Debug Metadata node
    if (nodeData.name === 'Debug Metadata (LoraManager)') {
      const onNodeCreated = nodeType.prototype.onNodeCreated

      nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, [])

        // Add the JSON display widget
        createJsonDisplayWidget(this)
      }
    }
  }
})
