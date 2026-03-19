<template>
  <div class="lora-pool-widget">
    <!-- Summary View -->
    <LoraPoolSummaryView
      :selected-base-models="state.selectedBaseModels.value"
      :available-base-models="state.availableBaseModels.value"
      :include-tags="state.includeTags.value"
      :exclude-tags="state.excludeTags.value"
      :include-folders="state.includeFolders.value"
      :exclude-folders="state.excludeFolders.value"
      :no-credit-required="state.noCreditRequired.value"
      :allow-selling="state.allowSelling.value"
      :preview-items="state.previewItems.value"
      :match-count="state.matchCount.value"
      :is-loading="state.isLoading.value"
      @open-modal="openModal"
      @update:include-folders="state.includeFolders.value = $event"
      @update:exclude-folders="state.excludeFolders.value = $event"
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
