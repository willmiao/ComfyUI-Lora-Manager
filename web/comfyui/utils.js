export const CONVERTED_TYPE = 'converted-widget';
import { app } from "../../scripts/app.js";
import { AutoComplete } from "./autocomplete.js";

export function chainCallback(object, property, callback) {
  if (object == undefined) {
    //This should not happen.
    console.error("Tried to add callback to non-existant object")
    return;
  }
  if (property in object) {
    const callback_orig = object[property]
    object[property] = function () {
      const r = callback_orig.apply(this, arguments);
      callback.apply(this, arguments);
      return r
    };
  } else {
    object[property] = callback;
  }
}

/**
 * Show a toast notification
 * @param {Object|string} options - Toast options object or message string for backward compatibility
 * @param {string} [options.severity] - Message severity level (success, info, warn, error, secondary, contrast)
 * @param {string} [options.summary] - Short title for the toast
 * @param {any} [options.detail] - Detailed message content
 * @param {boolean} [options.closable] - Whether user can close the toast (default: true)
 * @param {number} [options.life] - Duration in milliseconds before auto-closing
 * @param {string} [options.group] - Group identifier for managing related toasts
 * @param {any} [options.styleClass] - Style class of the message
 * @param {any} [options.contentStyleClass] - Style class of the content
 * @param {string} [type] - Deprecated: severity type for backward compatibility
 */
export function showToast(options, type = 'info') {
    // Handle backward compatibility: showToast(message, type)
    if (typeof options === 'string') {
        options = {
            detail: options,
            severity: type
        };
    }
    
    // Set defaults
    const toastOptions = {
        severity: options.severity || 'info',
        summary: options.summary,
        detail: options.detail,
        closable: options.closable !== false, // default to true
        life: options.life,
        group: options.group,
        styleClass: options.styleClass,
        contentStyleClass: options.contentStyleClass
    };
    
    // Remove undefined properties
    Object.keys(toastOptions).forEach(key => {
        if (toastOptions[key] === undefined) {
            delete toastOptions[key];
        }
    });
    
    if (app && app.extensionManager && app.extensionManager.toast) {
        app.extensionManager.toast.add(toastOptions);
    } else {
        const message = toastOptions.detail || toastOptions.summary || 'No message';
        const severity = toastOptions.severity.toUpperCase();
        console.log(`${severity}: ${message}`);
        // Fallback alert for critical errors only
        if (toastOptions.severity === 'error') {
            alert(message);
        }
    }
}

export function hideWidgetForGood(node, widget, suffix = "") {
  widget.origType = widget.type;
  widget.origComputeSize = widget.computeSize;
  widget.origSerializeValue = widget.serializeValue;
  widget.computeSize = () => [0, -4]; // -4 is due to the gap litegraph adds between widgets automatically
  widget.type = CONVERTED_TYPE + suffix;
  // widget.serializeValue = () => {
  //     // Prevent serializing the widget if we have no input linked
  //     const w = node.inputs?.find((i) => i.widget?.name === widget.name);
  //     if (w?.link == null) {
  //         return undefined;
  //     }
  //     return widget.origSerializeValue ? widget.origSerializeValue() : widget.value;
  // };

  // Hide any linked widgets, e.g. seed+seedControl
  if (widget.linkedWidgets) {
    for (const w of widget.linkedWidgets) {
      hideWidgetForGood(node, w, `:${widget.name}`);
    }
  }
}

// Update pattern to match both formats: <lora:name:model_strength> or <lora:name:model_strength:clip_strength>
export const LORA_PATTERN = /<lora:([^:]+):([-\d\.]+)(?::([-\d\.]+))?>/g;

// Get connected Lora Stacker nodes that feed into the current node
export function getConnectedInputStackers(node) {
    const connectedStackers = [];
    
    if (node.inputs) {
        for (const input of node.inputs) {
            if (input.name === "lora_stack" && input.link) {
                const link = app.graph.links[input.link];
                if (link) {
                    const sourceNode = app.graph.getNodeById(link.origin_id);
                    if (sourceNode && sourceNode.comfyClass === "Lora Stacker (LoraManager)") {
                        connectedStackers.push(sourceNode);
                    }
                }
            }
        }
    }
    return connectedStackers;
}

// Get connected TriggerWord Toggle nodes that receive output from the current node
export function getConnectedTriggerToggleNodes(node) {
    const connectedNodes = [];
    
    if (node.outputs && node.outputs.length > 0) {
        for (const output of node.outputs) {
            if (output.links && output.links.length > 0) {
                for (const linkId of output.links) {
                    const link = app.graph.links[linkId];
                    if (link) {
                        const targetNode = app.graph.getNodeById(link.target_id);
                        if (targetNode && targetNode.comfyClass === "TriggerWord Toggle (LoraManager)") {
                            connectedNodes.push(targetNode.id);
                        }
                    }
                }
            }
        }
    }
    return connectedNodes;
}

// Extract active lora names from a node's widgets
export function getActiveLorasFromNode(node) {
    const activeLoraNames = new Set();
    
    // For lorasWidget style entries (array of objects)
    if (node.lorasWidget && node.lorasWidget.value) {
        node.lorasWidget.value.forEach(lora => {
            if (lora.active) {
                activeLoraNames.add(lora.name);
            }
        });
    }
    
    return activeLoraNames;
}

// Recursively collect all active loras from a node and its input chain
export function collectActiveLorasFromChain(node, visited = new Set()) {
    // Prevent infinite loops from circular references
    if (visited.has(node.id)) {
        return new Set();
    }
    visited.add(node.id);
    
    // Get active loras from current node
    const allActiveLoraNames = getActiveLorasFromNode(node);
    
    // Get connected input stackers and collect their active loras
    const inputStackers = getConnectedInputStackers(node);
    for (const stacker of inputStackers) {
        const stackerLoras = collectActiveLorasFromChain(stacker, visited);
        stackerLoras.forEach(name => allActiveLoraNames.add(name));
    }
    
    return allActiveLoraNames;
}

// Update trigger words for connected toggle nodes
export function updateConnectedTriggerWords(node, loraNames) {
    const connectedNodeIds = getConnectedTriggerToggleNodes(node);
    if (connectedNodeIds.length > 0) {
        fetch("/api/lm/loras/get_trigger_words", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                lora_names: Array.from(loraNames),
                node_ids: connectedNodeIds
            })
        }).catch(err => console.error("Error fetching trigger words:", err));
    }
}

export function mergeLoras(lorasText, lorasArr) {
  // Parse lorasText into a map: name -> {strength, clipStrength}
  const parsedLoras = {};
  let match;
  LORA_PATTERN.lastIndex = 0;
  while ((match = LORA_PATTERN.exec(lorasText)) !== null) {
    const name = match[1];
    const modelStrength = Number(match[2]);
    const clipStrength = match[3] ? Number(match[3]) : modelStrength;
    parsedLoras[name] = { strength: modelStrength, clipStrength };
  }

  // Build result array in the order of lorasArr
  const result = [];
  const usedNames = new Set();

  for (const lora of lorasArr) {
    if (parsedLoras[lora.name]) {
      result.push({
        name: lora.name,
        strength: lora.strength !== undefined ? lora.strength : parsedLoras[lora.name].strength,
        active: lora.active !== undefined ? lora.active : true,
        expanded: lora.expanded !== undefined ? lora.expanded : false,
        clipStrength: lora.clipStrength !== undefined ? lora.clipStrength : parsedLoras[lora.name].clipStrength,
      });
      usedNames.add(lora.name);
    }
  }

  // Add any new loras from lorasText that are not in lorasArr, in their text order
  for (const name in parsedLoras) {
    if (!usedNames.has(name)) {
      result.push({
        name,
        strength: parsedLoras[name].strength,
        active: true,
        clipStrength: parsedLoras[name].clipStrength,
      });
    }
  }

  return result;
}

/**
 * Initialize autocomplete for an input widget and setup cleanup
 * @param {Object} node - The node instance
 * @param {Object} inputWidget - The input widget to add autocomplete to
 * @param {Function} originalCallback - The original callback function
 * @returns {Function} Enhanced callback function with autocomplete
 */
export function setupInputWidgetWithAutocomplete(node, inputWidget, originalCallback) {
    let autocomplete = null;
    
    // Enhanced callback that initializes autocomplete and calls original callback
    const enhancedCallback = (value) => {
        // Initialize autocomplete on first callback if not already done
        if (!autocomplete && inputWidget.inputEl) {
            autocomplete = new AutoComplete(inputWidget.inputEl, 'loras', {
                maxItems: 20,
                minChars: 1,
                debounceDelay: 200
            });
            // Store reference for cleanup
            node.autocomplete = autocomplete;
        }
        
        // Call the original callback
        if (originalCallback) {
            originalCallback(value);
        }
    };
    
    // Setup cleanup on node removal
    setupAutocompleteCleanup(node);
    
    return enhancedCallback;
}

/**
 * Setup autocomplete cleanup when node is removed
 * @param {Object} node - The node instance
 */
export function setupAutocompleteCleanup(node) {
    // Override onRemoved to cleanup autocomplete
    const originalOnRemoved = node.onRemoved;
    node.onRemoved = function() {
        if (this.autocomplete) {
            this.autocomplete.destroy();
            this.autocomplete = null;
        }
        
        if (originalOnRemoved) {
            originalOnRemoved.call(this);
        }
    };
}

/**
 * Forward middle mouse (button 1) pointer events from a container to the ComfyUI canvas,
 * so that workflow panning works even when the pointer is over a DOM widget.
 * @param {HTMLElement} container - The root DOM element of the widget
 */
export function forwardMiddleMouseToCanvas(container) {
    if (!container) return;
    // Forward pointerdown
    container.addEventListener('pointerdown', (event) => {
        if (event.button === 1) {
            app.canvas.processMouseDown(event);
        }
    });
    // Forward pointermove
    container.addEventListener('pointermove', (event) => {
        if ((event.buttons & 4) === 4) {
            app.canvas.processMouseMove(event);
        }
    });
    // Forward pointerup
    container.addEventListener('pointerup', (event) => {
        if (event.button === 1) {
            app.canvas.processMouseUp(event);
        }
    });
}