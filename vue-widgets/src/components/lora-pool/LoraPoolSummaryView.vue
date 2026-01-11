<template>
  <div class="summary-view">
    <!-- Header with filter count badge -->
    <div class="summary-view__header">
      <div class="summary-view__badge">
        <svg class="summary-view__badge-icon" viewBox="0 0 16 16" fill="currentColor">
          <path d="M1.5 1.5A.5.5 0 0 1 2 1h12a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-.128.334L10 8.692V13.5a.5.5 0 0 1-.342.474l-3 1A.5.5 0 0 1 6 14.5V8.692L1.628 3.834A.5.5 0 0 1 1.5 3.5v-2z"/>
        </svg>
        <span class="summary-view__count">{{ matchCount.toLocaleString() }}</span>
      </div>
    </div>

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

.summary-view__header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.summary-view__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: rgba(66, 153, 225, 0.15);
  border: 1px solid rgba(66, 153, 225, 0.4);
  border-radius: 4px;
  color: #4299e1;
}

.summary-view__badge-icon {
  width: 12px;
  height: 12px;
}

.summary-view__count {
  font-size: 12px;
  font-weight: 600;
}

.summary-view__filters {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  margin-right: -4px;
}
</style>
