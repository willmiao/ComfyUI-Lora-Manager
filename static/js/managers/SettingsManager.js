import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { state, createDefaultSettings } from '../state/index.js';
import { resetAndReload } from '../api/modelApiFactory.js';
import { DOWNLOAD_PATH_TEMPLATES, MAPPABLE_BASE_MODELS, PATH_TEMPLATE_PLACEHOLDERS, DEFAULT_PATH_TEMPLATES, DEFAULT_PRIORITY_TAG_CONFIG } from '../utils/constants.js';
import { translate } from '../utils/i18nHelpers.js';
import { i18n } from '../i18n/index.js';
import { configureModelCardVideo } from '../components/shared/ModelCard.js';
import { validatePriorityTagString, getPriorityTagSuggestionsMap, invalidatePriorityTagSuggestionsCache } from '../utils/priorityTagHelpers.js';
import { bannerService } from './BannerService.js';

export class SettingsManager {
    constructor() {
        this.initialized = false;
        this.isOpen = false;
        this.initializationPromise = null;
        this.availableLibraries = {};
        this.activeLibrary = '';
        this.settingsFilePath = null;
        this.registeredStartupBannerIds = new Set();
        
        // Add initialization to sync with modal state
        this.currentPage = document.body.dataset.page || 'loras';

        this.backendSettingKeys = new Set(Object.keys(createDefaultSettings()));

        // Start initialization but don't await here to avoid blocking constructor
        this.initializationPromise = this.initializeSettings();

        this.initialize();
    }

    // Add method to wait for initialization to complete
    async waitForInitialization() {
        if (this.initializationPromise) {
            await this.initializationPromise;
        }
    }

    async initializeSettings() {
        // Reset to defaults before syncing
        state.global.settings = createDefaultSettings();

        // Sync settings from backend to frontend
        await this.syncSettingsFromBackend();
    }

    async syncSettingsFromBackend() {
        try {
            const response = await fetch('/api/lm/settings');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.success && data.settings) {
                state.global.settings = this.mergeSettingsWithDefaults(data.settings);
                this.settingsFilePath = data.settings.settings_file || this.settingsFilePath;
                this.registerStartupMessages(data.messages);
                console.log('Settings synced from backend');
            } else {
                console.error('Failed to sync settings from backend:', data.error);
                state.global.settings = this.mergeSettingsWithDefaults();
                this.registerStartupMessages(data?.messages);
            }
        } catch (error) {
            console.error('Failed to sync settings from backend:', error);
            state.global.settings = this.mergeSettingsWithDefaults();
            this.registerStartupMessages();
        }

        await this.applyLanguageSetting();
        this.applyFrontendSettings();
    }

    async applyLanguageSetting() {
        const desiredLanguage = state?.global?.settings?.language;

        if (!desiredLanguage) {
            return;
        }

        try {
            if (i18n.getCurrentLocale() !== desiredLanguage) {
                await i18n.setLanguage(desiredLanguage);
            }
        } catch (error) {
            console.warn('Failed to apply language from settings:', error);
        }
    }

    mergeSettingsWithDefaults(backendSettings = {}) {
        const defaults = createDefaultSettings();
        const merged = { ...defaults, ...backendSettings };

        const baseMappings = backendSettings?.base_model_path_mappings;
        if (baseMappings && typeof baseMappings === 'object' && !Array.isArray(baseMappings)) {
            merged.base_model_path_mappings = baseMappings;
        } else {
            merged.base_model_path_mappings = defaults.base_model_path_mappings;
        }

        let templates = backendSettings?.download_path_templates;
        if (typeof templates === 'string') {
            try {
                const parsed = JSON.parse(templates);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    templates = parsed;
                }
            } catch (parseError) {
                console.warn('Failed to parse download_path_templates string from backend, using defaults');
                templates = null;
            }
        }

        if (!templates || typeof templates !== 'object' || Array.isArray(templates)) {
            templates = {};
        }

        merged.download_path_templates = { ...DEFAULT_PATH_TEMPLATES, ...templates };

        const priorityTags = backendSettings?.priority_tags;
        const normalizedPriority = { ...DEFAULT_PRIORITY_TAG_CONFIG };
        if (priorityTags && typeof priorityTags === 'object' && !Array.isArray(priorityTags)) {
            Object.entries(priorityTags).forEach(([modelType, configValue]) => {
                if (typeof configValue === 'string') {
                    normalizedPriority[modelType] = configValue.trim();
                }
            });
        }
        merged.priority_tags = normalizedPriority;

        Object.keys(merged).forEach(key => this.backendSettingKeys.add(key));

        return merged;
    }

    registerStartupMessages(messages = []) {
        if (!Array.isArray(messages) || messages.length === 0) {
            return;
        }

        const severityPriority = {
            error: 90,
            warning: 60,
            info: 30,
        };

        messages.forEach((message, index) => {
            if (!message || typeof message !== 'object') {
                return;
            }

            if (!this.settingsFilePath && typeof message.settings_file === 'string') {
                this.settingsFilePath = message.settings_file;
            }

            const bannerId = `startup-${message.code || index}`;
            if (this.registeredStartupBannerIds.has(bannerId)) {
                return;
            }

            const severity = (message.severity || 'info').toLowerCase();
            const bannerTitle = message.title || 'Configuration notice';
            const bannerContent = message.message || message.content || '';
            const priority = typeof message.priority === 'number'
                ? message.priority
                : severityPriority[severity] || severityPriority.info;
            const dismissible = message.dismissible !== false;

            const normalizedActions = Array.isArray(message.actions)
                ? message.actions.map(action => ({
                    text: action.label || action.text || 'Review settings',
                    icon: action.icon || 'fas fa-cog',
                    action: action.action,
                    type: action.type || 'primary',
                    url: action.url,
                }))
                : [];

            bannerService.registerBanner(bannerId, {
                id: bannerId,
                title: bannerTitle,
                content: bannerContent,
                actions: normalizedActions,
                dismissible,
                priority,
                onRegister: (bannerElement) => {
                    normalizedActions.forEach(action => {
                        if (!action.action) {
                            return;
                        }

                        const button = bannerElement.querySelector(`.banner-action[data-action="${action.action}"]`);
                        if (button) {
                            button.addEventListener('click', (event) => {
                                event.preventDefault();
                                this.handleStartupBannerAction(action.action);
                            });
                        }
                    });
                },
            });

            this.registeredStartupBannerIds.add(bannerId);
        });
    }

    handleStartupBannerAction(action) {
        switch (action) {
            case 'open-settings-modal':
                modalManager.showModal('settingsModal');
                break;
            case 'open-settings-location':
                this.openSettingsFileLocation();
                break;
            default:
                console.warn('Unhandled startup banner action:', action);
        }
    }

    // Helper method to determine if a setting should be saved to backend
    isBackendSetting(settingKey) {
        return this.backendSettingKeys.has(settingKey);
    }

    // Helper method to save setting based on whether it's frontend or backend
    async saveSetting(settingKey, value) {
        // Update state
        state.global.settings[settingKey] = value;

        if (!this.isBackendSetting(settingKey)) {
            return;
        }

        // Save to backend
        try {
            const payload = {};
            payload[settingKey] = value;

            const response = await fetch('/api/lm/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error('Failed to save setting to backend');
            }

            // Parse response and check for success
            const data = await response.json();
            if (data.success === false) {
                throw new Error(data.error || 'Failed to save setting to backend');
            }
        } catch (error) {
            console.error(`Failed to save backend setting ${settingKey}:`, error);
            throw error;
        }
    }

    initialize() {
        if (this.initialized) return;
        
        // Add event listener to sync state when modal is closed via other means (like Escape key)
        const settingsModal = document.getElementById('settingsModal');
        if (settingsModal) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                        this.isOpen = settingsModal.style.display === 'block';
                        
                        // When modal is opened, update checkbox state from current settings
                        if (this.isOpen) {
                            this.loadSettingsToUI();
                        }
                    }
                });
            });
            
            observer.observe(settingsModal, { attributes: true });
        }
        
        // Add event listeners for all toggle-visibility buttons
        document.querySelectorAll('.toggle-visibility').forEach(button => {
            button.addEventListener('click', () => this.toggleInputVisibility(button));
        });

        const openSettingsLocationButton = document.querySelector('.settings-open-location-trigger');
        if (openSettingsLocationButton) {
            if (openSettingsLocationButton.dataset.settingsPath) {
                this.settingsFilePath = openSettingsLocationButton.dataset.settingsPath;
            }
            openSettingsLocationButton.addEventListener('click', () => {
                const filePath = openSettingsLocationButton.dataset.settingsPath;
                this.openSettingsFileLocation(filePath);
            });
        }

        ['lora', 'checkpoint', 'embedding'].forEach(modelType => {
            const customInput = document.getElementById(`${modelType}CustomTemplate`);
            if (customInput) {
                customInput.addEventListener('input', (e) => {
                    const template = e.target.value;
                    settingsManager.validateTemplate(modelType, template);
                    settingsManager.updateTemplatePreview(modelType, template);
                });

                customInput.addEventListener('blur', (e) => {
                    const template = e.target.value;
                    if (settingsManager.validateTemplate(modelType, template)) {
                        settingsManager.updateTemplate(modelType, template);
                    }
                });

                customInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.target.blur();
                    }
                });
            }
        });

        this.setupPriorityTagInputs();

        this.initialized = true;
    }

    async openSettingsFileLocation(filePath) {
        const targetPath = filePath || this.settingsFilePath || document.querySelector('.settings-open-location-trigger')?.dataset.settingsPath;

        if (!targetPath) {
            showToast('settings.openSettingsFileLocation.failed', {}, 'error');
            return;
        }

        try {
            const response = await fetch('/api/lm/open-file-location', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ file_path: targetPath }),
            });

            if (!response.ok) {
                throw new Error(`Request failed with status ${response.status}`);
            }

            this.settingsFilePath = targetPath;

            showToast('settings.openSettingsFileLocation.success', {}, 'success');
        } catch (error) {
            console.error('Failed to open settings file location:', error);
            showToast('settings.openSettingsFileLocation.failed', {}, 'error');
        }
    }

    async loadSettingsToUI() {
        // Set frontend settings from state
        const blurMatureContentCheckbox = document.getElementById('blurMatureContent');
        if (blurMatureContentCheckbox) {
            blurMatureContentCheckbox.checked = state.global.settings.blur_mature_content ?? true;
        }

        const showOnlySFWCheckbox = document.getElementById('showOnlySFW');
        if (showOnlySFWCheckbox) {
            showOnlySFWCheckbox.checked = state.global.settings.show_only_sfw ?? false;
        }

        // Set video autoplay on hover setting
        const autoplayOnHoverCheckbox = document.getElementById('autoplayOnHover');
        if (autoplayOnHoverCheckbox) {
            autoplayOnHoverCheckbox.checked = state.global.settings.autoplay_on_hover || false;
        }

        // Set display density setting
        const displayDensitySelect = document.getElementById('displayDensity');
        if (displayDensitySelect) {
            displayDensitySelect.value = state.global.settings.display_density || 'default';
        }

        // Set card info display setting
        const cardInfoDisplaySelect = document.getElementById('cardInfoDisplay');
        if (cardInfoDisplaySelect) {
            cardInfoDisplaySelect.value = state.global.settings.card_info_display || 'always';
        }

        // Set model card footer action
        const modelCardFooterActionSelect = document.getElementById('modelCardFooterAction');
        if (modelCardFooterActionSelect) {
            modelCardFooterActionSelect.value = state.global.settings.model_card_footer_action || 'example_images';
        }

        // Set model name display setting
        const modelNameDisplaySelect = document.getElementById('modelNameDisplay');
        if (modelNameDisplaySelect) {
            modelNameDisplaySelect.value = state.global.settings.model_name_display || 'model_name';
        }

        // Set optimize example images setting
        const optimizeExampleImagesCheckbox = document.getElementById('optimizeExampleImages');
        if (optimizeExampleImagesCheckbox) {
            optimizeExampleImagesCheckbox.checked = state.global.settings.optimize_example_images ?? true;
        }

        // Set auto download example images setting
        const autoDownloadExampleImagesCheckbox = document.getElementById('autoDownloadExampleImages');
        if (autoDownloadExampleImagesCheckbox) {
            autoDownloadExampleImagesCheckbox.checked = state.global.settings.auto_download_example_images || false;
        }

        // Load download path templates
        this.loadDownloadPathTemplates();

        // Load priority tag settings
        this.loadPriorityTagSettings();

        // Set include trigger words setting
        const includeTriggerWordsCheckbox = document.getElementById('includeTriggerWords');
        if (includeTriggerWordsCheckbox) {
            includeTriggerWordsCheckbox.checked = state.global.settings.include_trigger_words || false;
        }

        // Load metadata archive settings
        await this.loadMetadataArchiveSettings();

        // Load base model path mappings
        this.loadBaseModelMappings();

        // Load library options
        await this.loadLibraries();

        // Load default lora root
        await this.loadLoraRoots();
        
        // Load default checkpoint root
        await this.loadCheckpointRoots();

        // Load default embedding root
        await this.loadEmbeddingRoots();

        // Load language setting
        const languageSelect = document.getElementById('languageSelect');
        if (languageSelect) {
            const currentLanguage = state.global.settings.language || 'en';
            languageSelect.value = currentLanguage;
        }

        this.loadProxySettings();
    }

    setupPriorityTagInputs() {
        ['lora', 'checkpoint', 'embedding'].forEach((modelType) => {
            const textarea = document.getElementById(`${modelType}PriorityTagsInput`);
            if (!textarea) {
                return;
            }

            textarea.addEventListener('input', () => this.handlePriorityTagInput(modelType));
            textarea.addEventListener('blur', () => this.handlePriorityTagSave(modelType));
            textarea.addEventListener('keydown', (event) => this.handlePriorityTagKeyDown(event, modelType));
        });
    }

    loadPriorityTagSettings() {
        const priorityConfig = state.global.settings.priority_tags || {};
        ['lora', 'checkpoint', 'embedding'].forEach((modelType) => {
            const textarea = document.getElementById(`${modelType}PriorityTagsInput`);
            if (!textarea) {
                return;
            }

            const storedValue = priorityConfig[modelType] ?? DEFAULT_PRIORITY_TAG_CONFIG[modelType] ?? '';
            textarea.value = storedValue;
            this.displayPriorityTagValidation(modelType, true, []);
        });
    }

    handlePriorityTagInput(modelType) {
        const textarea = document.getElementById(`${modelType}PriorityTagsInput`);
        if (!textarea) {
            return;
        }

        const validation = validatePriorityTagString(textarea.value);
        this.displayPriorityTagValidation(modelType, validation.valid, validation.errors);
    }

    handlePriorityTagKeyDown(event, modelType) {
        if (event.key !== 'Enter') {
            return;
        }

        if (event.shiftKey) {
            return;
        }

        event.preventDefault();
        this.handlePriorityTagSave(modelType);
    }

    async handlePriorityTagSave(modelType) {
        const textarea = document.getElementById(`${modelType}PriorityTagsInput`);
        if (!textarea) {
            return;
        }

        const validation = validatePriorityTagString(textarea.value);
        if (!validation.valid) {
            this.displayPriorityTagValidation(modelType, false, validation.errors);
            return;
        }

        const sanitized = validation.formatted;
        const currentValue = state.global.settings.priority_tags?.[modelType] || '';
        this.displayPriorityTagValidation(modelType, true, []);

        if (sanitized === currentValue) {
            textarea.value = sanitized;
            return;
        }

        const updatedConfig = {
            ...state.global.settings.priority_tags,
            [modelType]: sanitized,
        };

        try {
            textarea.value = sanitized;
            await this.saveSetting('priority_tags', updatedConfig);
            showToast('settings.priorityTags.saveSuccess', {}, 'success');
            await this.refreshPriorityTagSuggestions();
        } catch (error) {
            console.error('Failed to save priority tag configuration:', error);
            showToast('settings.priorityTags.saveError', {}, 'error');
        }
    }

    displayPriorityTagValidation(modelType, isValid, errors = []) {
        const textarea = document.getElementById(`${modelType}PriorityTagsInput`);
        const errorElement = document.getElementById(`${modelType}PriorityTagsError`);
        if (!textarea) {
            return;
        }

        if (isValid || errors.length === 0) {
            textarea.classList.remove('settings-input-error');
            if (errorElement) {
                errorElement.textContent = '';
                errorElement.style.display = 'none';
            }
            return;
        }

        textarea.classList.add('settings-input-error');
        if (errorElement) {
            const message = this.getPriorityTagErrorMessage(errors[0]);
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        }
    }

    getPriorityTagErrorMessage(error) {
        if (!error) {
            return '';
        }

        const entryIndex = error.index ?? 0;
        switch (error.type) {
            case 'missingClosingParen':
                return translate('settings.priorityTags.validation.missingClosingParen', { index: entryIndex }, `Entry ${entryIndex} is missing a closing parenthesis.`);
            case 'missingCanonical':
                return translate('settings.priorityTags.validation.missingCanonical', { index: entryIndex }, `Entry ${entryIndex} must include a canonical tag.`);
            case 'duplicateCanonical':
                return translate('settings.priorityTags.validation.duplicateCanonical', { tag: error.canonical }, `The canonical tag "${error.canonical}" is duplicated.`);
            default:
                return translate('settings.priorityTags.validation.unknown', {}, 'Invalid priority tag configuration.');
        }
    }

    async refreshPriorityTagSuggestions() {
        invalidatePriorityTagSuggestionsCache();
        try {
            await getPriorityTagSuggestionsMap();
            window.dispatchEvent(new CustomEvent('lm:priority-tags-updated'));
        } catch (error) {
            console.warn('Failed to refresh priority tag suggestions:', error);
        }
    }

    loadProxySettings() {
        // Load proxy enabled setting
        const proxyEnabledCheckbox = document.getElementById('proxyEnabled');
        if (proxyEnabledCheckbox) {
            proxyEnabledCheckbox.checked = state.global.settings.proxy_enabled || false;
            
            // Add event listener for toggling proxy settings group visibility
            proxyEnabledCheckbox.addEventListener('change', () => {
                const proxySettingsGroup = document.getElementById('proxySettingsGroup');
                if (proxySettingsGroup) {
                    proxySettingsGroup.style.display = proxyEnabledCheckbox.checked ? 'block' : 'none';
                }
            });
            
            // Set initial visibility
            const proxySettingsGroup = document.getElementById('proxySettingsGroup');
            if (proxySettingsGroup) {
                proxySettingsGroup.style.display = proxyEnabledCheckbox.checked ? 'block' : 'none';
            }
        }

        // Load proxy type
        const proxyTypeSelect = document.getElementById('proxyType');
        if (proxyTypeSelect) {
            proxyTypeSelect.value = state.global.settings.proxy_type || 'http';
        }

        // Load proxy host
        const proxyHostInput = document.getElementById('proxyHost');
        if (proxyHostInput) {
            proxyHostInput.value = state.global.settings.proxy_host || '';
        }

        // Load proxy port
        const proxyPortInput = document.getElementById('proxyPort');
        if (proxyPortInput) {
            proxyPortInput.value = state.global.settings.proxy_port || '';
        }

        // Load proxy username
        const proxyUsernameInput = document.getElementById('proxyUsername');
        if (proxyUsernameInput) {
            proxyUsernameInput.value = state.global.settings.proxy_username || '';
        }

        // Load proxy password
        const proxyPasswordInput = document.getElementById('proxyPassword');
        if (proxyPasswordInput) {
            proxyPasswordInput.value = state.global.settings.proxy_password || '';
        }
    }

    async loadLibraries() {
        const librarySelect = document.getElementById('librarySelect');
        if (!librarySelect) {
            return;
        }

        const setPlaceholderOption = (textKey, fallback) => {
            librarySelect.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = translate(textKey, {}, fallback);
            librarySelect.appendChild(option);
        };

        setPlaceholderOption('settings.folderSettings.loadingLibraries', 'Loading libraries...');
        librarySelect.disabled = true;

        try {
            const response = await fetch('/api/lm/settings/libraries');
            if (!response.ok) {
                throw new Error('Failed to fetch library registry');
            }

            const data = await response.json();
            if (data.success === false) {
                throw new Error(data.error || 'Failed to fetch library registry');
            }

            const libraries = data.libraries && typeof data.libraries === 'object'
                ? data.libraries
                : {};

            this.availableLibraries = libraries;

            const entries = Object.entries(libraries);
            if (entries.length === 0) {
                this.activeLibrary = '';
                setPlaceholderOption('settings.folderSettings.noLibraries', 'No libraries configured');
                return;
            }

            const activeName = data.active_library && libraries[data.active_library]
                ? data.active_library
                : entries[0][0];

            this.activeLibrary = activeName;

            librarySelect.innerHTML = '';
            const fragment = document.createDocumentFragment();
            entries
                .sort((a, b) => {
                    const nameA = this.getLibraryDisplayName(a[0], a[1]).toLowerCase();
                    const nameB = this.getLibraryDisplayName(b[0], b[1]).toLowerCase();
                    return nameA.localeCompare(nameB);
                })
                .forEach(([name, info]) => {
                    const option = document.createElement('option');
                    option.value = name;
                    option.textContent = this.getLibraryDisplayName(name, info);
                    fragment.appendChild(option);
                });

            librarySelect.appendChild(fragment);
            librarySelect.value = activeName;
            librarySelect.disabled = entries.length <= 1;
        } catch (error) {
            console.error('Error loading libraries:', error);
            setPlaceholderOption('settings.folderSettings.noLibraries', 'No libraries configured');
            this.availableLibraries = {};
            this.activeLibrary = '';
            librarySelect.disabled = true;
            showToast('toast.settings.libraryLoadFailed', { message: error.message }, 'error');
        }
    }

    getLibraryDisplayName(libraryName, libraryData = {}) {
        if (libraryData && typeof libraryData === 'object') {
            const metadata = libraryData.metadata;
            if (metadata && typeof metadata === 'object' && metadata.display_name) {
                return metadata.display_name;
            }

            if (libraryData.display_name) {
                return libraryData.display_name;
            }
        }

        return libraryName;
    }

    async handleLibraryChange() {
        const librarySelect = document.getElementById('librarySelect');
        if (!librarySelect) {
            return;
        }

        const selectedLibrary = librarySelect.value;
        if (!selectedLibrary || selectedLibrary === this.activeLibrary) {
            librarySelect.value = this.activeLibrary;
            return;
        }

        librarySelect.disabled = true;

        try {
            state.loadingManager.showSimpleLoading('Activating library...');
            await this.activateLibrary(selectedLibrary);
            // Add a short delay before reloading the page
            await new Promise(resolve => setTimeout(resolve, 300));
            window.location.reload();
        } catch (error) {
            console.error('Failed to activate library:', error);
            showToast('toast.settings.libraryActivateFailed', { message: error.message }, 'error');
            await this.loadLibraries();
        } finally {
            state.loadingManager.hide();
            if (!document.hidden) {
                librarySelect.disabled = librarySelect.options.length <= 1;
            }
        }
    }

    async activateLibrary(libraryName) {
        const response = await fetch('/api/lm/settings/libraries/activate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ library: libraryName }),
        });

        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }

        const data = await response.json();
        if (data.success === false) {
            throw new Error(data.error || 'Failed to activate library');
        }

        const activeName = data.active_library || libraryName;
        this.activeLibrary = activeName;
        return data;
    }

    async loadLoraRoots() {
        try {
            const defaultLoraRootSelect = document.getElementById('defaultLoraRoot');
            if (!defaultLoraRootSelect) return;
            
            // Fetch lora roots
            const response = await fetch('/api/lm/loras/roots');
            if (!response.ok) {
                throw new Error('Failed to fetch LoRA roots');
            }
            
            const data = await response.json();
            if (!data.roots || data.roots.length === 0) {
                throw new Error('No LoRA roots found');
            }
            
            // Clear existing options except the first one (No Default)
            const noDefaultOption = defaultLoraRootSelect.querySelector('option[value=""]');
            defaultLoraRootSelect.innerHTML = '';
            defaultLoraRootSelect.appendChild(noDefaultOption);
            
            // Add options for each root
            data.roots.forEach(root => {
                const option = document.createElement('option');
                option.value = root;
                option.textContent = root;
                defaultLoraRootSelect.appendChild(option);
            });
            
            // Set selected value from settings
            const defaultRoot = state.global.settings.default_lora_root || '';
            defaultLoraRootSelect.value = defaultRoot;
            
        } catch (error) {
            console.error('Error loading LoRA roots:', error);
            showToast('toast.settings.loraRootsFailed', { message: error.message }, 'error');
        }
    }

    async loadCheckpointRoots() {
        try {
            const defaultCheckpointRootSelect = document.getElementById('defaultCheckpointRoot');
            if (!defaultCheckpointRootSelect) return;
            
            // Fetch checkpoint roots
            const response = await fetch('/api/lm/checkpoints/roots');
            if (!response.ok) {
                throw new Error('Failed to fetch checkpoint roots');
            }
            
            const data = await response.json();
            if (!data.roots || data.roots.length === 0) {
                throw new Error('No checkpoint roots found');
            }
            
            // Clear existing options except the first one (No Default)
            const noDefaultOption = defaultCheckpointRootSelect.querySelector('option[value=""]');
            defaultCheckpointRootSelect.innerHTML = '';
            defaultCheckpointRootSelect.appendChild(noDefaultOption);
            
            // Add options for each root
            data.roots.forEach(root => {
                const option = document.createElement('option');
                option.value = root;
                option.textContent = root;
                defaultCheckpointRootSelect.appendChild(option);
            });
            
            // Set selected value from settings
            const defaultRoot = state.global.settings.default_checkpoint_root || '';
            defaultCheckpointRootSelect.value = defaultRoot;
            
        } catch (error) {
            console.error('Error loading checkpoint roots:', error);
            showToast('toast.settings.checkpointRootsFailed', { message: error.message }, 'error');
        }
    }

    async loadEmbeddingRoots() {
        try {
            const defaultEmbeddingRootSelect = document.getElementById('defaultEmbeddingRoot');
            if (!defaultEmbeddingRootSelect) return;

            // Fetch embedding roots
            const response = await fetch('/api/lm/embeddings/roots');
            if (!response.ok) {
                throw new Error('Failed to fetch embedding roots');
            }

            const data = await response.json();
            if (!data.roots || data.roots.length === 0) {
                throw new Error('No embedding roots found');
            }

            // Clear existing options except the first one (No Default)
            const noDefaultOption = defaultEmbeddingRootSelect.querySelector('option[value=""]');
            defaultEmbeddingRootSelect.innerHTML = '';
            defaultEmbeddingRootSelect.appendChild(noDefaultOption);

            // Add options for each root
            data.roots.forEach(root => {
                const option = document.createElement('option');
                option.value = root;
                option.textContent = root;
                defaultEmbeddingRootSelect.appendChild(option);
            });

            // Set selected value from settings
            const defaultRoot = state.global.settings.default_embedding_root || '';
            defaultEmbeddingRootSelect.value = defaultRoot;

        } catch (error) {
            console.error('Error loading embedding roots:', error);
            showToast('toast.settings.embeddingRootsFailed', { message: error.message }, 'error');
        }
    }

    loadBaseModelMappings() {
        const mappingsContainer = document.getElementById('baseModelMappingsContainer');
        if (!mappingsContainer) return;

        const mappings = state.global.settings.base_model_path_mappings || {};
        
        // Clear existing mappings
        mappingsContainer.innerHTML = '';

        // Add existing mappings
        Object.entries(mappings).forEach(([baseModel, pathValue]) => {
            this.addMappingRow(baseModel, pathValue);
        });

        // Add empty row for new mappings if none exist
        if (Object.keys(mappings).length === 0) {
            this.addMappingRow('', '');
        }
    }

    addMappingRow(baseModel = '', pathValue = '') {
        const mappingsContainer = document.getElementById('baseModelMappingsContainer');
        if (!mappingsContainer) return;

        const row = document.createElement('div');
        row.className = 'mapping-row';
        
        const availableModels = MAPPABLE_BASE_MODELS.filter(model => {
            const existingMappings = state.global.settings.base_model_path_mappings || {};
            return !existingMappings.hasOwnProperty(model) || model === baseModel;
        });

        row.innerHTML = `
            <div class="mapping-controls">
                <select class="base-model-select">
                    <option value="">${translate('settings.downloadPathTemplates.selectBaseModel', {}, 'Select Base Model')}</option>
                    ${availableModels.map(model => 
                        `<option value="${model}" ${model === baseModel ? 'selected' : ''}>${model}</option>`
                    ).join('')}
                </select>
                <input type="text" class="path-value-input" placeholder="${translate('settings.downloadPathTemplates.customPathPlaceholder', {}, 'Custom path (e.g., flux)')}" value="${pathValue}">
                <button type="button" class="remove-mapping-btn" title="${translate('settings.downloadPathTemplates.removeMapping', {}, 'Remove mapping')}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        // Add event listeners
        const baseModelSelect = row.querySelector('.base-model-select');
        const pathValueInput = row.querySelector('.path-value-input');
        const removeBtn = row.querySelector('.remove-mapping-btn');

        // Save on select change immediately
        baseModelSelect.addEventListener('change', () => this.updateBaseModelMappings());
        
        // Save on input blur or Enter key
        pathValueInput.addEventListener('blur', () => this.updateBaseModelMappings());
        pathValueInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.target.blur();
            }
        });
        
        removeBtn.addEventListener('click', () => {
            row.remove();
            this.updateBaseModelMappings();
        });

        mappingsContainer.appendChild(row);
    }

    updateBaseModelMappings() {
        const mappingsContainer = document.getElementById('baseModelMappingsContainer');
        if (!mappingsContainer) return;

        const rows = mappingsContainer.querySelectorAll('.mapping-row');
        const newMappings = {};
        let hasValidMapping = false;

        rows.forEach(row => {
            const baseModelSelect = row.querySelector('.base-model-select');
            const pathValueInput = row.querySelector('.path-value-input');
            
            const baseModel = baseModelSelect.value.trim();
            const pathValue = pathValueInput.value.trim();
            
            if (baseModel && pathValue) {
                newMappings[baseModel] = pathValue;
                hasValidMapping = true;
            }
        });

        // Check if mappings have actually changed
        const currentMappings = state.global.settings.base_model_path_mappings || {};
        const mappingsChanged = JSON.stringify(currentMappings) !== JSON.stringify(newMappings);

        if (mappingsChanged) {
            // Update state and save
            state.global.settings.base_model_path_mappings = newMappings;
            this.saveBaseModelMappings();
        }

        // Add empty row if no valid mappings exist
        const hasEmptyRow = Array.from(rows).some(row => {
            const baseModelSelect = row.querySelector('.base-model-select');
            const pathValueInput = row.querySelector('.path-value-input');
            return !baseModelSelect.value && !pathValueInput.value;
        });

        if (!hasEmptyRow) {
            this.addMappingRow('', '');
        }

        // Update available options in all selects
        this.updateAvailableBaseModels();
    }

    updateAvailableBaseModels() {
        const mappingsContainer = document.getElementById('baseModelMappingsContainer');
        if (!mappingsContainer) return;

        const existingMappings = state.global.settings.base_model_path_mappings || {};
        const rows = mappingsContainer.querySelectorAll('.mapping-row');

        rows.forEach(row => {
            const select = row.querySelector('.base-model-select');
            const currentValue = select.value;
            
            // Get available models (not already mapped, except current)
            const availableModels = MAPPABLE_BASE_MODELS.filter(model => 
                !existingMappings.hasOwnProperty(model) || model === currentValue
            );

            // Rebuild options
            select.innerHTML = `<option value="">${translate('settings.downloadPathTemplates.selectBaseModel', {}, 'Select Base Model')}</option>` +
                availableModels.map(model => 
                    `<option value="${model}" ${model === currentValue ? 'selected' : ''}>${model}</option>`
                ).join('');
        });
    }

    async saveBaseModelMappings() {
        try {
            // Save to backend using universal save method
            await this.saveSetting('base_model_path_mappings', state.global.settings.base_model_path_mappings);

            // Show success toast
            const mappingCount = Object.keys(state.global.settings.base_model_path_mappings).length;
            if (mappingCount > 0) {
                showToast('toast.settings.mappingsUpdated', { 
                    count: mappingCount,
                    plural: mappingCount !== 1 ? 's' : ''
                }, 'success');
            } else {
                showToast('toast.settings.mappingsCleared', {}, 'success');
            }

        } catch (error) {
            console.error('Error saving base model mappings:', error);
            showToast('toast.settings.mappingSaveFailed', { message: error.message }, 'error');
        }
    }

    loadDownloadPathTemplates() {
        const templates = state.global.settings.download_path_templates || DEFAULT_PATH_TEMPLATES;
        
        Object.keys(templates).forEach(modelType => {
            this.loadTemplateForModelType(modelType, templates[modelType]);
        });
    }

    loadTemplateForModelType(modelType, template) {
        const presetSelect = document.getElementById(`${modelType}TemplatePreset`);
        const customRow = document.getElementById(`${modelType}CustomRow`);
        const customInput = document.getElementById(`${modelType}CustomTemplate`);
        
        if (!presetSelect) return;

        // Find matching preset
        const matchingPreset = this.findMatchingPreset(template);
        
        if (matchingPreset !== null) {
            presetSelect.value = matchingPreset;
            if (customRow) customRow.style.display = 'none';
        } else {
            // Custom template
            presetSelect.value = 'custom';
            if (customRow) customRow.style.display = 'block';
            if (customInput) {
                customInput.value = template;
                this.validateTemplate(modelType, template);
            }
        }
        
        this.updateTemplatePreview(modelType, template);
    }

    findMatchingPreset(template) {
        const presetValues = Object.values(DOWNLOAD_PATH_TEMPLATES)
            .map(t => t.value)
            .filter(v => v !== 'custom');
        
        return presetValues.includes(template) ? template : null;
    }

    updateTemplatePreset(modelType, value) {
        const customRow = document.getElementById(`${modelType}CustomRow`);
        const customInput = document.getElementById(`${modelType}CustomTemplate`);
        
        if (value === 'custom') {
            if (customRow) customRow.style.display = 'block';
            if (customInput) customInput.focus();
            return;
        } else {
            if (customRow) customRow.style.display = 'none';
        }
        
        // Update template
        this.updateTemplate(modelType, value);
    }

    updateTemplate(modelType, template) {
        // Validate template if it's custom
        if (document.getElementById(`${modelType}TemplatePreset`).value === 'custom') {
            if (!this.validateTemplate(modelType, template)) {
                return; // Don't save invalid templates
            }
        }
        
        // Update state
        if (!state.global.settings.download_path_templates) {
            state.global.settings.download_path_templates = { ...DEFAULT_PATH_TEMPLATES };
        }
        state.global.settings.download_path_templates[modelType] = template;
        
        // Update preview
        this.updateTemplatePreview(modelType, template);
        
        // Save settings
        this.saveDownloadPathTemplates();
    }

    validateTemplate(modelType, template) {
        const validationElement = document.getElementById(`${modelType}Validation`);
        if (!validationElement) return true;
        
        // Reset validation state
        validationElement.innerHTML = '';
        validationElement.className = 'template-validation';
        
        if (!template) {
            validationElement.innerHTML = `<i class="fas fa-check"></i> ${translate('settings.downloadPathTemplates.validation.validFlat', {}, 'Valid (flat structure)')}`;
            validationElement.classList.add('valid');
            return true;
        }
        
        // Check for invalid characters
        const invalidChars = /[<>:"|?*]/;
        if (invalidChars.test(template)) {
            validationElement.innerHTML = `<i class="fas fa-times"></i> ${translate('settings.downloadPathTemplates.validation.invalidChars', {}, 'Invalid characters detected')}`;
            validationElement.classList.add('invalid');
            return false;
        }
        
        // Check for double slashes
        if (template.includes('//')) {
            validationElement.innerHTML = `<i class="fas fa-times"></i> ${translate('settings.downloadPathTemplates.validation.doubleSlashes', {}, 'Double slashes not allowed')}`;
            validationElement.classList.add('invalid');
            return false;
        }
        
        // Check if it starts or ends with slash
        if (template.startsWith('/') || template.endsWith('/')) {
            validationElement.innerHTML = `<i class="fas fa-times"></i> ${translate('settings.downloadPathTemplates.validation.leadingTrailingSlash', {}, 'Cannot start or end with slash')}`;
            validationElement.classList.add('invalid');
            return false;
        }
        
        // Extract placeholders
        const placeholderRegex = /\{([^}]+)\}/g;
        const matches = template.match(placeholderRegex) || [];
        
        // Check for invalid placeholders
        const invalidPlaceholders = matches.filter(match => 
            !PATH_TEMPLATE_PLACEHOLDERS.includes(match)
        );
        
        if (invalidPlaceholders.length > 0) {
            validationElement.innerHTML = `<i class="fas fa-times"></i> ${translate('settings.downloadPathTemplates.validation.invalidPlaceholder', { placeholder: invalidPlaceholders[0] }, `Invalid placeholder: ${invalidPlaceholders[0]}`)}`;
            validationElement.classList.add('invalid');
            return false;
        }
        
        // Template is valid
        validationElement.innerHTML = `<i class="fas fa-check"></i> ${translate('settings.downloadPathTemplates.validation.validTemplate', {}, 'Valid template')}`;
        validationElement.classList.add('valid');
        return true;
    }

    updateTemplatePreview(modelType, template) {
        const previewElement = document.getElementById(`${modelType}Preview`);
        if (!previewElement) return;
        
        if (!template) {
            previewElement.textContent = 'model-name.safetensors';
        } else {
            // Generate example preview
            const exampleTemplate = template
                .replace('{base_model}', 'Flux.1 D')
                .replace('{author}', 'authorname')
                .replace('{first_tag}', 'style');
            previewElement.textContent = `${exampleTemplate}/model-name.safetensors`;
        }
        previewElement.style.display = 'block';
    }

    async saveDownloadPathTemplates() {
        try {
            // Save to backend using universal save method
            await this.saveSetting('download_path_templates', state.global.settings.download_path_templates);

            showToast('toast.settings.downloadTemplatesUpdated', {}, 'success');

        } catch (error) {
            console.error('Error saving download path templates:', error);
            showToast('toast.settings.downloadTemplatesFailed', { message: error.message }, 'error');
        }
    }

    toggleSettings() {
        if (this.isOpen) {
            modalManager.closeModal('settingsModal');
        } else {
            modalManager.showModal('settingsModal');
        }
        this.isOpen = !this.isOpen;
    }

    async saveToggleSetting(elementId, settingKey) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const value = element.checked;

        try {
            await this.saveSetting(settingKey, value);

            if (settingKey === 'proxy_enabled') {
                const proxySettingsGroup = document.getElementById('proxySettingsGroup');
                if (proxySettingsGroup) {
                    proxySettingsGroup.style.display = value ? 'block' : 'none';
                }
            }

            // Refresh metadata archive status when enable setting changes
            if (settingKey === 'enable_metadata_archive_db') {
                await this.updateMetadataArchiveStatus();
            }
                
            showToast('toast.settings.settingsUpdated', { setting: settingKey.replace(/_/g, ' ') }, 'success');
            
            // Apply frontend settings immediately
            this.applyFrontendSettings();
            
            // Trigger auto download setup/teardown when setting changes
            if (settingKey === 'auto_download_example_images' && window.exampleImagesManager) {
                if (value) {
                    window.exampleImagesManager.setupAutoDownload();
                } else {
                    window.exampleImagesManager.clearAutoDownload();
                }
            }
            
            if (settingKey === 'show_only_sfw' || settingKey === 'blur_mature_content') {
                this.reloadContent();
            }
            
            // Recalculate layout when compact mode changes
            if (settingKey === 'compact_mode' && state.virtualScroller) {
                state.virtualScroller.calculateLayout();
                showToast('toast.settings.compactModeToggled', {
                    state: value ? 'toast.settings.compactModeEnabled' : 'toast.settings.compactModeDisabled'
                }, 'success');
            }

        } catch (error) {
            showToast('toast.settings.settingSaveFailed', { message: error.message }, 'error');
        }
    }
    
    async saveSelectSetting(elementId, settingKey) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const value = element.value;
        
        try {
            // Update frontend state with mapped keys
            await this.saveSetting(settingKey, value);

            // Apply frontend settings immediately
            this.applyFrontendSettings();
            
            // Recalculate layout when display density changes
            if (settingKey === 'display_density' && state.virtualScroller) {
                state.virtualScroller.calculateLayout();
                
                let densityName = "Default";
                if (value === 'medium') densityName = "Medium";
                if (value === 'compact') densityName = "Compact";
                
                showToast('toast.settings.displayDensitySet', { density: densityName }, 'success');
                return;
            }
            
            showToast('toast.settings.settingsUpdated', { setting: settingKey.replace(/_/g, ' ') }, 'success');

            if (settingKey === 'model_name_display') {
                this.reloadContent();
            }

            if (settingKey === 'model_card_footer_action') {
                this.reloadContent();
            }
        } catch (error) {
            showToast('toast.settings.settingSaveFailed', { message: error.message }, 'error');
        }
    }

    async loadMetadataArchiveSettings() {
        try {
            // Load current settings from state
            const enableMetadataArchiveCheckbox = document.getElementById('enableMetadataArchive');
            if (enableMetadataArchiveCheckbox) {
                enableMetadataArchiveCheckbox.checked = state.global.settings.enable_metadata_archive_db || false;
            }

            // Load status
            await this.updateMetadataArchiveStatus();
        } catch (error) {
            console.error('Error loading metadata archive settings:', error);
        }
    }

    async updateMetadataArchiveStatus() {
        try {
            const response = await fetch('/api/lm/metadata-archive-status');
            const data = await response.json();

            const statusContainer = document.getElementById('metadataArchiveStatus');
            if (statusContainer && data.success) {
                const status = data;
                const sizeText = status.databaseSize > 0 ? ` (${this.formatFileSize(status.databaseSize)})` : '';
                
                statusContainer.innerHTML = `
                    <div class="archive-status-item">
                        <span class="archive-status-label">${translate('settings.metadataArchive.status')}:</span>
                        <span class="archive-status-value status-${status.isAvailable ? 'available' : 'unavailable'}">
                            ${status.isAvailable ? translate('settings.metadataArchive.statusAvailable') : translate('settings.metadataArchive.statusUnavailable')}
                            ${sizeText}
                        </span>
                    </div>
                    <div class="archive-status-item">
                        <span class="archive-status-label">${translate('settings.metadataArchive.enabled')}:</span>
                        <span class="archive-status-value status-${status.isEnabled ? 'enabled' : 'disabled'}">
                            ${status.isEnabled ? translate('common.status.enabled') : translate('common.status.disabled')}
                        </span>
                    </div>
                `;

                // Update button states
                const downloadBtn = document.getElementById('downloadMetadataArchiveBtn');
                const removeBtn = document.getElementById('removeMetadataArchiveBtn');
                
                if (downloadBtn) {
                    downloadBtn.disabled = status.isAvailable;
                    downloadBtn.textContent = status.isAvailable ? 
                        translate('settings.metadataArchive.downloadedButton') : 
                        translate('settings.metadataArchive.downloadButton');
                }
                
                if (removeBtn) {
                    removeBtn.disabled = !status.isAvailable;
                }
            }
        } catch (error) {
            console.error('Error updating metadata archive status:', error);
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async downloadMetadataArchive() {
        try {
            const downloadBtn = document.getElementById('downloadMetadataArchiveBtn');
            
            if (downloadBtn) {
                downloadBtn.disabled = true;
                downloadBtn.textContent = translate('settings.metadataArchive.downloadingButton');
            }
            
            // Show loading with enhanced progress
            const progressUpdater = state.loadingManager.showEnhancedProgress(translate('settings.metadataArchive.preparing'));

            // Set up WebSocket for progress updates
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            const downloadId = `metadata_archive_${Date.now()}`;
            const ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);
            
            let wsConnected = false;
            let actualDownloadId = downloadId; // Will be updated when WebSocket confirms the ID
            
            // Promise to wait for WebSocket connection and ID confirmation
            const wsReady = new Promise((resolve) => {
                ws.onopen = () => {
                    wsConnected = true;
                    console.log('Connected to metadata archive download progress WebSocket');
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    // Handle download ID confirmation
                    if (data.type === 'download_id') {
                        actualDownloadId = data.download_id;
                        console.log(`Connected to metadata archive download progress with ID: ${data.download_id}`);
                        resolve(data.download_id);
                        return;
                    }
                    
                    // Handle metadata archive download progress
                    if (data.type === 'metadata_archive_download') {
                        const message = data.message || '';
                        
                        // Update progress bar based on stage
                        let progressPercent = 0;
                        if (data.stage === 'download') {
                            // Extract percentage from message if available
                            const percentMatch = data.message.match(/(\d+\.?\d*)%/);
                            if (percentMatch) {
                                progressPercent = Math.min(parseFloat(percentMatch[1]), 90); // Cap at 90% for download
                            } else {
                                progressPercent = 0; // Default download progress
                            }
                        } else if (data.stage === 'extract') {
                            progressPercent = 95; // Near completion for extraction
                        }
                        
                        // Update loading manager progress
                        progressUpdater.updateProgress(progressPercent, '', `${message}`);
                    }
                };
                
                ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    resolve(downloadId); // Fallback to original ID
                };
                
                // Timeout fallback
                setTimeout(() => resolve(downloadId), 5000);
            });
            
            ws.onclose = () => {
                console.log('WebSocket connection closed');
            };

            // Wait for WebSocket to be ready
            await wsReady;

            const response = await fetch(`/api/lm/download-metadata-archive?download_id=${encodeURIComponent(actualDownloadId)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            // Close WebSocket
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }

            if (data.success) {
                // Complete progress
                await progressUpdater.complete(translate('settings.metadataArchive.downloadComplete'));
                
                showToast('settings.metadataArchive.downloadSuccess', 'success');
                
                // Update settings using universal save method
                await this.saveSetting('enable_metadata_archive_db', true);
                
                // Update UI
                const enableCheckbox = document.getElementById('enableMetadataArchive');
                if (enableCheckbox) {
                    enableCheckbox.checked = true;
                }
                
                await this.updateMetadataArchiveStatus();
            } else {
                // Hide loading on error
                state.loadingManager.hide();
                showToast('settings.metadataArchive.downloadError' + ': ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Error downloading metadata archive:', error);
            
            // Hide loading on error
            state.loadingManager.hide();

            showToast('settings.metadataArchive.downloadError' + ': ' + error.message, 'error');
        } finally {
            const downloadBtn = document.getElementById('downloadMetadataArchiveBtn');
            if (downloadBtn) {
                downloadBtn.disabled = false;
                downloadBtn.textContent = translate('settings.metadataArchive.downloadButton');
            }
        }
    }

    async removeMetadataArchive() {
        if (!confirm(translate('settings.metadataArchive.removeConfirm'))) {
            return;
        }

        try {
            const removeBtn = document.getElementById('removeMetadataArchiveBtn');
            if (removeBtn) {
                removeBtn.disabled = true;
                removeBtn.textContent = translate('settings.metadataArchive.removingButton');
            }

            const response = await fetch('/api/lm/remove-metadata-archive', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            if (data.success) {
                showToast('settings.metadataArchive.removeSuccess', 'success');

                // Update settings using universal save method
                await this.saveSetting('enable_metadata_archive_db', false);
                
                // Update UI
                const enableCheckbox = document.getElementById('enableMetadataArchive');
                if (enableCheckbox) {
                    enableCheckbox.checked = false;
                }
                
                await this.updateMetadataArchiveStatus();
            } else {
                showToast('settings.metadataArchive.removeError' + ': ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Error removing metadata archive:', error);
            showToast('settings.metadataArchive.removeError' + ': ' + error.message, 'error');
        } finally {
            const removeBtn = document.getElementById('removeMetadataArchiveBtn');
            if (removeBtn) {
                removeBtn.disabled = false;
                removeBtn.textContent = translate('settings.metadataArchive.removeButton');
            }
        }
    }
    
    async saveInputSetting(elementId, settingKey) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const value = element.value.trim(); // Trim whitespace
        
        try {
            // Check if value has changed from existing value
            const currentValue = state.global.settings[settingKey] || '';
            if (value === currentValue) {
                return; // No change, exit early
            }
            
            // For username and password, handle empty values specially
            if ((settingKey === 'proxy_username' || settingKey === 'proxy_password') && value === '') {
                // Remove from state instead of setting to empty string
                delete state.global.settings[settingKey];
                
                // Send delete flag to backend
                const payload = {};
                payload[settingKey] = '__DELETE__';
                
                const response = await fetch('/api/lm/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error('Failed to delete setting');
                }
            } else {
                // Use the universal save method
                await this.saveSetting(settingKey, value);
            }
            
            showToast('toast.settings.settingsUpdated', { setting: settingKey.replace(/_/g, ' ') }, 'success');
            
        } catch (error) {
            showToast('toast.settings.settingSaveFailed', { message: error.message }, 'error');
        }
    }

    async saveLanguageSetting() {
        const element = document.getElementById('languageSelect');
        if (!element) return;

        const selectedLanguage = element.value;

        try {
            // Use the universal save method for language (frontend-only setting)
            await this.saveSetting('language', selectedLanguage);

            // Reload the page to apply the new language
            window.location.reload();

        } catch (error) {
            showToast('toast.settings.languageChangeFailed', { message: error.message }, 'error');
        }
    }

    toggleInputVisibility(button) {
        const input = button.parentElement.querySelector('input');
        const icon = button.querySelector('i');
        
        if (input.type === 'password') {
            input.type = 'text';
            icon.className = 'fas fa-eye-slash';
        } else {
            input.type = 'password';
            icon.className = 'fas fa-eye';
        }
    }

    confirmClearCache() {
        // Show confirmation modal
        modalManager.showModal('clearCacheModal');
    }

    async reloadContent() {
        if (this.currentPage === 'loras') {
            // Reload the loras without updating folders
            await resetAndReload(false);
        } else if (this.currentPage === 'recipes') {
            // Reload the recipes without updating folders
            await window.recipeManager.loadRecipes();
        } else if (this.currentPage === 'checkpoints') {
            // Reload the checkpoints without updating folders
            await resetAndReload(false);
        } else if (this.currentPage === 'embeddings') {
            // Reload the embeddings without updating folders
            await resetAndReload(false);
        }
    }

    applyFrontendSettings() {
        // Apply autoplay setting to existing videos in card previews
        const autoplayOnHover = state.global.settings.autoplay_on_hover;
        document.querySelectorAll('.card-preview video').forEach(video => {
            configureModelCardVideo(video, autoplayOnHover);
        });
        
        // Apply display density class to grid
        const grid = document.querySelector('.card-grid');
        if (grid) {
            const density = state.global.settings.display_density || 'default';

            // Remove all density classes first
            grid.classList.remove('default-density', 'medium-density', 'compact-density');

            // Add the appropriate density class
            grid.classList.add(`${density}-density`);
        }

        // Apply card info display setting
        const cardInfoDisplay = state.global.settings.card_info_display || 'always';
        document.body.classList.toggle('hover-reveal', cardInfoDisplay === 'hover');
    }
}

// Create singleton instance
export const settingsManager = new SettingsManager();
