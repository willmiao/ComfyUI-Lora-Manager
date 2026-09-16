import { beforeEach, describe, expect, it, vi } from "vitest";

const {
    MODEL_TAGS_MODULE,
    I18N_HELPERS_MODULE,
    UI_HELPERS_MODULE,
    MODEL_API_MODULE,
    PRIORITY_TAGS_MODULE,
    STATE_MODULE,
    saveModelMetadataMock,
} = vi.hoisted(() => ({
    MODEL_TAGS_MODULE: new URL('../../../static/js/components/shared/ModelTags.js', import.meta.url).pathname,
    I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    MODEL_API_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    PRIORITY_TAGS_MODULE: new URL('../../../static/js/utils/priorityTagHelpers.js', import.meta.url).pathname,
    STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
    saveModelMetadataMock: vi.fn(),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
    translate: vi.fn((key, params, fallback) => fallback || key),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
    showToast: vi.fn(),
    copyToClipboard: vi.fn(),
}));

vi.mock(MODEL_API_MODULE, () => ({
    getModelApiClient: vi.fn(() => ({
        saveModelMetadata: saveModelMetadataMock,
    })),
}));

vi.mock(PRIORITY_TAGS_MODULE, () => ({
    getPriorityTagSuggestions: vi.fn(async () => []),
}));

vi.mock(STATE_MODULE, () => ({
    state: { currentPageType: 'loras' },
}));

const TAG_SECTION_HTML = (tags) => `
    <div class="model-tags-container">
        <div class="model-tags-header">
            <div class="model-tags-compact">
                ${tags.map((tag) => `<span class="model-tag-compact">${tag}</span>`).join('')}
            </div>
            <button class="edit-tags-btn" data-file-path="test.safetensors" title="Edit tags">
                <i class="fas fa-pencil-alt"></i>
            </button>
        </div>
        <div class="model-tags-tooltip">
            <div class="tooltip-content">
                ${tags.map((tag) => `<span class="tooltip-tag">${tag}</span>`).join('')}
            </div>
        </div>
    </div>
`;

describe("ModelTags reordering", () => {
    let setupTagEditMode;

    beforeEach(async () => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        saveModelMetadataMock.mockResolvedValue({});

        const module = await import(MODEL_TAGS_MODULE);
        setupTagEditMode = module.setupTagEditMode;
    });

    function section() {
        return document.querySelector('.model-tags-container');
    }

    function items() {
        return Array.from(document.querySelectorAll('.metadata-item'));
    }

    function order() {
        return items().map((item) => item.dataset.tag);
    }

    function handles() {
        return Array.from(document.querySelectorAll('.reorder-handle'));
    }

    function firePointer(type, target, init = {}) {
        target.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            ...init,
        }));
    }

    function dragToEnd(target) {
        firePointer('pointerdown', target, { clientY: 10 });
        firePointer('pointermove', target, { clientY: 999 });
        firePointer('pointerup', target, { clientY: 999 });
    }

    function pressKey(target, key, init = {}) {
        const event = new KeyboardEvent('keydown', {
            key,
            bubbles: true,
            cancelable: true,
            ...init,
        });
        target.dispatchEvent(event);
        return event;
    }

    async function enterEditMode(tags = ['alpha', 'beta', 'gamma']) {
        document.body.innerHTML = TAG_SECTION_HTML(tags);
        setupTagEditMode('loras');

        document.querySelector('.edit-tags-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        await vi.waitFor(() => {
            expect(document.querySelector('.metadata-edit-container')).toBeTruthy();
        });
    }

    it("renders a grip handle per tag and flags the section as sortable", async () => {
        await enterEditMode(['alpha', 'beta']);

        expect(items()).toHaveLength(2);
        expect(handles()).toHaveLength(2);
        expect(section().classList.contains('has-sortable-words')).toBe(true);
        expect(
            document.querySelector('.metadata-items').classList.contains('pointer-sort-enabled'),
        ).toBe(true);
    });

    it("does not offer reordering for a single tag", async () => {
        await enterEditMode(['alpha']);

        expect(handles()).toHaveLength(1);
        expect(section().classList.contains('has-sortable-words')).toBe(false);
    });

    it("keeps the whole chip draggable, not just the grip", async () => {
        await enterEditMode();

        // Drag from the chip body (no handle involved)
        dragToEnd(items()[0].querySelector('.metadata-item-content'));

        expect(order()).toEqual(['beta', 'gamma', 'alpha']);
    });

    it("reorders by dragging the grip", async () => {
        await enterEditMode();

        dragToEnd(handles()[0]);

        expect(order()).toEqual(['beta', 'gamma', 'alpha']);
    });

    it("does not reorder when the grip is only clicked", async () => {
        await enterEditMode();

        const handle = handles()[0];
        firePointer('pointerdown', handle, { clientY: 10 });
        firePointer('pointermove', handle, { clientY: 12 });
        firePointer('pointerup', handle, { clientY: 12 });

        expect(order()).toEqual(['alpha', 'beta', 'gamma']);
    });

    it("saves the new order after a keyboard reorder", async () => {
        await enterEditMode();

        pressKey(handles()[0], 'ArrowRight', { altKey: true });
        expect(order()).toEqual(['beta', 'alpha', 'gamma']);

        const liveRegion = section().querySelector('.reorder-live-region');
        expect(liveRegion.getAttribute('aria-live')).toBe('polite');
        expect(liveRegion.textContent).toBe('Moved to position 2 of 3');

        expect(handles()[0].getAttribute('aria-label'))
            .toBe('Reorder beta, position 1 of 3');

        document.querySelector('.save-tags-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        await vi.waitFor(() => {
            expect(saveModelMetadataMock).toHaveBeenCalled();
        });

        expect(saveModelMetadataMock).toHaveBeenCalledWith('test.safetensors', {
            tags: ['beta', 'alpha', 'gamma'],
        });
    });

    it("swallows the reorder shortcut at the ends of the list", async () => {
        await enterEditMode();

        const event = pressKey(handles()[0], 'ArrowLeft', { altKey: true });

        expect(event.defaultPrevented).toBe(true);
        expect(order()).toEqual(['alpha', 'beta', 'gamma']);
    });

    it("updates the sortable flag when tags are deleted", async () => {
        await enterEditMode(['alpha', 'beta']);

        items()[1].querySelector('.metadata-delete-btn')
            .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

        expect(order()).toEqual(['alpha']);
        expect(section().classList.contains('has-sortable-words')).toBe(false);
    });
});
