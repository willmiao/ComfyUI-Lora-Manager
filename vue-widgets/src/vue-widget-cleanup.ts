import type { App as VueApp } from 'vue'

export function createVueWidgetCleanup(vueApp: VueApp, onCleanup?: () => void) {
  let didUnmount = false

  return () => {
    if (didUnmount) {
      return
    }

    vueApp.unmount()
    didUnmount = true
    onCleanup?.()
  }
}
