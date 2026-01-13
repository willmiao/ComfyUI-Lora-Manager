import { ref } from 'vue'
import type { BaseModelOption, TagOption, FolderTreeNode, LoraItem } from './types'

export function useLoraPoolApi() {
  const isLoading = ref(false)

  const fetchBaseModels = async (limit = 50): Promise<BaseModelOption[]> => {
    try {
      const response = await fetch(`/api/lm/loras/base-models?limit=${limit}`)
      const data = await response.json()
      return data.base_models || []
    } catch (error) {
      console.error('[LoraPoolApi] Failed to fetch base models:', error)
      return []
    }
  }

  const fetchTags = async (limit = 100): Promise<TagOption[]> => {
    try {
      const response = await fetch(`/api/lm/loras/top-tags?limit=${limit}`)
      const data = await response.json()
      return data.tags || []
    } catch (error) {
      console.error('[LoraPoolApi] Failed to fetch tags:', error)
      return []
    }
  }

  const fetchFolderTree = async (): Promise<FolderTreeNode[]> => {
    try {
      const response = await fetch('/api/lm/loras/unified-folder-tree')
      const data = await response.json()
      return transformFolderTree(data.tree || {})
    } catch (error) {
      console.error('[LoraPoolApi] Failed to fetch folder tree:', error)
      return []
    }
  }

  const transformFolderTree = (tree: Record<string, any>, parentPath = ''): FolderTreeNode[] => {
    if (!tree || typeof tree !== 'object') {
      return []
    }

    return Object.entries(tree).map(([name, children]) => {
      const path = parentPath ? `${parentPath}/${name}` : name
      const childNodes = transformFolderTree(children as Record<string, any>, path)

      return {
        key: path,
        label: name,
        children: childNodes.length > 0 ? childNodes : undefined
      }
    })
  }

  interface FetchLorasParams {
    baseModels?: string[]
    tagsInclude?: string[]
    tagsExclude?: string[]
    foldersInclude?: string[]
    foldersExclude?: string[]
    noCreditRequired?: boolean
    allowSelling?: boolean
    page?: number
    pageSize?: number
  }

  const fetchLoras = async (params: FetchLorasParams): Promise<{ items: LoraItem[]; total: number }> => {
    isLoading.value = true
    try {
      const urlParams = new URLSearchParams()
      urlParams.set('page', String(params.page || 1))
      urlParams.set('page_size', String(params.pageSize || 6))

      params.baseModels?.forEach(bm => urlParams.append('base_model', bm))
      params.tagsInclude?.forEach(tag => urlParams.append('tag_include', tag))
      params.tagsExclude?.forEach(tag => urlParams.append('tag_exclude', tag))

      // Folder filters
      if (params.foldersInclude && params.foldersInclude.length > 0) {
        urlParams.set('folder', params.foldersInclude[0])
        urlParams.set('recursive', 'true')
      }
      params.foldersExclude?.forEach(folder => urlParams.append('folder_exclude', folder))

      if (params.noCreditRequired !== undefined) {
        urlParams.set('credit_required', String(!params.noCreditRequired))
      }

      if (params.allowSelling !== undefined) {
        urlParams.set('allow_selling_generated_content', String(params.allowSelling))
      }

      const response = await fetch(`/api/lm/loras/list?${urlParams}`)
      const data = await response.json()

      return {
        items: data.items || [],
        total: data.total || 0
      }
    } catch (error) {
      console.error('[LoraPoolApi] Failed to fetch loras:', error)
      return { items: [], total: 0 }
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    fetchBaseModels,
    fetchTags,
    fetchFolderTree,
    fetchLoras
  }
}
