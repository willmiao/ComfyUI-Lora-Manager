import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { TextAreaCaretHelper } from "./textarea_caret_helper.js";
import { getPromptCustomWordsAutocompletePreference } from "./settings.js";

// Command definitions for category filtering
const TAG_COMMANDS = {
    '/character': { categories: [4, 11], label: 'Character' },
    '/char': { categories: [4, 11], label: 'Character' },
    '/artist': { categories: [1, 8], label: 'Artist' },
    '/general': { categories: [0, 7], label: 'General' },
    '/copyright': { categories: [3, 10], label: 'Copyright' },
    '/meta': { categories: [5, 14], label: 'Meta' },
    '/species': { categories: [12], label: 'Species' },
    '/lore': { categories: [15], label: 'Lore' },
    '/emb': { type: 'embedding', label: 'Embeddings' },
    '/embedding': { type: 'embedding', label: 'Embeddings' },
};

// Category display information
const CATEGORY_INFO = {
    0: { bg: 'rgba(0, 155, 230, 0.2)', text: '#4bb4ff', label: 'General' },
    1: { bg: 'rgba(255, 138, 139, 0.2)', text: '#ffc3c3', label: 'Artist' },
    3: { bg: 'rgba(199, 151, 255, 0.2)', text: '#ddc9fb', label: 'Copyright' },
    4: { bg: 'rgba(53, 198, 74, 0.2)', text: '#93e49a', label: 'Character' },
    5: { bg: 'rgba(234, 208, 132, 0.2)', text: '#f7e7c3', label: 'Meta' },
    7: { bg: 'rgba(0, 155, 230, 0.2)', text: '#4bb4ff', label: 'General' },
    8: { bg: 'rgba(255, 138, 139, 0.2)', text: '#ffc3c3', label: 'Artist' },
    10: { bg: 'rgba(199, 151, 255, 0.2)', text: '#ddc9fb', label: 'Copyright' },
    11: { bg: 'rgba(53, 198, 74, 0.2)', text: '#93e49a', label: 'Character' },
    12: { bg: 'rgba(237, 137, 54, 0.2)', text: '#f6ad55', label: 'Species' },
    14: { bg: 'rgba(234, 208, 132, 0.2)', text: '#f7e7c3', label: 'Meta' },
    15: { bg: 'rgba(72, 187, 120, 0.2)', text: '#68d391', label: 'Lore' },
};

// Format post count with K/M suffix
function formatPostCount(count) {
    if (count >= 1000000) {
        return (count / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
    } else if (count >= 1000) {
        return (count / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
    }
    return count.toString();
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

function splitRelativePath(relativePath = '') {
    const parts = relativePath.split(/[/\\]+/).filter(Boolean);
    const fileName = parts.pop() ?? '';
    return {
        directories: parts,
        fileName,
    };
}

function removeGeneralExtension(fileName = '') {
    return fileName.replace(/\.[^.]+$/, '');
}

function removeLoraExtension(fileName = '') {
    return fileName.replace(/\.(safetensors|ckpt|pt|bin)$/i, '');
}

function parseSearchTokens(term = '') {
    const include = [];
    const exclude = [];

    term.split(/\s+/).forEach((rawTerm) => {
        const token = rawTerm.trim();
        if (!token) {
            return;
        }
        if (token.startsWith('-') && token.length > 1) {
            exclude.push(token.slice(1).toLowerCase());
        } else {
            include.push(token.toLowerCase());
        }
    });

    return { include, exclude };
}

function createDefaultBehavior(modelType) {
    return {
        enablePreview: false,
        async getInsertText(_instance, relativePath) {
            const trimmed = relativePath?.trim() ?? '';
            if (!trimmed) {
                return '';
            }
            return `${trimmed}, `;
        },
    };
}

const MODEL_BEHAVIORS = {
    loras: {
        enablePreview: true,
        init(instance) {
            if (!instance.options.showPreview) {
                return;
            }
            instance.initPreviewTooltip({ modelType: instance.modelType });
        },
        showPreview(instance, relativePath, itemElement) {
            if (!instance.previewTooltip) {
                return;
            }
            instance.showPreviewForItem(relativePath, itemElement);
        },
        hidePreview(instance) {
            if (!instance.previewTooltip) {
                return;
            }
            instance.previewTooltip.hide();
        },
        destroy(instance) {
            if (instance.previewTooltip) {
                instance.previewTooltip.cleanup();
                instance.previewTooltip = null;
            }
        },
        async getInsertText(_instance, relativePath) {
            const fileName = removeLoraExtension(splitRelativePath(relativePath).fileName);

            let strength = 1.0;
            let hasStrength = false;
            let clipStrength = null;

            try {
                const response = await api.fetchApi(`/lm/loras/usage-tips-by-path?relative_path=${encodeURIComponent(relativePath)}`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.usage_tips) {
                        try {
                            const usageTips = JSON.parse(data.usage_tips);
                            const parsedStrength = parseUsageTipNumber(usageTips.strength);
                            if (parsedStrength !== null) {
                                strength = parsedStrength;
                                hasStrength = true;
                            }
                            const clipSource = usageTips.clip_strength ?? usageTips.clipStrength;
                            const parsedClipStrength = parseUsageTipNumber(clipSource);
                            if (parsedClipStrength !== null) {
                                clipStrength = parsedClipStrength;
                                if (!hasStrength) {
                                    strength = 1.0;
                                }
                            }
                        } catch (parseError) {
                            console.warn('Failed to parse usage tips JSON:', parseError);
                        }
                    }
                }
            } catch (error) {
                console.warn('Failed to fetch usage tips:', error);
            }

            if (clipStrength !== null) {
                return `<lora:${fileName}:${strength}:${clipStrength}>, `;
            }
            return `<lora:${fileName}:${strength}>, `;
        }
    },
    embeddings: {
        enablePreview: true,
        init(instance) {
            if (!instance.options.showPreview) {
                return;
            }
            instance.initPreviewTooltip({ modelType: instance.modelType });
        },
        async getInsertText(_instance, relativePath) {
            const { directories, fileName } = splitRelativePath(relativePath);
            const trimmedName = removeGeneralExtension(fileName);
            const folder = directories.length ? `${directories.join('\\')}\\` : '';
            return `embedding:${folder}${trimmedName}, `;
        },
    },
    custom_words: {
        enablePreview: false,
        async getInsertText(_instance, relativePath) {
            return `${relativePath}, `;
        },
    },
    prompt: {
        enablePreview: true,
        init(instance) {
            if (!instance.options.showPreview) {
                return;
            }
            instance.initPreviewTooltip({ modelType: 'embeddings' });
        },
        showPreview(instance, relativePath, itemElement) {
            if (!instance.previewTooltip || instance.searchType !== 'embeddings') {
                return;
            }
            instance.showPreviewForItem(relativePath, itemElement);
        },
        hidePreview(instance) {
            if (!instance.previewTooltip || instance.searchType !== 'embeddings') {
                return;
            }
            instance.previewTooltip.hide();
        },
        destroy(instance) {
            if (instance.previewTooltip) {
                instance.previewTooltip.cleanup();
                instance.previewTooltip = null;
            }
        },
        async getInsertText(instance, relativePath) {
            const rawSearchTerm = instance.getSearchTerm(instance.inputElement.value);
            const match = rawSearchTerm.match(/^emb:(.*)$/i);

            if (match) {
                const { directories, fileName } = splitRelativePath(relativePath);
                const trimmedName = removeGeneralExtension(fileName);
                const folder = directories.length ? `${directories.join('\\')}\\` : '';
                return `embedding:${folder}${trimmedName}, `;
            } else {
                return `${relativePath}, `;
            }
        },
    },
};

function getModelBehavior(modelType) {
    return MODEL_BEHAVIORS[modelType] ?? createDefaultBehavior(modelType);
}

class AutoComplete {
    constructor(inputElement, modelType = 'loras', options = {}) {
        this.inputElement = inputElement;
        this.modelType = modelType;
        this.behavior = getModelBehavior(modelType);
        this.options = {
            maxItems: 20,
            minChars: 1,
            debounceDelay: 200,
            showPreview: this.behavior.enablePreview ?? false,
            ...options
        };
        
        this.dropdown = null;
        this.selectedIndex = -1;
        this.items = [];
        this.debounceTimer = null;
        this.isVisible = false;
        this.currentSearchTerm = '';
        this.previewTooltip = null;
        this.previewTooltipPromise = null;
        this.searchType = null;

        // Command mode state
        this.activeCommand = null;  // Current active command (e.g., { categories: [4, 11], label: 'Character' })
        this.showingCommands = false;  // Whether showing command list dropdown

        // Initialize TextAreaCaretHelper
        this.helper = new TextAreaCaretHelper(inputElement, () => app.canvas.ds.scale);

        this.onInput = null;
        this.onKeyDown = null;
        this.onBlur = null;
        this.onDocumentClick = null;

        this.init();
    }
    
    init() {
        this.createDropdown();
        this.bindEvents();
    }
    
    createDropdown() {
        this.dropdown = document.createElement('div');
        this.dropdown.className = 'comfy-autocomplete-dropdown';
        
        // Apply new color scheme
        this.dropdown.style.cssText = `
            position: absolute;
            z-index: 10000;
            overflow-y: visible;
            background-color: rgba(40, 44, 52, 0.95);
            border: 1px solid rgba(226, 232, 240, 0.2);
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            display: none;
            min-width: 200px;
            width: auto;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        `;
        
        // Custom scrollbar styles with new color scheme
        const style = document.createElement('style');
        style.textContent = `
            .comfy-autocomplete-dropdown::-webkit-scrollbar {
                width: 8px;
            }
            .comfy-autocomplete-dropdown::-webkit-scrollbar-track {
                background: rgba(40, 44, 52, 0.3);
                border-radius: 4px;
            }
            .comfy-autocomplete-dropdown::-webkit-scrollbar-thumb {
                background: rgba(226, 232, 240, 0.2);
                border-radius: 4px;
            }
            .comfy-autocomplete-dropdown::-webkit-scrollbar-thumb:hover {
                background: rgba(226, 232, 240, 0.4);
            }
        `;
        document.head.appendChild(style);
        
        // Append to body to avoid overflow issues
        document.body.appendChild(this.dropdown);

        if (typeof this.behavior.init === 'function') {
            this.behavior.init(this);
        }
    }
    
    initPreviewTooltip(options = {}) {
        if (this.previewTooltip || this.previewTooltipPromise) {
            return;
        }
        // Dynamically import and create preview tooltip
        this.previewTooltipPromise = import('./preview_tooltip.js').then(module => {
            const config = { modelType: this.modelType, ...options };
            this.previewTooltip = new module.PreviewTooltip(config);
        }).catch(err => {
            console.warn('Failed to load preview tooltip:', err);
        }).finally(() => {
            this.previewTooltipPromise = null;
        });
    }
    
    bindEvents() {
        // Handle input changes
        this.onInput = (e) => {
            this.handleInput(e.target.value);
        };
        this.inputElement.addEventListener('input', this.onInput);

        // Handle keyboard navigation
        this.onKeyDown = (e) => {
            this.handleKeyDown(e);
        };
        this.inputElement.addEventListener('keydown', this.onKeyDown);

        // Handle focus out to hide dropdown
        this.onBlur = () => {
            // Delay hiding to allow for clicks on dropdown items
            setTimeout(() => {
                this.hide();
            }, 150);
        };
        this.inputElement.addEventListener('blur', this.onBlur);

        // Handle clicks outside to hide dropdown
        this.onDocumentClick = (e) => {
            if (!this.dropdown) {
                return;
            }

            const target = e.target;
            if (!(target instanceof Node)) {
                return;
            }

            if (!this.dropdown.contains(target) && target !== this.inputElement) {
                this.hide();
            }
        };
        document.addEventListener('click', this.onDocumentClick);

        // Mark this element as having autocomplete events bound
        this.inputElement._autocompleteEventsBound = true;
    }

    /**
     * Check if the autocomplete is valid (input element is in DOM and events are bound)
     */
    isValid() {
        return this.inputElement &&
               document.body.contains(this.inputElement) &&
               this.inputElement._autocompleteEventsBound === true;
    }

    /**
     * Check if events need to be rebound (element exists but events not bound)
     */
    needsRebind() {
        return this.inputElement &&
               document.body.contains(this.inputElement) &&
               this.inputElement._autocompleteEventsBound !== true;
    }

    /**
     * Rebind events to the input element (useful after Vue moves the element)
     */
    rebindEvents() {
        // Remove old listeners if they exist
        if (this.onInput) {
            this.inputElement.removeEventListener('input', this.onInput);
        }
        if (this.onKeyDown) {
            this.inputElement.removeEventListener('keydown', this.onKeyDown);
        }
        if (this.onBlur) {
            this.inputElement.removeEventListener('blur', this.onBlur);
        }

        // Rebind all events
        this.bindEvents();

        console.log('[Lora Manager] Autocomplete events rebound');
    }

    /**
     * Refresh the TextAreaCaretHelper (useful after element properties change)
     */
    refreshHelper() {
        if (this.inputElement && document.body.contains(this.inputElement)) {
            this.helper = new TextAreaCaretHelper(this.inputElement, () => app.canvas.ds.scale);
        }
    }
    
    handleInput(value = '') {
        // Clear previous debounce timer
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // Get the search term (text after last comma / '>')
        const rawSearchTerm = this.getSearchTerm(value);
        let searchTerm = rawSearchTerm;
        let endpoint = `/lm/${this.modelType}/relative-paths`;

        // For embeddings, only trigger autocomplete when the current token
        // starts with the explicit "emb:" prefix. This avoids interrupting
        // normal prompt typing while still allowing quick manual triggering.
        if (this.modelType === 'embeddings') {
            const match = rawSearchTerm.match(/^emb:(.*)$/i);
            if (!match) {
                this.hide();
                return;
            }
            searchTerm = (match[1] || '').trim();
        }

        // For prompt model type, check if we're searching embeddings or custom words
        if (this.modelType === 'prompt') {
            const match = rawSearchTerm.match(/^emb:(.*)$/i);
            if (match) {
                // User typed "emb:" prefix - always allow embeddings search
                endpoint = '/lm/embeddings/relative-paths';
                searchTerm = (match[1] || '').trim();
                this.searchType = 'embeddings';
                this.activeCommand = null;
                this.showingCommands = false;
            } else if (getPromptCustomWordsAutocompletePreference()) {
                // Setting enabled - check for command mode
                const commandResult = this._parseCommandInput(rawSearchTerm);

                if (commandResult.showCommands) {
                    // Show command list dropdown
                    this.showingCommands = true;
                    this.activeCommand = null;
                    this.searchType = 'commands';
                    this._showCommandList(commandResult.commandFilter);
                    return;
                } else if (commandResult.command) {
                    // Command is active, use filtered search
                    this.showingCommands = false;
                    this.activeCommand = commandResult.command;
                    searchTerm = commandResult.searchTerm;

                    if (commandResult.command.type === 'embedding') {
                        // /emb or /embedding command
                        endpoint = '/lm/embeddings/relative-paths';
                        this.searchType = 'embeddings';
                    } else {
                        // Category filter command
                        const categories = commandResult.command.categories.join(',');
                        endpoint = `/lm/custom-words/search?category=${categories}`;
                        this.searchType = 'custom_words';
                    }
                } else {
                    // No command - regular custom words search with enriched results
                    this.showingCommands = false;
                    this.activeCommand = null;
                    endpoint = '/lm/custom-words/search?enriched=true';
                    searchTerm = rawSearchTerm;
                    this.searchType = 'custom_words';
                }
            } else {
                // Setting disabled - no autocomplete for non-emb: terms
                this.hide();
                return;
            }
        }

        if (searchTerm.length < this.options.minChars) {
            this.hide();
            return;
        }

        // Debounce the search
        this.debounceTimer = setTimeout(() => {
            this.search(searchTerm, endpoint);
        }, this.options.debounceDelay);
    }
    
    getSearchTerm(value) {
        // Use helper to get text before cursor for more accurate positioning
        const beforeCursor = this.helper.getBeforeCursor();
        if (!beforeCursor) {
            return '';
        }

        // Split on comma and '>' delimiters only (do not split on spaces)
        const segments = beforeCursor.split(/[,\>]+/);

        // Return the last non-empty segment as search term
        const lastSegment = segments[segments.length - 1] || '';
        return lastSegment.trim();
    }

    async search(term = '', endpoint = null) {
        try {
            this.currentSearchTerm = term;

            if (!endpoint) {
                endpoint = `/lm/${this.modelType}/relative-paths`;
            }

            const url = endpoint.includes('?')
                ? `${endpoint}&search=${encodeURIComponent(term)}&limit=${this.options.maxItems}`
                : `${endpoint}?search=${encodeURIComponent(term)}&limit=${this.options.maxItems}`;

            const response = await api.fetchApi(url);
            const data = await response.json();

            // Support both response formats:
            // 1. Model endpoint format: { success: true, relative_paths: [...] }
            // 2. Custom words format: { success: true, words: [...] }
            if (data.success) {
                const items = data.relative_paths || data.words || [];
                if (items.length > 0) {
                    this.items = items;
                    this.render();
                    this.show();
                } else {
                    this.items = [];
                    this.hide();
                }
            } else {
                this.items = [];
                this.hide();
            }
        } catch (error) {
            console.error('Autocomplete search error:', error);
            this.items = [];
            this.hide();
        }
    }

    /**
     * Parse command input to detect command mode
     * @param {string} rawInput - Raw input text
     * @returns {Object} - { showCommands, commandFilter, command, searchTerm }
     */
    _parseCommandInput(rawInput) {
        const trimmed = rawInput.trim();

        // Check if input starts with "/"
        if (!trimmed.startsWith('/')) {
            return { showCommands: false, command: null, searchTerm: trimmed };
        }

        // Split into potential command and search term
        const spaceIndex = trimmed.indexOf(' ');

        if (spaceIndex === -1) {
            // Still typing command (e.g., "/cha")
            const partialCommand = trimmed.toLowerCase();

            // Check for exact command match
            if (TAG_COMMANDS[partialCommand]) {
                return {
                    showCommands: false,
                    command: TAG_COMMANDS[partialCommand],
                    searchTerm: '',
                };
            }

            // Show command suggestions
            return {
                showCommands: true,
                commandFilter: partialCommand.slice(1), // Remove leading "/"
                command: null,
                searchTerm: '',
            };
        }

        // Command with search term (e.g., "/char miku")
        const commandPart = trimmed.slice(0, spaceIndex).toLowerCase();
        const searchPart = trimmed.slice(spaceIndex + 1).trim();

        if (TAG_COMMANDS[commandPart]) {
            return {
                showCommands: false,
                command: TAG_COMMANDS[commandPart],
                searchTerm: searchPart,
            };
        }

        // Unknown command, treat as regular search
        return { showCommands: false, command: null, searchTerm: trimmed };
    }

    /**
     * Show the command list dropdown
     * @param {string} filter - Optional filter for commands
     */
    _showCommandList(filter = '') {
        const filterLower = filter.toLowerCase();

        // Get unique commands (avoid duplicates like /char and /character)
        const seenLabels = new Set();
        const commands = [];

        for (const [cmd, info] of Object.entries(TAG_COMMANDS)) {
            if (seenLabels.has(info.label)) continue;

            if (!filter || cmd.slice(1).startsWith(filterLower)) {
                seenLabels.add(info.label);
                commands.push({ command: cmd, ...info });
            }
        }

        if (commands.length === 0) {
            this.hide();
            return;
        }

        this.items = commands;
        this._renderCommandList();
        this.show();
    }

    /**
     * Render the command list dropdown
     */
    _renderCommandList() {
        this.dropdown.innerHTML = '';
        this.selectedIndex = -1;

        this.items.forEach((item, index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'comfy-autocomplete-item comfy-autocomplete-command';

            const cmdSpan = document.createElement('span');
            cmdSpan.className = 'lm-autocomplete-command-name';
            cmdSpan.textContent = item.command;

            const labelSpan = document.createElement('span');
            labelSpan.className = 'lm-autocomplete-command-label';
            labelSpan.textContent = item.label;

            itemEl.appendChild(cmdSpan);
            itemEl.appendChild(labelSpan);

            itemEl.style.cssText = `
                padding: 8px 12px;
                cursor: pointer;
                color: rgba(226, 232, 240, 0.8);
                border-bottom: 1px solid rgba(226, 232, 240, 0.1);
                transition: all 0.2s ease;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
            `;

            itemEl.addEventListener('mouseenter', () => {
                this.selectItem(index);
            });

            itemEl.addEventListener('click', () => {
                this._insertCommand(item.command);
            });

            this.dropdown.appendChild(itemEl);
        });

        // Remove border from last item
        if (this.dropdown.lastChild) {
            this.dropdown.lastChild.style.borderBottom = 'none';
        }

        // Auto-select first item
        if (this.items.length > 0) {
            setTimeout(() => this.selectItem(0), 100);
        }
    }

    /**
     * Insert a command into the input
     * @param {string} command - The command to insert (e.g., "/char")
     */
    _insertCommand(command) {
        const currentValue = this.inputElement.value;
        const caretPos = this.getCaretPosition();

        // Find the start of the current command being typed
        const beforeCursor = currentValue.substring(0, caretPos);
        const segments = beforeCursor.split(/[,\>]+/);
        const lastSegment = segments[segments.length - 1];
        const commandStartPos = caretPos - lastSegment.length;

        // Insert command with trailing space
        const insertText = command + ' ';
        const newValue = currentValue.substring(0, commandStartPos) + insertText + currentValue.substring(caretPos);
        const newCaretPos = commandStartPos + insertText.length;

        this.inputElement.value = newValue;

        // Trigger input event
        const event = new Event('input', { bubbles: true });
        this.inputElement.dispatchEvent(event);

        this.hide();

        // Focus and position cursor
        this.inputElement.focus();
        this.inputElement.setSelectionRange(newCaretPos, newCaretPos);
    }

    render() {
        this.dropdown.innerHTML = '';
        this.selectedIndex = -1;

        // Early return if no items to prevent empty dropdown
        if (!this.items || this.items.length === 0) {
            return;
        }

        // Check if items are enriched (have tag_name, category, post_count)
        const isEnriched = this.items[0] && typeof this.items[0] === 'object' && 'tag_name' in this.items[0];

        this.items.forEach((itemData, index) => {
            const item = document.createElement('div');
            item.className = 'comfy-autocomplete-item';

            // Get the display text and path for insertion
            const displayText = isEnriched ? itemData.tag_name : itemData;
            const insertPath = isEnriched ? itemData.tag_name : itemData;

            if (isEnriched) {
                // Render enriched item with category badge and post count
                this._renderEnrichedItem(item, itemData, this.currentSearchTerm);
            } else {
                // Create highlighted content for simple items, wrapped in a span
                // to prevent flex layout from breaking up the text
                const nameSpan = document.createElement('span');
                nameSpan.className = 'lm-autocomplete-name';
                nameSpan.innerHTML = this.highlightMatch(displayText, this.currentSearchTerm);
                nameSpan.style.cssText = `
                    flex: 1;
                    min-width: 0;
                    overflow: hidden;
                    text-overflow: ellipsis;
                `;
                item.appendChild(nameSpan);
            }

            // Apply item styles with new color scheme
            item.style.cssText = `
                padding: 8px 12px;
                cursor: pointer;
                color: rgba(226, 232, 240, 0.8);
                border-bottom: 1px solid rgba(226, 232, 240, 0.1);
                transition: all 0.2s ease;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                position: relative;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 8px;
            `;

            // Hover and selection handlers
            item.addEventListener('mouseenter', () => {
                this.selectItem(index);
            });

            item.addEventListener('mouseleave', () => {
                this.hidePreview();
            });

            // Click handler
            item.addEventListener('click', () => {
                this.insertSelection(insertPath);
            });

            this.dropdown.appendChild(item);
        });

        // Remove border from last item
        if (this.dropdown.lastChild) {
            this.dropdown.lastChild.style.borderBottom = 'none';
        }

        // Auto-select the first item with a small delay
        if (this.items.length > 0) {
            setTimeout(() => {
                this.selectItem(0);
            }, 100);
        }
    }

    /**
     * Render an enriched autocomplete item with category badge and post count
     * @param {HTMLElement} itemEl - The item element to populate
     * @param {Object} itemData - The enriched item data { tag_name, category, post_count }
     * @param {string} searchTerm - The current search term for highlighting
     */
    _renderEnrichedItem(itemEl, itemData, searchTerm) {
        // Create name span with highlighted match
        const nameSpan = document.createElement('span');
        nameSpan.className = 'lm-autocomplete-name';
        nameSpan.innerHTML = this.highlightMatch(itemData.tag_name, searchTerm);
        nameSpan.style.cssText = `
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
        `;

        // Create meta container for count and badge
        const metaSpan = document.createElement('span');
        metaSpan.className = 'lm-autocomplete-meta';
        metaSpan.style.cssText = `
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
        `;

        // Add post count
        if (itemData.post_count > 0) {
            const countSpan = document.createElement('span');
            countSpan.className = 'lm-autocomplete-count';
            countSpan.textContent = formatPostCount(itemData.post_count);
            countSpan.style.cssText = `
                font-size: 11px;
                color: rgba(226, 232, 240, 0.5);
            `;
            metaSpan.appendChild(countSpan);
        }

        // Add category badge
        const categoryInfo = CATEGORY_INFO[itemData.category];
        if (categoryInfo) {
            const badgeSpan = document.createElement('span');
            badgeSpan.className = 'lm-autocomplete-category';
            badgeSpan.textContent = categoryInfo.label;
            badgeSpan.style.cssText = `
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 10px;
                background: ${categoryInfo.bg};
                color: ${categoryInfo.text};
                white-space: nowrap;
            `;
            metaSpan.appendChild(badgeSpan);
        }

        itemEl.appendChild(nameSpan);
        itemEl.appendChild(metaSpan);
    }
    
    highlightMatch(text, searchTerm) {
        const { include } = parseSearchTokens(searchTerm);
        const sanitizedTokens = include
            .filter(Boolean)
            .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

        if (!sanitizedTokens.length) {
            return text;
        }

        const regex = new RegExp(`(${sanitizedTokens.join('|')})`, 'gi');
        return text.replace(
            regex,
            '<span style="background-color: rgba(66, 153, 225, 0.3); color: white; padding: 1px 2px; border-radius: 2px;">$1</span>',
        );
    }
    
    showPreviewForItem(relativePath, itemElement) {
        if (!this.options.showPreview || !this.previewTooltip) return;
        
        // Extract filename without extension for preview
        const fileName = relativePath.split(/[/\\]/).pop();
        const loraName = fileName.replace(/\.(safetensors|ckpt|pt|bin)$/i, '');
        
        // Get item position for tooltip positioning
        const rect = itemElement.getBoundingClientRect();
        const x = rect.right + 10;
        const y = rect.top;
        
        this.previewTooltip.show(loraName, x, y, true); // Pass true for fromAutocomplete flag
    }
    
    hidePreview() {
        if (!this.options.showPreview) {
            return;
        }
        if (typeof this.behavior.hidePreview === 'function') {
            this.behavior.hidePreview(this);
        } else if (this.previewTooltip) {
            this.previewTooltip.hide();
        }
    }
    
    show() {
        if (!this.items || this.items.length === 0) {
            this.hide();
            return;
        }
        
        // Position dropdown at cursor position using TextAreaCaretHelper
        this.positionAtCursor();
        this.dropdown.style.display = 'block';
        this.isVisible = true;
    }
    
    positionAtCursor() {
        const position = this.helper.getCursorOffset();
        this.dropdown.style.left = (position.left ?? 0) + "px";
        this.dropdown.style.top = (position.top ?? 0) + "px";
        this.dropdown.style.maxHeight = (window.innerHeight - position.top) + "px";
        
        // Adjust width to fit content
        // Temporarily show the dropdown to measure content width
        const originalDisplay = this.dropdown.style.display;
        this.dropdown.style.display = 'block';
        this.dropdown.style.visibility = 'hidden';
        
        // Measure the content width
        let maxWidth = 200; // minimum width
        const items = this.dropdown.querySelectorAll('.comfy-autocomplete-item');
        items.forEach(item => {
            const itemWidth = item.scrollWidth + 24; // Add padding
            maxWidth = Math.max(maxWidth, itemWidth);
        });
        
        // Set the width and restore visibility
        this.dropdown.style.width = Math.min(maxWidth, 400) + 'px'; // Cap at 400px
        this.dropdown.style.visibility = 'visible';
        this.dropdown.style.display = originalDisplay;
    }
    
    getCaretPosition() {
        return this.inputElement.selectionStart || 0;
    }
    
    hide() {
        if (!this.dropdown) {
            return;
        }

        this.dropdown.style.display = 'none';
        this.isVisible = false;
        this.selectedIndex = -1;
        this.showingCommands = false;

        // Hide preview tooltip
        this.hidePreview();

        // Clear selection styles from all items
        const items = this.dropdown.querySelectorAll('.comfy-autocomplete-item');
        items.forEach(item => {
            item.classList.remove('comfy-autocomplete-item-selected');
            item.style.backgroundColor = '';
        });
    }
    
    selectItem(index) {
        // Remove previous selection
        const prevSelected = this.dropdown.querySelector('.comfy-autocomplete-item-selected');
        if (prevSelected) {
            prevSelected.classList.remove('comfy-autocomplete-item-selected');
            prevSelected.style.backgroundColor = '';
        }
        
        // Add new selection
        if (index >= 0 && index < this.items.length) {
            this.selectedIndex = index;
            const item = this.dropdown.children[index];
            item.classList.add('comfy-autocomplete-item-selected');
            item.style.backgroundColor = 'rgba(66, 153, 225, 0.2)';
            
            // Scroll into view if needed
            item.scrollIntoView({ block: 'nearest' });
            
            // Show preview for selected item
            if (this.options.showPreview) {
                if (typeof this.behavior.showPreview === 'function') {
                    this.behavior.showPreview(this, this.items[index], item);
                } else if (this.previewTooltip) {
                    this.showPreviewForItem(this.items[index], item);
                }
            }
        }
    }
    
    handleKeyDown(e) {
        if (!this.isVisible) {
            return;
        }
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectItem(Math.min(this.selectedIndex + 1, this.items.length - 1));
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                this.selectItem(Math.max(this.selectedIndex - 1, 0));
                break;
                
            case 'Enter':
                e.preventDefault();
                if (this.selectedIndex >= 0 && this.selectedIndex < this.items.length) {
                    if (this.showingCommands) {
                        // Insert command
                        this._insertCommand(this.items[this.selectedIndex].command);
                    } else {
                        // Insert selection (handle enriched items)
                        const selectedItem = this.items[this.selectedIndex];
                        const insertPath = typeof selectedItem === 'object' && 'tag_name' in selectedItem
                            ? selectedItem.tag_name
                            : selectedItem;
                        this.insertSelection(insertPath);
                    }
                }
                break;
                
            case 'Escape':
                e.preventDefault();
                this.hide();
                break;
        }
    }
    
    async insertSelection(relativePath) {
        const insertText = await this.getInsertText(relativePath);
        if (!insertText) {
            this.hide();
            return;
        }

        const currentValue = this.inputElement.value;
        const caretPos = this.getCaretPosition();

        // Use getSearchTerm to get the current search term before cursor
        const beforeCursor = currentValue.substring(0, caretPos);
        const searchTerm = this.getSearchTerm(beforeCursor);
        const searchStartPos = caretPos - searchTerm.length;

        // Only replace the search term, not everything after the last comma
        const newValue = currentValue.substring(0, searchStartPos) + insertText + currentValue.substring(caretPos);
        const newCaretPos = searchStartPos + insertText.length;

        this.inputElement.value = newValue;

        // Trigger input event to notify about the change
        const event = new Event('input', { bubbles: true });
        this.inputElement.dispatchEvent(event);

        this.hide();

        // Focus back to input and position cursor
        this.inputElement.focus();
        this.inputElement.setSelectionRange(newCaretPos, newCaretPos);
    }

    async getInsertText(relativePath) {
        if (typeof this.behavior.getInsertText === 'function') {
            try {
                const result = await this.behavior.getInsertText(this, relativePath);
                if (typeof result === 'string' && result.length > 0) {
                    return result;
                }
            } catch (error) {
                console.warn('Failed to format autocomplete insertion:', error);
            }
        }

        const trimmed = typeof relativePath === 'string' ? relativePath.trim() : '';
        if (!trimmed) {
            return '';
        }
        return `${trimmed}, `;
    }

    /**
     * Check if the autocomplete instance is still valid
     * (input element exists and is in the DOM)
     * @returns {boolean}
     */
    isValid() {
        return this.inputElement && document.body.contains(this.inputElement);
    }

    /**
     * Refresh the TextAreaCaretHelper to update cached measurements
     * Useful after element is moved in DOM (e.g., Vue mode switch)
     */
    refreshCaretHelper() {
        if (this.inputElement && document.body.contains(this.inputElement)) {
            this.helper = new TextAreaCaretHelper(this.inputElement, () => app.canvas.ds.scale);
        }
    }

    destroy() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        if (this.onInput) {
            this.inputElement.removeEventListener('input', this.onInput);
            this.onInput = null;
        }

        if (this.onKeyDown) {
            this.inputElement.removeEventListener('keydown', this.onKeyDown);
            this.onKeyDown = null;
        }

        if (this.onBlur) {
            this.inputElement.removeEventListener('blur', this.onBlur);
            this.onBlur = null;
        }

        if (this.onDocumentClick) {
            document.removeEventListener('click', this.onDocumentClick);
            this.onDocumentClick = null;
        }

        if (typeof this.behavior.destroy === 'function') {
            this.behavior.destroy(this);
        } else if (this.previewTooltip) {
            this.previewTooltip.cleanup();
            this.previewTooltip = null;
        }
        this.previewTooltipPromise = null;
        
        if (this.dropdown && this.dropdown.parentNode) {
            this.dropdown.parentNode.removeChild(this.dropdown);
            this.dropdown = null;
        }
        
    }
}

export { AutoComplete };
