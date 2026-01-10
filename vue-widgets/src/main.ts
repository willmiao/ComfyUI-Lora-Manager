import { createApp, type App as VueApp } from 'vue'
import PrimeVue from 'primevue/config'
import DemoWidget from '@/components/DemoWidget.vue'

// @ts-ignore - ComfyUI external module
import { app } from '../../../scripts/app.js'

const vueApps = new Map<number, VueApp>()

// @ts-ignore
function createVueWidget(node) {
  const container = document.createElement('div')
  container.id = `lora-manager-demo-widget-${node.id}`
  container.style.width = '100%'
  container.style.height = '100%'
  container.style.minHeight = '300px'
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.overflow = 'hidden'

  const widget = node.addDOMWidget(
    'lora_demo_widget',
    'lora-manager-demo',
    container,
    {
      getMinHeight: () => 320,
      hideOnZoom: false,
      serialize: true
    }
  )

  const vueApp = createApp(DemoWidget, {
    widget,
    node
  })

  vueApp.use(PrimeVue)

  vueApp.mount(container)
  vueApps.set(node.id, vueApp)

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
  name: 'comfyui.loramanager.demo',

  getCustomWidgets() {
    return {
      // @ts-ignore
      LORA_DEMO_WIDGET(node) {
        return createVueWidget(node)
      }
    }
  },

  // @ts-ignore
  nodeCreated(node) {
    if (node.constructor?.comfyClass !== 'LoraManagerDemoNode') return

    const [oldWidth, oldHeight] = node.size

    node.setSize([Math.max(oldWidth, 350), Math.max(oldHeight, 400)])
  }
})
