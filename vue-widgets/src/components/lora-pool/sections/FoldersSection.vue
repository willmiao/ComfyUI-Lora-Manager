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
        </div>
        <div class="section__input-row">
          <input
            v-model="includeInput"
            type="text"
            class="section__input"
            placeholder="Path..."
            @keydown.enter="addInclude"
          />
          <button
            type="button"
            class="section__add-btn section__add-btn--include"
            @click="addInclude"
          >
            +
          </button>
        </div>
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
      </div>

      <!-- Exclude column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--exclude">EXCLUDE</span>
        </div>
        <div class="section__input-row">
          <input
            v-model="excludeInput"
            type="text"
            class="section__input"
            placeholder="Path..."
            @keydown.enter="addExclude"
          />
          <button
            type="button"
            class="section__add-btn section__add-btn--exclude"
            @click="addExclude"
          >
            +
          </button>
        </div>
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import FilterChip from '../shared/FilterChip.vue'

const props = defineProps<{
  includeFolders: string[]
  excludeFolders: string[]
}>()

const emit = defineEmits<{
  'update:includeFolders': [value: string[]]
  'update:excludeFolders': [value: string[]]
}>()

const includeInput = ref('')
const excludeInput = ref('')

const truncatePath = (path: string) => {
  if (path.length <= 20) return path
  return '...' + path.slice(-17)
}

const addInclude = () => {
  const path = includeInput.value.trim()
  if (path && !props.includeFolders.includes(path)) {
    emit('update:includeFolders', [...props.includeFolders, path])
    includeInput.value = ''
  }
}

const removeInclude = (path: string) => {
  emit('update:includeFolders', props.includeFolders.filter(p => p !== path))
}

const addExclude = () => {
  const path = excludeInput.value.trim()
  if (path && !props.excludeFolders.includes(path)) {
    emit('update:excludeFolders', [...props.excludeFolders, path])
    excludeInput.value = ''
  }
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
  margin-bottom: 6px;
}

.section__column-title {
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.section__column-title--include {
  color: #22c55e;
}

.section__column-title--exclude {
  color: #ef4444;
}

.section__input-row {
  display: flex;
  gap: 4px;
}

.section__input {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--fg-color, #fff);
  font-size: 11px;
  outline: none;
}

.section__input:focus {
  border-color: var(--fg-color, #fff);
}

.section__input::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}

.section__add-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--fg-color, #fff);
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.section__add-btn:hover {
  border-color: var(--fg-color, #fff);
}

.section__add-btn--include:hover {
  background: rgba(34, 197, 94, 0.2);
  border-color: #22c55e;
  color: #22c55e;
}

.section__add-btn--exclude:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: #ef4444;
  color: #ef4444;
}

.section__paths {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
</style>
