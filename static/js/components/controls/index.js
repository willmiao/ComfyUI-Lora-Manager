// Controls components index file
import { PageControls } from './PageControls.js';
import { LorasControls } from './LorasControls.js';
import { CheckpointsControls } from './CheckpointsControls.js';
import { EmbeddingsControls } from './EmbeddingsControls.js';
import { OtherControls } from './OtherControls.js';
import { WorkflowControls } from './WorkflowControls.js';

// Export the classes
export { PageControls, LorasControls, CheckpointsControls, EmbeddingsControls, OtherControls, WorkflowControls };

/**
 * Factory function to create the appropriate controls based on page type
 * @param {string} pageType - The type of page ('loras', 'checkpoints', 'embeddings', 'other', or 'workflows')
 * @returns {PageControls} - The appropriate controls instance
 */
export function createPageControls(pageType) {
    if (pageType === 'loras') {
        return new LorasControls();
    } else if (pageType === 'checkpoints') {
        return new CheckpointsControls();
    } else if (pageType === 'embeddings') {
        return new EmbeddingsControls();
    } else if (pageType === 'other') {
        return new OtherControls();
    } else if (pageType === 'workflows') {
        return new WorkflowControls();
    } else {
        console.error(`Unknown page type: ${pageType}`);
        return null;
    }
}
