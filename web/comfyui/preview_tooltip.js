import { api } from "../../scripts/api.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { isVideoPreviewUrl } from "./mediaTypes.js";
import {
  buildLicenseIconData,
  buildNewLicenseIconData,
  createLicenseIconElement,
  createNewLicenseIconElement,
  getUseNewLicenseIcons,
  parseLicenseFlags,
} from "./license_icons.js";

/**
 * Fetch a model's preview URL and license metadata.
 *
 * Returns `null` when the model has no preview: a missing preview is normal
 * (e.g. a LoRA only added to the target node, or a file without a sidecar
 * image), so callers can stay quiet instead of reporting an error.
 *
 * @param {string} modelType - backend model prefix (`loras`, `checkpoints`, …)
 * @param {string} modelName - file name or library-relative path
 */
export async function fetchModelPreviewData(modelType, modelName) {
  const response = await api.fetchApi(
    `/lm/${modelType}/preview-url?name=${encodeURIComponent(modelName)}&license_flags=true`,
    { method: "GET" }
  );
  if (!response.ok) {
    return null;
  }
  const data = await response.json().catch(() => null);
  if (!data || !data.success || !data.preview_url) {
    return null;
  }
  return {
    previewUrl: data.preview_url,
    displayName: data.display_name,
    licenseFlags: parseLicenseFlags(data.license_flags),
    useNewLicenseIcons: data.use_new_license_icons,
  };
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
      // Extra class on the tooltip element. Callers may need to lift it above
      // their own layer (e.g. a floating panel), which is a styling concern.
      className = "",
      // Optional () => DOMRect bounding the area the tooltip may occupy.
      // Callers that live in a split pane can keep the preview off the
      // neighbouring pane (e.g. a detail column with its own actions).
      positionBoundary,
    } = options;

    this.positionBoundary =
      typeof positionBoundary === "function" ? positionBoundary : null;

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

    // Pre-fetch license icon style from LM backend so the tooltip
    // respects the standalone settings toggle as early as possible.
    void getUseNewLicenseIcons();

    this.element = document.createElement("div");
    this.element.className = className
      ? `lm-tooltip ${className}`
      : "lm-tooltip";
    document.body.appendChild(this.element);
    this.hideTimeout = null;
    this.isFromAutocomplete = false;
    this.currentModelName = null;
    // Bumped by hide()/cleanup() so an in-flight show() that resolves after
    // the pointer left does not pop the tooltip back up.
    this.requestSequence = 0;

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
    return fetchModelPreviewData(this.modelType, modelName);
  }

  async resolvePreviewData(modelName) {
    const raw = await this.previewUrlResolver(modelName);
    // A resolver may report "nothing to preview" (missing file, recipe
    // without a preview) by returning null; that is a normal no-op, not an
    // error worth logging.
    if (!raw) return null;
    if (typeof raw === "string") {
      return {
        previewUrl: raw,
        displayName: this.displayNameFormatter(modelName),
      };
    }

    const { previewUrl, displayName, licenseFlags, useNewLicenseIcons } = raw;
    if (!previewUrl) return null;
    return {
      previewUrl,
      displayName:
        displayName !== undefined
          ? displayName
          : this.displayNameFormatter(modelName),
      licenseFlags: parseLicenseFlags(licenseFlags),
      useNewLicenseIcons,
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
        // Re-entering the trigger cancels hide()'s fade-out; restore the
        // opacity it set. Bump the sequence so a show() for another row that
        // is still resolving cannot replace this one when it lands.
        this.requestSequence += 1;
        this.currentModelName = modelName;
        this.element.style.opacity = "1";
        this.position(x, y);
        return;
      }

      const requestSequence = ++this.requestSequence;
      this.currentModelName = modelName;
      const preview = await this.resolvePreviewData(modelName);
      if (requestSequence !== this.requestSequence) return;
      if (!preview) {
        // Nothing to show for this item: drop any tooltip left from the
        // previous one instead of leaving it attached to the new name.
        this.hide();
        return;
      }
      const { previewUrl, displayName, licenseFlags, useNewLicenseIcons } = preview;

      while (this.element.firstChild) {
        this.element.removeChild(this.element.firstChild);
      }

      const mediaContainer = document.createElement("div");
      mediaContainer.className = "lm-tooltip__media-container";

      const isVideo = isVideoPreviewUrl(previewUrl);
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
      this.renderLicenseOverlay(mediaContainer, licenseFlags, useNewLicenseIcons);
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
      if (requestSequence !== this.requestSequence) return;

      requestAnimationFrame(() => {
        if (requestSequence !== this.requestSequence) return;
        this.position(x, y);
        this.element.style.transition = "opacity 0.15s ease";
        this.element.style.opacity = "1";
      });
    } catch (error) {
      console.warn("Failed to load preview:", error);
    }
  }

  /** Resolve the caller's allowed area, if any, into a usable rect. */
  resolvePositionBoundary() {
    if (!this.positionBoundary) return null;
    try {
      const rect = this.positionBoundary();
      return rect && rect.width > 0 ? rect : null;
    } catch {
      return null;
    }
  }

  position(x, y) {
    const rect = this.element.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const boundary = this.resolvePositionBoundary();
    const gap = 10;

    let left = x + gap;
    let top = y + gap;

    // Prefer the right of the anchor, but flip left as soon as that would
    // cross the caller's pane (or the viewport). Inside the quick picker the
    // pane ends where the detail column starts, so the preview stays on the
    // list side instead of covering the selected item's info and actions.
    const rightEdge = boundary ? boundary.right : viewportWidth;
    if (left + rect.width + (boundary ? gap : 0) > rightEdge) {
      left = x - rect.width - gap;
    }

    if (top + rect.height > viewportHeight) {
      top = y - rect.height - gap;
    }

    if (boundary) {
      left = Math.max(boundary.left + gap, left);
    }

    left = Math.max(10, Math.min(left, viewportWidth - rect.width - 10));
    top = Math.max(10, Math.min(top, viewportHeight - rect.height - 10));

    Object.assign(this.element.style, {
      left: `${left}px`,
      top: `${top}px`,
    });
  }

  hide() {
    // Invalidate an in-flight show() as well: without this, leaving the
    // trigger before the preview URL resolved would let show() complete and
    // pop the tooltip up after the pointer is gone.
    this.requestSequence += 1;
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

  renderLicenseOverlay(container, licenseFlags, useNewLicenseIcons) {
    const useNew = useNewLicenseIcons !== undefined ? useNewLicenseIcons : getUseNewLicenseIcons();
    const icons = useNew
      ? buildNewLicenseIconData(licenseFlags)
      : buildLicenseIconData(licenseFlags);
    if (!icons.length) {
      return;
    }

    const overlay = document.createElement("div");
    overlay.className = useNew
      ? "lm-tooltip__license-overlay-new"
      : "lm-tooltip__license-overlay";
    icons.forEach((descriptor) => {
      overlay.appendChild(
        useNew
          ? createNewLicenseIconElement(descriptor)
          : createLicenseIconElement(descriptor)
      );
    });
    container.appendChild(overlay);
  }

  cleanup() {
    this.requestSequence += 1;
    if (this.hideTimeout) {
      clearTimeout(this.hideTimeout);
    }
    document.removeEventListener("click", this.globalClickHandler);
    document.removeEventListener("scroll", this.globalScrollHandler, true);
    this.element.remove();
  }
}
