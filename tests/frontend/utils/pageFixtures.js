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

/**
 * Renders the Embeddings page template with expected dataset attributes.
 * @returns {Element}
 */
export function renderEmbeddingsPage() {
  return renderTemplate('embeddings.html', {
    dataset: {
      page: 'embeddings',
    },
  });
}

/**
 * Renders the Other Models page template with expected dataset attributes.
 * @returns {Element}
 */
export function renderOtherPage() {
  return renderTemplate('other.html', {
    dataset: {
      page: 'other',
    },
  });
}

/**
 * Renders the Recipes page template with expected dataset attributes.
 * @returns {Element}
 */
export function renderRecipesPage() {
  return renderTemplate('recipes.html', {
    dataset: {
      page: 'recipes',
    },
  });
}
