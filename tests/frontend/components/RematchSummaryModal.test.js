import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => {
  if (typeof fallback === 'string') {
    // Apply {param} interpolation so counts remain assertable.
    return Object.entries(params || {}).reduce(
      (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
      fallback
    );
  }
  return key;
});

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

async function getShowRematchSummary() {
  const { showRematchSummary } = await import(
    '../../../static/js/components/RematchSummaryModal.js'
  );
  return showRematchSummary;
}

const L4_LORA = { recipe_id: 'r1', type: 'lora', entry: 'old.safetensors', file_name: 'new.safetensors', lora_index: 2 };
const L4_CHECKPOINT = { recipe_id: 'r2', type: 'checkpoint', entry: 'cp-old', file_name: 'cp-new.safetensors' };

describe('RematchSummaryModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
    global.fetch = vi.fn();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete global.fetch;
    delete navigator.clipboard;
    vi.restoreAllMocks();
  });

  it('renders a success header when everything matched cleanly', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({ scope: 'global', total: 10, matchedRecipes: 2, matchedEntries: 3 });

    const modal = document.getElementById('rematchSummaryModal');
    expect(modal).not.toBeNull();
    expect(modal.querySelector('.summary-header').classList.contains('success')).toBe(true);
    expect(modal.querySelector('.summary-title').textContent).toBe('Matched 3 entries');
    expect(modal.querySelector('.failure-table')).toBeNull();
  });

  it('renders an error header when nothing matched and errors occurred', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({ scope: 'global', total: 3, errors: 3 });

    const modal = document.getElementById('rematchSummaryModal');
    expect(modal.querySelector('.summary-header').classList.contains('error')).toBe(true);
    expect(modal.querySelector('.summary-title').textContent).toBe('Rematch failed');
  });

  it('renders a warning header for unresolved entries, L4 matches, or cancellations', async () => {
    const showRematchSummary = await getShowRematchSummary();

    showRematchSummary({ scope: 'bulk', total: 2, matchedEntries: 1, unresolvedEntries: 1, unresolvedRecipes: 1 });
    expect(document.querySelector('#rematchSummaryModal .summary-header').classList.contains('warning')).toBe(true);

    showRematchSummary({ scope: 'bulk', total: 2, matchedEntries: 2, l4Matches: [L4_LORA] });
    expect(document.querySelector('#rematchSummaryModal .summary-header').classList.contains('warning')).toBe(true);

    showRematchSummary({ scope: 'global', total: 5, matchedEntries: 2, cancelled: true });
    const modal = document.getElementById('rematchSummaryModal');
    expect(modal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(modal.querySelector('.rematch-cancelled-note')).not.toBeNull();
  });

  it('renders the four stat cards in order', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({
      scope: 'bulk',
      total: 4,
      matchedRecipes: 1,
      matchedEntries: 2,
      unresolvedEntries: 3,
      errors: 1,
      l4Matches: [L4_LORA],
    });

    const modal = document.getElementById('rematchSummaryModal');
    const values = Array.from(modal.querySelectorAll('.stat-card-value')).map(el => el.textContent);
    expect(values).toEqual(['2', '1', '3', '1']);
    const labels = Array.from(modal.querySelectorAll('.stat-card-label')).map(el => el.textContent);
    expect(labels).toEqual(['Matched entries', 'Needs review', 'Unresolved', 'Errors']);
  });

  it('renders the L4 review table only when matches exist', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({ scope: 'bulk', total: 2, matchedEntries: 2, l4Matches: [L4_LORA, L4_CHECKPOINT] });

    const modal = document.getElementById('rematchSummaryModal');
    const rows = modal.querySelectorAll('.failure-table tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('r1');
    expect(rows[0].textContent).toContain('old.safetensors');
    expect(rows[0].textContent).toContain('new.safetensors');
    expect(rows[1].textContent).toContain('cp-new.safetensors');
    expect(modal.querySelectorAll('.rematch-undo-btn')).toHaveLength(2);
  });

  it('undo posts to the lora restore endpoint, then strikes and disables the row', async () => {
    const showRematchSummary = await getShowRematchSummary();
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ success: true }) });

    showRematchSummary({ scope: 'bulk', total: 1, matchedEntries: 1, l4Matches: [L4_LORA] });

    const modal = document.getElementById('rematchSummaryModal');
    const row = modal.querySelector('tr[data-l4-index="0"]');
    const button = row.querySelector('.rematch-undo-btn');
    button.click();
    await vi.waitFor(() => expect(button.disabled).toBe(true));

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/lora/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipe_id: 'r1', lora_index: 2 }),
    });
    expect(row.classList.contains('undone')).toBe(true);
    expect(button.textContent).toBe('Undone');
  });

  it('undo posts to the checkpoint restore endpoint with recipe_id only', async () => {
    const showRematchSummary = await getShowRematchSummary();
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ success: true }) });

    showRematchSummary({ scope: 'bulk', total: 1, matchedEntries: 1, l4Matches: [L4_CHECKPOINT] });

    const button = document.querySelector('.rematch-undo-btn');
    button.click();
    await vi.waitFor(() => expect(button.disabled).toBe(true));

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/checkpoint/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipe_id: 'r2' }),
    });
  });

  it('keeps the row actionable and toasts when undo fails', async () => {
    const showRematchSummary = await getShowRematchSummary();
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ success: false, error: 'no snapshot' }) });

    showRematchSummary({ scope: 'bulk', total: 1, matchedEntries: 1, l4Matches: [L4_LORA] });

    const row = document.querySelector('tr[data-l4-index="0"]');
    const button = row.querySelector('.rematch-undo-btn');
    button.click();
    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalled());

    expect(button.disabled).toBe(false);
    expect(row.classList.contains('undone')).toBe(false);
    expect(showToastMock).toHaveBeenCalledWith(
      'modals.rematchResults.undoFailed',
      { message: 'no snapshot' },
      'error'
    );
  });

  it('copy report includes scope, counts and the L4 list with undo status', async () => {
    const showRematchSummary = await getShowRematchSummary();
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
    const writeText = vi.fn().mockResolvedValue(undefined);
    navigator.clipboard = { writeText };

    showRematchSummary({
      scope: 'bulk',
      total: 2,
      matchedRecipes: 1,
      matchedEntries: 2,
      unresolvedEntries: 1,
      unresolvedRecipes: 1,
      skipped: 0,
      errors: 0,
      l4Matches: [L4_LORA, L4_CHECKPOINT],
    });

    // Undo the first row before copying so the report carries its status.
    const undoButton = document.querySelector('tr[data-l4-index="0"] .rematch-undo-btn');
    undoButton.click();
    await vi.waitFor(() => expect(undoButton.disabled).toBe(true));

    document.querySelector('[data-action="copy-report"]').click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalled());

    const report = writeText.mock.calls[0][0];
    expect(report).toContain('Scope: Selected recipes');
    expect(report).toContain('Total recipes: 2');
    expect(report).toContain('Matched entries: 2');
    expect(report).toContain('Needs review (filename matches): 2');
    expect(report).toContain('Unresolved entries: 1 (in 1 recipes)');
    expect(report).toContain('[r1] old.safetensors -> new.safetensors [undone]');
    expect(report).toContain('[r2] cp-old -> cp-new.safetensors');
    // The success toast fires in the writeText .then() microtask.
    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalledWith('toast.api.copiedToClipboard', {}, 'success'));
  });

  it('close removes the modal from the DOM', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({ scope: 'single', total: 1, matchedEntries: 1 });

    expect(document.getElementById('rematchSummaryModal')).not.toBeNull();
    document.querySelector('[data-action="close-modal"].cancel-btn').click();
    expect(document.getElementById('rematchSummaryModal')).toBeNull();
  });

  it('escapes HTML in L4 row fields', async () => {
    const showRematchSummary = await getShowRematchSummary();
    showRematchSummary({
      scope: 'bulk',
      total: 1,
      matchedEntries: 1,
      l4Matches: [{ recipe_id: 'r<x>', type: 'lora', entry: '<img src=x>', file_name: 'f.safetensors', lora_index: 0 }],
    });

    const modal = document.getElementById('rematchSummaryModal');
    expect(modal.querySelector('.failure-table img')).toBeNull();
    expect(modal.querySelector('.failure-table tbody tr').textContent).toContain('<img src=x>');
  });
});
