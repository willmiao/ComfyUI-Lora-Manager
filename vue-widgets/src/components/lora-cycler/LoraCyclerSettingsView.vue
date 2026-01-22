<template>
  <div class="cycler-settings">
    <div class="settings-header">
      <h3 class="settings-title">CYCLER SETTINGS</h3>
    </div>

    <!-- Progress Display -->
    <div class="setting-section progress-section">
      <div class="progress-display">
        <div class="progress-info">
          <span class="progress-label">Next LoRA:</span>
          <span class="progress-name" :title="currentLoraFilename">{{ currentLoraName || 'None' }}</span>
        </div>
        <div class="progress-counter">
          <span class="progress-index">{{ currentIndex }}</span>
          <span class="progress-separator">/</span>
          <span class="progress-total">{{ totalCount }}</span>
          <button
            class="refresh-button"
            :disabled="isLoading"
            @click="$emit('refresh')"
            title="Refresh list"
          >
            <svg
              class="refresh-icon"
              :class="{ spinning: isLoading }"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              <path d="M21 3v5h-5"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Starting Index -->
    <div class="setting-section">
      <label class="setting-label">Starting Index</label>
      <div class="index-input-container">
        <input
          type="number"
          class="index-input"
          :min="1"
          :max="totalCount || 1"
          :value="currentIndex"
          :disabled="totalCount === 0"
          @input="onIndexInput"
          @blur="onIndexBlur"
        />
        <span class="index-hint">1 - {{ totalCount || 1 }}</span>
      </div>
    </div>

    <!-- Model Strength -->
    <div class="setting-section">
      <label class="setting-label">Model Strength</label>
      <div class="slider-container">
        <SingleSlider
          :min="-10"
          :max="10"
          :value="modelStrength"
          :step="0.1"
          :default-range="{ min: 0.5, max: 1.5 }"
          @update:value="$emit('update:modelStrength', $event)"
        />
      </div>
    </div>

    <!-- Clip Strength -->
    <div class="setting-section">
      <div class="section-header-with-toggle">
        <label class="setting-label">
          Clip Strength - {{ useCustomClipRange ? 'Custom Value' : 'Use Model Strength' }}
        </label>
        <button
          type="button"
          class="toggle-switch"
          :class="{ 'toggle-switch--active': useCustomClipRange }"
          @click="$emit('update:useCustomClipRange', !useCustomClipRange)"
          role="switch"
          :aria-checked="useCustomClipRange"
          title="Use custom clip strength when enabled, otherwise use model strength"
        >
          <span class="toggle-switch__track"></span>
          <span class="toggle-switch__thumb"></span>
        </button>
      </div>
      <div class="slider-container" :class="{ 'slider-container--disabled': isClipStrengthDisabled }">
        <SingleSlider
          :min="-10"
          :max="10"
          :value="clipStrength"
          :step="0.1"
          :default-range="{ min: 0.5, max: 1.5 }"
          :disabled="isClipStrengthDisabled"
          @update:value="$emit('update:clipStrength', $event)"
        />
      </div>
    </div>

    <!-- Sort By -->
    <div class="setting-section">
      <label class="setting-label">Sort By</label>
      <div class="sort-tabs">
        <label class="sort-tab" :class="{ active: sortBy === 'filename' }">
          <input
            type="radio"
            name="sort-by"
            value="filename"
            :checked="sortBy === 'filename'"
            @change="$emit('update:sortBy', 'filename')"
          />
          <span class="sort-tab-label">Filename</span>
        </label>
        <label class="sort-tab" :class="{ active: sortBy === 'model_name' }">
          <input
            type="radio"
            name="sort-by"
            value="model_name"
            :checked="sortBy === 'model_name'"
            @change="$emit('update:sortBy', 'model_name')"
          />
          <span class="sort-tab-label">Model Name</span>
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SingleSlider from '../shared/SingleSlider.vue'

const props = defineProps<{
  currentIndex: number
  totalCount: number
  currentLoraName: string
  currentLoraFilename: string
  modelStrength: number
  clipStrength: number
  useCustomClipRange: boolean
  isClipStrengthDisabled: boolean
  sortBy: 'filename' | 'model_name'
  isLoading: boolean
}>()

const emit = defineEmits<{
  'update:currentIndex': [value: number]
  'update:modelStrength': [value: number]
  'update:clipStrength': [value: number]
  'update:useCustomClipRange': [value: boolean]
  'update:sortBy': [value: 'filename' | 'model_name']
  'refresh': []
}>()

// Temporary value for input while typing
const tempIndex = ref<string>('')

const onIndexInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  tempIndex.value = input.value
}

const onIndexBlur = (event: Event) => {
  const input = event.target as HTMLInputElement
  const value = parseInt(input.value, 10)

  if (!isNaN(value)) {
    const clampedValue = Math.max(1, Math.min(value, props.totalCount || 1))
    emit('update:currentIndex', clampedValue)
    input.value = clampedValue.toString()
  } else {
    input.value = props.currentIndex.toString()
  }
  tempIndex.value = ''
}
</script>

<style scoped>
.cycler-settings {
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
  margin-bottom: 8px;
}

.setting-label {
  font-size: 13px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.8);
  display: block;
  margin-bottom: 6px;
}

/* Progress Display */
.progress-section {
  margin-bottom: 12px;
}

.progress-display {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.progress-label {
  font-size: 10px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.progress-name {
  font-size: 13px;
  font-weight: 500;
  color: rgba(191, 219, 254, 1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-counter {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-left: 12px;
  flex-shrink: 0;
}

.progress-index {
  font-size: 18px;
  font-weight: 600;
  color: rgba(66, 153, 225, 1);
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}

.progress-separator {
  font-size: 14px;
  color: rgba(226, 232, 240, 0.4);
  margin: 0 2px;
}

.progress-total {
  font-size: 14px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.6);
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}

.refresh-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-left: 8px;
  padding: 0;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: rgba(226, 232, 240, 0.6);
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-button:hover:not(:disabled) {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.4);
  color: rgba(191, 219, 254, 1);
}

.refresh-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Index Input */
.index-input-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.index-input {
  width: 80px;
  padding: 6px 10px;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  color: #e4e4e7;
  font-size: 13px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}

.index-input:focus {
  outline: none;
  border-color: rgba(66, 153, 225, 0.6);
}

.index-input:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.index-hint {
  font-size: 11px;
  color: rgba(226, 232, 240, 0.4);
}

/* Slider Container */
.slider-container {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  padding: 6px;
}

.slider-container--disabled {
  opacity: 0.5;
  pointer-events: none;
}

.section-header-with-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-header-with-toggle .setting-label {
  margin-bottom: 4px;
}

/* Toggle Switch */
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
  top: 3px;
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

/* Sort Tabs */
.sort-tabs {
  display: flex;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  overflow: hidden;
}

.sort-tab {
  flex: 1;
  position: relative;
  padding: 8px 12px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sort-tab input[type="radio"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.sort-tab-label {
  font-size: 13px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.7);
  transition: all 0.2s ease;
}

.sort-tab:hover .sort-tab-label {
  color: rgba(226, 232, 240, 0.9);
}

.sort-tab.active .sort-tab-label {
  color: rgba(191, 219, 254, 1);
  font-weight: 600;
}

.sort-tab.active {
  background: rgba(66, 153, 225, 0.2);
}

.sort-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(66, 153, 225, 0.9);
}
</style>
