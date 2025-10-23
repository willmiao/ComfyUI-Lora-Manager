import { translate } from './i18nHelpers.js';
import { state, getCurrentPageState } from '../state/index.js';
import { getStorageItem, setStorageItem } from './storageHelpers.js';
import { NODE_TYPE_ICONS, DEFAULT_NODE_COLOR } from './constants.js';
import { eventManager } from './EventManager.js';

/**
 * Utility function to copy text to clipboard with fallback for older browsers
 * @param {string} text - The text to copy to clipboard
 * @param {string} successMessage - Optional success message to show in toast
 * @returns {Promise<boolean>} - Promise that resolves to true if copy was successful
/**
 * Utility function to copy text to clipboard with fallback for older browsers
 * @param {string} text - The text to copy to clipboard
 * @param {string} successMessage - Optional success message to show in toast
 * @returns {Promise<boolean>} - Promise that resolves to true if copy was successful
 */
export async function copyToClipboard(text, successMessage = null) {
    const defaultSuccessMessage = successMessage || translate('uiHelpers.clipboard.copied', {}, 'Copied to clipboard');
    
    try {
        // Modern clipboard API
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'absolute';
            textarea.style.left = '-99999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
        
        if (defaultSuccessMessage) {
            showToast('uiHelpers.clipboard.copied', {}, 'success');
        }
        return true;
    } catch (err) {
        console.error('Copy failed:', err);
        showToast('uiHelpers.clipboard.copyFailed', {}, 'error');
        return false;
    }
}

export function showToast(key, params = {}, type = 'info') {
    const message = translate(key, params);
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    // Get or create toast container
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.append(toastContainer);
    }
    
    toastContainer.append(toast);

    // Calculate vertical position for stacked toasts
    const existingToasts = Array.from(toastContainer.querySelectorAll('.toast'));
    const toastIndex = existingToasts.indexOf(toast);
    const topOffset = 20; // Base offset from top
    const spacing = 10; // Space between toasts
    
    // Set position based on existing toasts
    toast.style.top = `${topOffset + (toastIndex * (toast.offsetHeight || 60 + spacing))}px`;

    requestAnimationFrame(() => {
        toast.classList.add('show');
        
        // Set timeout based on type
        let timeout = 2000; // Default (info)
        if (type === 'warning' || type === 'error') {
            timeout = 5000;
        }
        
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => {
                toast.remove();
                
                // Reposition remaining toasts
                if (toastContainer) {
                    const remainingToasts = Array.from(toastContainer.querySelectorAll('.toast'));
                    remainingToasts.forEach((t, index) => {
                        t.style.top = `${topOffset + (index * (t.offsetHeight || 60 + spacing))}px`;
                    });
                    
                    // Remove container if empty
                    if (remainingToasts.length === 0) {
                        toastContainer.remove();
                    }
                }
            });
        }, timeout);
    });
}

export function restoreFolderFilter() {
    const activeFolder = getStorageItem('activeFolder');
    const folderTag = activeFolder && document.querySelector(`.tag[data-folder="${activeFolder}"]`);
    if (folderTag) {
        folderTag.classList.add('active');
        filterByFolder(activeFolder);
    }
}

export function initTheme() {
    const savedTheme = getStorageItem('theme') || 'auto';
    applyTheme(savedTheme);
    
    // Update theme when system preference changes (for 'auto' mode)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const currentTheme = getStorageItem('theme') || 'auto';
        if (currentTheme === 'auto') {
            applyTheme('auto');
        }
    });
}

export function toggleTheme() {
    const currentTheme = getStorageItem('theme') || 'auto';
    let newTheme;
    
    if (currentTheme === 'light') {
        newTheme = 'dark';
    } else {
        newTheme = 'light';
    }
    
    setStorageItem('theme', newTheme);
    applyTheme(newTheme);
    
    // Force a repaint to ensure theme changes are applied immediately
    document.body.style.display = 'none';
    document.body.offsetHeight; // Trigger a reflow
    document.body.style.display = '';
    
    return newTheme;
}

// Add a new helper function to apply the theme
function applyTheme(theme) {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const htmlElement = document.documentElement;
    
    // Remove any existing theme attributes
    htmlElement.removeAttribute('data-theme');
    
    // Apply the appropriate theme
    if (theme === 'dark' || (theme === 'auto' && prefersDark)) {
        htmlElement.setAttribute('data-theme', 'dark');
        document.body.dataset.theme = 'dark';
    } else {
        htmlElement.setAttribute('data-theme', 'light');
        document.body.dataset.theme = 'light';
    }
    
    // Update the theme-toggle icon state
    updateThemeToggleIcons(theme);
}

// New function to update theme toggle icons
function updateThemeToggleIcons(theme) {
    const themeToggle = document.querySelector('.theme-toggle');
    if (!themeToggle) return;
    
    // Remove any existing active classes
    themeToggle.classList.remove('theme-light', 'theme-dark', 'theme-auto');
    
    // Add the appropriate class based on current theme
    themeToggle.classList.add(`theme-${theme}`);
}

function filterByFolder(folderPath) {
    document.querySelectorAll('.model-card').forEach(card => {
        card.style.display = card.dataset.folder === folderPath ? '' : 'none';
    });
}

export function openCivitai(filePath) {
    const loraCard = document.querySelector(`.model-card[data-filepath="${filePath}"]`);
    if (!loraCard) return;
    
    const metaData = JSON.parse(loraCard.dataset.meta);
    const civitaiId = metaData.modelId;
    const versionId = metaData.id;
    
    if (civitaiId) {
        let url = `https://civitai.com/models/${civitaiId}`;
        if (versionId) {
            url += `?modelVersionId=${versionId}`;
        }
        window.open(url, '_blank');
    } else {
        // 如果没有ID，尝试使用名称搜索
        const modelName = loraCard.dataset.name;
        window.open(`https://civitai.com/models?query=${encodeURIComponent(modelName)}`, '_blank');
    }
}

/**
 * Dynamically positions the search options panel and filter panel
 * based on the current layout and folder tags container height
 */
export function updatePanelPositions() {
    const searchOptionsPanel = document.getElementById('searchOptionsPanel');
    const filterPanel = document.getElementById('filterPanel');
    
    if (!searchOptionsPanel && !filterPanel) return;
    
    // Get the header element
    const header = document.querySelector('.app-header');
    if (!header) return;
    
    // Calculate the position based on the bottom of the header
    const headerRect = header.getBoundingClientRect();
    const topPosition = headerRect.bottom + 5; // Add 5px padding
    
    // Set the positions
    if (searchOptionsPanel) {
      searchOptionsPanel.style.top = `${topPosition}px`;
    }
    
    if (filterPanel) {
      filterPanel.style.top = `${topPosition}px`;
    }
    
    // Adjust panel horizontal position based on the search container
    const searchContainer = document.querySelector('.header-search');
    if (searchContainer) {
      const searchRect = searchContainer.getBoundingClientRect();
      
      // Position the search options panel aligned with the search container
      if (searchOptionsPanel) {
        searchOptionsPanel.style.right = `${window.innerWidth - searchRect.right}px`;
      }
      
      // Position the filter panel aligned with the filter button
      if (filterPanel) {
        const filterButton = document.getElementById('filterButton');
        if (filterButton) {
          const filterRect = filterButton.getBoundingClientRect();
          filterPanel.style.right = `${window.innerWidth - filterRect.right}px`;
        }
      }
    }
}

export function initBackToTop() {
    const button = document.getElementById('backToTopBtn');
    if (!button) return;

    // Get the scrollable container
    const scrollContainer = document.querySelector('.page-content');
    
    // Show/hide button based on scroll position
    const toggleBackToTop = () => {
        const scrollThreshold = window.innerHeight * 0.3;
        if (scrollContainer.scrollTop > scrollThreshold) {
            button.classList.add('visible');
        } else {
            button.classList.remove('visible');
        }
    };

    // Smooth scroll to top
    button.addEventListener('click', () => {
        scrollContainer.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // Listen for scroll events on the scrollable container
    scrollContainer.addEventListener('scroll', toggleBackToTop);
    
    // Initial check
    toggleBackToTop();
}

export function getNSFWLevelName(level) {
    if (level === 0) return 'Unknown';
    if (level >= 32) return 'Blocked';
    if (level >= 16) return 'XXX';
    if (level >= 8) return 'X';
    if (level >= 4) return 'R';
    if (level >= 2) return 'PG13';
    if (level >= 1) return 'PG';
    return 'Unknown';
}

function parseUsageTipNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
}

export function getLoraStrengthsFromUsageTips(usageTips = {}) {
  const parsedStrength = parseUsageTipNumber(usageTips.strength);
  const clipStrengthSource = usageTips.clip_strength ?? usageTips.clipStrength;
  const parsedClipStrength = parseUsageTipNumber(clipStrengthSource);

  return {
    strength: parsedStrength !== null ? parsedStrength : 1,
    hasStrength: parsedStrength !== null,
    clipStrength: parsedClipStrength,
    hasClipStrength: parsedClipStrength !== null,
  };
}

export function buildLoraSyntax(fileName, usageTips = {}) {
  const { strength, hasStrength, clipStrength, hasClipStrength } = getLoraStrengthsFromUsageTips(usageTips);

  if (hasClipStrength) {
    const modelStrength = hasStrength ? strength : 1;
    return `<lora:${fileName}:${modelStrength}:${clipStrength}>`;
  }

  return `<lora:${fileName}:${strength}>`;
}

export function copyLoraSyntax(card) {
  const usageTips = JSON.parse(card.dataset.usage_tips || "{}");
  const baseSyntax = buildLoraSyntax(card.dataset.file_name, usageTips);

  // Check if trigger words should be included
  const includeTriggerWords = state.global.settings.include_trigger_words;

  if (!includeTriggerWords) {
    const message = translate('uiHelpers.lora.syntaxCopied', {}, 'LoRA syntax copied to clipboard');
    copyToClipboard(baseSyntax, message);
    return;
  }

  // Get trigger words from metadata
  const meta = card.dataset.meta ? JSON.parse(card.dataset.meta) : null;
  const trainedWords = meta?.trainedWords;

  if (
    !trainedWords ||
    !Array.isArray(trainedWords) ||
    trainedWords.length === 0
  ) {
    const message = translate('uiHelpers.lora.syntaxCopiedNoTriggerWords', {}, 'LoRA syntax copied to clipboard (no trigger words found)');
    copyToClipboard(baseSyntax, message);
    return;
  }

  let finalSyntax = baseSyntax;

  if (trainedWords.length === 1) {
    // Single group: append trigger words to the same line
    const triggers = trainedWords[0]
      .split(",")
      .map((word) => word.trim())
      .filter((word) => word);
    if (triggers.length > 0) {
      finalSyntax = `${baseSyntax}, ${triggers.join(", ")}`;
    }
    const message = translate('uiHelpers.lora.syntaxCopiedWithTriggerWords', {}, 'LoRA syntax with trigger words copied to clipboard');
    copyToClipboard(finalSyntax, message);
  } else {
    // Multiple groups: format with separators
    const groups = trainedWords
      .map((group) => {
        const triggers = group
          .split(",")
          .map((word) => word.trim())
          .filter((word) => word);
        return triggers.join(", ");
      })
      .filter((group) => group);

    if (groups.length > 0) {
      // Use separator between all groups except the first
      finalSyntax = baseSyntax + ", " + groups[0];
      for (let i = 1; i < groups.length; i++) {
        finalSyntax += `\n${"-".repeat(17)}\n${groups[i]}`;
      }
    }
    const message = translate('uiHelpers.lora.syntaxCopiedWithTriggerWordGroups', {}, 'LoRA syntax with trigger word groups copied to clipboard');
    copyToClipboard(finalSyntax, message);
  }
}

async function fetchWorkflowRegistry() {
  try {
    const response = await fetch('/api/lm/get-registry');
    const registryData = await response.json();

    if (!registryData.success) {
      if (registryData.error === 'Standalone Mode Active') {
        showToast('toast.general.cannotInteractStandalone', {}, 'warning');
      } else {
        showToast('toast.general.failedWorkflowInfo', {}, 'error');
      }
      return null;
    }

    return registryData.data;
  } catch (error) {
    console.error('Failed to get registry:', error);
    showToast('uiHelpers.workflow.communicationFailed', {}, 'error');
    return null;
  }
}

function filterRegistryNodes(nodes = {}, predicate) {
  if (typeof nodes !== 'object' || nodes === null) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(nodes).filter(([, node]) => {
      try {
        return predicate(node);
      } catch (error) {
        console.warn('Failed to evaluate registry node predicate', error);
        return false;
      }
    }),
  );
}

function getWidgetNames(node) {
  if (!node) {
    return [];
  }

  if (Array.isArray(node.widget_names)) {
    return node.widget_names;
  }

  if (node.capabilities && Array.isArray(node.capabilities.widget_names)) {
    return node.capabilities.widget_names;
  }

  return [];
}

function isAbsolutePath(path) {
  if (typeof path !== 'string') {
    return false;
  }

  return path.startsWith('/') || path.startsWith('\\') || /^[a-zA-Z]:[\\/]/.test(path);
}

async function ensureRelativeModelPath(modelPath, collectionType) {
  if (!modelPath || !isAbsolutePath(modelPath)) {
    return modelPath;
  }

  const fileName = modelPath.split(/[/\\]/).pop();
  if (!fileName) {
    return modelPath;
  }

  try {
    const response = await fetch(`/api/lm/${collectionType}/relative-paths?search=${encodeURIComponent(fileName)}&limit=10`);
    if (!response.ok) {
      return modelPath;
    }
    const data = await response.json();
    const relativePaths = Array.isArray(data?.relative_paths) ? data.relative_paths : [];
    if (relativePaths.length === 0) {
      return modelPath;
    }
    const exactMatch = relativePaths.find((path) => path.endsWith(fileName));
    return exactMatch || relativePaths[0] || modelPath;
  } catch (error) {
    console.warn('LoRA Manager: failed to resolve relative path for model', error);
    return modelPath;
  }
}

/**
 * Sends LoRA syntax to the active ComfyUI workflow
 * @param {string} loraSyntax - The LoRA syntax to send
 * @param {boolean} replaceMode - Whether to replace existing LoRAs (true) or append (false)
 * @param {string} syntaxType - The type of syntax ('lora' or 'recipe')
 * @returns {Promise<boolean>} - Whether the operation was successful
 */
export async function sendLoraToWorkflow(loraSyntax, replaceMode = false, syntaxType = 'lora') {
  const registry = await fetchWorkflowRegistry();
  if (!registry) {
    return false;
  }

  const loraNodes = filterRegistryNodes(registry.nodes, (node) => {
    if (!node) {
      return false;
    }
    if (node.capabilities && typeof node.capabilities === 'object') {
      if (node.capabilities.supports_lora === true) {
        return true;
      }
    }
    return typeof node.type === 'number' && node.type > 0;
  });

  const nodeKeys = Object.keys(loraNodes);
  if (nodeKeys.length === 0) {
    showToast('uiHelpers.workflow.noSupportedNodes', {}, 'warning');
    return false;
  }

  if (nodeKeys.length === 1) {
    return await sendLoraToNodes([nodeKeys[0]], loraNodes, loraSyntax, replaceMode, syntaxType);
  }

  const actionType =
    syntaxType === 'recipe'
      ? translate('uiHelpers.nodeSelector.recipe', {}, 'Recipe')
      : translate('uiHelpers.nodeSelector.lora', {}, 'LoRA');
  const actionMode = replaceMode
    ? translate('uiHelpers.nodeSelector.replace', {}, 'Replace')
    : translate('uiHelpers.nodeSelector.append', {}, 'Append');

  showNodeSelector(loraNodes, {
    actionType,
    actionMode,
    onSend: (selectedNodeIds) =>
      sendLoraToNodes(selectedNodeIds, loraNodes, loraSyntax, replaceMode, syntaxType),
  });
  return true;
}

export async function sendModelPathToWorkflow(modelPath, options) {
  const {
    widgetName,
    collectionType = 'checkpoints',
    actionTypeText = 'Checkpoint',
    successMessage = 'Updated workflow node',
    failureMessage = 'Failed to update workflow node',
    missingNodesMessage = 'No compatible nodes available in the current workflow',
    missingTargetMessage = 'No target node selected',
  } = options;

  if (!widgetName) {
    console.warn('LoRA Manager: widget name is required to send model to workflow');
    return false;
  }

  const relativePath = await ensureRelativeModelPath(modelPath, collectionType);

  const registry = await fetchWorkflowRegistry();
  if (!registry) {
    return false;
  }

  const targetNodes = filterRegistryNodes(registry.nodes, (node) => {
    const widgetNames = getWidgetNames(node);
    return widgetNames.includes(widgetName);
  });

  const nodeKeys = Object.keys(targetNodes);
  if (nodeKeys.length === 0) {
    showToast(missingNodesMessage, {}, 'warning');
    return false;
  }

  const actionType = actionTypeText;
  const actionMode = translate('uiHelpers.nodeSelector.replace', {}, 'Replace');

  const messages = {
    successMessage,
    failureMessage,
    missingTargetMessage,
  };

  const handleSend = (selectedNodeIds) =>
    sendWidgetValueToNodes(selectedNodeIds, targetNodes, widgetName, relativePath, messages);

  if (nodeKeys.length === 1) {
    return await handleSend([nodeKeys[0]]);
  }

  showNodeSelector(targetNodes, {
    actionType,
    actionMode,
    onSend: handleSend,
  });
  return true;
}

/**
 * Send LoRA to specific nodes
 * @param {Array|undefined} nodeIds - Array of node IDs or undefined for desktop mode
 * @param {string} loraSyntax - The LoRA syntax to send
 * @param {boolean} replaceMode - Whether to replace existing LoRAs
 * @param {string} syntaxType - The type of syntax ('lora' or 'recipe')
 */
function resolveNodeReference(nodeKey, nodesMap) {
  if (!nodeKey) {
    return null;
  }

  const directMatch = nodesMap?.[nodeKey];
  if (directMatch) {
    return {
      node_id: directMatch.id,
      graph_id: directMatch.graph_id ?? null,
    };
  }

  if (typeof nodeKey === 'string' && nodeKey.includes(':')) {
    const [graphId, ...rest] = nodeKey.split(':');
    const nodeIdPart = rest.join(':');
    const numericNodeId = Number(nodeIdPart);
    return {
      node_id: Number.isNaN(numericNodeId) ? nodeIdPart : numericNodeId,
      graph_id: graphId || null,
    };
  }

  const numericId = Number(nodeKey);
  return {
    node_id: Number.isNaN(numericId) ? nodeKey : numericId,
    graph_id: null,
  };
}

async function sendLoraToNodes(nodeIds, nodesMap, loraSyntax, replaceMode, syntaxType) {
  try {
    // Call the backend API to update the lora code
    const requestBody = {
      lora_code: loraSyntax,
      mode: replaceMode ? 'replace' : 'append'
    };

    if (Array.isArray(nodeIds)) {
      const references = nodeIds
        .map((nodeKey) => resolveNodeReference(nodeKey, nodesMap))
        .filter((reference) => reference && reference.node_id !== undefined);

      if (references.length > 0) {
        requestBody.node_ids = references;
      }
    } else if (nodeIds) {
      const reference = resolveNodeReference(nodeIds, nodesMap);
      if (reference) {
        requestBody.node_ids = [reference];
      }
    }

    const response = await fetch('/api/lm/update-lora-code', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });
    
    const result = await response.json();
    
    if (result.success) {
      // Use different toast messages based on syntax type
      if (syntaxType === 'recipe') {
        const messageKey = replaceMode ? 
          'uiHelpers.workflow.recipeReplaced' :
          'uiHelpers.workflow.recipeAdded';
        showToast(messageKey, {}, 'success');
      } else {
        const messageKey = replaceMode ? 
          'uiHelpers.workflow.loraReplaced' :
          'uiHelpers.workflow.loraAdded';
        showToast(messageKey, {}, 'success');
      }
      return true;
    } else {
      const messageKey = syntaxType === 'recipe' ? 
        'uiHelpers.workflow.recipeFailedToSend' :
        'uiHelpers.workflow.loraFailedToSend';
      showToast(messageKey, {}, 'error');
      return false;
    }
  } catch (error) {
    console.error('Failed to send to workflow:', error);
    const messageKey = syntaxType === 'recipe' ? 
      'uiHelpers.workflow.recipeFailedToSend' :
      'uiHelpers.workflow.loraFailedToSend';
    showToast(messageKey, {}, 'error');
    return false;
  }
}

async function sendWidgetValueToNodes(nodeIds, nodesMap, widgetName, value, messages = {}) {
  const {
    successMessage = 'Updated workflow node',
    failureMessage = 'Failed to update workflow node',
    missingTargetMessage = 'No target node selected',
  } = messages;

  const targetIds = Array.isArray(nodeIds) ? nodeIds : [];
  if (targetIds.length === 0) {
    showToast(missingTargetMessage, {}, 'warning');
    return false;
  }

  const references = targetIds
    .map((nodeKey) => resolveNodeReference(nodeKey, nodesMap))
    .filter((reference) => reference && reference.node_id !== undefined);

  if (references.length === 0) {
    showToast(missingTargetMessage, {}, 'warning');
    return false;
  }

  try {
    const response = await fetch('/api/lm/update-node-widget', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        widget_name: widgetName,
        value,
        node_ids: references,
      }),
    });

    const result = await response.json();
    if (result.success) {
      showToast(successMessage, {}, 'success');
      return true;
    }

    const errorMessage = result?.error || failureMessage;
    showToast(errorMessage, {}, 'error');
    return false;
  } catch (error) {
    console.error('Failed to send widget value to workflow:', error);
    showToast(failureMessage, {}, 'error');
    return false;
  }
}

// Global variable to track active node selector state
let nodeSelectorState = {
  isActive: false,
  clickHandler: null,
  selectorClickHandler: null,
  currentNodes: {},
  onSend: null,
  enableSendAll: true,
};

/**
 * Show node selector popup near mouse position
 * @param {Object} nodes - Registry nodes data
 * @param {Object} options - Configuration for display and actions
 * @param {string} options.actionType - Display label for the action type (e.g. LoRA)
 * @param {string} options.actionMode - Display label for the action mode (e.g. Replace)
 * @param {Function} options.onSend - Callback invoked with selected node ids
 * @param {boolean} [options.enableSendAll=true] - Whether to show the "send to all" option
 */
function showNodeSelector(nodes, options = {}) {
  const selector = document.getElementById('nodeSelector');
  if (!selector) return;
  
  // Clean up any existing state
  hideNodeSelector();

  const safeNodes = nodes || {};
  const onSend = typeof options.onSend === 'function' ? options.onSend : null;
  if (!onSend) {
    console.warn('LoRA Manager: node selector invoked without send handler');
    return;
  }

  nodeSelectorState.currentNodes = safeNodes;
  nodeSelectorState.onSend = onSend;
  nodeSelectorState.enableSendAll = options.enableSendAll !== false;
  
  // Generate node list HTML with icons and proper colors
  const nodeItems = Object.entries(safeNodes).map(([nodeKey, node]) => {
    const iconClass = NODE_TYPE_ICONS[node.type] || 'fas fa-question-circle';
    const bgColor = node.bgcolor || DEFAULT_NODE_COLOR;
    const graphLabel = node.graph_name ? ` (${node.graph_name})` : '';

    return `
      <div class="node-item" data-node-id="${nodeKey}">
        <div class="node-icon-indicator" style="background-color: ${bgColor}">
          <i class="${iconClass}"></i>
        </div>
        <span>#${node.id}${graphLabel} ${node.title}</span>
      </div>
    `;
  }).join('');
  
  // Add header with action mode indicator
  const actionType = options.actionType ?? translate('uiHelpers.nodeSelector.lora', {}, 'LoRA');
  const actionMode = options.actionMode ?? translate('uiHelpers.nodeSelector.replace', {}, 'Replace');
  const selectTargetNodeText = translate('uiHelpers.nodeSelector.selectTargetNode', {}, 'Select target node');
  const sendToAllText = translate('uiHelpers.nodeSelector.sendToAll', {}, 'Send to All');

  const sendAllMarkup = nodeSelectorState.enableSendAll
    ? `
    <div class="node-item send-all-item" data-action="send-all">
      <div class="node-icon-indicator all-nodes">
        <i class="fas fa-broadcast-tower"></i>
      </div>
      <span>${sendToAllText}</span>
    </div>`
    : '';
  
  selector.innerHTML = `
    <div class="node-selector-header">
      <span class="selector-action-type">${actionMode} ${actionType}</span>
      <span class="selector-instruction">${selectTargetNodeText}</span>
    </div>
    ${nodeItems}
    ${sendAllMarkup}
  `;
  
  // Position near mouse
  positionNearMouse(selector);
  
  // Show selector
  selector.style.display = 'block';
  nodeSelectorState.isActive = true;
  
  // Update event manager state
  eventManager.setState('nodeSelectorActive', true);
  
  // Setup event listeners with proper cleanup through event manager
  setupNodeSelectorEvents(selector);
}

/**
 * Setup event listeners for node selector using event manager
 * @param {HTMLElement} selector - The selector element
 */
function setupNodeSelectorEvents(selector) {
  // Clean up any existing event listeners
  cleanupNodeSelectorEvents();
  
  // Register click outside handler with event manager
  eventManager.addHandler('click', 'nodeSelector-outside', (e) => {
    if (!selector.contains(e.target)) {
      hideNodeSelector();
      return true; // Stop propagation
    }
  }, {
    priority: 200, // High priority to handle before other click handlers
    onlyWhenNodeSelectorActive: true
  });
  
  // Register node selection handler with event manager  
  eventManager.addHandler('click', 'nodeSelector-selection', async (e) => {
    const nodeItem = e.target.closest('.node-item');
    if (!nodeItem) return false; // Continue with other handlers
    
    const onSend = nodeSelectorState.onSend;
    if (typeof onSend !== 'function') {
      hideNodeSelector();
      return true;
    }

    e.stopPropagation();
    
    const action = nodeItem.dataset.action;
    const nodeId = nodeItem.dataset.nodeId;
    const nodes = nodeSelectorState.currentNodes || {};
    
    try {
      if (action === 'send-all') {
        if (!nodeSelectorState.enableSendAll) {
          return true;
        }
        const allNodeIds = Object.keys(nodes);
        await onSend(allNodeIds);
      } else if (nodeId) {
        await onSend([nodeId]);
      }
    } finally {
      hideNodeSelector();
    }

    return true; // Stop propagation
  }, {
    priority: 150, // High priority but lower than outside click
    targetSelector: '#nodeSelector',
    onlyWhenNodeSelectorActive: true
  });
}

/**
 * Clean up node selector event listeners
 */
function cleanupNodeSelectorEvents() {
  // Remove event handlers from event manager
  eventManager.removeHandler('click', 'nodeSelector-outside');
  eventManager.removeHandler('click', 'nodeSelector-selection');
  
  // Clear legacy references
  nodeSelectorState.clickHandler = null;
  nodeSelectorState.selectorClickHandler = null;
}

/**
 * Hide node selector
 */
function hideNodeSelector() {
  const selector = document.getElementById('nodeSelector');
  if (selector) {
    selector.style.display = 'none';
    selector.innerHTML = ''; // Clear content to prevent memory leaks
  }
  
  // Clean up event listeners
  cleanupNodeSelectorEvents();
  nodeSelectorState.isActive = false;
  nodeSelectorState.currentNodes = {};
  nodeSelectorState.onSend = null;
  nodeSelectorState.enableSendAll = true;
  
  // Update event manager state
  eventManager.setState('nodeSelectorActive', false);
}

/**
 * Position element near mouse cursor
 * @param {HTMLElement} element - Element to position
 */
function positionNearMouse(element) {
  // Get current mouse position from last mouse event or use default
  const mouseX = window.lastMouseX || window.innerWidth / 2;
  const mouseY = window.lastMouseY || window.innerHeight / 2;
  
  // Show element temporarily to get dimensions
  element.style.visibility = 'hidden';
  element.style.display = 'block';
  
  const rect = element.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  
  // Calculate position with offset from mouse
  let x = mouseX + 10;
  let y = mouseY + 10;
  
  // Ensure element doesn't go offscreen
  if (x + rect.width > viewportWidth) {
    x = mouseX - rect.width - 10;
  }
  
  if (y + rect.height > viewportHeight) {
    y = mouseY - rect.height - 10;
  }
  
  // Apply position
  element.style.left = `${x}px`;
  element.style.top = `${y}px`;
  element.style.visibility = 'visible';
}

/**
 * Initialize mouse tracking for positioning elements
 */
export function initializeMouseTracking() {
  // Register mouse tracking with event manager
  eventManager.addHandler('mousemove', 'uiHelpers-mouseTracking', (e) => {
    window.lastMouseX = e.clientX;
    window.lastMouseY = e.clientY;
  }, {
    priority: 10 // Low priority since this is just tracking
  });
}

// Initialize mouse tracking when module loads
initializeMouseTracking();

/**
 * Opens the example images folder for a specific model
 * @param {string} modelHash - The SHA256 hash of the model
 */
export async function openExampleImagesFolder(modelHash) {
  try {
    const response = await fetch('/api/lm/open-example-images-folder', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model_hash: modelHash
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      const message = translate('uiHelpers.exampleImages.openingFolder', {}, 'Opening example images folder');
      showToast('uiHelpers.exampleImages.opened', {}, 'success');
      return true;
    } else {
      showToast('uiHelpers.exampleImages.failedToOpen', {}, 'error');
      return false;
    }
  } catch (error) {
    console.error('Failed to open example images folder:', error);
    showToast('uiHelpers.exampleImages.failedToOpen', {}, 'error');
    return false;
  }
}
