import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { TextAreaCaretHelper } from "./textarea_caret_helper.js";
import {
    getAutocompleteAppendCommaPreference,
    getAutocompleteAutoFormatPreference,
    getAutocompleteAcceptKeyPreference,
    getPromptTagAutocompletePreference,
    getTagSpaceReplacementPreference,
} from "./settings.js";
import { showToast } from "./utils.js";

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
    // Autocomplete toggle commands - only show one based on current state
    '/ac': {
        type: 'toggle_setting',
        settingId: 'loramanager.prompt_tag_autocomplete',
        value: true,
        label: 'Autocomplete: ON',
        condition: () => !getPromptTagAutocompletePreference()
    },
    '/noac': {
        type: 'toggle_setting',
        settingId: 'loramanager.prompt_tag_autocomplete',
        value: false,
        label: 'Autocomplete: OFF',
        condition: () => getPromptTagAutocompletePreference()
    },
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

function formatAutocompleteInsertion(text = '') {
    const trimmed = typeof text === 'string' ? text.trim() : '';
    if (!trimmed) {
        return '';
    }

    return getAutocompleteAppendCommaPreference() ? `${trimmed},` : `${trimmed} `;
}

function normalizeAutocompleteSegment(segment = '') {
    return segment.replace(/\s+/g, ' ').trim();
}

export function formatAutocompleteTextOnBlur(text = '') {
    if (typeof text !== 'string') {
        return '';
    }

    return text
        .split('\n')
        .map((line) => {
            if (!line.trim()) {
                return '';
            }

            const cleanedSegments = line
                .split(',')
                .map(normalizeAutocompleteSegment)
                .filter(Boolean);

            return cleanedSegments.join(', ');
        })
        .join('\n');
}

function shouldAcceptAutocompleteKey(key) {
    const mode = getAutocompleteAcceptKeyPreference();

    if (mode === 'tab_only') {
        return key === 'Tab';
    }

    if (mode === 'enter_only') {
        return key === 'Enter';
    }

    return key === 'Tab' || key === 'Enter';
}

function normalizeAutocompleteMatchText(text = '') {
    return text.toLowerCase().replace(/[-_\s']/g, '');
}

const AUTOCOMPLETE_METADATA_VERSION = 1;

function createAutocompleteMetadataBase(textWidgetName = 'text') {
    return {
        version: AUTOCOMPLETE_METADATA_VERSION,
        textWidgetName,
    };
}

function createDefaultBehavior(modelType) {
    return {
        enablePreview: false,
        async getInsertText(_instance, relativePath) {
            const trimmed = relativePath?.trim() ?? '';
            if (!trimmed) {
                return '';
            }
            return formatAutocompleteInsertion(trimmed);
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
                return formatAutocompleteInsertion(`<lora:${fileName}:${strength}:${clipStrength}>`);
            }
            return formatAutocompleteInsertion(`<lora:${fileName}:${strength}>`);
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
            const folder = directories.length ? `${directories.join('/')}/` : '';
            return formatAutocompleteInsertion(`embedding:${folder}${trimmedName}`);
        },
    },
    custom_words: {
        enablePreview: false,
        async getInsertText(_instance, relativePath) {
            return formatAutocompleteInsertion(relativePath);
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
        async getInsertText(instance, relativePath) {
            const rawSearchTerm = instance.getSearchTerm(instance.inputElement.value);
            const match = rawSearchTerm.match(/^emb:(.*)$/i);

            if (match || instance.searchType === 'embeddings') {
                const { directories, fileName } = splitRelativePath(relativePath);
                const trimmedName = removeGeneralExtension(fileName);
                const folder = directories.length ? `${directories.join('/')}/` : '';
                return formatAutocompleteInsertion(`embedding:${folder}${trimmedName}`);
            } else {
                let tagText = relativePath;

                if (getTagSpaceReplacementPreference()) {
                    tagText = tagText.replace(/_/g, ' ');
                }

                return formatAutocompleteInsertion(tagText);
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
            maxItems: 100,
            pageSize: 20,
            visibleItems: 15,  // Fixed at 15 items for balanced UX
            itemHeight: 40,
            minChars: 1,
            debounceDelay: 200,
            showPreview: this.behavior.enablePreview ?? false,
            enableVirtualScroll: true,
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

        // Virtual scrolling state
        this.virtualScrollOffset = 0;
        this.hasMoreItems = true;
        this.isLoadingMore = false;
        this.currentPage = 0;
        this.scrollContainer = null;
        this.contentContainer = null;
        this.totalHeight = 0;

        // Command mode state
        this.activeCommand = null;  // Current active command (e.g., { categories: [4, 11], label: 'Character' })
        this.showingCommands = false;  // Whether showing command list dropdown

        // Initialize TextAreaCaretHelper
        this.helper = new TextAreaCaretHelper(inputElement, () => app.canvas.ds.scale);

        this.onInput = null;
        this.onKeyDown = null;
        this.onBlur = null;
        this.onDocumentClick = null;
        this.onScroll = null;

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
            overflow: hidden;
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

        if (this.options.enableVirtualScroll) {
            // Create scroll container for virtual scrolling
            this.scrollContainer = document.createElement('div');
            this.scrollContainer.className = 'comfy-autocomplete-scroll-container';
            this.scrollContainer.style.cssText = `
                overflow-y: auto;
                max-height: ${this.options.visibleItems * this.options.itemHeight}px;
                position: relative;
            `;

            // Create content container for virtual items
            this.contentContainer = document.createElement('div');
            this.contentContainer.className = 'comfy-autocomplete-content';
            this.contentContainer.style.cssText = `
                position: relative;
                width: 100%;
            `;

            this.scrollContainer.appendChild(this.contentContainer);
            this.dropdown.appendChild(this.scrollContainer);
        }

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
            .comfy-autocomplete-scroll-container::-webkit-scrollbar {
                width: 8px;
            }
            .comfy-autocomplete-scroll-container::-webkit-scrollbar-track {
                background: rgba(40, 44, 52, 0.3);
                border-radius: 4px;
            }
            .comfy-autocomplete-scroll-container::-webkit-scrollbar-thumb {
                background: rgba(226, 232, 240, 0.2);
                border-radius: 4px;
            }
            .comfy-autocomplete-scroll-container::-webkit-scrollbar-thumb:hover {
                background: rgba(226, 232, 240, 0.4);
            }
            .comfy-autocomplete-loading {
                padding: 12px;
                text-align: center;
                color: rgba(226, 232, 240, 0.5);
                font-size: 12px;
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
            if (getAutocompleteAutoFormatPreference()) {
                const formattedValue = formatAutocompleteTextOnBlur(this.inputElement.value);
                if (formattedValue !== this.inputElement.value) {
                    this.inputElement.value = formattedValue;
                    this.inputElement.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }

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

        // Bind scroll event for virtual scrolling
        if (this.options.enableVirtualScroll && this.scrollContainer) {
            this.onScroll = () => {
                this.handleScroll();
            };
            this.scrollContainer.addEventListener('scroll', this.onScroll);
        }
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

        // For prompt model type, check if we're searching embeddings, commands, or tags
        if (this.modelType === 'prompt') {
            const match = rawSearchTerm.match(/^emb:(.*)$/i);
            if (match) {
                // User typed "emb:" prefix - always allow embeddings search
                endpoint = '/lm/embeddings/relative-paths';
                searchTerm = (match[1] || '').trim();
                this.searchType = 'embeddings';
                this.activeCommand = null;
                this.showingCommands = false;
            } else {
                // Check for command mode FIRST (always runs, regardless of setting)
                const commandResult = this._parseCommandInput(rawSearchTerm);

                if (commandResult.showCommands) {
                    // Show command list dropdown
                    this.showingCommands = true;
                    this.activeCommand = null;
                    this.searchType = 'commands';
                    this._showCommandList(commandResult.commandFilter);
                    return;
                } else if (commandResult.command?.type === 'toggle_setting') {
                    // Handle toggle setting command (/ac, /noac)
                    this._handleToggleSettingCommand(commandResult.command);
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
                } else if (getPromptTagAutocompletePreference()) {
                    // No command and setting enabled - regular tag search with enriched results
                    this.showingCommands = false;
                    this.activeCommand = null;
                    endpoint = '/lm/custom-words/search?enriched=true';
                    // Use full search term for query variation generation
                    // The search() method will generate multiple query variations including:
                    // - Original query (for natural language matching)
                    // - Underscore version (e.g., "looking_to_the_side" for "looking to the side")
                    // - Last token (for backward compatibility with continuous typing)
                    searchTerm = rawSearchTerm;
                    this.searchType = 'custom_words';
                } else {
                    // No command and setting disabled - no autocomplete for direct typing
                    this.hide();
                    return;
                }
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
        return this.getActiveSearchRange(value).text;
    }

    getActiveSearchRange(value = null) {
        const currentValue = typeof value === 'string' ? value : this.inputElement.value;
        const caretPos = this.getCaretPosition();
        const beforeCursor = this.helper.getBeforeCursor() ?? currentValue.substring(0, caretPos);
        let start = this._getHardBoundaryStart(beforeCursor);

        if (!getAutocompleteAppendCommaPreference()) {
            const persistedBoundaryEnd = this._getPersistedBoundaryEnd(currentValue, caretPos);
            if (persistedBoundaryEnd !== null && persistedBoundaryEnd > start) {
                start = persistedBoundaryEnd;
            }
        }

        const rawText = beforeCursor.substring(start);
        const text = rawText.trim();
        const leadingWhitespaceLength = rawText.length - rawText.trimStart().length;
        const trimmedStart = start + leadingWhitespaceLength;

        return {
            start,
            trimmedStart,
            end: caretPos,
            beforeCursor,
            rawText,
            text,
        };
    }

    _getHardBoundaryStart(beforeCursor = '') {
        const lastComma = beforeCursor.lastIndexOf(',');
        const lastAngle = beforeCursor.lastIndexOf('>');
        const lastNewline = Math.max(beforeCursor.lastIndexOf('\n'), beforeCursor.lastIndexOf('\r'));
        return Math.max(lastComma, lastAngle, lastNewline) + 1;
    }

    _getMetadataWidget() {
        return this.inputElement?._autocompleteMetadataWidget
            ?? this.inputElement?._autocompleteHostWidget?.metadataWidget
            ?? null;
    }

    _getMetadataBase() {
        return createAutocompleteMetadataBase(this.inputElement?._autocompleteTextWidgetName ?? 'text');
    }

    _getAutocompleteMetadata() {
        const metadataWidget = this._getMetadataWidget();
        const value = metadataWidget?.value;

        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            return this._getMetadataBase();
        }

        return {
            ...this._getMetadataBase(),
            ...value,
        };
    }

    _setAutocompleteMetadata(metadata = {}) {
        const metadataWidget = this._getMetadataWidget();
        if (!metadataWidget) {
            return;
        }

        metadataWidget.value = {
            ...this._getMetadataBase(),
            ...metadata,
        };
    }

    _clearLastAcceptedBoundary() {
        const metadataWidget = this._getMetadataWidget();
        if (!metadataWidget) {
            return;
        }

        const metadata = this._getAutocompleteMetadata();
        delete metadata.lastAccepted;
        metadataWidget.value = metadata;
    }

    _storeLastAcceptedBoundary(boundary) {
        this._setAutocompleteMetadata({ lastAccepted: boundary });
    }

    _getPersistedBoundaryEnd(currentValue, caretPos) {
        const metadata = this._getAutocompleteMetadata();
        const boundary = metadata?.lastAccepted;

        if (!boundary || typeof boundary !== 'object') {
            return null;
        }

        const { start, end, insertedText, textSnapshot } = boundary;

        if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
            this._clearLastAcceptedBoundary();
            return null;
        }

        if (end > currentValue.length || end > caretPos) {
            this._clearLastAcceptedBoundary();
            return null;
        }

        if (typeof insertedText !== 'string' || insertedText.length === 0) {
            this._clearLastAcceptedBoundary();
            return null;
        }

        if (currentValue.slice(start, end) !== insertedText) {
            this._clearLastAcceptedBoundary();
            return null;
        }

        if (typeof textSnapshot !== 'string' || currentValue.slice(0, end) !== textSnapshot) {
            this._clearLastAcceptedBoundary();
            return null;
        }

        return end;
    }

    /**
     * Extract the last space-separated token from a search term
     * Tag names don't contain spaces, so for tag autocomplete we only need the last token
     * @param {string} term - The full search term (e.g., "hello 1gi")
     * @returns {string} - The last token (e.g., "1gi"), or the original term if no spaces
     */
    _getLastSpaceToken(term) {
        const tokens = term.trim().split(/\s+/);
        return tokens[tokens.length - 1] || term;
    }

    /**
     * Generate query variations for better autocomplete matching
     * Includes original query and normalized versions (spaces to underscores, etc.)
     * @param {string} term - Original search term
     * @returns {string[]} - Array of query variations
     */
    _generateQueryVariations(term) {
        if (!term || term.length < this.options.minChars) {
            return [];
        }

        const variations = new Set();
        const trimmed = term.trim();

        // Always include original query
        variations.add(trimmed);
        variations.add(trimmed.toLowerCase());

        // Add underscore version (Danbooru convention: spaces become underscores)
        // e.g., "looking to the side" -> "looking_to_the_side"
        if (trimmed.includes(' ')) {
            const underscoreVersion = trimmed.replace(/ /g, '_');
            variations.add(underscoreVersion);
            variations.add(underscoreVersion.toLowerCase());
        }

        // Add no-space version for flexible matching
        // e.g., "blue hair" -> "bluehair"
        if (trimmed.includes(' ') || trimmed.includes('_')) {
            const noSpaceVersion = trimmed.replace(/[ _]/g, '');
            variations.add(noSpaceVersion);
            variations.add(noSpaceVersion.toLowerCase());
        }

        // Add last token only (legacy behavior for continuous typing)
        const lastToken = this._getLastSpaceToken(trimmed);
        if (lastToken !== trimmed) {
            variations.add(lastToken);
            variations.add(lastToken.toLowerCase());
        }

        return Array.from(variations).filter(v => v.length >= this.options.minChars);
    }

    /**
     * Get display text for an item (without extension for models)
     * @param {string|Object} item - Item to get display text from
     * @returns {string} - Display text without extension
     */
    _getDisplayText(item) {
        const itemText = typeof item === 'object' && item.tag_name ? item.tag_name : String(item);
        // Remove extension for models to avoid matching/displaying .safetensors etc.
        if (this.modelType === 'loras' || this.searchType === 'embeddings') {
            return removeLoraExtension(itemText);
        } else if (this.modelType === 'embeddings') {
            return removeGeneralExtension(itemText);
        }
        return itemText;
    }

    /**
     * Check if an item matches a search term
     * Supports both string items and enriched items with tag_name property
     * @param {string|Object} item - Item to check
     * @param {string} searchTerm - Search term to match against
     * @returns {Object} - { matched: boolean, isExactMatch: boolean }
     */
    _matchItem(item, searchTerm) {
        const itemText = this._getDisplayText(item);
        const itemTextLower = itemText.toLowerCase();
        const searchTermLower = searchTerm.toLowerCase();

        // Exact match (case-insensitive)
        if (itemTextLower === searchTermLower) {
            return { matched: true, isExactMatch: true };
        }

        // Partial match (contains)
        if (itemTextLower.includes(searchTermLower)) {
            return { matched: true, isExactMatch: false };
        }

        // Symbol-insensitive match: remove common separators and retry
        // e.g., "blue hair" can match "blue_hair" or "bluehair"
        const normalizedItem = itemTextLower.replace(/[-_\s']/g, '');
        const normalizedSearch = searchTermLower.replace(/[-_\s']/g, '');
        if (normalizedItem.includes(normalizedSearch)) {
            return { matched: true, isExactMatch: false };
        }

        return { matched: false, isExactMatch: false };
    }

    _getLiveSearchTermForAcceptance() {
        const rawSearchTerm = this.getSearchTerm(this.inputElement.value);

        if (this.modelType === 'embeddings') {
            const match = rawSearchTerm.match(/^emb:(.*)$/i);
            return (match?.[1] || '').trim();
        }

        if (this.modelType === 'prompt') {
            const embeddingMatch = rawSearchTerm.match(/^emb:(.*)$/i);
            if (embeddingMatch) {
                return (embeddingMatch[1] || '').trim();
            }

            const commandResult = this._parseCommandInput(rawSearchTerm);
            return commandResult.searchTerm ?? rawSearchTerm;
        }

        return rawSearchTerm;
    }

    _getPreferredSelectedIndex(searchTerm = '') {
        if (!this.items?.length) {
            return -1;
        }

        if (this.showingCommands) {
            if (this.selectedIndex >= 0 && this.selectedIndex < this.items.length) {
                return this.selectedIndex;
            }
            return 0;
        }

        const trimmedSearchTerm = searchTerm.trim();
        if (!trimmedSearchTerm) {
            if (this.selectedIndex >= 0 && this.selectedIndex < this.items.length) {
                return this.selectedIndex;
            }
            return 0;
        }

        const searchLower = trimmedSearchTerm.toLowerCase();
        const normalizedSearch = normalizeAutocompleteMatchText(trimmedSearchTerm);
        let bestIndex = -1;
        let bestScore = -Infinity;

        this.items.forEach((item, index) => {
            const displayText = this._getDisplayText(item);
            const textLower = displayText.toLowerCase();
            const normalizedText = normalizeAutocompleteMatchText(displayText);
            let score = -1;

            if (textLower === searchLower) {
                score = 5000;
            } else if (normalizedText === normalizedSearch) {
                score = 4500;
            } else if (textLower.startsWith(searchLower)) {
                score = 4000;
            } else if (normalizedText.startsWith(normalizedSearch)) {
                score = 3500;
            } else if (textLower.includes(searchLower)) {
                score = 3000;
            } else if (normalizedText.includes(normalizedSearch)) {
                score = 2500;
            }

            if (score > -1) {
                score -= index;
                if (score > bestScore) {
                    bestScore = score;
                    bestIndex = index;
                }
            }
        });

        if (bestIndex !== -1) {
            return bestIndex;
        }

        if (this.selectedIndex >= 0 && this.selectedIndex < this.items.length) {
            return this.selectedIndex;
        }

        return 0;
    }

    async search(term = '', endpoint = null) {
        try {
            this.currentSearchTerm = term;

            // Save current search type to detect mode changes during async search
            const searchTypeAtStart = this.searchType;

            // Clear items before starting new search to avoid stale data
            // This is critical for preventing command suggestions from persisting
            // when switching from command mode to regular tag search
            this.items = [];

            if (!endpoint) {
                endpoint = `/lm/${this.modelType}/relative-paths`;
            }

            // Generate multiple query variations for better matching
            const queryVariations = this._generateQueryVariations(term);

            if (queryVariations.length === 0) {
                this.items = [];
                this.hide();
                return;
            }

            // Limit the number of parallel queries to avoid overwhelming the server
            const queriesToExecute = queryVariations.slice(0, 4);

            // Execute all queries in parallel
            const searchPromises = queriesToExecute.map(async (query) => {
                const url = endpoint.includes('?')
                    ? `${endpoint}&search=${encodeURIComponent(query)}&limit=${this.options.maxItems}`
                    : `${endpoint}?search=${encodeURIComponent(query)}&limit=${this.options.maxItems}`;

                try {
                    const response = await api.fetchApi(url);
                    const data = await response.json();
                    return data.success ? (data.relative_paths || data.words || []) : [];
                } catch (error) {
                    console.warn(`Search query failed for "${query}":`, error);
                    return [];
                }
            });

            const resultsArrays = await Promise.all(searchPromises);

            // Check if search type changed during async operation
            // If so, skip updating items to prevent stale data from showing
            if (this.searchType !== searchTypeAtStart) {
                console.log('[Lora Manager] Search type changed during search, skipping update');
                return;
            }

            // Merge and deduplicate results while preserving order from backend
            // Backend returns results sorted by relevance, so we maintain that order
            const seen = new Set();
            const mergedItems = [];

            for (const resultArray of resultsArrays) {
                for (const item of resultArray) {
                    const itemKey = typeof item === 'object' && item.tag_name
                        ? item.tag_name.toLowerCase()
                        : String(item).toLowerCase();

                    if (!seen.has(itemKey)) {
                        seen.add(itemKey);
                        mergedItems.push(item);
                    }
                }
            }

            // Use backend-sorted results directly without re-scoring
            // Backend already ranks by: FTS5 bm25 score + post count + exact prefix boost
            if (mergedItems.length > 0) {
                this.items = mergedItems;
                this.render();
                this.show();
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
                const cmd = TAG_COMMANDS[partialCommand];
                // Filter out toggle commands that don't meet their condition
                if (cmd.type === 'toggle_setting' && cmd.condition && !cmd.condition()) {
                    return { showCommands: false, command: null, searchTerm: '' };
                }
                return {
                    showCommands: false,
                    command: cmd,
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
            const cmd = TAG_COMMANDS[commandPart];
            // Filter out toggle commands that don't meet their condition
            if (cmd.type === 'toggle_setting' && cmd.condition && !cmd.condition()) {
                return { showCommands: false, command: null, searchTerm: trimmed };
            }
            return {
                showCommands: false,
                command: cmd,
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
        // Only show command list if we're in command mode
        // This prevents stale command suggestions from appearing after switching to tag search
        if (this.searchType !== 'commands' && this.showingCommands !== true) {
            return;
        }
        
        const filterLower = filter.toLowerCase();

        // Get unique commands (avoid duplicates like /char and /character)
        const seenLabels = new Set();
        const commands = [];

        for (const [cmd, info] of Object.entries(TAG_COMMANDS)) {
            if (seenLabels.has(info.label)) continue;

            // Filter out toggle commands that don't meet their condition
            if (info.type === 'toggle_setting' && info.condition) {
                if (!info.condition()) continue;
            }

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
        // Clear command list items properly based on rendering mode
        if (this.contentContainer) {
            // Virtual scrolling mode - clear content container
            this.contentContainer.innerHTML = '';
        } else {
            // Non-virtual scrolling mode - clear dropdown direct children
            this.dropdown.innerHTML = '';
        }
        this.selectedIndex = -1;

        this.items.forEach((item, index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'comfy-autocomplete-item comfy-autocomplete-command';
            itemEl.dataset.index = index.toString();

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
                height: ${this.options.itemHeight}px;
                box-sizing: border-box;
            `;

            itemEl.addEventListener('mouseenter', () => {
                this.selectItem(index);
            });

            itemEl.addEventListener('click', () => {
                this._insertCommand(item.command);
            });

            // Append to correct container based on rendering mode
            if (this.contentContainer) {
                this.contentContainer.appendChild(itemEl);
            } else {
                this.dropdown.appendChild(itemEl);
            }
        });

        // Remove border from last item
        const lastChild = this.contentContainer ? this.contentContainer.lastChild : this.dropdown.lastChild;
        if (lastChild) {
            lastChild.style.borderBottom = 'none';
        }

        // Auto-select immediately so accept keys remain stable.
        if (this.items.length > 0) {
            this.selectItem(0);
        }
        
        // Update virtual scroll height for virtual scrolling mode
        if (this.contentContainer) {
            this.updateVirtualScrollHeight();
        }
    }

    /**
     * Insert a command into the input
     * @param {string} command - The command to insert (e.g., "/char")
     */
    _insertCommand(command) {
        const currentValue = this.inputElement.value;
        const activeRange = this.getActiveSearchRange(currentValue);
        const commandStartPos = activeRange.trimmedStart;

        // Insert command with trailing space
        const insertText = command + ' ';
        const newValue = currentValue.substring(0, commandStartPos) + insertText + currentValue.substring(activeRange.end);
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
        this.selectedIndex = -1;

        // Reset virtual scroll state
        this.virtualScrollOffset = 0;
        this.currentPage = 0;
        this.hasMoreItems = true;
        this.isLoadingMore = false;

        // Early return if no items to prevent empty dropdown
        if (!this.items || this.items.length === 0) {
            if (this.contentContainer) {
                this.contentContainer.innerHTML = '';
            } else {
                this.dropdown.innerHTML = '';
            }
            return;
        }

        if (this.options.enableVirtualScroll && this.contentContainer) {
            // Use virtual scrolling - always update visible items to ensure content is fresh
            // The dropdown visibility is controlled by show()/hide()
            this.updateVirtualScrollHeight();
            this.updateVisibleItems();
        } else {
            // Traditional rendering (fallback)
            this.dropdown.innerHTML = '';

            // Check if items are enriched (have tag_name, category, post_count) or command objects
            const isEnriched = this.items[0] && typeof this.items[0] === 'object' && 'tag_name' in this.items[0];
            const isCommand = this.items[0] && typeof this.items[0] === 'object' && 'command' in this.items[0];

            this.items.forEach((itemData, index) => {
                const item = document.createElement('div');
                item.className = 'comfy-autocomplete-item';

                if (isCommand) {
                    // Render command item
                    const cmdSpan = document.createElement('span');
                    cmdSpan.className = 'lm-autocomplete-command-name';
                    cmdSpan.textContent = itemData.command;

                    const labelSpan = document.createElement('span');
                    labelSpan.className = 'lm-autocomplete-command-label';
                    labelSpan.textContent = itemData.label;

                    item.appendChild(cmdSpan);
                    item.appendChild(labelSpan);
                    item.style.cssText = `
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
                } else if (isEnriched) {
                    // Render enriched item with category badge and post count
                    this._renderEnrichedItem(item, itemData, this.currentSearchTerm);
                } else {
                    // Create highlighted content for simple items, wrapped in a span
                    // to prevent flex layout from breaking up the text
                    const nameSpan = document.createElement('span');
                    nameSpan.className = 'lm-autocomplete-name';
                    // Use display text without extension for cleaner UI
                    const displayTextWithoutExt = this._getDisplayText(itemData);
                    nameSpan.innerHTML = this.highlightMatch(displayTextWithoutExt, this.currentSearchTerm);
                    nameSpan.style.cssText = `
                        flex: 1;
                        min-width: 0;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    `;
                    item.appendChild(nameSpan);
                    
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
                }

                // Hover and selection handlers
                item.addEventListener('mouseenter', () => {
                    this.selectItem(index);
                });

                item.addEventListener('mouseleave', () => {
                    this.hidePreview();
                });

                // Click handler
                item.addEventListener('click', () => {
                    if (isCommand) {
                        this._insertCommand(itemData.command);
                    } else {
                        const insertPath = isEnriched ? itemData.tag_name : itemData;
                        this.insertSelection(insertPath);
                    }
                });

                this.dropdown.appendChild(item);
            });

            // Remove border from last item
            if (this.dropdown.lastChild) {
                this.dropdown.lastChild.style.borderBottom = 'none';
            }
        }

        // Auto-select immediately so accept keys do not fall through
        // to native focus traversal while the dropdown is visible.
        if (this.items.length > 0) {
            this.selectItem(0);
        }
    }

    /**
     * Render an enriched autocomplete item with category badge and post count
     * @param {HTMLElement} itemEl - The item element to populate
     * @param {Object} itemData - The enriched item data { tag_name, category, post_count, matched_alias? }
     * @param {string} searchTerm - The current search term for highlighting
     */
    _renderEnrichedItem(itemEl, itemData, searchTerm) {
        // Create name span with highlighted match
        const nameSpan = document.createElement('span');
        nameSpan.className = 'lm-autocomplete-name';

        // If matched via alias, show: "tag_name ← alias" with alias highlighted
        if (itemData.matched_alias) {
            const tagText = document.createTextNode(itemData.tag_name + ' ');
            nameSpan.appendChild(tagText);

            const aliasSpan = document.createElement('span');
            aliasSpan.className = 'lm-matched-alias';
            aliasSpan.innerHTML = '← ' + this.highlightMatch(itemData.matched_alias, searchTerm);
            aliasSpan.style.cssText = `
                font-size: 11px;
                color: rgba(226, 232, 240, 0.5);
            `;
            nameSpan.appendChild(aliasSpan);
        } else {
            nameSpan.innerHTML = this.highlightMatch(itemData.tag_name, searchTerm);
        }

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
    
    /**
     * Handle scroll event for virtual scrolling and loading more items
     */
    handleScroll() {
        if (!this.scrollContainer || this.isLoadingMore) {
            return;
        }

        const { scrollTop, scrollHeight, clientHeight } = this.scrollContainer;
        const scrollBottom = scrollTop + clientHeight;
        const threshold = this.options.itemHeight * 2; // Load more when within 2 items of bottom

        // Check if we need to load more items
        if (scrollBottom >= scrollHeight - threshold && this.hasMoreItems) {
            this.loadMoreItems();
        }

        // Update visible items for virtual scrolling
        if (this.options.enableVirtualScroll) {
            this.updateVisibleItems();
        }
    }

    /**
     * Load more items (pagination)
     */
    async loadMoreItems() {
        if (this.isLoadingMore || !this.hasMoreItems || this.showingCommands) {
            return;
        }

        this.isLoadingMore = true;
        this.currentPage++;

        try {
            // Show loading indicator
            this.showLoadingIndicator();

            // Get the current endpoint
            let endpoint = `/lm/${this.modelType}/relative-paths`;
            if (this.modelType === 'prompt') {
                if (this.searchType === 'embeddings') {
                    endpoint = '/lm/embeddings/relative-paths';
                } else if (this.searchType === 'custom_words') {
                    if (this.activeCommand?.categories) {
                        const categories = this.activeCommand.categories.join(',');
                        endpoint = `/lm/custom-words/search?category=${categories}`;
                    } else {
                        endpoint = '/lm/custom-words/search?enriched=true';
                    }
                }
            }

            const queryVariations = this._generateQueryVariations(this.currentSearchTerm);
            const queriesToExecute = queryVariations.slice(0, 4);
            const offset = this.items.length;

            // Execute all queries in parallel with offset
            const searchPromises = queriesToExecute.map(async (query) => {
                const url = endpoint.includes('?')
                    ? `${endpoint}&search=${encodeURIComponent(query)}&limit=${this.options.pageSize}&offset=${offset}`
                    : `${endpoint}?search=${encodeURIComponent(query)}&limit=${this.options.pageSize}&offset=${offset}`;

                try {
                    const response = await api.fetchApi(url);
                    const data = await response.json();
                    return data.success ? (data.relative_paths || data.words || []) : [];
                } catch (error) {
                    console.warn(`Search query failed for "${query}":`, error);
                    return [];
                }
            });

            const resultsArrays = await Promise.all(searchPromises);

            // Merge and deduplicate results with existing items
            const seen = new Set(this.items.map(item => {
                const itemKey = typeof item === 'object' && item.tag_name
                    ? item.tag_name.toLowerCase()
                    : String(item).toLowerCase();
                return itemKey;
            }));
            const newItems = [];

            for (const resultArray of resultsArrays) {
                for (const item of resultArray) {
                    const itemKey = typeof item === 'object' && item.tag_name
                        ? item.tag_name.toLowerCase()
                        : String(item).toLowerCase();

                    if (!seen.has(itemKey)) {
                        seen.add(itemKey);
                        newItems.push(item);
                    }
                }
            }

            // If we got fewer items than requested, we've reached the end
            if (newItems.length < this.options.pageSize) {
                this.hasMoreItems = false;
            }

            // If we got new items, append them and re-render
            // IMPORTANT: Do NOT re-sort! Backend already returns results sorted by relevance
            if (newItems.length > 0) {
                this.items.push(...newItems);

                // Update render
                if (this.options.enableVirtualScroll) {
                    this.updateVirtualScrollHeight();
                    this.updateVisibleItems();
                } else {
                    this.render();
                }
            } else {
                this.hasMoreItems = false;
            }
        } catch (error) {
            console.error('Error loading more items:', error);
            this.hasMoreItems = false;
        } finally {
            this.isLoadingMore = false;
            this.hideLoadingIndicator();
        }
    }

    /**
     * Show loading indicator at the bottom of the list
     */
    showLoadingIndicator() {
        if (!this.contentContainer) return;

        let loadingEl = this.contentContainer.querySelector('.comfy-autocomplete-loading');
        if (!loadingEl) {
            loadingEl = document.createElement('div');
            loadingEl.className = 'comfy-autocomplete-loading';
            loadingEl.textContent = 'Loading more...';
            loadingEl.style.cssText = `
                padding: 12px;
                text-align: center;
                color: rgba(226, 232, 240, 0.5);
                font-size: 12px;
            `;
            this.contentContainer.appendChild(loadingEl);
        }
    }

    /**
     * Hide loading indicator
     */
    hideLoadingIndicator() {
        if (!this.contentContainer) return;

        const loadingEl = this.contentContainer.querySelector('.comfy-autocomplete-loading');
        if (loadingEl) {
            loadingEl.remove();
        }
    }

    /**
     * Update the total height of the virtual scroll container
     */
    updateVirtualScrollHeight() {
        if (!this.contentContainer || !this.scrollContainer) return;

        this.totalHeight = this.items.length * this.options.itemHeight;
        this.contentContainer.style.height = `${this.totalHeight}px`;
        
        // Adjust scroll container max-height based on actual content
        // Only show scrollbar when content exceeds visibleItems limit
        const maxHeight = this.options.visibleItems * this.options.itemHeight;
        const shouldShowScrollbar = this.totalHeight > maxHeight;
        
        this.scrollContainer.style.maxHeight = shouldShowScrollbar ? `${maxHeight}px` : `${this.totalHeight}px`;
        this.scrollContainer.style.overflowY = shouldShowScrollbar ? 'auto' : 'hidden';
    }

    /**
     * Update which items are visible based on scroll position
     */
    updateVisibleItems() {
        if (!this.scrollContainer || !this.contentContainer) return;

        const scrollTop = this.scrollContainer.scrollTop;
        const containerHeight = this.scrollContainer.clientHeight;

        // Calculate which items should be visible with a larger buffer for smoother rendering
        // Use a fixed buffer of 5 items to ensure selected item is always rendered
        const startIndex = Math.max(0, Math.floor(scrollTop / this.options.itemHeight) - 5);
        const endIndex = Math.min(
            this.items.length - 1,
            Math.ceil((scrollTop + containerHeight) / this.options.itemHeight) + 5
        );

        // Clear current content
        this.contentContainer.innerHTML = '';

        // Create spacer for items before visible range
        if (startIndex > 0) {
            const topSpacer = document.createElement('div');
            topSpacer.style.height = `${startIndex * this.options.itemHeight}px`;
            this.contentContainer.appendChild(topSpacer);
        }

        // Render visible items
        const isEnriched = this.items[0] && typeof this.items[0] === 'object' && 'tag_name' in this.items[0];
        const isCommand = this.items[0] && typeof this.items[0] === 'object' && 'command' in this.items[0];

        for (let i = startIndex; i <= endIndex; i++) {
            const itemData = this.items[i];
            const itemEl = this.createItemElement(itemData, i, isEnriched, isCommand);
            this.contentContainer.appendChild(itemEl);
        }

        // Create spacer for items after visible range
        if (endIndex < this.items.length - 1) {
            const bottomSpacer = document.createElement('div');
            bottomSpacer.style.height = `${(this.items.length - 1 - endIndex) * this.options.itemHeight}px`;
            this.contentContainer.appendChild(bottomSpacer);
        }
        
        // Re-apply selection styling after re-rendering
        // This ensures the selected item remains highlighted even after DOM updates
        if (this.selectedIndex >= startIndex && this.selectedIndex <= endIndex) {
            const selectedEl = this.contentContainer.querySelector(`.comfy-autocomplete-item[data-index="${this.selectedIndex}"]`);
            if (selectedEl) {
                selectedEl.classList.add('comfy-autocomplete-item-selected');
                selectedEl.style.backgroundColor = 'rgba(66, 153, 225, 0.2)';
            }
        }
    }

    /**
     * Create a single item element
     */
    createItemElement(itemData, index, isEnriched, isCommand = false) {
        const item = document.createElement('div');
        item.className = 'comfy-autocomplete-item';
        item.dataset.index = index.toString();
        item.style.cssText = `
            height: ${this.options.itemHeight}px;
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
            box-sizing: border-box;
        `;

        // Check if this is a command object (override parameter if needed)
        if (!isCommand && itemData && typeof itemData === 'object' && 'command' in itemData) {
            isCommand = true;
        }

        if (isCommand) {
            // Render command item
            const cmdSpan = document.createElement('span');
            cmdSpan.className = 'lm-autocomplete-command-name';
            cmdSpan.textContent = itemData.command;

            const labelSpan = document.createElement('span');
            labelSpan.className = 'lm-autocomplete-command-label';
            labelSpan.textContent = itemData.label;

            item.appendChild(cmdSpan);
            item.appendChild(labelSpan);
            item.style.gap = '12px';
        } else if (isEnriched) {
            this._renderEnrichedItem(item, itemData, this.currentSearchTerm);
        } else {
            const nameSpan = document.createElement('span');
            nameSpan.className = 'lm-autocomplete-name';
            // Use display text without extension for cleaner UI
            const displayTextWithoutExt = this._getDisplayText(itemData);
            nameSpan.innerHTML = this.highlightMatch(displayTextWithoutExt, this.currentSearchTerm);
            nameSpan.style.cssText = `
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
            `;
            item.appendChild(nameSpan);
        }

        // Hover and selection handlers
        item.addEventListener('mouseenter', () => {
            this.selectItem(index);
        });

        item.addEventListener('mouseleave', () => {
            this.hidePreview();
        });

        // Click handler
        item.addEventListener('click', () => {
            if (isCommand) {
                this._insertCommand(itemData.command);
            } else {
                const insertPath = isEnriched ? itemData.tag_name : itemData;
                this.insertSelection(insertPath);
            }
        });

        return item;
    }

    show() {
        if (!this.items || this.items.length === 0) {
            this.hide();
            return;
        }

        // For virtual scrolling, render items first so positionAtCursor can measure width correctly
        if (this.options.enableVirtualScroll && this.contentContainer) {
            this.dropdown.style.display = 'block';
            this.isVisible = true;
            // Skip updateVisibleItems if showing commands (already rendered by _renderCommandList)
            if (!this.showingCommands) {
                this.updateVisibleItems();
            }
            this.positionAtCursor();
        } else {
            // Position dropdown at cursor position using TextAreaCaretHelper
            this.positionAtCursor();
            this.dropdown.style.display = 'block';
            this.isVisible = true;
        }
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

        // Temporarily remove width constraints to allow content to expand naturally
        // This prevents items.scrollWidth from being limited by a narrow container
        const originalWidth = this.dropdown.style.width;
        this.dropdown.style.width = 'auto';
        this.dropdown.style.minWidth = '200px';

        // Measure the content width
        let maxWidth = 200; // minimum width
        // For virtual scrolling, query items from contentContainer; otherwise from dropdown
        const container = this.options.enableVirtualScroll && this.contentContainer
            ? this.contentContainer
            : this.dropdown;
        const items = container.querySelectorAll('.comfy-autocomplete-item');
        items.forEach(item => {
            const itemWidth = item.scrollWidth + 24; // Add padding
            maxWidth = Math.max(maxWidth, itemWidth);
        });

        // Set the width and restore visibility
        this.dropdown.style.width = Math.min(maxWidth, 400) + 'px'; // Cap at 400px
        this.dropdown.style.minWidth = '';
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
        
        // Clear items to prevent stale data from being displayed
        // when autocomplete is shown again
        this.items = [];
        
        // Clear content container to prevent stale items from showing
        if (this.contentContainer) {
            // Virtual scrolling mode - clear content container
            this.contentContainer.innerHTML = '';
        } else {
            // Non-virtual scrolling mode - clear dropdown direct children
            this.dropdown.innerHTML = '';
        }

        // Reset virtual scrolling state
        this.virtualScrollOffset = 0;
        this.currentPage = 0;
        this.hasMoreItems = true;
        this.isLoadingMore = false;
        this.totalHeight = 0;

        // Reset scroll position
        if (this.scrollContainer) {
            this.scrollContainer.scrollTop = 0;
        }

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
        const container = this.options.enableVirtualScroll && this.contentContainer
            ? this.contentContainer
            : this.dropdown;
        const prevSelected = container.querySelector('.comfy-autocomplete-item-selected');
        if (prevSelected) {
            prevSelected.classList.remove('comfy-autocomplete-item-selected');
            prevSelected.style.backgroundColor = '';
        }

        // Add new selection
        if (index >= 0 && index < this.items.length) {
            this.selectedIndex = index;

            // For virtual scrolling, we need to ensure the item is rendered
            if (this.options.enableVirtualScroll && this.scrollContainer) {
                // Calculate if the item is currently visible
                const itemTop = index * this.options.itemHeight;
                const itemBottom = itemTop + this.options.itemHeight;
                const scrollTop = this.scrollContainer.scrollTop;
                const containerHeight = this.scrollContainer.clientHeight;
                const scrollBottom = scrollTop + containerHeight;

                // If item is not visible, scroll to make it visible
                if (itemTop < scrollTop || itemBottom > scrollBottom) {
                    // Scroll to position the item in the visible area
                    // Position item at 1/3 from top for better visibility
                    const targetScrollTop = Math.max(0, itemTop - containerHeight / 3);
                    this.scrollContainer.scrollTop = targetScrollTop;
                    
                    // Re-render visible items after scroll
                    this.updateVisibleItems();
                    
                    // Apply selection after DOM is updated
                    // Use setTimeout to ensure DOM has been re-rendered
                    setTimeout(() => {
                        this._applyItemSelection(index);
                    }, 0);
                } else {
                    // Item is already visible, apply selection immediately
                    this._applyItemSelection(index);
                }
            } else {
                // Traditional rendering
                const item = container.children[index];
                if (item) {
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
        }
    }

    /**
     * Apply selection styling to an item (used after virtual scroll re-render)
     * @param {number} index - Index of item to select
     */
    _applyItemSelection(index) {
        if (!this.contentContainer) return;

        // Find the item element using data-index attribute
        const selectedEl = this.contentContainer.querySelector(`.comfy-autocomplete-item[data-index="${index}"]`);

        if (selectedEl) {
            selectedEl.classList.add('comfy-autocomplete-item-selected');
            selectedEl.style.backgroundColor = 'rgba(66, 153, 225, 0.2)';

            // Show preview for selected item
            if (this.options.showPreview) {
                if (typeof this.behavior.showPreview === 'function') {
                    this.behavior.showPreview(this, this.items[index], selectedEl);
                } else if (this.previewTooltip) {
                    this.showPreviewForItem(this.items[index], selectedEl);
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
                if (this.options.enableVirtualScroll && this.scrollContainer) {
                    // For virtual scrolling, handle boundary cases
                    if (this.selectedIndex >= this.items.length - 1) {
                        // Already at last item, try to load more
                        if (this.hasMoreItems && !this.isLoadingMore) {
                            this.loadMoreItems().then(() => {
                                // After loading more, select the next item
                                if (this.selectedIndex < this.items.length - 1) {
                                    this.selectItem(this.selectedIndex + 1);
                                }
                            });
                        }
                    } else {
                        this.selectItem(this.selectedIndex + 1);
                    }
                } else {
                    this.selectItem(Math.min(this.selectedIndex + 1, this.items.length - 1));
                }
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (this.options.enableVirtualScroll && this.scrollContainer) {
                    // For virtual scrolling, handle top boundary
                    if (this.selectedIndex <= 0) {
                        // Already at first item, ensure it's selected
                        this.selectItem(0);
                    } else {
                        this.selectItem(this.selectedIndex - 1);
                    }
                } else {
                    this.selectItem(Math.max(this.selectedIndex - 1, 0));
                }
                break;
                
            case 'Enter':
            case 'Tab':
                if (!shouldAcceptAutocompleteKey(e.key)) {
                    break;
                }

                {
                    const liveSearchTerm = this._getLiveSearchTermForAcceptance();
                    const preferredIndex = this._getPreferredSelectedIndex(liveSearchTerm);
                    if (preferredIndex !== -1 && preferredIndex !== this.selectedIndex) {
                        this.selectItem(preferredIndex);
                    }
                }

                if (this.selectedIndex >= 0 && this.selectedIndex < this.items.length) {
                    e.preventDefault();
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
        const activeRange = this.getActiveSearchRange(currentValue);
        const caretPos = activeRange.end;
        const fullSearchTerm = activeRange.text;
        let replaceStartPos = activeRange.trimmedStart;

        // For regular tag autocomplete (no command), only replace the last space-separated token
        // This allows "hello 1gi" + selecting "1girl" to become "hello 1girl, "
        // However, if the user typed a multi-word phrase that matches a tag (e.g., "looking to the side"
        // matching "looking_to_the_side"), replace the entire phrase instead of just the last word.
        // Command mode (e.g., "/char miku") should replace the entire command+search
        let searchTerm = fullSearchTerm;
        if (this.modelType === 'prompt' && this.searchType === 'custom_words' && !this.activeCommand) {
            // Check if the selectedItem exists and its tag_name matches the full search term
            // when converted to underscore format (Danbooru convention)
            const selectedItem = this.selectedIndex >= 0 ? this.items[this.selectedIndex] : null;
            const selectedTagName = selectedItem && typeof selectedItem === 'object' && 'tag_name' 
                ? selectedItem.tag_name 
                : null;
            
            // Convert full search term to underscore format and check if it matches selected tag
            // Normalize multiple spaces to single underscore for matching (e.g., "looking  to   the side" -> "looking_to_the_side")
            const underscoreVersion = fullSearchTerm.replace(/ +/g, '_').toLowerCase();
            const selectedTagLower = selectedTagName?.toLowerCase() ?? '';
            
            // If multi-word search term is a prefix or suffix of the selected tag,
            // replace the entire phrase. This handles cases where user types partial tag name.
            // Examples:
            // - "looking to the" -> "looking_to_the_side" (prefix match)
            // - "to the side" -> "looking_to_the_side" (suffix match)
            // - "looking to the side" -> "looking_to_the_side" (exact match)
            if (fullSearchTerm.includes(' ') && (
                selectedTagLower.startsWith(underscoreVersion) ||
                selectedTagLower.endsWith(underscoreVersion) ||
                underscoreVersion === selectedTagLower
            )) {
                searchTerm = fullSearchTerm;
                replaceStartPos = activeRange.trimmedStart;
            } else {
                searchTerm = this._getLastSpaceToken(fullSearchTerm);
                replaceStartPos = searchTerm === fullSearchTerm
                    ? activeRange.trimmedStart
                    : caretPos - searchTerm.length;
            }
        }

        // Only replace the search term, not everything after the last comma
        const newValue = currentValue.substring(0, replaceStartPos) + insertText + currentValue.substring(caretPos);
        const newCaretPos = replaceStartPos + insertText.length;

        this.inputElement.value = newValue;
        this._storeLastAcceptedBoundary({
            start: replaceStartPos,
            end: newCaretPos,
            insertedText: insertText,
            textSnapshot: newValue.substring(0, newCaretPos),
        });

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
        return formatAutocompleteInsertion(trimmed);
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

    /**
     * Handle toggle setting command (/ac, /noac)
     * @param {Object} command - The toggle command with settingId and value
     */
    async _handleToggleSettingCommand(command) {
        const { settingId, value } = command;

        try {
            // Use ComfyUI's setting API to update global setting
            const settingManager = app?.extensionManager?.setting;
            if (settingManager && typeof settingManager.set === 'function') {
                await settingManager.set(settingId, value);
                this._showToggleFeedback(value);
                this._clearCurrentToken();
            } else {
                // Fallback: use legacy settings API
                const setting = app.ui.settings.settingsById?.[settingId];
                if (setting) {
                    app.ui.settings.setSettingValue(settingId, value);
                    this._showToggleFeedback(value);
                    this._clearCurrentToken();
                }
            }
        } catch (error) {
            console.error('[Lora Manager] Failed to toggle setting:', error);
            showToast({
                severity: 'error',
                summary: 'Error',
                detail: 'Failed to toggle autocomplete setting',
                life: 3000
            });
        }

        this.hide();
    }

    /**
     * Show visual feedback for toggle action using toast
     * @param {boolean} enabled - New autocomplete state
     */
    _showToggleFeedback(enabled) {
        showToast({
            severity: enabled ? 'success' : 'secondary',
            summary: enabled ? 'Autocomplete Enabled' : 'Autocomplete Disabled',
            detail: enabled 
                ? 'Tag autocomplete is now ON. Type to see suggestions.' 
                : 'Tag autocomplete is now OFF. Use /ac to re-enable.',
            life: 3000
        });
    }

    /**
     * Clear the current command token from input
     * Preserves leading spaces after delimiters (e.g., "1girl, /ac" -> "1girl, ")
     */
    _clearCurrentToken() {
        const currentValue = this.inputElement.value;
        const activeRange = this.getActiveSearchRange(currentValue);
        const caretPos = activeRange.end;
        const lastSegment = activeRange.rawText;
        
        // Find the command start position, preserving leading spaces
        // lastSegment includes leading spaces (e.g., " /ac"), find where command actually starts
        const commandMatch = lastSegment.match(/^(\s*)(\/\w+)/);
        if (commandMatch) {
            // commandMatch[1] is leading spaces, commandMatch[2] is the command
            const leadingSpaces = commandMatch[1].length;
            // Keep the spaces by starting after them
            const commandStartPos = activeRange.start + leadingSpaces;
            
            // Skip trailing spaces when deleting
            let endPos = caretPos;
            while (endPos < currentValue.length && currentValue[endPos] === ' ') {
                endPos++;
            }

            const newValue = currentValue.substring(0, commandStartPos) + currentValue.substring(endPos);
            const newCaretPos = commandStartPos;

            this.inputElement.value = newValue;

            // Trigger input event to notify about the change
            const event = new Event('input', { bubbles: true });
            this.inputElement.dispatchEvent(event);

            // Focus back to input and position cursor
            this.inputElement.focus();
            this.inputElement.setSelectionRange(newCaretPos, newCaretPos);
        } else {
            // Fallback: delete the whole last segment (original behavior)
            const commandStartPos = activeRange.start;
            
            let endPos = caretPos;
            while (endPos < currentValue.length && currentValue[endPos] === ' ') {
                endPos++;
            }

            const newValue = currentValue.substring(0, commandStartPos) + currentValue.substring(endPos);
            const newCaretPos = commandStartPos;

            this.inputElement.value = newValue;

            const event = new Event('input', { bubbles: true });
            this.inputElement.dispatchEvent(event);

            this.inputElement.focus();
            this.inputElement.setSelectionRange(newCaretPos, newCaretPos);
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

        if (this.onScroll && this.scrollContainer) {
            this.scrollContainer.removeEventListener('scroll', this.onScroll);
            this.onScroll = null;
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
