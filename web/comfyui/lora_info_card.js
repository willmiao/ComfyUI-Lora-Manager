import { app } from "../../scripts/app.js";
import { createFloatingPanel } from "./floating_panel.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { findLoraIndex } from "./lora_selection.js";
import { normalizeLoraNameKey, syncClipStrengthIfCollapsed } from "./loras_widget_utils.js";
import { isVideoPreviewUrl } from "./mediaTypes.js";
import {
  fetchLoraDetails,
  formatUsageTips,
  openLoraManager,
  refreshLoraMetadata,
  saveLoraNotes,
} from "./lora_canvas_api.js";
import { openLoraQuickPanel } from "./lora_quick_panel.js";

const PANEL_GAP = 10;
const ACTIVE_TAB_KEY = "lm:info-card:active-tab";
const VALID_TABS = new Set(["overview", "notes", "description"]);
let activeInfoCard = null;

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export function sanitizeDescriptionHtml(value) {
  const documentNode = new DOMParser().parseFromString(String(value || ""), "text/html");
  documentNode.querySelectorAll("script, style, iframe, object, embed, link, meta, base, form, input, button, svg, math")
    .forEach((element) => element.remove());
  documentNode.querySelectorAll("*").forEach((element) => {
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on")) {
        element.removeAttribute(attribute.name);
        continue;
      }
      if (name === "style") {
        const color = element.style.color;
        const backgroundColor = element.style.backgroundColor;
        element.removeAttribute(attribute.name);
        if (color) element.style.color = color;
        if (backgroundColor) element.style.backgroundColor = backgroundColor;
        continue;
      }
      if (name !== "href" && name !== "src") continue;
      const url = attribute.value.trim();
      const safe = /^(https?:|mailto:)/i.test(url) || /^(#|\/(?!\/)|\.{1,2}\/)/.test(url);
      if (!safe) element.removeAttribute(attribute.name);
    }
    if (element.tagName === "A") {
      element.setAttribute("target", "_blank");
      element.setAttribute("rel", "noopener noreferrer nofollow");
    }
  });
  return documentNode.body.innerHTML;
}

export function computeInfoCardPosition(anchor, panel, viewport, gap = PANEL_GAP, margin = 12) {
  const candidates = [
    { left: anchor.right + gap, top: anchor.top },
    { left: anchor.left - panel.width - gap, top: anchor.top },
    { left: anchor.left, top: anchor.bottom + gap },
    { left: anchor.left, top: anchor.top - panel.height - gap },
  ];
  const fitting = candidates.find((candidate) =>
    candidate.left >= margin &&
    candidate.top >= margin &&
    candidate.left + panel.width <= viewport.width - margin &&
    candidate.top + panel.height <= viewport.height - margin
  );
  if (fitting) return fitting;

  const right = candidates[0];
  return {
    left: Math.max(margin, Math.min(right.left, viewport.width - panel.width - margin)),
    top: Math.max(margin, Math.min(right.top, viewport.height - panel.height - margin)),
  };
}

export function updateLoraStrength(widget, loraName, field, rawValue) {
  const value = Number(rawValue);
  if (!Number.isFinite(value)) return false;
  const loras = Array.isArray(widget?.value) ? widget.value.slice() : [];
  const index = findLoraIndex(loras, normalizeLoraNameKey(loraName));
  if (index < 0) return false;
  const entry = { ...loras[index], [field]: value.toFixed(2) };
  if (field === "strength") syncClipStrengthIfCollapsed(entry);
  loras[index] = entry;
  widget.value = loras;
  widget.callback?.(loras);
  return true;
}

export class LoraInfoCard {
  constructor({ node, widget, loraName, anchorElement }) {
    this.node = node;
    this.widget = widget;
    this.loraName = loraName;
    this.details = null;
    this.activeTab = "overview";
    try {
      const savedTab = localStorage.getItem(ACTIVE_TAB_KEY);
      if (VALID_TABS.has(savedTab)) this.activeTab = savedTab;
    } catch { /* default */ }
    this.followFrame = null;
    this.userMoved = false;
    this.panel = null;
    this.notesDraft = null;
    this.originalNotes = "";
    this.savingNotes = false;
  }

  open() {
    ensureLmStyles();
    this.panel = createFloatingPanel({
      title: "LoRA info",
      context: this.loraName,
      className: "lm-info-card",
      width: 410,
      height: 640,
      minWidth: 340,
      minHeight: 380,
      onClose: () => {
        cancelAnimationFrame(this.followFrame);
        document.removeEventListener("pointerdown", this.onOutsidePointer, true);
        if (activeInfoCard === this) activeInfoCard = null;
      },
      onDragStart: () => { this.userMoved = true; },
    });
    this.onOutsidePointer = (event) => {
      if (!this.panel.element.contains(event.target) && !event.target.closest?.(".lm-lora-info-button")) {
        this.close();
      }
    };
    setTimeout(() => document.addEventListener("pointerdown", this.onOutsidePointer, true), 0);
    this.buildLoading();
    this.followAnchor();
    this.loadDetails();
    return this;
  }

  close() {
    this.panel?.close();
  }

  anchorRect() {
    if (this.node?.id != null) {
      const nodeElement = document.querySelector(`[data-node-id="${this.node.id}"]`);
      if (nodeElement?.isConnected) return nodeElement.getBoundingClientRect();
    }
    const canvas = app.canvas;
    const scale = canvas?.ds?.scale;
    const offset = canvas?.ds?.offset;
    const canvasElement = canvas?.canvas;
    if (!canvasElement || !this.node?.pos || !this.node?.size) return null;
    const canvasRect = canvasElement.getBoundingClientRect();
    const titleHeight = globalThis.LiteGraph?.NODE_TITLE_HEIGHT || 30;
    const zoom = scale || 1;
    const [offsetX = 0, offsetY = 0] = offset || [];
    const left = canvasRect.left + (this.node.pos[0] + offsetX) * zoom;
    const top = canvasRect.top + (this.node.pos[1] - titleHeight + offsetY) * zoom;
    return {
      left,
      top,
      right: left + this.node.size[0] * zoom,
      bottom: top + (this.node.size[1] + titleHeight) * zoom,
    };
  }

  followAnchor() {
    if (!this.panel?.isOpen()) return;
    if (!this.userMoved) {
      const anchor = this.anchorRect();
      if (!anchor) {
        this.close();
        return;
      }
      const panelRect = this.panel.getRect();
      const position = computeInfoCardPosition(anchor, panelRect, {
        width: window.innerWidth,
        height: window.innerHeight,
      });
      this.panel.setPosition(position.left, position.top);
    }
    this.followFrame = requestAnimationFrame(() => this.followAnchor());
  }

  buildLoading() {
    this.panel.body.replaceChildren();
    this.panel.body.appendChild(el("div", "lm-info-card__loading", "Loading local details…"));
    this.panel.footer.replaceChildren();
  }

  async loadDetails() {
    try {
      const details = await fetchLoraDetails(this.loraName);
      if (!this.panel?.isOpen()) return;
      this.details = details;
      if (!this.notesDirty()) {
        this.originalNotes = details.notes || "";
        this.notesDraft = this.originalNotes;
      }
      this.render();
    } catch (error) {
      if (!this.panel?.isOpen()) return;
      this.panel.body.replaceChildren();
      this.panel.body.appendChild(el("div", "lm-info-card__error", error.message));
      this.renderFooter();
    }
  }

  currentEntry() {
    const loras = Array.isArray(this.widget?.value) ? this.widget.value : [];
    const index = findLoraIndex(loras, normalizeLoraNameKey(this.loraName));
    return index >= 0 ? loras[index] : null;
  }

  render() {
    const { body } = this.panel;
    body.replaceChildren();
    this.panel.setContext(this.details.model_name || this.loraName);

    const tabs = el("nav", "lm-info-card__tabs");
    tabs.setAttribute("aria-label", "LoRA information sections");
    this.tabButtons = {};
    for (const [id, label] of [["overview", "Overview"], ["notes", "Notes"], ["description", "Description"]]) {
      const button = el("button", "lm-info-card__tab", label);
      button.type = "button";
      button.classList.toggle("is-active", this.activeTab === id);
      button.setAttribute("aria-pressed", String(this.activeTab === id));
      button.addEventListener("click", () => this.setActiveTab(id));
      this.tabButtons[id] = button;
      tabs.appendChild(button);
    }
    body.appendChild(tabs);
    this.tabContent = el("div", "lm-info-card__tab-content");
    body.appendChild(this.tabContent);
    this.statusElement = el("div", "lm-info-card__status", "Local library data");
    body.appendChild(this.statusElement);
    this.renderActiveTab();
    this.renderFooter();
  }

  setActiveTab(tab) {
    if (!VALID_TABS.has(tab)) return;
    this.activeTab = tab;
    try { localStorage.setItem(ACTIVE_TAB_KEY, tab); } catch { /* cosmetic only */ }
    for (const [id, button] of Object.entries(this.tabButtons)) {
      button.classList.toggle("is-active", id === tab);
      button.setAttribute("aria-pressed", String(id === tab));
    }
    this.renderActiveTab();
  }

  renderActiveTab() {
    this.tabContent.replaceChildren();
    if (this.activeTab === "notes") this.renderNotes();
    else if (this.activeTab === "description") this.renderDescription();
    else this.renderOverview();
  }

  renderOverview() {
    const details = this.details;
    const entry = this.currentEntry();
    const header = el("div", "lm-info-card__identity");
    if (details.preview_url) {
      const video = isVideoPreviewUrl(details.preview_url);
      const preview = el(video ? "video" : "img", "lm-info-card__preview");
      preview.src = details.preview_url;
      if (video) {
        preview.muted = true;
        preview.loop = true;
        preview.autoplay = true;
        preview.playsInline = true;
      } else {
        preview.alt = "";
      }
      header.appendChild(preview);
    }
    const identityText = el("div", "lm-info-card__identity-text");
    identityText.appendChild(el("h2", "lm-info-card__name", details.model_name || this.loraName));
    identityText.appendChild(el("div", "lm-info-card__meta", details.base_model || "Base model unknown"));
    const relativePath = [details.folder, details.file_name].filter(Boolean).join("/") || this.loraName;
    identityText.appendChild(el("div", "lm-info-card__path", relativePath));
    header.appendChild(identityText);
    this.tabContent.appendChild(header);

    if (entry) {
      const strengths = el("section", "lm-info-card__section");
      strengths.appendChild(el("h3", "lm-info-card__heading", "Current row"));
      strengths.appendChild(this.strengthInput("Strength", "strength", entry.strength));
      if (entry.expanded || Number(entry.clipStrength) !== Number(entry.strength)) {
        strengths.appendChild(this.strengthInput("Clip strength", "clipStrength", entry.clipStrength));
      }
      this.tabContent.appendChild(strengths);
    } else {
      this.tabContent.appendChild(el("div", "lm-info-card__warning", "This LoRA is no longer on the node. Metadata is read-only."));
    }

    const triggerSection = el("section", "lm-info-card__section");
    triggerSection.appendChild(el("h3", "lm-info-card__heading", "Trigger words"));
    const words = details.civitai?.trainedWords || [];
    const chips = el("div", "lm-info-card__chips");
    if (words.length) {
      words.forEach((word) => chips.appendChild(el("span", "lm-info-card__chip", word)));
    } else {
      chips.appendChild(el("span", "lm-info-card__empty", "No trigger words in the local metadata."));
    }
    triggerSection.appendChild(chips);
    if (words.length) {
      triggerSection.appendChild(el("p", "lm-info-card__hint", "Enable or disable these in a connected TriggerWord Toggle node."));
    }
    this.tabContent.appendChild(triggerSection);

    const usage = formatUsageTips(details);
    if (usage) {
      const usageSection = el("section", "lm-info-card__section");
      usageSection.appendChild(el("h3", "lm-info-card__heading", "Usage tips"));
      usageSection.appendChild(el("div", "lm-info-card__usage", usage));
      this.tabContent.appendChild(usageSection);
    }
  }

  strengthInput(label, field, value) {
    const row = el("label", "lm-info-card__strength");
    row.appendChild(el("span", "", label));
    const input = el("input", "lm-info-card__number");
    input.type = "number";
    input.step = "0.05";
    input.value = Number(value ?? 1).toFixed(2);
    input.addEventListener("change", () => {
      if (!updateLoraStrength(this.widget, this.loraName, field, input.value)) {
        this.setStatus("The LoRA row no longer exists");
        return;
      }
      input.value = Number(input.value).toFixed(2);
      this.setStatus(`Updated ${label.toLowerCase()}`);
    });
    row.appendChild(input);
    return row;
  }

  notesDirty() {
    return this.notesDraft !== null && this.notesDraft !== this.originalNotes;
  }

  renderNotes() {
    const section = el("section", "lm-info-card__notes-section");
    section.appendChild(el("h3", "lm-info-card__heading", "Your notes"));
    const textarea = el("textarea", "lm-info-card__notes");
    textarea.value = this.notesDraft ?? this.originalNotes;
    textarea.placeholder = "Add notes about this LoRA…";
    textarea.disabled = this.savingNotes || !this.details.file_path;
    textarea.addEventListener("input", () => {
      this.notesDraft = textarea.value;
      save.disabled = !this.notesDirty() || this.savingNotes;
    });
    section.appendChild(textarea);
    const save = el("button", "lm-info-card__primary", this.savingNotes ? "Saving…" : "Save notes");
    save.type = "button";
    save.disabled = !this.notesDirty() || this.savingNotes || !this.details.file_path;
    save.addEventListener("click", () => this.saveNotes());
    section.appendChild(save);
    this.tabContent.appendChild(section);
  }

  async saveNotes() {
    if (!this.notesDirty() || this.savingNotes) return;
    this.savingNotes = true;
    this.setStatus("Saving notes…");
    try {
      await saveLoraNotes(this.details.file_path, this.notesDraft);
      this.originalNotes = this.notesDraft;
      this.details.notes = this.originalNotes;
      this.setStatus("Notes saved");
      this.renderActiveTab();
    } catch (error) {
      this.setStatus(error.message);
    } finally {
      this.savingNotes = false;
      if (this.activeTab === "notes") this.renderActiveTab();
    }
  }

  renderDescription() {
    const sections = [
      ["About this version", this.details.description || this.details.civitai?.description],
      ["Model description", this.details.modelDescription || this.details.civitai?.model?.description],
    ];
    let hasContent = false;
    for (const [heading, value] of sections) {
      if (!value) continue;
      hasContent = true;
      const section = el("section", "lm-info-card__description-section");
      section.appendChild(el("h3", "lm-info-card__heading", heading));
      const content = el("div", "lm-info-card__description");
      content.innerHTML = sanitizeDescriptionHtml(value);
      section.appendChild(content);
      this.tabContent.appendChild(section);
    }
    if (!hasContent) {
      this.tabContent.appendChild(el("div", "lm-info-card__empty", "No description in the local metadata."));
    }
  }

  renderFooter() {
    const { footer } = this.panel;
    footer.replaceChildren();
    const full = el("button", "lm-info-card__secondary", "Full details");
    full.type = "button";
    full.addEventListener("click", () => openLoraManager(this.details?.file_path || ""));
    footer.appendChild(full);

    if (this.details?.file_path) {
      const refresh = el("button", "lm-info-card__secondary", "↻ Refresh");
      refresh.type = "button";
      refresh.title = "Refresh metadata from the configured remote provider";
      refresh.addEventListener("click", async () => {
        if (this.notesDirty()) {
          this.setStatus("Save your notes before refreshing metadata");
          return;
        }
        refresh.disabled = true;
        this.setStatus("Refreshing metadata…");
        try {
          await refreshLoraMetadata(this.details.file_path);
          await this.loadDetails();
          this.setStatus("Metadata updated");
        } catch (error) {
          this.setStatus(error.message);
        } finally {
          refresh.disabled = false;
        }
      });
      footer.appendChild(refresh);
    }

    if (this.currentEntry()) {
      const replace = el("button", "lm-info-card__secondary", "Replace…");
      replace.type = "button";
      replace.addEventListener("click", () => {
        const { node, loraName } = this;
        this.close();
        openLoraQuickPanel({ node, replaceName: loraName });
      });
      footer.appendChild(replace);
    }
  }

  setStatus(message) {
    if (this.statusElement) this.statusElement.textContent = message || "";
  }
}

export function openLoraInfoCard(options) {
  activeInfoCard?.close();
  activeInfoCard = new LoraInfoCard(options).open();
  return activeInfoCard;
}

export function closeLoraInfoCardFor(widget) {
  if (activeInfoCard?.widget === widget) activeInfoCard.close();
}

export function closeLoraInfoCard() {
  activeInfoCard?.close();
}

app.registerExtension({
  name: "LoraManager.LoraInfoCard",
  afterConfigureGraph() {
    closeLoraInfoCard();
  },
});
