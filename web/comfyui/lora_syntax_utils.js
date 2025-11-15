import { LORA_PATTERN } from "./utils.js";

const DEFAULT_DECIMALS = 2;
const DEFAULT_DEBOUNCE_MS = 80;

function normalizeStrengthValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return (1).toFixed(DEFAULT_DECIMALS);
  }
  return numeric.toFixed(DEFAULT_DECIMALS);
}

function shouldIncludeClipStrength(lora, hadClipFromText) {
  const clip = lora?.clipStrength;
  const strength = lora?.strength;

  if (clip === undefined || clip === null) {
    return Boolean(hadClipFromText);
  }

  const clipValue = Number(clip);
  const strengthValue = Number(strength);

  if (!Number.isFinite(clipValue) || !Number.isFinite(strengthValue)) {
    return Boolean(hadClipFromText);
  }

  if (Math.abs(clipValue - strengthValue) > Number.EPSILON) {
    return true;
  }

  return Boolean(lora?.expanded || hadClipFromText);
}

function cleanupLoraSyntax(text) {
  if (!text) {
    return "";
  }

  let cleaned = text
    .replace(/\s+/g, " ")
    .replace(/,\s*,+/g, ",")
    .replace(/\s*,\s*/g, ",")
    .trim();

  if (cleaned === ",") {
    return "";
  }

  cleaned = cleaned.replace(/(^,)|(,$)/g, "");
  cleaned = cleaned.replace(/,\s*/g, ", ");

  return cleaned.trim();
}

export function applyLoraValuesToText(originalText, loras) {
  const baseText = typeof originalText === "string" ? originalText : "";
  const loraArray = Array.isArray(loras) ? loras : [];
  const loraMap = new Map();

  loraArray.forEach((lora) => {
    if (!lora || !lora.name) {
      return;
    }
    loraMap.set(lora.name, lora);
  });

  LORA_PATTERN.lastIndex = 0;
  const retainedNames = new Set();

  const updated = baseText.replace(
    LORA_PATTERN,
    (match, name, strength, clipStrength) => {
      const lora = loraMap.get(name);
      if (!lora) {
        return "";
      }

      retainedNames.add(name);

      const formattedStrength = normalizeStrengthValue(
        lora.strength ?? strength
      );
      const formattedClip = normalizeStrengthValue(
        lora.clipStrength ?? lora.strength ?? clipStrength
      );

      const includeClip = shouldIncludeClipStrength(lora, clipStrength);

      if (includeClip) {
        return `<lora:${name}:${formattedStrength}:${formattedClip}>`;
      }

      return `<lora:${name}:${formattedStrength}>`;
    }
  );

  const cleaned = cleanupLoraSyntax(updated);

  if (loraMap.size === retainedNames.size) {
    return cleaned;
  }

  // Some LoRAs in the widget are not represented in the input text.
  // Append them in a deterministic order so that the syntax stays complete.
  const missingEntries = [];
  loraMap.forEach((lora, name) => {
    if (retainedNames.has(name)) {
      return;
    }

    const formattedStrength = normalizeStrengthValue(lora.strength);
    const formattedClip = normalizeStrengthValue(
      lora.clipStrength ?? lora.strength
    );
    const includeClip = shouldIncludeClipStrength(lora, null);

    const syntax = includeClip
      ? `<lora:${name}:${formattedStrength}:${formattedClip}>`
      : `<lora:${name}:${formattedStrength}>`;

    missingEntries.push(syntax);
  });

  if (missingEntries.length === 0) {
    return cleaned;
  }

  const separator = cleaned ? " " : "";
  return `${cleaned}${separator}${missingEntries.join(" ")}`.trim();
}

export function debounce(fn, delay = DEFAULT_DEBOUNCE_MS) {
  let timeoutId = null;
  let lastArgs = [];
  let lastContext = null;

  const debounced = function (...args) {
    lastArgs = args;
    lastContext = this;

    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      timeoutId = null;
      fn.apply(lastContext, lastArgs);
    }, delay);
  };

  debounced.flush = () => {
    if (!timeoutId) {
      return;
    }

    clearTimeout(timeoutId);
    timeoutId = null;
    fn.apply(lastContext, lastArgs);
  };

  debounced.cancel = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  return debounced;
}

export function __testables() {
  return {
    normalizeStrengthValue,
    shouldIncludeClipStrength,
    cleanupLoraSyntax,
  };
}
