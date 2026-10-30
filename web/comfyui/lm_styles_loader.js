const STYLE_ID = "lm-lora-shared-styles";
const THEME_STYLE_ID = "lm-lora-theme-tokens";
let stylePromise = null;

function injectStyles(cssText) {
  let styleEl = document.getElementById(STYLE_ID);
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = STYLE_ID;
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = cssText;
}

function injectTheme(cssText) {
  let styleEl = document.getElementById(THEME_STYLE_ID);
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = THEME_STYLE_ID;
    document.head.insertBefore(styleEl, document.head.firstChild);
  }
  styleEl.textContent = cssText;
}

// This module is loaded both as a plain extension script (web/comfyui/) and
// inlined into the compiled Vue bundle (web/comfyui/vue-widgets/), so resolve
// the stylesheet directory from the module location instead of assuming "./".
function stylesBaseUrl() {
  const moduleUrl = new URL(import.meta.url);
  const bundleDir = "/vue-widgets/";
  if (moduleUrl.pathname.includes(bundleDir)) {
    return new URL("../", moduleUrl);
  }
  return new URL("./", moduleUrl);
}

async function loadCssText(fileName) {
  const cssUrl = new URL(fileName, stylesBaseUrl());
  const response = await fetch(cssUrl);
  if (!response.ok) {
    throw new Error(`Failed to load ${cssUrl}`);
  }
  return await response.text();
}

export function ensureLmStyles() {
  if (!stylePromise) {
    // Theme tokens are plain CSS custom properties consumed by lm_styles.css,
    // so they must be injected alongside it (never on their own).
    stylePromise = Promise.all([loadCssText("lm_theme.css"), loadCssText("lm_styles.css")])
      .then(([themeCss, stylesCss]) => {
        injectTheme(themeCss);
        injectStyles(stylesCss);
        return true;
      })
      .catch((error) => {
        console.warn("Failed to load LoRA Manager styles", error);
        stylePromise = null;
        return false;
      });
  }
  return stylePromise;
}
