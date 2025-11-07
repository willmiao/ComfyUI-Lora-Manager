import { api } from "../../scripts/api.js";
import {
  getConnectedTriggerToggleNodes,
  getLinkFromGraph,
  getNodeKey,
} from "./utils.js";

const TRIGGER_WORD_CACHE_TTL = 5 * 60 * 1000; // 5 minutes
const triggerWordCache = new Map();

const LORA_NODE_CLASSES = new Set([
  "Lora Loader (LoraManager)",
  "Lora Stacker (LoraManager)",
  "WanVideo Lora Select (LoraManager)",
]);

function normalizeTriggerWordList(triggerWords) {
  if (!triggerWords) {
    return [];
  }

  if (triggerWords instanceof Set) {
    return Array.from(triggerWords)
      .map((word) => (word == null ? "" : String(word)).trim())
      .filter(Boolean);
  }

  if (!Array.isArray(triggerWords)) {
    return [(triggerWords == null ? "" : String(triggerWords)).trim()].filter(
      Boolean
    );
  }

  return triggerWords
    .map((word) => (word == null ? "" : String(word)).trim())
    .filter(Boolean);
}

export async function fetchTriggerWordsForLora(loraName) {
  if (!loraName) {
    return [];
  }

  const cached = triggerWordCache.get(loraName);
  if (cached && Date.now() - cached.timestamp < TRIGGER_WORD_CACHE_TTL) {
    return cached.words;
  }

  const response = await api.fetchApi(
    `/lm/loras/get-trigger-words?name=${encodeURIComponent(loraName)}`,
    { method: "GET" }
  );

  if (!response?.ok) {
    const errorText = response ? await response.text().catch(() => "") : "";
    throw new Error(errorText || `Failed to fetch trigger words for ${loraName}`);
  }

  const data = (await response.json().catch(() => ({}))) || {};
  const triggerWords = Array.isArray(data.trigger_words)
    ? data.trigger_words.filter((word) => typeof word === "string")
    : [];
  const normalized = triggerWords
    .map((word) => word.trim())
    .filter((word) => word.length > 0);

  triggerWordCache.set(loraName, {
    words: normalized,
    timestamp: Date.now(),
  });

  return normalized;
}

export function highlightTriggerWordsAlongChain(startNode, triggerWords) {
  const normalizedWords = normalizeTriggerWordList(triggerWords);
  highlightNodeRecursive(startNode, normalizedWords, new Set());
}

export async function applySelectionHighlight(node, selection) {
  if (!node) {
    return;
  }

  node.__lmSelectionHighlightToken =
    (node.__lmSelectionHighlightToken || 0) + 1;
  const requestId = node.__lmSelectionHighlightToken;

  const loraName = selection?.name;
  const isActive = !!selection?.active;

  if (!loraName || !isActive) {
    highlightTriggerWordsAlongChain(node, []);
    return;
  }

  try {
    const triggerWords = await fetchTriggerWordsForLora(loraName);
    if (node.__lmSelectionHighlightToken !== requestId) {
      return;
    }
    highlightTriggerWordsAlongChain(node, triggerWords);
  } catch (error) {
    console.error("Error fetching trigger words for highlight:", error);
    if (node.__lmSelectionHighlightToken === requestId) {
      highlightTriggerWordsAlongChain(node, []);
    }
  }
}

function highlightNodeRecursive(node, triggerWords, visited) {
  if (!node) {
    return;
  }

  const nodeKey = getNodeKey(node);
  if (!nodeKey || visited.has(nodeKey)) {
    return;
  }
  visited.add(nodeKey);

  highlightTriggerWordsOnNode(node, triggerWords);

  if (!node.outputs) {
    return;
  }

  for (const output of node.outputs) {
    if (!output?.links?.length) {
      continue;
    }

    for (const linkId of output.links) {
      const link = getLinkFromGraph(node.graph, linkId);
      if (!link) {
        continue;
      }

      const targetNode = node.graph?.getNodeById?.(link.target_id);
      if (!targetNode) {
        continue;
      }

      if (LORA_NODE_CLASSES.has(targetNode.comfyClass)) {
        highlightNodeRecursive(targetNode, triggerWords, visited);
      }
    }
  }
}

function highlightTriggerWordsOnNode(node, triggerWords) {
  const connectedToggles = getConnectedTriggerToggleNodes(node);
  if (!connectedToggles.length) {
    return;
  }

  connectedToggles.forEach((toggleNode) => {
    if (typeof toggleNode?.highlightTriggerWords === "function") {
      toggleNode.highlightTriggerWords(triggerWords);
    } else {
      toggleNode.__pendingHighlightWords = Array.isArray(triggerWords)
        ? [...triggerWords]
        : triggerWords;
    }
  });
}
