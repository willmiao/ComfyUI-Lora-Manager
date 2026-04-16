import { describe, expect, it } from 'vitest';

import { ModelContextMenuMixin } from '../../../static/js/components/ContextMenu/ModelContextMenuMixin.js';

describe('ModelContextMenuMixin.extractModelVersionId', () => {
  it('accepts civitai.red model URLs', () => {
    expect(
      ModelContextMenuMixin.extractModelVersionId(
        'https://civitai.red/models/65423/nijimecha-artstyle?modelVersionId=777'
      )
    ).toEqual({ modelId: '65423', modelVersionId: '777' });
  });

  it('rejects model-like URLs from unsupported hosts', () => {
    expect(
      ModelContextMenuMixin.extractModelVersionId(
        'https://example.com/models/65423?modelVersionId=777'
      )
    ).toEqual({ modelId: null, modelVersionId: null });
  });
});
