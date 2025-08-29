/**
 * Simplified Chinese (zh-CN) translations for LoRA Manager
 */
export const zhCN = {
    // 应用中使用的通用术语
    common: {
        // 文件操作
        file: '文件',
        folder: '文件夹',
        name: '名称',
        size: '大小',
        date: '日期',
        type: '类型',
        path: '路径',
        
        // 文件大小
        fileSize: {
            zero: '0 字节',
            bytes: '字节',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // 操作
        actions: {
            save: '保存',
            cancel: '取消',
            delete: '删除',
            edit: '编辑',
            copy: '复制',
            move: '移动',
            refresh: '刷新',
            download: '下载',
            upload: '上传',
            search: '搜索',
            filter: '筛选',
            sort: '排序',
            select: '选择',
            selectAll: '全选',
            deselectAll: '取消全选',
            confirm: '确认',
            close: '关闭',
            back: '返回',
            next: '下一步',
            previous: '上一步',
            view: '查看',
            preview: '预览',
            details: '详情',
            settings: '设置',
            help: '帮助',
            about: '关于'
        },
        
        // 状态信息
        status: {
            loading: '加载中...',
            saving: '保存中...',
            saved: '已保存',
            error: '错误',
            success: '成功',
            warning: '警告',
            info: '信息',
            processing: '处理中...',
            completed: '已完成',
            failed: '失败',
            cancelled: '已取消',
            pending: '等待中',
            ready: '就绪'
        }
    },
    
    // 头部和导航
    header: {
        appTitle: 'LoRA',
        navigation: {
            loras: 'LoRA',
            recipes: '配方',
            checkpoints: '大模型',
            embeddings: 'Embedding',
            statistics: '统计'
        },
        search: {
            placeholder: '搜索...',
            placeholders: {
                loras: '搜索 LoRA...',
                recipes: '搜索配方...',
                checkpoints: '搜索大模型...',
                embeddings: '搜索 Embedding...'
            },
            options: '搜索选项',
            searchIn: '搜索范围：',
            notAvailable: '统计页面不支持搜索',
            filters: {
                filename: '文件名',
                modelname: '模型名称',
                tags: '标签',
                creator: '创作者',
                title: '配方标题',
                loraName: 'LoRA 文件名',
                loraModel: 'LoRA 模型名称'
            }
        },
        filter: {
            title: '筛选模型',
            baseModel: '基础模型',
            modelTags: '标签（前20个）',
            clearAll: '清除所有筛选'
        },
        theme: {
            toggle: '切换主题',
            switchToLight: '切换到浅色主题',
            switchToDark: '切换到深色主题',
            switchToAuto: '切换到自动主题'
        }
    },
    
    // LoRA 页面
    loras: {
        title: 'LoRA',
        controls: {
            sort: {
                title: '排序方式...',
                name: '名称',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: '添加日期',
                dateDesc: '最新',
                dateAsc: '最旧',
                size: '文件大小',
                sizeDesc: '最大',
                sizeAsc: '最小'
            },
            refresh: {
                title: '刷新模型列表',
                quick: '快速刷新（增量）',
                full: '完全重建（完整）'
            },
            fetch: '从 Civitai 获取',
            download: '从 URL 下载',
            bulk: '批量操作',
            duplicates: '查找重复项',
            favorites: '仅显示收藏'
        },
        bulkOperations: {
            title: '批量操作',
            selected: '已选择{count}项',
            sendToWorkflow: '发送到工作流',
            copyAll: '复制LoRA语法',
            refreshAll: '刷新元数据',
            moveAll: '移动',
            deleteAll: '删除',
            clear: '清除选择'
        },
        contextMenu: {
            refreshMetadata: '刷新 Civitai 数据',
            relinkCivitai: '重新链接到 Civitai',
            copySyntax: '复制 LoRA 语法',
            sendToWorkflowAppend: '发送到工作流（追加）',
            sendToWorkflowReplace: '发送到工作流（替换）',
            openExamples: '打开示例文件夹',
            downloadExamples: '下载示例图片',
            replacePreview: '替换预览图',
            setContentRating: '设置内容评级',
            moveToFolder: '移动到文件夹',
            excludeModel: '排除模型',
            deleteModel: '删除模型'
        },
        modal: {
            title: 'LoRA 详情',
            tabs: {
                examples: '示例',
                description: '模型描述',
                recipes: '配方'
            },
            info: {
                filename: '文件名',
                modelName: '模型名称',
                baseModel: '基础模型',
                fileSize: '文件大小',
                dateAdded: '添加日期',
                triggerWords: '触发词',
                description: '描述',
                tags: '标签',
                rating: '评分',
                downloads: '下载量',
                likes: '点赞数',
                version: '版本'
            },
            actions: {
                copyTriggerWords: '复制触发词',
                copyLoraName: '复制 LoRA 名称',
                sendToWorkflow: '发送到工作流',
                viewOnCivitai: '在 Civitai 上查看',
                downloadExamples: '下载示例图片'
            }
        }
    },
    
    // 配方页面
    recipes: {
        title: 'LoRA 配方',
        controls: {
            import: '导入配方',
            create: '创建配方',
            export: '导出选中',
            downloadMissing: '下载缺失的 LoRA'
        },
        card: {
            author: '作者',
            loras: '{count} 个 LoRA',
            tags: '标签',
            actions: {
                sendToWorkflow: '发送到工作流',
                edit: '编辑配方',
                duplicate: '复制配方',
                export: '导出配方',
                delete: '删除配方'
            }
        }
    },
    
    // 大模型页面
    checkpoints: {
        title: '大模型',
        info: {
            filename: '文件名',
            modelName: '模型名称',
            baseModel: '基础模型',
            fileSize: '文件大小',
            dateAdded: '添加日期'
        }
    },
    
    // 嵌入模型页面
    embeddings: {
        title: 'Embedding',
        info: {
            filename: '文件名',
            modelName: '模型名称',
            triggerWords: '触发词',
            fileSize: '文件大小',
            dateAdded: '添加日期'
        }
    },
    
    // 统计页面
    statistics: {
        title: '统计信息',
        overview: {
            title: '概览',
            totalLoras: 'LoRA 总数',
            totalCheckpoints: '大模型总数',
            totalEmbeddings: 'Embedding 总数',
            totalSize: '总大小',
            favoriteModels: '收藏模型'
        },
        charts: {
            modelsByType: '按类型统计模型',
            modelsByBaseModel: '按基础模型统计',
            modelsBySize: '按文件大小统计',
            modelsAddedOverTime: '模型添加时间分布'
        }
    },
    
    // 模态框和对话框
    modals: {
        delete: {
            title: '确认删除',
            message: '确定要删除这个模型吗？',
            warningMessage: '此操作无法撤销。',
            confirm: '删除',
            cancel: '取消'
        },
        exclude: {
            title: '排除模型',
            message: '确定要从库中排除这个模型吗？',
            confirm: '排除',
            cancel: '取消'
        },
        download: {
            title: '下载模型',
            url: '模型 URL',
            placeholder: '输入 Civitai 模型 URL...',
            download: '下载',
            cancel: '取消'
        },
        move: {
            title: '移动模型',
            selectFolder: '选择目标文件夹',
            createFolder: '创建新文件夹',
            folderName: '文件夹名称',
            move: '移动',
            cancel: '取消'
        },
        contentRating: {
            title: '设置内容评级',
            current: '当前',
            levels: {
                pg: '普通级',
                pg13: '辅导级',
                r: '限制级',
                x: '成人级',
                xxx: '重口级'
            }
        }
    },
    
    // 错误信息
    errors: {
        general: '发生错误',
        networkError: '网络错误，请检查您的连接。',
        serverError: '服务器错误，请稍后重试。',
        fileNotFound: '文件未找到',
        invalidFile: '无效的文件格式',
        uploadFailed: '上传失败',
        downloadFailed: '下载失败',
        saveFailed: '保存失败',
        loadFailed: '加载失败',
        deleteFailed: '删除失败',
        moveFailed: '移动失败',
        copyFailed: '复制失败',
        fetchFailed: '从 Civitai 获取数据失败',
        invalidUrl: '无效的 URL 格式',
        missingPermissions: '权限不足'
    },
    
    // 成功信息
    success: {
        saved: '保存成功',
        deleted: '删除成功',
        moved: '移动成功',
        copied: '复制成功',
        downloaded: '下载成功',
        uploaded: '上传成功',
        refreshed: '刷新成功',
        exported: '导出成功',
        imported: '导入成功'
    },
    
    // 键盘快捷键
    keyboard: {
        navigation: '键盘导航：',
        shortcuts: {
            pageUp: '向上滚动一页',
            pageDown: '向下滚动一页',
            home: '跳转到顶部',
            end: '跳转到底部',
            bulkMode: '切换批量模式',
            search: '聚焦搜索框',
            escape: '关闭模态框/面板'
        }
    },
    
    // 初始化
    initialization: {
        title: '初始化 LoRA 管理器',
        message: '正在扫描并构建 LoRA 缓存，这可能需要几分钟时间...',
        steps: {
            scanning: '扫描模型文件...',
            processing: '处理元数据...',
            building: '构建缓存...',
            finalizing: '完成中...'
        }
    },
    
    // 工具提示和帮助文本
    tooltips: {
        refresh: '刷新模型列表',
        bulkOperations: '选择多个模型进行批量操作',
        favorites: '仅显示收藏的模型',
        duplicates: '查找和管理重复的模型',
        search: '按名称、标签或其他条件搜索模型',
        filter: '按各种条件筛选模型',
        sort: '按不同属性排序模型',
        backToTop: '滚动回页面顶部'
    }
};
