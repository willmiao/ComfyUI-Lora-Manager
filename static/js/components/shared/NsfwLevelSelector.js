import { getNSFWLevelName } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';

let selectorController = null;

function buildController(selectorElement) {
    if (!selectorElement) return null;

    const levelButtons = Array.from(selectorElement.querySelectorAll('.nsfw-level-btn'));
    const closeBtn = selectorElement.querySelector('.close-nsfw-selector');
    const currentLevelEl = selectorElement.querySelector('#currentNSFWLevel');

    let onSelect = null;
    let onClose = null;
    let isOpen = false;
    let ignoreNextOutside = false;

    const setLabel = (level, multipleLabel) => {
        if (!currentLevelEl) return;
        if (multipleLabel) {
            currentLevelEl.textContent = multipleLabel;
            return;
        }
        currentLevelEl.textContent = getNSFWLevelName(level);
    };

    const hide = () => {
        selectorElement.style.display = 'none';
        selectorElement.dataset.cardPath = '';
        isOpen = false;
        if (typeof onClose === 'function') {
            onClose();
        }
        onSelect = null;
        onClose = null;
    };

    const show = ({ currentLevel = 0, onSelect: selectCb, onClose: closeCb, multipleLabel = '', cardPath = '' } = {}) => {
        onSelect = selectCb || null;
        onClose = closeCb || null;
        isOpen = true;
        ignoreNextOutside = true; // ignore the click that triggered open
        selectorElement.dataset.cardPath = cardPath || '';

        // Position near center of viewport
        const viewportWidth = document.documentElement.clientWidth;
        const viewportHeight = document.documentElement.clientHeight;
        const rect = selectorElement.getBoundingClientRect();
        const finalX = Math.max((viewportWidth - rect.width) / 2, 0);
        const finalY = Math.max((viewportHeight - rect.height) / 2, 0);

        selectorElement.style.left = `${finalX}px`;
        selectorElement.style.top = `${finalY}px`;

        setLabel(currentLevel, multipleLabel);

        // Highlight selected level (if not showing multiple values)
        levelButtons.forEach((btn) => {
            const btnLevel = parseInt(btn.dataset.level || '0', 10);
            if (multipleLabel) {
                btn.classList.remove('active');
            } else if (btnLevel === currentLevel) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        selectorElement.style.display = 'block';
    };

    if (closeBtn) {
        closeBtn.addEventListener('click', hide);
    }

    document.addEventListener('click', (e) => {
        if (!isOpen) return;
        if (ignoreNextOutside) {
            ignoreNextOutside = false;
            return;
        }
        if (!selectorElement.contains(e.target)) {
            hide();
        }
    });

    levelButtons.forEach((btn) => {
        btn.addEventListener('click', async () => {
            if (!isOpen) return;
            const level = parseInt(btn.dataset.level || '0', 10);
            if (typeof onSelect === 'function') {
                try {
                    const result = await onSelect(level);
                    if (result === false) {
                        return;
                    }
                } catch (error) {
                    console.error('NSFW selector onSelect failed', error);
                    return;
                }
            }
            hide();
        });
    });

    const showMultiple = (labelKey = 'modals.contentRating.multiple') => {
        const fallback = 'Multiple values';
        const text = translate(labelKey, {}, fallback);
        show({ multipleLabel: text });
    };

    return {
        show,
        hide,
        showMultiple,
        isOpen: () => isOpen,
    };
}

export function getNsfwLevelSelector() {
    if (selectorController) {
        return selectorController;
    }

    const element = document.getElementById('nsfwLevelSelector');
    selectorController = buildController(element);
    return selectorController;
}
