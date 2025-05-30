/**
 * Utility functions to update checkpoint cards after modal edits
 */

/**
 * Update the checkpoint card after metadata edits in the modal
 * @param {string} filePath - Path to the checkpoint file
 * @param {Object} updates - Object containing the updates (model_name, base_model, etc)
 */
export function updateCheckpointCard(filePath, updates) {
    // Find the card with matching filepath
    const checkpointCard = document.querySelector(`.lora-card[data-filepath="${filePath}"]`);
    if (!checkpointCard) return;

    // Update card dataset and visual elements based on the updates object
    Object.entries(updates).forEach(([key, value]) => {
        // Update dataset
        checkpointCard.dataset[key] = value;

        // Update visual elements based on the property
        switch(key) {
            case 'name': // model_name
                // Update the model name in the footer
                const modelNameElement = checkpointCard.querySelector('.model-name');
                if (modelNameElement) modelNameElement.textContent = value;
                break;

            case 'base_model':
                // Update the base model label in the card header
                const baseModelLabel = checkpointCard.querySelector('.base-model-label');
                if (baseModelLabel) {
                    baseModelLabel.textContent = value;
                    baseModelLabel.title = value;
                }
                break;
                
            case 'filepath':
                // The filepath was changed (file renamed), update the dataset
                checkpointCard.dataset.filepath = value;
                break;
                
            case 'tags':
                // Update tags if they're displayed on the card
                try {
                    checkpointCard.dataset.tags = JSON.stringify(value);
                } catch (e) {
                    console.error('Failed to update tags:', e);
                }
                break;
                
            // Add other properties as needed
        }
    });
}

/**
 * Update the Lora card after metadata edits in the modal
 * @param {string} filePath - Path to the Lora file
 * @param {Object} updates - Object containing the updates (model_name, base_model, notes, usage_tips, etc)
 * @param {string} [newFilePath] - Optional new file path if the file has been renamed
 */
export function updateLoraCard(filePath, updates, newFilePath) {
    // Find the card with matching filepath
    const loraCard = document.querySelector(`.lora-card[data-filepath="${filePath}"]`);
    if (!loraCard) return;

    // If file was renamed, update the filepath first
    if (newFilePath) {
        loraCard.dataset.filepath = newFilePath;
    }

    // Update card dataset and visual elements based on the updates object
    Object.entries(updates).forEach(([key, value]) => {
        // Update dataset
        loraCard.dataset[key] = value;

        // Update visual elements based on the property
        switch(key) {
            case 'model_name':
                // Update the model name in the card title
                const titleElement = loraCard.querySelector('.card-title');
                if (titleElement) titleElement.textContent = value;
                
                // Also update the model name in the footer if it exists
                const modelNameElement = loraCard.querySelector('.model-name');
                if (modelNameElement) modelNameElement.textContent = value;
                break;

            case 'file_name':
                // Update the file_name in the dataset
                loraCard.dataset.file_name = value;
                break;
                
            case 'base_model':
                // Update the base model label in the card header if it exists
                const baseModelLabel = loraCard.querySelector('.base-model-label');
                if (baseModelLabel) {
                    baseModelLabel.textContent = value;
                    baseModelLabel.title = value;
                }
                break;
                
            case 'tags':
                // Update tags if they're displayed on the card
                try {
                    if (typeof value === 'string') {
                        loraCard.dataset.tags = value;
                    } else {
                        loraCard.dataset.tags = JSON.stringify(value);
                    }
                    
                    // If there's a tag container, update its content
                    const tagContainer = loraCard.querySelector('.card-tags');
                    if (tagContainer) {
                        // This depends on how your tags are rendered
                        // You may need to update this logic based on your tag rendering function
                    }
                } catch (e) {
                    console.error('Failed to update tags:', e);
                }
                break;
                
            // No visual updates needed for notes, usage_tips as they're typically not shown on cards
        }
    });
    
    return loraCard; // Return the updated card element for chaining
}

/**
 * Update the recipe card after metadata edits in the modal
 * @param {string} recipeId - ID of the recipe to update
 * @param {Object} updates - Object containing the updates (title, tags, source_path)
 */
export function updateRecipeCard(recipeId, updates) {
    // Find the card with matching recipe ID
    const recipeCard = document.querySelector(`.lora-card[data-id="${recipeId}"]`);
    if (!recipeCard) return;

    // Get the recipe card component instance
    const recipeCardInstance = recipeCard._recipeCardInstance;
    
    // Update card dataset and visual elements based on the updates object
    Object.entries(updates).forEach(([key, value]) => {
        // Update dataset
        recipeCard.dataset[key] = value;

        // Update visual elements based on the property
        switch(key) {
            case 'title':
                // Update the title in the recipe object
                if (recipeCardInstance && recipeCardInstance.recipe) {
                    recipeCardInstance.recipe.title = value;
                }
                
                // Update the title shown in the card
                const modelNameElement = recipeCard.querySelector('.model-name');
                if (modelNameElement) modelNameElement.textContent = value;
                break;
                
            case 'tags':
                // Update tags in the recipe object (not displayed on card UI)
                if (recipeCardInstance && recipeCardInstance.recipe) {
                    recipeCardInstance.recipe.tags = value;
                }
                
                // Store in dataset as JSON string
                try {
                    if (typeof value === 'string') {
                        recipeCard.dataset.tags = value;
                    } else {
                        recipeCard.dataset.tags = JSON.stringify(value);
                    }
                } catch (e) {
                    console.error('Failed to update recipe tags:', e);
                }
                break;
                
            case 'source_path':
                // Update source_path in the recipe object (not displayed on card UI)
                if (recipeCardInstance && recipeCardInstance.recipe) {
                    recipeCardInstance.recipe.source_path = value;
                }
                break;
        }
    });
    
    return recipeCard; // Return the updated card element for chaining
}