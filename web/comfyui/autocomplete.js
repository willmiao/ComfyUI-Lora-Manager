import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { TextAreaCaretHelper } from "./textarea_caret_helper.js";

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
    }
    
    handleInput(value = '') {
        // Clear previous debounce timer
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        // Get the search term (text after last comma)
        const searchTerm = this.getSearchTerm(value);
        
        if (searchTerm.length < this.options.minChars) {
            this.hide();
            return;
        }
        
        // Debounce the search
        this.debounceTimer = setTimeout(() => {
            this.search(searchTerm);
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
    
    async search(term = '') {
        try {
            this.currentSearchTerm = term;
            const response = await api.fetchApi(`/lm/${this.modelType}/relative-paths?search=${encodeURIComponent(term)}&limit=${this.options.maxItems}`);
            const data = await response.json();
            
            if (data.success && data.relative_paths && data.relative_paths.length > 0) {
                this.items = data.relative_paths;
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
    
    render() {
        this.dropdown.innerHTML = '';
        this.selectedIndex = -1;
        
        // Early return if no items to prevent empty dropdown
        if (!this.items || this.items.length === 0) {
            return;
        }
        
        this.items.forEach((relativePath, index) => {
            const item = document.createElement('div');
            item.className = 'comfy-autocomplete-item';
            
            // Create highlighted content
            const highlightedContent = this.highlightMatch(relativePath, this.currentSearchTerm);
            item.innerHTML = highlightedContent;
            
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
                this.insertSelection(relativePath);
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
            }, 100); // 50ms delay
        }
    }
    
    highlightMatch(text, searchTerm) {
        if (!searchTerm) return text;
        
        const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<span style="background-color: rgba(66, 153, 225, 0.3); color: white; padding: 1px 2px; border-radius: 2px;">$1</span>');
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
                    this.insertSelection(this.items[this.selectedIndex]);
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
