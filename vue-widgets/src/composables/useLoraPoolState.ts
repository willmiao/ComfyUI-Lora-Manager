import { ref, computed, watch } from 'vue'
import type {
  LoraPoolConfig,
  LegacyLoraPoolConfig,
  BaseModelOption,
  TagOption,
  FolderTreeNode,
  LoraItem,
  ComponentWidget
} from './types'
import { useLoraPoolApi } from './useLoraPoolApi'

export function useLoraPoolState(widget: ComponentWidget) {
  const api = useLoraPoolApi()

  // Flag to prevent infinite loops during config restoration
  // callback → restoreFromConfig → watch → refreshPreview → buildConfig → widget.value = config → callback → ...
  let isRestoring = false

  // Filter state
  const selectedBaseModels = ref<string[]>([])
  const includeTags = ref<string[]>([])
  const excludeTags = ref<string[]>([])
  const includeFolders = ref<string[]>([])
  const excludeFolders = ref<string[]>([])
  const noCreditRequired = ref(false)
  const allowSelling = ref(false)

  // Available options from API
  const availableBaseModels = ref<BaseModelOption[]>([])
  const availableTags = ref<TagOption[]>([])
  const folderTree = ref<FolderTreeNode[]>([])

  // Preview state
  const previewItems = ref<LoraItem[]>([])
  const matchCount = ref(0)
  const isLoading = computed(() => api.isLoading.value)

  // Build config from current state
  const buildConfig = (): LoraPoolConfig => {
    const config: LoraPoolConfig = {
      version: 2,
      filters: {
        baseModels: selectedBaseModels.value,
        tags: {
          include: includeTags.value,
          exclude: excludeTags.value
        },
        folders: {
          include: includeFolders.value,
          exclude: excludeFolders.value
        },
        license: {
          noCreditRequired: noCreditRequired.value,
          allowSelling: allowSelling.value
        }
      },
      preview: {
        matchCount: matchCount.value,
        lastUpdated: Date.now()
      }
    }

    // Update widget value (this triggers callback for UI sync)
    // Skip during restoration to prevent infinite loops:
    // callback → restoreFromConfig → watch → refreshPreview → buildConfig → widget.value = config → callback → ...
    if (!isRestoring) {
      widget.value = config
    }
    return config
  }

  // Migrate legacy config (v1) to current format (v2)
  const migrateConfig = (legacy: LegacyLoraPoolConfig): LoraPoolConfig => {
    return {
      version: 2,
      filters: {
        baseModels: legacy.filters.baseModels || [],
        tags: {
          include: legacy.filters.tags?.include || [],
          exclude: legacy.filters.tags?.exclude || []
        },
        folders: {
          include: legacy.filters.folder?.path ? [legacy.filters.folder.path] : [],
          exclude: []
        },
        license: {
          noCreditRequired: legacy.filters.license?.noCreditRequired ?? false,
          allowSelling: legacy.filters.license?.allowSellingGeneratedContent ?? false
        }
      },
      preview: legacy.preview || { matchCount: 0, lastUpdated: 0 }
    }
  }

  // Restore state from config
  const restoreFromConfig = (rawConfig: LoraPoolConfig | LegacyLoraPoolConfig) => {
    // Set flag to prevent buildConfig from triggering widget.value updates during restoration
    // This breaks the infinite loop: callback → restoreFromConfig → watch → refreshPreview → buildConfig → widget.value = config → callback
    isRestoring = true

    try {
      // Migrate if needed
      const config = rawConfig.version === 1
        ? migrateConfig(rawConfig as LegacyLoraPoolConfig)
        : rawConfig as LoraPoolConfig

      if (!config?.filters) return

      const { filters, preview } = config

      // Helper to update ref only if value changed
      const updateIfChanged = <T>(refValue: { value: T }, newValue: T) => {
        if (JSON.stringify(refValue.value) !== JSON.stringify(newValue)) {
          refValue.value = newValue
        }
      }

      updateIfChanged(selectedBaseModels, filters.baseModels || [])
      updateIfChanged(includeTags, filters.tags?.include || [])
      updateIfChanged(excludeTags, filters.tags?.exclude || [])
      updateIfChanged(includeFolders, filters.folders?.include || [])
      updateIfChanged(excludeFolders, filters.folders?.exclude || [])
      updateIfChanged(noCreditRequired, filters.license?.noCreditRequired ?? false)
      updateIfChanged(allowSelling, filters.license?.allowSelling ?? false)

      // matchCount doesn't trigger watchers, so direct assignment is fine
      matchCount.value = preview?.matchCount || 0
    } finally {
      isRestoring = false
    }
  }

  // Fetch filter options from API
  const fetchFilterOptions = async () => {
    const [baseModels, tags, folders] = await Promise.all([
      api.fetchBaseModels(),
      api.fetchTags(),
      api.fetchFolderTree()
    ])

    availableBaseModels.value = baseModels
    availableTags.value = tags
    folderTree.value = folders
  }

  // Refresh preview with current filters
  const refreshPreview = async () => {
    const result = await api.fetchLoras({
      baseModels: selectedBaseModels.value,
      tagsInclude: includeTags.value,
      tagsExclude: excludeTags.value,
      foldersInclude: includeFolders.value,
      foldersExclude: excludeFolders.value,
      noCreditRequired: noCreditRequired.value || undefined,
      allowSelling: allowSelling.value || undefined,
      pageSize: 6
    })

    previewItems.value = result.items
    matchCount.value = result.total
    buildConfig()
  }

  // Debounced filter change handler
  let filterTimeout: ReturnType<typeof setTimeout> | null = null
  const onFilterChange = () => {
    if (filterTimeout) clearTimeout(filterTimeout)
    filterTimeout = setTimeout(() => {
      refreshPreview()
    }, 300)
  }

  // Watch all filter changes
  watch([
    selectedBaseModels,
    includeTags,
    excludeTags,
    includeFolders,
    excludeFolders,
    noCreditRequired,
    allowSelling
  ], onFilterChange, { deep: true })

  return {
    // Filter state
    selectedBaseModels,
    includeTags,
    excludeTags,
    includeFolders,
    excludeFolders,
    noCreditRequired,
    allowSelling,

    // Available options
    availableBaseModels,
    availableTags,
    folderTree,

    // Preview state
    previewItems,
    matchCount,
    isLoading,

    // Actions
    buildConfig,
    restoreFromConfig,
    fetchFilterOptions,
    refreshPreview
  }
}

export type LoraPoolStateReturn = ReturnType<typeof useLoraPoolState>
