import fs from 'node:fs';
import path from 'node:path';

const TEMPLATE_ROOT = path.resolve(process.cwd(), 'templates');

/**
 * Reads an HTML template from the templates directory and returns its markup.
 * @param {string} relativePath - Path relative to the templates directory.
 * @returns {string}
 */
export function readTemplate(relativePath) {
  const filePath = path.join(TEMPLATE_ROOT, relativePath);
  return fs.readFileSync(filePath, 'utf-8');
}

/**
 * Injects the provided HTML markup into the supplied container (defaults to document.body).
 * @param {string} html
 * @param {Element} [container=document.body]
 * @returns {Element}
 */
export function mountMarkup(html, container = document.body) {
  container.innerHTML = html;
  return container;
}

/**
 * Loads a template file and mounts it into the DOM, returning the container used.
 * @param {string} relativePath - Template path relative to templates directory.
 * @param {{
 *   container?: Element,
 *   dataset?: Record<string, string>,
 *   beforeMount?: (options: { container: Element }) => void,
 *   afterMount?: (options: { container: Element }) => void
 * }} [options]
 * @returns {Element}
 */
export function renderTemplate(relativePath, options = {}) {
  const { container = document.body, dataset = {}, beforeMount, afterMount } = options;
  if (beforeMount) {
    beforeMount({ container });
  }

  const html = readTemplate(relativePath);
  const target = mountMarkup(html, container);

  Object.entries(dataset).forEach(([key, value]) => {
    target.dataset[key] = value;
  });

  if (afterMount) {
    afterMount({ container: target });
  }

  return target;
}

/**
 * Utility to reset the DOM to a clean state. Useful when tests modify the structure
 * beyond what the shared Vitest setup clears.
 * @param {Element} [container=document.body]
 */
export function resetDom(container = document.body) {
  container.innerHTML = '';
  if (container === document.body) {
    document.body.removeAttribute('data-page');
  }
}
