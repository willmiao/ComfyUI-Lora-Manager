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
}

export interface LoraEntry {
  name: string
  strength: number
  clipStrength: number
  active: boolean
  expanded: boolean
  locked: boolean
}

export interface ComponentWidget {
  serializeValue?: () => Promise<LoraPoolConfig | RandomizerConfig>
  value?: LoraPoolConfig | LegacyLoraPoolConfig | RandomizerConfig
  onSetValue?: (v: LoraPoolConfig | LegacyLoraPoolConfig | RandomizerConfig) => void
  updateConfig?: (v: LoraPoolConfig | RandomizerConfig) => void
}
