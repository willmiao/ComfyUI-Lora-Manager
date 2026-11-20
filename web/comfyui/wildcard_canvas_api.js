import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";

async function request(path, options = {}) {
  const response = await api.fetchApi(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    const error = new Error(data.error || `HTTP ${response.status}`);
    error.payload = data;
    throw error;
  }
  return data;
}

export function searchWildcardLibrary(search = "") {
  const query = new URLSearchParams({ search });
  return request(`/lm/wildcards/active?${query}`);
}

export function setWildcardActive(filePath, active) {
  return request(`/lm/wildcards/${active ? "activate" : "deactivate"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath }),
  });
}

export function openWildcardManager(filePath = "") {
  const hash = filePath ? `#model=${encodeURIComponent(filePath)}` : "";
  const url = `${window.location.origin}${lmUrl("/wildcards")}${hash}`;
  // Reuse the existing LoRA Manager tab (the recipe picker uses the same named
  // window) and let the wildcard page open the linked resource's modal.
  window.open(url, "lm-lora-manager");
}

export function openWildcardsFolder() {
  return request(`/lm/wildcards/open-location`, { method: "POST" });
}
