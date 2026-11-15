/**
 * LoRA Manager widget accent.
 *
 * LM widgets are embedded in ComfyUI: their surfaces, text and borders always
 * follow the active ComfyUI palette (see lm_theme.css, where every --lm-*
 * surface/text token aliases a ComfyUI token). The only thing LM owns is its
 * brand accent, because accent colour is the one dimension a widget can change
 * without looking foreign inside a node that ComfyUI still paints.
 *
 * Everything decorative derives from --lm-accent with color-mix (selection,
 * focus ring, badges, accent labels), so overriding one custom property
 * recolours all of it:
 *
 *   <html style="--lm-base-accent: #8b5cf6; --lm-base-on-accent: #fff">
 *
 * `--lm-base-accent` exists because `--lm-accent` is declared per context in
 * lm_theme.css: an inline `--lm-accent` on <html> would be shadowed by those
 * declarations.
 */

export const LM_THEME_ACCENT_SETTING_ID = "loramanager.comfy_theme_accent";

/**
 * The LM brand accent, also the default of `loramanager.comfy_theme_accent`.
 * When the setting holds this value the override is removed entirely, so the
 * brand keeps its white-on-accent text treatment.
 */
export const LM_THEME_ACCENT_DEFAULT = "#4299e1";

/**
 * Preset accents offered next to the free colour picker. A preset is a single
 * colour, so naming one does not promise a whole palette — these are the
 * values that stay legible both as a fill and as a 18% surface tint.
 */
export const LM_THEME_ACCENT_PRESETS = [
  { name: "Azure", color: "#4299e1" },
  { name: "Violet", color: "#8b5cf6" },
  { name: "Teal", color: "#14b8a6" },
  { name: "Amber", color: "#f59e0b" },
  { name: "Rose", color: "#f43f5e" },
  { name: "Slate", color: "#64748b" },
];

const LM_ACCENT_PROPERTY = "--lm-base-accent";
const LM_ON_ACCENT_PROPERTY = "--lm-base-on-accent";
const LM_SWATCH_COLOR_PROPERTY = "--lm-accent-swatch-color";

// ============================================================================
// Colour parsing
// ============================================================================

/**
 * Normalize a color-picker value to `#rrggbb` (or `#rrggbbaa`), or null when
 * it is not a hex color. The value travels through the settings store, so
 * anything unexpected is treated as "no override".
 *
 * ComfyUI's `color` setting persists hex WITHOUT the leading `#` (the
 * PrimeVue ColorPicker contract, see FormColorPicker.vue), so the prefix is
 * optional here; the canonical form returned always carries it.
 */
export function normalizeLmAccent(value) {
  if (typeof value !== "string") return null;
  const raw = value.trim().toLowerCase();
  if (!raw) return null;
  const accent = raw.startsWith("#") ? raw : `#${raw}`;
  if (!/^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/.test(accent)) return null;
  // Expand the shorthand so the contrast maths below sees real channels.
  return accent.length === 4 ? `#${accent[1]}${accent[1]}${accent[2]}${accent[2]}${accent[3]}${accent[3]}` : accent;
}

function toRgb(accent) {
  return {
    r: parseInt(accent.slice(1, 3), 16),
    g: parseInt(accent.slice(3, 5), 16),
    b: parseInt(accent.slice(5, 7), 16),
  };
}

function relativeLuminance({ r, g, b }) {
  const channel = (value) => {
    const srgb = value / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(a, b) {
  const [high, low] = a > b ? [a, b] : [b, a];
  return (high + 0.05) / (low + 0.05);
}

/**
 * The readable text color for a solid accent fill. The default accent keeps
 * the brand's white-on-blue treatment; any override picks whichever of white
 * and near-black wins on WCAG contrast, so a pale accent cannot end up with
 * white text on it. Written to --lm-base-on-accent, which lm_theme.css turns
 * into --lm-on-accent per context (declaring --lm-on-accent itself would be
 * shadowed by the per-context declaration).
 */
function readableOnAccent(accent) {
  const luminance = relativeLuminance(toRgb(accent));
  const white = contrastRatio(1, luminance);
  const ink = contrastRatio(relativeLuminance({ r: 17, g: 17, b: 17 }), luminance);
  return ink > white ? "#111" : "#fff";
}

// ============================================================================
// Applying the accent
// ============================================================================

/**
 * Apply a user accent color. Passing the default (or anything invalid) clears
 * the override, which restores #4299e1 and the original white-on-accent text.
 * Returns the applied `#rrggbb` value, or null when the override was cleared.
 */
export function applyLmAccent(value) {
  const accent = normalizeLmAccent(value);
  const root = document.documentElement.style;

  if (!accent || accent === LM_THEME_ACCENT_DEFAULT) {
    root.removeProperty(LM_ACCENT_PROPERTY);
    root.removeProperty(LM_ON_ACCENT_PROPERTY);
    return null;
  }

  root.setProperty(LM_ACCENT_PROPERTY, accent);
  root.setProperty(LM_ON_ACCENT_PROPERTY, readableOnAccent(accent));
  return accent;
}

/** The accent currently in effect (`#rrggbb`). */
export function getLmAccent() {
  return document.documentElement.style.getPropertyValue(LM_ACCENT_PROPERTY) || LM_THEME_ACCENT_DEFAULT;
}

// ============================================================================
// Settings control
// ============================================================================

/**
 * Custom renderer for `loramanager.comfy_theme_accent` (ComfyUI calls a
 * function-typed `type` with `(name, setter, value, attrs)` and appends the
 * returned element, rebuilding it on every settings re-render — so this must
 * stay stateless and cheap).
 *
 * Presets are plain swatches because a named single color cannot over-promise
 * the way a named palette would. The native colour input doubles as the
 * "current value" indicator and the custom picker; it commits on `change`
 * (not `input`) so a re-render cannot close the picker mid-drag.
 */
export function renderLmAccentSetting(name, setter, value) {
  const current = normalizeLmAccent(value) ?? LM_THEME_ACCENT_DEFAULT;
  const row = document.createElement("div");
  row.className = "lm-accent-setting";
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", name || "Widget accent color");

  for (const preset of LM_THEME_ACCENT_PRESETS) {
    const swatch = document.createElement("button");
    swatch.type = "button";
    swatch.className = "lm-accent-setting__swatch";
    swatch.title = preset.name;
    swatch.setAttribute("aria-label", preset.name);
    swatch.setAttribute("aria-pressed", String(preset.color === current));
    swatch.style.setProperty(LM_SWATCH_COLOR_PROPERTY, preset.color);
    swatch.addEventListener("click", () => setter(preset.color));
    row.appendChild(swatch);
  }

  const custom = document.createElement("input");
  custom.type = "color";
  custom.className = "lm-accent-setting__custom";
  custom.value = current;
  custom.title = "Custom color";
  custom.setAttribute("aria-label", "Custom accent color");
  custom.addEventListener("change", () => {
    if (custom.value) setter(custom.value);
  });
  row.appendChild(custom);

  return row;
}
