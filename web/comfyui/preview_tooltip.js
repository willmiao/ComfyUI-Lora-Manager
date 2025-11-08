import { api } from "../../scripts/api.js";
import { ensureLmStyles } from "./lm_styles_loader.js";

const LICENSE_ICON_PATH = "/loras_static/images/tabler/";
const LICENSE_FLAG_BITS = {
  allowNoCredit: 1 << 0,
  allowOnImages: 1 << 1,
  allowOnCivitai: 1 << 2,
  allowRental: 1 << 3,
  allowSellingModels: 1 << 4,
  allowDerivatives: 1 << 5,
  allowRelicense: 1 << 6,
};

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

function parseLicenseFlags(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

function buildLicenseIconData(licenseFlags) {
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

function createLicenseIconElement({ icon, label }) {
  const element = document.createElement("span");
  element.className = "lm-tooltip__license-icon";
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", label);
  element.title = label;
  element.style.setProperty("--license-icon-image", `url('${LICENSE_ICON_PATH}${icon}')`);
  return element;
}

/**
 * Lightweight preview tooltip that can display images or videos for different model types.
 */
export class PreviewTooltip {
  constructor(options = {}) {
    const {
      modelType = "loras",
      previewUrlResolver,
      displayNameFormatter,
    } = options;

    this.modelType = modelType;
    this.previewUrlResolver =
      typeof previewUrlResolver === "function"
        ? previewUrlResolver
        : (name) => this.defaultPreviewUrlResolver(name);
    this.displayNameFormatter =
      typeof displayNameFormatter === "function"
        ? displayNameFormatter
        : (name) => name;

    ensureLmStyles();

    this.element = document.createElement("div");
    this.element.className = "lm-tooltip";
    document.body.appendChild(this.element);
    this.hideTimeout = null;
    this.isFromAutocomplete = false;
    this.currentModelName = null;

    this.globalClickHandler = (event) => {
      if (!event.target.closest(".comfy-autocomplete-dropdown")) {
        this.hide();
      }
    };
    document.addEventListener("click", this.globalClickHandler);

    this.globalScrollHandler = () => this.hide();
    document.addEventListener("scroll", this.globalScrollHandler, true);
  }

  async defaultPreviewUrlResolver(modelName) {
    const response = await api.fetchApi(
      `/lm/${this.modelType}/preview-url?name=${encodeURIComponent(modelName)}&license_flags=true`,
      { method: "GET" }
    );
    if (!response.ok) {
      throw new Error("Failed to fetch preview URL");
    }
    const data = await response.json();
    if (!data.success || !data.preview_url) {
      throw new Error("No preview available");
    }
    return {
      previewUrl: data.preview_url,
      displayName: data.display_name ?? modelName,
      licenseFlags: parseLicenseFlags(data.license_flags),
    };
  }

  async resolvePreviewData(modelName) {
    const raw = await this.previewUrlResolver(modelName);
    if (!raw) {
      throw new Error("No preview data returned");
    }
    if (typeof raw === "string") {
      return {
        previewUrl: raw,
        displayName: this.displayNameFormatter(modelName),
      };
    }

    const { previewUrl, displayName, licenseFlags } = raw;
    if (!previewUrl) {
      throw new Error("No preview URL available");
    }
    return {
      previewUrl,
      displayName:
        displayName !== undefined
          ? displayName
          : this.displayNameFormatter(modelName),
      licenseFlags: parseLicenseFlags(licenseFlags),
    };
  }

  async show(modelName, x, y, fromAutocomplete = false) {
    try {
      if (this.hideTimeout) {
        clearTimeout(this.hideTimeout);
        this.hideTimeout = null;
      }

      this.isFromAutocomplete = fromAutocomplete;

      if (
        this.element.style.display === "block" &&
        this.currentModelName === modelName
      ) {
        this.position(x, y);
        return;
      }

      this.currentModelName = modelName;
      const { previewUrl, displayName, licenseFlags } = await this.resolvePreviewData(
        modelName
      );

      while (this.element.firstChild) {
        this.element.removeChild(this.element.firstChild);
      }

      const mediaContainer = document.createElement("div");
      mediaContainer.className = "lm-tooltip__media-container";

      const isVideo = previewUrl.endsWith(".mp4");
      const mediaElement = isVideo
        ? document.createElement("video")
        : document.createElement("img");
      mediaElement.classList.add("lm-tooltip__media");

      if (isVideo) {
        mediaElement.autoplay = true;
        mediaElement.loop = true;
        mediaElement.muted = true;
        mediaElement.controls = false;
      }

      const nameLabel = document.createElement("div");
      nameLabel.textContent = displayName;
      nameLabel.className = "lm-tooltip__label";

      mediaContainer.appendChild(mediaElement);
      this.renderLicenseOverlay(mediaContainer, licenseFlags);
      mediaContainer.appendChild(nameLabel);
      this.element.appendChild(mediaContainer);

      this.element.style.opacity = "0";
      this.element.style.display = "block";

      const waitForLoad = () =>
        new Promise((resolve) => {
          if (isVideo) {
            if (mediaElement.readyState >= 2) {
              resolve();
            } else {
              mediaElement.addEventListener("loadeddata", resolve, {
                once: true,
              });
              mediaElement.addEventListener("error", resolve, { once: true });
            }
          } else if (mediaElement.complete) {
            resolve();
          } else {
            mediaElement.addEventListener("load", resolve, { once: true });
            mediaElement.addEventListener("error", resolve, { once: true });
          }

          setTimeout(resolve, 1000);
        });

      mediaElement.src = previewUrl;
      await waitForLoad();

      requestAnimationFrame(() => {
        this.position(x, y);
        this.element.style.transition = "opacity 0.15s ease";
        this.element.style.opacity = "1";
      });
    } catch (error) {
      console.warn("Failed to load preview:", error);
    }
  }

  position(x, y) {
    const rect = this.element.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = x + 10;
    let top = y + 10;

    if (left + rect.width > viewportWidth) {
      left = x - rect.width - 10;
    }

    if (top + rect.height > viewportHeight) {
      top = y - rect.height - 10;
    }

    left = Math.max(10, Math.min(left, viewportWidth - rect.width - 10));
    top = Math.max(10, Math.min(top, viewportHeight - rect.height - 10));

    Object.assign(this.element.style, {
      left: `${left}px`,
      top: `${top}px`,
    });
  }

  hide() {
    if (this.element.style.display === "block") {
      this.element.style.opacity = "0";
      this.hideTimeout = setTimeout(() => {
        this.element.style.display = "none";
        this.currentModelName = null;
        this.isFromAutocomplete = false;
        const video = this.element.querySelector("video");
        if (video) {
          video.pause();
        }
        this.hideTimeout = null;
      }, 150);
    }
  }

  renderLicenseOverlay(container, licenseFlags) {
    const icons = buildLicenseIconData(licenseFlags);
    if (!icons.length) {
      return;
    }

    const overlay = document.createElement("div");
    overlay.className = "lm-tooltip__license-overlay";
    icons.forEach((descriptor) => {
      overlay.appendChild(createLicenseIconElement(descriptor));
    });
    container.appendChild(overlay);
  }

  cleanup() {
    if (this.hideTimeout) {
      clearTimeout(this.hideTimeout);
    }
    document.removeEventListener("click", this.globalClickHandler);
    document.removeEventListener("scroll", this.globalScrollHandler, true);
    this.element.remove();
  }
}
