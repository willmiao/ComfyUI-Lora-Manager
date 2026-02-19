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
          ref="searchInputRef"
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Search tags..."
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

    <div ref="tagsContainerRef" class="tags-container" @scroll="handleScroll">
      <button
        v-for="tag in visibleTags"
        :key="tag.tag"
        type="button"
        class="tag-chip"
        :class="{ 'tag-chip--selected': isSelected(tag.tag) }"
        @click="toggleTag(tag.tag)"
      >
        {{ tag.tag }}
      </button>
      <div v-if="visibleTags.length === 0" class="no-results">
        No tags found
      </div>
      <div v-if="hasMoreTags" class="load-more-hint">
        Scroll to load more...
      </div>
    </div>
  </ModalWrapper>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
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
const searchInputRef = ref<HTMLInputElement | null>(null)
const tagsContainerRef = ref<HTMLElement | null>(null)
const displayedCount = ref(200)

const BATCH_SIZE = 200
const SCROLL_THRESHOLD = 100

const filteredTags = computed(() => {
  if (!searchQuery.value) {
    return props.tags
  }
  const query = searchQuery.value.toLowerCase()
  return props.tags.filter(t => t.tag.toLowerCase().includes(query))
})

const visibleTags = computed(() => {
  // When searching, show all filtered results
  if (searchQuery.value) {
    return filteredTags.value
  }
  // Otherwise, use virtual scrolling
  return filteredTags.value.slice(0, displayedCount.value)
})

const hasMoreTags = computed(() => {
  if (searchQuery.value) return false
  return displayedCount.value < filteredTags.value.length
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

const clearSearch = () => {
  searchQuery.value = ''
  displayedCount.value = BATCH_SIZE
  searchInputRef.value?.focus()
}

const handleScroll = () => {
  if (searchQuery.value) return
  
  const container = tagsContainerRef.value
  if (!container) return
  
  const { scrollTop, scrollHeight, clientHeight } = container
  const scrollBottom = scrollHeight - scrollTop - clientHeight
  
  // Load more tags when user scrolls near bottom
  if (scrollBottom < SCROLL_THRESHOLD && hasMoreTags.value) {
    displayedCount.value = Math.min(
      displayedCount.value + BATCH_SIZE,
      filteredTags.value.length
    )
  }
}

watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    displayedCount.value = BATCH_SIZE
    nextTick(() => {
      searchInputRef.value?.focus()
    })
  }
})

watch(() => props.tags, () => {
  displayedCount.value = BATCH_SIZE
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

.load-more-hint {
  width: 100%;
  padding: 12px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.4;
  font-size: 12px;
  font-style: italic;
}
</style>
