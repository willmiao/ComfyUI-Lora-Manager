/**
 * German (de) translations for LoRA Manager
 */
export const de = {
    // Allgemeine Begriffe in der Anwendung
    common: {
        // Dateioperationen
        file: 'Datei',
        folder: 'Ordner',
        name: 'Name',
        size: 'Größe',
        date: 'Datum',
        type: 'Typ',
        path: 'Pfad',
        
        // Dateigrößen
        fileSize: {
            zero: '0 Bytes',
            bytes: 'Bytes',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // Aktionen
        actions: {
            save: 'Speichern',
            cancel: 'Abbrechen',
            delete: 'Löschen',
            edit: 'Bearbeiten',
            copy: 'Kopieren',
            move: 'Verschieben',
            refresh: 'Aktualisieren',
            download: 'Herunterladen',
            upload: 'Hochladen',
            search: 'Suchen',
            filter: 'Filter',
            sort: 'Sortieren',
            select: 'Auswählen',
            selectAll: 'Alle auswählen',
            deselectAll: 'Auswahl aufheben',
            confirm: 'Bestätigen',
            close: 'Schließen',
            back: 'Zurück',
            next: 'Weiter',
            previous: 'Vorherige',
            view: 'Anzeigen',
            preview: 'Vorschau',
            details: 'Details',
            settings: 'Einstellungen',
            help: 'Hilfe',
            about: 'Über'
        },
        
        // Spracheinstellungen
        language: {
            current: 'Sprache',
            select: 'Sprache auswählen',
            select_help: 'Wählen Sie Ihre bevorzugte Oberflächensprache',
            english: 'Englisch',
            chinese_simplified: 'Chinesisch (vereinfacht)',
            chinese_traditional: 'Chinesisch (traditionell)',
            russian: 'Russisch',
            german: 'Deutsch',
            japanese: 'Japanisch',
            korean: 'Koreanisch',
            french: 'Französisch',
            spanish: 'Spanisch'
        },
        
        // Statusmeldungen
        status: {
            loading: 'Lädt...',
            saving: 'Speichere...',
            saved: 'Gespeichert',
            error: 'Fehler',
            success: 'Erfolgreich',
            warning: 'Warnung',
            info: 'Information',
            processing: 'Verarbeite...',
            completed: 'Abgeschlossen',
            failed: 'Fehlgeschlagen',
            cancelled: 'Abgebrochen',
            pending: 'Wartend',
            ready: 'Bereit'
        }
    },
    
    // Kopfzeile und Navigation
    header: {
        appTitle: 'LoRA Manager',
        navigation: {
            loras: 'LoRAs',
            recipes: 'Rezepte',
            checkpoints: 'Checkpoints',
            embeddings: 'Embeddings',
            statistics: 'Statistiken'
        },
        search: {
            placeholder: 'Suchen...',
            placeholders: {
                loras: 'LoRAs suchen...',
                recipes: 'Rezepte suchen...',
                checkpoints: 'Checkpoints suchen...',
                embeddings: 'Embeddings suchen...'
            },
            options: 'Suchoptionen',
            searchIn: 'Suchen in:',
            notAvailable: 'Suche nicht verfügbar auf der Statistikseite',
            filters: {
                filename: 'Dateiname',
                modelname: 'Modellname',
                tags: 'Tags',
                creator: 'Ersteller',
                title: 'Rezepttitel',
                loraName: 'LoRA Dateiname',
                loraModel: 'LoRA Modellname'
            }
        },
        filter: {
            title: 'Modelle filtern',
            baseModel: 'Basismodell',
            modelTags: 'Tags (Top 20)',
            clearAll: 'Alle Filter löschen'
        },
        theme: {
            toggle: 'Design wechseln',
            switchToLight: 'Zu hellem Design wechseln',
            switchToDark: 'Zu dunklem Design wechseln',
            switchToAuto: 'Zu automatischem Design wechseln'
        }
    },
    
    // LoRA Seite
    loras: {
        title: 'LoRA Modelle',
        controls: {
            sort: {
                title: 'Modelle sortieren nach...',
                name: 'Name',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: 'Hinzufügungsdatum',
                dateDesc: 'Neueste',
                dateAsc: 'Älteste',
                size: 'Dateigröße',
                sizeDesc: 'Größte',
                sizeAsc: 'Kleinste'
            },
            refresh: {
                title: 'Modellliste aktualisieren',
                quick: 'Schnelle Aktualisierung (inkrementell)',
                full: 'Vollständiger Neuaufbau (komplett)'
            },
            fetch: 'Von Civitai abrufen',
            download: 'Von URL herunterladen',
            bulk: 'Massenoperationen',
            duplicates: 'Duplikate finden',
            favorites: 'Nur Favoriten anzeigen'
        },
        bulkOperations: {
            title: 'Massenoperationen',
            selected: '{count} ausgewählt',
            selectAll: 'Alle auf aktueller Seite auswählen',
            deselectAll: 'Alle abwählen',
            actions: {
                move: 'Ausgewählte verschieben',
                delete: 'Ausgewählte löschen',
                setRating: 'Inhaltsbewertung festlegen',
                export: 'Ausgewählte exportieren'
            }
        },
        card: {
            actions: {
                copyTriggerWords: 'Trigger-Wörter kopieren',
                copyLoraName: 'LoRA-Namen kopieren',
                sendToWorkflow: 'An Workflow senden',
                sendToWorkflowAppend: 'An Workflow senden (anhängen)',
                sendToWorkflowReplace: 'An Workflow senden (ersetzen)',
                openExamples: 'Beispielordner öffnen',
                downloadExamples: 'Beispielbilder herunterladen',
                replacePreview: 'Vorschau ersetzen',
                setContentRating: 'Inhaltsbewertung festlegen',
                moveToFolder: 'In Ordner verschieben',
                excludeModel: 'Modell ausschließen',
                deleteModel: 'Modell löschen'
            },
            modal: {
                title: 'LoRA Details',
                tabs: {
                    examples: 'Beispiele',
                    description: 'Modellbeschreibung',
                    recipes: 'Rezepte'
                },
                info: {
                    filename: 'Dateiname',
                    modelName: 'Modellname',
                    baseModel: 'Basismodell',
                    fileSize: 'Dateigröße',
                    dateAdded: 'Hinzufügungsdatum',
                    triggerWords: 'Trigger-Wörter',
                    description: 'Beschreibung',
                    tags: 'Tags',
                    rating: 'Bewertung',
                    downloads: 'Downloads',
                    likes: 'Gefällt mir',
                    version: 'Version'
                },
                actions: {
                    copyTriggerWords: 'Trigger-Wörter kopieren',
                    copyLoraName: 'LoRA-Namen kopieren',
                    sendToWorkflow: 'An Workflow senden',
                    viewOnCivitai: 'Auf Civitai anzeigen',
                    downloadExamples: 'Beispielbilder herunterladen'
                }
            }
        }
    },
    
    // Rezepte Seite
    recipes: {
        title: 'LoRA Rezepte',
        controls: {
            import: 'Rezept importieren',
            create: 'Rezept erstellen',
            export: 'Ausgewählte exportieren',
            downloadMissing: 'Fehlende LoRAs herunterladen'
        },
        card: {
            author: 'Autor',
            loras: '{count} LoRAs',
            tags: 'Tags',
            actions: {
                sendToWorkflow: 'An Workflow senden',
                edit: 'Rezept bearbeiten',
                duplicate: 'Rezept duplizieren',
                export: 'Rezept exportieren',
                delete: 'Rezept löschen'
            }
        }
    },
    
    // Checkpoint Seite
    checkpoints: {
        title: 'Checkpoint Modelle',
        info: {
            filename: 'Dateiname',
            modelName: 'Modellname',
            baseModel: 'Basismodell',
            fileSize: 'Dateigröße',
            dateAdded: 'Hinzufügungsdatum'
        }
    },
    
    // Embeddings Seite
    embeddings: {
        title: 'Embedding Modelle',
        info: {
            filename: 'Dateiname',
            modelName: 'Modellname',
            triggerWords: 'Trigger-Wörter',
            fileSize: 'Dateigröße',
            dateAdded: 'Hinzufügungsdatum'
        }
    },
    
    // Statistik Seite
    statistics: {
        title: 'Statistiken',
        overview: {
            title: 'Übersicht',
            totalModels: 'Gesamte Modelle',
            totalSize: 'Gesamtgröße',
            avgFileSize: 'Durchschnittliche Dateigröße',
            newestModel: 'Neuestes Modell'
        },
        charts: {
            modelsByBaseModel: 'Nach Basismodell',
            modelsByMonth: 'Nach Monat',
            fileSizeDistribution: 'Dateigrößenverteilung',
            topTags: 'Beliebte Tags'
        }
    },
    
    // Modale Dialoge
    modals: {
        delete: {
            title: 'Löschen bestätigen',
            message: 'Sind Sie sicher, dass Sie dieses Modell löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.',
            confirm: 'Löschen',
            cancel: 'Abbrechen'
        },
        exclude: {
            title: 'Modell ausschließen',
            message: 'Sind Sie sicher, dass Sie dieses Modell aus der Bibliothek ausschließen möchten?',
            confirm: 'Ausschließen',
            cancel: 'Abbrechen'
        },
        download: {
            title: 'Modell herunterladen',
            url: 'Modell URL',
            placeholder: 'Civitai Modell URL eingeben...',
            download: 'Herunterladen',
            cancel: 'Abbrechen'
        },
        move: {
            title: 'Modell verschieben',
            selectFolder: 'Zielordner auswählen',
            createFolder: 'Neuen Ordner erstellen',
            folderName: 'Ordnername',
            move: 'Verschieben',
            cancel: 'Abbrechen'
        },
        contentRating: {
            title: 'Inhaltsbewertung festlegen',
            current: 'Aktuell',
            levels: {
                pg: 'Allgemein',
                pg13: 'Ab 13',
                r: 'Eingeschränkt',
                x: 'Erwachsene',
                xxx: 'Explizit'
            }
        }
    },
    
    // Fehlermeldungen
    errors: {
        general: 'Ein Fehler ist aufgetreten',
        networkError: 'Netzwerkfehler. Überprüfen Sie Ihre Verbindung.',
        serverError: 'Serverfehler. Versuchen Sie es später erneut.',
        fileNotFound: 'Datei nicht gefunden',
        invalidFile: 'Ungültiges Dateiformat',
        uploadFailed: 'Upload fehlgeschlagen',
        downloadFailed: 'Download fehlgeschlagen',
        saveFailed: 'Speichern fehlgeschlagen',
        loadFailed: 'Laden fehlgeschlagen',
        deleteFailed: 'Löschen fehlgeschlagen',
        moveFailed: 'Verschieben fehlgeschlagen',
        copyFailed: 'Kopieren fehlgeschlagen',
        fetchFailed: 'Daten von Civitai konnten nicht abgerufen werden',
        invalidUrl: 'Ungültiges URL-Format',
        missingPermissions: 'Unzureichende Berechtigungen'
    },
    
    // Erfolgsmeldungen
    success: {
        saved: 'Erfolgreich gespeichert',
        deleted: 'Erfolgreich gelöscht',
        moved: 'Erfolgreich verschoben',
        copied: 'Erfolgreich kopiert',
        downloaded: 'Erfolgreich heruntergeladen',
        uploaded: 'Erfolgreich hochgeladen',
        refreshed: 'Erfolgreich aktualisiert',
        exported: 'Erfolgreich exportiert',
        imported: 'Erfolgreich importiert'
    },
    
    // Tastaturkürzel
    keyboard: {
        navigation: 'Tastaturnavigation:',
        shortcuts: {
            pageUp: 'Eine Seite nach oben scrollen',
            pageDown: 'Eine Seite nach unten scrollen',
            home: 'Zum Anfang springen',
            end: 'Zum Ende springen',
            bulkMode: 'Massenmodus umschalten',
            search: 'Suche fokussieren',
            escape: 'Modal/Panel schließen'
        }
    },
    
    // Initialisierung
    initialization: {
        title: 'LoRA Manager initialisieren',
        message: 'Scannen und Aufbau des LoRA-Caches. Dies kann einige Minuten dauern...',
        steps: {
            scanning: 'Modelldateien scannen...',
            processing: 'Metadaten verarbeiten...',
            building: 'Cache aufbauen...',
            finalizing: 'Abschließen...'
        }
    },
    
    // Tooltips und Hilfetext
    tooltips: {
        refresh: 'Modellliste aktualisieren',
        bulkOperations: 'Mehrere Modelle für Batch-Operationen auswählen',
        favorites: 'Nur Lieblingsmodelle anzeigen',
        duplicates: 'Doppelte Modelle finden und verwalten',
        search: 'Modelle nach Name, Tags oder anderen Kriterien suchen',
        filter: 'Modelle nach verschiedenen Kriterien filtern',
        sort: 'Modelle nach verschiedenen Attributen sortieren',
        backToTop: 'Zurück zum Seitenanfang scrollen'
    }
};
