// Test double for ComfyUI's /scripts/ui/components/button.js (frontend 1.33+).
// Mirrors only the surface the LoRA Manager extension touches: the button
// element, its icon element, the passed class list, and the click action.

export class ComfyButton {
  constructor(options = {}) {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = options.classList ?? '';

    const iconElement = document.createElement('i');
    iconElement.className = options.icon ?? '';
    element.appendChild(iconElement);

    if (typeof options.action === 'function') {
      element.addEventListener('click', options.action);
    }

    this.element = element;
    this.iconElement = iconElement;
    this.options = options;
  }
}

export default ComfyButton;
