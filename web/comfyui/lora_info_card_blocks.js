import { fetchLoraBlockWeightSchema } from "./lora_canvas_api.js";
import { normalizeLbwConfig } from "./lora_block_weight.js";
import { findLoraIndex } from "./lora_selection.js";
import { normalizeLoraNameKey } from "./loras_widget_utils.js";

function updateLoraLbw(widget, loraName, config, { commit = true } = {}) {
  const loras = Array.isArray(widget?.value) ? widget.value.slice() : [];
  const index = findLoraIndex(loras, normalizeLoraNameKey(loraName));
  if (index < 0) return false;
  loras[index] = { ...loras[index], lbw: normalizeLbwConfig(config) };
  widget.value = loras;
  if (commit) widget.callback?.(loras);
  return true;
}

const GROUP_LABELS = {
  IN: "Input blocks",
  MID: "Middle block",
  OUT: "Output blocks",
  DOUBLE: "Double blocks",
  SINGLE: "Single blocks",
};

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export function buildOnlyGroupWeights(groups, selectedGroup = "") {
  const weights = {};
  for (const group of groups) weights[group] = group === selectedGroup ? 1 : 0;
  return weights;
}

export class LoraInfoCardBlocks {
  constructor(card) {
    this.card = card;
    this.schema = null;
    this.error = "";
    this.schemaPromise = null;
  }

  config() {
    return normalizeLbwConfig(this.card.currentEntry()?.lbw);
  }

  writeConfig(config, message) {
    if (!updateLoraLbw(this.card.widget, this.card.loraName, config)) {
      this.card.setStatus("The LoRA row no longer exists");
      return;
    }
    this.card.setStatus(message);
    this.render(this.card.tabContent);
  }

  async loadSchema() {
    if (this.schema || this.schemaPromise) return;
    this.schemaPromise = fetchLoraBlockWeightSchema(this.card.loraName);
    try {
      this.schema = await this.schemaPromise;
    } catch (error) {
      this.error = error.message;
    } finally {
      this.schemaPromise = null;
      if (this.card.panel?.isOpen() && this.card.activeTab === "blocks") {
        this.render(this.card.tabContent);
      }
    }
  }

  numberInput(blockId, label, value, disabled, onChange) {
    const row = el("label", "lm-info-card__strength lm-info-card__lbw-weight");
    row.appendChild(el("span", "lm-info-card__lbw-weight-label", label));
    const grip = el("span", "lm-info-card__strength-grip", "↔");
    grip.title = "Drag horizontally to adjust";
    grip.setAttribute("aria-hidden", "true");
    row.appendChild(grip);
    const input = el("input", "lm-info-card__number lm-info-card__lbw-number");
    input.type = "number";
    input.step = "0.05";
    input.min = "-10";
    input.max = "10";
    input.value = Number(value).toFixed(2);
    input.disabled = disabled;
    input.dataset.blockId = blockId;
    input.setAttribute("aria-label", `${label} block weight`);
    input.addEventListener("change", () => {
      const next = Number(input.value);
      if (!Number.isFinite(next)) {
        input.value = Number(value).toFixed(2);
        return;
      }
      onChange(next);
    });
    row.appendChild(input);
    this.bindWeightDrag(row, input, blockId, label);
    return row;
  }

  bindWeightDrag(row, input, blockId, label) {
    const isGroup = this.schema.groups.includes(blockId);
    const block = this.schema.blocks.find((item) => item.id === blockId);
    this.card.bindValueDrag(row, input, {
      readValue: () => {
        if (!this.card.currentEntry()) return null;
        const weights = this.config().weights;
        return weights[blockId] ?? weights[block?.group] ?? 1;
      },
      updateValue: (value, commit) => {
        const config = this.config();
        const weights = { ...config.weights, [blockId]: value };
        if (isGroup) {
          for (const item of this.schema.blocks) {
            if (item.group === blockId) delete weights[item.id];
          }
        }
        return updateLoraLbw(
          this.card.widget,
          this.card.loraName,
          { ...config, weights },
          { commit },
        );
      },
      status: `Updated ${label} block weight`,
      onCommitted: () => this.render(this.card.tabContent),
    });
  }

  setWeight(blockId, value) {
    const config = this.config();
    const weights = { ...config.weights, [blockId]: value };
    this.writeConfig({ ...config, weights }, `Updated ${blockId} block weight`);
  }

  setGroupWeight(group, value) {
    const config = this.config();
    const weights = { ...config.weights, [group]: value };
    for (const block of this.schema.blocks) {
      if (block.group === group) delete weights[block.id];
    }
    this.writeConfig({ ...config, weights }, `Updated ${GROUP_LABELS[group] || group}`);
  }

  render(container) {
    container.replaceChildren();
    const section = el("section", "lm-info-card__section lm-info-card__lbw");
    section.appendChild(el("h3", "lm-info-card__heading", "Block weights"));
    section.appendChild(el(
      "p",
      "lm-info-card__lbw-help",
      "Multiplies this row's model and CLIP strengths. Unspecified blocks use 1.00; BASE covers text encoders and other weights.",
    ));
    container.appendChild(section);

    if (!this.schema && !this.error) {
      section.appendChild(el("div", "lm-info-card__loading", "Inspecting LoRA blocks…"));
      this.loadSchema();
      return;
    }
    if (this.error) {
      section.appendChild(el("div", "lm-info-card__warning", this.error));
      return;
    }
    if (this.schema.kind === "unsupported") {
      section.appendChild(el(
        "div",
        "lm-info-card__warning",
        "This LoRA does not use a supported SD/SDXL U-Net or FLUX block layout.",
      ));
      return;
    }

    const config = this.config();
    const enable = el("label", "lm-info-card__lbw-enable");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = config.enabled;
    checkbox.setAttribute("aria-label", "Enable block weights");
    checkbox.addEventListener("change", () => {
      this.writeConfig({ ...config, enabled: checkbox.checked }, checkbox.checked ? "Block weights enabled" : "Block weights disabled");
    });
    enable.appendChild(checkbox);
    enable.appendChild(el("span", "", "Enable block weights"));
    section.appendChild(enable);

    const controls = el("fieldset", "lm-info-card__lbw-controls");
    controls.disabled = !config.enabled;
    section.appendChild(controls);

    const presetRow = el("div", "lm-info-card__lbw-preset-row");
    const preset = el("select", "lm-info-card__lbw-preset");
    preset.setAttribute("aria-label", "Block weight preset");
    for (const [value, label] of [
      ["", "Choose a preset…"],
      ["all", "All blocks: 1.00"],
      ["base", "BASE / other only"],
      ...this.schema.groups.map((group) => [group, `${GROUP_LABELS[group] || group} only`]),
    ]) {
      const option = el("option", "", label);
      option.value = value;
      preset.appendChild(option);
    }
    preset.addEventListener("change", () => {
      if (!preset.value) return;
      const weights = preset.value === "all"
        ? {}
        : buildOnlyGroupWeights(this.schema.groups, preset.value === "base" ? "" : preset.value);
      this.writeConfig({ ...config, weights }, `Applied ${preset.selectedOptions[0].textContent}`);
    });
    presetRow.appendChild(preset);
    const reset = el("button", "lm-info-card__secondary", "Reset");
    reset.type = "button";
    reset.addEventListener("click", () => this.writeConfig({ ...config, weights: {} }, "Block weights reset"));
    presetRow.appendChild(reset);
    controls.appendChild(presetRow);

    controls.appendChild(this.numberInput(
      "BASE",
      "BASE / other",
      config.weights.BASE ?? 1,
      false,
      (value) => this.setWeight("BASE", value),
    ));

    for (const group of this.schema.groups) {
      controls.appendChild(this.numberInput(
        group,
        GROUP_LABELS[group] || group,
        config.weights[group] ?? 1,
        false,
        (value) => this.setGroupWeight(group, value),
      ));
    }

    const details = el("details", "lm-info-card__lbw-individual");
    details.appendChild(el("summary", "", `Individual blocks (${this.schema.blocks.length})`));
    const list = el("div", "lm-info-card__lbw-individual-list");
    for (const block of this.schema.blocks) {
      const effectiveValue = config.weights[block.id] ?? config.weights[block.group] ?? 1;
      list.appendChild(this.numberInput(
        block.id,
        block.id,
        effectiveValue,
        false,
        (value) => this.setWeight(block.id, value),
      ));
    }
    details.appendChild(list);
    controls.appendChild(details);
  }
}
