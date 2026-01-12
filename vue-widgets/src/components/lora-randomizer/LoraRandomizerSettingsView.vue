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

    <!-- Roll Mode -->
    <div class="setting-section">
      <label class="setting-label">Roll Mode</label>
      <div class="roll-mode-selector">
        <label class="radio-label">
          <input
            type="radio"
            name="roll-mode"
            value="frontend"
            :checked="rollMode === 'frontend'"
            @change="$emit('update:rollMode', 'frontend')"
          />
          <span>Frontend Roll (fixed until re-rolled)</span>
        </label>
        <button
          class="roll-button"
          :disabled="rollMode !== 'frontend' || isRolling"
          @click="$emit('roll')"
        >
          <span class="roll-button__content">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"></rect><path d="M8 8h.01"></path><path d="M16 16h.01"></path><path d="M16 8h.01"></path><path d="M8 16h.01"></path></svg>
            Roll
          </span>
        </button>
      </div>
      <div class="roll-mode-selector">
        <label class="radio-label">
          <input
            type="radio"
            name="roll-mode"
            value="backend"
            :checked="rollMode === 'backend'"
            @change="$emit('update:rollMode', 'backend')"
          />
          <span>Backend Roll (randomizes each execution)</span>
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
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
  rollMode: 'frontend' | 'backend'
  isRolling: boolean
  isClipStrengthDisabled: boolean
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
  'update:rollMode': [value: 'frontend' | 'backend']
  roll: []
}>()
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

.roll-button {
  padding: 8px 16px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border: none;
  border-radius: 4px;
  color: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  display: flex;
  align-items: center;
  justify-content: center;
}

.roll-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.roll-button:active:not(:disabled) {
  transform: translateY(0);
}

.roll-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: linear-gradient(135deg, #52525b 0%, #3f3f46 100%);
}

.roll-button__content {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
