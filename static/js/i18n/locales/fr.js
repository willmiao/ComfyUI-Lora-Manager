/**
 * French (fr) translations for LoRA Manager
 */
export const fr = {
    // Termes communs utilisés dans l'application
    common: {
        // Opérations sur les fichiers
        file: 'Fichier',
        folder: 'Dossier',
        name: 'Nom',
        size: 'Taille',
        date: 'Date',
        type: 'Type',
        path: 'Chemin',
        
        // Tailles de fichiers
        fileSize: {
            zero: '0 Octets',
            bytes: 'Octets',
            kb: 'Ko',
            mb: 'Mo',
            gb: 'Go',
            tb: 'To'
        },
        
        // Actions
        actions: {
            save: 'Enregistrer',
            cancel: 'Annuler',
            delete: 'Supprimer',
            edit: 'Modifier',
            copy: 'Copier',
            move: 'Déplacer',
            refresh: 'Actualiser',
            download: 'Télécharger',
            upload: 'Importer',
            search: 'Rechercher',
            filter: 'Filtrer',
            sort: 'Trier',
            select: 'Sélectionner',
            selectAll: 'Tout sélectionner',
            deselectAll: 'Tout désélectionner',
            confirm: 'Confirmer',
            close: 'Fermer',
            back: 'Retour',
            next: 'Suivant',
            previous: 'Précédent',
            view: 'Afficher',
            preview: 'Aperçu',
            details: 'Détails',
            settings: 'Paramètres',
            help: 'Aide',
            about: 'À propos'
        },
        
        // Paramètres de langue
        language: {
            current: 'Langue',
            select: 'Sélectionner la langue',
            select_help: 'Choisissez votre langue d\'interface préférée',
            english: 'Anglais',
            chinese_simplified: 'Chinois (simplifié)',
            chinese_traditional: 'Chinois (traditionnel)',
            russian: 'Russe',
            german: 'Allemand',
            japanese: 'Japonais',
            korean: 'Coréen',
            french: 'Français',
            spanish: 'Espagnol'
        },
        
        // Messages de statut
        status: {
            loading: 'Chargement...',
            saving: 'Enregistrement...',
            saved: 'Enregistré',
            error: 'Erreur',
            success: 'Succès',
            warning: 'Avertissement',
            info: 'Information',
            processing: 'Traitement...',
            completed: 'Terminé',
            failed: 'Échec',
            cancelled: 'Annulé',
            pending: 'En attente',
            ready: 'Prêt'
        }
    },
    
    // En-tête et navigation
    header: {
        appTitle: 'Gestionnaire LoRA',
        navigation: {
            loras: 'LoRA',
            recipes: 'Recettes',
            checkpoints: 'Points de contrôle',
            embeddings: 'Embeddings',
            statistics: 'Statistiques'
        },
        search: {
            placeholder: 'Rechercher...',
            placeholders: {
                loras: 'Rechercher des LoRA...',
                recipes: 'Rechercher des recettes...',
                checkpoints: 'Rechercher des points de contrôle...',
                embeddings: 'Rechercher des embeddings...'
            },
            options: 'Options de recherche',
            searchIn: 'Rechercher dans :',
            notAvailable: 'Recherche non disponible sur la page des statistiques',
            filters: {
                filename: 'Nom de fichier',
                modelname: 'Nom du modèle',
                tags: 'Tags',
                creator: 'Créateur',
                title: 'Titre de la recette',
                loraName: 'Nom du fichier LoRA',
                loraModel: 'Nom du modèle LoRA'
            }
        },
        filter: {
            title: 'Filtrer les modèles',
            baseModel: 'Modèle de base',
            modelTags: 'Tags (Top 20)',
            clearAll: 'Effacer tous les filtres'
        },
        theme: {
            toggle: 'Basculer le thème',
            switchToLight: 'Passer au thème clair',
            switchToDark: 'Passer au thème sombre',
            switchToAuto: 'Passer au thème automatique'
        }
    },
    
    // Page LoRA
    loras: {
        title: 'Modèles LoRA',
        controls: {
            sort: {
                title: 'Trier les modèles par...',
                name: 'Nom',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: 'Date d\'ajout',
                dateDesc: 'Plus récents',
                dateAsc: 'Plus anciens',
                size: 'Taille du fichier',
                sizeDesc: 'Plus grands',
                sizeAsc: 'Plus petits'
            },
            refresh: {
                title: 'Actualiser la liste des modèles',
                quick: 'Actualisation rapide (incrémentale)',
                full: 'Reconstruction complète (complète)'
            },
            fetch: 'Récupérer depuis Civitai',
            download: 'Télécharger depuis URL',
            bulk: 'Opérations en lot',
            duplicates: 'Trouver les doublons',
            favorites: 'Afficher seulement les favoris'
        },
        bulkOperations: {
            title: 'Opérations en lot',
            selected: '{count} sélectionné(s)',
            selectAll: 'Sélectionner tous sur la page courante',
            deselectAll: 'Désélectionner tous',
            actions: {
                move: 'Déplacer les éléments sélectionnés',
                delete: 'Supprimer les éléments sélectionnés',
                setRating: 'Définir la classification du contenu',
                export: 'Exporter les éléments sélectionnés'
            }
        },
        card: {
            actions: {
                copyTriggerWords: 'Copier les mots déclencheurs',
                copyLoraName: 'Copier le nom LoRA',
                sendToWorkflow: 'Envoyer au flux de travail',
                sendToWorkflowAppend: 'Envoyer au flux de travail (ajouter)',
                sendToWorkflowReplace: 'Envoyer au flux de travail (remplacer)',
                openExamples: 'Ouvrir le dossier d\'exemples',
                downloadExamples: 'Télécharger les images d\'exemple',
                replacePreview: 'Remplacer l\'aperçu',
                setContentRating: 'Définir la classification du contenu',
                moveToFolder: 'Déplacer vers le dossier',
                excludeModel: 'Exclure le modèle',
                deleteModel: 'Supprimer le modèle'
            },
            modal: {
                title: 'Détails LoRA',
                tabs: {
                    examples: 'Exemples',
                    description: 'Description du modèle',
                    recipes: 'Recettes'
                },
                info: {
                    filename: 'Nom de fichier',
                    modelName: 'Nom du modèle',
                    baseModel: 'Modèle de base',
                    fileSize: 'Taille du fichier',
                    dateAdded: 'Date d\'ajout',
                    triggerWords: 'Mots déclencheurs',
                    description: 'Description',
                    tags: 'Tags',
                    rating: 'Évaluation',
                    downloads: 'Téléchargements',
                    likes: 'J\'aime',
                    version: 'Version'
                },
                actions: {
                    copyTriggerWords: 'Copier les mots déclencheurs',
                    copyLoraName: 'Copier le nom LoRA',
                    sendToWorkflow: 'Envoyer au flux de travail',
                    viewOnCivitai: 'Voir sur Civitai',
                    downloadExamples: 'Télécharger les images d\'exemple'
                }
            }
        }
    },
    
    // Page recettes
    recipes: {
        title: 'Recettes LoRA',
        controls: {
            import: 'Importer une recette',
            create: 'Créer une recette',
            export: 'Exporter les éléments sélectionnés',
            downloadMissing: 'Télécharger les LoRA manquants'
        },
        card: {
            author: 'Auteur',
            loras: '{count} LoRA',
            tags: 'Tags',
            actions: {
                sendToWorkflow: 'Envoyer au flux de travail',
                edit: 'Modifier la recette',
                duplicate: 'Dupliquer la recette',
                export: 'Exporter la recette',
                delete: 'Supprimer la recette'
            }
        }
    },
    
    // Page points de contrôle
    checkpoints: {
        title: 'Modèles de points de contrôle',
        info: {
            filename: 'Nom de fichier',
            modelName: 'Nom du modèle',
            baseModel: 'Modèle de base',
            fileSize: 'Taille du fichier',
            dateAdded: 'Date d\'ajout'
        }
    },
    
    // Page embeddings
    embeddings: {
        title: 'Modèles d\'embedding',
        info: {
            filename: 'Nom de fichier',
            modelName: 'Nom du modèle',
            triggerWords: 'Mots déclencheurs',
            fileSize: 'Taille du fichier',
            dateAdded: 'Date d\'ajout'
        }
    },
    
    // Page statistiques
    statistics: {
        title: 'Statistiques',
        overview: {
            title: 'Aperçu',
            totalModels: 'Total des modèles',
            totalSize: 'Taille totale',
            avgFileSize: 'Taille moyenne des fichiers',
            newestModel: 'Modèle le plus récent'
        },
        charts: {
            modelsByBaseModel: 'Par modèle de base',
            modelsByMonth: 'Par mois',
            fileSizeDistribution: 'Distribution des tailles de fichier',
            topTags: 'Tags populaires'
        }
    },
    
    // Boîtes de dialogue modales
    modals: {
        delete: {
            title: 'Confirmer la suppression',
            message: 'Êtes-vous sûr de vouloir supprimer ce modèle ? Cette action ne peut pas être annulée.',
            confirm: 'Supprimer',
            cancel: 'Annuler'
        },
        exclude: {
            title: 'Exclure le modèle',
            message: 'Êtes-vous sûr de vouloir exclure ce modèle de la bibliothèque ?',
            confirm: 'Exclure',
            cancel: 'Annuler'
        },
        download: {
            title: 'Télécharger le modèle',
            url: 'URL du modèle',
            placeholder: 'Entrer l\'URL du modèle Civitai...',
            download: 'Télécharger',
            cancel: 'Annuler'
        },
        move: {
            title: 'Déplacer le modèle',
            selectFolder: 'Sélectionner le dossier de destination',
            createFolder: 'Créer un nouveau dossier',
            folderName: 'Nom du dossier',
            move: 'Déplacer',
            cancel: 'Annuler'
        },
        contentRating: {
            title: 'Définir la classification du contenu',
            current: 'Actuel',
            levels: {
                pg: 'Tout public',
                pg13: '13 ans et plus',
                r: 'Restreint',
                x: 'Adulte',
                xxx: 'Explicite'
            }
        }
    },
    
    // Messages d'erreur
    errors: {
        general: 'Une erreur s\'est produite',
        networkError: 'Erreur réseau. Vérifiez votre connexion.',
        serverError: 'Erreur serveur. Veuillez réessayer plus tard.',
        fileNotFound: 'Fichier non trouvé',
        invalidFile: 'Format de fichier invalide',
        uploadFailed: 'Échec de l\'import',
        downloadFailed: 'Échec du téléchargement',
        saveFailed: 'Échec de l\'enregistrement',
        loadFailed: 'Échec du chargement',
        deleteFailed: 'Échec de la suppression',
        moveFailed: 'Échec du déplacement',
        copyFailed: 'Échec de la copie',
        fetchFailed: 'Impossible de récupérer les données de Civitai',
        invalidUrl: 'Format d\'URL invalide',
        missingPermissions: 'Permissions insuffisantes'
    },
    
    // Messages de succès
    success: {
        saved: 'Enregistré avec succès',
        deleted: 'Supprimé avec succès',
        moved: 'Déplacé avec succès',
        copied: 'Copié avec succès',
        downloaded: 'Téléchargé avec succès',
        uploaded: 'Importé avec succès',
        refreshed: 'Actualisé avec succès',
        exported: 'Exporté avec succès',
        imported: 'Importé avec succès'
    },
    
    // Raccourcis clavier
    keyboard: {
        navigation: 'Navigation au clavier :',
        shortcuts: {
            pageUp: 'Défiler d\'une page vers le haut',
            pageDown: 'Défiler d\'une page vers le bas',
            home: 'Aller au début',
            end: 'Aller à la fin',
            bulkMode: 'Basculer le mode lot',
            search: 'Focus sur la recherche',
            escape: 'Fermer modal/panneau'
        }
    },
    
    // Initialisation
    initialization: {
        title: 'Initialisation du gestionnaire LoRA',
        message: 'Analyse et construction du cache LoRA. Cela peut prendre quelques minutes...',
        steps: {
            scanning: 'Analyse des fichiers de modèles...',
            processing: 'Traitement des métadonnées...',
            building: 'Construction du cache...',
            finalizing: 'Finalisation...'
        }
    },
    
    // Infobulles et texte d'aide
    tooltips: {
        refresh: 'Actualiser la liste des modèles',
        bulkOperations: 'Sélectionner plusieurs modèles pour des opérations par lot',
        favorites: 'Afficher seulement les modèles favoris',
        duplicates: 'Trouver et gérer les modèles en double',
        search: 'Rechercher des modèles par nom, tags ou autres critères',
        filter: 'Filtrer les modèles selon divers critères',
        sort: 'Trier les modèles selon différents attributs',
        backToTop: 'Revenir en haut de la page'
    }
};
