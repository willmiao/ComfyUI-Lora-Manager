<template>
  <div class="randomizer-settings">
    <div class="settings-header">
      <h3 class="settings-title">RANDOMIZER SETTINGS</h3>
    </div>

    <!-- LoRA Count -->
    <div class="setting-section">
      <label class="setting-label">LoRA Count</label>
      <div class="count-mode-selector">
        <label class="radio-label">
          <input
            type="radio"
            name="count-mode"
            value="fixed"
            :checked="countMode === 'fixed'"
            @change="$emit('update:countMode', 'fixed')"
          />
          <span>Fixed:</span>
          <input
            type="number"
            class="number-input"
            :value="countFixed"
            :disabled="countMode !== 'fixed'"
            min="1"
            max="100"
            @input="$emit('update:countFixed', parseInt(($event.target as HTMLInputElement).value))"
          />
        </label>
      </div>
      <div class="count-mode-selector">
        <label class="radio-label">
          <input
            type="radio"
            name="count-mode"
            value="range"
            :checked="countMode === 'range'"
            @change="$emit('update:countMode', 'range')"
          />
          <span>Range:</span>
          <input
            type="number"
            class="number-input"
            :value="countMin"
            :disabled="countMode !== 'range'"
            min="1"
            max="100"
            @input="$emit('update:countMin', parseInt(($event.target as HTMLInputElement).value))"
          />
          <span>to</span>
          <input
            type="number"
            class="number-input"
            :value="countMax"
            :disabled="countMode !== 'range'"
            min="1"
            max="100"
            @input="$emit('update:countMax', parseInt(($event.target as HTMLInputElement).value))"
          />
        </label>
      </div>
    </div>

    <!-- Model Strength Range -->
    <div class="setting-section">
      <label class="setting-label">Model Strength Range</label>
      <div class="strength-inputs">
        <div class="strength-input-group">
          <label>Min:</label>
          <input
            type="number"
            class="number-input"
            :value="modelStrengthMin"
            min="0"
            max="10"
            step="0.1"
            @input="$emit('update:modelStrengthMin', parseFloat(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="strength-input-group">
          <label>Max:</label>
          <input
            type="number"
            class="number-input"
            :value="modelStrengthMax"
            min="0"
            max="10"
            step="0.1"
            @input="$emit('update:modelStrengthMax', parseFloat(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </div>

    <!-- Clip Strength Range -->
    <div class="setting-section">
      <label class="setting-label">Clip Strength Range</label>
      <div class="checkbox-group">
        <label class="checkbox-label">
          <input
            type="checkbox"
            :checked="useSameClipStrength"
            @change="$emit('update:useSameClipStrength', ($event.target as HTMLInputElement).checked)"
          />
          <span>Same as model</span>
        </label>
      </div>
      <div class="strength-inputs" :class="{ disabled: isClipStrengthDisabled }">
        <div class="strength-input-group">
          <label>Min:</label>
          <input
            type="number"
            class="number-input"
            :value="clipStrengthMin"
            :disabled="isClipStrengthDisabled"
            min="0"
            max="10"
            step="0.1"
            @input="$emit('update:clipStrengthMin', parseFloat(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="strength-input-group">
          <label>Max:</label>
          <input
            type="number"
            class="number-input"
            :value="clipStrengthMax"
            :disabled="isClipStrengthDisabled"
            min="0"
            max="10"
            step="0.1"
            @input="$emit('update:clipStrengthMax', parseFloat(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </div>

    <!-- Roll Mode - New 3-button design -->
    <div class="setting-section">
      <label class="setting-label">Roll Mode</label>
      <div class="roll-buttons-with-tooltip">
        <div class="roll-buttons">
          <button
            class="roll-button"
            :class="{ selected: rollMode === 'fixed' }"
            :disabled="isRolling"
            @click="$emit('generate-fixed')"
          >
            <svg class="roll-button__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="2" width="20" height="20" rx="5"/>
              <circle cx="12" cy="12" r="3"/>
              <circle cx="6" cy="8" r="1.5"/>
              <circle cx="18" cy="16" r="1.5"/>
            </svg>
            <span class="roll-button__text">Generate Fixed</span>
          </button>
          <button
            class="roll-button"
            :class="{ selected: rollMode === 'always' }"
            :disabled="isRolling"
            @click="$emit('always-randomize')"
          >
            <svg class="roll-button__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              <path d="M21 3v5h-5"/>
              <circle cx="12" cy="12" r="3"/>
              <circle cx="6" cy="8" r="1.5"/>
              <circle cx="18" cy="16" r="1.5"/>
            </svg>
            <span class="roll-button__text">Always Randomize</span>
          </button>
          <button
            class="roll-button"
            :class="{ selected: rollMode === 'fixed' && canReuseLast && areLorasEqual(currentLoras, lastUsed) }"
            :disabled="!canReuseLast"
            @mouseenter="showTooltip = true"
            @mouseleave="showTooltip = false"
            @click="$emit('reuse-last')"
          >
            <svg class="roll-button__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 14 4 9l5-5"/>
              <path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5v0a5.5 5.5 0 0 1-5.5 5.5H11"/>
            </svg>
            <span class="roll-button__text">Reuse Last</span>
          </button>
        </div>

        <!-- Last Used Preview Tooltip -->
        <Transition name="tooltip">
          <LastUsedPreview
            v-if="showTooltip && lastUsed && lastUsed.length > 0"
            :loras="lastUsed"
          />
        </Transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import LastUsedPreview from './LastUsedPreview.vue'
import type { LoraEntry } from '../../composables/types'

defineProps<{
  countMode: 'fixed' | 'range'
  countFixed: number
  countMin: number
  countMax: number
  modelStrengthMin: number
  modelStrengthMax: number
  useSameClipStrength: boolean
  clipStrengthMin: number
  clipStrengthMax: number
  rollMode: 'fixed' | 'always'
  isRolling: boolean
  isClipStrengthDisabled: boolean
  lastUsed: LoraEntry[] | null
  currentLoras: LoraEntry[]
  canReuseLast: boolean
}>()

defineEmits<{
  'update:countMode': [value: 'fixed' | 'range']
  'update:countFixed': [value: number]
  'update:countMin': [value: number]
  'update:countMax': [value: number]
  'update:modelStrengthMin': [value: number]
  'update:modelStrengthMax': [value: number]
  'update:useSameClipStrength': [value: boolean]
  'update:clipStrengthMin': [value: number]
  'update:clipStrengthMax': [value: number]
  'update:rollMode': [value: 'fixed' | 'always']
  'generate-fixed': []
  'always-randomize': []
  'reuse-last': []
}>()

const showTooltip = ref(false)

const areLorasEqual = (a: LoraEntry[] | null, b: LoraEntry[] | null): boolean => {
  if (!a || !b) return false
  if (a.length !== b.length) return false
  const sortedA = [...a].sort((x, y) => x.name.localeCompare(y.name))
  const sortedB = [...b].sort((x, y) => x.name.localeCompare(y.name))
  return sortedA.every((lora, i) =>
    lora.name === sortedB[i].name &&
    lora.strength === sortedB[i].strength &&
    lora.clipStrength === sortedB[i].clipStrength
  )
}
</script>

<style scoped>
.randomizer-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #e4e4e7;
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.settings-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: #a1a1aa;
  margin: 0;
  text-transform: uppercase;
}

.setting-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.setting-label {
  font-size: 12px;
  font-weight: 500;
  color: #d4d4d8;
}

.count-mode-selector,
.roll-mode-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: rgba(30, 30, 36, 0.5);
  border-radius: 4px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e4e4e7;
  cursor: pointer;
  flex: 1;
}

.radio-label input[type='radio'] {
  cursor: pointer;
}

.radio-label input[type='radio']:disabled {
  cursor: not-allowed;
}

.number-input {
  width: 60px;
  padding: 4px 8px;
  background: rgba(20, 20, 24, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  color: #e4e4e7;
  font-size: 13px;
}

.number-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.strength-inputs {
  display: flex;
  gap: 12px;
  padding: 6px 8px;
  background: rgba(30, 30, 36, 0.5);
  border-radius: 4px;
}

.strength-inputs.disabled {
  opacity: 0.5;
}

.strength-input-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.strength-input-group label {
  font-size: 12px;
  color: #d4d4d8;
}

.checkbox-group {
  padding: 6px 8px;
  background: rgba(30, 30, 36, 0.5);
  border-radius: 4px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e4e4e7;
  cursor: pointer;
}

.checkbox-label input[type='checkbox'] {
  cursor: pointer;
}

/* Roll buttons with tooltip container */
.roll-buttons-with-tooltip {
  position: relative;
}

/* Roll buttons container */
.roll-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}

.roll-button {
  padding: 8px 10px;
  background: rgba(30, 30, 36, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #e4e4e7;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.roll-button:hover:not(:disabled) {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.4);
  color: #bfdbfe;
}

.roll-button.selected {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
  color: #e4e4e7;
  box-shadow: 0 0 0 1px rgba(66, 153, 225, 0.3);
}

.roll-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.roll-button__icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.roll-button__text {
  font-size: 11px;
  text-align: center;
  line-height: 1.2;
}

/* Tooltip transitions */
.tooltip-enter-active,
.tooltip-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.tooltip-enter-from,
.tooltip-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
