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
            modalOpen: false
        };
    }

    /**
     * Register an event handler with priority
     * @param {string} eventType - The DOM event type (e.g., 'click', 'mousedown')
     * @param {string} source - Source identifier (e.g., 'bulkManager', 'contextMenu')
     * @param {Function} handler - Event handler function
     * @param {Object} options - Additional options including priority (higher number = higher priority)
     */
    addHandler(eventType, source, handler, options = {}) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, []);
            // Set up the actual DOM listener once
            this.setupDOMListener(eventType);
        }
        
        const handlerList = this.handlers.get(eventType);
        handlerList.push({
            source,
            handler,
            priority: options.priority || 0,
            options
        });
        
        // Sort by priority
        handlerList.sort((a, b) => b.priority - a.priority);
    }

    /**
     * Remove an event handler
     */
    removeHandler(eventType, source) {
        if (!this.handlers.has(eventType)) return;
        
        const handlerList = this.handlers.get(eventType);
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
            
            // Execute handler
            const result = handler(event);
            
            // Stop propagation if handler returns true
            if (result === true) break;
        }
    }
    
    /**
     * Update application state
     */
    setState(state, value) {
        this.activeStates[state] = value;
    }
}

export const eventManager = new EventManager();