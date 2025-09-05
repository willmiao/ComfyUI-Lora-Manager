# Centralized Event Management System

This document describes the centralized event management system that coordinates event handling across the ComfyUI LoRA Manager application.

## Overview

The `EventManager` class provides a centralized way to handle DOM events with priority-based execution, conditional execution based on application state, and proper cleanup mechanisms.

## Features

- **Priority-based execution**: Handlers with higher priority run first
- **Conditional execution**: Handlers can be executed based on application state
- **Element filtering**: Handlers can target specific elements or exclude others
- **Automatic cleanup**: Cleanup functions are called when handlers are removed
- **State tracking**: Tracks application states like bulk mode, modal open, etc.

## Basic Usage

### Importing

```javascript
import { eventManager } from './EventManager.js';
```

### Adding Event Handlers

```javascript
eventManager.addHandler('click', 'myComponent', (event) => {
    console.log('Button clicked!');
    return true; // Stop propagation to other handlers
}, {
    priority: 100,
    targetSelector: '.my-button',
    skipWhenModalOpen: true
});
```

### Removing Event Handlers

```javascript
// Remove specific handler
eventManager.removeHandler('click', 'myComponent');

// Remove all handlers for a component
eventManager.removeAllHandlersForSource('myComponent');
```

### Updating Application State

```javascript
// Set state
eventManager.setState('bulkMode', true);
eventManager.setState('modalOpen', true);

// Get state
const isBulkMode = eventManager.getState('bulkMode');
```

## Available States

- `bulkMode`: Whether bulk selection mode is active
- `marqueeActive`: Whether marquee selection is in progress
- `modalOpen`: Whether any modal is currently open
- `nodeSelectorActive`: Whether the node selector popup is active

## Handler Options

### Priority
Higher numbers = higher priority. Handlers run in descending priority order.

```javascript
{
    priority: 100 // High priority
}
```

### Conditional Execution

```javascript
{
    onlyInBulkMode: true,               // Only run when bulk mode is active
    onlyWhenMarqueeActive: true,        // Only run when marquee selection is active
    skipWhenModalOpen: true,            // Skip when any modal is open
    skipWhenNodeSelectorActive: true,   // Skip when node selector is active
    onlyWhenNodeSelectorActive: true    // Only run when node selector is active
}
```

### Element Filtering

```javascript
{
    targetSelector: '.model-card',      // Only handle events on matching elements
    excludeSelector: 'button, input',  // Exclude events from these elements
    button: 0                          // Only handle specific mouse button (0=left, 1=middle, 2=right)
}
```

### Cleanup Functions

```javascript
{
    cleanup: () => {
        // Custom cleanup logic
        console.log('Handler cleaned up');
    }
}
```

## Integration Examples

### BulkManager Integration

```javascript
class BulkManager {
    registerEventHandlers() {
        // High priority keyboard shortcuts
        eventManager.addHandler('keydown', 'bulkManager-keyboard', (e) => {
            return this.handleGlobalKeyboard(e);
        }, {
            priority: 100,
            skipWhenModalOpen: true
        });

        // Marquee selection
        eventManager.addHandler('mousedown', 'bulkManager-marquee-start', (e) => {
            return this.handleMarqueeStart(e);
        }, {
            priority: 80,
            skipWhenModalOpen: true,
            targetSelector: '.models-container',
            excludeSelector: '.model-card, button, input',
            button: 0
        });
    }
    
    cleanup() {
        eventManager.removeAllHandlersForSource('bulkManager-keyboard');
        eventManager.removeAllHandlersForSource('bulkManager-marquee-start');
    }
}
```

### Modal Integration

```javascript
class ModalManager {
    showModal(modalId) {
        // Update state when modal opens
        eventManager.setState('modalOpen', true);
        this.displayModal(modalId);
    }
    
    closeModal(modalId) {
        // Update state when modal closes
        eventManager.setState('modalOpen', false);
        this.hideModal(modalId);
    }
}
```

### Component Event Delegation

```javascript
export function setupComponentEvents() {
    eventManager.addHandler('click', 'myComponent-actions', (event) => {
        const button = event.target.closest('.action-button');
        if (!button) return false;
        
        this.handleAction(button.dataset.action);
        return true; // Stop propagation
    }, {
        priority: 60,
        targetSelector: '.component-container'
    });
}
```

## Best Practices

### 1. Use Descriptive Source Names
Use the format `componentName-purposeDescription`:
```javascript
// Good
'bulkManager-marqueeSelection'
'nodeSelector-clickOutside'
'modelCard-delegation'

// Avoid
'bulk'
'click'
'handler1'
```

### 2. Set Appropriate Priorities
- 200+: Critical system events (escape keys, critical modals)
- 100-199: High priority application events (keyboard shortcuts)
- 50-99: Normal UI interactions (buttons, cards)
- 1-49: Low priority events (tracking, analytics)

### 3. Use Conditional Execution
Instead of checking state inside handlers, use options:
```javascript
// Good
eventManager.addHandler('click', 'bulk-action', handler, {
    onlyInBulkMode: true
});

// Avoid
eventManager.addHandler('click', 'bulk-action', (e) => {
    if (!state.bulkMode) return;
    // handler logic
});
```

### 4. Clean Up Properly
Always clean up handlers when components are destroyed:
```javascript
class MyComponent {
    constructor() {
        this.registerEvents();
    }
    
    destroy() {
        eventManager.removeAllHandlersForSource('myComponent');
    }
}
```

### 5. Return Values Matter
- Return `true` to stop event propagation to other handlers
- Return `false` or `undefined` to continue with other handlers

## Migration Guide

### From Direct Event Listeners

**Before:**
```javascript
document.addEventListener('click', (e) => {
    if (e.target.closest('.my-button')) {
        this.handleClick(e);
    }
});
```

**After:**
```javascript
eventManager.addHandler('click', 'myComponent-button', (e) => {
    this.handleClick(e);
}, {
    targetSelector: '.my-button'
});
```

### From Event Delegation

**Before:**
```javascript
container.addEventListener('click', (e) => {
    const card = e.target.closest('.model-card');
    if (!card) return;
    
    if (e.target.closest('.action-btn')) {
        this.handleAction(e);
    }
});
```

**After:**
```javascript
eventManager.addHandler('click', 'container-actions', (e) => {
    const card = e.target.closest('.model-card');
    if (!card) return false;
    
    if (e.target.closest('.action-btn')) {
        this.handleAction(e);
        return true;
    }
}, {
    targetSelector: '.container'
});
```

## Performance Benefits

1. **Reduced DOM listeners**: Single listener per event type instead of multiple
2. **Conditional execution**: Handlers only run when conditions are met
3. **Priority ordering**: Important handlers run first, avoiding unnecessary work
4. **Automatic cleanup**: Prevents memory leaks from orphaned listeners
5. **Centralized debugging**: All event handling flows through one system

## Debugging

Enable debug logging to trace event handling:
```javascript
// Add to EventManager.js for debugging
console.log(`Handling ${eventType} event with ${handlers.length} handlers`);
```

The event manager provides a foundation for coordinated, efficient event handling across the entire application.
