export class BaseContextMenu {
    constructor(menuId, cardSelector) {
        this.menu = document.getElementById(menuId);
        this.cardSelector = cardSelector;
        this.currentCard = null;
        this.submenuTimeout = null;
        this.openSubmenu = null;

        if (!this.menu) {
            console.error(`Context menu element with ID ${menuId} not found`);
            return;
        }

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

            // Ignore clicks on submenu trigger (has-submenu parent)
            if (menuItem.classList.contains('has-submenu')) return;

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
            submenu.classList.remove('flip-left');
        }
        if (this.openSubmenu === trigger) {
            this.openSubmenu = null;
        }
    }

    _positionSubmenu(submenu) {
        const submenuRect = submenu.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth;

        if (submenuRect.right > viewportWidth) {
            submenu.classList.add('flip-left');
        } else {
            submenu.classList.remove('flip-left');
        }
    }

    handleMenuAction(action, menuItem) {
        // Override in subclass
        console.warn('handleMenuAction not implemented');
    }

    showMenu(x, y, card) {
        this.currentCard = card;
        this.menu.style.display = 'block';

        // Get menu dimensions
        const menuRect = this.menu.getBoundingClientRect();

        // Get viewport dimensions
        const viewportWidth = document.documentElement.clientWidth;
        const viewportHeight = document.documentElement.clientHeight;

        // Calculate position
        let finalX = x;
        let finalY = y;

        // Ensure menu doesn't go offscreen right
        if (x + menuRect.width > viewportWidth) {
            finalX = x - menuRect.width;
        }

        // Ensure menu doesn't go offscreen bottom
        if (y + menuRect.height > viewportHeight) {
            finalY = y - menuRect.height;
        }

        // Position menu
        this.menu.style.left = `${finalX}px`;
        this.menu.style.top = `${finalY}px`;
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
