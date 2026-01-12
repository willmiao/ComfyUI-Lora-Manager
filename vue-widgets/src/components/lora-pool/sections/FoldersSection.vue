<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">FOLDERS</span>
    </div>
    <div class="section__columns">
      <!-- Include column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--include">INCLUDE</span>
          <button
            type="button"
            class="section__edit-btn section__edit-btn--include"
            @click="$emit('edit-include')"
          >
            <svg viewBox="0 0 16 16" fill="currentColor">
              <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z"/>
            </svg>
          </button>
        </div>
        <div class="section__content">
          <div v-if="includeFolders.length > 0" class="section__paths">
            <FilterChip
              v-for="path in includeFolders"
              :key="path"
              :label="truncatePath(path)"
              variant="path"
              removable
              @remove="removeInclude(path)"
            />
          </div>
          <div v-else class="section__empty">
            No folders selected
          </div>
        </div>
      </div>

      <!-- Exclude column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--exclude">EXCLUDE</span>
          <button
            type="button"
            class="section__edit-btn section__edit-btn--exclude"
            @click="$emit('edit-exclude')"
          >
            <svg viewBox="0 0 16 16" fill="currentColor">
              <path d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z"/>
            </svg>
          </button>
        </div>
        <div class="section__content">
          <div v-if="excludeFolders.length > 0" class="section__paths">
            <FilterChip
              v-for="path in excludeFolders"
              :key="path"
              :label="truncatePath(path)"
              variant="path"
              removable
              @remove="removeExclude(path)"
            />
          </div>
          <div v-else class="section__empty">
            No folders selected
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import FilterChip from '../shared/FilterChip.vue'

const props = defineProps<{
  includeFolders: string[]
  excludeFolders: string[]
}>()

const emit = defineEmits<{
  'update:includeFolders': [value: string[]]
  'update:excludeFolders': [value: string[]]
  'edit-include': []
  'edit-exclude': []
}>()

const truncatePath = (path: string) => {
  if (path.length <= 20) return path
  return '...' + path.slice(-17)
}

const removeInclude = (path: string) => {
  emit('update:includeFolders', props.includeFolders.filter(p => p !== path))
}

const removeExclude = (path: string) => {
  emit('update:excludeFolders', props.excludeFolders.filter(p => p !== path))
}
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}

.section__header {
  margin-bottom: 8px;
}

.section__title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}

.section__columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.section__column {
  min-width: 0;
}

.section__column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.section__column-title {
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.section__column-title--include {
  color: #4299e1;
}

.section__column-title--exclude {
  color: #ef4444;
}

.section__edit-btn {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.5;
  border-radius: 3px;
  padding: 0;
  transition: all 0.15s;
}

.section__edit-btn svg {
  width: 12px;
  height: 12px;
}

.section__edit-btn:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}

.section__edit-btn--include:hover {
  color: #4299e1;
}

.section__edit-btn--exclude:hover {
  color: #ef4444;
}

.section__content {
  min-height: 22px;
}

.section__paths {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 22px;
}

.section__empty {
  font-size: 10px;
  color: var(--fg-color, #fff);
  opacity: 0.3;
  font-style: italic;
  min-height: 22px;
  display: flex;
  align-items: center;
}
</style>
