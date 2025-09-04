export { LoraContextMenu } from './LoraContextMenu.js';
export { RecipeContextMenu } from './RecipeContextMenu.js';
export { CheckpointContextMenu } from './CheckpointContextMenu.js';
export { EmbeddingContextMenu } from './EmbeddingContextMenu.js';
export { ModelContextMenuMixin } from './ModelContextMenuMixin.js';

import { LoraContextMenu } from './LoraContextMenu.js';
import { RecipeContextMenu } from './RecipeContextMenu.js';
import { CheckpointContextMenu } from './CheckpointContextMenu.js';
import { EmbeddingContextMenu } from './EmbeddingContextMenu.js';
import { state } from '../../state/index.js';

// Factory method to create page-specific context menu instances
export function createPageContextMenu(pageType) {
    switch (pageType) {
        case 'loras':
            return new LoraContextMenu();
        case 'recipes':
            return new RecipeContextMenu();
        case 'checkpoints':
            return new CheckpointContextMenu();
        case 'embeddings':
            return new EmbeddingContextMenu();
        default:
            return null;
    }
}

// Initialize context menu coordination for pages that support it
export function initializeContextMenuCoordination(pageContextMenu, bulkContextMenu) {
    // Centralized context menu event handler
    document.addEventListener('contextmenu', (e) => {
        const card = e.target.closest('.model-card');
        if (!card) {
            // Hide all menus if not right-clicking on a card
            pageContextMenu?.hideMenu();
            bulkContextMenu?.hideMenu();
            return;
        }
        
        e.preventDefault();
        
        // Hide all menus first
        pageContextMenu?.hideMenu();
        bulkContextMenu?.hideMenu();
        
        // Determine which menu to show based on bulk mode and selection state
        if (state.bulkMode && card.classList.contains('selected')) {
            // Show bulk menu for selected cards in bulk mode
            bulkContextMenu?.showMenu(e.clientX, e.clientY, card);
        } else if (!state.bulkMode) {
            // Show regular menu when not in bulk mode
            pageContextMenu?.showMenu(e.clientX, e.clientY, card);
        }
        // Don't show any menu for unselected cards in bulk mode
    });
}