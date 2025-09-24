import { renderTemplate } from './domFixtures.js';

/**
 * Renders the LoRAs page template with expected dataset attributes.
 * @returns {Element}
 */
export function renderLorasPage() {
  return renderTemplate('loras.html', {
    dataset: {
      page: 'loras',
    },
  });
}

/**
 * Renders the Checkpoints page template with expected dataset attributes.
 * @returns {Element}
 */
export function renderCheckpointsPage() {
  return renderTemplate('checkpoints.html', {
    dataset: {
      page: 'checkpoints',
    },
  });
}
