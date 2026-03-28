<template>
  <div class="lora-pool-widget" @wheel="onWheel">
    <!-- Summary View -->
    <LoraPoolSummaryView
      :selected-base-models="state.selectedBaseModels.value"
      :available-base-models="state.availableBaseModels.value"
      :include-tags="state.includeTags.value"
      :exclude-tags="state.excludeTags.value"
      :include-folders="state.includeFolders.value"
      :exclude-folders="state.excludeFolders.value"
      :include-patterns="state.includePatterns.value"
      :exclude-patterns="state.excludePatterns.value"
      :use-regex="state.useRegex.value"
      :no-credit-required="state.noCreditRequired.value"
      :allow-selling="state.allowSelling.value"
      :preview-items="state.previewItems.value"
      :match-count="state.matchCount.value"
      :is-loading="state.isLoading.value"
      @open-modal="openModal"
      @update:include-folders="state.includeFolders.value = $event"
      @update:exclude-folders="state.excludeFolders.value = $event"
      @update:include-patterns="state.includePatterns.value = $event"
      @update:exclude-patterns="state.excludePatterns.value = $event"
      @update:use-regex="state.useRegex.value = $event"
      @update:no-credit-required="state.noCreditRequired.value = $event"
      @update:allow-selling="state.allowSelling.value = $event"
      @refresh="state.refreshPreview"
    />

    <!-- Modals -->
    <BaseModelModal
      :visible="modalState.isModalOpen('baseModels')"
      :models="state.availableBaseModels.value"
      :selected="state.selectedBaseModels.value"
      @close="modalState.closeModal"
      @update:selected="state.selectedBaseModels.value = $event"
    />

    <TagsModal
      :visible="modalState.isModalOpen('includeTags')"
      :tags="state.availableTags.value"
      :selected="state.includeTags.value"
      variant="include"
      @close="modalState.closeModal"
      @update:selected="state.includeTags.value = $event"
    />

    <TagsModal
      :visible="modalState.isModalOpen('excludeTags')"
      :tags="state.availableTags.value"
      :selected="state.excludeTags.value"
      variant="exclude"
      @close="modalState.closeModal"
      @update:selected="state.excludeTags.value = $event"
    />

    <FoldersModal
      :visible="modalState.isModalOpen('includeFolders')"
      :folders="state.folderTree.value"
      :selected="state.includeFolders.value"
      variant="include"
      @close="modalState.closeModal"
      @update:selected="state.includeFolders.value = $event"
    />

    <FoldersModal
      :visible="modalState.isModalOpen('excludeFolders')"
      :folders="state.folderTree.value"
      :selected="state.excludeFolders.value"
      variant="exclude"
      @close="modalState.closeModal"
      @update:selected="state.excludeFolders.value = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import LoraPoolSummaryView from './lora-pool/LoraPoolSummaryView.vue'
import BaseModelModal from './lora-pool/modals/BaseModelModal.vue'
import TagsModal from './lora-pool/modals/TagsModal.vue'
import FoldersModal from './lora-pool/modals/FoldersModal.vue'
import { useLoraPoolState } from '../composables/useLoraPoolState'
import { useModalState, type ModalType } from '../composables/useModalState'
import type { ComponentWidget, LoraPoolConfig } from '../composables/types'

// Props
const props = defineProps<{
  widget: ComponentWidget<LoraPoolConfig>
  node: { id: number }
}>()

// State management
const state = useLoraPoolState(props.widget)
const modalState = useModalState()

// Modal handling
const openModal = (modal: ModalType) => {
  modalState.openModal(modal)
}

/**
 * Handle mouse wheel events on the widget.
 * Forwards the event to the ComfyUI canvas for zooming when appropriate.
 */
const onWheel = (event: WheelEvent) => {
  // Check if the event originated from a slider component
  // Sliders have data-capture-wheel="true" attribute
  const target = event.target as HTMLElement
  if (target?.closest('[data-capture-wheel="true"]')) {
    // Event is from a slider, slider already handled it
    // Just stop propagation to prevent canvas zoom
    event.stopPropagation()
    return
  }

  // Access ComfyUI app from global window
  const app = (window as any).app
  if (!app || !app.canvas || typeof app.canvas.processMouseWheel !== 'function') {
    return
  }

  const deltaX = event.deltaX
  const deltaY = event.deltaY
  const isHorizontal = Math.abs(deltaX) > Math.abs(deltaY)

  // 1. Handle pinch-to-zoom (ctrlKey is true for pinch-to-zoom on most browsers)
  if (event.ctrlKey) {
    event.preventDefault()
    event.stopPropagation()
    app.canvas.processMouseWheel(event)
    return
  }

  // 2. Horizontal scroll: pass to canvas (widgets usually don't scroll horizontally)
  if (isHorizontal) {
    event.preventDefault()
    event.stopPropagation()
    app.canvas.processMouseWheel(event)
    return
  }

  // 3. Vertical scrolling: forward to canvas
  event.preventDefault()
  event.stopPropagation()
  app.canvas.processMouseWheel(event)
}

// Lifecycle
onMounted(async () => {
  // Setup callback for external value updates (e.g., workflow load, undo/redo)
  // ComfyUI calls this automatically after setValue() in domWidget.ts
  // NOTE: callback should NOT call refreshPreview() to avoid infinite loops:
  // watch(filters) → refreshPreview() → buildConfig() → widget.value = v → callback → refreshPreview() → ...
  props.widget.callback = (v: LoraPoolConfig) => {
    if (v) {
      console.log('[LoraPoolWidget] Restoring config from callback')
      state.restoreFromConfig(v)
      // Preview will refresh automatically via watch() when restoreFromConfig changes filter refs
    }
  }

  // Restore from saved value if workflow was already loaded
  if (props.widget.value) {
    console.log('[LoraPoolWidget] Restoring from initial value')
    state.restoreFromConfig(props.widget.value as LoraPoolConfig)
  }

  // Fetch filter options
  await state.fetchFilterOptions()

  // Initial preview (only called once on mount)
  // When workflow is loaded, callback restores config, then watch triggers this
  await state.refreshPreview()
})
</script>

<style scoped>
.lora-pool-widget {
  padding: 12px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
</style>
