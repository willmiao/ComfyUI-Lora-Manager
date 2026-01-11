import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import LoraPoolWidget from '@/components/LoraPoolWidget.vue'

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

  const widget = node.addDOMWidget(
    'pool_config',
    'LORA_POOL_CONFIG',
    container,
    {
      // getMinHeight: () => 680,
      serialize: true
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

  widget.onRemove = () => {
    const vueApp = vueApps.get(node.id)
    if (vueApp) {
      vueApp.unmount()
      vueApps.delete(node.id)
    }
  }

  widget.computeLayoutSize = () => ({
    minHeight: 600,
    minWidth: 500
  })

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
