/**
 * Korean (ko) translations for LoRA Manager
 */
export const ko = {
    // 애플리케이션 전체에서 사용되는 공통 용어
    common: {
        // 파일 작업
        file: '파일',
        folder: '폴더',
        name: '이름',
        size: '크기',
        date: '날짜',
        type: '유형',
        path: '경로',
        
        // 파일 크기
        fileSize: {
            zero: '0 바이트',
            bytes: '바이트',
            kb: 'KB',
            mb: 'MB',
            gb: 'GB',
            tb: 'TB'
        },
        
        // 작업
        actions: {
            save: '저장',
            cancel: '취소',
            delete: '삭제',
            edit: '편집',
            copy: '복사',
            move: '이동',
            refresh: '새로고침',
            download: '다운로드',
            upload: '업로드',
            search: '검색',
            filter: '필터',
            sort: '정렬',
            select: '선택',
            selectAll: '모두 선택',
            deselectAll: '선택 해제',
            confirm: '확인',
            close: '닫기',
            back: '뒤로',
            next: '다음',
            previous: '이전',
            view: '보기',
            preview: '미리보기',
            details: '세부정보',
            settings: '설정',
            help: '도움말',
            about: '정보'
        },
        
        // 언어 설정
        language: {
            current: '언어',
            select: '언어 선택',
            select_help: '선호하는 인터페이스 언어를 선택하세요',
            english: '영어',
            chinese_simplified: '중국어(간체)',
            chinese_traditional: '중국어(번체)',
            russian: '러시아어',
            german: '독일어',
            japanese: '일본어',
            korean: '한국어',
            french: '프랑스어',
            spanish: '스페인어'
        },
        
        // 상태 메시지
        status: {
            loading: '로딩 중...',
            saving: '저장 중...',
            saved: '저장됨',
            error: '오류',
            success: '성공',
            warning: '경고',
            info: '정보',
            processing: '처리 중...',
            completed: '완료',
            failed: '실패',
            cancelled: '취소됨',
            pending: '대기 중',
            ready: '준비 완료'
        }
    },
    
    // 헤더 및 네비게이션
    header: {
        appTitle: 'LoRA 매니저',
        navigation: {
            loras: 'LoRA',
            recipes: '레시피',
            checkpoints: '체크포인트',
            embeddings: '임베딩',
            statistics: '통계'
        },
        search: {
            placeholder: '검색...',
            placeholders: {
                loras: 'LoRA 검색...',
                recipes: '레시피 검색...',
                checkpoints: '체크포인트 검색...',
                embeddings: '임베딩 검색...'
            },
            options: '검색 옵션',
            searchIn: '검색 범위:',
            notAvailable: '통계 페이지에서는 검색이 불가능합니다',
            filters: {
                filename: '파일명',
                modelname: '모델명',
                tags: '태그',
                creator: '제작자',
                title: '레시피 제목',
                loraName: 'LoRA 파일명',
                loraModel: 'LoRA 모델명'
            }
        },
        filter: {
            title: '모델 필터',
            baseModel: '베이스 모델',
            modelTags: '태그 (상위 20개)',
            clearAll: '모든 필터 지우기'
        },
        theme: {
            toggle: '테마 전환',
            switchToLight: '밝은 테마로 전환',
            switchToDark: '어두운 테마로 전환',
            switchToAuto: '자동 테마로 전환'
        }
    },
    
    // LoRA 페이지
    loras: {
        title: 'LoRA 모델',
        controls: {
            sort: {
                title: '모델 정렬...',
                name: '이름',
                nameAsc: 'A - Z',
                nameDesc: 'Z - A',
                date: '추가 날짜',
                dateDesc: '최신순',
                dateAsc: '오래된순',
                size: '파일 크기',
                sizeDesc: '큰 순서',
                sizeAsc: '작은 순서'
            },
            refresh: {
                title: '모델 목록 새로고침',
                quick: '빠른 새로고침 (증분)',
                full: '전체 재구축 (완전)'
            },
            fetch: 'Civitai에서 가져오기',
            download: 'URL에서 다운로드',
            bulk: '일괄 작업',
            duplicates: '중복 찾기',
            favorites: '즐겨찾기만 표시'
        },
        bulkOperations: {
            title: '일괄 작업',
            selected: '{count}개 선택됨',
            selectAll: '현재 페이지 모두 선택',
            deselectAll: '모든 선택 해제',
            actions: {
                move: '선택항목 이동',
                delete: '선택항목 삭제',
                setRating: '콘텐츠 등급 설정',
                export: '선택항목 내보내기'
            }
        },
        card: {
            actions: {
                copyTriggerWords: '트리거 단어 복사',
                copyLoraName: 'LoRA 이름 복사',
                sendToWorkflow: '워크플로우로 전송',
                sendToWorkflowAppend: '워크플로우로 전송 (추가)',
                sendToWorkflowReplace: '워크플로우로 전송 (교체)',
                openExamples: '예제 폴더 열기',
                downloadExamples: '예제 이미지 다운로드',
                replacePreview: '미리보기 교체',
                setContentRating: '콘텐츠 등급 설정',
                moveToFolder: '폴더로 이동',
                excludeModel: '모델 제외',
                deleteModel: '모델 삭제'
            },
            modal: {
                title: 'LoRA 세부정보',
                tabs: {
                    examples: '예제',
                    description: '모델 설명',
                    recipes: '레시피'
                },
                info: {
                    filename: '파일명',
                    modelName: '모델명',
                    baseModel: '베이스 모델',
                    fileSize: '파일 크기',
                    dateAdded: '추가 날짜',
                    triggerWords: '트리거 단어',
                    description: '설명',
                    tags: '태그',
                    rating: '평점',
                    downloads: '다운로드 수',
                    likes: '좋아요 수',
                    version: '버전'
                },
                actions: {
                    copyTriggerWords: '트리거 단어 복사',
                    copyLoraName: 'LoRA 이름 복사',
                    sendToWorkflow: '워크플로우로 전송',
                    viewOnCivitai: 'Civitai에서 보기',
                    downloadExamples: '예제 이미지 다운로드'
                }
            }
        }
    },
    
    // 레시피 페이지
    recipes: {
        title: 'LoRA 레시피',
        controls: {
            import: '레시피 가져오기',
            create: '레시피 만들기',
            export: '선택항목 내보내기',
            downloadMissing: '누락된 LoRA 다운로드'
        },
        card: {
            author: '저자',
            loras: '{count}개의 LoRA',
            tags: '태그',
            actions: {
                sendToWorkflow: '워크플로우로 전송',
                edit: '레시피 편집',
                duplicate: '레시피 복제',
                export: '레시피 내보내기',
                delete: '레시피 삭제'
            }
        }
    },
    
    // 체크포인트 페이지
    checkpoints: {
        title: '체크포인트 모델',
        info: {
            filename: '파일명',
            modelName: '모델명',
            baseModel: '베이스 모델',
            fileSize: '파일 크기',
            dateAdded: '추가 날짜'
        }
    },
    
    // 임베딩 페이지
    embeddings: {
        title: '임베딩 모델',
        info: {
            filename: '파일명',
            modelName: '모델명',
            triggerWords: '트리거 단어',
            fileSize: '파일 크기',
            dateAdded: '추가 날짜'
        }
    },
    
    // 통계 페이지
    statistics: {
        title: '통계',
        overview: {
            title: '개요',
            totalModels: '총 모델 수',
            totalSize: '총 크기',
            avgFileSize: '평균 파일 크기',
            newestModel: '최신 모델'
        },
        charts: {
            modelsByBaseModel: '베이스 모델별',
            modelsByMonth: '월별',
            fileSizeDistribution: '파일 크기 분포',
            topTags: '인기 태그'
        }
    },
    
    // 모달 대화상자
    modals: {
        delete: {
            title: '삭제 확인',
            message: '이 모델을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.',
            confirm: '삭제',
            cancel: '취소'
        },
        exclude: {
            title: '모델 제외',
            message: '이 모델을 라이브러리에서 제외하시겠습니까?',
            confirm: '제외',
            cancel: '취소'
        },
        download: {
            title: '모델 다운로드',
            url: '모델 URL',
            placeholder: 'Civitai 모델 URL 입력...',
            download: '다운로드',
            cancel: '취소'
        },
        move: {
            title: '모델 이동',
            selectFolder: '대상 폴더 선택',
            createFolder: '새 폴더 만들기',
            folderName: '폴더명',
            move: '이동',
            cancel: '취소'
        },
        contentRating: {
            title: '콘텐츠 등급 설정',
            current: '현재',
            levels: {
                pg: '전체관람가',
                pg13: '13세 이상',
                r: '제한관람가',
                x: '성인',
                xxx: '노골적'
            }
        }
    },
    
    // 오류 메시지
    errors: {
        general: '오류가 발생했습니다',
        networkError: '네트워크 오류. 연결을 확인하세요.',
        serverError: '서버 오류. 나중에 다시 시도하세요.',
        fileNotFound: '파일을 찾을 수 없습니다',
        invalidFile: '잘못된 파일 형식',
        uploadFailed: '업로드 실패',
        downloadFailed: '다운로드 실패',
        saveFailed: '저장 실패',
        loadFailed: '로드 실패',
        deleteFailed: '삭제 실패',
        moveFailed: '이동 실패',
        copyFailed: '복사 실패',
        fetchFailed: 'Civitai에서 데이터를 가져오지 못했습니다',
        invalidUrl: '잘못된 URL 형식',
        missingPermissions: '권한이 부족합니다'
    },
    
    // 성공 메시지
    success: {
        saved: '성공적으로 저장되었습니다',
        deleted: '성공적으로 삭제되었습니다',
        moved: '성공적으로 이동되었습니다',
        copied: '성공적으로 복사되었습니다',
        downloaded: '성공적으로 다운로드되었습니다',
        uploaded: '성공적으로 업로드되었습니다',
        refreshed: '성공적으로 새로고침되었습니다',
        exported: '성공적으로 내보내졌습니다',
        imported: '성공적으로 가져왔습니다'
    },
    
    // 키보드 단축키
    keyboard: {
        navigation: '키보드 내비게이션:',
        shortcuts: {
            pageUp: '한 페이지 위로 스크롤',
            pageDown: '한 페이지 아래로 스크롤',
            home: '맨 위로 이동',
            end: '맨 아래로 이동',
            bulkMode: '일괄 모드 전환',
            search: '검색 포커스',
            escape: '모달/패널 닫기'
        }
    },
    
    // 초기화
    initialization: {
        title: 'LoRA 매니저 초기화',
        message: 'LoRA 캐시를 스캔하고 구축중입니다. 몇 분 정도 걸릴 수 있습니다...',
        steps: {
            scanning: '모델 파일 스캔 중...',
            processing: '메타데이터 처리 중...',
            building: '캐시 구축 중...',
            finalizing: '마무리 중...'
        }
    },
    
    // 툴팁 및 도움말 텍스트
    tooltips: {
        refresh: '모델 목록 새로고침',
        bulkOperations: '여러 모델을 선택하여 일괄 작업',
        favorites: '즐겨찾기 모델만 표시',
        duplicates: '중복 모델 찾기 및 관리',
        search: '이름, 태그 또는 기타 기준으로 모델 검색',
        filter: '다양한 기준으로 모델 필터링',
        sort: '다른 속성으로 모델 정렬',
        backToTop: '페이지 맨 위로 스크롤'
    }
};
