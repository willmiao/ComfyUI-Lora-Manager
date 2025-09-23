/**
 * Event Management Initialization
 * 
 * This module handles the initialization and coordination of the centralized
 * event management system across the application.
 */

import { eventManager } from './EventManager.js';
import { modalManager } from '../managers/ModalManager.js';
import { state } from '../state/index.js';

/**
 * Initialize the centralized event management system
 */
export function initializeEventManagement() {
    console.log('Initializing centralized event management system...');
    
    // Initialize modal state tracking
    initializeModalStateTracking();
    
    // Set up global error handling for event handlers
    setupGlobalEventErrorHandling();
    
    // Set up cleanup on page unload
    setupPageUnloadCleanup();
    
    // Register global event handlers that need coordination
    registerContextMenuEvents();
    registerGlobalClickHandlers();
    
    console.log('Event management system initialized successfully');
}

/**
 * Initialize modal state tracking with the event manager
 */
function initializeModalStateTracking() {
    // Override modalManager methods to update event manager state
    const originalShowModal = modalManager.showModal.bind(modalManager);
    const originalCloseModal = modalManager.closeModal.bind(modalManager);
    const originalIsAnyModalOpen = modalManager.isAnyModalOpen.bind(modalManager);
    
    modalManager.showModal = function(...args) {
        const result = originalShowModal(...args);
        eventManager.setState('modalOpen', this.isAnyModalOpen());
        return result;
    };
    
    modalManager.closeModal = function(...args) {
        const result = originalCloseModal(...args);
        eventManager.setState('modalOpen', this.isAnyModalOpen());
        return result;
    };
}

/**
 * Set up global error handling for event handlers
 */
function setupGlobalEventErrorHandling() {
    // Override the handleEvent method to add better error handling
    const originalHandleEvent = eventManager.handleEvent.bind(eventManager);
    
    eventManager.handleEvent = function(eventType, event) {
        try {
            return originalHandleEvent(eventType, event);
        } catch (error) {
            console.error(`Critical error in event management for ${eventType}:`, error);
            // Don't let event handling errors crash the app
        }
    };
}

/**
 * Set up cleanup when the page is unloaded
 */
function setupPageUnloadCleanup() {
    window.addEventListener('beforeunload', () => {
        console.log('Cleaning up event management system...');
        eventManager.cleanup();
    });
}

/**
 * Register context menu related events with proper priority
 */
function registerContextMenuEvents() {
    eventManager.addHandler('contextmenu', 'contextMenu-coordination', (e) => {
        const card = e.target.closest('.model-card');
        const pageContent = e.target.closest('.page-content');

        if (!pageContent) {
            window.globalContextMenuInstance?.hideMenu();
            return false;
        }

        if (card) {
            e.preventDefault();

            // Hide all menus first
            window.pageContextMenu?.hideMenu();
            window.bulkManager?.bulkContextMenu?.hideMenu();
            window.globalContextMenuInstance?.hideMenu();

            // Determine which menu to show based on bulk mode and selection state
            if (state.bulkMode && card.classList.contains('selected')) {
                // Show bulk menu for selected cards in bulk mode
                window.bulkManager?.bulkContextMenu?.showMenu(e.clientX, e.clientY, card);
            } else if (!state.bulkMode) {
                // Show regular menu when not in bulk mode
                window.pageContextMenu?.showMenu(e.clientX, e.clientY, card);
            }
        } else {
            e.preventDefault();

            window.pageContextMenu?.hideMenu();
            window.bulkManager?.bulkContextMenu?.hideMenu();
            window.globalContextMenuInstance?.hideMenu();

            window.globalContextMenuInstance?.showMenu(e.clientX, e.clientY, null);
        }

        return true; // Stop propagation
    }, {
        priority: 200, // Higher priority than bulk manager events
        skipWhenModalOpen: true
    });
}

/**
 * Register global click handlers for context menu hiding
 */
function registerGlobalClickHandlers() {
    eventManager.addHandler('click', 'contextMenu-hide', (e) => {
        // Hide context menus when clicking elsewhere
        if (!e.target.closest('.context-menu')) {
            window.pageContextMenu?.hideMenu();
            window.bulkManager?.bulkContextMenu?.hideMenu();
            window.globalContextMenuInstance?.hideMenu();
        }
        return false; // Allow other handlers to process
    }, {
        priority: 50,
        skipWhenModalOpen: true
    });
}

/**
 * Register common application-wide event handlers
 */
export function registerGlobalEventHandlers() {
    // Escape key handler for closing modals/panels
    eventManager.addHandler('keydown', 'global-escape', (e) => {
        if (e.key === 'Escape') {
            // Check if any modal is open and close it
            if (eventManager.getState('modalOpen')) {
                modalManager.closeCurrentModal();
                return true; // Stop propagation
            }
            
            // Check if node selector is active and close it
            if (eventManager.getState('nodeSelectorActive')) {
                // The node selector should handle its own escape key
                return false; // Continue with other handlers
            }
        }
        return false; // Continue with other handlers
    }, {
        priority: 250 // Very high priority for escape handling
    });
    
    // Global focus management
    eventManager.addHandler('focusin', 'global-focus', (e) => {
        // Track focus for accessibility and keyboard navigation
        window.lastFocusedElement = e.target;
    }, {
        priority: 10 // Low priority for tracking
    });
    
    // Global click tracking for analytics (if needed)
    eventManager.addHandler('click', 'global-analytics', (e) => {
        // Track clicks for usage analytics
        // This runs last and doesn't interfere with other handlers
        trackUserInteraction(e);
    }, {
        priority: 1 // Lowest priority
    });
}

/**
 * Example analytics tracking function
 */
function trackUserInteraction(event) {
    // Implement analytics tracking here
    // This is just a placeholder
    if (window.analytics && typeof window.analytics.track === 'function') {
        const element = event.target;
        const elementInfo = {
            tag: element.tagName.toLowerCase(),
            class: element.className,
            id: element.id,
            text: element.textContent?.substring(0, 50)
        };
        
        window.analytics.track('ui_interaction', elementInfo);
    }
}

/**
 * Utility function to check if event management is properly initialized
 */
export function isEventManagementInitialized() {
    return eventManager && typeof eventManager.addHandler === 'function';
}

/**
 * Get event management statistics for debugging
 */
export function getEventManagementStats() {
    const stats = {
        totalEventTypes: eventManager.handlers.size,
        totalHandlers: 0,
        handlersBySource: {},
        currentStates: { ...eventManager.activeStates }
    };
    
    eventManager.handlers.forEach((handlers, eventType) => {
        stats.totalHandlers += handlers.length;
        handlers.forEach(handler => {
            if (!stats.handlersBySource[handler.source]) {
                stats.handlersBySource[handler.source] = 0;
            }
            stats.handlersBySource[handler.source]++;
        });
    });
    
    return stats;
}
