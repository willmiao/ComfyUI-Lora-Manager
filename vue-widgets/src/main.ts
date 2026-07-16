import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import LoraPoolWidget from '@/components/LoraPoolWidget.vue'
import LoraRandomizerWidget from '@/components/LoraRandomizerWidget.vue'
import LoraCyclerWidget from '@/components/LoraCyclerWidget.vue'
import JsonDisplayWidget from '@/components/JsonDisplayWidget.vue'
import AutocompleteTextWidget from '@/components/AutocompleteTextWidget.vue'
import LoraInfoWidget from '@/components/LoraInfoWidget.vue'
import { createVueWidgetCleanup } from './vue-widget-cleanup'
import type { LoraPoolConfig, RandomizerConfig, CyclerConfig } from './composables/types'
import {
  setupModeChangeHandler,
  createModeChangeCallback,
  LORA_CHAIN_NODE_TYPES
} from './mode-change-handler'

const LORA_POOL_WIDGET_MIN_WIDTH = 500
const LORA_POOL_WIDGET_MIN_HEIGHT = 520
const LORA_RANDOMIZER_WIDGET_MIN_WIDTH = 500
const LORA_RANDOMIZER_WIDGET_MIN_HEIGHT = 448
const LORA_RANDOMIZER_WIDGET_MAX_HEIGHT = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
const LORA_CYCLER_WIDGET_MIN_WIDTH = 380
const LORA_CYCLER_WIDGET_MIN_HEIGHT = 408
const LORA_CYCLER_WIDGET_MAX_HEIGHT = LORA_CYCLER_WIDGET_MIN_HEIGHT
const JSON_DISPLAY_WIDGET_MIN_WIDTH = 300
const JSON_DISPLAY_WIDGET_MIN_HEIGHT = 200
const LORA_INFO_WIDGET_MIN_WIDTH = 300
const LORA_INFO_WIDGET_MIN_HEIGHT = 200
const AUTOCOMPLETE_TEXT_WIDGET_MIN_HEIGHT = 60
const AUTOCOMPLETE_TEXT_WIDGET_MAX_HEIGHT = 100
// Per-modelType min size hints for node initial sizing.
// These are returned from the factory so ComfyUI's _initialMinSize mechanism
// gives the node a sensible default width (and height for prompt/embeddings).
const AUTOCOMPLETE_TEXT_MIN_WIDTH_DEFAULT = 400
const AUTOCOMPLETE_TEXT_MIN_HEIGHT_DEFAULT = 300
const AUTOCOMPLETE_METADATA_VERSION = 1
const LORA_MANAGER_WIDGET_IDS_PROPERTY = '__lm_widget_ids'

// @ts-ignore - ComfyUI external module
import { app } from '../../../scripts/app.js'
// @ts-ignore - ComfyUI external module
import { api } from '../../../scripts/api.js'
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

const vueApps = new Map<number | string, VueApp>()
let autocompleteTextWidgetInstanceId = 0

export function createAutocompleteTextWidgetInstanceId() {
  autocompleteTextWidgetInstanceId += 1
  return autocompleteTextWidgetInstanceId
}

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

  let internalValue: LoraPoolConfig | undefined

  const widget = node.addDOMWidget(
    'pool_config',
    'LORA_POOL_CONFIG',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: LoraPoolConfig) {
        internalValue = v
        // ComfyUI automatically calls widget.callback after setValue
        // No need for custom onSetValue mechanism
      },
      serialize: true,
      // Per dev guide: providing getMinHeight via options allows the system to
      // skip expensive DOM measurements during rendering loop, improving performance
      getMinHeight() {
        return LORA_POOL_WIDGET_MIN_HEIGHT
      }
    }
  )

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

  // Initialize with default config to avoid sending undefined/empty string to backend
  const defaultConfig: RandomizerConfig = {
    count_mode: 'range',
    count_fixed: 3,
    count_min: 2,
    count_max: 5,
    model_strength_min: 0.0,
    model_strength_max: 1.0,
    use_same_clip_strength: true,
    clip_strength_min: 0.0,
    clip_strength_max: 1.0,
    roll_mode: 'fixed',
    use_recommended_strength: false,
    recommended_strength_scale_min: 0.5,
    recommended_strength_scale_max: 1.0,
  }
  let internalValue: RandomizerConfig = defaultConfig

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
        // ComfyUI automatically calls widget.callback after setValue
        // No need for custom onSetValue mechanism
      },
      serialize: true,
      getMinHeight() {
        return LORA_RANDOMIZER_WIDGET_MIN_HEIGHT
      }
    }
  )

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
    node,
    api
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

  const defaultConfig: CyclerConfig = {
    current_index: 1,
    total_count: 0,
    pool_config_hash: '',
    model_strength: 1.0,
    clip_strength: 1.0,
    use_same_clip_strength: true,
    use_preset_strength: false,
    preset_strength_scale: 1.0,
    sort_by: 'filename',
    current_lora_name: '',
    current_lora_filename: '',
    repeat_count: 1,
    repeat_used: 0,
    is_paused: false,
    include_no_lora: false,
  }
  let internalValue: CyclerConfig | undefined = defaultConfig

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
        // ComfyUI automatically calls widget.callback after setValue
        // No need for custom onSetValue mechanism
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

  // Add method to get pool config from connected node
  node.getPoolConfig = () => getPoolConfigFromConnectedNode(node)

  const vueApp = createApp(LoraCyclerWidget, {
    widget,
    node,
    api
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

const widgetInputOptions: Map<string, { placeholder?: string }> = new Map()

function getSerializableWidgetNames(node: any): string[] {
  return (node.widgets || [])
    .filter((widget: any) => widget && widget.serialize !== false)
    .map((widget: any) => widget.name)
}

function createAutocompleteMetadataValue(textWidgetName = 'text') {
  return {
    version: AUTOCOMPLETE_METADATA_VERSION,
    textWidgetName
  }
}

function shouldBypassAutocompleteWidgetMigration(
  node: any,
  widgetValues: unknown[]
): boolean {
  const inputDefs = node?.constructor?.nodeData?.inputs
  if (!inputDefs || !Array.isArray(widgetValues)) {
    return false
  }

  const widgetNames = new Set((node.widgets || []).map((widget: any) => widget?.name))
  const hasAutocompleteMetadataWidget = Array.from(widgetNames).some((name) =>
    typeof name === 'string' && name.startsWith('__lm_autocomplete_meta_')
  )

  if (!hasAutocompleteMetadataWidget) {
    return false
  }

  const originalWidgetsInputs = Object.values(inputDefs).filter((input: any) =>
    widgetNames.has(input.name) || input.forceInput
  )

  const widgetIndexHasForceInput = originalWidgetsInputs.flatMap((input: any) =>
    input.control_after_generate
      ? [!!input.forceInput, false]
      : [!!input.forceInput]
  )

  const result = (
    widgetIndexHasForceInput.some(Boolean) &&
    widgetIndexHasForceInput.length === widgetValues.length
  )

  return result
}

function remapWidgetValuesByName(
  widgetValues: unknown[],
  savedWidgetNames: string[],
  currentWidgetNames: string[]
): unknown[] {
  const valueByName = new Map<string, unknown>()
  savedWidgetNames.forEach((name, index) => {
    if (index < widgetValues.length) {
      valueByName.set(name, widgetValues[index])
    }
  })

  const currentWidgetNameSet = new Set(currentWidgetNames)
  const remappedValues: unknown[] = []
  for (const name of currentWidgetNames) {
    if (valueByName.has(name)) {
      remappedValues.push(valueByName.get(name))
    }
  }

  // Append values for saved widget names that are NOT in the current widget
  // list (e.g. forceInput widgets like "seed" that haven't been converted
  // back to DOM widgets yet at configure time).  Without these, the
  // resulting array may accidentally match the length of ComfyUI's
  // widgetIndexHasForceInput array, causing migrateWidgetsValues to
  // incorrectly filter out the wrong values and drop real widget content.
  for (const name of savedWidgetNames) {
    if (!currentWidgetNameSet.has(name) && valueByName.has(name)) {
      remappedValues.push(valueByName.get(name))
    }
  }

  return remappedValues
}

function injectDefaultAutocompleteMetadataValues(
  widgetValues: unknown[],
  currentWidgetNames: string[]
): unknown[] {
  const repairedValues: unknown[] = []
  let legacyValueIndex = 0

  for (const widgetName of currentWidgetNames) {
    if (widgetName.startsWith('__lm_autocomplete_meta_')) {
      const textWidgetName = widgetName.replace('__lm_autocomplete_meta_', '') || 'text'
      repairedValues.push(createAutocompleteMetadataValue(textWidgetName))
      continue
    }

    if (legacyValueIndex < widgetValues.length) {
      repairedValues.push(widgetValues[legacyValueIndex])
      legacyValueIndex++
    }
  }

  return repairedValues
}

function normalizeAutocompleteWidgetValues(node: any, info: any) {
  if (!info || !Array.isArray(info.widgets_values)) {
    return
  }

  const currentWidgetNames = getSerializableWidgetNames(node)

  if (currentWidgetNames.length === 0) {
    return
  }

  const savedWidgetNames = info.properties?.[LORA_MANAGER_WIDGET_IDS_PROPERTY]

  if (Array.isArray(savedWidgetNames) && savedWidgetNames.length > 0) {
    const remappedValues = remapWidgetValuesByName(
      info.widgets_values,
      savedWidgetNames,
      currentWidgetNames
    )
    info.widgets_values = remappedValues
    return
  }

  const metadataWidgetCount = currentWidgetNames.filter((name) =>
    name.startsWith('__lm_autocomplete_meta_')
  ).length

  if (
    metadataWidgetCount > 0 &&
    info.widgets_values.length === currentWidgetNames.length - metadataWidgetCount
  ) {
    const repairedValues = injectDefaultAutocompleteMetadataValues(
      info.widgets_values,
      currentWidgetNames
    )
    info.widgets_values = repairedValues
  }
}

function applyAutocompleteTextLayoutFix(
  widget: any,
  _container: HTMLElement | undefined,
  isVueMode: boolean
): void {
  // In Vue rendering mode the WidgetDOM wrapper handles sizing, so we
  // only provide a computeSize hint and leave the container unconstrained.
  // In canvas mode we clear all custom sizing so LiteGraph's default
  // widget-area layout takes over.  Neither path sets a hard max-height;
  // the textarea can grow freely (e.g. in app mode where
  // [&_textarea]:resize-y applies).
  if (isVueMode) {
    ;(widget as any).computeLayoutSize = undefined
    widget.computeSize = (width?: number) =>
      [width ?? 200, AUTOCOMPLETE_TEXT_WIDGET_MAX_HEIGHT - 4]
  } else {
    delete (widget as any).computeLayoutSize
    delete (widget as any).computeSize
  }
}

// Listen for Vue DOM mode setting changes and dispatch custom event
const initVueDomModeListener = () => {
  if (app.ui?.settings?.addEventListener) {
    app.ui.settings.addEventListener('Comfy.VueNodes.Enabled.change', () => {
      // Use requestAnimationFrame to ensure the setting value has been updated
      // before we read it (the event may fire before internal state updates)
      requestAnimationFrame(() => {
        const isVueDomMode = app.ui?.settings?.getSettingValue?.('Comfy.VueNodes.Enabled') ?? false

        if (app.graph?.nodes) {
          for (const node of app.graph.nodes) {
            const textWidget = node.widgets?.find(
              (w: any) => w.type === 'AUTOCOMPLETE_TEXT_LORAS'
            )
            if (!textWidget) continue
            const container = (textWidget as any).element as HTMLElement | undefined
            applyAutocompleteTextLayoutFix(textWidget, container, isVueDomMode)
          }
        }

        requestAnimationFrame(() => {
          for (const nodeEl of document.querySelectorAll('[data-node-id]')) {
            const grid = nodeEl.querySelector('[data-testid="node-widgets"]') as HTMLElement | null
            if (!grid) continue
            const nodeId = nodeEl.getAttribute('data-node-id')
            const node = app.graph?.getNodeById(nodeId as any)
            if (!node) continue
            const rows: string[] = []
            let needsFix = false
            for (const w of node.widgets ?? []) {
              if (w.type === 'LORA_MANAGER_AUTOCOMPLETE_METADATA') {
                rows.push('min-content')
              } else if (w.name === 'loras') {
                rows.push('auto')
              } else if (w.name === 'text' && w.type === 'AUTOCOMPLETE_TEXT_LORAS') {
                rows.push(isVueDomMode ? 'min-content' : 'auto')
                needsFix = true
              } else {
                rows.push('auto')
              }
            }
            if (needsFix) {
              grid.style.gridTemplateRows = rows.join(' ')
            }
          }
        })

        app.canvas?.setDirty(true, true)

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

// @ts-ignore
function createLoraInfoWidget(node: any) {
  const container = document.createElement('div')
  container.id = `lora-info-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  forwardMiddleMouseToCanvas(container)

  let internalValue: { name?: string; notes?: string; filePath?: string } | undefined

  const widget = node.addDOMWidget(
    'lora_info_display',
    'LORA_INFO_DISPLAY',
    container,
    {
      getValue() {
        return internalValue
      },
      setValue(v: { name?: string; notes?: string; filePath?: string }) {
        internalValue = v
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v)
        }
      },
      serialize: false, // Display-only widget
      getMinHeight() {
        return LORA_INFO_WIDGET_MIN_HEIGHT
      }
    }
  )

  const vueApp = createApp(LoraInfoWidget, {
    widget,
    node,
    api,
    app,
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  vueApps.set(node.id + 40000, vueApp) // Offset to avoid collision

  widget.computeLayoutSize = () => {
    const minWidth = LORA_INFO_WIDGET_MIN_WIDTH
    const minHeight = LORA_INFO_WIDGET_MIN_HEIGHT

    return { minHeight, minWidth }
  }

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id + 40000)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id + 40000)
    }
  }

  return { widget }
}

// Factory function for creating autocomplete text widgets
// @ts-ignore
function createAutocompleteTextWidgetFactory(
  node: any,
  widgetName: string,
  modelType: 'loras' | 'embeddings' | 'prompt',
  inputOptions: { placeholder?: string } = {}
) {
  const metadataWidgetName = `__lm_autocomplete_meta_${widgetName}`

  let container: HTMLElement | null = null

  const existingContainers = document.querySelectorAll<HTMLElement>(
    '[id^="autocomplete-text-widget-"]'
  )
  for (const el of existingContainers) {
    if (el.children.length === 0) {
      container = el
      break
    }
  }

  if (!container) {
    const instanceId = String(createAutocompleteTextWidgetInstanceId())
    container = document.createElement('div')
    container.id = `autocomplete-text-widget-${instanceId}`
    container.style.width = '100%'
    container.style.height = '100%'
    container.style.display = 'flex'
    container.style.flexDirection = 'column'
    container.style.overflow = 'hidden'
    forwardMiddleMouseToCanvas(container)
  }

  // Store textarea reference on the container element so cloned widgets can access it
  // This is necessary because when widgets are promoted to subgraph nodes,
  // the cloned widget shares the same element but needs access to inputEl
  const widgetElementRef = { inputEl: undefined as HTMLTextAreaElement | undefined }
  ;(container as any).__widgetInputEl = widgetElementRef

  const metadataWidget = node.addWidget('text', metadataWidgetName, {
    version: AUTOCOMPLETE_METADATA_VERSION,
    textWidgetName: widgetName
  })
  metadataWidget.value = createAutocompleteMetadataValue(widgetName)
  metadataWidget.type = 'LORA_MANAGER_AUTOCOMPLETE_METADATA'
  metadataWidget.hidden = true
  metadataWidget.computeSize = () => [0, -4]
  metadataWidget.serializeValue = () => metadataWidget.value

  const widget = node.addDOMWidget(
    widgetName,
    `AUTOCOMPLETE_TEXT_${modelType.toUpperCase()}`,
    container,
    {
      getValue() {
        // Access inputEl from widget or from the shared element reference
        const inputEl = widget.inputEl ?? (container as any).__widgetInputEl?.inputEl
        return inputEl?.value ?? ''
      },
      setValue(v: string) {
        // Access inputEl from widget or from the shared element reference
        const inputEl = widget.inputEl ?? (container as any).__widgetInputEl?.inputEl
        if (inputEl) {
          inputEl.value = v ?? ''
          // Notify Vue component of value change via custom event
          inputEl.dispatchEvent(new CustomEvent('lora-manager:autocomplete-value-changed', {
            detail: { value: v ?? '' }
          }))
        } else {
          ;(widget as any)._pendingValue = v ?? ''
        }
        // Also call onSetValue if defined (for Vue component integration)
        if (typeof widget.onSetValue === 'function') {
          widget.onSetValue(v ?? '')
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
  widget.metadataWidget = metadataWidget

  // Get spellcheck setting from ComfyUI settings (default: false)
  const spellcheck = app.ui?.settings?.getSettingValue?.('Comfy.TextareaWidget.Spellcheck') ?? false

  const maxHeight = modelType === 'loras' ? AUTOCOMPLETE_TEXT_WIDGET_MAX_HEIGHT : undefined

  const vueApp = createApp(AutocompleteTextWidget, {
    widget,
    node,
    modelType,
    placeholder: inputOptions.placeholder || widgetName,
    showPreview: true,
    spellcheck,
    maxHeight
  })

  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  })

  vueApp.mount(container)
  const appKey = container.id
  vueApps.set(appKey, vueApp)

  if (maxHeight) {
    container.style.minHeight = `${AUTOCOMPLETE_TEXT_WIDGET_MIN_HEIGHT}px`
  }

  if (modelType === 'loras') {
    applyAutocompleteTextLayoutFix(
      widget,
      container,
      typeof LiteGraph !== 'undefined' && LiteGraph.vueNodesMode
    )
  }

  const vueCleanup = createVueWidgetCleanup(vueApp, () => {
    vueApps.delete(appKey)
  })

  widget.onRemove = () => {
    vueCleanup()
  }

  // Return minWidth/minHeight hints so ComfyUI's _initialMinSize mechanism
  // sets a sensible initial node width (and height for prompt/embeddings).
  // loras modelType retains its existing height constraints (getMaxHeight: 100).
  const minWidth = AUTOCOMPLETE_TEXT_MIN_WIDTH_DEFAULT
  const minHeight = modelType === 'loras' ? undefined : AUTOCOMPLETE_TEXT_MIN_HEIGHT_DEFAULT

  return { widget, minWidth, minHeight }
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

        const opts: { isRandomizerNode?: boolean; onSelectionChange?: (selection: any) => void } = {
          isRandomizerNode,
        }
        if (isRandomizerNode) {
          opts.onSelectionChange = async (selection: any) => {
            if (!selection?.name || !selection?.active) return

            // Walk outputs to find directly connected Lora Info nodes
            const infoNodes: any[] = []
            if (node.outputs) {
              for (const output of node.outputs) {
                if (!output?.links?.length) continue
                for (const linkId of output.links) {
                  const links = node.graph?.links
                  if (!links) continue
                  const link = Array.isArray(links) ? links[linkId] : links.get?.(linkId)
                  if (!link) continue
                  const targetNode = node.graph?.getNodeById?.(link.target_id)
                  if (targetNode?.comfyClass === 'Lora Info (LoraManager)') {
                    infoNodes.push(targetNode)
                  }
                }
              }
            }

            if (infoNodes.length === 0) return

            // Bump request token to guard against stale async responses
            for (const infoNode of infoNodes) {
              infoNode.__loraInfoReqId = (infoNode.__loraInfoReqId || 0) + 1
            }
            const reqIdSnapshot = new Map<any, number>()
            for (const infoNode of infoNodes) {
              reqIdSnapshot.set(infoNode, infoNode.__loraInfoReqId)
            }

            // Fetch notes via the real ComfyUI api
            let infoData: any
            try {
              const response = await api.fetchApi(
                `/lm/loras/get-notes?name=${encodeURIComponent(selection.name)}`,
                { method: 'GET' }
              )
              if (response?.ok) {
                const data = await response.json()
                infoData = {
                  name: selection.name,
                  notes: data?.notes || '',
                  filePath: data?.file_path || '',
                }
              } else {
                infoData = { name: selection.name, notes: '[Error loading notes]', filePath: '' }
              }
            } catch {
              infoData = { name: selection.name, notes: '[Error loading notes]', filePath: '' }
            }

            for (const infoNode of infoNodes) {
              if (infoNode.__loraInfoReqId !== reqIdSnapshot.get(infoNode)) {
                continue
              }
              if (typeof infoNode._setLoraInfo === 'function') {
                infoNode._setLoraInfo(infoData)
              }
            }
          }
        }

        return addLorasWidgetCache(node, 'loras', opts, callback)
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
      },
    }
  },

  // Add display-only widget to Debug Metadata node
  // Register mode change handlers for LoRA provider nodes
  // Extract and store input options for autocomplete widgets
  // @ts-ignore
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const comfyClass = nodeType.comfyClass
    const inputs = { ...nodeData.input?.required, ...nodeData.input?.optional }
    let hasAutocompleteWidget = false

    // Extract and store input options for autocomplete widgets
    for (const [inputName, inputDef] of Object.entries(inputs)) {
      // @ts-ignore
      if (Array.isArray(inputDef) && typeof inputDef[0] === 'string' && inputDef[0].startsWith('AUTOCOMPLETE_TEXT_')) {
        // @ts-ignore
        const options = inputDef[1] || {}
        widgetInputOptions.set(`${nodeData.name}:${inputName}`, options)
        hasAutocompleteWidget = true
      }
    }

    if (hasAutocompleteWidget) {
      const originalOnSerialize = nodeType.prototype.onSerialize
      const originalConfigure = nodeType.prototype.configure

      nodeType.prototype.onSerialize = function (serialized: any) {
        originalOnSerialize?.apply(this, arguments)

        serialized.properties = serialized.properties || {}
        const widgetIds = getSerializableWidgetNames(this)
        serialized.properties[LORA_MANAGER_WIDGET_IDS_PROPERTY] = widgetIds
      }

      nodeType.prototype.configure = function (info: any) {
        normalizeAutocompleteWidgetValues(this, info)

        const bypassResult = shouldBypassAutocompleteWidgetMigration(this, info?.widgets_values ?? [])

        if (bypassResult) {
          info.widgets_values = [...(info.widgets_values ?? []), null]
        }

        return originalConfigure?.apply(this, arguments)
      }
    }

    // Register mode change handlers for LORA_STACK chain nodes
    if (LORA_CHAIN_NODE_TYPES.includes(comfyClass)) {
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

    // Add the Lora Info display widget
    if (nodeData.name === 'Lora Info (LoraManager)') {
      const onNodeCreated = nodeType.prototype.onNodeCreated

      nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, [])

        // Create the lora info display widget
        createLoraInfoWidget(this)
      }
    }
  }
})
