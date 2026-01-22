// Shared types for LoRA Pool Widget

export interface LoraPoolConfig {
  version: number
  filters: {
    baseModels: string[]
    tags: { include: string[]; exclude: string[] }
    folders: { include: string[]; exclude: string[] }
    license: {
      noCreditRequired: boolean
      allowSelling: boolean
    }
  }
  preview: { matchCount: number; lastUpdated: number }
}

export interface LoraItem {
  file_path: string
  file_name: string
  model_name?: string
  preview_url?: string
}

export interface BaseModelOption {
  name: string
  count: number
}

export interface TagOption {
  tag: string
  count: number
}

export interface FolderTreeNode {
  key: string
  label: string
  children?: FolderTreeNode[]
}

// Legacy config for migration (v1)
export interface LegacyLoraPoolConfig {
  version: 1
  filters: {
    baseModels: string[]
    tags: { include: string[]; exclude: string[] }
    folder: { path: string | null; recursive: boolean }
    favoritesOnly: boolean
    license: {
      noCreditRequired: boolean | null
      allowSellingGeneratedContent: boolean | null
    }
  }
  preview: { matchCount: number; lastUpdated: number }
}

// Randomizer config
export interface RandomizerConfig {
  count_mode: 'fixed' | 'range'
  count_fixed: number
  count_min: number
  count_max: number
  model_strength_min: number
  model_strength_max: number
  use_same_clip_strength: boolean
  clip_strength_min: number
  clip_strength_max: number
  roll_mode: 'fixed' | 'always'
  last_used?: LoraEntry[] | null
  use_recommended_strength: boolean
  recommended_strength_scale_min: number
  recommended_strength_scale_max: number
  execution_seed?: number | null  // Seed for execution_stack (previous next_seed)
  next_seed?: number | null       // Seed for ui_loras (current)
}

export interface LoraEntry {
  name: string
  strength: number
  clipStrength: number
  active: boolean
  expanded: boolean
  locked: boolean
}

// Cycler config
export interface CyclerConfig {
  current_index: number       // 1-based index
  total_count: number         // Cached for display
  pool_config_hash: string    // For change detection
  model_strength: number
  clip_strength: number
  use_same_clip_strength: boolean
  sort_by: 'filename' | 'model_name'
  current_lora_name: string   // For display
  current_lora_filename: string
  // Dual-index mechanism for batch queue synchronization
  execution_index?: number | null  // Index to use for current execution
  next_index?: number | null       // Index for display after execution
}

export interface ComponentWidget {
  serializeValue?: () => Promise<LoraPoolConfig | RandomizerConfig | CyclerConfig>
  value?: LoraPoolConfig | LegacyLoraPoolConfig | RandomizerConfig | CyclerConfig
  onSetValue?: (v: LoraPoolConfig | LegacyLoraPoolConfig | RandomizerConfig | CyclerConfig) => void
  updateConfig?: (v: LoraPoolConfig | RandomizerConfig | CyclerConfig) => void
}
