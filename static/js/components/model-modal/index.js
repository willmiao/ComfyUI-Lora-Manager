/**
 * Model Modal - New Split-View Overlay Design
 * Phase 1 Implementation
 */

import { ModelModal } from './ModelModal.js';

// Export the public API
export const modelModal = {
  show: ModelModal.show.bind(ModelModal),
  close: ModelModal.close.bind(ModelModal),
  isOpen: ModelModal.isOpen.bind(ModelModal),
};

// Default export for convenience
export default modelModal;
