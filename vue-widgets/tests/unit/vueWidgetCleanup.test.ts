import { describe, expect, it, vi } from 'vitest'
import { createVueWidgetCleanup } from '@/vue-widget-cleanup'

describe('createVueWidgetCleanup', () => {
  it('cleans up only the Vue app bound to the widget remove handler', () => {
    const firstCleanup = vi.fn()
    const secondCleanup = vi.fn()
    const firstApp = { unmount: vi.fn() }
    const secondApp = { unmount: vi.fn() }

    const removeFirst = createVueWidgetCleanup(firstApp as any, firstCleanup)
    const removeSecond = createVueWidgetCleanup(secondApp as any, secondCleanup)

    removeFirst()

    expect(firstApp.unmount).toHaveBeenCalledTimes(1)
    expect(firstCleanup).toHaveBeenCalledTimes(1)
    expect(secondApp.unmount).not.toHaveBeenCalled()
    expect(secondCleanup).not.toHaveBeenCalled()

    removeSecond()

    expect(secondApp.unmount).toHaveBeenCalledTimes(1)
    expect(secondCleanup).toHaveBeenCalledTimes(1)
  })

  it('is idempotent when ComfyUI calls the remove handler more than once', () => {
    const cleanup = vi.fn()
    const app = { unmount: vi.fn() }
    const remove = createVueWidgetCleanup(app as any, cleanup)

    remove()
    remove()

    expect(app.unmount).toHaveBeenCalledTimes(1)
    expect(cleanup).toHaveBeenCalledTimes(1)
  })
})
