<template>
  <div class="last-used-preview">
    <div class="last-used-preview__content">
      <div
        v-for="lora in displayLoras"
        :key="lora.name"
        class="last-used-preview__item"
      >
        <img
          v-if="previewUrls[lora.name]"
          :src="previewUrls[lora.name]"
          class="last-used-preview__thumb"
          @error="onImageError(lora.name)"
        />
        <div v-else class="last-used-preview__thumb last-used-preview__thumb--placeholder">
          <svg viewBox="0 0 16 16" fill="currentColor">
            <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
            <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
          </svg>
        </div>
        <div class="last-used-preview__info">
          <span class="last-used-preview__name">{{ lora.name }}</span>
          <span class="last-used-preview__strength">
            M: {{ lora.strength }}{{ lora.clipStrength !== undefined ? ` / C: ${lora.clipStrength}` : '' }}
          </span>
        </div>
      </div>
      <div v-if="loras.length > 5" class="last-used-preview__more">
        +{{ (loras.length - 5).toLocaleString() }} more LoRAs
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { LoraEntry } from '../../composables/types'

const props = defineProps<{
  loras: LoraEntry[]
}>()

const displayLoras = computed(() => props.loras.slice(0, 5))

// Preview URLs cache
const previewUrls = ref<Record<string, string>>({})

// Fetch preview URL for a lora using API
const fetchPreviewUrl = async (loraName: string) => {
  try {
    const response = await fetch(`/api/lm/loras/preview-url?name=${encodeURIComponent(loraName)}`)

    if (response.ok) {
      const data = await response.json()
      if (data.preview_url) {
        previewUrls.value[loraName] = data.preview_url
      }
    }
  } catch (error) {
    // Silent fail, just use placeholder
  }
}

// Load preview URLs on mount
props.loras.forEach(lora => {
  fetchPreviewUrl(lora.name)
})

const onImageError = (loraName: string) => {
  previewUrls.value[loraName] = ''
}
</script>

<style scoped>
.last-used-preview {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 8px;
  z-index: 100;
  width: 280px;
}

.last-used-preview__content {
  background: var(--comfy-menu-bg, #1a1a1a);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.last-used-preview__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
}

.last-used-preview__thumb {
  width: 28px;
  height: 28px;
  object-fit: cover;
  border-radius: 3px;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.2);
}

.last-used-preview__thumb--placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-color, #fff);
  opacity: 0.2;
}

.last-used-preview__thumb--placeholder svg {
  width: 14px;
  height: 14px;
}

.last-used-preview__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.last-used-preview__name {
  font-size: 11px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.last-used-preview__strength {
  font-size: 10px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}

.last-used-preview__more {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  padding: 4px;
}
</style>
