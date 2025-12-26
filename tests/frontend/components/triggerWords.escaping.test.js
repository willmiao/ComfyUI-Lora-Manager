import { describe, it, expect, beforeEach, vi } from "vitest";

const {
    TRIGGER_WORDS_MODULE,
    UTILS_MODULE,
    I18N_HELPERS_MODULE,
} = vi.hoisted(() => ({
    TRIGGER_WORDS_MODULE: new URL('../../../static/js/components/shared/TriggerWords.js', import.meta.url).pathname,
    UTILS_MODULE: new URL('../../../static/js/components/shared/utils.js', import.meta.url).pathname,
    I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
    translate: vi.fn((key, params, fallback) => fallback || key),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
    copyToClipboard: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    getModelApiClient: vi.fn(),
}));

describe("TriggerWords HTML Escaping", () => {
    let renderTriggerWords;

    beforeEach(async () => {
        document.body.innerHTML = '';
        const module = await import(TRIGGER_WORDS_MODULE);
        renderTriggerWords = module.renderTriggerWords;
    });

    it("escapes HTML tags in trigger words rendering", () => {
        const words = ["<style>guangying</style>", "fym <artist>"];
        const html = renderTriggerWords(words, "test.safetensors");

        expect(html).toContain("&lt;style&gt;guangying&lt;/style&gt;");
        expect(html).toContain("fym &lt;artist&gt;");
        expect(html).not.toContain("<style>guangying</style>");
    });

    it("uses dataset for copyTriggerWord to safely handle special characters", () => {
        const words = ["word'with'quotes", "<tag>"];
        const html = renderTriggerWords(words, "test.safetensors");

        // Check for dataset-word attribute
        expect(html).toContain('data-word="word&#39;with&#39;quotes"');
        expect(html).toContain('data-word="&lt;tag&gt;"');

        // Check for the onclick handler
        expect(html).toContain('onclick="copyTriggerWord(this.dataset.word)"');
    });
});
