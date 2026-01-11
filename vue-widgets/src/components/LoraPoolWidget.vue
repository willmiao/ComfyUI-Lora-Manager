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
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import LoraPoolSummaryView from './lora-pool/LoraPoolSummaryView.vue'
import BaseModelModal from './lora-pool/modals/BaseModelModal.vue'
import TagsModal from './lora-pool/modals/TagsModal.vue'
import { useLoraPoolState } from '../composables/useLoraPoolState'
import { useModalState, type ModalType } from '../composables/useModalState'
import type { ComponentWidget, LoraPoolConfig, LegacyLoraPoolConfig } from '../composables/types'

// Props
const props = defineProps<{
  widget: ComponentWidget
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
  console.log('[LoraPoolWidget] Mounted, node ID:', props.node.id)

  // Setup serialization
  props.widget.serializeValue = async () => {
    const config = state.buildConfig()
    console.log('[LoraPoolWidget] Serializing config:', config)
    return config
  }

  // Restore from saved value
  if (props.widget.value) {
    console.log('[LoraPoolWidget] Restoring from saved value:', props.widget.value)
    state.restoreFromConfig(props.widget.value as LoraPoolConfig | LegacyLoraPoolConfig)
  }

  // Fetch filter options
  await state.fetchFilterOptions()

  // Initial preview
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
