<template>
  <div class="summary-view">
    <!-- Filter sections -->
    <div class="summary-view__filters">
      <BaseModelSection
        :selected="selectedBaseModels"
        :models="availableBaseModels"
        @edit="$emit('open-modal', 'baseModels')"
      />

      <TagsSection
        :include-tags="includeTags"
        :exclude-tags="excludeTags"
        @edit-include="$emit('open-modal', 'includeTags')"
        @edit-exclude="$emit('open-modal', 'excludeTags')"
      />

      <FoldersSection
        :include-folders="includeFolders"
        :exclude-folders="excludeFolders"
        @update:include-folders="$emit('update:includeFolders', $event)"
        @update:exclude-folders="$emit('update:excludeFolders', $event)"
        @edit-include="$emit('open-modal', 'includeFolders')"
        @edit-exclude="$emit('open-modal', 'excludeFolders')"
      />

      <LicenseSection
        :no-credit-required="noCreditRequired"
        :allow-selling="allowSelling"
        @update:no-credit-required="$emit('update:noCreditRequired', $event)"
        @update:allow-selling="$emit('update:allowSelling', $event)"
      />
    </div>

    <!-- Preview -->
    <LoraPoolPreview
      :items="previewItems"
      :match-count="matchCount"
      :is-loading="isLoading"
      @refresh="$emit('refresh')"
    />
  </div>
</template>

<script setup lang="ts">
import BaseModelSection from './sections/BaseModelSection.vue'
import TagsSection from './sections/TagsSection.vue'
import FoldersSection from './sections/FoldersSection.vue'
import LicenseSection from './sections/LicenseSection.vue'
import LoraPoolPreview from './LoraPoolPreview.vue'
import type { BaseModelOption, LoraItem } from '../../composables/types'
import type { ModalType } from '../../composables/useModalState'

defineProps<{
  // Base models
  selectedBaseModels: string[]
  availableBaseModels: BaseModelOption[]
  // Tags
  includeTags: string[]
  excludeTags: string[]
  // Folders
  includeFolders: string[]
  excludeFolders: string[]
  // License
  noCreditRequired: boolean
  allowSelling: boolean
  // Preview
  previewItems: LoraItem[]
  matchCount: number
  isLoading: boolean
}>()

defineEmits<{
  'open-modal': [modal: ModalType]
  'update:includeFolders': [value: string[]]
  'update:excludeFolders': [value: string[]]
  'update:noCreditRequired': [value: boolean]
  'update:allowSelling': [value: boolean]
  refresh: []
}>()
</script>

<style scoped>
.summary-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.summary-view__filters {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  margin-right: -4px;
  /* Allow flex item to shrink below content size */
  min-height: 0;
}
</style>
