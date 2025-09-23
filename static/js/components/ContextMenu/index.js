export { LoraContextMenu } from './LoraContextMenu.js';
export { RecipeContextMenu } from './RecipeContextMenu.js';
export { CheckpointContextMenu } from './CheckpointContextMenu.js';
export { EmbeddingContextMenu } from './EmbeddingContextMenu.js';
export { GlobalContextMenu } from './GlobalContextMenu.js';
export { ModelContextMenuMixin } from './ModelContextMenuMixin.js';

import { LoraContextMenu } from './LoraContextMenu.js';
import { RecipeContextMenu } from './RecipeContextMenu.js';
import { CheckpointContextMenu } from './CheckpointContextMenu.js';
import { EmbeddingContextMenu } from './EmbeddingContextMenu.js';
import { GlobalContextMenu } from './GlobalContextMenu.js';

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

export function createGlobalContextMenu() {
    return new GlobalContextMenu();
}