import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";

/**
 * Shared license-icon helpers for the ComfyUI widgets.
 *
 * CivitAI permissions are cached as a compact bitfield (`license_flags`). This
 * module turns that bitfield into the two icon sets the UI supports: the
 * classic "restriction" icons and the newer CivitAI-style allowed/denied
 * icons. The active set follows the standalone `use_new_license_icons`
 * setting, cached locally so a widget can render synchronously.
 */

export const LICENSE_ICON_PATH = lmUrl("/loras_static/images/tabler/");

export const LICENSE_FLAG_BITS = {
  allowNoCredit: 1 << 0,
  allowOnImages: 1 << 1,
  allowOnCivitai: 1 << 2,
  allowRental: 1 << 3,
  allowSellingModels: 1 << 4,
  allowDerivatives: 1 << 5,
  allowRelicense: 1 << 6,
};

// Fields written into `civitai.model` by the backend when license data exists.
const LICENSE_MODEL_FIELDS = [
  "allowNoCredit",
  "allowCommercialUse",
  "allowDerivatives",
  "allowDifferentLicense",
];

// ── Set 1 (classic) icon definitions ──

const LICENSE_ICON_COPY = {
  credit: "Creator credit required",
  image: "No selling generated content",
  rentcivit: "No Civitai generation",
  rent: "No generation services",
  sell: "No selling models",
  derivatives: "No sharing merges",
  relicense: "Same permissions required",
};

const COMMERCIAL_ICON_CONFIG = [
  { bit: LICENSE_FLAG_BITS.allowOnImages, icon: "photo-off.svg", label: LICENSE_ICON_COPY.image },
  { bit: LICENSE_FLAG_BITS.allowOnCivitai, icon: "brush-off.svg", label: LICENSE_ICON_COPY.rentcivit },
  { bit: LICENSE_FLAG_BITS.allowRental, icon: "world-off.svg", label: LICENSE_ICON_COPY.rent },
  { bit: LICENSE_FLAG_BITS.allowSellingModels, icon: "shopping-cart-off.svg", label: LICENSE_ICON_COPY.sell },
];

// ── Set 2 (new CivitAI-style) icon definitions ──

const NEW_LICENSE_ICON_COPY = {
  commercial: { allowed: "Commercial use allowed", denied: "No commercial use" },
  genServices: { allowed: "Generation services allowed", denied: "No generation services" },
  credit: { allowed: "No credit required", denied: "Creator credit required" },
  derivatives: { allowed: "Merges allowed", denied: "No merges allowed" },
  relicense: { allowed: "Different permissions allowed on merges", denied: "Same permissions required on merges" },
};

const NEW_ICON_CONFIG = [
  {
    icon: "currency-dollar.svg",
    labelKey: "commercial",
    allowedFn: (flags) => (flags & LICENSE_FLAG_BITS.allowOnImages) !== 0 || (flags & LICENSE_FLAG_BITS.allowSellingModels) !== 0,
  },
  {
    icon: "brush.svg",
    labelKey: "genServices",
    allowedFn: (flags) => (flags & LICENSE_FLAG_BITS.allowOnCivitai) !== 0 || (flags & LICENSE_FLAG_BITS.allowRental) !== 0,
  },
  {
    icon: "user.svg",
    labelKey: "credit",
    allowedFn: (flags) => (flags & LICENSE_FLAG_BITS.allowNoCredit) !== 0,
  },
  {
    icon: "git-merge.svg",
    labelKey: "derivatives",
    allowedFn: (flags) => (flags & LICENSE_FLAG_BITS.allowDerivatives) !== 0,
  },
  {
    icon: "license.svg",
    labelKey: "relicense",
    allowedFn: (flags) => (flags & LICENSE_FLAG_BITS.allowRelicense) !== 0,
  },
];

export function parseLicenseFlags(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

/**
 * Whether `civitai` carries real license metadata.
 *
 * The lightweight cache keeps only `civitai.model.type`, and the aggregated
 * `license_flags` default to "everything allowed" when no license data was
 * ever seen. Requiring at least one license field here keeps the UI from
 * presenting that default as a real permission grant.
 */
export function hasLicenseMetadata(civitai) {
  const model = civitai?.model;
  if (!model || typeof model !== "object") return false;
  return LICENSE_MODEL_FIELDS.some((field) =>
    Object.prototype.hasOwnProperty.call(model, field)
  );
}

export function buildLicenseIconData(licenseFlags) {
  if (licenseFlags == null) {
    return [];
  }

  const icons = [];

  if ((licenseFlags & LICENSE_FLAG_BITS.allowNoCredit) === 0) {
    icons.push({ icon: "user-check.svg", label: LICENSE_ICON_COPY.credit });
  }

  COMMERCIAL_ICON_CONFIG.forEach((config) => {
    if ((licenseFlags & config.bit) === 0) {
      icons.push({ icon: config.icon, label: config.label });
    }
  });

  if ((licenseFlags & LICENSE_FLAG_BITS.allowDerivatives) === 0) {
    icons.push({ icon: "exchange-off.svg", label: LICENSE_ICON_COPY.derivatives });
  }

  if ((licenseFlags & LICENSE_FLAG_BITS.allowRelicense) === 0) {
    icons.push({ icon: "rotate-2.svg", label: LICENSE_ICON_COPY.relicense });
  }

  return icons;
}

export function buildNewLicenseIconData(licenseFlags) {
  if (licenseFlags == null) {
    return [];
  }

  return NEW_ICON_CONFIG.map((config) => {
    const allowed = config.allowedFn(licenseFlags);
    const label = allowed
      ? NEW_LICENSE_ICON_COPY[config.labelKey].allowed
      : NEW_LICENSE_ICON_COPY[config.labelKey].denied;
    return {
      icon: config.icon,
      label,
      allowed,
    };
  });
}

export function createLicenseIconElement({ icon, label }, className = "lm-tooltip__license-icon") {
  const element = document.createElement("span");
  element.className = className;
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", label);
  element.title = label;
  element.style.setProperty("--license-icon-image", `url('${LICENSE_ICON_PATH}${icon}')`);
  return element;
}

export function createNewLicenseIconElement(
  { icon, label, allowed },
  className = "lm-tooltip__license-icon-new"
) {
  const element = document.createElement("span");
  element.className = `${className} ${allowed ? "allowed" : "denied"}`;
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", label);
  element.title = label;
  element.style.setProperty("--license-icon-image", `url('${LICENSE_ICON_PATH}${icon}')`);
  return element;
}

// ── License icon style setting ──

const LICENSE_ICON_STORAGE_KEY = "lm_license_icon_new_style";

// Module-level cache: null = not yet initialized
let _useNewIconsCached = null;
let _settingRequest = null;

function readStoredSetting() {
  try {
    const stored = localStorage.getItem(LICENSE_ICON_STORAGE_KEY);
    return stored === null ? null : stored === "true";
  } catch (_) {
    return null;
  }
}

// Fetch the setting from the LoRA Manager backend API via the proper
// ComfyUI api helper (handles base URL, credentials, etc.).
// Stores the result in both the in-memory cache and localStorage so the
// value survives page reloads even before the API responds.
async function _fetchLicenseIconSetting() {
  if (!_settingRequest) {
    _settingRequest = (async () => {
      try {
        const response = await api.fetchApi("/lm/settings");
        if (response.ok) {
          const data = await response.json();
          const value = data.use_new_license_icons !== false;
          _useNewIconsCached = value;
          try { localStorage.setItem(LICENSE_ICON_STORAGE_KEY, String(value)); } catch (_) {}
        }
      } catch (_) {
        // API not available; cached/localStorage fallback stays in place
      }
    })().finally(() => {
      _settingRequest = null;
    });
  }
  return _settingRequest;
}

/** Synchronous read used where the icon set must be known immediately. */
export function getUseNewLicenseIcons() {
  // 1) In-memory cache hit
  if (_useNewIconsCached !== null) {
    return _useNewIconsCached;
  }

  // 2) localStorage — survives page reloads
  const stored = readStoredSetting();
  if (stored !== null) {
    _useNewIconsCached = stored;
    // Refresh from API in background for next time
    void _fetchLicenseIconSetting();
    return _useNewIconsCached;
  }

  // 3) First-ever run: kick off API fetch, default to new style
  void _fetchLicenseIconSetting();
  return true;
}

/**
 * Resolve the icon style, waiting for the first settings request when neither
 * the in-memory cache nor localStorage can answer.
 */
export async function ensureUseNewLicenseIcons() {
  if (_useNewIconsCached !== null) {
    return _useNewIconsCached;
  }

  const stored = readStoredSetting();
  if (stored !== null) {
    _useNewIconsCached = stored;
    void _fetchLicenseIconSetting();
    return stored;
  }

  await _fetchLicenseIconSetting();
  return _useNewIconsCached ?? true;
}
