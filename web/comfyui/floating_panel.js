const DEFAULT_RECT = { width: 860, height: 560 };

function finite(value, fallback) {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function readRect(storageKey, fallback) {
  if (!storageKey) return { ...fallback };
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
    return saved && typeof saved === "object" ? { ...fallback, ...saved } : { ...fallback };
  } catch {
    return { ...fallback };
  }
}

function startPointerDrag(handle, event, onMove, onEnd) {
  if (event.button !== 0) return false;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    handle.removeEventListener("pointermove", move);
    handle.removeEventListener("pointerup", finish);
    handle.removeEventListener("pointercancel", finish);
    handle.removeEventListener("lostpointercapture", finish);
    try { handle.releasePointerCapture(event.pointerId); } catch { /* already released */ }
    onEnd?.();
  };
  const move = (moveEvent) => {
    if (!(moveEvent.buttons & 1)) {
      finish();
      return;
    }
    onMove(moveEvent);
  };
  try { handle.setPointerCapture(event.pointerId); } catch { /* older frontend */ }
  handle.addEventListener("pointermove", move);
  handle.addEventListener("pointerup", finish);
  handle.addEventListener("pointercancel", finish);
  handle.addEventListener("lostpointercapture", finish);
  event.preventDefault();
  return true;
}

export function createFloatingPanel({
  title,
  context = "",
  className = "",
  storageKey = "",
  width = DEFAULT_RECT.width,
  height = DEFAULT_RECT.height,
  minWidth = 480,
  minHeight = 300,
  onClose,
  onDragStart,
} = {}) {
  const previousFocus = document.activeElement;
  const element = document.createElement("section");
  element.className = `lm-popover lm-floating-panel ${className}`.trim();
  element.setAttribute("role", "dialog");
  element.setAttribute("aria-modal", "false");
  element.setAttribute("aria-label", title || "LoRA Manager");

  const header = document.createElement("header");
  header.className = "lm-floating-panel__header";
  const heading = document.createElement("div");
  heading.className = "lm-floating-panel__heading";
  const titleElement = document.createElement("strong");
  titleElement.textContent = title || "LoRA Manager";
  const contextElement = document.createElement("span");
  contextElement.className = "lm-floating-panel__context";
  contextElement.textContent = context;
  heading.append(titleElement, contextElement);

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "lm-floating-panel__close";
  closeButton.setAttribute("aria-label", "Close");
  closeButton.title = "Close (Esc)";
  closeButton.textContent = "×";
  header.append(heading, closeButton);

  const body = document.createElement("div");
  body.className = "lm-floating-panel__body";
  const footer = document.createElement("footer");
  footer.className = "lm-floating-panel__footer";
  const resizeGrip = document.createElement("div");
  resizeGrip.className = "lm-floating-panel__resize";
  resizeGrip.title = "Drag to resize";
  element.append(header, body, footer, resizeGrip);
  document.body.appendChild(element);

  let rect = readRect(storageKey, {
    width,
    height,
    left: Math.max(16, (window.innerWidth - width) / 2),
    top: Math.max(64, (window.innerHeight - height) / 2),
  });
  let closed = false;

  const clampToViewport = () => {
    rect.width = Math.max(minWidth, Math.min(finite(rect.width, width), window.innerWidth - 24));
    rect.height = Math.max(minHeight, Math.min(finite(rect.height, height), window.innerHeight - 24));
    rect.left = Math.max(12, Math.min(finite(rect.left, 12), window.innerWidth - rect.width - 12));
    rect.top = Math.max(48, Math.min(finite(rect.top, 48), window.innerHeight - rect.height - 12));
    Object.assign(element.style, {
      left: `${Math.round(rect.left)}px`,
      top: `${Math.round(rect.top)}px`,
      width: `${Math.round(rect.width)}px`,
      height: `${Math.round(rect.height)}px`,
    });
  };

  const saveRect = () => {
    if (!storageKey) return;
    try { localStorage.setItem(storageKey, JSON.stringify(rect)); } catch { /* cosmetic only */ }
  };

  header.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button, input, select, textarea, a")) return;
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;
    if (!startPointerDrag(header, event, (moveEvent) => {
      rect.left = moveEvent.clientX - offsetX;
      rect.top = moveEvent.clientY - offsetY;
      clampToViewport();
    }, saveRect)) return;
    onDragStart?.();
  });

  resizeGrip.addEventListener("pointerdown", (event) => {
    const offsetX = event.clientX - (rect.left + rect.width);
    const offsetY = event.clientY - (rect.top + rect.height);
    startPointerDrag(resizeGrip, event, (moveEvent) => {
      rect.width = moveEvent.clientX - offsetX - rect.left;
      rect.height = moveEvent.clientY - offsetY - rect.top;
      clampToViewport();
    }, saveRect);
    event.stopPropagation();
  });

  element.addEventListener("pointerdown", (event) => event.stopPropagation());
  element.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    close();
  });
  closeButton.addEventListener("click", () => close());

  const onViewportResize = () => clampToViewport();
  window.addEventListener("resize", onViewportResize);

  function close() {
    if (closed) return;
    closed = true;
    window.removeEventListener("resize", onViewportResize);
    element.remove();
    onClose?.();
    if (previousFocus?.isConnected && typeof previousFocus.focus === "function") {
      previousFocus.focus({ preventScroll: true });
    }
  }

  clampToViewport();
  return {
    element,
    header,
    body,
    footer,
    titleElement,
    contextElement,
    closeButton,
    close,
    clampToViewport,
    setContext(value) { contextElement.textContent = value || ""; },
    setPosition(left, top) {
      rect.left = left;
      rect.top = top;
      clampToViewport();
    },
    getRect() { return { ...rect }; },
    isOpen: () => !closed,
  };
}
