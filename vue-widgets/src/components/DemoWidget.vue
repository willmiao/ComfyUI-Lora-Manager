<template>
  <div class="demo-widget-container">
    <h3 class="demo-title">LoRA Manager Demo Widget</h3>

    <div class="demo-content">
      <div class="input-group">
        <label for="demo-input">Model Name:</label>
        <InputText
          id="demo-input"
          v-model="modelName"
          placeholder="Enter model name..."
          class="demo-input"
        />
      </div>

      <div class="input-group">
        <label for="strength-input">Strength:</label>
        <InputNumber
          id="strength-input"
          v-model="strength"
          :min="0"
          :max="2"
          :step="0.1"
          showButtons
          class="demo-input"
        />
      </div>

      <div class="button-group">
        <Button
          label="Apply"
          icon="pi pi-check"
          @click="handleApply"
          severity="success"
        />
        <Button
          label="Reset"
          icon="pi pi-refresh"
          @click="handleReset"
          severity="secondary"
        />
      </div>

      <Card v-if="appliedValue" class="result-card">
        <template #title>Current Configuration</template>
        <template #content>
          <p><strong>Model:</strong> {{ appliedValue.modelName || 'None' }}</p>
          <p><strong>Strength:</strong> {{ appliedValue.strength }}</p>
        </template>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Card from 'primevue/card'

interface ComponentWidget {
  serializeValue?: (node: unknown, index: number) => Promise<unknown>
  value?: unknown
}

const props = defineProps<{
  widget: ComponentWidget
  node: { id: number }
}>()

const modelName = ref('')
const strength = ref(1.0)
const appliedValue = ref<{ modelName: string; strength: number } | null>(null)

function handleApply() {
  appliedValue.value = {
    modelName: modelName.value,
    strength: strength.value
  }
  console.log('Applied configuration:', appliedValue.value)
}

function handleReset() {
  modelName.value = ''
  strength.value = 1.0
  appliedValue.value = null
  console.log('Reset configuration')
}

onMounted(() => {
  // Serialize the widget value when the workflow is saved or executed
  props.widget.serializeValue = async () => {
    const value = appliedValue.value || { modelName: '', strength: 1.0 }
    console.log('Serializing widget value:', value)
    return value
  }

  // Restore widget value if it exists
  if (props.widget.value) {
    const savedValue = props.widget.value as { modelName: string; strength: number }
    modelName.value = savedValue.modelName || ''
    strength.value = savedValue.strength || 1.0
    appliedValue.value = savedValue
    console.log('Restored widget value:', savedValue)
  }
})
</script>

<style scoped>
.demo-widget-container {
  padding: 12px;
  box-sizing: border-box;
  background: var(--comfy-menu-bg);
  border-radius: 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.demo-title {
  margin: 0 0 12px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--fg-color);
}

.demo-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--fg-color);
}

.demo-input {
  width: 100%;
}

.button-group {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.result-card {
  margin-top: 8px;
  background: var(--comfy-input-bg);
}

.result-card :deep(.p-card-title) {
  font-size: 14px;
  margin-bottom: 8px;
}

.result-card :deep(.p-card-content) {
  padding-top: 0;
}

.result-card p {
  margin: 4px 0;
  font-size: 13px;
  color: var(--fg-color);
}
</style>
