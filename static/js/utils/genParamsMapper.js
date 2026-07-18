/**
 * genParamsMapper.js
 * Maps display/recipe generation parameter values (sampler, scheduler) to
 * ComfyUI internal widget values, enabling "Send Gen Params to Workflow".
 *
 * Strategy (3 layers):
 *   1. Direct lookup via SAMPLER_DISPLAY_TO_INTERNAL
 *   2. Combined-name parsing (e.g. "Euler a Karras" → sampler + scheduler)
 *   3. Graceful skip for model-specific / unrecognized values
 */

// ---------------------------------------------------------------------------
// Sampler display name → internal name (ComfyUI KSampler.SAMPLERS / SAMPLER_NAMES)
// ---------------------------------------------------------------------------
const SAMPLER_DISPLAY_TO_INTERNAL = {
    // --- Euler family ---
    'Euler':                     'euler',
    'euler':                     'euler',
    'Euler a':                   'euler_ancestral',
    'Euler A':                   'euler_ancestral',
    'Euler ancestral':           'euler_ancestral',
    'Euler Ancestral':           'euler_ancestral',
    'euler_ancestral':           'euler_ancestral',

    // --- Heun ---
    'Heun':                      'heun',
    'heun':                      'heun',
    'Heun++':                    'heunpp2',
    'heunpp2':                   'heunpp2',

    // --- DPM2 ---
    'DPM2':                      'dpm_2',
    'DPM 2':                     'dpm_2',
    'dpm_2':                     'dpm_2',
    'DPM2 a':                    'dpm_2_ancestral',
    'DPM2 Ancestral':            'dpm_2_ancestral',
    'dpm_2_ancestral':           'dpm_2_ancestral',

    // --- LMS ---
    'LMS':                       'lms',
    'lms':                       'lms',

    // --- DPM fast / adaptive ---
    'DPM fast':                  'dpm_fast',
    'DPM Fast':                  'dpm_fast',
    'dpm_fast':                  'dpm_fast',
    'DPM adaptive':              'dpm_adaptive',
    'DPM Adaptive':              'dpm_adaptive',
    'dpm_adaptive':              'dpm_adaptive',

    // --- DPM++ 2S ancestral ---
    'DPM++ 2S a':                'dpmpp_2s_ancestral',
    'DPM++ 2S A':                'dpmpp_2s_ancestral',
    'DPM++ 2S Ancestral':        'dpmpp_2s_ancestral',
    'dpmpp_2s_ancestral':        'dpmpp_2s_ancestral',

    // --- DPM++ SDE ---
    'DPM++ SDE':                 'dpmpp_sde',
    'dpmpp_sde':                 'dpmpp_sde',

    // --- DPM++ 2M ---
    'DPM++ 2M':                  'dpmpp_2m',
    'dpmpp_2m':                  'dpmpp_2m',

    // --- DPM++ 2M SDE ---
    'DPM++ 2M SDE':              'dpmpp_2m_sde',
    'dpmpp_2m_sde':              'dpmpp_2m_sde',

    // --- DPM++ 3M SDE ---
    'DPM++ 3M SDE':              'dpmpp_3m_sde',
    'dpmpp_3m_sde':              'dpmpp_3m_sde',

    // --- Others ---
    'DDIM':                      'ddim',
    'ddim':                      'ddim',
    'DDPM':                      'ddpm',
    'ddpm':                      'ddpm',
    'LCM':                       'lcm',
    'lcm':                       'lcm',
    'IPNDM':                     'ipndm',
    'ipndm':                     'ipndm',
    'DEIS':                      'deis',
    'deis':                      'deis',
    'UniPC':                     'uni_pc',
    'unipc':                     'uni_pc',
    'uni_pc':                    'uni_pc',

    // --- Restart / res_multistep ---
    'Restart':                   'res_multistep',
    'res_multistep':             'res_multistep',

    // --- ER SDE ---
    'ER SDE':                    'er_sde',
    'E-R SDE':                   'er_sde',
    'er_sde':                     'er_sde',

    // --- SA Solver ---
    'SA Solver':                 'sa_solver',
    'SA solver':                 'sa_solver',
    'sa_solver':                 'sa_solver',

    // --- Seeds ---
    'Seeds 2':                   'seeds_2',
    'seeds_2':                   'seeds_2',
    'Seeds 3':                   'seeds_3',
    'seeds_3':                   'seeds_3',
};

// ---------------------------------------------------------------------------
// Known scheduler suffixes (ComfyUI KSampler.SCHEDULERS)
// Sorted by length (descending) for longest-match-first parsing.
// ---------------------------------------------------------------------------
const SCHEDULER_SUFFIXES = [
    'sgm_uniform',
    'ddim_uniform',
    'linear_quadratic',
    'kl_optimal',
    'exponential',
    'karras',
    'simple',
    'normal',
    'beta',
];

// ---------------------------------------------------------------------------
// Scheduler-only values (values that are schedulers, not samplers)
// ---------------------------------------------------------------------------
const SCHEDULER_ONLY_VALUES = new Set([
    'simple', 'sgm_uniform', 'karras', 'exponential',
    'ddim_uniform', 'beta', 'normal', 'linear_quadratic', 'kl_optimal',
]);

// ---------------------------------------------------------------------------
// Param key → widget name candidates (searched in order)
// ---------------------------------------------------------------------------
const PARAM_TO_WIDGET_CANDIDATES = {
    seed:      ['seed', 'noise_seed'],
    steps:     ['steps'],
    cfg:       ['cfg'],
    sampler:   ['sampler_name', 'sampler'],
    scheduler: ['scheduler'],
};

// ---------------------------------------------------------------------------
// Parse a combined sampler+scheduler value (space-separated or underscore)
// e.g., "Euler a Karras", "DPM++ 2M beta", "er_sde_beta"
// Returns { sampler: internalName|null, scheduler: internalName|null } or null
// ---------------------------------------------------------------------------
function parseCombinedSamplerName(rawValue) {
    if (!rawValue || typeof rawValue !== 'string') return null;
    const trimmed = rawValue.trim();
    if (!trimmed) return null;

    // Try space-separated first: split on last space
    const spaceIdx = trimmed.lastIndexOf(' ');
    if (spaceIdx > 0) {
        const candidateScheduler = trimmed.slice(spaceIdx + 1).trim().toLowerCase();
        if (SCHEDULER_SUFFIXES.includes(candidateScheduler)) {
            const samplerPart = trimmed.slice(0, spaceIdx).trim();
            const internalSampler = SAMPLER_DISPLAY_TO_INTERNAL[samplerPart];
            if (internalSampler) {
                return { sampler: internalSampler, scheduler: candidateScheduler };
            }
            // samplerPart might be a combined name itself (e.g., "DPM++ 2M SDE")
            // Try recursing (one level max) — already handled since we split at last space
        }
    }

    // Try underscore-separated: e.g., "er_sde_beta"
    const underIdx = trimmed.lastIndexOf('_');
    if (underIdx > 0) {
        const candidateScheduler = trimmed.slice(underIdx + 1).trim().toLowerCase();
        if (SCHEDULER_SUFFIXES.includes(candidateScheduler)) {
            const samplerPart = trimmed.slice(0, underIdx).trim();
            const internalSampler = SAMPLER_DISPLAY_TO_INTERNAL[samplerPart] || SAMPLER_DISPLAY_TO_INTERNAL[samplerPart.toLowerCase()];
            if (internalSampler) {
                return { sampler: internalSampler, scheduler: candidateScheduler };
            }
        }
    }

    return null;
}

// ---------------------------------------------------------------------------
// Main resolver: takes a raw sampler value from recipe/showcase metadata
// and returns { sampler: internalName|null, scheduler: internalName|null }
// ---------------------------------------------------------------------------
function resolveSamplerScheduler(rawValue) {
    if (!rawValue || typeof rawValue !== 'string') {
        return { sampler: null, scheduler: null };
    }

    const trimmed = rawValue.trim();
    if (!trimmed) return { sampler: null, scheduler: null };

    // 1. Try direct lookup first
    const direct = SAMPLER_DISPLAY_TO_INTERNAL[trimmed];
    if (direct) return { sampler: direct, scheduler: null };

    // 2. Try lowercase direct lookup
    const lowerDirect = SAMPLER_DISPLAY_TO_INTERNAL[trimmed.toLowerCase()];
    if (lowerDirect) return { sampler: lowerDirect, scheduler: null };

    // 3. Scheduler-only value? (check BEFORE the "already internal name" regex,
    //    because scheduler values like "karras", "simple" also match that pattern)
    if (SCHEDULER_ONLY_VALUES.has(trimmed.toLowerCase())) {
        return { sampler: null, scheduler: trimmed.toLowerCase() };
    }

    // 4. Already an internal name? (lowercase, no spaces)
    if (/^[a-z][a-z0-9_]+$/.test(trimmed)) {
        return { sampler: trimmed, scheduler: null };
    }

    // 5. Try combined name parsing (space-separated or underscore)
    const combined = parseCombinedSamplerName(trimmed);
    if (combined) return combined;

    // 6. Custom format like "multistep/dpmpp_2m_simple" — try extracting the last segment
    if (trimmed.includes('/')) {
        const parts = trimmed.split('/');
        const last = parts[parts.length - 1];
        if (last) {
            const subResult = resolveSamplerScheduler(last);
            if (subResult.sampler || subResult.scheduler) return subResult;
        }
    }

    // 7. Unrecognized — return null for both
    return { sampler: null, scheduler: null };
}

// ---------------------------------------------------------------------------
// Find which gen params can be sent to a given node, matching by widget names
// Returns array of { widgetName, value } objects
// ---------------------------------------------------------------------------
function findMatchingWidgets(nodeWidgetNames, resolvedParams) {
    if (!nodeWidgetNames || !Array.isArray(nodeWidgetNames) || nodeWidgetNames.length === 0) {
        return [];
    }

    const widgetSet = new Set(nodeWidgetNames.map(w => String(w).toLowerCase()));
    const updates = [];

    // Simple numeric/string params: seed, steps, cfg
    const simpleParams = [
        { key: 'seed', value: resolvedParams.seed },
        { key: 'steps', value: resolvedParams.steps },
        { key: 'cfg', value: resolvedParams.cfg },
    ];
    for (const { key, value } of simpleParams) {
        if (value === undefined || value === null || value === '') continue;
        const candidates = PARAM_TO_WIDGET_CANDIDATES[key] || [key];
        for (const candidate of candidates) {
            if (widgetSet.has(candidate.toLowerCase())) {
                updates.push({ widgetName: candidate, value });
                break;
            }
        }
    }

    // Sampler
    if (resolvedParams.sampler) {
        const candidates = PARAM_TO_WIDGET_CANDIDATES.sampler;
        for (const candidate of candidates) {
            if (widgetSet.has(candidate.toLowerCase())) {
                updates.push({ widgetName: candidate, value: resolvedParams.sampler });
                break;
            }
        }
    }

    // Scheduler
    if (resolvedParams.scheduler) {
        const candidates = PARAM_TO_WIDGET_CANDIDATES.scheduler;
        for (const candidate of candidates) {
            if (widgetSet.has(candidate.toLowerCase())) {
                updates.push({ widgetName: candidate, value: resolvedParams.scheduler });
                break;
            }
        }
    }

    return updates;
}

export {
    SAMPLER_DISPLAY_TO_INTERNAL,
    SCHEDULER_SUFFIXES,
    SCHEDULER_ONLY_VALUES,
    PARAM_TO_WIDGET_CANDIDATES,
    parseCombinedSamplerName,
    resolveSamplerScheduler,
    findMatchingWidgets,
};
