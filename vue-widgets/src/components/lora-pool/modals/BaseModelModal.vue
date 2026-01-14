<template>
  <ModalWrapper
    :visible="visible"
    title="Select Base Models"
    subtitle="Choose which base models to include in your filter"
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
          placeholder="Search models..."
          @input="onSearch"
        />
      </div>
    </template>

    <div class="model-list">
      <label
        v-for="model in filteredModels"
        :key="model.name"
        class="model-item"
      >
        <input
          type="checkbox"
          :checked="isSelected(model.name)"
          @change="toggleModel(model.name)"
          class="model-checkbox"
        />
        <span class="model-checkbox-visual">
          <svg v-if="isSelected(model.name)" class="check-icon" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
          </svg>
        </span>
        <span class="model-name">{{ model.name }}</span>
        <span class="model-count">({{ model.count }})</span>
      </label>
      <div v-if="filteredModels.length === 0" class="no-results">
        No models found
      </div>
    </div>
  </ModalWrapper>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import ModalWrapper from './ModalWrapper.vue'
import type { BaseModelOption } from '../../../composables/types'

const props = defineProps<{
  visible: boolean
  models: BaseModelOption[]
  selected: string[]
}>()

const emit = defineEmits<{
  close: []
  'update:selected': [value: string[]]
}>()

const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

const filteredModels = computed(() => {
  if (!searchQuery.value) {
    return props.models
  }
  const query = searchQuery.value.toLowerCase()
  return props.models.filter(m => m.name.toLowerCase().includes(query))
})

const isSelected = (name: string) => {
  return props.selected.includes(name)
}

const toggleModel = (name: string) => {
  const newSelected = isSelected(name)
    ? props.selected.filter(n => n !== name)
    : [...props.selected, name]
  emit('update:selected', newSelected)
}

const onSearch = () => {
  // Debounce handled by v-model reactivity
}

watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    nextTick(() => {
      searchInputRef.value?.focus()
    })
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
  padding: 8px 12px 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: var(--fg-color, #fff);
}

.search-input::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.model-item:hover {
  background: var(--comfy-input-bg, #333);
}

.model-checkbox {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.model-checkbox-visual {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 4px;
  flex-shrink: 0;
  transition: all 0.15s;
}

.model-item:hover .model-checkbox-visual {
  border-color: var(--fg-color, #fff);
}

.model-checkbox:checked + .model-checkbox-visual {
  background: var(--fg-color, #fff);
  border-color: var(--fg-color, #fff);
}

.check-icon {
  width: 12px;
  height: 12px;
  color: var(--comfy-menu-bg, #1a1a1a);
}

.model-name {
  flex: 1;
  font-size: 13px;
  color: var(--fg-color, #fff);
}

.model-count {
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}

.no-results {
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}
</style>
