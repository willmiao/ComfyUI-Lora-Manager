import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as storageHelpers from '../../../static/js/utils/storageHelpers.js';

const {
    getStorageItem,
    setStorageItem,
    removeStorageItem,
    getSessionItem,
    setSessionItem,
    removeSessionItem,
} = storageHelpers;

const createFakeStorage = () => {
    const store = new Map();
    return {
        getItem: vi.fn((key) => (store.has(key) ? store.get(key) : null)),
        setItem: vi.fn((key, value) => {
            store.set(key, value);
        }),
        removeItem: vi.fn((key) => {
            store.delete(key);
        }),
        clear: vi.fn(() => {
            store.clear();
        }),
        key: vi.fn((index) => Array.from(store.keys())[index] ?? null),
        get length() {
            return store.size;
        },
        _store: store
    };
};

let localStorageMock;
let sessionStorageMock;
let consoleLogMock;

beforeEach(() => {
    localStorageMock = createFakeStorage();
    sessionStorageMock = createFakeStorage();
    vi.stubGlobal('localStorage', localStorageMock);
    vi.stubGlobal('sessionStorage', sessionStorageMock);
    consoleLogMock = vi.spyOn(console, 'log').mockImplementation(() => {});
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('storageHelpers namespace utilities', () => {
    it('returns parsed JSON for prefixed localStorage items', () => {
        localStorage.setItem('lora_manager_preferences', JSON.stringify({ theme: 'dark' }));

        const result = getStorageItem('preferences');

        expect(result).toEqual({ theme: 'dark' });
        expect(localStorage.getItem).toHaveBeenCalledWith('lora_manager_preferences');
    });

    it('falls back to legacy keys and migrates them to the namespace', () => {
        localStorage.setItem('legacy_key', 'value');

        const value = getStorageItem('legacy_key');

        expect(value).toBe('value');
        expect(localStorage.getItem('lora_manager_legacy_key')).toBe('value');
    });

    it('serializes objects when setting prefixed localStorage values', () => {
        const data = { ids: [1, 2, 3] };

        setStorageItem('data', data);

        expect(localStorage.setItem).toHaveBeenCalledWith('lora_manager_data', JSON.stringify(data));
        expect(localStorage.getItem('lora_manager_data')).toEqual(JSON.stringify(data));
    });

    it('removes both prefixed and legacy localStorage entries', () => {
        localStorage.setItem('lora_manager_temp', '123');
        localStorage.setItem('temp', '456');

        removeStorageItem('temp');

        expect(localStorage.getItem('lora_manager_temp')).toBeNull();
        expect(localStorage.getItem('temp')).toBeNull();
    });

    it('returns parsed JSON for session storage items', () => {
        sessionStorage.setItem('lora_manager_session', JSON.stringify({ page: 'loras' }));

        const session = getSessionItem('session');

        expect(session).toEqual({ page: 'loras' });
    });

    it('stores primitives in session storage directly', () => {
        setSessionItem('token', 'abc123');

        expect(sessionStorage.setItem).toHaveBeenCalledWith('lora_manager_token', 'abc123');
        expect(sessionStorage.getItem('lora_manager_token')).toBe('abc123');
    });

    it('removes session storage entries by namespace', () => {
        sessionStorage.setItem('lora_manager_flag', '1');

        removeSessionItem('flag');

        expect(sessionStorage.getItem('lora_manager_flag')).toBeNull();
    });
});
