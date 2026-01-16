<template>
  <div class="json-display-widget">
    <div class="json-content" ref="contentRef">
      <pre v-if="hasMetadata" v-html="highlightedJson"></pre>
      <div v-else class="placeholder">No metadata available</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface JsonDisplayWidget {
  serializeValue?: () => Promise<unknown>
  value?: unknown
  onSetValue?: (v: unknown) => void
}

const props = defineProps<{
  widget: JsonDisplayWidget
  node: { id: number; onExecuted?: (output: Record<string, unknown>) => void }
}>()

const metadata = ref<Record<string, unknown> | null>(null)

const hasMetadata = computed(() =>
  metadata.value !== null && Object.keys(metadata.value).length > 0
)

const highlightedJson = computed(() => {
  if (!metadata.value) return ''
  const jsonStr = JSON.stringify(metadata.value, null, 2)
  return syntaxHighlight(jsonStr)
})

// Color scheme matching original json_display_widget.js
const colors = {
  key: '#6ad6f5',      // Light blue for keys
  string: '#98c379',   // Soft green for strings
  number: '#e5c07b',   // Amber for numbers
  boolean: '#c678dd',  // Purple for booleans
  null: '#7f848e'      // Gray for null
}

function syntaxHighlight(json: string): string {
  // Escape HTML entities
  json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  // Apply syntax highlighting with regex
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      let color = colors.number

      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          // Key
          color = colors.key
          match = match.replace(/:$/, '')
          return `<span style="color:${color};">${match}</span>:`
        } else {
          // String value
          color = colors.string
        }
      } else if (/true|false/.test(match)) {
        color = colors.boolean
      } else if (/null/.test(match)) {
        color = colors.null
      }

      return `<span style="color:${color};">${match}</span>`
    }
  )
}

onMounted(() => {
  // Display-only widget - return null on serialization to avoid saving large metadata
  props.widget.serializeValue = async () => null

  // Handle external value updates (e.g., loading workflow, paste)
  props.widget.onSetValue = (v) => {
    if (v && typeof v === 'object') {
      metadata.value = v as Record<string, unknown>
    }
  }

  // Restore from saved value if exists (for workflow loading)
  if (props.widget.value && typeof props.widget.value === 'object') {
    metadata.value = props.widget.value as Record<string, unknown>
  }

  // Override onExecuted to handle backend UI updates
  // Following the pattern from LoraRandomizerWidget.vue
  const originalOnExecuted = (props.node as any).onExecuted?.bind(props.node)

  ;(props.node as any).onExecuted = function(output: any) {
    // Update metadata from backend ui return
    if (output?.metadata !== undefined) {
      let metadataValue = output.metadata

      // ComfyUI wraps ui values in arrays, unwrap if needed
      if (Array.isArray(metadataValue)) {
        metadataValue = metadataValue[0]
      }

      // If it's a string (JSON), parse it
      if (typeof metadataValue === 'string') {
        try {
          metadataValue = JSON.parse(metadataValue)
        } catch (e) {
          console.error('[JsonDisplayWidget] Failed to parse JSON:', e)
        }
      }

      metadata.value = metadataValue
    }

    // Call original onExecuted if it exists
    if (originalOnExecuted) {
      return originalOnExecuted(output)
    }
  }
})
</script>

<style scoped>
.json-display-widget {
  padding: 8px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 6px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.json-content {
  flex: 1;
  overflow: auto;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: rgba(226, 232, 240, 0.9);
}

.json-content pre {
  margin: 0;
  padding: 0;
}

.placeholder {
  font-style: italic;
  color: rgba(226, 232, 240, 0.6);
  text-align: center;
  padding: 20px 0;
}
</style>
