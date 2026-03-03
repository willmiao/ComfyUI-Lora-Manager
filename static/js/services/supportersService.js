/**
 * Supporters service - Fetches and manages supporters data
 */

let supportersData = null;
let isLoading = false;
let loadPromise = null;

/**
 * Fetch supporters data from the API
 * @returns {Promise<Object>} Supporters data
 */
export async function fetchSupporters() {
    // Return cached data if available
    if (supportersData) {
        return supportersData;
    }

    // Return existing promise if already loading
    if (isLoading && loadPromise) {
        return loadPromise;
    }

    isLoading = true;
    loadPromise = fetch('/api/lm/supporters')
        .then(response => {
            if (!response.ok) {
                throw new Error(`Failed to fetch supporters: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.supporters) {
                supportersData = data.supporters;
                return supportersData;
            }
            throw new Error(data.error || 'Failed to load supporters data');
        })
        .catch(error => {
            console.error('Error loading supporters:', error);
            // Return empty data on error
            return {
                specialThanks: [],
                allSupporters: [],
                totalCount: 0
            };
        })
        .finally(() => {
            isLoading = false;
            loadPromise = null;
        });

    return loadPromise;
}

/**
 * Clear cached supporters data
 */
export function clearSupportersCache() {
    supportersData = null;
}

let autoScrollRequest = null;
let autoScrollTimeout = null;
let isUserInteracting = false;
let isHovering = false;
let currentScrollPos = 0;

/**
 * Handle user interaction to stop auto-scroll
 */
function handleInteraction() {
    isUserInteracting = true;
}

/**
 * Handle mouse enter to pause auto-scroll
 */
function handleMouseEnter() {
    isHovering = true;
}

/**
 * Handle mouse leave to resume auto-scroll
 */
function handleMouseLeave() {
    isHovering = false;
}

/**
 * Initialize auto-scrolling for the supporters list like movie credits
 * @param {HTMLElement} container The scrollable container
 */
function initAutoScroll(container) {
    if (!container) return;
    
    // Stop any existing animation and clear any pending timeout
    if (autoScrollRequest) {
        cancelAnimationFrame(autoScrollRequest);
        autoScrollRequest = null;
    }
    if (autoScrollTimeout) {
        clearTimeout(autoScrollTimeout);
        autoScrollTimeout = null;
    }
    
    // Reset state for new scroll
    isUserInteracting = false;
    isHovering = false;
    container.scrollTop = 0;
    currentScrollPos = 0;

    const scrollSpeed = 0.4; // Pixels per frame (~24px/sec at 60fps)
    
    const step = () => {
        // Stop animation if container is hidden or no longer in DOM
        if (!container.offsetParent) {
            autoScrollRequest = null;
            return;
        }

        if (!isHovering && !isUserInteracting) {
            const prevScrollTop = container.scrollTop;
            currentScrollPos += scrollSpeed;
            container.scrollTop = currentScrollPos;
            
            // Check if we reached the bottom
            if (container.scrollTop === prevScrollTop && currentScrollPos > 1) {
                const isAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 1;
                if (isAtBottom) {
                    autoScrollRequest = null;
                    return;
                }
            }
        } else {
            // Keep currentScrollPos in sync if user scrolls manually or pauses
            currentScrollPos = container.scrollTop;
        }
        
        autoScrollRequest = requestAnimationFrame(step);
    };

    // Remove existing listeners before adding to avoid duplicates
    container.removeEventListener('mouseenter', handleMouseEnter);
    container.removeEventListener('mouseleave', handleMouseLeave);
    container.removeEventListener('wheel', handleInteraction);
    container.removeEventListener('touchstart', handleInteraction);
    container.removeEventListener('mousedown', handleInteraction);

    // Event listeners to handle user control
    container.addEventListener('mouseenter', handleMouseEnter);
    container.addEventListener('mouseleave', handleMouseLeave);
    
    // Use { passive: true } for better scroll performance
    container.addEventListener('wheel', handleInteraction, { passive: true });
    container.addEventListener('touchstart', handleInteraction, { passive: true });
    container.addEventListener('mousedown', handleInteraction);

    // Initial delay before starting the credits-style scroll
    autoScrollTimeout = setTimeout(() => {
        if (container.scrollHeight > container.clientHeight) {
            autoScrollRequest = requestAnimationFrame(step);
        }
    }, 1800);
}

/**
 * Render supporters in the support modal
 */
export async function renderSupporters() {
    const supporters = await fetchSupporters();

    // Update subtitle with total count
    const subtitleEl = document.getElementById('supportersSubtitle');
    if (subtitleEl) {
        const originalText = subtitleEl.textContent;
        subtitleEl.textContent = originalText.replace(/\d+/, supporters.totalCount);
    }

    // Render special thanks
    const specialThanksGrid = document.getElementById('specialThanksGrid');
    if (specialThanksGrid && supporters.specialThanks) {
        specialThanksGrid.innerHTML = supporters.specialThanks
            .map(supporter => `
                <div class="supporter-special-card" title="${supporter}">
                    <span class="supporter-special-name">${supporter}</span>
                </div>
            `)
            .join('');
    }

    // Render all supporters
    const supportersGrid = document.getElementById('supportersGrid');
    if (supportersGrid && supporters.allSupporters) {
        supportersGrid.innerHTML = supporters.allSupporters
            .map((supporter, index, array) => {
                const separator = index < array.length - 1
                    ? '<span class="supporter-separator">·</span>'
                    : '';
                return `
                    <span class="supporter-name-item" title="${supporter}">${supporter}</span>${separator}
                `;
            })
            .join('');
            
        // Initialize the auto-scroll effect
        initAutoScroll(supportersGrid);
    }
}
