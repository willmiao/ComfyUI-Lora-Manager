import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import LoraPoolWidget from '@/components/LoraPoolWidget.vue'
import LoraRandomizerWidget from '@/components/LoraRandomizerWidget.vue'
import LoraCyclerWidget from '@/components/LoraCyclerWidget.vue'
import JsonDisplayWidget from '@/components/JsonDisplayWidget.vue'
import type { LoraPoolConfig, LegacyLoraPoolConfig, RandomizerConfig, CyclerConfig } from './composables/types'

const LORA_POOL_WIDGET_MIN_WIDTH = 500
const LORA_POOL_WIDGET_MIN_HEIGHT = 400
const LORA_RANDOMIZER_WIDGET_MIN_WIDTH = 500
const LORA_RANDOMIZER_WIDGET_MIN_HEIGHT = 448
const LORA_RANDOMIZER_WIDGET_MAX_HEIGHT = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
const LORA_CYCLER_WIDGET_MIN_WIDTH = 380
const LORA_CYCLER_WIDGET_MIN_HEIGHT = 410
const LORA_CYCLER_WIDGET_MAX_HEIGHT = LORA_CYCLER_WIDGET_MIN_HEIGHT
const JSON_DISPLAY_WIDGET_MIN_WIDTH = 300
const JSON_DISPLAY_WIDGET_MIN_HEIGHT = 200

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
        internalValue = v
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: true,
      getMinHeight() {
        return LORA_CYCLER_WIDGET_MIN_HEIGHT
      }
    }
  )

  widget.updateConfig = (v: CyclerConfig) => {
    internalValue = v
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
      }
    }
  },

  // Add display-only widget to Debug Metadata node
  // @ts-ignore
  async beforeRegisterNodeDef(nodeType, nodeData) {
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
