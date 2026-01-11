<template>
  <span class="filter-chip" :class="variantClass">
    <span class="filter-chip__text">{{ label }}</span>
    <span v-if="count !== undefined" class="filter-chip__count">({{ count }})</span>
    <button
      v-if="removable"
      class="filter-chip__remove"
      @click.stop="$emit('remove')"
      type="button"
    >
      &times;
    </button>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  count?: number
  variant?: 'include' | 'exclude' | 'neutral' | 'path'
  removable?: boolean
}>()

defineEmits<{
  remove: []
}>()

const variantClass = computed(() => {
  return props.variant ? `filter-chip--${props.variant}` : ''
})
</script>

<style scoped>
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: var(--comfy-input-bg);
  border: 1px solid var(--border-color);
  color: var(--fg-color);
  white-space: nowrap;
}

.filter-chip__text {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.filter-chip__count {
  opacity: 0.6;
  font-size: 10px;
}

.filter-chip__remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 2px;
  padding: 0;
  background: transparent;
  border: none;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.filter-chip__remove:hover {
  opacity: 1;
}

/* Variants */
.filter-chip--include {
  background: rgba(66, 153, 225, 0.15);
  border-color: rgba(66, 153, 225, 0.4);
  color: #4299e1;
}

.filter-chip--exclude {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.4);
  color: #ef4444;
}

.filter-chip--neutral {
  background: rgba(100, 100, 100, 0.3);
  border-color: rgba(150, 150, 150, 0.4);
  color: var(--fg-color);
}

.filter-chip--path {
  background: rgba(30, 30, 30, 0.8);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--fg-color);
  font-family: monospace;
  font-size: 10px;
}
</style>
