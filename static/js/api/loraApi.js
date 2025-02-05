import { state } from '../state/index.js';
import { showToast } from '../utils/uiHelpers.js';
import { createLoraCard } from '../components/LoraCard.js';
import { initializeInfiniteScroll } from '../utils/infiniteScroll.js';
import { showDeleteModal } from '../utils/modalUtils.js';

export async function loadMoreLoras() {
    if (state.isLoading || !state.hasMore) return;
    
    state.isLoading = true;
    try {
        const params = new URLSearchParams({
            page: state.currentPage,
            page_size: 20,
            sort_by: state.sortBy
        });
        
        if (state.activeFolder !== null) {
            params.append('folder', state.activeFolder);
        }

        console.log('Loading loras with params:', params.toString());

        const response = await fetch(`/api/loras?${params}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch loras: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Received data:', data);
        
        if (data.items.length === 0 && state.currentPage === 1) {
            const grid = document.getElementById('loraGrid');
            grid.innerHTML = '<div class="no-results">No loras found in this folder</div>';
            state.hasMore = false;
        } else if (data.items.length > 0) {
            state.hasMore = state.currentPage < data.total_pages;
            state.currentPage++;
            appendLoraCards(data.items);
            
            const sentinel = document.getElementById('scroll-sentinel');
            if (sentinel && state.observer) {
                state.observer.observe(sentinel);
            }
        } else {
            state.hasMore = false;
        }
        
    } catch (error) {
        console.error('Error loading loras:', error);
        showToast('Failed to load loras: ' + error.message, 'error');
    } finally {
        state.isLoading = false;
    }
}

export async function fetchCivitai() {
    let ws = null;
    
    await state.loadingManager.showWithProgress(async (loading) => {
        try {
            ws = new WebSocket(`ws://${window.location.host}/ws/fetch-progress`);
            
            const operationComplete = new Promise((resolve, reject) => {
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    switch(data.status) {
                        case 'started':
                            loading.setStatus('Starting metadata fetch...');
                            break;
                            
                        case 'processing':
                            const percent = ((data.processed / data.total) * 100).toFixed(1);
                            loading.setProgress(percent);
                            loading.setStatus(
                                `Processing (${data.processed}/${data.total}) ${data.current_name}`
                            );
                            break;
                            
                        case 'completed':
                            loading.setProgress(100);
                            loading.setStatus(
                                `Completed: Updated ${data.success} of ${data.processed} loras`
                            );
                            resolve();
                            break;
                            
                        case 'error':
                            reject(new Error(data.error));
                            break;
                    }
                };
                
                ws.onerror = (error) => {
                    reject(new Error('WebSocket error: ' + error.message));
                };
            });
            
            await new Promise((resolve, reject) => {
                ws.onopen = resolve;
                ws.onerror = reject;
            });
            
            const response = await fetch('/api/fetch-all-civitai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                throw new Error('Failed to fetch metadata');
            }
            
            await operationComplete;
            
            await resetAndReload();
            
        } catch (error) {
            console.error('Error fetching metadata:', error);
            showToast('Failed to fetch metadata: ' + error.message, 'error');
        } finally {
            if (ws) {
                ws.close();
            }
        }
    }, {
        initialMessage: 'Connecting...',
        completionMessage: 'Metadata update complete'
    });
}

export async function deleteModel(filePath) {
    showDeleteModal(filePath);
}

export async function replacePreview(filePath) {
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingStatus = document.querySelector('.loading-status');
    
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*,video/mp4';
    
    input.onchange = async function() {
        if (!input.files || !input.files[0]) return;
        
        const file = input.files[0];
        const formData = new FormData();
        formData.append('preview_file', file);
        formData.append('model_path', filePath);
        
        try {
            loadingOverlay.style.display = 'flex';
            loadingStatus.textContent = 'Uploading preview...';
            
            const response = await fetch('/api/replace_preview', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const data = await response.json();
            
            // 更新预览版本
            state.previewVersions.set(filePath, Date.now());
            
            // 更新卡片显示
            const card = document.querySelector(`.lora-card[data-filepath="${filePath}"]`);
            const previewContainer = card.querySelector('.card-preview');
            const oldPreview = previewContainer.querySelector('img, video');
            
            const previewUrl = `${data.preview_url}?t=${state.previewVersions.get(filePath)}`;
            
            if (file.type.startsWith('video/')) {
                const video = document.createElement('video');
                video.controls = true;
                video.autoplay = true;
                video.muted = true;
                video.loop = true;
                video.src = previewUrl;
                oldPreview.replaceWith(video);
            } else {
                const img = document.createElement('img');
                img.src = previewUrl;
                oldPreview.replaceWith(img);
            }
            
        } catch (error) {
            console.error('Error uploading preview:', error);
            alert('Failed to upload preview image');
        } finally {
            loadingOverlay.style.display = 'none';
        }
    };
    
    input.click();
}

export function appendLoraCards(loras) {
    const grid = document.getElementById('loraGrid');
    const sentinel = document.getElementById('scroll-sentinel');
    
    loras.forEach(lora => {
        const card = createLoraCard(lora);
        if (sentinel) {
            grid.insertBefore(card, sentinel);
        } else {
            grid.appendChild(card);
        }
    });
}

export async function resetAndReload() {
    console.log('Resetting with state:', { ...state });
    
    state.currentPage = 1;
    state.hasMore = true;
    state.isLoading = false;
    
    const grid = document.getElementById('loraGrid');
    grid.innerHTML = '';
    
    const sentinel = document.createElement('div');
    sentinel.id = 'scroll-sentinel';
    grid.appendChild(sentinel);
    
    initializeInfiniteScroll();
    
    await loadMoreLoras();
}

export async function refreshLoras() {
    try {
        state.loadingManager.showSimpleLoading('Refreshing loras...');
        await resetAndReload();
        showToast('Refresh complete', 'success');
    } catch (error) {
        console.error('Refresh failed:', error);
        showToast('Failed to refresh loras', 'error');
    } finally {
        state.loadingManager.hide();
        state.loadingManager.restoreProgressBar();
    }
}

export async function fetchMetadata(filePath, sha256, provider = 'civitai') {
    const response = await fetch('/api/fetch-metadata', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            file_path: filePath,
            sha256: sha256,
            provider: provider
        })
    });
    
    if (!response.ok) {
        throw new Error('Failed to fetch metadata');
    }
    
    return response.json();
}