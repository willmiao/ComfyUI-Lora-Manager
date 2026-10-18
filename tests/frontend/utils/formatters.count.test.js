import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    formatCount,
    formatCountExact,
    formatCountTitle,
} from '../../../static/js/utils/formatters.js';
import { i18n } from '../../../static/js/i18n/index.js';

// The display locale is a property of the app, not of the test runner, so it is
// pinned here instead of relying on the environment default.
let originalLocale;

beforeEach(() => {
    originalLocale = i18n.currentLocale;
    i18n.currentLocale = 'en';
    vi.stubGlobal('i18n', {
        t: (key, params) => {
            if (key === 'header.filter.countTitle') {
                return `${params.name} — ${params.count} models`;
            }
            if (key === 'recipes.filter.countTitle') {
                return `${params.name} — ${params.count} recipes`;
            }
            return key;
        },
    });
});

afterEach(() => {
    i18n.currentLocale = originalLocale;
    vi.unstubAllGlobals();
});

describe('formatCount', () => {
    it('shows counts below the compact threshold exactly and grouped', () => {
        expect(formatCount(0)).toBe('0');
        expect(formatCount(7)).toBe('7');
        expect(formatCount(999)).toBe('999');
        expect(formatCount(5210)).toBe('5,210');
        expect(formatCount(9999)).toBe('9,999');
    });

    it('abbreviates to three significant digits from 10000 up', () => {
        expect(formatCount(10000)).toBe('10K');
        expect(formatCount(12345)).toBe('12.3K');
        expect(formatCount(19876)).toBe('19.9K');
        expect(formatCount(123456)).toBe('123K');
        expect(formatCount(1234567)).toBe('1.23M');
    });

    it('treats missing or non numeric values as zero', () => {
        expect(formatCount(undefined)).toBe('0');
        expect(formatCount(null)).toBe('0');
        expect(formatCount('not-a-number')).toBe('0');
        expect(formatCount('19876')).toBe('19.9K');
    });

    it('honours a caller supplied threshold', () => {
        expect(formatCount(1234567, { compactFrom: 1000 })).toBe('1.23M');
        expect(formatCount(19876, { compactFrom: Infinity })).toBe('19,876');
        // The abbreviation still has to save width: "5.21K" is exactly as wide
        // as "5,210", so the exact count wins.
        expect(formatCount(5210, { compactFrom: 1000 })).toBe('5,210');
    });

    it('follows the UI locale rather than the browser locale', () => {
        // Documents that the abbreviation itself is locale specific: Chinese
        // switches to 万 at the same threshold instead of K.
        i18n.currentLocale = 'zh-CN';
        expect(formatCount(9999)).toBe('9,999');
        expect(formatCount(19876)).toBe('1.99万');
    });

    it('keeps the exact count where the locale has no compact unit', () => {
        // German has no compact unit below a million: Intl would render 18,475
        // as the rounded plain number "18.500", which reads as exact but is not.
        i18n.currentLocale = 'de';
        expect(formatCount(18475)).toBe('18.475');
        // The tooltip is exact either way, it just repeats the same number here.
        expect(formatCountTitle('Flux.1 D', 18475)).toBe('Flux.1 D — 18.475 models');
        // From a million up German does have a unit, and it is shorter.
        // (Compared against Intl's own output: it uses a non-breaking space.)
        const compact = i18n.formatNumber(12345678, {
            notation: 'compact',
            maximumSignificantDigits: 3,
        });
        expect(formatCount(12345678)).toBe(compact);
        expect(compact.length).toBeLessThan(formatCountExact(12345678).length);
    });

    it('keeps the exact count where the locale abbreviation is wider', () => {
        // Russian "18,5 тыс." is wider than the exact "18 475", which defeats
        // the point of abbreviating; "1,23 млн" is genuinely shorter.
        i18n.currentLocale = 'ru';
        expect(formatCount(18475)).toBe(formatCountExact(18475));

        const compact = i18n.formatNumber(1234567, {
            notation: 'compact',
            maximumSignificantDigits: 3,
        });
        expect(formatCount(1234567)).toBe(compact);
        expect(compact.length).toBeLessThan(formatCountExact(1234567).length);
    });
});

describe('formatCountExact', () => {
    it('never abbreviates', () => {
        expect(formatCountExact(19876)).toBe('19,876');
        expect(formatCountExact(1234567)).toBe('1,234,567');
        expect(formatCountExact(undefined)).toBe('0');
    });
});

describe('formatCountTitle', () => {
    it('pairs the full name with the exact count at every magnitude', () => {
        // Set unconditionally: an affordance that only exists above a threshold
        // is undiscoverable, and the name is what CSS may have ellipsized.
        expect(formatCountTitle('character', 0)).toBe('character — 0 models');
        expect(formatCountTitle('character', 578)).toBe('character — 578 models');
        expect(formatCountTitle('character', 9999)).toBe('character — 9,999 models');
        expect(formatCountTitle('character', 10000)).toBe('character — 10,000 models');
        expect(formatCountTitle('character', 18475)).toBe('character — 18,475 models');
        // The rendered pill may say "18.5K"; the tooltip never abbreviates.
        expect(formatCountTitle('character', 18475)).not.toContain('18.5K');
    });

    it('uses the page specific sentence on the recipes page', () => {
        expect(formatCountTitle('Illustrious', 19876, 'recipes.filter.countTitle'))
            .toBe('Illustrious — 19,876 recipes');
    });
});
