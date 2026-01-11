<template>
  <div class="section">
    <div class="section__header">
      <span class="section__title">TAGS</span>
    </div>
    <div class="section__columns">
      <!-- Include column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--include">INCLUDE</span>
          <EditButton @click="$emit('edit-include')" />
        </div>
        <div class="section__column-content">
          <div v-if="includeTags.length === 0" class="section__empty">
            None
          </div>
          <div v-else class="section__chips">
            <FilterChip
              v-for="tag in includeTags"
              :key="tag"
              :label="tag"
              variant="include"
            />
          </div>
        </div>
      </div>

      <!-- Exclude column -->
      <div class="section__column">
        <div class="section__column-header">
          <span class="section__column-title section__column-title--exclude">EXCLUDE</span>
          <EditButton @click="$emit('edit-exclude')" />
        </div>
        <div class="section__column-content">
          <div v-if="excludeTags.length === 0" class="section__empty">
            None
          </div>
          <div v-else class="section__chips">
            <FilterChip
              v-for="tag in excludeTags"
              :key="tag"
              :label="tag"
              variant="exclude"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import FilterChip from '../shared/FilterChip.vue'
import EditButton from '../shared/EditButton.vue'

defineProps<{
  includeTags: string[]
  excludeTags: string[]
}>()

defineEmits<{
  'edit-include': []
  'edit-exclude': []
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

.section__column-content {
  min-height: 28px;
}

.section__empty {
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
  gap: 4px;
}
</style>
