<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">LICENSE</span>
    </div>
    <div class="section__toggles">
      <label class="toggle-item">
        <span class="toggle-item__label">No Credit Required</span>
        <button
          type="button"
          class="toggle-switch"
          :class="{ 'toggle-switch--active': noCreditRequired }"
          @click="$emit('update:noCreditRequired', !noCreditRequired)"
          role="switch"
          :aria-checked="noCreditRequired"
        >
          <span class="toggle-switch__track"></span>
          <span class="toggle-switch__thumb"></span>
        </button>
      </label>

      <label class="toggle-item">
        <span class="toggle-item__label">Allow Selling</span>
        <button
          type="button"
          class="toggle-switch"
          :class="{ 'toggle-switch--active': allowSelling }"
          @click="$emit('update:allowSelling', !allowSelling)"
          role="switch"
          :aria-checked="allowSelling"
        >
          <span class="toggle-switch__track"></span>
          <span class="toggle-switch__thumb"></span>
        </button>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  noCreditRequired: boolean
  allowSelling: boolean
}>()

defineEmits<{
  'update:noCreditRequired': [value: boolean]
  'update:allowSelling': [value: boolean]
}>()
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

.section__toggles {
  display: flex;
  gap: 16px;
}

.toggle-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.toggle-item__label {
  font-size: 12px;
  color: var(--fg-color, #fff);
}

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
