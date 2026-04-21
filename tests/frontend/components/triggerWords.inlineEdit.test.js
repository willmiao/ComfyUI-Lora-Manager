import { beforeEach, describe, expect, it, vi } from "vitest";

const {
    TRIGGER_WORDS_MODULE,
    I18N_HELPERS_MODULE,
    UI_HELPERS_MODULE,
} = vi.hoisted(() => ({
    TRIGGER_WORDS_MODULE: new URL('../../../static/js/components/shared/TriggerWords.js', import.meta.url).pathname,
    I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
    translate: vi.fn((key, params, fallback) => fallback || key),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
    showToast: vi.fn(),
    copyToClipboard: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    getModelApiClient: vi.fn(() => ({
        saveModelMetadata: vi.fn(),
    })),
}));

describe("TriggerWords inline editing", () => {
    let renderTriggerWords;
    let setupTriggerWordsEditMode;
    let showToast;
    let copyToClipboard;

    beforeEach(async () => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        global.fetch = vi.fn(async () => ({
            json: async () => ({
                success: true,
                trained_words: [],
                class_tokens: null,
            }),
        }));

        const module = await import(TRIGGER_WORDS_MODULE);
        const uiHelpers = await import(UI_HELPERS_MODULE);
        renderTriggerWords = module.renderTriggerWords;
        setupTriggerWordsEditMode = module.setupTriggerWordsEditMode;
        showToast = uiHelpers.showToast;
        copyToClipboard = uiHelpers.copyToClipboard;
    });

    async function enterEditMode(words = ["alpha", "beta"]) {
        document.body.innerHTML = renderTriggerWords(words, "test.safetensors");
        setupTriggerWordsEditMode();

        document.querySelector('.edit-trigger-words-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        await vi.waitFor(() => {
            expect(document.querySelector('.metadata-suggestions-dropdown')).toBeTruthy();
        });
    }

    function editFirstTag(nextValue, key = 'Enter') {
        const firstTag = document.querySelector('.trigger-word-tag');
        firstTag.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        const input = firstTag.querySelector('.trigger-word-edit-input');
        input.value = nextValue;
        input.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));

        return firstTag;
    }

    it("updates an existing trigger word in place", async () => {
        await enterEditMode();

        const firstTag = editFirstTag("gamma");

        expect(firstTag.dataset.word).toBe("gamma");
        expect(firstTag.querySelector('.trigger-word-content').textContent).toBe("gamma");
        expect(document.querySelector('.trigger-word-edit-input')).toBeNull();
    });

    it("enters edit mode and edits the double-clicked tag from display mode without copying", async () => {
        document.body.innerHTML = renderTriggerWords(["alpha", "beta"], "test.safetensors");
        setupTriggerWordsEditMode();

        const firstTag = document.querySelector('.trigger-word-tag');
        firstTag.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        firstTag.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        firstTag.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));

        await vi.waitFor(() => {
            expect(document.querySelector('.trigger-words').classList.contains('edit-mode')).toBe(true);
            expect(firstTag.querySelector('.trigger-word-edit-input')).toBeTruthy();
        });

        await new Promise(resolve => setTimeout(resolve, 260));
        expect(copyToClipboard).not.toHaveBeenCalled();
    });

    it("keeps the original word and shows a toast when editing to a duplicate", async () => {
        await enterEditMode();

        const firstTag = editFirstTag("beta");

        expect(firstTag.dataset.word).toBe("alpha");
        expect(firstTag.querySelector('.trigger-word-content').textContent).toBe("alpha");
        expect(showToast).toHaveBeenCalledWith('toast.triggerWords.alreadyExists', {}, 'error');
    });

    it("restores the original value when Escape is pressed", async () => {
        await enterEditMode();

        const firstTag = editFirstTag("gamma", "Escape");

        expect(firstTag.dataset.word).toBe("alpha");
        expect(firstTag.querySelector('.trigger-word-content').textContent).toBe("alpha");
    });

    it("preserves the current tag dimensions while editing long trigger words", async () => {
        await enterEditMode(["alpha beta gamma delta epsilon zeta eta theta"]);

        const firstTag = document.querySelector('.trigger-word-tag');
        vi.spyOn(firstTag, 'getBoundingClientRect').mockReturnValue({
            width: 320,
            height: 44,
            top: 0,
            right: 320,
            bottom: 44,
            left: 0,
            x: 0,
            y: 0,
            toJSON: () => ({}),
        });

        firstTag.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        const editor = firstTag.querySelector('.trigger-word-edit-input');
        expect(editor.tagName).toBe('TEXTAREA');
        expect(firstTag.style.getPropertyValue('--trigger-word-edit-width')).toBe('320px');
        expect(firstTag.style.getPropertyValue('--trigger-word-edit-height')).toBe('44px');
    });

    it("restores all original trigger words when edit mode is canceled", async () => {
        await enterEditMode();
        editFirstTag("gamma");

        document.querySelector('.edit-trigger-words-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        const words = Array.from(document.querySelectorAll('.trigger-word-tag'))
            .map(tag => tag.dataset.word);
        expect(words).toEqual(["alpha", "beta"]);
    });
});
