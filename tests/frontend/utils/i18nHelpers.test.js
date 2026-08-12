import { describe, it, afterEach, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { translate } from '../../../static/js/utils/i18nHelpers.js';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');

/**
 * Real en.json translations backed by a minimal `window.i18n` stub that mirrors
 * the nested lookup + {param} interpolation of static/js/i18n/index.js, so the
 * assertions exercise actual key resolution rather than key presence.
 */
const loadEnTranslations = () =>
    JSON.parse(readFileSync(resolve(repoRoot, 'locales/en.json'), 'utf8'));

const installWindowI18n = () => {
    const translations = loadEnTranslations();

    const interpolate = (str, params) =>
        str.replace(/\{\{?(\w+)\}?\}/g, (match, key) =>
            params[key] !== undefined ? params[key] : match,
        );

    window.i18n = {
        t: (key, params = {}) => {
            const keys = key.split('.');
            let value = translations;
            for (const k of keys) {
                if (value && typeof value === 'object' && k in value) {
                    value = value[k];
                } else {
                    console.warn(`Translation key not found: ${key}`);
                    return key;
                }
            }
            if (typeof value !== 'string') {
                console.warn(`Translation key is not a string: ${key}`);
                return key;
            }
            return interpolate(value, params);
        },
        getCurrentLocale: () => 'en',
    };
};

afterEach(() => {
    delete window.i18n;
});

describe('translate() with real en.json locale', () => {
    it('resolves undo toast keys with interpolation', () => {
        installWindowI18n();

        expect(translate('toast.undo.deleted', { name: 'x' })).toBe('Deleted x');
        expect(translate('toast.undo.deletedBulk', { count: 3 })).toBe('Deleted 3 item(s)');
        expect(translate('toast.undo.action')).toBe('Undo');
        expect(translate('toast.undo.restored')).toBe('Item restored');
        expect(translate('toast.undo.expired')).toBe(
            'Undo window expired. The item was permanently deleted.',
        );
        expect(translate('toast.undo.failed', { error: 'boom' })).toBe('Undo failed: boom');
    });

    it('resolves delete-model modal keys with interpolation', () => {
        installWindowI18n();

        expect(translate('modals.deleteModel.recoverableWarning')).toBe(
            'This will permanently delete the file after 30 seconds unless you undo.',
        );
        expect(translate('modals.deleteModel.freesSpace', { size: '1.2 MB' })).toBe(
            'Frees 1.2 MB',
        );
    });

    it('returns the raw key when no translation exists (fallback contract)', () => {
        installWindowI18n();
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

        expect(translate('toast.undo.nonExistentKey')).toBe('toast.undo.nonExistentKey');

        warnSpy.mockRestore();
    });
});
