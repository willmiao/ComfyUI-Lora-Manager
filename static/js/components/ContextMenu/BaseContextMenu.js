import { positionFixedMenu, positionSubmenu } from '../../utils/menuPosition.js';
import { closeContextMenus, registerContextMenuCloser } from '../../utils/contextMenuCoordinator.js';

export class BaseContextMenu {
    constructor(menuId, cardSelector) {
        this.menu = document.getElementById(menuId);
        this.menuId = menuId;
        this.cardSelector = cardSelector;
        this.currentCard = null;
        this.submenuTimeout = null;
        this.openSubmenu = null;

        if (!this.menu) {
            console.error(`Context menu element with ID ${menuId} not found`);
            return;
        }

        // Nothing else may stay open while this menu is visible (another page
        // menu or a sidebar menu).
        registerContextMenuCloser(menuId, () => this.hideMenu());

        this.init();
    }

    init() {
        // Hide menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.menu.contains(e.target)) {
                this.hideMenu();
            }
        });

        // Handle menu item clicks (including submenu items)
        this.menu.addEventListener('click', (e) => {
            const menuItem = e.target.closest('.context-menu-item');
            if (!menuItem || !this.currentCard) return;

            // Ignore clicks on submenu trigger (has-submenu parent) or disabled items
            if (menuItem.classList.contains('has-submenu')) return;
            if (menuItem.classList.contains('disabled')) return;

            const action = menuItem.dataset.action;
            if (!action) return;

            this.handleMenuAction(action, menuItem);
            this.hideMenu();
        });

        // Submenu hover handling
        // Use mouseover/mouseout (which bubble) with relatedTarget checks
        // to reliably detect crossing the .has-submenu boundary
        this.menu.addEventListener('mouseover', (e) => {
            const trigger = e.target.closest('.has-submenu');
            if (!trigger) return;

            // Only act when entering from outside this trigger's tree
            if (e.relatedTarget && trigger.contains(e.relatedTarget)) return;

            this._openSubmenu(trigger);
        });

        this.menu.addEventListener('mouseout', (e) => {
            const trigger = e.target.closest('.has-submenu');
            if (!trigger) return;

            // Only close when leaving the trigger's tree entirely
            if (e.relatedTarget && trigger.contains(e.relatedTarget)) return;

            this._scheduleSubmenuClose(trigger);
        });
    }

    _openSubmenu(trigger) {
        // Clear any pending close
        if (this.submenuTimeout) {
            clearTimeout(this.submenuTimeout);
            this.submenuTimeout = null;
        }

        // Hide any previously open submenu
        if (this.openSubmenu && this.openSubmenu !== trigger) {
            this._hideSubmenu(this.openSubmenu);
        }

        const submenu = trigger.querySelector('.context-submenu');
        if (!submenu) return;

        submenu.style.display = 'block';
        this.openSubmenu = trigger;
        this._positionSubmenu(submenu);
    }

    _scheduleSubmenuClose(trigger) {
        this.submenuTimeout = setTimeout(() => {
            this._hideSubmenu(trigger);
            this.submenuTimeout = null;
        }, 250);
    }

    _hideSubmenu(trigger) {
        const submenu = trigger.querySelector('.context-submenu');
        if (submenu) {
            submenu.style.display = 'none';
            submenu.style.top = '';
            submenu.style.maxHeight = '';
            submenu.style.overflowY = '';
            submenu.classList.remove('flip-left');
        }
        if (this.openSubmenu === trigger) {
            this.openSubmenu = null;
        }
    }

    _positionSubmenu(submenu) {
        positionSubmenu(submenu);
    }

    handleMenuAction(action, menuItem) {
        // Override in subclass
        console.warn('handleMenuAction not implemented');
    }

    /**
     * Hook for subclasses whose entries depend on the right-clicked card
     * (excluded state, AI enrichment availability, missing-LoRA entry, ...).
     *
     * Runs while the menu is displayed but before it is measured, so entries
     * toggled or re-labelled here are accounted for when the menu is placed
     * against the viewport. Doing this after `showMenu` meant the flip decision
     * used the height of the *previous* menu content.
     */
    prepareMenu(card) { }

    showMenu(x, y, card) {
        // Context menus are mutually exclusive: drop whatever is open (another
        // page menu or a sidebar menu) before showing this one.
        closeContextMenus(this.menuId);

        this.currentCard = card;
        this.menu.style.display = 'block';
        this.prepareMenu(card);
        positionFixedMenu(this.menu, x, y);
    }

    hideMenu() {
        if (this.submenuTimeout) {
            clearTimeout(this.submenuTimeout);
            this.submenuTimeout = null;
        }
        if (this.openSubmenu) {
            this._hideSubmenu(this.openSubmenu);
        }
        if (this.menu) {
            this.menu.style.display = 'none';
        }
        this.currentCard = null;
    }
}
