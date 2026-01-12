<template>
  <ModalWrapper
    :visible="visible"
    :title="variant === 'include' ? 'Include Folders' : 'Exclude Folders'"
    :subtitle="variant === 'include' ? 'Select folders to include in the filter' : 'Select folders to exclude from the filter'"
    @close="$emit('close')"
  >
    <template #search>
      <div class="search-container">
        <svg class="search-icon" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Search folders..."
        />
      </div>
    </template>

    <div class="folder-tree">
      <template v-if="filteredFolders.length > 0">
        <FolderTreeNode
          v-for="node in filteredFolders"
          :key="node.key"
          :node="node"
          :selected="selected"
          :expanded="expandedKeys"
          :variant="variant"
          :depth="0"
          @toggle-expand="toggleExpand"
          @toggle-select="toggleSelect"
        />
      </template>
      <div v-else class="no-results">
        No folders found
      </div>
    </div>
  </ModalWrapper>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import ModalWrapper from './ModalWrapper.vue'
import FolderTreeNode from './FolderTreeNode.vue'
import type { FolderTreeNode as FolderTreeNodeType } from '../../../composables/types'

const props = defineProps<{
  visible: boolean
  folders: FolderTreeNodeType[]
  selected: string[]
  variant: 'include' | 'exclude'
}>()

const emit = defineEmits<{
  close: []
  'update:selected': [value: string[]]
}>()

const searchQuery = ref('')
const expandedKeys = ref<Set<string>>(new Set())

// Filter folders based on search query
const filteredFolders = computed(() => {
  if (!searchQuery.value) {
    return props.folders
  }
  const query = searchQuery.value.toLowerCase()
  return filterTree(props.folders, query)
})

// Recursively filter the tree, keeping matching nodes and their ancestors
const filterTree = (nodes: FolderTreeNodeType[], query: string): FolderTreeNodeType[] => {
  const result: FolderTreeNodeType[] = []

  for (const node of nodes) {
    const matches = node.key.toLowerCase().includes(query) || node.label.toLowerCase().includes(query)
    const filteredChildren = node.children ? filterTree(node.children, query) : []

    if (matches || filteredChildren.length > 0) {
      result.push({
        ...node,
        children: filteredChildren.length > 0 ? filteredChildren : node.children
      })
      // Auto-expand nodes when searching
      if (searchQuery.value && filteredChildren.length > 0) {
        expandedKeys.value.add(node.key)
      }
    }
  }

  return result
}

// Toggle expanded state
const toggleExpand = (key: string) => {
  if (expandedKeys.value.has(key)) {
    expandedKeys.value.delete(key)
  } else {
    expandedKeys.value.add(key)
  }
  // Force reactivity update
  expandedKeys.value = new Set(expandedKeys.value)
}

// Toggle selection
const toggleSelect = (key: string) => {
  const newSelected = props.selected.includes(key)
    ? props.selected.filter(k => k !== key)
    : [...props.selected, key]
  emit('update:selected', newSelected)
}

// Reset expanded state when modal opens
watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    searchQuery.value = ''
    // Auto-expand first level
    expandedKeys.value = new Set()
  }
})
</script>

<style scoped>
.search-container {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: var(--fg-color, #fff);
}

.search-input::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}

.folder-tree {
  display: flex;
  flex-direction: column;
}

.no-results {
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}
</style>
