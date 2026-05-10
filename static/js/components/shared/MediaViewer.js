let activeViewer = null;

function createMediaElement(item) {
    const { url, type = 'image' } = item;
    if (type === 'video') {
        const el = document.createElement('video');
        el.controls = true;
        el.autoplay = true;
        el.loop = true;
        el.muted = true;
        el.className = 'media-viewer-media media-viewer-video';
        el.src = url;
        return el;
    }
    const el = document.createElement('img');
    el.className = 'media-viewer-media media-viewer-image';
    el.src = url;
    el.alt = 'Full size preview';
    el.draggable = false;
    return el;
}

function preloadAdjacent(items, index) {
    [index - 1, index + 1].forEach(i => {
        if (i >= 0 && i < items.length && items[i].type !== 'video') {
            const preload = new Image();
            preload.src = items[i].url;
        }
    });
}

export function openMediaViewer(arg1, arg2, arg3) {
    closeMediaViewer();

    let items, currentIndex, title = '';

    if (Array.isArray(arg1)) {
        items = arg1;
        currentIndex = typeof arg2 === 'number' ? arg2 : 0;
        title = (arg3 && arg3.title) || '';
    } else {
        items = [{ url: arg1, type: (arg2 && arg2.type) || 'image' }];
        currentIndex = 0;
        title = (arg2 && arg2.title) || '';
    }

    if (currentIndex < 0 || currentIndex >= items.length) currentIndex = 0;

    const overlay = document.createElement('div');
    overlay.className = 'media-viewer-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', title || 'Media viewer');

    const closeBtn = document.createElement('button');
    closeBtn.className = 'media-viewer-close';
    closeBtn.innerHTML = '<i class="fas fa-times"></i>';
    closeBtn.title = 'Close (Esc)';
    closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeMediaViewer();
    });

    const contentContainer = document.createElement('div');
    contentContainer.className = 'media-viewer-content-container';

    let mediaElement = createMediaElement(items[currentIndex]);
    contentContainer.appendChild(mediaElement);

    const hasNavigation = items.length > 1;

    const counter = document.createElement('div');
    counter.className = 'media-viewer-counter';
    counter.textContent = hasNavigation ? `${currentIndex + 1} / ${items.length}` : '';
    contentContainer.appendChild(counter);

    if (title) {
        const titleBar = document.createElement('div');
        titleBar.className = 'media-viewer-title';
        titleBar.textContent = title;
        contentContainer.appendChild(titleBar);
    }

    let prevBtn, nextBtn;
    if (hasNavigation) {
        prevBtn = document.createElement('button');
        prevBtn.className = 'media-viewer-nav media-viewer-prev';
        prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
        prevBtn.title = 'Previous (←)';
        nextBtn = document.createElement('button');
        nextBtn.className = 'media-viewer-nav media-viewer-next';
        nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
        nextBtn.title = 'Next (→)';

        const navigate = (delta) => {
            const newIndex = (currentIndex + delta + items.length) % items.length;
            currentIndex = newIndex;

            const oldMedia = contentContainer.querySelector('.media-viewer-media');
            const newMedia = createMediaElement(items[currentIndex]);

            if (oldMedia) {
                if (oldMedia.tagName === 'VIDEO') {
                    oldMedia.pause();
                    oldMedia.src = '';
                }
                oldMedia.replaceWith(newMedia);
            }
            mediaElement = newMedia;

            counter.textContent = `${currentIndex + 1} / ${items.length}`;
            preloadAdjacent(items, currentIndex);
        };

        prevBtn.addEventListener('click', (e) => { e.stopPropagation(); navigate(-1); });
        nextBtn.addEventListener('click', (e) => { e.stopPropagation(); navigate(1); });

        overlay.appendChild(prevBtn);
        overlay.appendChild(nextBtn);
    }

    overlay.appendChild(closeBtn);
    overlay.appendChild(contentContainer);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
        overlay.classList.add('active');
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeMediaViewer();
        }
    });

    const keyHandler = (e) => {
        if (e.key === 'Escape') {
            closeMediaViewer();
            return;
        }
        if (hasNavigation) {
            if (e.key === 'ArrowLeft') {
                e.stopPropagation();
                e.preventDefault();
                prevBtn.click();
                return;
            }
            if (e.key === 'ArrowRight') {
                e.stopPropagation();
                e.preventDefault();
                nextBtn.click();
                return;
            }
        }
    };
    document.addEventListener('keydown', keyHandler, true);

    activeViewer = { overlay, keyHandler };
    preloadAdjacent(items, currentIndex);

    if (items[currentIndex].type === 'video') {
        const recipeVideo = document.getElementById('recipeModalVideo');
        if (recipeVideo && !recipeVideo.paused) {
            recipeVideo.pause();
        }
    }
}

export function closeMediaViewer() {
    if (!activeViewer) return;

    const { overlay, keyHandler } = activeViewer;

    const video = overlay.querySelector('video');
    if (video) {
        video.pause();
        video.src = '';
    }

    const img = overlay.querySelector('img');
    if (img) {
        img.src = '';
    }

    document.removeEventListener('keydown', keyHandler, true);

    overlay.classList.remove('active');
    overlay.addEventListener('transitionend', () => {
        if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
    }, { once: true });

    setTimeout(() => {
        if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
    }, 500);

    activeViewer = null;
}

export function isMediaViewerOpen() {
    return activeViewer !== null;
}
