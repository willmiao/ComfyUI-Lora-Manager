import { showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';

export class ImageProcessor {
    constructor(importManager) {
        this.importManager = importManager;
    }

    handleFileUpload(event) {
        const file = event.target.files[0];
        if (file) {
            this.handleDroppedFile(file);
        }
    }

    /**
     * Shared entry for files coming from the file picker, drag & drop,
     * or clipboard paste.
     */
    handleDroppedFile(file) {
        const errorElement = document.getElementById('uploadError');

        // Validate file type
        if (!file.type.match('image.*')) {
            errorElement.textContent = translate('recipes.controls.import.errors.selectImageFile', {}, 'Please select an image file');
            return;
        }

        // Reset error
        errorElement.textContent = '';
        this.importManager.recipeImage = file;
        this.importManager.importMode = 'upload';
        console.log(`[RecipeImport] Recipe image selected: ${file.name}`);

        // Show the selected file name in the drop zone
        this.importManager.updateSelectedFileName(file.name);

        // Auto-proceed to next step if file is selected
        this.importManager.uploadAndAnalyzeImage();
    }

    async handleUrlInput() {
        const urlInput = document.getElementById('imageUrlInput');
        const errorElement = document.getElementById('importUrlError');
        const input = urlInput.value.trim();

        // Validate input
        if (!input) {
            errorElement.textContent = translate('recipes.controls.import.errors.enterUrlOrPath', {}, 'Please enter a URL or file path');
            return;
        }

        // Front-end format validation before hitting the backend
        if (input.startsWith('http://') || input.startsWith('https://')) {
            try {
                new URL(input);
            } catch {
                errorElement.textContent = translate('recipes.controls.import.errors.invalidUrl', {}, 'Please enter a valid URL');
                return;
            }
        } else if (!/\.(png|jpe?g|webp|gif|bmp|avif|jxl|mp4|webm)$/i.test(input)) {
            errorElement.textContent = translate('recipes.controls.import.errors.invalidInputFormat', {}, 'Please enter an image URL or a local image file path');
            return;
        }

        // Reset error
        errorElement.textContent = '';
        this.importManager.importMode = 'url';

        console.log(
            `[RecipeImport] Analyzing recipe input (${input.startsWith('http://') || input.startsWith('https://') ? 'remote URL' : 'local path'}): ${input.slice(0, 80)}`
        );

        // Put the fetch button into a loading state to prevent duplicate submits
        const fetchBtn = document.getElementById('fetchImageBtn');
        this._setFetchButtonLoading(fetchBtn, true);

        // Show loading indicator
        this.importManager.loadingManager.showSimpleLoading(translate('recipes.controls.import.processingInput', {}, 'Processing input...'));

        try {
            // Check if it's a URL or a local file path
            if (input.startsWith('http://') || input.startsWith('https://')) {
                // Handle as URL
                await this.analyzeImageFromUrl(input);
            } else {
                // Handle as local file path
                await this.analyzeImageFromLocalPath(input);
            }
        } catch (error) {
            errorElement.textContent = error.message || 'Failed to process input';
        } finally {
            this._setFetchButtonLoading(fetchBtn, false);
            this.importManager.loadingManager.hide();
        }
    }

    _setFetchButtonLoading(button, isLoading) {
        if (!button) return;
        button.disabled = isLoading;
        button.classList.toggle('loading', isLoading);
        const icon = button.querySelector('i');
        if (icon) {
            icon.className = isLoading ? 'fas fa-spinner fa-spin' : 'fas fa-download';
        }
    }

    async analyzeImageFromUrl(url) {
        try {
            // Call the API with URL data
            const response = await fetch('/api/lm/recipes/analyze-image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: url })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to analyze image from URL');
            }
            
            // Get recipe data from response
            const recipeData = await response.json();

            if (!recipeData) {
                throw new Error('No recipe data returned from image analysis');
            }

            this.importManager.recipeData = recipeData;
            this._ensureCheckpointMetadata();

            // Check if we have an error message
            if (this.importManager.recipeData.error) {
                throw new Error(this.importManager.recipeData.error);
            }

            this.importManager.recipeData.loras = Array.isArray(this.importManager.recipeData.loras)
                ? this.importManager.recipeData.loras
                : [];

            // Find missing LoRAs
            this.importManager.missingLoras = this.importManager.recipeData.loras.filter(
                lora => !lora.existsLocally
            );
            
            // Reset import as new flag
            this.importManager.importAsNew = false;
            
            // Proceed to recipe details step
            console.log(
                `[RecipeImport] Analysis complete: ${this.importManager.recipeData.loras.length} LoRA(s) found, ${this.importManager.missingLoras.length} missing locally.`
            );
            this.importManager.showRecipeDetailsStep();
            
        } catch (error) {
            console.error('Error analyzing URL:', error);
            throw error;
        }
    }

    async analyzeImageFromLocalPath(path) {
        try {
            // Call the API with local path data
            const response = await fetch('/api/lm/recipes/analyze-local-image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ path: path })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load image from local path');
            }
            
            // Get recipe data from response
            const recipeData = await response.json();

            if (!recipeData) {
                throw new Error('No recipe data returned from image analysis');
            }

            this.importManager.recipeData = recipeData;
            this._ensureCheckpointMetadata();

            // Check if we have an error message
            if (this.importManager.recipeData.error) {
                throw new Error(this.importManager.recipeData.error);
            }

            this.importManager.recipeData.loras = Array.isArray(this.importManager.recipeData.loras)
                ? this.importManager.recipeData.loras
                : [];

            // Find missing LoRAs
            this.importManager.missingLoras = this.importManager.recipeData.loras.filter(
                lora => !lora.existsLocally
            );
            
            // Reset import as new flag
            this.importManager.importAsNew = false;
            
            // Proceed to recipe details step
            console.log(
                `[RecipeImport] Analysis complete: ${this.importManager.recipeData.loras.length} LoRA(s) found, ${this.importManager.missingLoras.length} missing locally.`
            );
            this.importManager.showRecipeDetailsStep();
            
        } catch (error) {
            console.error('Error analyzing local path:', error);
            throw error;
        }
    }

    async uploadAndAnalyzeImage() {
        if (!this.importManager.recipeImage) {
            showToast('toast.recipes.selectImageFirst', {}, 'error');
            return;
        }
        
        try {
            this.importManager.loadingManager.showSimpleLoading(translate('recipes.controls.import.analyzingMetadata', {}, 'Analyzing image metadata...'));
            
            // Create form data for upload
            const formData = new FormData();
            formData.append('image', this.importManager.recipeImage);
            
            // Upload image for analysis
            const response = await fetch('/api/lm/recipes/analyze-image', {
                method: 'POST',
                body: formData
            });
             
            // Get recipe data from response
            const recipeData = await response.json();

            if (!recipeData) {
                throw new Error('No recipe data returned from image analysis');
            }

            this.importManager.recipeData = recipeData;
            this._ensureCheckpointMetadata();

            // Check if we have an error message
            if (this.importManager.recipeData.error) {
                throw new Error(this.importManager.recipeData.error);
            }

            this.importManager.recipeData.loras = Array.isArray(this.importManager.recipeData.loras)
                ? this.importManager.recipeData.loras
                : [];
            
            // Find missing LoRAs
            this.importManager.missingLoras = this.importManager.recipeData.loras.filter(
                lora => !lora.existsLocally
            );
            
            // Reset import as new flag
            this.importManager.importAsNew = false;
            
            // Proceed to recipe details step
            console.log(
                `[RecipeImport] Analysis complete: ${this.importManager.recipeData.loras.length} LoRA(s) found, ${this.importManager.missingLoras.length} missing locally.`
            );
            this.importManager.showRecipeDetailsStep();
            
        } catch (error) {
            document.getElementById('uploadError').textContent = error.message;
        } finally {
            this.importManager.loadingManager.hide();
        }
    }

    _ensureCheckpointMetadata() {
        if (!this.importManager.recipeData) return;

        if (this.importManager.recipeData.model && !this.importManager.recipeData.checkpoint) {
            this.importManager.recipeData.checkpoint = this.importManager.recipeData.model;
        }
    }
}
