/**
 * External model source helpers (Hugging Face / ModelScope / TensorArt).
 *
 * Mirrors `py/services/model_sources/registry.py` so the frontend and the
 * backend agree on URL recognition, version-group keys, and which sites
 * support AI metadata enrichment.
 *
 * Models loaded from an older cache may only carry the legacy `hf_url`
 * field; every helper here falls back to it, and to the legacy
 * `hf:user/repo` group key shape.
 */

import { translate } from './i18nHelpers.js';

export const MODEL_SOURCES = [
  {
    platform: 'huggingface',
    label: 'Hugging Face',
    groupPrefix: 'hf',
    supportsEnrichment: true,
    supportsDownload: true,
    defaultRevision: 'main',
    defaultSubdir: 'huggingface',
    exampleUrl: 'https://huggingface.co/user/repo',
    placeholder: 'https://huggingface.co/user/repo',
    pattern: /^https?:\/\/(?:www\.)?huggingface\.co\/([^/?#\s]+\/[^/?#\s]+)/i,
    // `blob` is the web preview page; it maps 1:1 to the `resolve` download URL.
    filePattern:
      /^https?:\/\/(?:www\.)?huggingface\.co\/([^/?#\s]+\/[^/?#\s]+)\/(?:resolve|blob)\/([^/?#\s]+)\/(.+)$/i,
    canonical: (id) => `https://huggingface.co/${id}`,
    filePage: (id, filename) => `https://huggingface.co/${id}/blob/main/${filename}`,
    // Bare `user/repo` has always meant Hugging Face; keep that meaning.
    bareRepoPattern: /^([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)$/,
  },
  {
    platform: 'modelscope',
    label: 'ModelScope',
    groupPrefix: 'ms',
    supportsEnrichment: true,
    supportsDownload: true,
    defaultRevision: 'master',
    defaultSubdir: 'modelscope',
    exampleUrl: 'https://modelscope.cn/models/user/repo',
    placeholder: 'https://modelscope.cn/models/user/repo',
    pattern: /^https?:\/\/(?:www\.)?modelscope\.(?:cn|com)\/models\/([^/?#\s]+\/[^/?#\s]+)/i,
    filePattern:
      /^https?:\/\/(?:www\.)?modelscope\.(?:cn|com)\/models\/([^/?#\s]+\/[^/?#\s]+)\/resolve\/([^/?#\s]+)\/(.+)$/i,
    canonical: (id) => `https://modelscope.cn/models/${id}`,
    filePage: (id, filename) =>
      `https://modelscope.cn/models/${id}/file/view/master/${filename}`,
  },
  {
    // A separate catalogue from `modelscope.cn`, not an alias: a repository
    // published on one is routinely absent from the other, so the host is part
    // of the model's identity. Mirrors ModelScopeIntlSource in the backend.
    platform: 'modelscope-ai',
    label: 'ModelScope (International)',
    groupPrefix: 'msai',
    supportsEnrichment: true,
    supportsDownload: true,
    defaultRevision: 'master',
    defaultSubdir: 'modelscope-ai',
    exampleUrl: 'https://www.modelscope.ai/models/user/repo',
    placeholder: 'https://www.modelscope.ai/models/user/repo',
    pattern: /^https?:\/\/(?:www\.)?modelscope\.ai\/models\/([^/?#\s]+\/[^/?#\s]+)/i,
    filePattern:
      /^https?:\/\/(?:www\.)?modelscope\.ai\/models\/([^/?#\s]+\/[^/?#\s]+)\/resolve\/([^/?#\s]+)\/(.+)$/i,
    canonical: (id) => `https://www.modelscope.ai/models/${id}`,
    filePage: (id, filename) =>
      `https://www.modelscope.ai/models/${id}/file/view/master/${filename}`,
  },
  {
    platform: 'tensorart',
    label: 'TensorArt',
    groupPrefix: 'ta',
    supportsEnrichment: false,
    supportsDownload: false,
    defaultRevision: '',
    defaultSubdir: '',
    exampleUrl: 'https://tensor.art/models/827823520299086029',
    placeholder: 'https://tensor.art/models/827823520299086029',
    pattern: /^https?:\/\/(?:www\.)?(?:tensor\.art|tusi\.cn)\/models\/(\d+)/i,
    filePattern: null,
    canonical: (id) => `https://tensor.art/models/${id}`,
    filePage: null,
  },
];

/** Return the source descriptor for a platform id, or null. */
export function getModelSource(platform) {
  if (!platform || typeof platform !== 'string') return null;
  const needle = platform.trim().toLowerCase();
  return MODEL_SOURCES.find((source) => source.platform === needle) || null;
}

/**
 * Parse any supported model URL.
 * @returns {{platform: string, label: string, groupPrefix: string,
 *   supportsEnrichment: boolean, supportsDownload: boolean,
 *   sourceId: string, url: string}|null}
 */
export function parseModelSourceUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const candidate = url.trim();
  if (!candidate) return null;
  for (const source of MODEL_SOURCES) {
    const match = candidate.match(source.pattern);
    if (match) {
      return {
        ...source,
        sourceId: match[1],
        url: source.canonical(match[1]),
      };
    }
  }
  return null;
}

/** Return the stored source URL of a model (new field, then legacy). */
export function getModelSourceUrl(model) {
  if (!model) return '';
  const value = model.source_url || model.hf_url || '';
  return typeof value === 'string' ? value.trim() : '';
}

/** Return the stored source platform of a model. */
export function getModelSourcePlatform(model) {
  if (!model) return '';
  const value = model.source_platform || '';
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

/**
 * Resolve the full source descriptor for a model, tolerating models that
 * predate the `source_*` fields.
 */
export function getModelSourceInfo(model) {
  if (!model) return null;
  const url = getModelSourceUrl(model);
  const declared = getModelSource(getModelSourcePlatform(model));
  const parsed = parseModelSourceUrl(url);

  if (declared) {
    return {
      ...declared,
      sourceId: parsed ? parsed.sourceId : '',
      url: parsed ? parsed.url : url,
    };
  }
  return parsed;
}

/**
 * Version-group key for a model, matching the backend's `_extract_group_key`.
 * Returns `''` when the model has no external source.
 */
export function getModelSourceGroupKey(model) {
  const info = getModelSourceInfo(model);
  if (!info || !info.sourceId) return '';
  return `${info.groupPrefix}:${info.sourceId}`;
}

/** Whether AI metadata enrichment can run for this model's source. */
export function canEnrichModelSource(model) {
  const info = getModelSourceInfo(model);
  return Boolean(info && info.supportsEnrichment);
}

/**
 * Parse a version-group key such as `hf:user/repo`, `ms:user/repo`, or
 * `ta:827823520299086029` back into its source descriptor.
 *
 * These keys are NOT CivitAI model ids, so callers must not send them to the
 * CivitAI API.
 *
 * @returns {{platform: string, label: string, sourceId: string}|null}
 */
export function parseModelSourceGroupKey(groupKey) {
  if (!groupKey || typeof groupKey !== 'string') return null;
  const separator = groupKey.indexOf(':');
  if (separator <= 0) return null;

  const prefix = groupKey.slice(0, separator);
  const source = MODEL_SOURCES.find((candidate) => candidate.groupPrefix === prefix);
  if (!source) return null;

  return {
    platform: source.platform,
    label: source.label,
    sourceId: groupKey.slice(separator + 1),
  };
}

/** Localised "View on X" title for the source globe icon. */
export function getModelSourceViewTitle(info) {
  if (!info) return '';
  if (info.platform === 'huggingface') {
    return translate('modelCard.actions.viewOnHuggingFace', {}, 'View on Hugging Face');
  }
  return translate(
    'modelCard.actions.viewOnSource',
    { source: info.label },
    `View on ${info.label}`
  );
}

/** Open a model page on its external site in a new tab. */
export function openModelSource(url) {
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
}

// ---------------------------------------------------------------------------
// Download support
// ---------------------------------------------------------------------------

/** Sources whose repositories the backend can download from. */
export const DOWNLOADABLE_SOURCES = MODEL_SOURCES.filter((s) => s.supportsDownload);

/**
 * Whether a DownloadManager `source` value refers to an external repository
 * download (as opposed to a CivitAI/CivArchive version or a direct link).
 */
export function isExternalModelSource(source) {
  return DOWNLOADABLE_SOURCES.some((s) => s.platform === source);
}

/** Return the downloadable source descriptor for a platform, or null. */
export function getDownloadSource(platform) {
  const source = getModelSource(platform);
  return source && source.supportsDownload ? source : null;
}

/** Normalise a repository id: reject traversal, exactly one slash. */
export function isValidRepoId(repo) {
  if (!repo || typeof repo !== 'string' || repo.split('/').length !== 2) return false;
  return repo
    .split('/')
    .every((part) => part && part !== '.' && part !== '..' && /^[A-Za-z0-9_][\w.-]*$/.test(part));
}

/**
 * Recognise a downloadable model-source URL.
 *
 * Handles both a repository page and a direct file (resolve) URL for every
 * source that supports downloads, plus the historical bare `owner/name`
 * shorthand, which only ever meant Hugging Face.
 *
 * @returns {{kind: 'repo'|'file', platform: string, label: string,
 *   repo: string, revision?: string, filename?: string}|null}
 */
export function detectModelSourceDownloadUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const candidate = url.trim();
  if (!candidate) return null;

  // Direct file URLs first: the repo pattern would match their prefix and
  // lose the revision/filename.
  for (const source of DOWNLOADABLE_SOURCES) {
    if (!source.filePattern) continue;
    const match = candidate.match(source.filePattern);
    if (match) {
      return {
        kind: 'file',
        platform: source.platform,
        label: source.label,
        repo: match[1],
        revision: match[2],
        filename: match[3],
      };
    }
  }

  for (const source of DOWNLOADABLE_SOURCES) {
    const match = candidate.match(source.pattern);
    if (match) {
      return {
        kind: 'repo',
        platform: source.platform,
        label: source.label,
        repo: match[1],
      };
    }
  }

  if (!candidate.includes('://')) {
    for (const source of DOWNLOADABLE_SOURCES) {
      if (!source.bareRepoPattern) continue;
      const match = candidate.match(source.bareRepoPattern);
      if (match && isValidRepoId(match[1])) {
        return {
          kind: 'repo',
          platform: source.platform,
          label: source.label,
          repo: match[1],
        };
      }
    }
  }

  return null;
}

/** Human-facing page for one file of an external repository. */
export function buildModelSourceFilePage({ platform, repo, filename }) {
  const source = getModelSource(platform);
  if (!source || !source.filePage || !filename) {
    return source ? source.canonical(repo) : null;
  }
  return source.filePage(repo, filename);
}
