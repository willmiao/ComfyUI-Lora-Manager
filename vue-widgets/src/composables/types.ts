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

export interface ComponentWidget {
  serializeValue?: () => Promise<LoraPoolConfig>
  value?: LoraPoolConfig | LegacyLoraPoolConfig
  onSetValue?: (v: LoraPoolConfig | LegacyLoraPoolConfig) => void
  updateConfig?: (v: LoraPoolConfig) => void
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
