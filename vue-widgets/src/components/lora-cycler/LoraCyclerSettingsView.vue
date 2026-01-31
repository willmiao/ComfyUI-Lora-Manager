<template>
  <div class="cycler-settings">
    <div class="settings-header">
      <h3 class="settings-title">CYCLER SETTINGS</h3>
    </div>

    <!-- Progress Display -->
    <div class="setting-section progress-section">
      <div class="progress-display" :class="{ executing: isWorkflowExecuting }">
        <div class="progress-info">
          <span class="progress-label">{{ isWorkflowExecuting ? 'Using LoRA:' : 'Next LoRA:' }}</span>
          <span class="progress-name" :title="currentLoraFilename">{{ currentLoraName || 'None' }}</span>
        </div>
        <div class="progress-counter">
          <span class="progress-index">{{ currentIndex }}</span>
          <span class="progress-separator">/</span>
          <span class="progress-total">{{ totalCount }}</span>

          <!-- Repeat indicator (only shown when repeatCount > 1) -->
          <div v-if="repeatCount > 1" class="repeat-badge">
            <span class="repeat-badge-label">Rep</span>
            <span class="repeat-badge-value">{{ repeatUsed }}/{{ repeatCount }}</span>
          </div>

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

    <!-- Starting Index with Advanced Controls -->
    <div class="setting-section">
      <label class="setting-label">Starting Index</label>
      <div class="index-controls-row">
        <!-- Index input -->
        <input
          type="number"
          class="index-input"
          :min="1"
          :max="totalCount || 1"
          :value="currentIndex"
          :disabled="totalCount === 0"
          @input="onIndexInput"
          @blur="onIndexBlur"
          @pointerdown.stop
          @pointermove.stop
          @pointerup.stop
        />
        <span class="index-hint">1 - {{ totalCount || 1 }}</span>

        <!-- Repeat control -->
        <span class="repeat-label">x</span>
        <input
          type="number"
          class="repeat-input"
          min="1"
          max="99"
          :value="repeatCount"
          @input="onRepeatInput"
          @blur="onRepeatBlur"
          @pointerdown.stop
          @pointermove.stop
          @pointerup.stop
          title="Repeat each LoRA this many times"
        />
        <span class="repeat-hint">times</span>

        <!-- Control buttons -->
        <button
          class="control-btn"
          :class="{ active: isPaused }"
          @click="$emit('toggle-pause')"
          :title="isPaused ? 'Continue iteration' : 'Pause iteration'"
        >
          <svg v-if="isPaused" viewBox="0 0 24 24" fill="currentColor" class="control-icon">
            <path d="M8 5v14l11-7z"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="currentColor" class="control-icon">
            <path d="M6 4h4v16H6zm8 0h4v16h-4z"/>
          </svg>
        </button>
        <button
          class="control-btn"
          @click="$emit('reset-index')"
          title="Reset to index 1"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" class="control-icon">
            <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
          </svg>
        </button>
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
  isLoading: boolean
  repeatCount: number
  repeatUsed: number
  isPaused: boolean
  isWorkflowExecuting: boolean
  executingRepeatStep: number
}>()

const emit = defineEmits<{
  'update:currentIndex': [value: number]
  'update:modelStrength': [value: number]
  'update:clipStrength': [value: number]
  'update:useCustomClipRange': [value: boolean]
  'update:repeatCount': [value: number]
  'toggle-pause': []
  'reset-index': []
  'refresh': []
}>()

// Temporary value for input while typing
const tempIndex = ref<string>('')
const tempRepeat = ref<string>('')

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

const onRepeatInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  tempRepeat.value = input.value
}

const onRepeatBlur = (event: Event) => {
  const input = event.target as HTMLInputElement
  const value = parseInt(input.value, 10)

  if (!isNaN(value)) {
    const clampedValue = Math.max(1, Math.min(value, 99))
    emit('update:repeatCount', clampedValue)
    input.value = clampedValue.toString()
  } else {
    input.value = props.repeatCount.toString()
  }
  tempRepeat.value = ''
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
  transition: border-color 0.3s ease;
}

.progress-display.executing {
  border-color: rgba(66, 153, 225, 0.5);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { border-color: rgba(66, 153, 225, 0.3); }
  50% { border-color: rgba(66, 153, 225, 0.7); }
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
  min-width: 4ch;
  text-align: right;
  font-variant-numeric: tabular-nums;
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
  min-width: 4ch;
  text-align: left;
  font-variant-numeric: tabular-nums;
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

/* Repeat Badge */
.repeat-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  padding: 2px 6px;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 4px;
}

.repeat-badge-label {
  font-size: 10px;
  color: rgba(253, 230, 138, 0.7);
  text-transform: uppercase;
}

.repeat-badge-value {
  font-size: 12px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  color: rgba(253, 230, 138, 1);
  min-width: 3ch;
  font-variant-numeric: tabular-nums;
}

/* Index Controls Row */
.index-controls-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.index-input {
  width: 60px;
  padding: 6px 8px;
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
  min-width: 7ch;
  font-variant-numeric: tabular-nums;
}

/* Repeat Controls */
.repeat-label {
  font-size: 13px;
  color: rgba(226, 232, 240, 0.6);
  margin-left: 4px;
}

.repeat-input {
  width: 44px;
  padding: 6px 6px;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  color: #e4e4e7;
  font-size: 13px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  text-align: center;
}

.repeat-input:focus {
  outline: none;
  border-color: rgba(66, 153, 225, 0.6);
}

.repeat-hint {
  font-size: 11px;
  color: rgba(226, 232, 240, 0.4);
}

/* Control Buttons */
.control-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: rgba(226, 232, 240, 0.6);
  cursor: pointer;
  transition: all 0.2s;
}

.control-btn:hover {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.4);
  color: rgba(191, 219, 254, 1);
}

.control-btn.active {
  background: rgba(245, 158, 11, 0.2);
  border-color: rgba(245, 158, 11, 0.5);
  color: rgba(253, 230, 138, 1);
}

.control-btn.active:hover {
  background: rgba(245, 158, 11, 0.3);
  border-color: rgba(245, 158, 11, 0.6);
}

.control-icon {
  width: 14px;
  height: 14px;
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
</style>
