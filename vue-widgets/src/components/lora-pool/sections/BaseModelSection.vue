<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">BASE MODEL</span>
      <EditButton @click="$emit('edit')" />
    </div>
    <div class="section__content">
      <div v-if="selected.length === 0" class="section__placeholder">
        All models
      </div>
      <div v-else class="section__chips">
        <FilterChip
          v-for="name in selected"
          :key="name"
          :label="name"
          :count="getCount(name)"
          variant="neutral"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import FilterChip from '../shared/FilterChip.vue'
import EditButton from '../shared/EditButton.vue'
import type { BaseModelOption } from '../../../composables/types'

const props = defineProps<{
  selected: string[]
  models: BaseModelOption[]
}>()

defineEmits<{
  edit: []
}>()

const getCount = (name: string) => {
  const model = props.models.find(m => m.name === name)
  return model?.count
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

.section__content {
  min-height: 32px;
  display: flex;
  align-items: center;
}

.section__placeholder {
  width: 100%;
  padding: 8px 12px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  box-sizing: border-box;
}

.section__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
