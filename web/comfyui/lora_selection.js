import { LORA_PATTERN } from "./utils.js";
import { normalizeLoraNameKey } from "./loras_widget_utils.js";

/**
 * Shared "add or enable" logic for LoRA entries.
 *
 * "Send to ComfyUI" from the LoRA Manager page delivers a
 * `<lora:name:strength>` code string over the websocket and writes it to the
 * node's textarea. Appending it for an entry the node already lists leaves a
 * disabled entry disabled, which looks like the button did nothing, so listed
 * LoRAs are switched on in place (strengths kept) and only unlisted codes fall
 * through to the append path.
 *
 * `applyLoraSelection` is the general add-or-enable primitive; the parse and
 * lookup helpers are shared with the autocomplete's "already added" cue.
 */

const DEFAULT_STRENGTH = 1;
const STRENGTH_DECIMALS = 2;

/**
 * Extract the LoRA tags from an A1111-style code string.
 *
 * Accepts model/CLIP strengths and the optional Lora Manager `LBW=` field; the
 * pattern is the one the textarea parser uses, so anything this reads is
 * something that surface will also recognise. Names are returned normalized
 * (forward slashes, extension stripped) because that is the form stored in a
 * node's LoRA list.
 */
export function parseLoraCodeTags(code) {
  const text = String(code ?? "");
  const pattern = new RegExp(LORA_PATTERN.source, "g");
  const tags = [];
  let match = pattern.exec(text);
  while (match) {
    const [tag, rawName, strength, clipStrength] = match;
    const name = normalizeLoraNameKey(rawName);
    if (name) {
      const modelStrength = Number(strength);
      tags.push({
        tag,
        name,
        strength: Number.isFinite(modelStrength) ? modelStrength : undefined,
        clipStrength:
          clipStrength === undefined ? undefined : Number(clipStrength),
      });
    }
    match = pattern.exec(text);
  }
  return tags;
}

/**
 * Find the list entry that refers to the same file as `targetName`.
 *
 * Entries are compared the way the backend resolves names: exact match on the
 * extension-free, forward-slash name, falling back to the bare file name for
 * legacy entries stored without their folder. Two folder-qualified names in
 * different folders are different files and never match.
 */
export function findLoraIndex(loras, targetName) {
  const targetBase = targetName.slice(targetName.lastIndexOf("/") + 1);
  let bareIndex = -1;
  for (let index = 0; index < loras.length; index += 1) {
    const key = normalizeLoraNameKey(loras[index]?.name);
    if (!key) {
      continue;
    }
    if (key === targetName) {
      return index;
    }
    if (bareIndex === -1 && key === targetBase) {
      bareIndex = index;
    }
  }
  return bareIndex;
}

function formatStrength(value) {
  if (value === null || value === undefined || value === "") {
    return DEFAULT_STRENGTH.toFixed(STRENGTH_DECIMALS);
  }
  const numeric = Number(value);
  return (Number.isFinite(numeric) ? numeric : DEFAULT_STRENGTH).toFixed(
    STRENGTH_DECIMALS
  );
}

/**
 * Apply a selection to a node's LoRA list.
 *
 * A LoRA that is already in the list is enabled in place (its strengths are
 * kept) instead of being added twice; a new one is appended active, using the
 * recommended strength from the library when one is configured. Returns the
 * list to write back and whether it actually changed.
 */
export function applyLoraSelection(currentLoras, selection) {
  const loras = Array.isArray(currentLoras) ? currentLoras : [];
  const name = normalizeLoraNameKey(selection?.name);
  if (!name) {
    return { loras, changed: false };
  }

  const existingIndex = findLoraIndex(loras, name);
  if (existingIndex >= 0) {
    const existing = loras[existingIndex];
    if (existing?.active) {
      return { loras, changed: false };
    }
    const next = loras.slice();
    next[existingIndex] = { ...existing, active: true };
    return { loras: next, changed: true };
  }

  const strength = formatStrength(selection?.strength);
  return {
    loras: [
      ...loras,
      {
        name,
        strength,
        clipStrength: strength,
        active: true,
        expanded: false,
        selected: false,
        locked: false,
        ...(selection?.lbw ? { lbw: selection.lbw } : {}),
      },
    ],
    changed: true,
  };
}

/**
 * Enable every LoRA from `code` that is already listed on the node.
 *
 * Returns the list to write back, whether anything changed, and the tags that
 * name a LoRA the list does not contain. The caller appends those tags through
 * the textarea path (which is what adds new entries); listed LoRAs never reach
 * it, so "Send to ComfyUI" on a disabled entry switches it on instead of
 * appending a duplicate tag that leaves the entry untouched.
 */
export function enableListedLorasFromCode(currentLoras, code) {
  const loras = Array.isArray(currentLoras) ? currentLoras : [];
  let next = loras;
  let changed = false;
  const unlistedTags = [];

  for (const parsed of parseLoraCodeTags(code)) {
    if (findLoraIndex(next, parsed.name) < 0) {
      unlistedTags.push(parsed.tag);
      continue;
    }
    const result = applyLoraSelection(next, {
      name: parsed.name,
      strength: parsed.strength,
    });
    if (result.changed) {
      next = result.loras;
      changed = true;
    }
  }

  return { loras: next, changed, unlistedTags };
}

function normalizeSetEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  if (entry.exclude || entry.isDeleted) return null;
  if (entry.inLibrary === false) return null;
  const name = normalizeLoraNameKey(
    entry.name ?? entry.file_name ?? entry.fileName ?? entry.relativePath ?? "",
  );
  if (!name) return null;
  const rawStrength = entry.strength ?? entry.weight;
  const numeric = Number(rawStrength);
  return {
    name,
    strength: Number.isFinite(numeric) ? numeric : undefined,
    ...(entry.lbw ? { lbw: entry.lbw } : {}),
  };
}

function sameLoraEntry(left, right) {
  return left?.name === right?.name
    && String(left?.strength ?? "") === String(right?.strength ?? "")
    && String(left?.clipStrength ?? "") === String(right?.clipStrength ?? "")
    && JSON.stringify(left?.lbw ?? null) === JSON.stringify(right?.lbw ?? null)
    && Boolean(left?.active) === Boolean(right?.active);
}

function sameLoraList(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  return left.every((entry, index) => sameLoraEntry(entry, right[index]));
}

/**
 * Apply a set of LoRAs (a recipe) to a node's LoRA list.
 *
 * `append` keeps the existing list and applies each available entry through
 * `applyLoraSelection`: a listed entry is enabled in place (its strengths are
 * kept), a missing one is appended active with the recipe strength.
 *
 * `replace` rewrites the list to exactly the available recipe entries, using
 * the recipe strengths. In both modes entries with `isDeleted`, `inLibrary ===
 * false`, or `exclude` are skipped and counted in `skipped`.
 *
 * Returns `{ loras, changed, applied, skipped }`; `applied` counts the
 * available entries, not only the ones that changed the list.
 */
export function applyLoraSet(currentLoras, entries, { mode = "append" } = {}) {
  const current = Array.isArray(currentLoras) ? currentLoras : [];
  const list = Array.isArray(entries) ? entries : [];
  const unique = [];
  const seen = new Set();
  for (const entry of list.map(normalizeSetEntry)) {
    if (!entry || seen.has(entry.name)) continue;
    seen.add(entry.name);
    unique.push(entry);
  }
  const skipped = list.length - unique.length;
  if (!unique.length) {
    return { loras: current, changed: false, applied: 0, skipped };
  }

  if (mode === "replace") {
    let next = [];
    for (const entry of unique) {
      next = applyLoraSelection(next, {
        name: entry.name,
        strength: entry.strength,
        lbw: entry.lbw,
      }).loras;
    }
    return {
      loras: next,
      changed: !sameLoraList(current, next),
      applied: unique.length,
      skipped,
    };
  }

  let next = current;
  let changed = false;
  for (const entry of unique) {
    const result = applyLoraSelection(next, {
      name: entry.name,
      strength: entry.strength,
      lbw: entry.lbw,
    });
    if (result.changed) {
      next = result.loras;
      changed = true;
    }
  }
  return { loras: next, changed, applied: unique.length, skipped };
}
