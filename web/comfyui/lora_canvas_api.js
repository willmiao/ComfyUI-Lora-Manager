import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";

async function readJson(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    throw new Error(data.error || fallbackMessage);
  }
  return data;
}

export async function searchLoraLibrary(query = "", limit = 50, { useActiveFilters = false } = {}) {
  const params = new URLSearchParams({
    search: query,
    limit: String(limit),
    match_model_name: "true",
    include_model_name: "true",
  });
  if (useActiveFilters) params.set("use_active_filters", "true");
  const data = await readJson(
    await api.fetchApi(`/lm/loras/relative-paths?${params}`),
    "Failed to search the LoRA library",
  );
  const items = Array.isArray(data.items) ? data.items : [];
  return items
    .filter((item) => item?.relative_path)
    .map((item) => ({
      relativePath: item.relative_path,
      modelName: item.model_name || item.relative_path.split("/").pop(),
    }));
}

export async function fetchLoraDetails(name) {
  const data = await readJson(
    await api.fetchApi(`/lm/loras/details?name=${encodeURIComponent(name)}`),
    "Failed to load LoRA details",
  );
  return data.metadata || {};
}

export async function fetchLoraFolderIndex({ useActiveFilters = false } = {}) {
  const query = useActiveFilters ? "?use_active_filters=true" : "";
  const data = await readJson(
    await api.fetchApi(`/lm/loras/folder-index${query}`),
    "Failed to load LoRA folders",
  );
  const normalizeNode = (node) => ({
    count: Number(node?.count) || 0,
    items: (node?.items || []).map((item) => ({
      relativePath: item.relative_path,
      modelName: item.model_name || item.relative_path?.split("/").pop(),
    })),
    folders: Object.fromEntries(
      Object.entries(node?.folders || {}).map(([name, child]) => [name, normalizeNode(child)]),
    ),
  });
  return normalizeNode(data.root);
}

export async function fetchActiveFilters() {
  const data = await readJson(
    await api.fetchApi("/lm/loras/active-filters"),
    "Failed to load active filters",
  );
  return data.filters || null;
}

const EMPTY_WILDCARD_MARKER = "__EMPTY_WILDCARD_RESULT__";

/**
 * Count the restrictions carried by the manager page's active-filter snapshot.
 *
 * Mirrors the page's badge for tags/base models/model types/licenses, and also
 * counts the folder scope: for the picker a pinned folder (or a non-recursive
 * root scope) narrows the library just like a filter does.
 *
 * @param {object|null} snapshot
 * @returns {number}
 */
export function countActiveFilters(snapshot) {
  const filters = snapshot?.filters || {};
  const countKeys = (value) => (
    value && typeof value === "object" ? Object.keys(value).length : 0
  );
  const baseModels = Array.isArray(filters.baseModel)
    ? filters.baseModel.filter((name) => name && name !== EMPTY_WILDCARD_MARKER)
    : [];
  const modelTypes = Array.isArray(filters.modelTypes) ? filters.modelTypes.length : 0;
  const activeFolder = snapshot?.activeFolder;
  const hasScope = Boolean(activeFolder && activeFolder !== "null")
    || snapshot?.recursiveSearch === false;
  const scope = hasScope ? 1 : 0;
  return (
    baseModels.length
    + countKeys(filters.tags)
    + countKeys(filters.autoTags)
    + countKeys(filters.license)
    + modelTypes
    + scope
  );
}

export async function refreshLoraMetadata(filePath) {
  if (!filePath) throw new Error("This LoRA is outside the managed library");
  return readJson(
    await api.fetchApi("/lm/loras/fetch-civitai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: filePath }),
    }),
    "Failed to refresh metadata",
  );
}

export function openLoraManagerHome(newWindow = false) {
  const url = `${window.location.origin}${lmUrl("/loras")}`;
  if (newWindow) {
    window.open(url, "_blank", "width=1200,height=800,resizable=yes,scrollbars=yes,status=yes");
  } else {
    window.open(url, "_blank");
  }
}

export function openLoraManager(filePath = "", newWindow = false) {
  const hash = filePath ? `#model=${encodeURIComponent(filePath)}` : "";
  const url = `${window.location.origin}${lmUrl("/loras")}${hash}`;
  if (newWindow) {
    window.open(url, "_blank", "width=1200,height=800,resizable=yes,scrollbars=yes,status=yes");
  } else {
    window.open(url, "lm-lora-manager");
  }
}

export function parseUsageTips(value) {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string" || !value.trim()) return {};
  try { return JSON.parse(value) || {}; } catch { return {}; }
}

export function recommendedStrength(details) {
  const tips = parseUsageTips(details?.usage_tips);
  const value = Number(tips.strength);
  return Number.isFinite(value) ? value : undefined;
}

export function formatUsageTips(details) {
  const tips = parseUsageTips(details?.usage_tips);
  const parts = [];
  if (tips.strength !== undefined) parts.push(`Strength ${tips.strength}`);
  if (tips.strength_min !== undefined || tips.strength_max !== undefined) {
    parts.push(`Range ${tips.strength_min ?? "…"}–${tips.strength_max ?? "…"}`);
  } else if (tips.strength_range) {
    parts.push(`Range ${tips.strength_range}`);
  }
  const clip = tips.clip_strength ?? tips.clipStrength;
  if (clip !== undefined) parts.push(`Clip ${clip}`);
  if (tips.clip_skip !== undefined) parts.push(`Clip skip ${tips.clip_skip}`);
  return parts.join(" · ");
}

export async function saveLoraNotes(filePath, notes) {
  if (!filePath) throw new Error("This LoRA is outside the managed library");
  return readJson(
    await api.fetchApi("/lm/loras/save-metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: filePath, notes }),
    }),
    "Failed to save notes",
  );
}
