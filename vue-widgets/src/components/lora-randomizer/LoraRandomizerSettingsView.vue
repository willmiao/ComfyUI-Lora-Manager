<template>
  <div class="randomizer-settings">
    <div class="settings-header">
      <h3 class="settings-title">RANDOMIZER SETTINGS</h3>
    </div>

    <!-- LoRA Count -->
    <div class="setting-section">
      <label class="setting-label">LoRA Count</label>
      <div class="count-mode-tabs">
        <label class="count-mode-tab" :class="{ active: countMode === 'fixed' }">
          <input
            type="radio"
            name="count-mode"
            value="fixed"
            :checked="countMode === 'fixed'"
            @change="$emit('update:countMode', 'fixed')"
          />
          <span class="count-mode-tab-label">Fixed</span>
        </label>
        <label class="count-mode-tab" :class="{ active: countMode === 'range' }">
          <input
            type="radio"
            name="count-mode"
            value="range"
            :checked="countMode === 'range'"
            @change="$emit('update:countMode', 'range')"
          />
          <span class="count-mode-tab-label">Range</span>
        </label>
      </div>

      <div class="slider-container">
        <SingleSlider
          v-if="countMode === 'fixed'"
          :min="1"
          :max="10"
          :value="countFixed"
          :step="1"
          :default-range="{ min: 1, max: 5 }"
          @update:value="$emit('update:countFixed', $event)"
        />
        <DualRangeSlider
          v-else
          :min="1"
          :max="10"
          :value-min="countMin"
          :value-max="countMax"
          :step="1"
          :default-range="{ min: 1, max: 5 }"
          @update:value-min="$emit('update:countMin', $event)"
          @update:value-max="$emit('update:countMax', $event)"
        />
      </div>
    </div>

    <!-- Model Strength Range -->
    <div class="setting-section">
      <label class="setting-label">Model Strength Range</label>
      <div class="slider-container">
        <DualRangeSlider
          :min="-10"
          :max="10"
          :value-min="modelStrengthMin"
          :value-max="modelStrengthMax"
          :step="0.1"
          :default-range="{ min: -2, max: 3 }"
          :scale-mode="'segmented'"
          :segments="strengthSegments"
          @update:value-min="$emit('update:modelStrengthMin', $event)"
          @update:value-max="$emit('update:modelStrengthMax', $event)"
        />
      </div>
    </div>

    <!-- Clip Strength Range -->
    <div class="setting-section">
      <div class="section-header-with-toggle">
        <label class="setting-label">
          Clip Strength Range - {{ useSameClipStrength ? 'Use Model Strength' : 'Custom Range' }}
        </label>
        <button
          type="button"
          class="toggle-switch"
          :class="{ 'toggle-switch--active': useSameClipStrength }"
          @click="$emit('update:useSameClipStrength', !useSameClipStrength)"
          role="switch"
          :aria-checked="useSameClipStrength"
          title="Lock clip strength to model strength"
        >
          <span class="toggle-switch__track"></span>
          <span class="toggle-switch__thumb"></span>
        </button>
      </div>
      <div class="slider-container">
        <DualRangeSlider
          :min="-10"
          :max="10"
          :value-min="clipStrengthMin"
          :value-max="clipStrengthMax"
          :step="0.1"
          :default-range="{ min: -1, max: 2 }"
          :scale-mode="'segmented'"
          :segments="strengthSegments"
          :disabled="isClipStrengthDisabled"
          @update:value-min="$emit('update:clipStrengthMin', $event)"
          @update:value-max="$emit('update:clipStrengthMax', $event)"
        />
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
import SingleSlider from '../shared/SingleSlider.vue'
import DualRangeSlider from '../shared/DualRangeSlider.vue'
import type { LoraEntry } from '../../composables/types'

const strengthSegments = [
  { min: -10, max: -2, widthPercent: 20 },
  { min: -2, max: 2, widthPercent: 60, wheelStepMultiplier: 0.5 },
  { min: 2, max: 10, widthPercent: 20 }
]

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
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #e4e4e7;
}

.settings-header {
  margin-bottom: 8px;
}

.settings-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  margin: 0;
  text-transform: uppercase;
}

.setting-section {
  margin-bottom: 16px;
}

.setting-label {
  font-size: 12px;
  font-weight: 500;
  color: #d4d4d8;
  display: block;
  margin-bottom: 8px;
}

.section-header-with-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-header-with-toggle .setting-label {
  margin-bottom: 0;
}

/* Count Mode Tabs */
.count-mode-tabs {
  display: flex;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.count-mode-tab {
  flex: 1;
  position: relative;
  padding: 8px 12px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.count-mode-tab input[type="radio"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.count-mode-tab-label {
  font-size: 12px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.7);
  transition: all 0.2s ease;
}

.count-mode-tab:hover .count-mode-tab-label {
  color: rgba(226, 232, 240, 0.9);
}

.count-mode-tab.active .count-mode-tab-label {
  color: rgba(191, 219, 254, 1);
  font-weight: 600;
}

.count-mode-tab.active {
  background: rgba(66, 153, 225, 0.2);
}

.count-mode-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(66, 153, 225, 0.9);
}

.slider-container {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 4px;
  padding: 4px 8px;
}

/* Toggle Switch (same style as LicenseSection) */
.toggle-switch {
  position: relative;
  width: 36px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}

.toggle-switch__track {
  position: absolute;
  inset: 0;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 10px;
  transition: all 0.2s;
}

.toggle-switch--active .toggle-switch__track {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
}

.toggle-switch__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  transition: all 0.2s;
  opacity: 0.6;
}

.toggle-switch--active .toggle-switch__thumb {
  transform: translateX(16px);
  background: #4299e1;
  opacity: 1;
}

.toggle-switch:hover .toggle-switch__thumb {
  opacity: 1;
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
