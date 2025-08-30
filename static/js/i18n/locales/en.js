/**
 * English (en) translations for LoRA Manager
 */
export const en = {
    // Common terms used throughout the application
    common: {
        // File operations
        file: 'File',
        folder: 'Folder',
        name: 'Name',
        size: 'Size',
        date: 'Date',
        type: 'Type',
        path: 'Path',
        
        // File sizes
        fileSize: {
            zero: '0 Bytes',
            bytes: 'Bytes',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // Actions
        actions: {
            save: 'Save',
            cancel: 'Cancel',
            delete: 'Delete',
            edit: 'Edit',
            copy: 'Copy',
            move: 'Move',
            refresh: 'Refresh',
            download: 'Download',
            upload: 'Upload',
            search: 'Search',
            filter: 'Filter',
            sort: 'Sort',
            select: 'Select',
            selectAll: 'Select All',
            deselectAll: 'Deselect All',
            confirm: 'Confirm',
            close: 'Close',
            back: 'Back',
            next: 'Next',
            previous: 'Previous',
            view: 'View',
            preview: 'Preview',
            details: 'Details',
            settings: 'Settings',
            help: 'Help',
            about: 'About'
        },
        
        // Status messages
        status: {
            loading: 'Loading...',
            saving: 'Saving...',
            saved: 'Saved',
            error: 'Error',
            success: 'Success',
            warning: 'Warning',
            info: 'Information',
            processing: 'Processing...',
            completed: 'Completed',
            failed: 'Failed',
            cancelled: 'Cancelled',
            pending: 'Pending',
            ready: 'Ready'
        },
        
        // Languages
        language: {
            current: 'Language',
            select: 'Select Language',
            select_help: 'Choose your preferred language for the interface',
            english: 'English',
            chinese_simplified: 'Chinese (Simplified)',
            chinese_traditional: 'Chinese (Traditional)',
            russian: 'Russian',
            german: 'German',
            japanese: 'Japanese',
            korean: 'Korean',
            french: 'French',
            spanish: 'Spanish'
        }
    },
    
    // Header and navigation
    header: {
        appTitle: 'LoRA Manager',
        navigation: {
            loras: 'LoRAs',
            recipes: 'Recipes',
            checkpoints: 'Checkpoints',
            embeddings: 'Embeddings',
            statistics: 'Stats'
        },
        search: {
            placeholder: 'Search...',
            placeholders: {
                loras: 'Search LoRAs...',
                recipes: 'Search recipes...',
                checkpoints: 'Search checkpoints...',
                embeddings: 'Search embeddings...'
            },
            options: 'Search Options',
            searchIn: 'Search In:',
            notAvailable: 'Search not available on statistics page',
            filters: {
                filename: 'Filename',
                modelname: 'Model Name',
                tags: 'Tags',
                creator: 'Creator',
                title: 'Recipe Title',
                loraName: 'LoRA Filename',
                loraModel: 'LoRA Model Name'
            }
        },
        filter: {
            title: 'Filter Models',
            baseModel: 'Base Model',
            modelTags: 'Tags (Top 20)',
            clearAll: 'Clear All Filters'
        },
        theme: {
            toggle: 'Toggle theme',
            switchToLight: 'Switch to light theme',
            switchToDark: 'Switch to dark theme',
            switchToAuto: 'Switch to auto theme'
        }
    },
    
    // LoRAs page
    loras: {
        title: 'LoRA Models',
        controls: {
            sort: {
                title: 'Sort models by...',
                name: 'Name',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: 'Date Added',
                dateDesc: 'Newest',
                dateAsc: 'Oldest',
                size: 'File Size',
                sizeDesc: 'Largest',
                sizeAsc: 'Smallest'
            },
            refresh: {
                title: 'Refresh model list',
                quick: 'Quick Refresh (incremental)',
                full: 'Full Rebuild (complete)'
            },
            fetch: 'Fetch from Civitai',
            download: 'Download from URL',
            bulk: 'Bulk Operations',
            duplicates: 'Find Duplicates',
            favorites: 'Show Favorites Only'
        },
        bulkOperations: {
            title: 'Bulk Operations',
            selected: '{count} selected',
            sendToWorkflow: 'Send all selected LoRAs to workflow',
            copyAll: 'Copy all selected LoRAs syntax',
            refreshAll: 'Refresh CivitAI metadata for selected models',
            moveAll: 'Move selected models to folder',
            deleteAll: 'Delete selected models',
            clear: 'Clear selection'
        },
        contextMenu: {
            refreshMetadata: 'Refresh Civitai Data',
            relinkCivitai: 'Re-link to Civitai',
            copySyntax: 'Copy LoRA Syntax',
            sendToWorkflowAppend: 'Send to Workflow (Append)',
            sendToWorkflowReplace: 'Send to Workflow (Replace)',
            openExamples: 'Open Examples Folder',
            downloadExamples: 'Download Example Images',
            replacePreview: 'Replace Preview',
            setContentRating: 'Set Content Rating',
            moveToFolder: 'Move to Folder',
            excludeModel: 'Exclude Model',
            deleteModel: 'Delete Model'
        },
        modal: {
            title: 'LoRA Details',
            tabs: {
                examples: 'Examples',
                description: 'Model Description',
                recipes: 'Recipes'
            },
            info: {
                filename: 'Filename',
                modelName: 'Model Name',
                baseModel: 'Base Model',
                fileSize: 'File Size',
                dateAdded: 'Date Added',
                triggerWords: 'Trigger Words',
                description: 'Description',
                tags: 'Tags',
                rating: 'Rating',
                downloads: 'Downloads',
                likes: 'Likes',
                version: 'Version'
            },
            actions: {
                copyTriggerWords: 'Copy trigger words',
                copyLoraName: 'Copy LoRA name',
                sendToWorkflow: 'Send to Workflow',
                viewOnCivitai: 'View on Civitai',
                downloadExamples: 'Download example images'
            }
        }
    },
    
    // Recipes page
    recipes: {
        title: 'LoRA Recipes',
        controls: {
            import: 'Import Recipe',
            create: 'Create Recipe',
            export: 'Export Selected',
            downloadMissing: 'Download Missing LoRAs'
        },
        card: {
            author: 'Author',
            loras: '{count} LoRAs',
            tags: 'Tags',
            actions: {
                sendToWorkflow: 'Send to Workflow',
                edit: 'Edit Recipe',
                duplicate: 'Duplicate Recipe',
                export: 'Export Recipe',
                delete: 'Delete Recipe'
            }
        }
    },
    
    // Checkpoints page
    checkpoints: {
        title: 'Checkpoint Models',
        info: {
            filename: 'Filename',
            modelName: 'Model Name',
            baseModel: 'Base Model',
            fileSize: 'File Size',
            dateAdded: 'Date Added'
        }
    },
    
    // Embeddings page
    embeddings: {
        title: 'Embedding Models',
        info: {
            filename: 'Filename',
            modelName: 'Model Name',
            triggerWords: 'Trigger Words',
            fileSize: 'File Size',
            dateAdded: 'Date Added'
        }
    },
    
    // Statistics page
    statistics: {
        title: 'Statistics',
        overview: {
            title: 'Overview',
            totalLoras: 'Total LoRAs',
            totalCheckpoints: 'Total Checkpoints',
            totalEmbeddings: 'Total Embeddings',
            totalSize: 'Total Size',
            favoriteModels: 'Favorite Models'
        },
        charts: {
            modelsByType: 'Models by Type',
            modelsByBaseModel: 'Models by Base Model',
            modelsBySize: 'Models by File Size',
            modelsAddedOverTime: 'Models Added Over Time'
        }
    },
    
    // Modals and dialogs
    modals: {
        delete: {
            title: 'Confirm Deletion',
            message: 'Are you sure you want to delete this model?',
            warningMessage: 'This action cannot be undone.',
            confirm: 'Delete',
            cancel: 'Cancel'
        },
        exclude: {
            title: 'Exclude Model',
            message: 'Are you sure you want to exclude this model from the library?',
            confirm: 'Exclude',
            cancel: 'Cancel'
        },
        download: {
            title: 'Download Model',
            url: 'Model URL',
            placeholder: 'Enter Civitai model URL...',
            download: 'Download',
            cancel: 'Cancel'
        },
        move: {
            title: 'Move Models',
            selectFolder: 'Select destination folder',
            createFolder: 'Create new folder',
            folderName: 'Folder name',
            move: 'Move',
            cancel: 'Cancel'
        },
        contentRating: {
            title: 'Set Content Rating',
            current: 'Current',
            levels: {
                pg: 'PG',
                pg13: 'PG13',
                r: 'R',
                x: 'X',
                xxx: 'XXX'
            }
        }
    },
    
    // Error messages
    errors: {
        general: 'An error occurred',
        networkError: 'Network error. Please check your connection.',
        serverError: 'Server error. Please try again later.',
        fileNotFound: 'File not found',
        invalidFile: 'Invalid file format',
        uploadFailed: 'Upload failed',
        downloadFailed: 'Download failed',
        saveFailed: 'Save failed',
        loadFailed: 'Load failed',
        deleteFailed: 'Delete failed',
        moveFailed: 'Move failed',
        copyFailed: 'Copy failed',
        fetchFailed: 'Failed to fetch data from Civitai',
        invalidUrl: 'Invalid URL format',
        missingPermissions: 'Insufficient permissions'
    },
    
    // Success messages
    success: {
        saved: 'Successfully saved',
        deleted: 'Successfully deleted',
        moved: 'Successfully moved',
        copied: 'Successfully copied',
        downloaded: 'Successfully downloaded',
        uploaded: 'Successfully uploaded',
        refreshed: 'Successfully refreshed',
        exported: 'Successfully exported',
        imported: 'Successfully imported'
    },
    
    // Keyboard shortcuts
    keyboard: {
        navigation: 'Keyboard Navigation:',
        shortcuts: {
            pageUp: 'Scroll up one page',
            pageDown: 'Scroll down one page',
            home: 'Jump to top',
            end: 'Jump to bottom',
            bulkMode: 'Toggle bulk mode',
            search: 'Focus search',
            escape: 'Close modal/panel'
        }
    },
    
    // Initialization
    initialization: {
        title: 'Initializing LoRA Manager',
        message: 'Scanning and building LoRA cache. This may take a few minutes...',
        loras: {
            title: 'Initializing LoRA Manager',
            message: 'Scanning and building LoRA cache. This may take a few minutes...'
        },
        checkpoints: {
            title: 'Initializing Checkpoint Manager',
            message: 'Scanning and building checkpoint cache. This may take a few minutes...'
        },
        embeddings: {
            title: 'Initializing Embedding Manager',
            message: 'Scanning and building embedding cache. This may take a few minutes...'
        },
        recipes: {
            title: 'Initializing Recipe Manager',
            message: 'Loading and processing recipes. This may take a few minutes...'
        },
        statistics: {
            title: 'Initializing Statistics',
            message: 'Processing model data for statistics. This may take a few minutes...'
        },
        steps: {
            scanning: 'Scanning model files...',
            processing: 'Processing metadata...',
            building: 'Building cache...',
            finalizing: 'Finalizing...'
        }
    },
    
    // Tooltips and help text
    tooltips: {
        refresh: 'Refresh the model list',
        bulkOperations: 'Select multiple models for batch operations',
        favorites: 'Show only favorite models',
        duplicates: 'Find and manage duplicate models',
        search: 'Search models by name, tags, or other criteria',
        filter: 'Filter models by various criteria',
        sort: 'Sort models by different attributes',
        backToTop: 'Scroll back to top of page'
    }
};
