<template>
  <div class="tree-node">
    <div
      class="tree-node__item"
      :class="[
        `tree-node__item--${variant}`,
        { 'tree-node__item--selected': isSelected }
      ]"
      :style="{ paddingLeft: `${depth * 16 + 8}px` }"
      @click="handleRowClick"
    >
      <!-- Expand/collapse toggle -->
      <button
        v-if="hasChildren"
        type="button"
        class="tree-node__toggle"
        @click.stop="$emit('toggle-expand', node.key)"
      >
        <svg
          class="tree-node__toggle-icon"
          :class="{ 'tree-node__toggle-icon--expanded': isExpanded }"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
        </svg>
      </button>
      <span v-else class="tree-node__toggle-spacer"></span>

      <!-- Checkbox -->
      <label class="tree-node__checkbox-label">
        <input
          type="checkbox"
          class="tree-node__checkbox"
          :checked="isSelected"
          @change="$emit('toggle-select', node.key)"
        />
        <span class="tree-node__checkbox-visual" :class="`tree-node__checkbox-visual--${variant}`">
          <svg v-if="isSelected" class="tree-node__check-icon" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
          </svg>
        </span>
      </label>

      <!-- Folder icon -->
      <svg class="tree-node__folder-icon" viewBox="0 0 16 16" fill="currentColor">
        <path d="M.54 3.87.5 3a2 2 0 0 1 2-2h3.672a2 2 0 0 1 1.414.586l.828.828A2 2 0 0 0 9.828 3H14a2 2 0 0 1 2 2v1.5a.5.5 0 0 1-1 0V5a1 1 0 0 0-1-1H9.828a3 3 0 0 1-2.12-.879l-.83-.828A1 1 0 0 0 6.172 2H2.5a1 1 0 0 0-1 .981l.006.139C1.72 3.042 1.95 3 2.19 3h5.396l.707.707a1 1 0 0 0 .707.293H14.5a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0V5H9a2 2 0 0 1-1.414-.586l-.828-.828A1 1 0 0 0 6.172 3H2.19a1.5 1.5 0 0 0-1.69.87z"/>
        <path d="M1.5 4.5h13a.5.5 0 0 1 .5.5v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V5a.5.5 0 0 1 .5-.5z"/>
      </svg>

      <!-- Folder name -->
      <span class="tree-node__label">{{ node.label }}</span>
    </div>

    <!-- Children (recursive) -->
    <div v-if="hasChildren && isExpanded" class="tree-node__children">
      <FolderTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :selected="selected"
        :expanded="expanded"
        :variant="variant"
        :depth="depth + 1"
        @toggle-expand="$emit('toggle-expand', $event)"
        @toggle-select="$emit('toggle-select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FolderTreeNode as FolderTreeNodeType } from '../../../composables/types'

const props = defineProps<{
  node: FolderTreeNodeType
  selected: string[]
  expanded: Set<string>
  variant: 'include' | 'exclude'
  depth: number
}>()

const emit = defineEmits<{
  'toggle-expand': [key: string]
  'toggle-select': [key: string]
}>()

const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
const isExpanded = computed(() => props.expanded.has(props.node.key))
const isSelected = computed(() => props.selected.includes(props.node.key))

// Handle row click - toggle selection unless clicking checkbox directly
const handleRowClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (target.closest('.tree-node__checkbox-label')) {
    return
  }
  emit('toggle-select', props.node.key)
}
</script>

<style scoped>
.tree-node__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.tree-node__item:hover {
  background: var(--comfy-input-bg, #333);
}

.tree-node__toggle {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.5;
  padding: 0;
  flex-shrink: 0;
}

.tree-node__toggle:hover {
  opacity: 1;
}

.tree-node__toggle-icon {
  width: 10px;
  height: 10px;
  transition: transform 0.15s;
}

.tree-node__toggle-icon--expanded {
  transform: rotate(90deg);
}

.tree-node__toggle-spacer {
  width: 16px;
  flex-shrink: 0;
}

.tree-node__checkbox-label {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.tree-node__checkbox {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.tree-node__checkbox-visual {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 3px;
  flex-shrink: 0;
  transition: all 0.15s;
}

.tree-node__item:hover .tree-node__checkbox-visual {
  border-color: var(--fg-color, #fff);
}

.tree-node__checkbox:checked + .tree-node__checkbox-visual--include {
  background: #4299e1;
  border-color: #4299e1;
}

.tree-node__checkbox:checked + .tree-node__checkbox-visual--exclude {
  background: #ef4444;
  border-color: #ef4444;
}

.tree-node__check-icon {
  width: 10px;
  height: 10px;
  color: #fff;
}

.tree-node__folder-icon {
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  flex-shrink: 0;
}

.tree-node__label {
  flex: 1;
  font-size: 13px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node__children {
  /* Children already indented via padding */
}
</style>
