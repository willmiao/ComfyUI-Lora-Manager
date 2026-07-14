<template>
  <div class="lora-info-widget">
    <template v-if="loraName">
      <div class="info-field">
        <label class="info-label">Filename</label>
        <div class="lora-filename">{{ loraName }}</div>
      </div>
      <div class="info-field notes-field">
        <label class="info-label">Notes</label>
        <textarea
          v-model="notes"
          class="lora-notes"
          placeholder="Add notes about this LoRA..."
          :disabled="saving"
        ></textarea>
      </div>
      <button
        class="save-btn"
        :disabled="notes === originalNotes || saving"
        @click="saveNotes"
      >
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
    </template>
    <div v-else class="placeholder">No LoRA selected</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

interface LoraInfoWidget {
  serializeValue?: () => Promise<unknown>
  value?: unknown
  onSetValue?: (v: unknown) => void
  callback?: unknown
  _setLoraInfo?: (data: { name: string; notes: string; filePath: string }) => void
}

const props = defineProps<{
  widget: LoraInfoWidget
  node: { id: number }
  api: { fetchApi: (url: string, options?: RequestInit) => Promise<Response> }
  app: { extensionManager: { toast: { add: (opts: Record<string, unknown>) => void } } }
}>()

const loraName = ref<string>('')
const notes = ref<string>('')
const originalNotes = ref<string>('')
const filePath = ref<string>('')
const saving = ref<boolean>(false)

async function saveNotes() {
  if (notes.value === originalNotes.value || saving.value) return
  if (!filePath.value) return

  saving.value = true
  try {
    const response = await props.api.fetchApi('/lm/loras/save-metadata', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath.value, notes: notes.value })
    })
    const result = await response.json()
    if (result.success) {
      props.app.extensionManager.toast.add({
        severity: 'success',
        summary: 'Saved',
        detail: 'Notes updated successfully',
        life: 2000
      })
      originalNotes.value = notes.value
    } else {
      props.app.extensionManager.toast.add({
        severity: 'error',
        summary: 'Error',
        detail: result.message || result.error || 'Failed to save notes',
        life: 3000
      })
    }
  } catch (e) {
    console.error('[LoraInfoWidget] Failed to save notes:', e)
    props.app.extensionManager.toast.add({
      severity: 'error',
      summary: 'Error',
      detail: (e as Error).message || 'Failed to save notes',
      life: 3000
    })
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  // Display-only widget - return null on serialization to avoid saving to workflow
  props.widget.serializeValue = async () => null

  // Handle external value updates (e.g., loading workflow, paste)
  props.widget.onSetValue = (v: unknown) => {
    if (v && typeof v === 'object') {
      const data = v as { name?: string; notes?: string; filePath?: string }
      if (data.name !== undefined) loraName.value = data.name
      if (data.notes !== undefined) {
        notes.value = data.notes
        originalNotes.value = data.notes
      }
      if (data.filePath !== undefined) filePath.value = data.filePath
    }
  }

  // Restore from saved value if exists (for workflow loading)
  if (props.widget.value && typeof props.widget.value === 'object') {
    const data = props.widget.value as { name?: string; notes?: string; filePath?: string }
    if (data.name !== undefined) loraName.value = data.name
    if (data.notes !== undefined) {
      notes.value = data.notes
      originalNotes.value = data.notes
    }
    if (data.filePath !== undefined) filePath.value = data.filePath
  }

  // Expose setLoraInfo on the widget object for external callers (e.g., lora_info.js).
  // Accepts null to clear the display (when selection is deselected).
  props.widget._setLoraInfo = (data: { name: string; notes: string; filePath: string } | null) => {
    if (data) {
      loraName.value = data.name
      notes.value = data.notes
      originalNotes.value = data.notes
      filePath.value = data.filePath
    } else {
      loraName.value = ''
      notes.value = ''
      originalNotes.value = ''
      filePath.value = ''
    }
  }

  // Consume any data pushed before the Vue component mounted (race condition fix)
  if (props.widget.__pendingLoraInfo) {
    props.widget._setLoraInfo(props.widget.__pendingLoraInfo)
    delete props.widget.__pendingLoraInfo
  }
})
</script>

<style scoped>
.lora-info-widget {
  padding: 12px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
}

.info-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}

.lora-filename {
  font-size: 13px;
  font-weight: 500;
  color: var(--fg-color, #fff);
  word-break: break-all;
  margin-bottom: 8px;
}

.notes-field {
  flex: 1;
  min-height: 0;
}

.lora-notes {
  width: 100%;
  flex: 1;
  min-height: 60px;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color, #444);
  background: var(--comfy-input-bg, #333);
  color: var(--fg-color, #fff);
  font-size: 12px;
  resize: none;
  box-sizing: border-box;
  font-family: inherit;
  outline: none;
}

.lora-notes:focus {
  border-color: var(--comfy-input-border, #444);
}

.lora-notes:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-btn {
  width: 100%;
  margin-top: 8px;
  padding: 6px 12px;
  border-radius: 4px;
  border: 1px solid rgba(66, 153, 225, 0.4);
  background: rgba(66, 153, 225, 0.15);
  color: var(--fg-color, #fff);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  box-sizing: border-box;
  flex-shrink: 0;
}

.save-btn:hover:not(:disabled) {
  background: rgba(66, 153, 225, 0.25);
  border-color: rgba(66, 153, 225, 0.6);
}

.save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  background: rgba(66, 153, 225, 0.05);
  border-color: rgba(226, 232, 240, 0.1);
}

.placeholder {
  font-style: italic;
  color: rgba(226, 232, 240, 0.5);
  text-align: center;
  padding: 16px 0;
  font-size: 12px;
}
</style>