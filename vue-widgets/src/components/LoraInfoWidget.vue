<template>
  <div class="lora-info-widget" :class="{ 'lm-vue-node': isVueMode }" @wheel="onWheel">
    <template v-if="loraName">
      <!-- Tab bar -->
      <div class="lora-info-tabs">
        <label
          class="lora-info-tab"
          :class="{ active: activeTab === 'notes' }"
        >
          <input
            type="radio"
            v-model="activeTab"
            value="notes"
            class="lora-info-tab-input"
          />
          <span class="lora-info-tab-label">Notes</span>
        </label>
        <label
          class="lora-info-tab"
          :class="{ active: activeTab === 'description' }"
        >
          <input
            type="radio"
            v-model="activeTab"
            value="description"
            class="lora-info-tab-input"
            @change="onDescriptionTabActivated"
          />
          <span class="lora-info-tab-label">Description</span>
        </label>
      </div>

      <!-- Notes tab content -->
      <div v-show="activeTab === 'notes'" class="tab-content notes-tab">
        <div class="info-field">
          <label class="info-label">Filename</label>
          <div class="lora-filename">{{ loraName }}</div>
        </div>
        <div class="info-field notes-field">
          <label class="info-label">Notes</label>
          <textarea
            v-model="notes"
            class="lora-notes lm-wheel-scrollable"
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
      </div>

      <!-- Description tab content -->
      <div v-show="activeTab === 'description'" class="tab-content description-tab lm-wheel-scrollable">
        <!-- Loading state -->
        <div v-if="descriptionLoading" class="description-state">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading description...</span>
        </div>

        <!-- Error state -->
        <div v-else-if="descriptionError" class="description-state error">
          <span>Failed to load description</span>
        </div>

        <!-- Empty state (loaded but no content) -->
        <div v-else-if="!hasDescription" class="description-state placeholder">
          <span>No description available</span>
        </div>

        <!-- Description content -->
        <div v-else class="description-content">
          <div v-if="versionDescription" class="description-section">
            <label class="info-label">About this version</label>
            <div class="description-text" v-html="versionDescription"></div>
          </div>
          <div v-if="modelDescription" class="description-section">
            <label class="info-label">Model Description</label>
            <div class="description-text" v-html="modelDescription"></div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="placeholder">No LoRA selected</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'

interface LoraInfoWidget {
  serializeValue?: () => Promise<unknown>
  value?: unknown
  onSetValue?: (v: unknown) => void
  callback?: unknown
  options?: {
    getValue?: () => LoraInfoWidgetValue
    setValue?: (v: unknown) => void
  }
  node?: { widgets?: Array<{ id?: string }>; widgets_values?: Array<unknown> }
  id?: string
  _setLoraInfo?: (data: { name: string; notes: string; filePath: string; activeTab?: string } | null) => void
  __pendingLoraInfo?: { name: string; notes: string; filePath: string; activeTab?: string } | null
}

interface LoraInfoWidgetValue {
  name?: string
  notes?: string
  filePath?: string
  activeTab?: string
}

const props = defineProps<{
  widget: LoraInfoWidget
  node: { id: number }
  api: { fetchApi: (url: string, options?: RequestInit) => Promise<Response> }
  app: { extensionManager: { toast: { add: (opts: Record<string, unknown>) => void } } }
  isVueMode?: boolean
}>()

const loraName = ref<string>('')
const notes = ref<string>('')
const originalNotes = ref<string>('')
const filePath = ref<string>('')
const saving = ref<boolean>(false)
const activeTab = ref<string>('notes')

// Description tab state
const versionDescription = ref<string>('')
const modelDescription = ref<string>('')
const descriptionLoading = ref<boolean>(false)
const descriptionError = ref<boolean>(false)
const descriptionLoaded = ref<boolean>(false)

const hasDescription = computed(() =>
  !!(versionDescription.value || modelDescription.value)
)

// Reset and auto-fetch description state when the LoRA selection changes
watch(filePath, (newPath) => {
  descriptionLoaded.value = false
  descriptionError.value = false
  versionDescription.value = ''
  modelDescription.value = ''
  if (newPath && activeTab.value === 'description') {
    fetchDescription()
  }
})

function onDescriptionTabActivated() {
  if (!descriptionLoaded.value && filePath.value) {
    fetchDescription()
  }
}

async function fetchDescription() {
  if (descriptionLoading.value || !filePath.value) return

  descriptionLoading.value = true
  descriptionError.value = false

  try {
    const response = await props.api.fetchApi(
      `/lm/loras/metadata?file_path=${encodeURIComponent(filePath.value)}`,
      { method: 'GET' }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch metadata: ${response.statusText}`)
    }

    const data = await response.json()
    if (data.success && data.metadata) {
      versionDescription.value = data.metadata.description || ''
      modelDescription.value = data.metadata.model?.description || ''
      descriptionLoaded.value = true
    } else {
      // Successful response but no metadata — treat as empty, not error
      descriptionLoaded.value = true
    }
  } catch (e) {
    console.error('[LoraInfoWidget] Failed to fetch description:', e)
    descriptionError.value = true
    // Don't set descriptionLoaded — allow retry on next tab switch
  } finally {
    descriptionLoading.value = false
  }
}

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

function onWheel(event: WheelEvent) {
  const target = event.target as HTMLElement | null
  if (!target) return

  const comfyApp = (window as unknown as { app?: { canvas?: { processMouseWheel?: (e: WheelEvent) => void } } }).app
  if (!comfyApp?.canvas?.processMouseWheel) return

  // Always pass pinch-to-zoom to canvas
  if (event.ctrlKey) {
    event.preventDefault()
    event.stopPropagation()
    comfyApp.canvas.processMouseWheel(event)
    return
  }

  // Horizontal scroll: pass to canvas
  if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
    event.preventDefault()
    event.stopPropagation()
    comfyApp.canvas.processMouseWheel(event)
    return
  }

  // Check if the target is inside a scrollable area (notes textarea or description tab)
  const scrollableEl = target.closest('.lora-notes, .description-tab') as HTMLElement | null
  if (scrollableEl) {
    const canScrollY = scrollableEl.scrollHeight > scrollableEl.clientHeight
    if (canScrollY) {
      // Let native scroll handle it, but stop propagation to prevent canvas zoom
      event.stopPropagation()
      return
    }
  }

  // Forward to canvas for zoom
  event.preventDefault()
  event.stopPropagation()
  comfyApp.canvas.processMouseWheel(event)
}

onMounted(() => {
  // Build current state snapshot for serialization
  const buildValue = (): LoraInfoWidgetValue => ({
    name: loraName.value,
    notes: notes.value,
    filePath: filePath.value,
    activeTab: activeTab.value,
  })

  // Set value from external source (workflow load, paste, etc.)
  const applyValue = (v: unknown) => {
    if (v && typeof v === 'object') {
      const data = v as LoraInfoWidgetValue
      // Set activeTab before filePath so the filePath watcher sees the correct tab
      // and triggers fetchDescription() when restoring description tab
      if (data.activeTab !== undefined) activeTab.value = data.activeTab
      if (data.name !== undefined) loraName.value = data.name
      if (data.notes !== undefined) {
        notes.value = data.notes
        originalNotes.value = data.notes
      }
      if (data.filePath !== undefined) filePath.value = data.filePath
    }
  }

  // ComponentWidgetImpl.value getter/setter delegates to options.getValue/options.setValue.
  // These must be set for workflow JSON persistence (LGraphNode.serialize/configure) to work.
  props.widget.options.getValue = buildValue
  props.widget.options.setValue = applyValue

  // Also set serializeValue for prompt/API serialization path (executionUtil.ts)
  props.widget.serializeValue = async () => buildValue()

  // Handle external value updates (e.g., loading workflow, paste)
  props.widget.onSetValue = applyValue

  // Restore from saved value. Because configure() may call widget.value = data
  // before onMounted fires (and before options.setValue is assigned), we check
  // widgets_values directly in case the value was already pushed.
  const widgetIndex = props.widget.node?.widgets?.findIndex(
    (w: { id?: string }) => w.id === props.widget.id
  )
  let restored = false
  if (widgetIndex !== undefined && widgetIndex >= 0) {
    const savedValue = props.widget.node?.widgets_values?.[widgetIndex]
    if (savedValue && typeof savedValue === 'object') {
      applyValue(savedValue)
      restored = true
    }
  }
  // Fallback: if configure() ran after onMounted, widget.value (via options.getValue)
  // already has the saved data. Only use this path if the widgets_values lookup didn't restore.
  if (!restored && props.widget.value && typeof props.widget.value === 'object') {
    applyValue(props.widget.value)
  }

  // Expose setLoraInfo on the widget object for external callers (e.g., lora_info.js).
  // Accepts null to clear the display (when selection is deselected).
  props.widget._setLoraInfo = (data: { name: string; notes: string; filePath: string; activeTab?: string } | null) => {
    if (data) {
      loraName.value = data.name
      notes.value = data.notes
      originalNotes.value = data.notes
      filePath.value = data.filePath
      // Preserve existing activeTab unless explicitly provided
      if (data.activeTab !== undefined) {
        activeTab.value = data.activeTab
      }
    } else {
      loraName.value = ''
      notes.value = ''
      originalNotes.value = ''
      filePath.value = ''
      // Do NOT reset activeTab on deselection — user's tab preference persists
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

/* Vue node mode: prevent content from pushing node size via ResizeObserver.
   contain:layout size tells the browser the element's intrinsic size is
   determined solely by CSS — not by descendant content. This breaks the
   feedback loop where content grows → ResizeObserver resizes → content
   reflows → repeat. Same technique used by tags_widget.js + lm_styles.css. */
.lora-info-widget.lm-vue-node {
  contain: layout size;
}

/* ── Tab bar ── */
.lora-info-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-color, #444);
  flex-shrink: 0;
}

.lora-info-tab {
  flex: 1;
  text-align: center;
  cursor: pointer;
  padding: 6px 0;
  position: relative;
}

.lora-info-tab-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.lora-info-tab-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  transition: opacity 0.15s;
}

.lora-info-tab:hover .lora-info-tab-label {
  opacity: 0.75;
}

.lora-info-tab.active .lora-info-tab-label {
  opacity: 1;
}

.lora-info-tab.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 25%;
  right: 25%;
  height: 2px;
  background: rgba(66, 153, 225, 0.8);
  border-radius: 1px;
}

/* ── Tab content ── */
.tab-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.notes-tab {
  display: flex;
  flex-direction: column;
}

.description-tab {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-height: 0;
}

/* ── Info fields (shared) ── */
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

/* ── Description states ── */
.description-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 16px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 12px;
  min-height: 0;
  flex-shrink: 0;
}

.description-state.error {
  opacity: 0.7;
  color: #f87171;
}

/* ── Description content ── */
.description-content {
  min-height: 0;
}

.description-section {
  margin-bottom: 14px;
}

.description-section:last-child {
  margin-bottom: 0;
}

.description-text {
  padding: 8px 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--fg-color, #fff);
  opacity: 0.85;
  word-break: break-word;
}

.description-text :deep(p) {
  margin: 0 0 8px 0;
}

.description-text :deep(p:last-child) {
  margin-bottom: 0;
}

.description-text :deep(a) {
  color: rgba(66, 153, 225, 0.9);
}

.description-text :deep(ul),
.description-text :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.description-text :deep(h1),
.description-text :deep(h2),
.description-text :deep(h3) {
  font-size: 13px;
  margin: 10px 0 4px 0;
  font-weight: 600;
  opacity: 0.95;
}

.description-text :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.description-text :deep(img) {
  max-width: 100%;
  border-radius: 4px;
}

/* ── Placeholder (shared) ── */
.placeholder {
  font-style: italic;
  color: rgba(226, 232, 240, 0.5);
  text-align: center;
  padding: 16px 0;
  font-size: 12px;
}

/* ── Spinner (Font Awesome) ── */
.fa-spinner {
  animation: fa-spin 1s linear infinite;
}

@keyframes fa-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>