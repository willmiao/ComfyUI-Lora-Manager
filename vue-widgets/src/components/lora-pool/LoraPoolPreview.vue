<template>
  <div class="preview">
    <div class="preview__header">
      <span class="preview__title">Matching LoRAs: {{ matchCount }}</span>
      <button
        type="button"
        class="preview__refresh"
        :class="{ 'preview__refresh--loading': isLoading }"
        @click="$emit('refresh')"
        :disabled="isLoading"
      >
        <svg class="preview__refresh-icon" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z"/>
          <path fill-rule="evenodd" d="M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"/>
        </svg>
      </button>
    </div>

    <div v-if="items.length > 0" class="preview__list">
      <div
        v-for="item in items.slice(0, 5)"
        :key="item.file_path"
        class="preview__item"
      >
        <img
          v-if="item.preview_url"
          :src="item.preview_url"
          class="preview__thumb"
          @error="onImageError"
        />
        <div v-else class="preview__thumb preview__thumb--placeholder">
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
          </svg>
        </div>
        <span class="preview__name">{{ item.model_name || item.file_name }}</span>
      </div>

      <div v-if="matchCount > 5" class="preview__more">
        +{{ matchCount - 5 }} more
      </div>
    </div>

    <div v-else-if="!isLoading" class="preview__empty">
      No matching LoRAs
    </div>

    <div v-else class="preview__loading">
      Loading...
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LoraItem } from '../../composables/types'

defineProps<{
  items: LoraItem[]
  matchCount: number
  isLoading: boolean
}>()

defineEmits<{
  refresh: []
}>()

const onImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.preview {
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #444);
}

.preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.preview__title {
  font-size: 12px;
  font-weight: 500;
  color: var(--fg-color, #fff);
}

.preview__refresh {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.6;
  border-radius: 4px;
  transition: all 0.15s;
}

.preview__refresh:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}

.preview__refresh:disabled {
  cursor: not-allowed;
}

.preview__refresh-icon {
  width: 14px;
  height: 14px;
}

.preview__refresh--loading .preview__refresh-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.preview__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.preview__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
}

.preview__thumb {
  width: 28px;
  height: 28px;
  object-fit: cover;
  border-radius: 3px;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.2);
}

.preview__thumb--placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-color, #fff);
  opacity: 0.2;
}

.preview__thumb--placeholder svg {
  width: 14px;
  height: 14px;
}

.preview__name {
  flex: 1;
  font-size: 11px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview__more {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  padding: 6px;
}

.preview__empty,
.preview__loading {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.4;
  text-align: center;
  padding: 16px;
}
</style>
