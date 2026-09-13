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
    exampleUrl: 'https://huggingface.co/user/repo',
    placeholder: 'https://huggingface.co/user/repo',
    pattern: /^https?:\/\/(?:www\.)?huggingface\.co\/([^/?#\s]+\/[^/?#\s]+)/i,
    canonical: (id) => `https://huggingface.co/${id}`,
  },
  {
    platform: 'modelscope',
    label: 'ModelScope',
    groupPrefix: 'ms',
    supportsEnrichment: true,
    supportsDownload: false,
    exampleUrl: 'https://modelscope.cn/models/user/repo',
    placeholder: 'https://modelscope.cn/models/user/repo',
    pattern: /^https?:\/\/(?:www\.)?modelscope\.(?:cn|com)\/models\/([^/?#\s]+\/[^/?#\s]+)/i,
    canonical: (id) => `https://modelscope.cn/models/${id}`,
  },
  {
    platform: 'tensorart',
    label: 'TensorArt',
    groupPrefix: 'ta',
    supportsEnrichment: false,
    supportsDownload: false,
    exampleUrl: 'https://tensor.art/models/827823520299086029',
    placeholder: 'https://tensor.art/models/827823520299086029',
    pattern: /^https?:\/\/(?:www\.)?(?:tensor\.art|tusi\.cn)\/models\/(\d+)/i,
    canonical: (id) => `https://tensor.art/models/${id}`,
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
