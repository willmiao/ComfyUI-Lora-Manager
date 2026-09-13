import { describe, it, expect, vi } from 'vitest';

const { I18N_MODULE } = vi.hoisted(() => ({
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key)),
}));

const {
  MODEL_SOURCES,
  parseModelSourceUrl,
  getModelSource,
  getModelSourceInfo,
  getModelSourceUrl,
  getModelSourceGroupKey,
  canEnrichModelSource,
  getModelSourceViewTitle,
  parseModelSourceGroupKey,
  openModelSource,
} = await import('../../../static/js/utils/modelSourceHelpers.js');

describe('modelSourceHelpers', () => {
  it('exposes one descriptor per supported platform', () => {
    expect(MODEL_SOURCES.map((s) => s.platform)).toEqual([
      'huggingface',
      'modelscope',
      'tensorart',
    ]);
  });

  describe('parseModelSourceUrl', () => {
    it('recognises Hugging Face URLs', () => {
      const info = parseModelSourceUrl('https://huggingface.co/user/repo');
      expect(info.platform).toBe('huggingface');
      expect(info.sourceId).toBe('user/repo');
    });

    it('recognises ModelScope URLs with view sub-paths', () => {
      const info = parseModelSourceUrl('https://modelscope.cn/models/user/repo/summary');
      expect(info.platform).toBe('modelscope');
      expect(info.sourceId).toBe('user/repo');
      expect(info.url).toBe('https://modelscope.cn/models/user/repo');
    });

    it('recognises TensorArt URLs and keeps only the numeric id', () => {
      const info = parseModelSourceUrl(
        'https://tensor.art/models/827823520299086029/Vivid-Impressions-Storybook-Sstyle-V1.0'
      );
      expect(info.platform).toBe('tensorart');
      expect(info.sourceId).toBe('827823520299086029');
      expect(info.url).toBe('https://tensor.art/models/827823520299086029');
    });

    it('rejects unsupported URLs', () => {
      expect(parseModelSourceUrl('https://example.com/x')).toBeNull();
      expect(parseModelSourceUrl('')).toBeNull();
      expect(parseModelSourceUrl(null)).toBeNull();
    });
  });

  describe('getModelSourceInfo', () => {
    it('falls back to the legacy hf_url field', () => {
      const info = getModelSourceInfo({ hf_url: 'https://huggingface.co/user/repo' });
      expect(info.platform).toBe('huggingface');
      expect(info.sourceId).toBe('user/repo');
    });

    it('prefers the canonical source fields', () => {
      const info = getModelSourceInfo({
        source_platform: 'modelscope',
        source_url: 'https://modelscope.cn/models/user/repo',
        hf_url: 'https://huggingface.co/old/repo',
      });
      expect(info.platform).toBe('modelscope');
    });

    it('returns null when there is no source', () => {
      expect(getModelSourceInfo({})).toBeNull();
      expect(getModelSourceInfo({ hf_url: '' })).toBeNull();
    });
  });

  describe('getModelSourceUrl', () => {
    it('reads source_url then hf_url', () => {
      expect(getModelSourceUrl({ source_url: 'https://a.example/1' })).toBe('https://a.example/1');
      expect(getModelSourceUrl({ hf_url: 'https://huggingface.co/u/r' })).toBe(
        'https://huggingface.co/u/r'
      );
      expect(getModelSourceUrl({})).toBe('');
    });
  });

  describe('getModelSourceGroupKey', () => {
    it('matches the backend group-key shapes', () => {
      expect(getModelSourceGroupKey({ hf_url: 'https://huggingface.co/u/r' })).toBe('hf:u/r');
      expect(
        getModelSourceGroupKey({ source_url: 'https://modelscope.cn/models/u/r' })
      ).toBe('ms:u/r');
      expect(getModelSourceGroupKey({ source_url: 'https://tensor.art/models/123' })).toBe(
        'ta:123'
      );
    });

    it('returns an empty string without a source', () => {
      expect(getModelSourceGroupKey({})).toBe('');
    });
  });

  describe('canEnrichModelSource', () => {
    it('allows Hugging Face and ModelScope', () => {
      expect(canEnrichModelSource({ hf_url: 'https://huggingface.co/u/r' })).toBe(true);
      expect(
        canEnrichModelSource({ source_url: 'https://modelscope.cn/models/u/r' })
      ).toBe(true);
    });

    it('disallows TensorArt and unlinked models', () => {
      expect(canEnrichModelSource({ source_url: 'https://tensor.art/models/123' })).toBe(false);
      expect(canEnrichModelSource({})).toBe(false);
    });
  });

  describe('getModelSourceViewTitle', () => {
    it('uses the branded label for non-HF sources', () => {
      expect(getModelSourceViewTitle(getModelSource('modelscope'))).toBe('View on ModelScope');
      expect(getModelSourceViewTitle(getModelSource('tensorart'))).toBe('View on TensorArt');
    });

    it('keeps the historical Hugging Face title', () => {
      expect(getModelSourceViewTitle(getModelSource('huggingface'))).toBe(
        'View on Hugging Face'
      );
    });
  });

  describe('parseModelSourceGroupKey', () => {
    it('parses every external group-key prefix', () => {
      expect(parseModelSourceGroupKey('hf:user/repo')).toEqual({
        platform: 'huggingface',
        label: 'Hugging Face',
        sourceId: 'user/repo',
      });
      expect(parseModelSourceGroupKey('ms:user/repo').platform).toBe('modelscope');
      expect(parseModelSourceGroupKey('ta:123').platform).toBe('tensorart');
    });

    it('rejects numeric CivitAI model ids and unknown prefixes', () => {
      expect(parseModelSourceGroupKey(222)).toBeNull();
      expect(parseModelSourceGroupKey('222')).toBeNull();
      expect(parseModelSourceGroupKey('unknown:1')).toBeNull();
      expect(parseModelSourceGroupKey('')).toBeNull();
      expect(parseModelSourceGroupKey(null)).toBeNull();
    });
  });

  describe('openModelSource', () => {
    it('opens the URL in a new tab', () => {
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {});
      openModelSource('https://modelscope.cn/models/u/r');
      expect(openSpy).toHaveBeenCalledWith(
        'https://modelscope.cn/models/u/r',
        '_blank',
        'noopener,noreferrer'
      );
      openSpy.mockRestore();
    });

    it('does nothing without a URL', () => {
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {});
      openModelSource('');
      expect(openSpy).not.toHaveBeenCalled();
      openSpy.mockRestore();
    });
  });
});
