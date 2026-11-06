import { describe, it, expect, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

const { registerExtensionMock } = vi.hoisted(() => ({
  registerExtensionMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: registerExtensionMock,
    graph: {},
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: { get: () => undefined, set: vi.fn() },
    },
  },
}));

vi.mock(API_MODULE, () => ({
  api: { fetchApi: vi.fn(), addEventListener: vi.fn() },
}));

vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import {
  enableListedLorasFromCode,
  parseLoraCodeTags,
} from '../../../web/comfyui/lora_selection.js';
import { applyLoraSelection } from '../../../web/comfyui/lora_stacker_search.js';

// Synthetic fixtures: every name below is invented and matches no real file.
const listed = (name, { active = true, strength = '0.80' } = {}) => ({
  name,
  strength,
  clipStrength: strength,
  active,
  expanded: false,
  selected: false,
  locked: false,
});

describe('LoRA code parsing', () => {
  it('reads a single tag with its strength', () => {
    expect(parseLoraCodeTags('<lora:portraits/sample_entry:0.75>')).toEqual([
      {
        tag: '<lora:portraits/sample_entry:0.75>',
        name: 'portraits/sample_entry',
        strength: 0.75,
        clipStrength: undefined,
      },
    ]);
  });

  it('reads every tag in the string and keeps clip strengths', () => {
    const tags = parseLoraCodeTags(
      'masterpiece, <lora:styles/sample_wash:0.6:0.4> and <lora:example_lora.safetensors:1>'
    );
    expect(tags.map((tag) => tag.name)).toEqual([
      'styles/sample_wash',
      'example_lora',
    ]);
    expect(tags[0].clipStrength).toBe(0.4);
    expect(tags[1].strength).toBe(1);
  });

  it('ignores text that carries no LoRA tag', () => {
    expect(parseLoraCodeTags('a prompt with no tags')).toEqual([]);
    expect(parseLoraCodeTags('')).toEqual([]);
    expect(parseLoraCodeTags(undefined)).toEqual([]);
  });
});

describe('Send to ComfyUI enable-in-place', () => {
  it('switches on a listed LoRA instead of appending it again', () => {
    const before = [listed('portraits/sample_entry', { active: false })];
    const result = enableListedLorasFromCode(
      before,
      '<lora:portraits/sample_entry:0.75>'
    );

    expect(result.changed).toBe(true);
    expect(result.unlistedTags).toEqual([]);
    expect(result.loras).toHaveLength(1);
    expect(result.loras[0]).toMatchObject({
      name: 'portraits/sample_entry',
      active: true,
      // The code's strength must not overwrite what the node already holds.
      strength: '0.80',
      clipStrength: '0.80',
    });
    // The input list is left untouched.
    expect(before[0].active).toBe(false);
  });

  it('reports no change for a LoRA that is already active', () => {
    const before = [listed('portraits/sample_entry')];
    const result = enableListedLorasFromCode(
      before,
      '<lora:portraits/sample_entry:0.75>'
    );

    expect(result.changed).toBe(false);
    expect(result.loras).toBe(before);
    expect(result.unlistedTags).toEqual([]);
  });

  it('hands a LoRA the list does not contain to the textarea path', () => {
    const before = [listed('portraits/sample_entry')];
    const result = enableListedLorasFromCode(
      before,
      '<lora:styles/sample_wash:0.6>'
    );

    expect(result.changed).toBe(false);
    expect(result.loras).toBe(before);
    expect(result.unlistedTags).toEqual(['<lora:styles/sample_wash:0.6>']);
  });

  it('enables the listed LoRAs in a mixed code string and forwards only the new ones', () => {
    const before = [
      listed('portraits/sample_entry', { active: false }),
      listed('styles/sample_wash'),
    ];
    const result = enableListedLorasFromCode(
      before,
      '<lora:portraits/sample_entry:0.7> <lora:example_new:0.9>'
    );

    expect(result.changed).toBe(true);
    expect(result.unlistedTags).toEqual(['<lora:example_new:0.9>']);
    expect(result.loras.map((entry) => [entry.name, entry.active])).toEqual([
      ['portraits/sample_entry', true],
      ['styles/sample_wash', true],
    ]);
  });

  it('matches a folder-qualified code against a legacy bare file name', () => {
    const before = [listed('sample_entry', { active: false })];
    const result = enableListedLorasFromCode(
      before,
      '<lora:portraits/sample_entry:0.7>'
    );

    expect(result.unlistedTags).toEqual([]);
    expect(result.loras).toHaveLength(1);
    expect(result.loras[0].active).toBe(true);
  });

  it('does not treat the same file name in another folder as listed', () => {
    const before = [listed('styles/sample_entry', { active: false })];
    const result = enableListedLorasFromCode(
      before,
      '<lora:portraits/sample_entry:0.7>'
    );

    // Folder-qualified names in different folders are different files, so the
    // code falls through to the add path rather than toggling the wrong entry.
    expect(result.changed).toBe(false);
    expect(result.unlistedTags).toEqual(['<lora:portraits/sample_entry:0.7>']);
  });
});

describe('shared selection API', () => {
  it('is still exported from the search module', () => {
    const { loras, changed } = applyLoraSelection([], {
      name: 'styles/sample_wash',
      strength: 0.55,
    });
    expect(changed).toBe(true);
    expect(loras[0]).toMatchObject({ active: true, strength: '0.55' });
  });
});

describe('Send to ComfyUI wiring', () => {
  const getLoaderExtension = () => {
    const extension = registerExtensionMock.mock.calls
      .map(([registered]) => registered)
      .find((registered) => registered?.name === 'LoraManager.LoraLoader');
    if (!extension) {
      throw new Error('Lora Loader extension not registered');
    }
    return extension;
  };

  const createNode = (loras) => ({
    inputWidget: { value: '', callback: vi.fn() },
    lorasWidget: { value: loras, callback: vi.fn() },
  });

  it('switches a listed LoRA on without touching the textarea', async () => {
    await import('../../../web/comfyui/lora_loader.js');
    const extension = getLoaderExtension();
    const node = createNode([
      listed('portraits/sample_entry', { active: false }),
    ]);

    extension.updateNodeLoraCode(
      node,
      '<lora:portraits/sample_entry:0.75>',
      'append'
    );

    expect(node.lorasWidget.value).toHaveLength(1);
    expect(node.lorasWidget.value[0].active).toBe(true);
    expect(node.lorasWidget.callback).toHaveBeenCalledTimes(1);
    // No duplicate tag, and nothing pushed through the textarea path.
    expect(node.inputWidget.value).toBe('');
    expect(node.inputWidget.callback).not.toHaveBeenCalled();
  });

  it('still appends a LoRA the node does not list', async () => {
    await import('../../../web/comfyui/lora_loader.js');
    const extension = getLoaderExtension();
    const node = createNode([listed('portraits/sample_entry')]);

    extension.updateNodeLoraCode(node, '<lora:styles/sample_wash:0.6>', 'append');

    expect(node.inputWidget.value).toBe('<lora:styles/sample_wash:0.6>');
    expect(node.inputWidget.callback).toHaveBeenCalledWith(
      '<lora:styles/sample_wash:0.6>'
    );
    expect(node.lorasWidget.value).toHaveLength(1);
    expect(node.lorasWidget.callback).not.toHaveBeenCalled();
  });

  it('enables the listed LoRA and appends only the new tag in a mixed payload', async () => {
    await import('../../../web/comfyui/lora_loader.js');
    const extension = getLoaderExtension();
    const node = createNode([
      listed('portraits/sample_entry', { active: false }),
    ]);

    extension.updateNodeLoraCode(
      node,
      '<lora:portraits/sample_entry:0.7> <lora:styles/sample_wash:0.6>',
      'append'
    );

    expect(node.lorasWidget.value[0].active).toBe(true);
    expect(node.lorasWidget.callback).toHaveBeenCalledTimes(1);
    // The whole code still goes through the textarea; the listed LoRA's tag is
    // already there, so only the new entry is added by the parser.
    expect(node.inputWidget.value).toContain('<lora:styles/sample_wash:0.6>');
  });

  it('leaves replace mode alone', async () => {
    await import('../../../web/comfyui/lora_loader.js');
    const extension = getLoaderExtension();
    const node = createNode([listed('portraits/sample_entry')]);

    extension.updateNodeLoraCode(node, '<lora:styles/sample_wash:1>', 'replace');

    expect(node.inputWidget.value).toBe('<lora:styles/sample_wash:1>');
    expect(node.lorasWidget.callback).not.toHaveBeenCalled();
  });
});
