/**
 * Russian (ru) translations for LoRA Manager
 */
export const ru = {
    // Общие термины, используемые в приложении
    common: {
        // Операции с файлами
        file: 'Файл',
        folder: 'Папка',
        name: 'Имя',
        size: 'Размер',
        date: 'Дата',
        type: 'Тип',
        path: 'Путь',
        
        // Размеры файлов
        fileSize: {
            zero: '0 Байт',
            bytes: 'Байт',
            kb: 'КБ',
            mb: 'МБ',
            gb: 'ГБ',
            tb: 'ТБ'
        },
        
        // Действия
        actions: {
            save: 'Сохранить',
            cancel: 'Отмена',
            delete: 'Удалить',
            edit: 'Редактировать',
            copy: 'Копировать',
            move: 'Переместить',
            refresh: 'Обновить',
            download: 'Скачать',
            upload: 'Загрузить',
            search: 'Поиск',
            filter: 'Фильтр',
            sort: 'Сортировка',
            select: 'Выбрать',
            selectAll: 'Выбрать все',
            deselectAll: 'Отменить выбор',
            confirm: 'Подтвердить',
            close: 'Закрыть',
            back: 'Назад',
            next: 'Далее',
            previous: 'Предыдущий',
            view: 'Просмотр',
            preview: 'Предпросмотр',
            details: 'Детали',
            settings: 'Настройки',
            help: 'Помощь',
            about: 'О программе'
        },
        
        // Настройки языка
        language: {
            current: 'Язык',
            select: 'Выберите язык',
            select_help: 'Выберите предпочитаемый язык интерфейса',
            english: 'Английский',
            chinese_simplified: 'Китайский (упрощенный)',
            chinese_traditional: 'Китайский (традиционный)',
            russian: 'Русский',
            german: 'Немецкий',
            japanese: 'Японский',
            korean: 'Корейский',
            french: 'Французский',
            spanish: 'Испанский'
        },
        
        // Сообщения о состоянии
        status: {
            loading: 'Загрузка...',
            saving: 'Сохранение...',
            saved: 'Сохранено',
            error: 'Ошибка',
            success: 'Успешно',
            warning: 'Предупреждение',
            info: 'Информация',
            processing: 'Обработка...',
            completed: 'Завершено',
            failed: 'Не удалось',
            cancelled: 'Отменено',
            pending: 'Ожидание',
            ready: 'Готово'
        }
    },
    
    // Заголовок и навигация
    header: {
        appTitle: 'LoRA Менеджер',
        navigation: {
            loras: 'LoRA',
            recipes: 'Рецепты',
            checkpoints: 'Чекпоинты',
            embeddings: 'Эмбеддинги',
            statistics: 'Статистика'
        },
        search: {
            placeholder: 'Поиск...',
            placeholders: {
                loras: 'Поиск LoRA...',
                recipes: 'Поиск рецептов...',
                checkpoints: 'Поиск чекпоинтов...',
                embeddings: 'Поиск эмбеддингов...'
            },
            options: 'Опции поиска',
            searchIn: 'Искать в:',
            notAvailable: 'Поиск недоступен на странице статистики',
            filters: {
                filename: 'Имя файла',
                modelname: 'Имя модели',
                tags: 'Теги',
                creator: 'Создатель',
                title: 'Название рецепта',
                loraName: 'Имя файла LoRA',
                loraModel: 'Имя модели LoRA'
            }
        },
        filter: {
            title: 'Фильтр моделей',
            baseModel: 'Базовая модель',
            modelTags: 'Теги (топ 20)',
            clearAll: 'Очистить все фильтры'
        },
        theme: {
            toggle: 'Переключить тему',
            switchToLight: 'Переключить на светлую тему',
            switchToDark: 'Переключить на тёмную тему',
            switchToAuto: 'Переключить на автоматическую тему'
        }
    },
    
    // Страница LoRA
    loras: {
        title: 'LoRA Модели',
        controls: {
            sort: {
                title: 'Сортировать модели по...',
                name: 'Имя',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: 'Дата добавления',
                dateDesc: 'Новые',
                dateAsc: 'Старые',
                size: 'Размер файла',
                sizeDesc: 'Большие',
                sizeAsc: 'Маленькие'
            },
            refresh: {
                title: 'Обновить список моделей',
                quick: 'Быстрое обновление (инкрементальное)',
                full: 'Полная перестройка (полная)'
            },
            fetch: 'Получить с Civitai',
            download: 'Скачать по URL',
            bulk: 'Массовые операции',
            duplicates: 'Найти дубликаты',
            favorites: 'Показать только избранные'
        },
        bulkOperations: {
            title: 'Массовые операции',
            selected: 'Выбрано {count}',
            selectAll: 'Выбрать все на текущей странице',
            deselectAll: 'Отменить выбор всех',
            actions: {
                move: 'Переместить выбранные',
                delete: 'Удалить выбранные',
                setRating: 'Установить рейтинг контента',
                export: 'Экспортировать выбранные'
            }
        },
        card: {
            actions: {
                copyTriggerWords: 'Копировать триггерные слова',
                copyLoraName: 'Копировать имя LoRA',
                sendToWorkflow: 'Отправить в рабочий процесс',
                sendToWorkflowAppend: 'Отправить в рабочий процесс (добавить)',
                sendToWorkflowReplace: 'Отправить в рабочий процесс (заменить)',
                openExamples: 'Открыть папку с примерами',
                downloadExamples: 'Скачать примеры изображений',
                replacePreview: 'Заменить превью',
                setContentRating: 'Установить рейтинг контента',
                moveToFolder: 'Переместить в папку',
                excludeModel: 'Исключить модель',
                deleteModel: 'Удалить модель'
            },
            modal: {
                title: 'Детали LoRA',
                tabs: {
                    examples: 'Примеры',
                    description: 'Описание модели',
                    recipes: 'Рецепты'
                },
                info: {
                    filename: 'Имя файла',
                    modelName: 'Имя модели',
                    baseModel: 'Базовая модель',
                    fileSize: 'Размер файла',
                    dateAdded: 'Дата добавления',
                    triggerWords: 'Триггерные слова',
                    description: 'Описание',
                    tags: 'Теги',
                    rating: 'Рейтинг',
                    downloads: 'Скачивания',
                    likes: 'Лайки',
                    version: 'Версия'
                },
                actions: {
                    copyTriggerWords: 'Копировать триггерные слова',
                    copyLoraName: 'Копировать имя LoRA',
                    sendToWorkflow: 'Отправить в рабочий процесс',
                    viewOnCivitai: 'Просмотреть на Civitai',
                    downloadExamples: 'Скачать примеры изображений'
                }
            }
        }
    },
    
    // Страница рецептов
    recipes: {
        title: 'LoRA Рецепты',
        controls: {
            import: 'Импортировать рецепт',
            create: 'Создать рецепт',
            export: 'Экспортировать выбранные',
            downloadMissing: 'Скачать отсутствующие LoRA'
        },
        card: {
            author: 'Автор',
            loras: '{count} LoRA',
            tags: 'Теги',
            actions: {
                sendToWorkflow: 'Отправить в рабочий процесс',
                edit: 'Редактировать рецепт',
                duplicate: 'Дублировать рецепт',
                export: 'Экспортировать рецепт',
                delete: 'Удалить рецепт'
            }
        }
    },
    
    // Страница чекпоинтов
    checkpoints: {
        title: 'Чекпоинты',
        info: {
            filename: 'Имя файла',
            modelName: 'Имя модели',
            baseModel: 'Базовая модель',
            fileSize: 'Размер файла',
            dateAdded: 'Дата добавления'
        }
    },
    
    // Страница эмбеддингов
    embeddings: {
        title: 'Эмбеддинги',
        info: {
            filename: 'Имя файла',
            modelName: 'Имя модели',
            triggerWords: 'Триггерные слова',
            fileSize: 'Размер файла',
            dateAdded: 'Дата добавления'
        }
    },
    
    // Страница статистики
    statistics: {
        title: 'Статистика',
        overview: {
            title: 'Обзор',
            totalModels: 'Всего моделей',
            totalSize: 'Общий размер',
            avgFileSize: 'Средний размер файла',
            newestModel: 'Новейшая модель'
        },
        charts: {
            modelsByBaseModel: 'По базовым моделям',
            modelsByMonth: 'По месяцам',
            fileSizeDistribution: 'Распределение размеров файлов',
            topTags: 'Популярные теги'
        }
    },
    
    // Модальные окна
    modals: {
        delete: {
            title: 'Подтвердить удаление',
            message: 'Вы уверены, что хотите удалить эту модель? Это действие нельзя отменить.',
            confirm: 'Удалить',
            cancel: 'Отмена'
        },
        exclude: {
            title: 'Исключить модель',
            message: 'Вы уверены, что хотите исключить эту модель из библиотеки?',
            confirm: 'Исключить',
            cancel: 'Отмена'
        },
        download: {
            title: 'Скачать модель',
            url: 'URL модели',
            placeholder: 'Введите URL модели Civitai...',
            download: 'Скачать',
            cancel: 'Отмена'
        },
        move: {
            title: 'Переместить модель',
            selectFolder: 'Выберите папку назначения',
            createFolder: 'Создать новую папку',
            folderName: 'Имя папки',
            move: 'Переместить',
            cancel: 'Отмена'
        },
        contentRating: {
            title: 'Установить рейтинг контента',
            current: 'Текущий',
            levels: {
                pg: 'Для всех',
                pg13: 'С 13 лет',
                r: 'Ограниченный',
                x: 'Для взрослых',
                xxx: 'Эротический'
            }
        }
    },
    
    // Сообщения об ошибках
    errors: {
        general: 'Произошла ошибка',
        networkError: 'Ошибка сети. Проверьте подключение.',
        serverError: 'Ошибка сервера. Попробуйте позже.',
        fileNotFound: 'Файл не найден',
        invalidFile: 'Неверный формат файла',
        uploadFailed: 'Загрузка не удалась',
        downloadFailed: 'Скачивание не удалось',
        saveFailed: 'Сохранение не удалось',
        loadFailed: 'Загрузка не удалась',
        deleteFailed: 'Удаление не удалось',
        moveFailed: 'Перемещение не удалось',
        copyFailed: 'Копирование не удалось',
        fetchFailed: 'Не удалось получить данные с Civitai',
        invalidUrl: 'Неверный формат URL',
        missingPermissions: 'Недостаточно прав'
    },
    
    // Сообщения об успехе
    success: {
        saved: 'Успешно сохранено',
        deleted: 'Успешно удалено',
        moved: 'Успешно перемещено',
        copied: 'Успешно скопировано',
        downloaded: 'Успешно скачано',
        uploaded: 'Успешно загружено',
        refreshed: 'Успешно обновлено',
        exported: 'Успешно экспортировано',
        imported: 'Успешно импортировано'
    },
    
    // Горячие клавиши
    keyboard: {
        navigation: 'Навигация с клавиатуры:',
        shortcuts: {
            pageUp: 'Прокрутить вверх на одну страницу',
            pageDown: 'Прокрутить вниз на одну страницу',
            home: 'Перейти к началу',
            end: 'Перейти к концу',
            bulkMode: 'Переключить массовый режим',
            search: 'Фокус на поиске',
            escape: 'Закрыть модальное окно/панель'
        }
    },
    
    // Инициализация
    initialization: {
        title: 'Инициализация LoRA Менеджера',
        message: 'Сканирование и построение кэша LoRA. Это может занять несколько минут...',
        steps: {
            scanning: 'Сканирование файлов моделей...',
            processing: 'Обработка метаданных...',
            building: 'Построение кэша...',
            finalizing: 'Завершение...'
        }
    },
    
    // Подсказки и справочный текст
    tooltips: {
        refresh: 'Обновить список моделей',
        bulkOperations: 'Выбрать несколько моделей для массовых операций',
        favorites: 'Показать только избранные модели',
        duplicates: 'Найти и управлять дублирующимися моделями',
        search: 'Поиск моделей по имени, тегам или другим критериям',
        filter: 'Фильтровать модели по различным критериям',
        sort: 'Сортировать модели по разным атрибутам',
        backToTop: 'Прокрутить обратно к верху страницы'
    }
};
