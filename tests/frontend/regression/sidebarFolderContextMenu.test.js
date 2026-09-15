import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import path from 'path';

// Regression guard for the sidebar folder context-menu layout: the update check
// sits on top, the folder operations form a single group, and the destructive
// entry stays last behind its own divider. SidebarManager gates those groups
// per page and collapses the dividers when a group is hidden, so a reorder here
// also changes what the recipes page shows.
describe('Sidebar folder context menu layout', () => {
  const repoRoot = path.resolve(__dirname, '../../..');
  const html = readFileSync(
    path.join(repoRoot, 'templates/components/context_menu.html'),
    'utf-8'
  );

  const menuHtml = html.slice(
    html.indexOf('id="sidebarFolderContextMenu"'),
    html.indexOf('<!-- Sidebar View Options Menu -->')
  );

  const sequence = [...menuHtml.matchAll(/<div class="([^"]+)"([^>]*)>/g)].map(([, classes, rest]) => {
    if (classes.includes('context-menu-separator')) return 'separator';
    return /data-action="([^"]+)"/.exec(rest)?.[1] || null;
  });

  it('keeps the update check first and the folder operations grouped', () => {
    expect(sequence).toEqual([
      'check-folder-updates',
      'separator',
      'create-subfolder',
      'rename-folder',
      'separator',
      'delete-folder',
    ]);
  });

  it('keeps the destructive entry last and visually marked', () => {
    const deleteEntry = menuHtml.match(/<div class="([^"]*)"\s+data-action="delete-folder"/);
    expect(deleteEntry).not.toBeNull();
    expect(deleteEntry[1]).toContain('delete-item');
    expect(sequence[sequence.length - 1]).toBe('delete-folder');
  });
});
