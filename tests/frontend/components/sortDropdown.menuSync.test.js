import { describe, it, beforeEach, expect } from 'vitest';
import { initSortDropdown } from '../../../static/js/components/controls/SortDropdown.js';

function renderSortDropdownDom() {
    document.body.innerHTML = `
    <div class="sort-dropdown-group">
      <select id="sortSelect">
        <option value="name:asc">Name Asc</option>
        <option value="name:desc">Name Desc</option>
        <option value="random" selected>Randomize (shuffle)</option>
      </select>
      <button class="sort-trigger" type="button">
        <span class="sort-trigger__label"></span>
      </button>
      <div class="sort-dropdown-menu"></div>
    </div>
  `;
    return {
        select: document.getElementById('sortSelect'),
        menu: document.querySelector('.sort-dropdown-menu'),
        label: document.querySelector('.sort-trigger__label'),
    };
}

describe('SortDropdown menu sync', () => {
    let select;
    let menu;
    let label;

    beforeEach(() => {
        ({ select, menu, label } = renderSortDropdownDom());
        initSortDropdown(select);
    });

    it('rebuilds the menu and highlights the selected item when an option value attribute changes', async () => {
        // The seeded Random option gets a new value each time it is picked.
        // The select's value getter follows the selected option's new value.
        const randomOpt = select.querySelector('option[value="random"]');
        randomOpt.value = 'random:abc123';
        await Promise.resolve();

        const items = [...menu.querySelectorAll('.sort-option')];
        expect(items.map((el) => el.dataset.value)).toContain('random:abc123');
        const seededItem = items.find((el) => el.dataset.value === 'random:abc123');
        expect(seededItem.classList.contains('is-selected')).toBe(true);
        expect(label.textContent).toBe('Randomize (shuffle)');
    });

    it('drops the stale seeded item and re-selects the plain random item when the option is reset', async () => {
        const randomOpt = select.querySelector('option[value="random"]');
        randomOpt.value = 'random:abc123';
        await Promise.resolve();

        // The rebuild must have happened: the seeded item is in the menu
        const seededItems = [...menu.querySelectorAll('.sort-option')]
            .filter((el) => el.dataset.value === 'random:abc123');
        expect(seededItems).toHaveLength(1);

        // PageControls resets the option to "random" when switching away
        randomOpt.value = 'random';
        await Promise.resolve();

        const items = [...menu.querySelectorAll('.sort-option')];
        expect(items.map((el) => el.dataset.value)).not.toContain('random:abc123');
        const randomItem = items.find((el) => el.dataset.value === 'random');
        expect(randomItem.classList.contains('is-selected')).toBe(true);
    });
});
