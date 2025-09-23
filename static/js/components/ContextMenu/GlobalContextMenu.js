import { BaseContextMenu } from './BaseContextMenu.js';

export class GlobalContextMenu extends BaseContextMenu {
    constructor() {
        super('globalContextMenu');
    }

    showMenu(x, y) {
        super.showMenu(x, y, null);
    }

    handleMenuAction(action, menuItem) {
        switch (action) {
            case 'placeholder-one':
            case 'placeholder-two':
            case 'placeholder-three':
                console.info(`Global context menu action triggered: ${action}`);
                break;
            default:
                console.warn(`Unhandled global context menu action: ${action}`);
                break;
        }
    }
}
