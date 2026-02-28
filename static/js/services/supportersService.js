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

/**
 * Render supporters in the support modal
 */
export async function renderSupporters() {
    const supporters = await fetchSupporters();

    // Update subtitle with total count
    const subtitleEl = document.getElementById('supportersSubtitle');
    if (subtitleEl) {
        // Get the translation key and replace count
        const originalText = subtitleEl.textContent;
        // Replace the count in the text (simple approach)
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
    }
}
