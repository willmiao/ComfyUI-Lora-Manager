import { describe, expect, it } from 'vitest';

import { NSFW_LEVELS, getMatureBlurThreshold } from '../../../static/js/utils/constants.js';

describe('getMatureBlurThreshold', () => {
  it('returns configured PG13 threshold', () => {
    expect(getMatureBlurThreshold({ mature_blur_level: 'PG13' })).toBe(NSFW_LEVELS.PG13);
  });

  it('normalizes lowercase values', () => {
    expect(getMatureBlurThreshold({ mature_blur_level: 'x' })).toBe(NSFW_LEVELS.X);
  });

  it('falls back to R when value is invalid or missing', () => {
    expect(getMatureBlurThreshold({ mature_blur_level: 'invalid' })).toBe(NSFW_LEVELS.R);
    expect(getMatureBlurThreshold({})).toBe(NSFW_LEVELS.R);
  });
});
