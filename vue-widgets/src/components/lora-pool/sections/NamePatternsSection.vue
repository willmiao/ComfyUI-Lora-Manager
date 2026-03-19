<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">NAME PATTERNS</span>
      <label class="section__toggle">
        <input
          type="checkbox"
          :checked="useRegex"
          @change="$emit('update:useRegex', ($event.target as HTMLInputElement).checked)"
        />
        <span class="section__toggle-label">Use Regex</span>
      </label>
    </div>
    <div class="section__columns">
      <!-- Include column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--include">INCLUDE</span>
        </div>
        <div class="section__input-wrapper">
          <input
            type="text"
            v-model="includeInput"
            :placeholder="useRegex ? 'Add regex pattern...' : 'Add text pattern...'"
            class="section__input"
            @keydown.enter="addInclude"
          />
          <button type="button" class="section__add-btn" @click="addInclude">+</button>
        </div>
        <div class="section__patterns">
          <FilterChip
            v-for="pattern in includePatterns"
            :key="pattern"
            :label="pattern"
            variant="include"
            removable
            @remove="removeInclude(pattern)"
          />
          <div v-if="includePatterns.length === 0" class="section__empty">
            {{ useRegex ? 'No regex patterns' : 'No text patterns' }}
          </div>
        </div>
      </div>

      <!-- Exclude column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--exclude">EXCLUDE</span>
        </div>
        <div class="section__input-wrapper">
          <input
            type="text"
            v-model="excludeInput"
            :placeholder="useRegex ? 'Add regex pattern...' : 'Add text pattern...'"
            class="section__input"
            @keydown.enter="addExclude"
          />
          <button type="button" class="section__add-btn" @click="addExclude">+</button>
        </div>
        <div class="section__patterns">
          <FilterChip
            v-for="pattern in excludePatterns"
            :key="pattern"
            :label="pattern"
            variant="exclude"
            removable
            @remove="removeExclude(pattern)"
          />
          <div v-if="excludePatterns.length === 0" class="section__empty">
            {{ useRegex ? 'No regex patterns' : 'No text patterns' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import FilterChip from '../shared/FilterChip.vue'

const props = defineProps<{
  includePatterns: string[]
  excludePatterns: string[]
  useRegex: boolean
}>()

const emit = defineEmits<{
  'update:includePatterns': [value: string[]]
  'update:excludePatterns': [value: string[]]
  'update:useRegex': [value: boolean]
}>()

const includeInput = ref('')
const excludeInput = ref('')

const addInclude = () => {
  const pattern = includeInput.value.trim()
  if (pattern && !props.includePatterns.includes(pattern)) {
    emit('update:includePatterns', [...props.includePatterns, pattern])
    includeInput.value = ''
  }
}

const addExclude = () => {
  const pattern = excludeInput.value.trim()
  if (pattern && !props.excludePatterns.includes(pattern)) {
    emit('update:excludePatterns', [...props.excludePatterns, pattern])
    excludeInput.value = ''
  }
}

const removeInclude = (pattern: string) => {
  emit('update:includePatterns', props.includePatterns.filter(p => p !== pattern))
}

const removeExclude = (pattern: string) => {
  emit('update:excludePatterns', props.excludePatterns.filter(p => p !== pattern))
}
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}

.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.section__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.7;
}

.section__toggle input[type="checkbox"] {
  margin: 0;
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.section__toggle-label {
  font-weight: 500;
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

.section__input-wrapper {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.section__input {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--comfy-input-border, #444);
  border-radius: 4px;
  color: var(--fg-color, #fff);
  font-size: 12px;
  outline: none;
}

.section__input:focus {
  border-color: #4299e1;
}

.section__add-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--comfy-input-border, #444);
  border-radius: 4px;
  color: var(--fg-color, #fff);
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.section__add-btn:hover {
  background: var(--comfy-input-bg-hover, #444);
  border-color: #4299e1;
}

.section__patterns {
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
