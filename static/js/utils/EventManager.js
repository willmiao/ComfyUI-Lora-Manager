/**
 * Centralized manager for handling DOM events across the application
 */
export class EventManager {
    constructor() {
        // Store registered handlers
        this.handlers = new Map();
        // Track active modals/states
        this.activeStates = {
            bulkMode: false,
            marqueeActive: false,
            modalOpen: false,
            nodeSelectorActive: false
        };
        // Store references to cleanup functions
        this.cleanupFunctions = new Map();
    }

    /**
     * Register an event handler with priority and conditional execution
     * @param {string} eventType - The DOM event type (e.g., 'click', 'mousedown')
     * @param {string} source - Source identifier (e.g., 'bulkManager', 'contextMenu')
     * @param {Function} handler - Event handler function
     * @param {Object} options - Additional options including priority and conditions
     */
    addHandler(eventType, source, handler, options = {}) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, []);
            // Set up the actual DOM listener once
            this.setupDOMListener(eventType);
        }
        
        const handlerList = this.handlers.get(eventType);
        const handlerEntry = {
            source,
            handler,
            priority: options.priority || 0,
            options,
            // Store cleanup function if provided
            cleanup: options.cleanup || null
        };
        
        handlerList.push(handlerEntry);
        
        // Sort by priority
        handlerList.sort((a, b) => b.priority - a.priority);
        
        return handlerEntry;
    }

    /**
     * Remove an event handler
     */
    removeHandler(eventType, source) {
        if (!this.handlers.has(eventType)) return;
        
        const handlerList = this.handlers.get(eventType);
        
        // Find and cleanup handler before removing
        const handlerToRemove = handlerList.find(h => h.source === source);
        if (handlerToRemove && handlerToRemove.cleanup) {
            try {
                handlerToRemove.cleanup();
            } catch (error) {
                console.warn(`Error during cleanup for ${source}:`, error);
            }
        }
        
        const newList = handlerList.filter(h => h.source !== source);
        
        if (newList.length === 0) {
            // Remove the DOM listener if no handlers remain
            this.cleanupDOMListener(eventType);
            this.handlers.delete(eventType);
        } else {
            this.handlers.set(eventType, newList);
        }
    }
    
    /**
     * Setup actual DOM event listener
     */
    setupDOMListener(eventType) {
        const listener = (event) => this.handleEvent(eventType, event);
        document.addEventListener(eventType, listener);
        this._domListeners = this._domListeners || {};
        this._domListeners[eventType] = listener;
    }
    
    /**
     * Clean up DOM event listener
     */
    cleanupDOMListener(eventType) {
        if (this._domListeners && this._domListeners[eventType]) {
            document.removeEventListener(eventType, this._domListeners[eventType]);
            delete this._domListeners[eventType];
        }
    }
    
    /**
     * Process an event through registered handlers
     */
    handleEvent(eventType, event) {
        if (!this.handlers.has(eventType)) return;
        
        const handlers = this.handlers.get(eventType);
        
        for (const {handler, options} of handlers) {
            // Apply conditional execution based on app state
            if (options.onlyInBulkMode && !this.activeStates.bulkMode) continue;
            if (options.onlyWhenMarqueeActive && !this.activeStates.marqueeActive) continue;
            if (options.skipWhenModalOpen && this.activeStates.modalOpen) continue;
            if (options.skipWhenNodeSelectorActive && this.activeStates.nodeSelectorActive) continue;
            if (options.onlyWhenNodeSelectorActive && !this.activeStates.nodeSelectorActive) continue;
            
            // Apply element-based filters
            if (options.targetSelector && !this._matchesSelector(event.target, options.targetSelector)) continue;
            if (options.excludeSelector && this._matchesSelector(event.target, options.excludeSelector)) continue;
            
            // Apply button filters
            if (options.button !== undefined && event.button !== options.button) continue;
            
            try {
                // Execute handler
                const result = handler(event);
                
                // Stop propagation if handler returns true
                if (result === true) break;
            } catch (error) {
                console.error(`Error in event handler for ${eventType}:`, error);
            }
        }
    }
    
    /**
     * Helper function to check if an element matches or is contained within an element matching the selector
     * This improves the robustness of the selector matching
     */
    _matchesSelector(element, selector) {
        if (element.matches && element.matches(selector)) {
            return true;
        }
        if (element.closest && element.closest(selector)) {
            return true;
        }
        return false;
    }
    
    /**
     * Update application state
     */
    setState(state, value) {
        if (this.activeStates.hasOwnProperty(state)) {
            this.activeStates[state] = value;
        } else {
            console.warn(`Unknown state: ${state}`);
        }
    }
    
    /**
     * Get current application state
     */
    getState(state) {
        return this.activeStates[state];
    }
    
    /**
     * Remove all handlers for a specific source
     */
    removeAllHandlersForSource(source) {
        const eventTypes = Array.from(this.handlers.keys());
        eventTypes.forEach(eventType => {
            this.removeHandler(eventType, source);
        });
    }
    
    /**
     * Clean up all event listeners (useful for app teardown)
     */
    cleanup() {
        const eventTypes = Array.from(this.handlers.keys());
        eventTypes.forEach(eventType => {
            const handlers = this.handlers.get(eventType);
            // Run cleanup functions
            handlers.forEach(h => {
                if (h.cleanup) {
                    try {
                        h.cleanup();
                    } catch (error) {
                        console.warn(`Error during cleanup for ${h.source}:`, error);
                    }
                }
            });
            this.cleanupDOMListener(eventType);
        });
        this.handlers.clear();
        this.cleanupFunctions.clear();
    }
}

export const eventManager = new EventManager();