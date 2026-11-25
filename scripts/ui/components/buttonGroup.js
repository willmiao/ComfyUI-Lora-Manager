// Test double for ComfyUI's /scripts/ui/components/buttonGroup.js (frontend
// 1.33+). Groups ComfyButton instances the way the real component does.

export class ComfyButtonGroup {
  constructor(...buttons) {
    const element = document.createElement('div');
    element.className = 'comfyui-button-group';

    for (const button of buttons) {
      element.appendChild(button?.element ?? button);
    }

    this.element = element;
  }
}

export default ComfyButtonGroup;
