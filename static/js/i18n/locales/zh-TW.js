/**
 * Traditional Chinese (zh-TW) translations for LoRA Manager
 */
export const zhTW = {
    // 應用中使用的通用術語
    common: {
        // 檔案操作
        file: '檔案',
        folder: '資料夾',
        name: '名稱',
        size: '大小',
        date: '日期',
        type: '類型',
        path: '路徑',
        
        // 檔案大小
        fileSize: {
            zero: '0 位元組',
            bytes: '位元組',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // 操作
        actions: {
            save: '儲存',
            cancel: '取消',
            delete: '刪除',
            edit: '編輯',
            copy: '複製',
            move: '移動',
            refresh: '重新整理',
            download: '下載',
            upload: '上傳',
            search: '搜尋',
            filter: '篩選',
            sort: '排序',
            select: '選擇',
            selectAll: '全選',
            deselectAll: '取消全選',
            confirm: '確認',
            close: '關閉',
            back: '返回',
            next: '下一步',
            previous: '上一步',
            view: '檢視',
            preview: '預覽',
            details: '詳情',
            settings: '設定',
            help: '說明',
            about: '關於'
        },
        
        // 語言設定
        language: {
            current: '語言',
            select: '選擇語言',
            select_help: '選擇您偏好的介面語言',
            english: '英語',
            chinese_simplified: '中文（簡體）',
            chinese_traditional: '中文（繁體）',
            russian: '俄語',
            german: '德語',
            japanese: '日語',
            korean: '韓語',
            french: '法語',
            spanish: '西班牙語'
        },
        
        // 狀態資訊
        status: {
            loading: '載入中...',
            saving: '儲存中...',
            saved: '已儲存',
            error: '錯誤',
            success: '成功',
            warning: '警告',
            info: '資訊',
            processing: '處理中...',
            completed: '已完成',
            failed: '失敗',
            cancelled: '已取消',
            pending: '等待中',
            ready: '就緒'
        }
    },
    
    // 標題列和導覽
    header: {
        appTitle: 'LoRA 管理器',
        navigation: {
            loras: 'LoRA',
            recipes: '配方',
            checkpoints: 'Checkpoint',
            embeddings: 'Embedding',
            statistics: '統計'
        },
        search: {
            placeholder: '搜尋...',
            placeholders: {
                loras: '搜尋 LoRA...',
                recipes: '搜尋配方...',
                checkpoints: '搜尋Checkpoint...',
                embeddings: '搜尋 Embedding...'
            },
            options: '搜尋選項',
            searchIn: '搜尋範圍：',
            notAvailable: '統計頁面不支援搜尋',
            filters: {
                filename: '檔案名稱',
                modelname: '模型名稱',
                tags: '標籤',
                creator: '創作者',
                title: '配方標題',
                loraName: 'LoRA 檔案名稱',
                loraModel: 'LoRA 模型名稱'
            }
        },
        filter: {
            title: '篩選模型',
            baseModel: '基礎模型',
            modelTags: '標籤（前20個）',
            clearAll: '清除所有篩選'
        },
        theme: {
            toggle: '切換主題',
            switchToLight: '切換到淺色主題',
            switchToDark: '切換到深色主題',
            switchToAuto: '切換到自動主題'
        }
    },
    
    // LoRA 頁面
    loras: {
        title: 'LoRA 模型',
        controls: {
            sort: {
                title: '排序方式...',
                name: '名稱',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: '新增日期',
                dateDesc: '最新',
                dateAsc: '最舊',
                size: '檔案大小',
                sizeDesc: '最大',
                sizeAsc: '最小'
            },
            refresh: {
                title: '重新整理模型清單',
                quick: '快速重新整理（增量）',
                full: '完整重建（完整）'
            },
            fetch: '從 Civitai 獲取',
            download: '從 URL 下載',
            bulk: '批次操作',
            duplicates: '尋找重複項',
            favorites: '僅顯示收藏'
        },
        bulkOperations: {
            title: '批次操作',
            selected: '已選擇 {count} 個',
            selectAll: '選擇所有當前頁面',
            deselectAll: '取消選擇所有',
            actions: {
                move: '移動選中項目',
                delete: '刪除選中項目',
                setRating: '設定內容評級',
                export: '匯出選中項目'
            }
        },
        card: {
            actions: {
                copyTriggerWords: '複製觸發詞',
                copyLoraName: '複製 LoRA 名稱',
                sendToWorkflow: '傳送到工作流程',
                sendToWorkflowAppend: '傳送到工作流程（附加）',
                sendToWorkflowReplace: '傳送到工作流程（替換）',
                openExamples: '開啟範例資料夾',
                downloadExamples: '下載範例圖片',
                replacePreview: '替換預覽圖',
                setContentRating: '設定內容評級',
                moveToFolder: '移動到資料夾',
                excludeModel: '排除模型',
                deleteModel: '刪除模型'
            },
            modal: {
                title: 'LoRA 詳情',
                tabs: {
                    examples: '範例',
                    description: '模型描述',
                    recipes: '配方'
                },
                info: {
                    filename: '檔案名稱',
                    modelName: '模型名稱',
                    baseModel: '基礎模型',
                    fileSize: '檔案大小',
                    dateAdded: '新增日期',
                    triggerWords: '觸發詞',
                    description: '描述',
                    tags: '標籤',
                    rating: '評級',
                    downloads: '下載次數',
                    likes: '按讚數',
                    version: '版本'
                },
                actions: {
                    copyTriggerWords: '複製觸發詞',
                    copyLoraName: '複製 LoRA 名稱',
                    sendToWorkflow: '傳送到工作流程',
                    viewOnCivitai: '在 Civitai 檢視',
                    downloadExamples: '下載範例圖片'
                }
            }
        }
    },
    
    // 配方頁面
    recipes: {
        title: 'LoRA 配方',
        controls: {
            import: '匯入配方',
            create: '建立配方',
            export: '匯出選中項目',
            downloadMissing: '下載缺少的 LoRA'
        },
        card: {
            author: '作者',
            loras: '{count} 個 LoRA',
            tags: '標籤',
            actions: {
                sendToWorkflow: '傳送到工作流程',
                edit: '編輯配方',
                duplicate: '複製配方',
                export: '匯出配方',
                delete: '刪除配方'
            }
        }
    },
    
    // Checkpoint頁面
    checkpoints: {
        title: 'Checkpoint',
        info: {
            filename: '檔案名稱',
            modelName: '模型名稱',
            baseModel: '基礎模型',
            fileSize: '檔案大小',
            dateAdded: '新增日期'
        }
    },
    
    // Embedding 頁面
    embeddings: {
        title: 'Embedding 模型',
        info: {
            filename: '檔案名稱',
            modelName: '模型名稱',
            triggerWords: '觸發詞',
            fileSize: '檔案大小',
            dateAdded: '新增日期'
        }
    },
    
    // 統計頁面
    statistics: {
        title: '統計',
        overview: {
            title: '概覽',
            totalModels: '總模型數',
            totalSize: '總大小',
            avgFileSize: '平均檔案大小',
            newestModel: '最新模型'
        },
        charts: {
            modelsByBaseModel: '按基礎模型分類',
            modelsByMonth: '按月份分類',
            fileSizeDistribution: '檔案大小分佈',
            topTags: '熱門標籤'
        }
    },
    
    // 模態對話框
    modals: {
        delete: {
            title: '確認刪除',
            message: '確定要刪除這個模型嗎？此操作無法復原。',
            confirm: '刪除',
            cancel: '取消'
        },
        exclude: {
            title: '排除模型',
            message: '確定要從程式庫中排除這個模型嗎？',
            confirm: '排除',
            cancel: '取消'
        },
        download: {
            title: '下載模型',
            url: '模型 URL',
            placeholder: '輸入 Civitai 模型 URL...',
            download: '下載',
            cancel: '取消'
        },
        move: {
            title: '移動模型',
            selectFolder: '選擇目標資料夾',
            createFolder: '建立新資料夾',
            folderName: '資料夾名稱',
            move: '移動',
            cancel: '取消'
        },
        contentRating: {
            title: '設定內容評級',
            current: '目前',
            levels: {
                pg: '普通級',
                pg13: '輔導級',
                r: '限制級',
                x: '成人級',
                xxx: '重口級'
            }
        }
    },
    
    // 錯誤訊息
    errors: {
        general: '發生錯誤',
        networkError: '網路錯誤。請檢查您的連線。',
        serverError: '伺服器錯誤。請稍後再試。',
        fileNotFound: '找不到檔案',
        invalidFile: '無效的檔案格式',
        uploadFailed: '上傳失敗',
        downloadFailed: '下載失敗',
        saveFailed: '儲存失敗',
        loadFailed: '載入失敗',
        deleteFailed: '刪除失敗',
        moveFailed: '移動失敗',
        copyFailed: '複製失敗',
        fetchFailed: '無法從 Civitai 獲取資料',
        invalidUrl: '無效的 URL 格式',
        missingPermissions: '權限不足'
    },
    
    // 成功訊息
    success: {
        saved: '儲存成功',
        deleted: '刪除成功',
        moved: '移動成功',
        copied: '複製成功',
        downloaded: '下載成功',
        uploaded: '上傳成功',
        refreshed: '重新整理成功',
        exported: '匯出成功',
        imported: '匯入成功'
    },
    
    // 鍵盤快速鍵
    keyboard: {
        navigation: '鍵盤導覽：',
        shortcuts: {
            pageUp: '向上捲動一頁',
            pageDown: '向下捲動一頁',
            home: '跳轉到頂部',
            end: '跳轉到底部',
            bulkMode: '切換批次模式',
            search: '聚焦搜尋框',
            escape: '關閉模態框/面板'
        }
    },
    
    // 初始化
    initialization: {
        title: '初始化 LoRA 管理器',
        message: '正在掃描並建構 LoRA 快取，這可能需要幾分鐘時間...',
        steps: {
            scanning: '掃描模型檔案...',
            processing: '處理中繼資料...',
            building: '建構快取...',
            finalizing: '完成中...'
        }
    },
    
    // 工具提示和說明文字
    tooltips: {
        refresh: '重新整理模型清單',
        bulkOperations: '選擇多個模型進行批次操作',
        favorites: '僅顯示收藏的模型',
        duplicates: '尋找並管理重複的模型',
        search: '按名稱、標籤或其他條件搜尋模型',
        filter: '按各種條件篩選模型',
        sort: '按不同屬性排序模型',
        backToTop: '捲動回頁面頂部'
    }
};
