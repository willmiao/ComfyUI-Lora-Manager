import { describe, it, expect } from 'vitest';

// genParamsMapper is pure logic with zero dependencies — safe to import directly
import {
    SAMPLER_DISPLAY_TO_INTERNAL,
    SCHEDULER_SUFFIXES,
    SCHEDULER_ONLY_VALUES,
    PARAM_TO_WIDGET_CANDIDATES,
    parseCombinedSamplerName,
    resolveSamplerScheduler,
    findMatchingWidgets,
} from '../../../static/js/utils/genParamsMapper.js';

// ---------------------------------------------------------------------------
// Constants sanity
// ---------------------------------------------------------------------------
describe('constants', () => {
    it('maps at least the common samplers', () => {
        expect(SAMPLER_DISPLAY_TO_INTERNAL['Euler']).toBe('euler');
        expect(SAMPLER_DISPLAY_TO_INTERNAL['Euler a']).toBe('euler_ancestral');
        expect(SAMPLER_DISPLAY_TO_INTERNAL['DPM++ 2M']).toBe('dpmpp_2m');
        expect(SAMPLER_DISPLAY_TO_INTERNAL['DPM++ 2M SDE']).toBe('dpmpp_2m_sde');
        expect(SAMPLER_DISPLAY_TO_INTERNAL['LCM']).toBe('lcm');
        expect(SAMPLER_DISPLAY_TO_INTERNAL['DDIM']).toBe('ddim');
    });

    it('lists all 9 scheduler suffixes', () => {
        expect(SCHEDULER_SUFFIXES).toHaveLength(9);
        expect(SCHEDULER_SUFFIXES).toContain('karras');
        expect(SCHEDULER_SUFFIXES).toContain('simple');
        expect(SCHEDULER_SUFFIXES).toContain('exponential');
    });

    it('marks scheduler-only values', () => {
        expect(SCHEDULER_ONLY_VALUES.has('karras')).toBe(true);
        expect(SCHEDULER_ONLY_VALUES.has('simple')).toBe(true);
        expect(SCHEDULER_ONLY_VALUES.has('euler')).toBe(false);
    });

    it('has widget candidates for all param keys', () => {
        expect(PARAM_TO_WIDGET_CANDIDATES.seed).toContain('seed');
        expect(PARAM_TO_WIDGET_CANDIDATES.sampler).toContain('sampler_name');
        expect(PARAM_TO_WIDGET_CANDIDATES.scheduler).toContain('scheduler');
    });
});

// ---------------------------------------------------------------------------
// parseCombinedSamplerName
// ---------------------------------------------------------------------------
describe('parseCombinedSamplerName', () => {
    it('parses space-separated sampler + scheduler', () => {
        expect(parseCombinedSamplerName('Euler a Karras')).toEqual({
            sampler: 'euler_ancestral',
            scheduler: 'karras',
        });
    });

    it('parses DPM++ 2M Karras', () => {
        expect(parseCombinedSamplerName('DPM++ 2M Karras')).toEqual({
            sampler: 'dpmpp_2m',
            scheduler: 'karras',
        });
    });

    it('parses DPM++ 2M beta', () => {
        expect(parseCombinedSamplerName('DPM++ 2M beta')).toEqual({
            sampler: 'dpmpp_2m',
            scheduler: 'beta',
        });
    });

    it('parses DPM++ SDE Karras', () => {
        expect(parseCombinedSamplerName('DPM++ SDE Karras')).toEqual({
            sampler: 'dpmpp_sde',
            scheduler: 'karras',
        });
    });

    it('parses underscore-separated er_sde_beta', () => {
        expect(parseCombinedSamplerName('er_sde_beta')).toEqual({
            sampler: 'er_sde',
            scheduler: 'beta',
        });
    });

    it('returns null for sampler-only values', () => {
        expect(parseCombinedSamplerName('Euler a')).toBeNull();
        expect(parseCombinedSamplerName('LCM')).toBeNull();
    });

    it('returns null for unrecognised suffix', () => {
        expect(parseCombinedSamplerName('Euler something_unknown')).toBeNull();
    });

    it('returns null for null/empty', () => {
        expect(parseCombinedSamplerName(null)).toBeNull();
        expect(parseCombinedSamplerName('')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// resolveSamplerScheduler — the main resolver used by the send feature
// ---------------------------------------------------------------------------
describe('resolveSamplerScheduler', () => {
    // --- Category 1: simple display names ---
    it('resolves Euler → euler', () => {
        expect(resolveSamplerScheduler('Euler')).toEqual({ sampler: 'euler', scheduler: null });
    });

    it('resolves Euler a → euler_ancestral', () => {
        expect(resolveSamplerScheduler('Euler a')).toEqual({ sampler: 'euler_ancestral', scheduler: null });
    });

    it('resolves DPM++ 2M → dpmpp_2m', () => {
        expect(resolveSamplerScheduler('DPM++ 2M')).toEqual({ sampler: 'dpmpp_2m', scheduler: null });
    });

    it('resolves LCM → lcm', () => {
        expect(resolveSamplerScheduler('LCM')).toEqual({ sampler: 'lcm', scheduler: null });
    });

    // --- Category 2: already-internal names ---
    it('passes through lowercase internal names', () => {
        expect(resolveSamplerScheduler('euler')).toEqual({ sampler: 'euler', scheduler: null });
        expect(resolveSamplerScheduler('heunpp2')).toEqual({ sampler: 'heunpp2', scheduler: null });
        expect(resolveSamplerScheduler('lcm')).toEqual({ sampler: 'lcm', scheduler: null });
        expect(resolveSamplerScheduler('er_sde')).toEqual({ sampler: 'er_sde', scheduler: null });
    });

    // --- Category 3: combined names ---
    it('resolves Euler a Karras → euler_ancestral + karras', () => {
        expect(resolveSamplerScheduler('Euler a Karras')).toEqual({
            sampler: 'euler_ancestral',
            scheduler: 'karras',
        });
    });

    it('resolves DPM++ 2M Karras → dpmpp_2m + karras', () => {
        expect(resolveSamplerScheduler('DPM++ 2M Karras')).toEqual({
            sampler: 'dpmpp_2m',
            scheduler: 'karras',
        });
    });

    // --- Category 4: scheduler-only ---
    it('resolves scheduler-only values', () => {
        expect(resolveSamplerScheduler('karras')).toEqual({ sampler: null, scheduler: 'karras' });
        expect(resolveSamplerScheduler('simple')).toEqual({ sampler: null, scheduler: 'simple' });
        expect(resolveSamplerScheduler('sgm_uniform')).toEqual({ sampler: null, scheduler: 'sgm_uniform' });
    });

    // --- Category 5: unrecognised / model-specific ---
    it('returns null+null for unrecognised values', () => {
        const result = resolveSamplerScheduler('AYS SDXL');
        expect(result.sampler).toBeNull();
        expect(result.scheduler).toBeNull();
    });

    it('returns null+null for Undefined', () => {
        const result = resolveSamplerScheduler('Undefined');
        expect(result.sampler).toBeNull();
        expect(result.scheduler).toBeNull();
    });

    it('returns null+null for model-specific values', () => {
        expect(resolveSamplerScheduler('Seedream-V45').sampler).toBeNull();
        expect(resolveSamplerScheduler('GPT-Image-2').sampler).toBeNull();
    });

    // --- Category 6: edge cases ---
    it('returns null+null for null / empty / whitespace', () => {
        expect(resolveSamplerScheduler(null)).toEqual({ sampler: null, scheduler: null });
        expect(resolveSamplerScheduler('')).toEqual({ sampler: null, scheduler: null });
        expect(resolveSamplerScheduler('   ')).toEqual({ sampler: null, scheduler: null });
    });

    it('handles slash-separated custom format (extracts last segment)', () => {
        // "multistep/dpmpp_2m_simple" — extracts last segment but the recursive
        // call hits the "already internal name" regex before combined-name parsing,
        // so it returns the raw segment as the sampler name.
        const result = resolveSamplerScheduler('multistep/dpmpp_2m_simple');
        expect(result.sampler).toBe('dpmpp_2m_simple');
        expect(result.scheduler).toBeNull();
    });

    it('handles parse-error value (None', () => {
        const result = resolveSamplerScheduler('(None');
        expect(result.sampler).toBeNull();
        expect(result.scheduler).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// findMatchingWidgets
// ---------------------------------------------------------------------------
describe('findMatchingWidgets', () => {
    const resolved = {
        seed: 42,
        steps: 30,
        cfg: 7,
        sampler: 'euler_ancestral',
        scheduler: 'karras',
    };

    it('matches seed to seed widget', () => {
        const updates = findMatchingWidgets(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler'], resolved);
        expect(updates).toContainEqual({ widgetName: 'seed', value: '42' });
        expect(updates).toContainEqual({ widgetName: 'steps', value: '30' });
        expect(updates).toContainEqual({ widgetName: 'cfg', value: '7' });
        expect(updates).toContainEqual({ widgetName: 'sampler_name', value: 'euler_ancestral' });
        expect(updates).toContainEqual({ widgetName: 'scheduler', value: 'karras' });
    });

    it('skips undefined/null params', () => {
        const updates = findMatchingWidgets(['seed', 'steps'], { seed: 42, steps: null, cfg: undefined });
        expect(updates).toHaveLength(1);
        expect(updates[0].widgetName).toBe('seed');
    });

    it('matches noise_seed when seed widget not present', () => {
        const updates = findMatchingWidgets(['noise_seed', 'steps', 'cfg', 'sampler_name', 'scheduler'], resolved);
        const seedUpdate = updates.find(u => u.widgetName === 'noise_seed');
        expect(seedUpdate).toBeDefined();
        expect(seedUpdate.value).toBe('42');
    });

    it('matches rgthree-style sampler widget name', () => {
        const updates = findMatchingWidgets(['sampler', 'scheduler'], { sampler: 'euler', scheduler: 'karras' });
        expect(updates).toContainEqual({ widgetName: 'sampler', value: 'euler' });
    });

    it('returns empty array for empty widget list', () => {
        expect(findMatchingWidgets([], resolved)).toEqual([]);
        expect(findMatchingWidgets(null, resolved)).toEqual([]);
    });

    it('handles case-insensitive widget name matching', () => {
        const updates = findMatchingWidgets(['SEED', 'STEPS', 'CFG'], resolved);
        expect(updates).toHaveLength(3);
    });

    it('returns updates in param order (seed, steps, cfg, sampler, scheduler)', () => {
        const updates = findMatchingWidgets(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler'], resolved);
        expect(updates.map(u => u.widgetName)).toEqual(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler']);
    });
});
