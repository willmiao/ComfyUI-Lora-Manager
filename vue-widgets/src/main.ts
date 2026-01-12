import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import LoraPoolWidget from '@/components/LoraPoolWidget.vue'
import type { LoraPoolConfig, LegacyLoraPoolConfig } from './composables/types'

// @ts-ignore - ComfyUI external module
import { app } from '../../../scripts/app.js'

const vueApps = new Map<number, VueApp>()

// @ts-ignore
function createLoraPoolWidget(node) {
  const container = document.createElement('div')
  container.id = `lora-pool-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

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
        return 700
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
    const minWidth = 500
    const minHeight = 700

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

app.registerExtension({
  name: 'LoraManager.VueWidgets',

  getCustomWidgets() {
    return {
      // @ts-ignore
      LORA_POOL_CONFIG(node) {
        return createLoraPoolWidget(node)
      }
    }
  }
})
