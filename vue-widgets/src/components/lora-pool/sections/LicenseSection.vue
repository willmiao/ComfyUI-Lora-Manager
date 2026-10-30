<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">LICENSE</span>
    </div>
    <div class="section__toggles">
      <label class="toggle-item">
        <span class="toggle-item__label" title="Use the model without crediting the creator">No Credit Required</span>
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
        <span class="toggle-item__label" title="Allow selling generated images">Allow Selling</span>
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
  color: var(--lm-fg);
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
  color: var(--lm-fg);
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
  background: var(--lm-surface);
  border: 1px solid var(--lm-border);
  border-radius: 10px;
  transition: all 0.2s;
}

.toggle-switch--active .toggle-switch__track {
  background: var(--lm-accent-soft);
  border-color: var(--lm-accent-border);
}

.toggle-switch__thumb {
  position: absolute;
  top: 3px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--lm-fg);
  border-radius: 50%;
  transition: all 0.2s;
  opacity: 0.6;
}

.toggle-switch--active .toggle-switch__thumb {
  transform: translateX(16px);
  background: var(--lm-accent);
  opacity: 1;
}

.toggle-switch:hover .toggle-switch__thumb {
  opacity: 1;
}
</style>
