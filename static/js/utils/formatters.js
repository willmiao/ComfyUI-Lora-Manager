import { i18n } from '../i18n/index.js';
import { translate } from './i18nHelpers.js';

/**
 * Magnitude from which counts are abbreviated in dense UI (filter chips,
 * dropdown rows). Below it the count is shown exact, so ordinary libraries
 * look exactly like before; above it a five digit number would otherwise
 * become the widest and loudest element of the row it sits in. The exact value
 * stays available through `formatCountExact` for tooltips and aria-labels.
 */
const COUNT_COMPACT_FROM = 10000;

/**
 * Format an entry count (models, recipes, tags) for dense UI.
 *
 * Abbreviated to ~3 significant digits above `compactFrom`, so a five digit
 * count does not become the widest element of the row it sits in. The
 * abbreviation is left to Intl, which follows the UI language ("19.9K",
 * "1.99万", "19,9 k").
 *
 * Locales without a compact unit for the magnitude are detected and fall back
 * to the exact, grouped count: German has no unit below a million, so its
 * "compact" form is a *rounded* plain number ("18.500" for 18,475) that reads
 * as exact but is not, and Russian's "19,9 тыс." is wider than "18 475". An
 * abbreviation is only used when the locale actually produced one and it is
 * shorter than the exact count.
 *
 * @param {number} value - The count
 * @param {Object} [options]
 * @param {number} [options.compactFrom] - Magnitude to start abbreviating at
 * @returns {string} Formatted count (e.g. "42", "5,210", "19.9K")
 */
export function formatCount(value, { compactFrom = COUNT_COMPACT_FROM } = {}) {
    const count = Number(value) || 0;
    const exact = i18n.formatNumber(count);
    if (count < compactFrom) {
        return exact;
    }

    const compact = i18n.formatNumber(count, {
        notation: 'compact',
        maximumSignificantDigits: 3,
    });
    const roundedPlain = i18n.formatNumber(Number(count.toPrecision(3)));

    return compact !== roundedPlain && compact.length < exact.length ? compact : exact;
}

/**
 * Format an entry count in full, for tooltips and aria-labels that must not
 * lose precision to `formatCount`'s abbreviation.
 *
 * @param {number} value - The count
 * @returns {string} Exact, locale-grouped count (e.g. "19,876")
 */
export function formatCountExact(value) {
    return i18n.formatNumber(Number(value) || 0);
}

/**
 * Hover text for a counted chip or dropdown row: the full name plus the exact
 * count.
 *
 * It is set unconditionally rather than only when the rendered count was
 * abbreviated, for two reasons: the name is what CSS ellipsizes when a chip is
 * narrow, so the tooltip is the only place the full label can be read; and an
 * affordance that appears at some magnitudes and not others is unpredictable.
 *
 * @param {string} name - Label the count belongs to
 * @param {number} value - The count
 * @param {string} [key] - Translation key for the sentence
 * @returns {string} e.g. "character — 18,475 models"
 */
export function formatCountTitle(name, value, key = 'header.filter.countTitle') {
    const exact = formatCountExact(value);
    return translate(key, { name, count: exact }, `${name} — ${exact} models`);
}

/**
 * Format a file size in bytes to a human-readable string
 * @param {number} bytes - The size in bytes
 * @returns {string} Formatted size string (e.g., "1.5 MB")
 */
export function formatFileSize(bytes) {
    if (!bytes || isNaN(bytes)) return '';
    
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
}

/**
 * Convert timestamp to human readable date string
 * @param {number} modified - Timestamp in seconds
 * @returns {string} Formatted date string
 */
export function formatDate(modified) {
    if (!modified) return '';
    const date = new Date(modified * 1000);
    return date.toLocaleString();
}
