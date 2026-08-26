import { describe, expect, it } from 'vitest';

import { ModelContextMenuMixin } from '../../../static/js/components/ContextMenu/ModelContextMenuMixin.js';

describe('ModelContextMenuMixin.getModelTypePrefix', () => {
  it('maps every known model type to its API route prefix', () => {
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'lora' })).toBe('loras');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'checkpoint' })).toBe('checkpoints');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'embedding' })).toBe('embeddings');
  });

  it('falls back to the loras prefix for unknown types', () => {
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'unknown' })).toBe('loras');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({})).toBe('loras');
  });
});
