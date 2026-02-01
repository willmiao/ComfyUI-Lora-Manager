<template>
  <ModalWrapper
    :visible="visible"
    title="Select LoRA"
    :subtitle="subtitleText"
    @close="$emit('close')"
  >
    <template #search>
      <div class="search-container">
        <svg class="search-icon" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
        </svg>
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Search LoRAs..."
        />
        <button
          v-if="searchQuery"
          type="button"
          class="clear-button"
          @click="clearSearch"
        >
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
          </svg>
        </button>
      </div>
    </template>

    <div class="lora-list">
      <div
        v-for="item in filteredList"
        :key="item.index"
        class="lora-item"
        :class="{ active: currentIndex === item.index }"
        @mouseenter="showPreview(item.lora.file_name, $event)"
        @mouseleave="hidePreview"
        @click="selectLora(item.index)"
      >
        <span class="lora-index">{{ item.index }}</span>
        <span class="lora-name" :title="item.lora.file_name">{{ item.lora.file_name }}</span>
        <span v-if="currentIndex === item.index" class="current-badge">Current</span>
      </div>
      <div v-if="filteredList.length === 0" class="no-results">
        No LoRAs found
      </div>
    </div>
  </ModalWrapper>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import ModalWrapper from '../lora-pool/modals/ModalWrapper.vue'
import type { LoraItem } from '../../composables/types'

interface LoraListItem {
  index: number
  lora: LoraItem
}

const props = defineProps<{
  visible: boolean
  loraList: LoraItem[]
  currentIndex: number
}>()

const emit = defineEmits<{
  close: []
  select: [index: number]
}>()

const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

// Preview tooltip instance (lazy init)
let previewTooltip: any = null

const subtitleText = computed(() => {
  const total = props.loraList.length
  const filtered = filteredList.value.length
  if (filtered === total) {
    return `Total: ${total} LoRA${total !== 1 ? 's' : ''}`
  }
  return `Showing ${filtered} of ${total} LoRA${total !== 1 ? 's' : ''}`
})

const filteredList = computed<LoraListItem[]>(() => {
  const list = props.loraList.map((lora, idx) => ({
    index: idx + 1,
    lora
  }))

  if (!searchQuery.value.trim()) {
    return list
  }

  const query = searchQuery.value.toLowerCase()
  return list.filter(item =>
    item.lora.file_name.toLowerCase().includes(query)
  )
})

const clearSearch = () => {
  searchQuery.value = ''
  searchInputRef.value?.focus()
}

const selectLora = (index: number) => {
  emit('select', index)
  emit('close')
}

// Custom preview URL resolver for Vue widgets environment
// The default preview_tooltip.js uses api.fetchApi which is mocked as native fetch
// in the Vue widgets build, so we need to use the full path with /api prefix
const customPreviewUrlResolver = async (modelName: string) => {
  const response = await fetch(
    `/api/lm/loras/preview-url?name=${encodeURIComponent(modelName)}&license_flags=true`
  )
  if (!response.ok) {
    throw new Error('Failed to fetch preview URL')
  }
  const data = await response.json()
  if (!data.success || !data.preview_url) {
    throw new Error('No preview available')
  }
  return {
    previewUrl: data.preview_url,
    displayName: data.display_name ?? modelName,
    licenseFlags: data.license_flags
  }
}

// Lazy load PreviewTooltip to avoid loading it unnecessarily
const getPreviewTooltip = async () => {
  if (!previewTooltip) {
    const { PreviewTooltip } = await import(/* @vite-ignore */ `${'../preview_tooltip.js'}`)
    previewTooltip = new PreviewTooltip({
      modelType: 'loras',
      displayNameFormatter: (name: string) => name,
      previewUrlResolver: customPreviewUrlResolver
    })
  }
  return previewTooltip
}

const showPreview = async (loraName: string, event: MouseEvent) => {
  const tooltip = await getPreviewTooltip()
  const rect = (event.target as HTMLElement).getBoundingClientRect()
  // Position to the right of the item, centered vertically
  tooltip.show(loraName, rect.right + 10, rect.top + rect.height / 2)
}

const hidePreview = async () => {
  if (previewTooltip) {
    previewTooltip.hide()
  }
}

// Focus search input when modal opens
watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    searchQuery.value = ''
    nextTick(() => {
      searchInputRef.value?.focus()
    })
  } else {
    // Hide preview when modal closes
    hidePreview()
  }
})

// Cleanup on unmount
onUnmounted(() => {
  if (previewTooltip) {
    previewTooltip.cleanup()
    previewTooltip = null
  }
})
</script>

<style scoped>
.search-container {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}

.search-input {
  width: 100%;
  padding: 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}

.search-input:focus {
  border-color: rgba(66, 153, 225, 0.6);
}

.search-input::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}

.clear-button {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  opacity: 0.5;
  transition: opacity 0.15s;
}

.clear-button:hover {
  opacity: 0.8;
}

.clear-button svg {
  width: 12px;
  height: 12px;
  color: var(--fg-color, #fff);
}

.lora-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 400px;
  overflow-y: auto;
}

.lora-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  border-left: 3px solid transparent;
}

.lora-item:hover {
  background: rgba(66, 153, 225, 0.15);
}

.lora-item.active {
  background: rgba(66, 153, 225, 0.25);
  border-left-color: rgba(66, 153, 225, 0.8);
}

.lora-index {
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.5);
  min-width: 3ch;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.lora-name {
  flex: 1;
  font-size: 13px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(66, 153, 225, 0.3);
  border: 1px solid rgba(66, 153, 225, 0.5);
  border-radius: 4px;
  color: rgba(191, 219, 254, 1);
  font-weight: 500;
}

.no-results {
  padding: 32px 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}
</style>
