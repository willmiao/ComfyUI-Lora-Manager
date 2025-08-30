/**
 * Japanese (ja) translations for LoRA Manager
 */
export const ja = {
    // アプリケーション全体で使用される共通用語
    common: {
        // ファイル操作
        file: 'ファイル',
        folder: 'フォルダ',
        name: '名前',
        size: 'サイズ',
        date: '日付',
        type: '種類',
        path: 'パス',
        
        // ファイルサイズ
        fileSize: {
            zero: '0 バイト',
            bytes: 'バイト',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // アクション
        actions: {
            save: '保存',
            cancel: 'キャンセル',
            delete: '削除',
            edit: '編集',
            copy: 'コピー',
            move: '移動',
            refresh: '更新',
            download: 'ダウンロード',
            upload: 'アップロード',
            search: '検索',
            filter: 'フィルター',
            sort: 'ソート',
            select: '選択',
            selectAll: 'すべて選択',
            deselectAll: '選択解除',
            confirm: '確認',
            close: '閉じる',
            back: '戻る',
            next: '次へ',
            previous: '前へ',
            view: '表示',
            preview: 'プレビュー',
            details: '詳細',
            settings: '設定',
            help: 'ヘルプ',
            about: 'について'
        },
        
        // 言語設定
        language: {
            current: '言語',
            select: '言語を選択',
            select_help: 'インターフェース言語を選択してください',
            english: '英語',
            chinese_simplified: '中国語（簡体字）',
            chinese_traditional: '中国語（繁体字）',
            russian: 'ロシア語',
            german: 'ドイツ語',
            japanese: '日本語',
            korean: '韓国語',
            french: 'フランス語',
            spanish: 'スペイン語'
        },
        
        // ステータスメッセージ
        status: {
            loading: '読み込み中...',
            saving: '保存中...',
            saved: '保存済み',
            error: 'エラー',
            success: '成功',
            warning: '警告',
            info: '情報',
            processing: '処理中...',
            completed: '完了',
            failed: '失敗',
            cancelled: 'キャンセル',
            pending: '待機中',
            ready: '準備完了'
        }
    },
    
    // ヘッダーとナビゲーション
    header: {
        appTitle: 'LoRA マネージャー',
        navigation: {
            loras: 'LoRA',
            recipes: 'レシピ',
            checkpoints: 'チェックポイント',
            embeddings: 'エンベディング',
            statistics: '統計'
        },
        search: {
            placeholder: '検索...',
            placeholders: {
                loras: 'LoRAを検索...',
                recipes: 'レシピを検索...',
                checkpoints: 'チェックポイントを検索...',
                embeddings: 'エンベディングを検索...'
            },
            options: '検索オプション',
            searchIn: '検索対象:',
            notAvailable: '統計ページでは検索は利用できません',
            filters: {
                filename: 'ファイル名',
                modelname: 'モデル名',
                tags: 'タグ',
                creator: '作成者',
                title: 'レシピタイトル',
                loraName: 'LoRAファイル名',
                loraModel: 'LoRAモデル名'
            }
        },
        filter: {
            title: 'モデルをフィルター',
            baseModel: 'ベースモデル',
            modelTags: 'タグ（トップ20）',
            clearAll: 'すべてのフィルターをクリア'
        },
        theme: {
            toggle: 'テーマ切り替え',
            switchToLight: 'ライトテーマに切り替え',
            switchToDark: 'ダークテーマに切り替え',
            switchToAuto: 'オートテーマに切り替え'
        }
    },
    
    // LoRAページ
    loras: {
        title: 'LoRAモデル',
        controls: {
            sort: {
                title: 'モデルをソート...',
                name: '名前',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: '追加日',
                dateDesc: '新しい順',
                dateAsc: '古い順',
                size: 'ファイルサイズ',
                sizeDesc: '大きい順',
                sizeAsc: '小さい順'
            },
            refresh: {
                title: 'モデルリストを更新',
                quick: 'クイック更新（増分）',
                full: '完全再構築（完全）'
            },
            fetch: 'Civitaiから取得',
            download: 'URLからダウンロード',
            bulk: '一括操作',
            duplicates: '重複を検索',
            favorites: 'お気に入りのみ表示'
        },
        bulkOperations: {
            title: '一括操作',
            selected: '{count}個選択中',
            selectAll: '現在のページのすべてを選択',
            deselectAll: 'すべての選択を解除',
            actions: {
                move: '選択項目を移動',
                delete: '選択項目を削除',
                setRating: 'コンテンツレーティングを設定',
                export: '選択項目をエクスポート'
            }
        },
        card: {
            actions: {
                copyTriggerWords: 'トリガーワードをコピー',
                copyLoraName: 'LoRA名をコピー',
                sendToWorkflow: 'ワークフローに送信',
                sendToWorkflowAppend: 'ワークフローに送信（追加）',
                sendToWorkflowReplace: 'ワークフローに送信（置換）',
                openExamples: 'サンプルフォルダを開く',
                downloadExamples: 'サンプル画像をダウンロード',
                replacePreview: 'プレビューを置換',
                setContentRating: 'コンテンツレーティングを設定',
                moveToFolder: 'フォルダに移動',
                excludeModel: 'モデルを除外',
                deleteModel: 'モデルを削除'
            },
            modal: {
                title: 'LoRA詳細',
                tabs: {
                    examples: 'サンプル',
                    description: 'モデル説明',
                    recipes: 'レシピ'
                },
                info: {
                    filename: 'ファイル名',
                    modelName: 'モデル名',
                    baseModel: 'ベースモデル',
                    fileSize: 'ファイルサイズ',
                    dateAdded: '追加日',
                    triggerWords: 'トリガーワード',
                    description: '説明',
                    tags: 'タグ',
                    rating: '評価',
                    downloads: 'ダウンロード数',
                    likes: 'いいね数',
                    version: 'バージョン'
                },
                actions: {
                    copyTriggerWords: 'トリガーワードをコピー',
                    copyLoraName: 'LoRA名をコピー',
                    sendToWorkflow: 'ワークフローに送信',
                    viewOnCivitai: 'Civitaiで表示',
                    downloadExamples: 'サンプル画像をダウンロード'
                }
            }
        }
    },
    
    // レシピページ
    recipes: {
        title: 'LoRAレシピ',
        controls: {
            import: 'レシピをインポート',
            create: 'レシピを作成',
            export: '選択項目をエクスポート',
            downloadMissing: '不足しているLoRAをダウンロード'
        },
        card: {
            author: '作者',
            loras: '{count}個のLoRA',
            tags: 'タグ',
            actions: {
                sendToWorkflow: 'ワークフローに送信',
                edit: 'レシピを編集',
                duplicate: 'レシピを複製',
                export: 'レシピをエクスポート',
                delete: 'レシピを削除'
            }
        }
    },
    
    // チェックポイントページ
    checkpoints: {
        title: 'チェックポイントモデル',
        info: {
            filename: 'ファイル名',
            modelName: 'モデル名',
            baseModel: 'ベースモデル',
            fileSize: 'ファイルサイズ',
            dateAdded: '追加日'
        }
    },
    
    // エンベディングページ
    embeddings: {
        title: 'エンベディングモデル',
        info: {
            filename: 'ファイル名',
            modelName: 'モデル名',
            triggerWords: 'トリガーワード',
            fileSize: 'ファイルサイズ',
            dateAdded: '追加日'
        }
    },
    
    // 統計ページ
    statistics: {
        title: '統計',
        overview: {
            title: '概要',
            totalModels: '総モデル数',
            totalSize: '総サイズ',
            avgFileSize: '平均ファイルサイズ',
            newestModel: '最新モデル'
        },
        charts: {
            modelsByBaseModel: 'ベースモデル別',
            modelsByMonth: '月別',
            fileSizeDistribution: 'ファイルサイズ分布',
            topTags: '人気タグ'
        }
    },
    
    // モーダルダイアログ
    modals: {
        delete: {
            title: '削除の確認',
            message: 'このモデルを削除してもよろしいですか？この操作は元に戻せません。',
            confirm: '削除',
            cancel: 'キャンセル'
        },
        exclude: {
            title: 'モデルを除外',
            message: 'このモデルをライブラリから除外してもよろしいですか？',
            confirm: '除外',
            cancel: 'キャンセル'
        },
        download: {
            title: 'モデルをダウンロード',
            url: 'モデルURL',
            placeholder: 'CivitaiモデルURLを入力...',
            download: 'ダウンロード',
            cancel: 'キャンセル'
        },
        move: {
            title: 'モデルを移動',
            selectFolder: '移動先フォルダを選択',
            createFolder: '新しいフォルダを作成',
            folderName: 'フォルダ名',
            move: '移動',
            cancel: 'キャンセル'
        },
        contentRating: {
            title: 'コンテンツレーティングを設定',
            current: '現在',
            levels: {
                pg: '全年齢',
                pg13: '13歳以上',
                r: '制限あり',
                x: '成人向け',
                xxx: '露骨'
            }
        }
    },
    
    // エラーメッセージ
    errors: {
        general: 'エラーが発生しました',
        networkError: 'ネットワークエラー。接続を確認してください。',
        serverError: 'サーバーエラー。後でもう一度試してください。',
        fileNotFound: 'ファイルが見つかりません',
        invalidFile: '無効なファイル形式',
        uploadFailed: 'アップロードに失敗しました',
        downloadFailed: 'ダウンロードに失敗しました',
        saveFailed: '保存に失敗しました',
        loadFailed: '読み込みに失敗しました',
        deleteFailed: '削除に失敗しました',
        moveFailed: '移動に失敗しました',
        copyFailed: 'コピーに失敗しました',
        fetchFailed: 'Civitaiからデータを取得できませんでした',
        invalidUrl: '無効なURL形式',
        missingPermissions: '権限が不足しています'
    },
    
    // 成功メッセージ
    success: {
        saved: '正常に保存されました',
        deleted: '正常に削除されました',
        moved: '正常に移動されました',
        copied: '正常にコピーされました',
        downloaded: '正常にダウンロードされました',
        uploaded: '正常にアップロードされました',
        refreshed: '正常に更新されました',
        exported: '正常にエクスポートされました',
        imported: '正常にインポートされました'
    },
    
    // キーボードショートカット
    keyboard: {
        navigation: 'キーボードナビゲーション:',
        shortcuts: {
            pageUp: '1ページ上にスクロール',
            pageDown: '1ページ下にスクロール',
            home: 'トップにジャンプ',
            end: 'ボトムにジャンプ',
            bulkMode: '一括モードを切り替え',
            search: '検索にフォーカス',
            escape: 'モーダル/パネルを閉じる'
        }
    },
    
    // 初期化
    initialization: {
        title: 'LoRAマネージャーを初期化中',
        message: 'LoRAキャッシュをスキャンして構築中です。数分かかる場合があります...',
        steps: {
            scanning: 'モデルファイルをスキャン中...',
            processing: 'メタデータを処理中...',
            building: 'キャッシュを構築中...',
            finalizing: '完了中...'
        }
    },
    
    // ツールチップとヘルプテキスト
    tooltips: {
        refresh: 'モデルリストを更新',
        bulkOperations: '複数のモデルを選択してバッチ操作',
        favorites: 'お気に入りモデルのみ表示',
        duplicates: '重複モデルを検索・管理',
        search: '名前、タグ、その他の条件でモデルを検索',
        filter: '様々な条件でモデルをフィルター',
        sort: '異なる属性でモデルをソート',
        backToTop: 'ページトップにスクロール'
    }
};
