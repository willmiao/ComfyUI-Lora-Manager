import { afterEach, describe, expect, it } from 'vitest'
import { getLmBasePath, lmApiUrl } from '@/utils/basePath'

const originalPathname = window.location.pathname

function setPathname(pathname: string) {
  window.history.replaceState(null, '', pathname)
}

afterEach(() => {
  setPathname(originalPathname)
})

describe('getLmBasePath', () => {
  it('returns an empty string when ComfyUI is served at the root', () => {
    setPathname('/')

    expect(getLmBasePath()).toBe('')
  })

  it('strips the trailing slash from a subpath prefix', () => {
    setPathname('/comfyui/')

    expect(getLmBasePath()).toBe('/comfyui')
  })

  it('keeps a prefix without a trailing slash as-is', () => {
    setPathname('/ComfyBackendDirect')

    expect(getLmBasePath()).toBe('/ComfyBackendDirect')
  })
})

describe('lmApiUrl', () => {
  it('leaves root-absolute paths unchanged at the root', () => {
    setPathname('/')

    expect(lmApiUrl('/api/lm/loras/list')).toBe('/api/lm/loras/list')
  })

  it('prepends the subpath prefix to root-absolute paths', () => {
    setPathname('/comfyui/')

    expect(lmApiUrl('/api/lm/loras/list')).toBe('/comfyui/api/lm/loras/list')
  })
})
