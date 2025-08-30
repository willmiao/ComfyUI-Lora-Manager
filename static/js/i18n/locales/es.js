/**
 * Spanish (es) translations for LoRA Manager
 */
export const es = {
    // Términos comunes utilizados en la aplicación
    common: {
        // Operaciones de archivos
        file: 'Archivo',
        folder: 'Carpeta',
        name: 'Nombre',
        size: 'Tamaño',
        date: 'Fecha',
        type: 'Tipo',
        path: 'Ruta',
        
        // Tamaños de archivo
        fileSize: {
            zero: '0 Bytes',
            bytes: 'Bytes',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // Acciones
        actions: {
            save: 'Guardar',
            cancel: 'Cancelar',
            delete: 'Eliminar',
            edit: 'Editar',
            copy: 'Copiar',
            move: 'Mover',
            refresh: 'Actualizar',
            download: 'Descargar',
            upload: 'Subir',
            search: 'Buscar',
            filter: 'Filtrar',
            sort: 'Ordenar',
            select: 'Seleccionar',
            selectAll: 'Seleccionar todo',
            deselectAll: 'Deseleccionar todo',
            confirm: 'Confirmar',
            close: 'Cerrar',
            back: 'Atrás',
            next: 'Siguiente',
            previous: 'Anterior',
            view: 'Ver',
            preview: 'Vista previa',
            details: 'Detalles',
            settings: 'Configuración',
            help: 'Ayuda',
            about: 'Acerca de'
        },
        
        // Configuración de idioma
        language: {
            current: 'Idioma',
            select: 'Seleccionar idioma',
            select_help: 'Elija su idioma de interfaz preferido',
            english: 'Inglés',
            chinese_simplified: 'Chino (simplificado)',
            chinese_traditional: 'Chino (tradicional)',
            russian: 'Ruso',
            german: 'Alemán',
            japanese: 'Japonés',
            korean: 'Coreano',
            french: 'Francés',
            spanish: 'Español'
        },
        
        // Mensajes de estado
        status: {
            loading: 'Cargando...',
            saving: 'Guardando...',
            saved: 'Guardado',
            error: 'Error',
            success: 'Éxito',
            warning: 'Advertencia',
            info: 'Información',
            processing: 'Procesando...',
            completed: 'Completado',
            failed: 'Falló',
            cancelled: 'Cancelado',
            pending: 'Pendiente',
            ready: 'Listo'
        }
    },
    
    // Encabezado y navegación
    header: {
        appTitle: 'Gestor LoRA',
        navigation: {
            loras: 'LoRA',
            recipes: 'Recetas',
            checkpoints: 'Puntos de control',
            embeddings: 'Embeddings',
            statistics: 'Estadísticas'
        },
        search: {
            placeholder: 'Buscar...',
            placeholders: {
                loras: 'Buscar LoRA...',
                recipes: 'Buscar recetas...',
                checkpoints: 'Buscar puntos de control...',
                embeddings: 'Buscar embeddings...'
            },
            options: 'Opciones de búsqueda',
            searchIn: 'Buscar en:',
            notAvailable: 'Búsqueda no disponible en la página de estadísticas',
            filters: {
                filename: 'Nombre del archivo',
                modelname: 'Nombre del modelo',
                tags: 'Etiquetas',
                creator: 'Creador',
                title: 'Título de la receta',
                loraName: 'Nombre del archivo LoRA',
                loraModel: 'Nombre del modelo LoRA'
            }
        },
        filter: {
            title: 'Filtrar modelos',
            baseModel: 'Modelo base',
            modelTags: 'Etiquetas (Top 20)',
            clearAll: 'Limpiar todos los filtros'
        },
        theme: {
            toggle: 'Cambiar tema',
            switchToLight: 'Cambiar a tema claro',
            switchToDark: 'Cambiar a tema oscuro',
            switchToAuto: 'Cambiar a tema automático'
        }
    },
    
    // Página LoRA
    loras: {
        title: 'Modelos LoRA',
        controls: {
            sort: {
                title: 'Ordenar modelos por...',
                name: 'Nombre',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: 'Fecha de agregado',
                dateDesc: 'Más recientes',
                dateAsc: 'Más antiguos',
                size: 'Tamaño del archivo',
                sizeDesc: 'Más grandes',
                sizeAsc: 'Más pequeños'
            },
            refresh: {
                title: 'Actualizar lista de modelos',
                quick: 'Actualización rápida (incremental)',
                full: 'Reconstrucción completa (completa)'
            },
            fetch: 'Obtener desde Civitai',
            download: 'Descargar desde URL',
            bulk: 'Operaciones en lote',
            duplicates: 'Encontrar duplicados',
            favorites: 'Mostrar solo favoritos'
        },
        bulkOperations: {
            title: 'Operaciones en lote',
            selected: '{count} seleccionado(s)',
            selectAll: 'Seleccionar todos en la página actual',
            deselectAll: 'Deseleccionar todos',
            actions: {
                move: 'Mover elementos seleccionados',
                delete: 'Eliminar elementos seleccionados',
                setRating: 'Establecer clasificación de contenido',
                export: 'Exportar elementos seleccionados'
            }
        },
        card: {
            actions: {
                copyTriggerWords: 'Copiar palabras clave',
                copyLoraName: 'Copiar nombre LoRA',
                sendToWorkflow: 'Enviar al flujo de trabajo',
                sendToWorkflowAppend: 'Enviar al flujo de trabajo (agregar)',
                sendToWorkflowReplace: 'Enviar al flujo de trabajo (reemplazar)',
                openExamples: 'Abrir carpeta de ejemplos',
                downloadExamples: 'Descargar imágenes de ejemplo',
                replacePreview: 'Reemplazar vista previa',
                setContentRating: 'Establecer clasificación de contenido',
                moveToFolder: 'Mover a carpeta',
                excludeModel: 'Excluir modelo',
                deleteModel: 'Eliminar modelo'
            },
            modal: {
                title: 'Detalles LoRA',
                tabs: {
                    examples: 'Ejemplos',
                    description: 'Descripción del modelo',
                    recipes: 'Recetas'
                },
                info: {
                    filename: 'Nombre del archivo',
                    modelName: 'Nombre del modelo',
                    baseModel: 'Modelo base',
                    fileSize: 'Tamaño del archivo',
                    dateAdded: 'Fecha de agregado',
                    triggerWords: 'Palabras clave',
                    description: 'Descripción',
                    tags: 'Etiquetas',
                    rating: 'Calificación',
                    downloads: 'Descargas',
                    likes: 'Me gusta',
                    version: 'Versión'
                },
                actions: {
                    copyTriggerWords: 'Copiar palabras clave',
                    copyLoraName: 'Copiar nombre LoRA',
                    sendToWorkflow: 'Enviar al flujo de trabajo',
                    viewOnCivitai: 'Ver en Civitai',
                    downloadExamples: 'Descargar imágenes de ejemplo'
                }
            }
        }
    },
    
    // Página de recetas
    recipes: {
        title: 'Recetas LoRA',
        controls: {
            import: 'Importar receta',
            create: 'Crear receta',
            export: 'Exportar elementos seleccionados',
            downloadMissing: 'Descargar LoRA faltantes'
        },
        card: {
            author: 'Autor',
            loras: '{count} LoRA',
            tags: 'Etiquetas',
            actions: {
                sendToWorkflow: 'Enviar al flujo de trabajo',
                edit: 'Editar receta',
                duplicate: 'Duplicar receta',
                export: 'Exportar receta',
                delete: 'Eliminar receta'
            }
        }
    },
    
    // Página de puntos de control
    checkpoints: {
        title: 'Modelos de puntos de control',
        info: {
            filename: 'Nombre del archivo',
            modelName: 'Nombre del modelo',
            baseModel: 'Modelo base',
            fileSize: 'Tamaño del archivo',
            dateAdded: 'Fecha de agregado'
        }
    },
    
    // Página de embeddings
    embeddings: {
        title: 'Modelos de embedding',
        info: {
            filename: 'Nombre del archivo',
            modelName: 'Nombre del modelo',
            triggerWords: 'Palabras clave',
            fileSize: 'Tamaño del archivo',
            dateAdded: 'Fecha de agregado'
        }
    },
    
    // Página de estadísticas
    statistics: {
        title: 'Estadísticas',
        overview: {
            title: 'Resumen',
            totalModels: 'Total de modelos',
            totalSize: 'Tamaño total',
            avgFileSize: 'Tamaño promedio de archivo',
            newestModel: 'Modelo más reciente'
        },
        charts: {
            modelsByBaseModel: 'Por modelo base',
            modelsByMonth: 'Por mes',
            fileSizeDistribution: 'Distribución de tamaños de archivo',
            topTags: 'Etiquetas populares'
        }
    },
    
    // Diálogos modales
    modals: {
        delete: {
            title: 'Confirmar eliminación',
            message: '¿Estás seguro de que quieres eliminar este modelo? Esta acción no se puede deshacer.',
            confirm: 'Eliminar',
            cancel: 'Cancelar'
        },
        exclude: {
            title: 'Excluir modelo',
            message: '¿Estás seguro de que quieres excluir este modelo de la biblioteca?',
            confirm: 'Excluir',
            cancel: 'Cancelar'
        },
        download: {
            title: 'Descargar modelo',
            url: 'URL del modelo',
            placeholder: 'Ingresa la URL del modelo de Civitai...',
            download: 'Descargar',
            cancel: 'Cancelar'
        },
        move: {
            title: 'Mover modelo',
            selectFolder: 'Seleccionar carpeta de destino',
            createFolder: 'Crear nueva carpeta',
            folderName: 'Nombre de la carpeta',
            move: 'Mover',
            cancel: 'Cancelar'
        },
        contentRating: {
            title: 'Establecer clasificación de contenido',
            current: 'Actual',
            levels: {
                pg: 'Apto para todos',
                pg13: '13 años y más',
                r: 'Restringido',
                x: 'Adultos',
                xxx: 'Explícito'
            }
        }
    },
    
    // Mensajes de error
    errors: {
        general: 'Ocurrió un error',
        networkError: 'Error de red. Verifica tu conexión.',
        serverError: 'Error del servidor. Inténtalo de nuevo más tarde.',
        fileNotFound: 'Archivo no encontrado',
        invalidFile: 'Formato de archivo inválido',
        uploadFailed: 'Falló la subida',
        downloadFailed: 'Falló la descarga',
        saveFailed: 'Falló el guardado',
        loadFailed: 'Falló la carga',
        deleteFailed: 'Falló la eliminación',
        moveFailed: 'Falló el movimiento',
        copyFailed: 'Falló la copia',
        fetchFailed: 'No se pudieron obtener datos de Civitai',
        invalidUrl: 'Formato de URL inválido',
        missingPermissions: 'Permisos insuficientes'
    },
    
    // Mensajes de éxito
    success: {
        saved: 'Guardado exitosamente',
        deleted: 'Eliminado exitosamente',
        moved: 'Movido exitosamente',
        copied: 'Copiado exitosamente',
        downloaded: 'Descargado exitosamente',
        uploaded: 'Subido exitosamente',
        refreshed: 'Actualizado exitosamente',
        exported: 'Exportado exitosamente',
        imported: 'Importado exitosamente'
    },
    
    // Atajos de teclado
    keyboard: {
        navigation: 'Navegación por teclado:',
        shortcuts: {
            pageUp: 'Desplazar hacia arriba una página',
            pageDown: 'Desplazar hacia abajo una página',
            home: 'Ir al inicio',
            end: 'Ir al final',
            bulkMode: 'Cambiar modo de lote',
            search: 'Enfocar búsqueda',
            escape: 'Cerrar modal/panel'
        }
    },
    
    // Inicialización
    initialization: {
        title: 'Inicializando Gestor LoRA',
        message: 'Escaneando y construyendo caché LoRA. Esto puede tomar algunos minutos...',
        steps: {
            scanning: 'Escaneando archivos de modelos...',
            processing: 'Procesando metadatos...',
            building: 'Construyendo caché...',
            finalizing: 'Finalizando...'
        }
    },
    
    // Tooltips y texto de ayuda
    tooltips: {
        refresh: 'Actualizar la lista de modelos',
        bulkOperations: 'Seleccionar múltiples modelos para operaciones por lotes',
        favorites: 'Mostrar solo modelos favoritos',
        duplicates: 'Encontrar y gestionar modelos duplicados',
        search: 'Buscar modelos por nombre, etiquetas u otros criterios',
        filter: 'Filtrar modelos por varios criterios',
        sort: 'Ordenar modelos por diferentes atributos',
        backToTop: 'Volver al inicio de la página'
    }
};
