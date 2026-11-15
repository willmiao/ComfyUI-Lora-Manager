import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyLmAccent,
  getLmAccent,
  LM_THEME_ACCENT_DEFAULT,
  LM_THEME_ACCENT_PRESETS,
  LM_THEME_ACCENT_SETTING_ID,
  normalizeLmAccent,
  renderLmAccentSetting,
} from "../../../web/comfyui/lm_theme.js";

// settings.js registers through app.registerExtension at import time; capture
// the extension so the wiring can be asserted without ComfyUI running.
const { APP_MODULE, registeredExtensions } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  registeredExtensions: [],
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: (extension) => registeredExtensions.push(extension),
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: { get: () => undefined, set: async () => {} },
    },
  },
}));

// Regression guard for the LM widget accent: it is the only theme dimension
// LM owns (surfaces/text/borders stay aliased to the ComfyUI palette), so the
// override mechanism and the settings control have to keep working.

const root = () => document.documentElement;

beforeEach(() => {
  root().style.removeProperty("--lm-base-accent");
  root().style.removeProperty("--lm-base-on-accent");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("accent normalization", () => {
  it("normalizes valid hex colors and rejects everything else", () => {
    expect(normalizeLmAccent("#ABC")).toBe("#aabbcc");
    expect(normalizeLmAccent("#4299E1")).toBe("#4299e1");
    expect(normalizeLmAccent("  #4299e1cc  ")).toBe("#4299e1cc");

    for (const value of [undefined, null, "", "#12345", "rgb(1,2,3)", 42, "#"]) {
      expect(normalizeLmAccent(value)).toBeNull();
    }
  });

  it("accepts the value format ComfyUI's color setting persists", () => {
    // FormColorPicker.vue stores hex without the leading "#" (PrimeVue
    // contract), so onChange hands us "c68f27", not "#c68f27". Rejecting that
    // form made the accent silently do nothing.
    expect(normalizeLmAccent("c68f27")).toBe("#c68f27");
    expect(normalizeLmAccent("C68F27")).toBe("#c68f27");
    expect(normalizeLmAccent("abc")).toBe("#aabbcc");
    expect(normalizeLmAccent("c68f27cc")).toBe("#c68f27cc");

    expect(applyLmAccent("c68f27")).toBe("#c68f27");
    expect(root().style.getPropertyValue("--lm-base-accent")).toBe("#c68f27");
  });
});

describe("applying the accent", () => {
  it("writes the override to the base token, not the context token", () => {
    // --lm-accent is declared per context in lm_theme.css, so an inline value
    // for it on <html> would be shadowed by those declarations. The override
    // has to go to --lm-base-accent, which only :root declares.
    expect(applyLmAccent("#7c3aed")).toBe("#7c3aed");
    expect(root().style.getPropertyValue("--lm-base-accent")).toBe("#7c3aed");
    expect(root().style.getPropertyValue("--lm-accent")).toBe("");
    expect(getLmAccent()).toBe("#7c3aed");
  });

  it("clears the override for the default and for invalid values", () => {
    applyLmAccent("#7c3aed");

    expect(applyLmAccent(LM_THEME_ACCENT_DEFAULT)).toBeNull();
    expect(root().style.getPropertyValue("--lm-base-accent")).toBe("");
    expect(root().style.getPropertyValue("--lm-base-on-accent")).toBe("");

    applyLmAccent("#7c3aed");
    expect(applyLmAccent("not-a-color")).toBeNull();
    expect(getLmAccent()).toBe(LM_THEME_ACCENT_DEFAULT);
  });

  it("keeps accent text readable on any accent", () => {
    // Dark accents keep white text; pale accents switch to near-black.
    applyLmAccent("#0b3d91");
    expect(root().style.getPropertyValue("--lm-base-on-accent")).toBe("#fff");

    applyLmAccent("#ffd54a");
    expect(root().style.getPropertyValue("--lm-base-on-accent")).toBe("#111");
  });

  it("treats the default accent as the brand look, not a computed one", () => {
    // Selecting the default swatch must restore white-on-accent text rather
    // than the #111 the contrast maths would pick for #4299e1.
    applyLmAccent("#7c3aed");
    applyLmAccent(LM_THEME_ACCENT_DEFAULT);
    expect(root().style.getPropertyValue("--lm-base-on-accent")).toBe("");
  });
});

describe("accent settings control", () => {
  const render = (value) => {
    const setter = vi.fn();
    const element = renderLmAccentSetting("Widget accent color", setter, value);
    return { element, setter };
  };

  it("renders one swatch per preset plus the custom picker", () => {
    const { element } = render(LM_THEME_ACCENT_DEFAULT);
    const swatches = element.querySelectorAll(".lm-accent-setting__swatch");

    expect(swatches).toHaveLength(LM_THEME_ACCENT_PRESETS.length);
    LM_THEME_ACCENT_PRESETS.forEach((preset, index) => {
      expect(swatches[index].getAttribute("aria-label")).toBe(preset.name);
      expect(swatches[index].style.getPropertyValue("--lm-accent-swatch-color")).toBe(preset.color);
    });
    expect(element.querySelectorAll('input[type="color"]')).toHaveLength(1);
  });

  it("marks the active preset, including a value stored without '#'", () => {
    const { element } = render("8b5cf6"); // ComfyUI's storage format
    const pressed = [...element.querySelectorAll('[aria-pressed="true"]')];

    expect(pressed).toHaveLength(1);
    expect(pressed[0].getAttribute("aria-label")).toBe("Violet");
    // The custom chip shows the normalized current value.
    expect(element.querySelector('input[type="color"]').value).toBe("#8b5cf6");
  });

  it("marks no preset for a custom accent", () => {
    const { element } = render("#123456");
    expect(element.querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
    expect(element.querySelector('input[type="color"]').value).toBe("#123456");
  });

  it("reports a clicked swatch through the setter", () => {
    const { element, setter } = render(LM_THEME_ACCENT_DEFAULT);
    const teal = [...element.querySelectorAll(".lm-accent-setting__swatch")].find(
      (swatch) => swatch.getAttribute("aria-label") === "Teal",
    );

    teal.click();
    expect(setter).toHaveBeenCalledWith("#14b8a6");
  });

  it("reports a picked custom color through the setter", () => {
    const { element, setter } = render(LM_THEME_ACCENT_DEFAULT);
    const input = element.querySelector('input[type="color"]');

    input.value = "#abcdef";
    input.dispatchEvent(new Event("change"));
    expect(setter).toHaveBeenCalledWith("#abcdef");
  });
});

describe("settings wiring", () => {
  it("registers the accent setting with the swatch renderer", async () => {
    // Importing settings.js runs app.registerExtension; the mocked app captures
    // it. This guards the one link the live check covered by hand: the setting
    // must keep using the custom renderer and the DOM-writing onChange, or the
    // swatches silently disappear / the accent silently stops applying.
    await import("../../../web/comfyui/settings.js");

    const extension = registeredExtensions.find((entry) => entry.name === "LoraManager.Settings");
    expect(extension).toBeDefined();

    const setting = extension.settings.find((entry) => entry.id === LM_THEME_ACCENT_SETTING_ID);
    expect(setting).toBeDefined();
    expect(setting.type).toBe(renderLmAccentSetting);
    expect(setting.defaultValue).toBe(LM_THEME_ACCENT_DEFAULT);

    setting.onChange("#123456");
    expect(document.documentElement.style.getPropertyValue("--lm-base-accent")).toBe("#123456");
  });
});
