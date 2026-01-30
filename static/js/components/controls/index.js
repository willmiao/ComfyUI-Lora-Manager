// Controls components index file
import { PageControls } from './PageControls.js';
import { LorasControls } from './LorasControls.js';
import { CheckpointsControls } from './CheckpointsControls.js';
import { EmbeddingsControls } from './EmbeddingsControls.js';
import { MiscControls } from './MiscControls.js';

// Export the classes
export { PageControls, LorasControls, CheckpointsControls, EmbeddingsControls, MiscControls };

/**
 * Factory function to create the appropriate controls based on page type
 * @param {string} pageType - The type of page ('loras', 'checkpoints', 'embeddings', or 'misc')
 * @returns {PageControls} - The appropriate controls instance
 */
export function createPageControls(pageType) {
    if (pageType === 'loras') {
        return new LorasControls();
    } else if (pageType === 'checkpoints') {
        return new CheckpointsControls();
    } else if (pageType === 'embeddings') {
        return new EmbeddingsControls();
    } else if (pageType === 'misc') {
        return new MiscControls();
    } else {
        console.error(`Unknown page type: ${pageType}`);
        return null;
    }
}