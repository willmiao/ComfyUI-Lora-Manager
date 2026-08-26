import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'fs';
import path from 'path';

// Regression guard: every `.modal` element shipped via components/modals.html
// must be registered in ModalManager.initialize(). An unregistered modal makes
// modalManager.showModal(id) silently no-op (see getModal returning undefined),
// which manifests as "clicking the menu item does nothing" with no console
// error — exactly the Link-to-CivitArchive bug this file guards against.
describe('ModalManager registry parity', () => {
  const repoRoot = path.resolve(__dirname, '../../..');
  const modalsHtml = readFileSync(
    path.join(repoRoot, 'templates/components/modals.html'),
    'utf-8'
  );
  const modalManagerSrc = readFileSync(
    path.join(repoRoot, 'static/js/managers/ModalManager.js'),
    'utf-8'
  );

  const collectModalIds = (target, seen = new Set()) => {
    if (statSync(target).isFile()) {
      extractIds(readFileSync(target, 'utf-8'), seen);
      return seen;
    }
    for (const entry of readdirSync(target, { withFileTypes: true })) {
      collectModalIds(path.join(target, entry.name), seen);
    }
    return seen;
  };

  const extractIds = (content, seen) => {
    for (const match of content.matchAll(/id="([A-Za-z][\w-]*)"[^>]*class="modal"/g)) {
      seen.add(match[1]);
    }
  };

  it('registers every modal declared in templates', () => {
    const includeFiles = [
      ...modalsHtml.matchAll(/\{%\s*include\s*'([^']+\.html)'\s*%\}/g),
    ].map((m) => m[1]);

    expect(includeFiles.length).toBeGreaterThan(0);

    const declaredIds = new Set();
    for (const relPath of includeFiles) {
      collectModalIds(path.join(repoRoot, 'templates', relPath), declaredIds);
    }

    expect(declaredIds.size).toBeGreaterThan(0);

    const unregistered = [...declaredIds].filter(
      (id) => !modalManagerSrc.includes(`registerModal('${id}'`)
    );

    expect(
      unregistered,
      'Modal ids rendered on pages but never registered in ModalManager.initialize() — showModal() will silently do nothing for them'
    ).toEqual([]);
  });
});
