<template>
  <ModalWrapper
    :visible="visible"
    :title="title"
    :subtitle="subtitle"
    :modal-class="variant === 'exclude' ? 'tags-modal--exclude' : 'tags-modal--include'"
    @close="$emit('close')"
  >
    <template #search>
      <div class="search-container">
        <svg class="search-icon" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Search tags..."
        />
      </div>
    </template>

    <div class="tags-container">
      <button
        v-for="tag in filteredTags"
        :key="tag.tag"
        type="button"
        class="tag-chip"
        :class="{ 'tag-chip--selected': isSelected(tag.tag) }"
        @click="toggleTag(tag.tag)"
      >
        {{ tag.tag }}
      </button>
      <div v-if="filteredTags.length === 0" class="no-results">
        No tags found
      </div>
    </div>
  </ModalWrapper>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import ModalWrapper from './ModalWrapper.vue'
import type { TagOption } from '../../../composables/types'

const props = defineProps<{
  visible: boolean
  tags: TagOption[]
  selected: string[]
  variant: 'include' | 'exclude'
}>()

const emit = defineEmits<{
  close: []
  'update:selected': [value: string[]]
}>()

const title = computed(() =>
  props.variant === 'include' ? 'Include Tags' : 'Exclude Tags'
)

const subtitle = computed(() =>
  props.variant === 'include'
    ? 'Select tags that items must have'
    : 'Select tags that items must NOT have'
)

const searchQuery = ref('')

const filteredTags = computed(() => {
  if (!searchQuery.value) {
    return props.tags
  }
  const query = searchQuery.value.toLowerCase()
  return props.tags.filter(t => t.tag.toLowerCase().includes(query))
})

const isSelected = (tag: string) => {
  return props.selected.includes(tag)
}

const toggleTag = (tag: string) => {
  const newSelected = isSelected(tag)
    ? props.selected.filter(t => t !== tag)
    : [...props.selected, tag]
  emit('update:selected', newSelected)
}
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

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-chip {
  padding: 6px 12px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 16px;
  color: var(--fg-color, #fff);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

/* Default hover (gray for neutral) */
.tag-chip:hover:not(.tag-chip--selected) {
  border-color: rgba(226, 232, 240, 0.5);
  background: rgba(255, 255, 255, 0.05);
}

/* Include variant hover - blue tint */
.tags-modal--include .tag-chip:hover:not(.tag-chip--selected) {
  border-color: rgba(66, 153, 225, 0.4);
  background: rgba(66, 153, 225, 0.08);
}

/* Exclude variant hover - red tint */
.tags-modal--exclude .tag-chip:hover:not(.tag-chip--selected) {
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
}

/* Selected chips hover - slightly deepen the color */
.tags-modal--include .tag-chip--selected:hover {
  background: rgba(66, 153, 225, 0.25);
  border-color: rgba(66, 153, 225, 0.7);
}

.tags-modal--exclude .tag-chip--selected:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.7);
}

/* Include variant - blue when selected */
.tags-modal--include .tag-chip--selected,
.tag-chip--selected {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.6);
  color: #4299e1;
}

/* Exclude variant - red when selected */
.tags-modal--exclude .tag-chip--selected {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.6);
  color: #ef4444;
}

.no-results {
  width: 100%;
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}
</style>
