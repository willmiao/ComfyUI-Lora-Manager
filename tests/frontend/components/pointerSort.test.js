import { beforeEach, describe, expect, it } from "vitest";

const POINTER_SORT_MODULE = new URL(
    '../../../static/js/components/shared/pointerSort.js',
    import.meta.url,
).pathname;

describe("pointerSort", () => {
    let enablePointerSort;
    let disablePointerSort;
    let moveItemWithinContainer;

    beforeEach(async () => {
        document.body.innerHTML = '';
        const module = await import(POINTER_SORT_MODULE);
        enablePointerSort = module.enablePointerSort;
        disablePointerSort = module.disablePointerSort;
        moveItemWithinContainer = module.moveItemWithinContainer;
    });

    function buildList(words) {
        document.body.innerHTML = `
            <div class="list">
                ${words.map((word) => `
                    <div class="item" data-id="${word}">
                        <span class="handle">::</span>
                        <span class="label">${word}</span>
                    </div>
                `).join('')}
            </div>
        `;
        return {
            container: document.querySelector('.list'),
            items: Array.from(document.querySelectorAll('.item')),
        };
    }

    /**
     * Explicit class names so the assertions test the configurable engine
     * rather than the metadata-* defaults used by the tag editor.
     */
    function sortOptions(extra = {}) {
        return {
            itemSelector: '.item',
            draggingClass: 'item-dragging',
            placeholderClass: 'item-placeholder',
            containerSortingClass: 'list-sorting',
            bodySortingClass: 'drag-active',
            ...extra,
        };
    }

    function order() {
        return Array.from(document.querySelectorAll('.item')).map((el) => el.dataset.id);
    }

    function firePointer(type, target, init = {}) {
        target.dispatchEvent(new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            ...init,
        }));
    }

    /**
     * jsdom reports zero-sized rects for every element, which makes the engine
     * treat a high clientY as "past the last item".
     */
    function dragToEnd(target) {
        firePointer('pointerdown', target);
        firePointer('pointermove', target, { clientY: 999 });
        firePointer('pointerup', target, { clientY: 999 });
    }

    it("reorders items when the whole item is draggable", () => {
        const { container } = buildList(['a', 'b', 'c']);
        enablePointerSort(container, sortOptions());

        const first = document.querySelector('.item');
        dragToEnd(first);

        expect(order()).toEqual(['b', 'c', 'a']);
    });

    it("keeps the metadata-* defaults the tag editor relies on", () => {
        document.body.innerHTML = `
            <div class="metadata-items">
                <div class="metadata-item" data-id="a">a</div>
                <div class="metadata-item" data-id="b">b</div>
            </div>
        `;
        const container = document.querySelector('.metadata-items');

        // No options at all: ModelTags.js calls the engine exactly like this
        enablePointerSort(container);

        const first = container.querySelector('.metadata-item');
        firePointer('pointerdown', first);
        firePointer('pointermove', first, { clientY: 999 });
        firePointer('pointerup', first, { clientY: 999 });

        expect(
            Array.from(container.querySelectorAll('.metadata-item')).map((el) => el.dataset.id),
        ).toEqual(['b', 'a']);
        expect(container.classList.contains('pointer-sort-enabled')).toBe(true);
        expect(document.querySelector('.reorder-placeholder')).toBeNull();
    });

    it("only starts a drag from the configured handle", () => {
        const { container } = buildList(['a', 'b', 'c']);
        enablePointerSort(container, sortOptions({ handleSelector: '.handle' }));

        // Pressing the item body must not start a drag
        dragToEnd(document.querySelector('.item .label'));
        expect(order()).toEqual(['a', 'b', 'c']);
        expect(document.querySelector('.item-dragging')).toBeNull();

        // Pressing the handle does
        dragToEnd(document.querySelector('.item .handle'));
        expect(order()).toEqual(['b', 'c', 'a']);
    });

    it("never drags items matching the blocked selector or the ignore selector", () => {
        const { container } = buildList(['a', 'b']);
        enablePointerSort(container, sortOptions({ blockedItemSelector: '.locked' }));

        document.querySelector('.item').classList.add('locked');
        dragToEnd(document.querySelector('.item'));
        expect(order()).toEqual(['a', 'b']);

        document.querySelector('.item').classList.remove('locked');
        enablePointerSort(container, sortOptions({ ignoreSelector: '.label' }));
        dragToEnd(document.querySelector('.item .label'));
        expect(order()).toEqual(['a', 'b']);
    });

    it("waits for the drag threshold before lifting an item", () => {
        const { container } = buildList(['a', 'b']);
        enablePointerSort(container, sortOptions({ dragThreshold: 10 }));

        const first = document.querySelector('.item');
        firePointer('pointerdown', first, { clientX: 10, clientY: 10 });

        firePointer('pointermove', first, { clientX: 15, clientY: 10 });
        expect(document.querySelector('.item-dragging')).toBeNull();

        firePointer('pointermove', first, { clientX: 60, clientY: 10 });
        expect(document.querySelector('.item-dragging')).not.toBeNull();

        firePointer('pointerup', first, { clientX: 60, clientY: 10 });
        expect(order()).toEqual(['b', 'a']);
    });

    it("calls onSorted once a drop completes", () => {
        const { container } = buildList(['a', 'b']);
        const onSorted = [];
        enablePointerSort(container, sortOptions({
            onSorted: (item) => onSorted.push(item.dataset.id),
        }));

        dragToEnd(document.querySelector('.item'));
        expect(onSorted).toEqual(['a']);
    });

    it("stops handling drags after disablePointerSort", () => {
        const { container } = buildList(['a', 'b']);
        enablePointerSort(container, sortOptions());

        disablePointerSort(container, sortOptions());
        dragToEnd(document.querySelector('.item'));

        expect(order()).toEqual(['a', 'b']);
    });

    it("moveItemWithinContainer moves items within bounds only", () => {
        const { container } = buildList(['a', 'b', 'c']);
        const items = Array.from(document.querySelectorAll('.item'));

        expect(moveItemWithinContainer(items[0], 1, sortOptions()))
            .toEqual({ index: 1, total: 3 });
        expect(order()).toEqual(['b', 'a', 'c']);

        expect(moveItemWithinContainer(items[2], -1, sortOptions()))
            .toEqual({ index: 1, total: 3 });
        expect(order()).toEqual(['b', 'c', 'a']);

        // Out of range / unknown item moves are refused
        const currentFirst = document.querySelector('.item');
        expect(moveItemWithinContainer(currentFirst, -1, sortOptions())).toBeNull();
        expect(moveItemWithinContainer(currentFirst, 3, sortOptions())).toBeNull();
        expect(moveItemWithinContainer(document.createElement('div'), 1, {
            ...sortOptions(),
            container,
        })).toBeNull();
    });
});
