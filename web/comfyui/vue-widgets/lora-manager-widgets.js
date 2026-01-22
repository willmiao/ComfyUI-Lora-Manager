(function() {
  "use strict";
  try {
    if (typeof document != "undefined") {
      var elementStyle = document.createElement("style");
      elementStyle.appendChild(document.createTextNode(`.filter-chip[data-v-7e36267d] {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: var(--comfy-input-bg);
  border: 1px solid var(--border-color);
  color: var(--fg-color);
  white-space: nowrap;
}
.filter-chip__text[data-v-7e36267d] {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.filter-chip__count[data-v-7e36267d] {
  opacity: 0.6;
  font-size: 10px;
}
.filter-chip__remove[data-v-7e36267d] {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 2px;
  padding: 0;
  background: transparent;
  border: none;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s;
}
.filter-chip__remove[data-v-7e36267d]:hover {
  opacity: 1;
}

/* Variants */
.filter-chip--include[data-v-7e36267d] {
  background: rgba(66, 153, 225, 0.15);
  border-color: rgba(66, 153, 225, 0.4);
  color: #4299e1;
}
.filter-chip--exclude[data-v-7e36267d] {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.4);
  color: #ef4444;
}
.filter-chip--neutral[data-v-7e36267d] {
  background: rgba(100, 100, 100, 0.3);
  border-color: rgba(150, 150, 150, 0.4);
  color: var(--fg-color);
}
.filter-chip--path[data-v-7e36267d] {
  background: rgba(30, 30, 30, 0.8);
  border-color: rgba(255, 255, 255, 0.15);
  color: var(--fg-color);
  font-family: monospace;
  font-size: 10px;
}

.edit-button[data-v-8da8aa4b] {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: transparent;
  border: none;
  color: var(--fg-color);
  font-size: 11px;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s;
  border-radius: 3px;
}
.edit-button[data-v-8da8aa4b]:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.05);
}
.edit-button__icon[data-v-8da8aa4b] {
  width: 10px;
  height: 10px;
}
.edit-button__text[data-v-8da8aa4b] {
  font-weight: 400;
}

.section[data-v-12f059e2] {
  margin-bottom: 16px;
}
.section__header[data-v-12f059e2] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section__title[data-v-12f059e2] {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}
.section__content[data-v-12f059e2] {
  min-height: 32px;
  display: flex;
  align-items: center;
}
.section__placeholder[data-v-12f059e2] {
  width: 100%;
  padding: 8px 12px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  box-sizing: border-box;
}
.section__chips[data-v-12f059e2] {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.section[data-v-b869b780] {
  margin-bottom: 16px;
}
.section__header[data-v-b869b780] {
  margin-bottom: 8px;
}
.section__title[data-v-b869b780] {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}
.section__columns[data-v-b869b780] {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.section__column[data-v-b869b780] {
  min-width: 0;
}
.section__column-header[data-v-b869b780] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.section__column-title[data-v-b869b780] {
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.section__column-title--include[data-v-b869b780] {
  color: #4299e1;
}
.section__column-title--exclude[data-v-b869b780] {
  color: #ef4444;
}
.section__column-content[data-v-b869b780] {
  min-height: 28px;
}
.section__empty[data-v-b869b780] {
  width: 100%;
  padding: 8px 12px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  box-sizing: border-box;
}
.section__chips[data-v-b869b780] {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.section[data-v-af9caf84] {
  margin-bottom: 16px;
}
.section__header[data-v-af9caf84] {
  margin-bottom: 8px;
}
.section__title[data-v-af9caf84] {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}
.section__columns[data-v-af9caf84] {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.section__column[data-v-af9caf84] {
  min-width: 0;
}
.section__column-header[data-v-af9caf84] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.section__column-title[data-v-af9caf84] {
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.section__column-title--include[data-v-af9caf84] {
  color: #4299e1;
}
.section__column-title--exclude[data-v-af9caf84] {
  color: #ef4444;
}
.section__edit-btn[data-v-af9caf84] {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.5;
  border-radius: 3px;
  padding: 0;
  transition: all 0.15s;
}
.section__edit-btn svg[data-v-af9caf84] {
  width: 12px;
  height: 12px;
}
.section__edit-btn[data-v-af9caf84]:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}
.section__edit-btn--include[data-v-af9caf84]:hover {
  color: #4299e1;
}
.section__edit-btn--exclude[data-v-af9caf84]:hover {
  color: #ef4444;
}
.section__content[data-v-af9caf84] {
  min-height: 22px;
}
.section__paths[data-v-af9caf84] {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 22px;
}
.section__empty[data-v-af9caf84] {
  font-size: 10px;
  color: var(--fg-color, #fff);
  opacity: 0.3;
  font-style: italic;
  min-height: 22px;
  display: flex;
  align-items: center;
}

.section[data-v-dea4adf6] {
  margin-bottom: 16px;
}
.section__header[data-v-dea4adf6] {
  margin-bottom: 8px;
}
.section__title[data-v-dea4adf6] {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
}
.section__toggles[data-v-dea4adf6] {
  display: flex;
  gap: 16px;
}
.toggle-item[data-v-dea4adf6] {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.toggle-item__label[data-v-dea4adf6] {
  font-size: 12px;
  color: var(--fg-color, #fff);
}
.toggle-switch[data-v-dea4adf6] {
  position: relative;
  width: 36px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}
.toggle-switch__track[data-v-dea4adf6] {
  position: absolute;
  inset: 0;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 10px;
  transition: all 0.2s;
}
.toggle-switch--active .toggle-switch__track[data-v-dea4adf6] {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
}
.toggle-switch__thumb[data-v-dea4adf6] {
  position: absolute;
  top: 3px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  transition: all 0.2s;
  opacity: 0.6;
}
.toggle-switch--active .toggle-switch__thumb[data-v-dea4adf6] {
  transform: translateX(16px);
  background: #4299e1;
  opacity: 1;
}
.toggle-switch:hover .toggle-switch__thumb[data-v-dea4adf6] {
  opacity: 1;
}

.preview[data-v-6a4b50a1] {
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #444);
  position: relative;
}
.preview__header[data-v-6a4b50a1] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: default;
}
.preview__title[data-v-6a4b50a1] {
  font-size: 12px;
  font-weight: 500;
  color: var(--fg-color, #fff);
}
.preview__refresh[data-v-6a4b50a1] {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.6;
  border-radius: 4px;
  transition: all 0.15s;
}
.preview__refresh[data-v-6a4b50a1]:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}
.preview__refresh[data-v-6a4b50a1]:disabled {
  cursor: not-allowed;
}
.preview__refresh-icon[data-v-6a4b50a1] {
  width: 14px;
  height: 14px;
}
.preview__refresh--loading .preview__refresh-icon[data-v-6a4b50a1] {
  animation: spin-6a4b50a1 1s linear infinite;
}
@keyframes spin-6a4b50a1 {
from { transform: rotate(0deg);
}
to { transform: rotate(360deg);
}
}

/* Tooltip styles */
.preview__tooltip[data-v-6a4b50a1] {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 8px;
  z-index: 100;
}
.preview__tooltip-content[data-v-6a4b50a1] {
  background: var(--comfy-menu-bg, #1a1a1a);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview__item[data-v-6a4b50a1] {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
}
.preview__thumb[data-v-6a4b50a1] {
  width: 28px;
  height: 28px;
  object-fit: cover;
  border-radius: 3px;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.2);
}
.preview__thumb--placeholder[data-v-6a4b50a1] {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-color, #fff);
  opacity: 0.2;
}
.preview__thumb--placeholder svg[data-v-6a4b50a1] {
  width: 14px;
  height: 14px;
}
.preview__name[data-v-6a4b50a1] {
  flex: 1;
  font-size: 11px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview__more[data-v-6a4b50a1] {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  padding: 4px;
}
.preview__empty[data-v-6a4b50a1] {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.4;
  text-align: center;
  padding: 8px 0 0 0;
}

/* Tooltip transitions */
.tooltip-enter-active[data-v-6a4b50a1],
.tooltip-leave-active[data-v-6a4b50a1] {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.tooltip-enter-from[data-v-6a4b50a1],
.tooltip-leave-to[data-v-6a4b50a1] {
  opacity: 0;
  transform: translateY(4px);
}

.summary-view[data-v-328e7526] {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.summary-view__filters[data-v-328e7526] {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  margin-right: -4px;
  /* Allow flex item to shrink below content size */
  min-height: 0;
}

.lora-pool-modal-backdrop[data-v-fce76ca8] {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(2px);
}
.lora-pool-modal[data-v-fce76ca8] {
  background: var(--comfy-menu-bg, #1a1a1a);
  border: 1px solid var(--border-color, #444);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  max-width: 400px;
  width: 90%;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}
.lora-pool-modal__header[data-v-fce76ca8] {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-color, #444);
}
.lora-pool-modal__title-container[data-v-fce76ca8] {
  flex: 1;
}
.lora-pool-modal__title[data-v-fce76ca8] {
  font-size: 16px;
  font-weight: 600;
  color: var(--fg-color, #fff);
  margin: 0;
}
.lora-pool-modal__subtitle[data-v-fce76ca8] {
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  margin: 4px 0 0 0;
}
.lora-pool-modal__close[data-v-fce76ca8] {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  font-size: 22px;
  cursor: pointer;
  opacity: 0.7;
  border-radius: 4px;
  line-height: 1;
  padding: 0;
  margin: -4px -4px 0 0;
}
.lora-pool-modal__close[data-v-fce76ca8]:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}
.lora-pool-modal__search[data-v-fce76ca8] {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #444);
}
.lora-pool-modal__body[data-v-fce76ca8] {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 16px;
}

/* Transitions */
.modal-enter-active[data-v-fce76ca8],
.modal-leave-active[data-v-fce76ca8] {
  transition: opacity 0.2s ease;
}
.modal-enter-from[data-v-fce76ca8],
.modal-leave-to[data-v-fce76ca8] {
  opacity: 0;
}
.modal-enter-active .lora-pool-modal[data-v-fce76ca8],
.modal-leave-active .lora-pool-modal[data-v-fce76ca8] {
  transition: transform 0.2s ease;
}
.modal-enter-from .lora-pool-modal[data-v-fce76ca8],
.modal-leave-to .lora-pool-modal[data-v-fce76ca8] {
  transform: scale(0.95);
}

.search-container[data-v-e02ca44a] {
  position: relative;
}
.search-icon[data-v-e02ca44a] {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}
.search-input[data-v-e02ca44a] {
  width: 100%;
  padding: 8px 12px 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
}
.search-input[data-v-e02ca44a]:focus {
  border-color: var(--fg-color, #fff);
}
.search-input[data-v-e02ca44a]::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}
.clear-button[data-v-e02ca44a] {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  opacity: 0.5;
  transition: opacity 0.15s;
}
.clear-button[data-v-e02ca44a]:hover {
  opacity: 0.8;
}
.clear-button svg[data-v-e02ca44a] {
  width: 12px;
  height: 12px;
  color: var(--fg-color, #fff);
}
.model-list[data-v-e02ca44a] {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.model-item[data-v-e02ca44a] {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.model-item[data-v-e02ca44a]:hover {
  background: var(--comfy-input-bg, #333);
}
.model-checkbox[data-v-e02ca44a] {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.model-checkbox-visual[data-v-e02ca44a] {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 4px;
  flex-shrink: 0;
  transition: all 0.15s;
}
.model-item:hover .model-checkbox-visual[data-v-e02ca44a] {
  border-color: var(--fg-color, #fff);
}
.model-checkbox:checked + .model-checkbox-visual[data-v-e02ca44a] {
  background: var(--fg-color, #fff);
  border-color: var(--fg-color, #fff);
}
.check-icon[data-v-e02ca44a] {
  width: 12px;
  height: 12px;
  color: var(--comfy-menu-bg, #1a1a1a);
}
.model-name[data-v-e02ca44a] {
  flex: 1;
  font-size: 13px;
  color: var(--fg-color, #fff);
}
.model-count[data-v-e02ca44a] {
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}
.no-results[data-v-e02ca44a] {
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}

.search-container[data-v-110d6f7d] {
  position: relative;
}
.search-icon[data-v-110d6f7d] {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}
.search-input[data-v-110d6f7d] {
  width: 100%;
  padding: 8px 12px 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
}
.search-input[data-v-110d6f7d]:focus {
  border-color: var(--fg-color, #fff);
}
.search-input[data-v-110d6f7d]::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}
.clear-button[data-v-110d6f7d] {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  opacity: 0.5;
  transition: opacity 0.15s;
}
.clear-button[data-v-110d6f7d]:hover {
  opacity: 0.8;
}
.clear-button svg[data-v-110d6f7d] {
  width: 12px;
  height: 12px;
  color: var(--fg-color, #fff);
}
.tags-container[data-v-110d6f7d] {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tag-chip[data-v-110d6f7d] {
  padding: 6px 12px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 16px;
  color: var(--fg-color, #fff);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

/* Default hover (gray for neutral) */
.tag-chip[data-v-110d6f7d]:hover:not(.tag-chip--selected) {
  border-color: rgba(226, 232, 240, 0.5);
  background: rgba(255, 255, 255, 0.05);
}

/* Include variant hover - blue tint */
.tags-modal--include .tag-chip[data-v-110d6f7d]:hover:not(.tag-chip--selected) {
  border-color: rgba(66, 153, 225, 0.4);
  background: rgba(66, 153, 225, 0.08);
}

/* Exclude variant hover - red tint */
.tags-modal--exclude .tag-chip[data-v-110d6f7d]:hover:not(.tag-chip--selected) {
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
}

/* Selected chips hover - slightly deepen the color */
.tags-modal--include .tag-chip--selected[data-v-110d6f7d]:hover {
  background: rgba(66, 153, 225, 0.25);
  border-color: rgba(66, 153, 225, 0.7);
}
.tags-modal--exclude .tag-chip--selected[data-v-110d6f7d]:hover {
  background: rgba(239, 68, 68, 0.25);
  border-color: rgba(239, 68, 68, 0.7);
}

/* Include variant - blue when selected */
.tags-modal--include .tag-chip--selected[data-v-110d6f7d],
.tag-chip--selected[data-v-110d6f7d] {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.6);
  color: #4299e1;
}

/* Exclude variant - red when selected */
.tags-modal--exclude .tag-chip--selected[data-v-110d6f7d] {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.6);
  color: #ef4444;
}
.no-results[data-v-110d6f7d] {
  width: 100%;
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}

.tree-node__item[data-v-90187dd4] {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.tree-node__item[data-v-90187dd4]:hover {
  background: var(--comfy-input-bg, #333);
}
.tree-node__toggle[data-v-90187dd4] {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-color, #fff);
  cursor: pointer;
  opacity: 0.5;
  padding: 0;
  flex-shrink: 0;
}
.tree-node__toggle[data-v-90187dd4]:hover {
  opacity: 1;
}
.tree-node__toggle-icon[data-v-90187dd4] {
  width: 10px;
  height: 10px;
  transition: transform 0.15s;
}
.tree-node__toggle-icon--expanded[data-v-90187dd4] {
  transform: rotate(90deg);
}
.tree-node__toggle-spacer[data-v-90187dd4] {
  width: 16px;
  flex-shrink: 0;
}
.tree-node__checkbox-label[data-v-90187dd4] {
  display: flex;
  align-items: center;
  cursor: pointer;
}
.tree-node__checkbox[data-v-90187dd4] {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.tree-node__checkbox-visual[data-v-90187dd4] {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #555);
  border-radius: 3px;
  flex-shrink: 0;
  transition: all 0.15s;
}
.tree-node__item:hover .tree-node__checkbox-visual[data-v-90187dd4] {
  border-color: var(--fg-color, #fff);
}
.tree-node__checkbox:checked + .tree-node__checkbox-visual--include[data-v-90187dd4] {
  background: #4299e1;
  border-color: #4299e1;
}
.tree-node__checkbox:checked + .tree-node__checkbox-visual--exclude[data-v-90187dd4] {
  background: #ef4444;
  border-color: #ef4444;
}
.tree-node__check-icon[data-v-90187dd4] {
  width: 10px;
  height: 10px;
  color: #fff;
}
.tree-node__folder-icon[data-v-90187dd4] {
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  flex-shrink: 0;
}
.tree-node__label[data-v-90187dd4] {
  flex: 1;
  font-size: 13px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-node__children[data-v-90187dd4] {
  /* Children already indented via padding */
}

.search-container[data-v-046dcbf4] {
  position: relative;
}
.search-icon[data-v-046dcbf4] {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 14px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}
.search-input[data-v-046dcbf4] {
  width: 100%;
  padding: 8px 12px 8px 32px;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  color: var(--fg-color, #fff);
  font-size: 13px;
  outline: none;
}
.search-input[data-v-046dcbf4]:focus {
  border-color: var(--fg-color, #fff);
}
.search-input[data-v-046dcbf4]::placeholder {
  color: var(--fg-color, #fff);
  opacity: 0.4;
}
.folder-tree[data-v-046dcbf4] {
  display: flex;
  flex-direction: column;
}
.no-results[data-v-046dcbf4] {
  padding: 20px;
  text-align: center;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  font-size: 13px;
}

.lora-pool-widget[data-v-7d3f681d] {
  padding: 12px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.last-used-preview[data-v-b940502e] {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 8px;
  z-index: 100;
  width: 280px;
}
.last-used-preview__content[data-v-b940502e] {
  background: var(--comfy-menu-bg, #1a1a1a);
  border: 1px solid var(--border-color, #444);
  border-radius: 6px;
  padding: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.last-used-preview__item[data-v-b940502e] {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  background: var(--comfy-input-bg, #333);
  border-radius: 6px;
}
.last-used-preview__thumb[data-v-b940502e] {
  width: 28px;
  height: 28px;
  object-fit: cover;
  border-radius: 3px;
  flex-shrink: 0;
  background: rgba(0, 0, 0, 0.2);
}
.last-used-preview__thumb--placeholder[data-v-b940502e] {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-color, #fff);
  opacity: 0.2;
}
.last-used-preview__thumb--placeholder svg[data-v-b940502e] {
  width: 14px;
  height: 14px;
}
.last-used-preview__info[data-v-b940502e] {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.last-used-preview__name[data-v-b940502e] {
  font-size: 11px;
  color: var(--fg-color, #fff);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.last-used-preview__strength[data-v-b940502e] {
  font-size: 10px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
}
.last-used-preview__more[data-v-b940502e] {
  font-size: 11px;
  color: var(--fg-color, #fff);
  opacity: 0.5;
  text-align: center;
  padding: 4px;
}

.single-slider[data-v-2db219ac] {
  position: relative;
  width: 100%;
  height: 24px;
  user-select: none;
  cursor: default !important;
  touch-action: none;
}
.single-slider.disabled[data-v-2db219ac] {
  opacity: 0.4;
  pointer-events: none;
}
.single-slider.is-dragging[data-v-2db219ac] {
  cursor: ew-resize !important;
}
.slider-track[data-v-2db219ac] {
  position: absolute;
  top: 12px;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  cursor: default !important;
}
.slider-track__bg[data-v-2db219ac] {
  position: absolute;
  inset: 0;
  background: rgba(66, 153, 225, 0.15);
  border-radius: 2px;
}
.slider-track__active[data-v-2db219ac] {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  background: rgba(66, 153, 225, 0.6);
  border-radius: 2px;
  transition: width 0.05s linear;
}
.slider-track__default[data-v-2db219ac] {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.1);
  border-radius: 2px;
}
.slider-handle[data-v-2db219ac] {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  cursor: ew-resize !important;
  z-index: 2;
  touch-action: none;
}
.slider-handle__thumb[data-v-2db219ac] {
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  position: absolute;
  top: 7px;
  left: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.15s ease;
}
.slider-handle:hover .slider-handle__thumb[data-v-2db219ac] {
  transform: scale(1.1);
}
.slider-handle:active .slider-handle__thumb[data-v-2db219ac] {
  transform: scale(1.15);
}
.slider-handle__value[data-v-2db219ac] {
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  color: var(--fg-color, #fff);
  opacity: 0.8;
  white-space: nowrap;
  pointer-events: none;
  line-height: 14px;
}

.dual-range-slider[data-v-05ce9afb] {
  position: relative;
  width: 100%;
  height: 24px;
  user-select: none;
  cursor: default !important;
  touch-action: none;
}
.dual-range-slider.disabled[data-v-05ce9afb] {
  opacity: 0.4;
  pointer-events: none;
}
.dual-range-slider.is-dragging[data-v-05ce9afb] {
  cursor: ew-resize !important;
}
.slider-track[data-v-05ce9afb] {
  position: absolute;
  top: 12px;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  cursor: default !important;
}
.slider-track__bg[data-v-05ce9afb] {
  position: absolute;
  inset: 0;
  background: rgba(66, 153, 225, 0.15);
  border-radius: 2px;
}
.slider-track__active[data-v-05ce9afb] {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.6);
  border-radius: 2px;
  transition: left 0.05s linear, width 0.05s linear;
}
.slider-track__default[data-v-05ce9afb] {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.1);
  border-radius: 2px;
}
.slider-track__segment[data-v-05ce9afb] {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.08);
  border-radius: 2px;
}
.slider-track__segment--expanded[data-v-05ce9afb] {
  background: rgba(66, 153, 225, 0.15);
}
.slider-track__segment[data-v-05ce9afb]:not(:last-child)::after {
  content: '';
  position: absolute;
  top: -1px;
  bottom: -1px;
  right: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.1);
}
.slider-handle[data-v-05ce9afb] {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  cursor: ew-resize !important;
  z-index: 2;
  touch-action: none;
}
.slider-handle__thumb[data-v-05ce9afb] {
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  position: absolute;
  top: 7px;
  left: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.15s ease;
}
.slider-handle:hover .slider-handle__thumb[data-v-05ce9afb] {
  transform: scale(1.1);
}
.slider-handle:active .slider-handle__thumb[data-v-05ce9afb] {
  transform: scale(1.15);
}
.slider-handle__value[data-v-05ce9afb] {
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  color: var(--fg-color, #fff);
  opacity: 0.8;
  white-space: nowrap;
  pointer-events: none;
  line-height: 14px;
}
.slider-handle--min .slider-handle__value[data-v-05ce9afb] {
  text-align: center;
}
.slider-handle--max .slider-handle__value[data-v-05ce9afb] {
  text-align: center;
}

.randomizer-settings[data-v-f7a531b6] {
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #e4e4e7;
}
.settings-header[data-v-f7a531b6] {
  margin-bottom: 8px;
}
.settings-title[data-v-f7a531b6] {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  margin: 0;
  text-transform: uppercase;
}
.setting-section[data-v-f7a531b6] {
  margin-bottom: 6px;
}
.setting-label[data-v-f7a531b6] {
  font-size: 13px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.8);
  display: block;
  margin-bottom: 8px;
}
.section-header-with-toggle[data-v-f7a531b6] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-header-with-toggle .setting-label[data-v-f7a531b6] {
  margin-bottom: 4px;
}

/* Count Mode Tabs */
.count-mode-tabs[data-v-f7a531b6] {
  display: flex;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 8px;
}
.count-mode-tab[data-v-f7a531b6] {
  flex: 1;
  position: relative;
  padding: 8px 12px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.count-mode-tab input[type="radio"][data-v-f7a531b6] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.count-mode-tab-label[data-v-f7a531b6] {
  font-size: 13px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.7);
  transition: all 0.2s ease;
}
.count-mode-tab:hover .count-mode-tab-label[data-v-f7a531b6] {
  color: rgba(226, 232, 240, 0.9);
}
.count-mode-tab.active .count-mode-tab-label[data-v-f7a531b6] {
  color: rgba(191, 219, 254, 1);
  font-weight: 600;
}
.count-mode-tab.active[data-v-f7a531b6] {
  background: rgba(66, 153, 225, 0.2);
}
.count-mode-tab.active[data-v-f7a531b6]::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(66, 153, 225, 0.9);
}
.slider-container[data-v-f7a531b6] {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  padding: 6px;
}
.slider-container--disabled[data-v-f7a531b6] {
  opacity: 0.5;
  pointer-events: none;
}

/* Toggle Switch (same style as LicenseSection) */
.toggle-switch[data-v-f7a531b6] {
  position: relative;
  width: 36px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}
.toggle-switch__track[data-v-f7a531b6] {
  position: absolute;
  inset: 0;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 10px;
  transition: all 0.2s;
}
.toggle-switch--active .toggle-switch__track[data-v-f7a531b6] {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
}
.toggle-switch__thumb[data-v-f7a531b6] {
  position: absolute;
  top: 3px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  transition: all 0.2s;
  opacity: 0.6;
}
.toggle-switch--active .toggle-switch__thumb[data-v-f7a531b6] {
  transform: translateX(16px);
  background: #4299e1;
  opacity: 1;
}
.toggle-switch:hover .toggle-switch__thumb[data-v-f7a531b6] {
  opacity: 1;
}

/* Roll buttons with tooltip container */
.roll-buttons-with-tooltip[data-v-f7a531b6] {
  position: relative;
}

/* Roll buttons container */
.roll-buttons[data-v-f7a531b6] {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 6px;
}
.roll-button[data-v-f7a531b6] {
  padding: 6px 8px;
  background: rgba(30, 30, 36, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #e4e4e7;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.roll-button[data-v-f7a531b6]:hover:not(:disabled) {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.4);
  color: #bfdbfe;
}
.roll-button.selected[data-v-f7a531b6] {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
  color: #e4e4e7;
  box-shadow: 0 0 0 1px rgba(66, 153, 225, 0.3);
}
.roll-button[data-v-f7a531b6]:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.roll-button__icon[data-v-f7a531b6] {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}
.roll-button__text[data-v-f7a531b6] {
  font-size: 12px;
  text-align: center;
  line-height: 1.2;
}

/* Tooltip transitions */
.tooltip-enter-active[data-v-f7a531b6],
.tooltip-leave-active[data-v-f7a531b6] {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.tooltip-enter-from[data-v-f7a531b6],
.tooltip-leave-to[data-v-f7a531b6] {
  opacity: 0;
  transform: translateY(4px);
}

.lora-randomizer-widget[data-v-45df1002] {
  padding: 6px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 6px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.cycler-settings[data-v-af73e0cf] {
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #e4e4e7;
}
.settings-header[data-v-af73e0cf] {
  margin-bottom: 8px;
}
.settings-title[data-v-af73e0cf] {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  margin: 0;
  text-transform: uppercase;
}
.setting-section[data-v-af73e0cf] {
  margin-bottom: 8px;
}
.setting-label[data-v-af73e0cf] {
  font-size: 13px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.8);
  display: block;
  margin-bottom: 6px;
}

/* Progress Display */
.progress-section[data-v-af73e0cf] {
  margin-bottom: 12px;
}
.progress-display[data-v-af73e0cf] {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.progress-info[data-v-af73e0cf] {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.progress-label[data-v-af73e0cf] {
  font-size: 10px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.progress-name[data-v-af73e0cf] {
  font-size: 13px;
  font-weight: 500;
  color: rgba(191, 219, 254, 1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.progress-counter[data-v-af73e0cf] {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-left: 12px;
  flex-shrink: 0;
}
.progress-index[data-v-af73e0cf] {
  font-size: 18px;
  font-weight: 600;
  color: rgba(66, 153, 225, 1);
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}
.progress-separator[data-v-af73e0cf] {
  font-size: 14px;
  color: rgba(226, 232, 240, 0.4);
  margin: 0 2px;
}
.progress-total[data-v-af73e0cf] {
  font-size: 14px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.6);
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}
.refresh-button[data-v-af73e0cf] {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-left: 8px;
  padding: 0;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: rgba(226, 232, 240, 0.6);
  cursor: pointer;
  transition: all 0.2s;
}
.refresh-button[data-v-af73e0cf]:hover:not(:disabled) {
  background: rgba(66, 153, 225, 0.2);
  border-color: rgba(66, 153, 225, 0.4);
  color: rgba(191, 219, 254, 1);
}
.refresh-button[data-v-af73e0cf]:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.refresh-icon[data-v-af73e0cf] {
  width: 14px;
  height: 14px;
}
.refresh-icon.spinning[data-v-af73e0cf] {
  animation: spin-af73e0cf 1s linear infinite;
}
@keyframes spin-af73e0cf {
from {
    transform: rotate(0deg);
}
to {
    transform: rotate(360deg);
}
}

/* Index Input */
.index-input-container[data-v-af73e0cf] {
  display: flex;
  align-items: center;
  gap: 8px;
}
.index-input[data-v-af73e0cf] {
  width: 80px;
  padding: 6px 10px;
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  color: #e4e4e7;
  font-size: 13px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
}
.index-input[data-v-af73e0cf]:focus {
  outline: none;
  border-color: rgba(66, 153, 225, 0.6);
}
.index-input[data-v-af73e0cf]:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.index-hint[data-v-af73e0cf] {
  font-size: 11px;
  color: rgba(226, 232, 240, 0.4);
}

/* Slider Container */
.slider-container[data-v-af73e0cf] {
  background: rgba(26, 32, 44, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.2);
  border-radius: 6px;
  padding: 6px;
}
.slider-container--disabled[data-v-af73e0cf] {
  opacity: 0.5;
  pointer-events: none;
}
.section-header-with-toggle[data-v-af73e0cf] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-header-with-toggle .setting-label[data-v-af73e0cf] {
  margin-bottom: 4px;
}

/* Toggle Switch */
.toggle-switch[data-v-af73e0cf] {
  position: relative;
  width: 36px;
  height: 20px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}
.toggle-switch__track[data-v-af73e0cf] {
  position: absolute;
  inset: 0;
  background: var(--comfy-input-bg, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 10px;
  transition: all 0.2s;
}
.toggle-switch--active .toggle-switch__track[data-v-af73e0cf] {
  background: rgba(66, 153, 225, 0.3);
  border-color: rgba(66, 153, 225, 0.6);
}
.toggle-switch__thumb[data-v-af73e0cf] {
  position: absolute;
  top: 3px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  transition: all 0.2s;
  opacity: 0.6;
}
.toggle-switch--active .toggle-switch__thumb[data-v-af73e0cf] {
  transform: translateX(16px);
  background: #4299e1;
  opacity: 1;
}
.toggle-switch:hover .toggle-switch__thumb[data-v-af73e0cf] {
  opacity: 1;
}

.lora-cycler-widget[data-v-95dec8bd] {
  padding: 6px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 6px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.json-display-widget[data-v-0f202476] {
  padding: 8px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 6px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
.json-content[data-v-0f202476] {
  flex: 1;
  overflow: auto;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: rgba(226, 232, 240, 0.9);
}
.json-content pre[data-v-0f202476] {
  margin: 0;
  padding: 0;
}
.placeholder[data-v-0f202476] {
  font-style: italic;
  color: rgba(226, 232, 240, 0.6);
  text-align: center;
  padding: 20px 0;
}`));
      document.head.appendChild(elementStyle);
    }
  } catch (e) {
    console.error("vite-plugin-css-injected-by-js", e);
  }
})();
import { app as app$1 } from "../../../scripts/app.js";
/**
* @vue/shared v3.5.26
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
// @__NO_SIDE_EFFECTS__
function makeMap(str) {
  const map = /* @__PURE__ */ Object.create(null);
  for (const key of str.split(",")) map[key] = 1;
  return (val) => val in map;
}
const EMPTY_OBJ = {};
const EMPTY_ARR = [];
const NOOP = () => {
};
const NO = () => false;
const isOn = (key) => key.charCodeAt(0) === 111 && key.charCodeAt(1) === 110 && // uppercase letter
(key.charCodeAt(2) > 122 || key.charCodeAt(2) < 97);
const isModelListener = (key) => key.startsWith("onUpdate:");
const extend = Object.assign;
const remove = (arr, el) => {
  const i2 = arr.indexOf(el);
  if (i2 > -1) {
    arr.splice(i2, 1);
  }
};
const hasOwnProperty$1 = Object.prototype.hasOwnProperty;
const hasOwn = (val, key) => hasOwnProperty$1.call(val, key);
const isArray = Array.isArray;
const isMap = (val) => toTypeString(val) === "[object Map]";
const isSet = (val) => toTypeString(val) === "[object Set]";
const isFunction = (val) => typeof val === "function";
const isString = (val) => typeof val === "string";
const isSymbol = (val) => typeof val === "symbol";
const isObject = (val) => val !== null && typeof val === "object";
const isPromise = (val) => {
  return (isObject(val) || isFunction(val)) && isFunction(val.then) && isFunction(val.catch);
};
const objectToString = Object.prototype.toString;
const toTypeString = (value) => objectToString.call(value);
const toRawType = (value) => {
  return toTypeString(value).slice(8, -1);
};
const isPlainObject = (val) => toTypeString(val) === "[object Object]";
const isIntegerKey = (key) => isString(key) && key !== "NaN" && key[0] !== "-" && "" + parseInt(key, 10) === key;
const isReservedProp = /* @__PURE__ */ makeMap(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
);
const cacheStringFunction = (fn) => {
  const cache = /* @__PURE__ */ Object.create(null);
  return ((str) => {
    const hit = cache[str];
    return hit || (cache[str] = fn(str));
  });
};
const camelizeRE = /-\w/g;
const camelize = cacheStringFunction(
  (str) => {
    return str.replace(camelizeRE, (c2) => c2.slice(1).toUpperCase());
  }
);
const hyphenateRE = /\B([A-Z])/g;
const hyphenate = cacheStringFunction(
  (str) => str.replace(hyphenateRE, "-$1").toLowerCase()
);
const capitalize = cacheStringFunction((str) => {
  return str.charAt(0).toUpperCase() + str.slice(1);
});
const toHandlerKey = cacheStringFunction(
  (str) => {
    const s2 = str ? `on${capitalize(str)}` : ``;
    return s2;
  }
);
const hasChanged = (value, oldValue) => !Object.is(value, oldValue);
const invokeArrayFns = (fns, ...arg) => {
  for (let i2 = 0; i2 < fns.length; i2++) {
    fns[i2](...arg);
  }
};
const def = (obj, key, value, writable = false) => {
  Object.defineProperty(obj, key, {
    configurable: true,
    enumerable: false,
    writable,
    value
  });
};
const looseToNumber = (val) => {
  const n = parseFloat(val);
  return isNaN(n) ? val : n;
};
const toNumber = (val) => {
  const n = isString(val) ? Number(val) : NaN;
  return isNaN(n) ? val : n;
};
let _globalThis;
const getGlobalThis = () => {
  return _globalThis || (_globalThis = typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : typeof global !== "undefined" ? global : {});
};
function normalizeStyle(value) {
  if (isArray(value)) {
    const res = {};
    for (let i2 = 0; i2 < value.length; i2++) {
      const item = value[i2];
      const normalized = isString(item) ? parseStringStyle(item) : normalizeStyle(item);
      if (normalized) {
        for (const key in normalized) {
          res[key] = normalized[key];
        }
      }
    }
    return res;
  } else if (isString(value) || isObject(value)) {
    return value;
  }
}
const listDelimiterRE = /;(?![^(]*\))/g;
const propertyDelimiterRE = /:([^]+)/;
const styleCommentRE = /\/\*[^]*?\*\//g;
function parseStringStyle(cssText) {
  const ret = {};
  cssText.replace(styleCommentRE, "").split(listDelimiterRE).forEach((item) => {
    if (item) {
      const tmp = item.split(propertyDelimiterRE);
      tmp.length > 1 && (ret[tmp[0].trim()] = tmp[1].trim());
    }
  });
  return ret;
}
function normalizeClass(value) {
  let res = "";
  if (isString(value)) {
    res = value;
  } else if (isArray(value)) {
    for (let i2 = 0; i2 < value.length; i2++) {
      const normalized = normalizeClass(value[i2]);
      if (normalized) {
        res += normalized + " ";
      }
    }
  } else if (isObject(value)) {
    for (const name in value) {
      if (value[name]) {
        res += name + " ";
      }
    }
  }
  return res.trim();
}
const specialBooleanAttrs = `itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,readonly`;
const isSpecialBooleanAttr = /* @__PURE__ */ makeMap(specialBooleanAttrs);
function includeBooleanAttr(value) {
  return !!value || value === "";
}
const isRef$1 = (val) => {
  return !!(val && val["__v_isRef"] === true);
};
const toDisplayString = (val) => {
  return isString(val) ? val : val == null ? "" : isArray(val) || isObject(val) && (val.toString === objectToString || !isFunction(val.toString)) ? isRef$1(val) ? toDisplayString(val.value) : JSON.stringify(val, replacer, 2) : String(val);
};
const replacer = (_key, val) => {
  if (isRef$1(val)) {
    return replacer(_key, val.value);
  } else if (isMap(val)) {
    return {
      [`Map(${val.size})`]: [...val.entries()].reduce(
        (entries, [key, val2], i2) => {
          entries[stringifySymbol(key, i2) + " =>"] = val2;
          return entries;
        },
        {}
      )
    };
  } else if (isSet(val)) {
    return {
      [`Set(${val.size})`]: [...val.values()].map((v2) => stringifySymbol(v2))
    };
  } else if (isSymbol(val)) {
    return stringifySymbol(val);
  } else if (isObject(val) && !isArray(val) && !isPlainObject(val)) {
    return String(val);
  }
  return val;
};
const stringifySymbol = (v2, i2 = "") => {
  var _a;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    isSymbol(v2) ? `Symbol(${(_a = v2.description) != null ? _a : i2})` : v2
  );
};
/**
* @vue/reactivity v3.5.26
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let activeEffectScope;
class EffectScope {
  constructor(detached = false) {
    this.detached = detached;
    this._active = true;
    this._on = 0;
    this.effects = [];
    this.cleanups = [];
    this._isPaused = false;
    this.parent = activeEffectScope;
    if (!detached && activeEffectScope) {
      this.index = (activeEffectScope.scopes || (activeEffectScope.scopes = [])).push(
        this
      ) - 1;
    }
  }
  get active() {
    return this._active;
  }
  pause() {
    if (this._active) {
      this._isPaused = true;
      let i2, l2;
      if (this.scopes) {
        for (i2 = 0, l2 = this.scopes.length; i2 < l2; i2++) {
          this.scopes[i2].pause();
        }
      }
      for (i2 = 0, l2 = this.effects.length; i2 < l2; i2++) {
        this.effects[i2].pause();
      }
    }
  }
  /**
   * Resumes the effect scope, including all child scopes and effects.
   */
  resume() {
    if (this._active) {
      if (this._isPaused) {
        this._isPaused = false;
        let i2, l2;
        if (this.scopes) {
          for (i2 = 0, l2 = this.scopes.length; i2 < l2; i2++) {
            this.scopes[i2].resume();
          }
        }
        for (i2 = 0, l2 = this.effects.length; i2 < l2; i2++) {
          this.effects[i2].resume();
        }
      }
    }
  }
  run(fn) {
    if (this._active) {
      const currentEffectScope = activeEffectScope;
      try {
        activeEffectScope = this;
        return fn();
      } finally {
        activeEffectScope = currentEffectScope;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    if (++this._on === 1) {
      this.prevScope = activeEffectScope;
      activeEffectScope = this;
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    if (this._on > 0 && --this._on === 0) {
      activeEffectScope = this.prevScope;
      this.prevScope = void 0;
    }
  }
  stop(fromParent) {
    if (this._active) {
      this._active = false;
      let i2, l2;
      for (i2 = 0, l2 = this.effects.length; i2 < l2; i2++) {
        this.effects[i2].stop();
      }
      this.effects.length = 0;
      for (i2 = 0, l2 = this.cleanups.length; i2 < l2; i2++) {
        this.cleanups[i2]();
      }
      this.cleanups.length = 0;
      if (this.scopes) {
        for (i2 = 0, l2 = this.scopes.length; i2 < l2; i2++) {
          this.scopes[i2].stop(true);
        }
        this.scopes.length = 0;
      }
      if (!this.detached && this.parent && !fromParent) {
        const last = this.parent.scopes.pop();
        if (last && last !== this) {
          this.parent.scopes[this.index] = last;
          last.index = this.index;
        }
      }
      this.parent = void 0;
    }
  }
}
function getCurrentScope() {
  return activeEffectScope;
}
let activeSub;
const pausedQueueEffects = /* @__PURE__ */ new WeakSet();
class ReactiveEffect {
  constructor(fn) {
    this.fn = fn;
    this.deps = void 0;
    this.depsTail = void 0;
    this.flags = 1 | 4;
    this.next = void 0;
    this.cleanup = void 0;
    this.scheduler = void 0;
    if (activeEffectScope && activeEffectScope.active) {
      activeEffectScope.effects.push(this);
    }
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    if (this.flags & 64) {
      this.flags &= -65;
      if (pausedQueueEffects.has(this)) {
        pausedQueueEffects.delete(this);
        this.trigger();
      }
    }
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags & 2 && !(this.flags & 32)) {
      return;
    }
    if (!(this.flags & 8)) {
      batch(this);
    }
  }
  run() {
    if (!(this.flags & 1)) {
      return this.fn();
    }
    this.flags |= 2;
    cleanupEffect(this);
    prepareDeps(this);
    const prevEffect = activeSub;
    const prevShouldTrack = shouldTrack;
    activeSub = this;
    shouldTrack = true;
    try {
      return this.fn();
    } finally {
      cleanupDeps(this);
      activeSub = prevEffect;
      shouldTrack = prevShouldTrack;
      this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let link = this.deps; link; link = link.nextDep) {
        removeSub(link);
      }
      this.deps = this.depsTail = void 0;
      cleanupEffect(this);
      this.onStop && this.onStop();
      this.flags &= -2;
    }
  }
  trigger() {
    if (this.flags & 64) {
      pausedQueueEffects.add(this);
    } else if (this.scheduler) {
      this.scheduler();
    } else {
      this.runIfDirty();
    }
  }
  /**
   * @internal
   */
  runIfDirty() {
    if (isDirty(this)) {
      this.run();
    }
  }
  get dirty() {
    return isDirty(this);
  }
}
let batchDepth = 0;
let batchedSub;
let batchedComputed;
function batch(sub, isComputed = false) {
  sub.flags |= 8;
  if (isComputed) {
    sub.next = batchedComputed;
    batchedComputed = sub;
    return;
  }
  sub.next = batchedSub;
  batchedSub = sub;
}
function startBatch() {
  batchDepth++;
}
function endBatch() {
  if (--batchDepth > 0) {
    return;
  }
  if (batchedComputed) {
    let e = batchedComputed;
    batchedComputed = void 0;
    while (e) {
      const next = e.next;
      e.next = void 0;
      e.flags &= -9;
      e = next;
    }
  }
  let error;
  while (batchedSub) {
    let e = batchedSub;
    batchedSub = void 0;
    while (e) {
      const next = e.next;
      e.next = void 0;
      e.flags &= -9;
      if (e.flags & 1) {
        try {
          ;
          e.trigger();
        } catch (err) {
          if (!error) error = err;
        }
      }
      e = next;
    }
  }
  if (error) throw error;
}
function prepareDeps(sub) {
  for (let link = sub.deps; link; link = link.nextDep) {
    link.version = -1;
    link.prevActiveLink = link.dep.activeLink;
    link.dep.activeLink = link;
  }
}
function cleanupDeps(sub) {
  let head;
  let tail = sub.depsTail;
  let link = tail;
  while (link) {
    const prev = link.prevDep;
    if (link.version === -1) {
      if (link === tail) tail = prev;
      removeSub(link);
      removeDep(link);
    } else {
      head = link;
    }
    link.dep.activeLink = link.prevActiveLink;
    link.prevActiveLink = void 0;
    link = prev;
  }
  sub.deps = head;
  sub.depsTail = tail;
}
function isDirty(sub) {
  for (let link = sub.deps; link; link = link.nextDep) {
    if (link.dep.version !== link.version || link.dep.computed && (refreshComputed(link.dep.computed) || link.dep.version !== link.version)) {
      return true;
    }
  }
  if (sub._dirty) {
    return true;
  }
  return false;
}
function refreshComputed(computed2) {
  if (computed2.flags & 4 && !(computed2.flags & 16)) {
    return;
  }
  computed2.flags &= -17;
  if (computed2.globalVersion === globalVersion) {
    return;
  }
  computed2.globalVersion = globalVersion;
  if (!computed2.isSSR && computed2.flags & 128 && (!computed2.deps && !computed2._dirty || !isDirty(computed2))) {
    return;
  }
  computed2.flags |= 2;
  const dep = computed2.dep;
  const prevSub = activeSub;
  const prevShouldTrack = shouldTrack;
  activeSub = computed2;
  shouldTrack = true;
  try {
    prepareDeps(computed2);
    const value = computed2.fn(computed2._value);
    if (dep.version === 0 || hasChanged(value, computed2._value)) {
      computed2.flags |= 128;
      computed2._value = value;
      dep.version++;
    }
  } catch (err) {
    dep.version++;
    throw err;
  } finally {
    activeSub = prevSub;
    shouldTrack = prevShouldTrack;
    cleanupDeps(computed2);
    computed2.flags &= -3;
  }
}
function removeSub(link, soft = false) {
  const { dep, prevSub, nextSub } = link;
  if (prevSub) {
    prevSub.nextSub = nextSub;
    link.prevSub = void 0;
  }
  if (nextSub) {
    nextSub.prevSub = prevSub;
    link.nextSub = void 0;
  }
  if (dep.subs === link) {
    dep.subs = prevSub;
    if (!prevSub && dep.computed) {
      dep.computed.flags &= -5;
      for (let l2 = dep.computed.deps; l2; l2 = l2.nextDep) {
        removeSub(l2, true);
      }
    }
  }
  if (!soft && !--dep.sc && dep.map) {
    dep.map.delete(dep.key);
  }
}
function removeDep(link) {
  const { prevDep, nextDep } = link;
  if (prevDep) {
    prevDep.nextDep = nextDep;
    link.prevDep = void 0;
  }
  if (nextDep) {
    nextDep.prevDep = prevDep;
    link.nextDep = void 0;
  }
}
let shouldTrack = true;
const trackStack = [];
function pauseTracking() {
  trackStack.push(shouldTrack);
  shouldTrack = false;
}
function resetTracking() {
  const last = trackStack.pop();
  shouldTrack = last === void 0 ? true : last;
}
function cleanupEffect(e) {
  const { cleanup } = e;
  e.cleanup = void 0;
  if (cleanup) {
    const prevSub = activeSub;
    activeSub = void 0;
    try {
      cleanup();
    } finally {
      activeSub = prevSub;
    }
  }
}
let globalVersion = 0;
class Link {
  constructor(sub, dep) {
    this.sub = sub;
    this.dep = dep;
    this.version = dep.version;
    this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Dep {
  // TODO isolatedDeclarations "__v_skip"
  constructor(computed2) {
    this.computed = computed2;
    this.version = 0;
    this.activeLink = void 0;
    this.subs = void 0;
    this.map = void 0;
    this.key = void 0;
    this.sc = 0;
    this.__v_skip = true;
  }
  track(debugInfo) {
    if (!activeSub || !shouldTrack || activeSub === this.computed) {
      return;
    }
    let link = this.activeLink;
    if (link === void 0 || link.sub !== activeSub) {
      link = this.activeLink = new Link(activeSub, this);
      if (!activeSub.deps) {
        activeSub.deps = activeSub.depsTail = link;
      } else {
        link.prevDep = activeSub.depsTail;
        activeSub.depsTail.nextDep = link;
        activeSub.depsTail = link;
      }
      addSub(link);
    } else if (link.version === -1) {
      link.version = this.version;
      if (link.nextDep) {
        const next = link.nextDep;
        next.prevDep = link.prevDep;
        if (link.prevDep) {
          link.prevDep.nextDep = next;
        }
        link.prevDep = activeSub.depsTail;
        link.nextDep = void 0;
        activeSub.depsTail.nextDep = link;
        activeSub.depsTail = link;
        if (activeSub.deps === link) {
          activeSub.deps = next;
        }
      }
    }
    return link;
  }
  trigger(debugInfo) {
    this.version++;
    globalVersion++;
    this.notify(debugInfo);
  }
  notify(debugInfo) {
    startBatch();
    try {
      if (false) ;
      for (let link = this.subs; link; link = link.prevSub) {
        if (link.sub.notify()) {
          ;
          link.sub.dep.notify();
        }
      }
    } finally {
      endBatch();
    }
  }
}
function addSub(link) {
  link.dep.sc++;
  if (link.sub.flags & 4) {
    const computed2 = link.dep.computed;
    if (computed2 && !link.dep.subs) {
      computed2.flags |= 4 | 16;
      for (let l2 = computed2.deps; l2; l2 = l2.nextDep) {
        addSub(l2);
      }
    }
    const currentTail = link.dep.subs;
    if (currentTail !== link) {
      link.prevSub = currentTail;
      if (currentTail) currentTail.nextSub = link;
    }
    link.dep.subs = link;
  }
}
const targetMap = /* @__PURE__ */ new WeakMap();
const ITERATE_KEY = /* @__PURE__ */ Symbol(
  ""
);
const MAP_KEY_ITERATE_KEY = /* @__PURE__ */ Symbol(
  ""
);
const ARRAY_ITERATE_KEY = /* @__PURE__ */ Symbol(
  ""
);
function track(target, type, key) {
  if (shouldTrack && activeSub) {
    let depsMap = targetMap.get(target);
    if (!depsMap) {
      targetMap.set(target, depsMap = /* @__PURE__ */ new Map());
    }
    let dep = depsMap.get(key);
    if (!dep) {
      depsMap.set(key, dep = new Dep());
      dep.map = depsMap;
      dep.key = key;
    }
    {
      dep.track();
    }
  }
}
function trigger(target, type, key, newValue, oldValue, oldTarget) {
  const depsMap = targetMap.get(target);
  if (!depsMap) {
    globalVersion++;
    return;
  }
  const run = (dep) => {
    if (dep) {
      {
        dep.trigger();
      }
    }
  };
  startBatch();
  if (type === "clear") {
    depsMap.forEach(run);
  } else {
    const targetIsArray = isArray(target);
    const isArrayIndex = targetIsArray && isIntegerKey(key);
    if (targetIsArray && key === "length") {
      const newLength = Number(newValue);
      depsMap.forEach((dep, key2) => {
        if (key2 === "length" || key2 === ARRAY_ITERATE_KEY || !isSymbol(key2) && key2 >= newLength) {
          run(dep);
        }
      });
    } else {
      if (key !== void 0 || depsMap.has(void 0)) {
        run(depsMap.get(key));
      }
      if (isArrayIndex) {
        run(depsMap.get(ARRAY_ITERATE_KEY));
      }
      switch (type) {
        case "add":
          if (!targetIsArray) {
            run(depsMap.get(ITERATE_KEY));
            if (isMap(target)) {
              run(depsMap.get(MAP_KEY_ITERATE_KEY));
            }
          } else if (isArrayIndex) {
            run(depsMap.get("length"));
          }
          break;
        case "delete":
          if (!targetIsArray) {
            run(depsMap.get(ITERATE_KEY));
            if (isMap(target)) {
              run(depsMap.get(MAP_KEY_ITERATE_KEY));
            }
          }
          break;
        case "set":
          if (isMap(target)) {
            run(depsMap.get(ITERATE_KEY));
          }
          break;
      }
    }
  }
  endBatch();
}
function reactiveReadArray(array) {
  const raw = toRaw(array);
  if (raw === array) return raw;
  track(raw, "iterate", ARRAY_ITERATE_KEY);
  return isShallow(array) ? raw : raw.map(toReactive);
}
function shallowReadArray(arr) {
  track(arr = toRaw(arr), "iterate", ARRAY_ITERATE_KEY);
  return arr;
}
function toWrapped(target, item) {
  if (isReadonly(target)) {
    return isReactive(target) ? toReadonly(toReactive(item)) : toReadonly(item);
  }
  return toReactive(item);
}
const arrayInstrumentations = {
  __proto__: null,
  [Symbol.iterator]() {
    return iterator(this, Symbol.iterator, (item) => toWrapped(this, item));
  },
  concat(...args) {
    return reactiveReadArray(this).concat(
      ...args.map((x) => isArray(x) ? reactiveReadArray(x) : x)
    );
  },
  entries() {
    return iterator(this, "entries", (value) => {
      value[1] = toWrapped(this, value[1]);
      return value;
    });
  },
  every(fn, thisArg) {
    return apply(this, "every", fn, thisArg, void 0, arguments);
  },
  filter(fn, thisArg) {
    return apply(
      this,
      "filter",
      fn,
      thisArg,
      (v2) => v2.map((item) => toWrapped(this, item)),
      arguments
    );
  },
  find(fn, thisArg) {
    return apply(
      this,
      "find",
      fn,
      thisArg,
      (item) => toWrapped(this, item),
      arguments
    );
  },
  findIndex(fn, thisArg) {
    return apply(this, "findIndex", fn, thisArg, void 0, arguments);
  },
  findLast(fn, thisArg) {
    return apply(
      this,
      "findLast",
      fn,
      thisArg,
      (item) => toWrapped(this, item),
      arguments
    );
  },
  findLastIndex(fn, thisArg) {
    return apply(this, "findLastIndex", fn, thisArg, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(fn, thisArg) {
    return apply(this, "forEach", fn, thisArg, void 0, arguments);
  },
  includes(...args) {
    return searchProxy(this, "includes", args);
  },
  indexOf(...args) {
    return searchProxy(this, "indexOf", args);
  },
  join(separator) {
    return reactiveReadArray(this).join(separator);
  },
  // keys() iterator only reads `length`, no optimization required
  lastIndexOf(...args) {
    return searchProxy(this, "lastIndexOf", args);
  },
  map(fn, thisArg) {
    return apply(this, "map", fn, thisArg, void 0, arguments);
  },
  pop() {
    return noTracking(this, "pop");
  },
  push(...args) {
    return noTracking(this, "push", args);
  },
  reduce(fn, ...args) {
    return reduce(this, "reduce", fn, args);
  },
  reduceRight(fn, ...args) {
    return reduce(this, "reduceRight", fn, args);
  },
  shift() {
    return noTracking(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(fn, thisArg) {
    return apply(this, "some", fn, thisArg, void 0, arguments);
  },
  splice(...args) {
    return noTracking(this, "splice", args);
  },
  toReversed() {
    return reactiveReadArray(this).toReversed();
  },
  toSorted(comparer) {
    return reactiveReadArray(this).toSorted(comparer);
  },
  toSpliced(...args) {
    return reactiveReadArray(this).toSpliced(...args);
  },
  unshift(...args) {
    return noTracking(this, "unshift", args);
  },
  values() {
    return iterator(this, "values", (item) => toWrapped(this, item));
  }
};
function iterator(self2, method, wrapValue) {
  const arr = shallowReadArray(self2);
  const iter = arr[method]();
  if (arr !== self2 && !isShallow(self2)) {
    iter._next = iter.next;
    iter.next = () => {
      const result = iter._next();
      if (!result.done) {
        result.value = wrapValue(result.value);
      }
      return result;
    };
  }
  return iter;
}
const arrayProto = Array.prototype;
function apply(self2, method, fn, thisArg, wrappedRetFn, args) {
  const arr = shallowReadArray(self2);
  const needsWrap = arr !== self2 && !isShallow(self2);
  const methodFn = arr[method];
  if (methodFn !== arrayProto[method]) {
    const result2 = methodFn.apply(self2, args);
    return needsWrap ? toReactive(result2) : result2;
  }
  let wrappedFn = fn;
  if (arr !== self2) {
    if (needsWrap) {
      wrappedFn = function(item, index) {
        return fn.call(this, toWrapped(self2, item), index, self2);
      };
    } else if (fn.length > 2) {
      wrappedFn = function(item, index) {
        return fn.call(this, item, index, self2);
      };
    }
  }
  const result = methodFn.call(arr, wrappedFn, thisArg);
  return needsWrap && wrappedRetFn ? wrappedRetFn(result) : result;
}
function reduce(self2, method, fn, args) {
  const arr = shallowReadArray(self2);
  let wrappedFn = fn;
  if (arr !== self2) {
    if (!isShallow(self2)) {
      wrappedFn = function(acc, item, index) {
        return fn.call(this, acc, toWrapped(self2, item), index, self2);
      };
    } else if (fn.length > 3) {
      wrappedFn = function(acc, item, index) {
        return fn.call(this, acc, item, index, self2);
      };
    }
  }
  return arr[method](wrappedFn, ...args);
}
function searchProxy(self2, method, args) {
  const arr = toRaw(self2);
  track(arr, "iterate", ARRAY_ITERATE_KEY);
  const res = arr[method](...args);
  if ((res === -1 || res === false) && isProxy(args[0])) {
    args[0] = toRaw(args[0]);
    return arr[method](...args);
  }
  return res;
}
function noTracking(self2, method, args = []) {
  pauseTracking();
  startBatch();
  const res = toRaw(self2)[method].apply(self2, args);
  endBatch();
  resetTracking();
  return res;
}
const isNonTrackableKeys = /* @__PURE__ */ makeMap(`__proto__,__v_isRef,__isVue`);
const builtInSymbols = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((key) => key !== "arguments" && key !== "caller").map((key) => Symbol[key]).filter(isSymbol)
);
function hasOwnProperty(key) {
  if (!isSymbol(key)) key = String(key);
  const obj = toRaw(this);
  track(obj, "has", key);
  return obj.hasOwnProperty(key);
}
class BaseReactiveHandler {
  constructor(_isReadonly = false, _isShallow = false) {
    this._isReadonly = _isReadonly;
    this._isShallow = _isShallow;
  }
  get(target, key, receiver) {
    if (key === "__v_skip") return target["__v_skip"];
    const isReadonly2 = this._isReadonly, isShallow2 = this._isShallow;
    if (key === "__v_isReactive") {
      return !isReadonly2;
    } else if (key === "__v_isReadonly") {
      return isReadonly2;
    } else if (key === "__v_isShallow") {
      return isShallow2;
    } else if (key === "__v_raw") {
      if (receiver === (isReadonly2 ? isShallow2 ? shallowReadonlyMap : readonlyMap : isShallow2 ? shallowReactiveMap : reactiveMap).get(target) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(target) === Object.getPrototypeOf(receiver)) {
        return target;
      }
      return;
    }
    const targetIsArray = isArray(target);
    if (!isReadonly2) {
      let fn;
      if (targetIsArray && (fn = arrayInstrumentations[key])) {
        return fn;
      }
      if (key === "hasOwnProperty") {
        return hasOwnProperty;
      }
    }
    const res = Reflect.get(
      target,
      key,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      isRef(target) ? target : receiver
    );
    if (isSymbol(key) ? builtInSymbols.has(key) : isNonTrackableKeys(key)) {
      return res;
    }
    if (!isReadonly2) {
      track(target, "get", key);
    }
    if (isShallow2) {
      return res;
    }
    if (isRef(res)) {
      const value = targetIsArray && isIntegerKey(key) ? res : res.value;
      return isReadonly2 && isObject(value) ? readonly(value) : value;
    }
    if (isObject(res)) {
      return isReadonly2 ? readonly(res) : reactive(res);
    }
    return res;
  }
}
class MutableReactiveHandler extends BaseReactiveHandler {
  constructor(isShallow2 = false) {
    super(false, isShallow2);
  }
  set(target, key, value, receiver) {
    let oldValue = target[key];
    const isArrayWithIntegerKey = isArray(target) && isIntegerKey(key);
    if (!this._isShallow) {
      const isOldValueReadonly = isReadonly(oldValue);
      if (!isShallow(value) && !isReadonly(value)) {
        oldValue = toRaw(oldValue);
        value = toRaw(value);
      }
      if (!isArrayWithIntegerKey && isRef(oldValue) && !isRef(value)) {
        if (isOldValueReadonly) {
          return true;
        } else {
          oldValue.value = value;
          return true;
        }
      }
    }
    const hadKey = isArrayWithIntegerKey ? Number(key) < target.length : hasOwn(target, key);
    const result = Reflect.set(
      target,
      key,
      value,
      isRef(target) ? target : receiver
    );
    if (target === toRaw(receiver)) {
      if (!hadKey) {
        trigger(target, "add", key, value);
      } else if (hasChanged(value, oldValue)) {
        trigger(target, "set", key, value);
      }
    }
    return result;
  }
  deleteProperty(target, key) {
    const hadKey = hasOwn(target, key);
    target[key];
    const result = Reflect.deleteProperty(target, key);
    if (result && hadKey) {
      trigger(target, "delete", key, void 0);
    }
    return result;
  }
  has(target, key) {
    const result = Reflect.has(target, key);
    if (!isSymbol(key) || !builtInSymbols.has(key)) {
      track(target, "has", key);
    }
    return result;
  }
  ownKeys(target) {
    track(
      target,
      "iterate",
      isArray(target) ? "length" : ITERATE_KEY
    );
    return Reflect.ownKeys(target);
  }
}
class ReadonlyReactiveHandler extends BaseReactiveHandler {
  constructor(isShallow2 = false) {
    super(true, isShallow2);
  }
  set(target, key) {
    return true;
  }
  deleteProperty(target, key) {
    return true;
  }
}
const mutableHandlers = /* @__PURE__ */ new MutableReactiveHandler();
const readonlyHandlers = /* @__PURE__ */ new ReadonlyReactiveHandler();
const shallowReactiveHandlers = /* @__PURE__ */ new MutableReactiveHandler(true);
const shallowReadonlyHandlers = /* @__PURE__ */ new ReadonlyReactiveHandler(true);
const toShallow = (value) => value;
const getProto = (v2) => Reflect.getPrototypeOf(v2);
function createIterableMethod(method, isReadonly2, isShallow2) {
  return function(...args) {
    const target = this["__v_raw"];
    const rawTarget = toRaw(target);
    const targetIsMap = isMap(rawTarget);
    const isPair = method === "entries" || method === Symbol.iterator && targetIsMap;
    const isKeyOnly = method === "keys" && targetIsMap;
    const innerIterator = target[method](...args);
    const wrap = isShallow2 ? toShallow : isReadonly2 ? toReadonly : toReactive;
    !isReadonly2 && track(
      rawTarget,
      "iterate",
      isKeyOnly ? MAP_KEY_ITERATE_KEY : ITERATE_KEY
    );
    return {
      // iterator protocol
      next() {
        const { value, done } = innerIterator.next();
        return done ? { value, done } : {
          value: isPair ? [wrap(value[0]), wrap(value[1])] : wrap(value),
          done
        };
      },
      // iterable protocol
      [Symbol.iterator]() {
        return this;
      }
    };
  };
}
function createReadonlyMethod(type) {
  return function(...args) {
    return type === "delete" ? false : type === "clear" ? void 0 : this;
  };
}
function createInstrumentations(readonly2, shallow) {
  const instrumentations = {
    get(key) {
      const target = this["__v_raw"];
      const rawTarget = toRaw(target);
      const rawKey = toRaw(key);
      if (!readonly2) {
        if (hasChanged(key, rawKey)) {
          track(rawTarget, "get", key);
        }
        track(rawTarget, "get", rawKey);
      }
      const { has } = getProto(rawTarget);
      const wrap = shallow ? toShallow : readonly2 ? toReadonly : toReactive;
      if (has.call(rawTarget, key)) {
        return wrap(target.get(key));
      } else if (has.call(rawTarget, rawKey)) {
        return wrap(target.get(rawKey));
      } else if (target !== rawTarget) {
        target.get(key);
      }
    },
    get size() {
      const target = this["__v_raw"];
      !readonly2 && track(toRaw(target), "iterate", ITERATE_KEY);
      return target.size;
    },
    has(key) {
      const target = this["__v_raw"];
      const rawTarget = toRaw(target);
      const rawKey = toRaw(key);
      if (!readonly2) {
        if (hasChanged(key, rawKey)) {
          track(rawTarget, "has", key);
        }
        track(rawTarget, "has", rawKey);
      }
      return key === rawKey ? target.has(key) : target.has(key) || target.has(rawKey);
    },
    forEach(callback, thisArg) {
      const observed = this;
      const target = observed["__v_raw"];
      const rawTarget = toRaw(target);
      const wrap = shallow ? toShallow : readonly2 ? toReadonly : toReactive;
      !readonly2 && track(rawTarget, "iterate", ITERATE_KEY);
      return target.forEach((value, key) => {
        return callback.call(thisArg, wrap(value), wrap(key), observed);
      });
    }
  };
  extend(
    instrumentations,
    readonly2 ? {
      add: createReadonlyMethod("add"),
      set: createReadonlyMethod("set"),
      delete: createReadonlyMethod("delete"),
      clear: createReadonlyMethod("clear")
    } : {
      add(value) {
        if (!shallow && !isShallow(value) && !isReadonly(value)) {
          value = toRaw(value);
        }
        const target = toRaw(this);
        const proto = getProto(target);
        const hadKey = proto.has.call(target, value);
        if (!hadKey) {
          target.add(value);
          trigger(target, "add", value, value);
        }
        return this;
      },
      set(key, value) {
        if (!shallow && !isShallow(value) && !isReadonly(value)) {
          value = toRaw(value);
        }
        const target = toRaw(this);
        const { has, get } = getProto(target);
        let hadKey = has.call(target, key);
        if (!hadKey) {
          key = toRaw(key);
          hadKey = has.call(target, key);
        }
        const oldValue = get.call(target, key);
        target.set(key, value);
        if (!hadKey) {
          trigger(target, "add", key, value);
        } else if (hasChanged(value, oldValue)) {
          trigger(target, "set", key, value);
        }
        return this;
      },
      delete(key) {
        const target = toRaw(this);
        const { has, get } = getProto(target);
        let hadKey = has.call(target, key);
        if (!hadKey) {
          key = toRaw(key);
          hadKey = has.call(target, key);
        }
        get ? get.call(target, key) : void 0;
        const result = target.delete(key);
        if (hadKey) {
          trigger(target, "delete", key, void 0);
        }
        return result;
      },
      clear() {
        const target = toRaw(this);
        const hadItems = target.size !== 0;
        const result = target.clear();
        if (hadItems) {
          trigger(
            target,
            "clear",
            void 0,
            void 0
          );
        }
        return result;
      }
    }
  );
  const iteratorMethods = [
    "keys",
    "values",
    "entries",
    Symbol.iterator
  ];
  iteratorMethods.forEach((method) => {
    instrumentations[method] = createIterableMethod(method, readonly2, shallow);
  });
  return instrumentations;
}
function createInstrumentationGetter(isReadonly2, shallow) {
  const instrumentations = createInstrumentations(isReadonly2, shallow);
  return (target, key, receiver) => {
    if (key === "__v_isReactive") {
      return !isReadonly2;
    } else if (key === "__v_isReadonly") {
      return isReadonly2;
    } else if (key === "__v_raw") {
      return target;
    }
    return Reflect.get(
      hasOwn(instrumentations, key) && key in target ? instrumentations : target,
      key,
      receiver
    );
  };
}
const mutableCollectionHandlers = {
  get: /* @__PURE__ */ createInstrumentationGetter(false, false)
};
const shallowCollectionHandlers = {
  get: /* @__PURE__ */ createInstrumentationGetter(false, true)
};
const readonlyCollectionHandlers = {
  get: /* @__PURE__ */ createInstrumentationGetter(true, false)
};
const shallowReadonlyCollectionHandlers = {
  get: /* @__PURE__ */ createInstrumentationGetter(true, true)
};
const reactiveMap = /* @__PURE__ */ new WeakMap();
const shallowReactiveMap = /* @__PURE__ */ new WeakMap();
const readonlyMap = /* @__PURE__ */ new WeakMap();
const shallowReadonlyMap = /* @__PURE__ */ new WeakMap();
function targetTypeMap(rawType) {
  switch (rawType) {
    case "Object":
    case "Array":
      return 1;
    case "Map":
    case "Set":
    case "WeakMap":
    case "WeakSet":
      return 2;
    default:
      return 0;
  }
}
function getTargetType(value) {
  return value["__v_skip"] || !Object.isExtensible(value) ? 0 : targetTypeMap(toRawType(value));
}
function reactive(target) {
  if (isReadonly(target)) {
    return target;
  }
  return createReactiveObject(
    target,
    false,
    mutableHandlers,
    mutableCollectionHandlers,
    reactiveMap
  );
}
function shallowReactive(target) {
  return createReactiveObject(
    target,
    false,
    shallowReactiveHandlers,
    shallowCollectionHandlers,
    shallowReactiveMap
  );
}
function readonly(target) {
  return createReactiveObject(
    target,
    true,
    readonlyHandlers,
    readonlyCollectionHandlers,
    readonlyMap
  );
}
function shallowReadonly(target) {
  return createReactiveObject(
    target,
    true,
    shallowReadonlyHandlers,
    shallowReadonlyCollectionHandlers,
    shallowReadonlyMap
  );
}
function createReactiveObject(target, isReadonly2, baseHandlers, collectionHandlers, proxyMap) {
  if (!isObject(target)) {
    return target;
  }
  if (target["__v_raw"] && !(isReadonly2 && target["__v_isReactive"])) {
    return target;
  }
  const targetType = getTargetType(target);
  if (targetType === 0) {
    return target;
  }
  const existingProxy = proxyMap.get(target);
  if (existingProxy) {
    return existingProxy;
  }
  const proxy = new Proxy(
    target,
    targetType === 2 ? collectionHandlers : baseHandlers
  );
  proxyMap.set(target, proxy);
  return proxy;
}
function isReactive(value) {
  if (isReadonly(value)) {
    return isReactive(value["__v_raw"]);
  }
  return !!(value && value["__v_isReactive"]);
}
function isReadonly(value) {
  return !!(value && value["__v_isReadonly"]);
}
function isShallow(value) {
  return !!(value && value["__v_isShallow"]);
}
function isProxy(value) {
  return value ? !!value["__v_raw"] : false;
}
function toRaw(observed) {
  const raw = observed && observed["__v_raw"];
  return raw ? toRaw(raw) : observed;
}
function markRaw(value) {
  if (!hasOwn(value, "__v_skip") && Object.isExtensible(value)) {
    def(value, "__v_skip", true);
  }
  return value;
}
const toReactive = (value) => isObject(value) ? reactive(value) : value;
const toReadonly = (value) => isObject(value) ? readonly(value) : value;
function isRef(r) {
  return r ? r["__v_isRef"] === true : false;
}
function ref(value) {
  return createRef(value, false);
}
function createRef(rawValue, shallow) {
  if (isRef(rawValue)) {
    return rawValue;
  }
  return new RefImpl(rawValue, shallow);
}
class RefImpl {
  constructor(value, isShallow2) {
    this.dep = new Dep();
    this["__v_isRef"] = true;
    this["__v_isShallow"] = false;
    this._rawValue = isShallow2 ? value : toRaw(value);
    this._value = isShallow2 ? value : toReactive(value);
    this["__v_isShallow"] = isShallow2;
  }
  get value() {
    {
      this.dep.track();
    }
    return this._value;
  }
  set value(newValue) {
    const oldValue = this._rawValue;
    const useDirectValue = this["__v_isShallow"] || isShallow(newValue) || isReadonly(newValue);
    newValue = useDirectValue ? newValue : toRaw(newValue);
    if (hasChanged(newValue, oldValue)) {
      this._rawValue = newValue;
      this._value = useDirectValue ? newValue : toReactive(newValue);
      {
        this.dep.trigger();
      }
    }
  }
}
function unref(ref2) {
  return isRef(ref2) ? ref2.value : ref2;
}
const shallowUnwrapHandlers = {
  get: (target, key, receiver) => key === "__v_raw" ? target : unref(Reflect.get(target, key, receiver)),
  set: (target, key, value, receiver) => {
    const oldValue = target[key];
    if (isRef(oldValue) && !isRef(value)) {
      oldValue.value = value;
      return true;
    } else {
      return Reflect.set(target, key, value, receiver);
    }
  }
};
function proxyRefs(objectWithRefs) {
  return isReactive(objectWithRefs) ? objectWithRefs : new Proxy(objectWithRefs, shallowUnwrapHandlers);
}
class ComputedRefImpl {
  constructor(fn, setter, isSSR) {
    this.fn = fn;
    this.setter = setter;
    this._value = void 0;
    this.dep = new Dep(this);
    this.__v_isRef = true;
    this.deps = void 0;
    this.depsTail = void 0;
    this.flags = 16;
    this.globalVersion = globalVersion - 1;
    this.next = void 0;
    this.effect = this;
    this["__v_isReadonly"] = !setter;
    this.isSSR = isSSR;
  }
  /**
   * @internal
   */
  notify() {
    this.flags |= 16;
    if (!(this.flags & 8) && // avoid infinite self recursion
    activeSub !== this) {
      batch(this, true);
      return true;
    }
  }
  get value() {
    const link = this.dep.track();
    refreshComputed(this);
    if (link) {
      link.version = this.dep.version;
    }
    return this._value;
  }
  set value(newValue) {
    if (this.setter) {
      this.setter(newValue);
    }
  }
}
function computed$1(getterOrOptions, debugOptions, isSSR = false) {
  let getter;
  let setter;
  if (isFunction(getterOrOptions)) {
    getter = getterOrOptions;
  } else {
    getter = getterOrOptions.get;
    setter = getterOrOptions.set;
  }
  const cRef = new ComputedRefImpl(getter, setter, isSSR);
  return cRef;
}
const INITIAL_WATCHER_VALUE = {};
const cleanupMap = /* @__PURE__ */ new WeakMap();
let activeWatcher = void 0;
function onWatcherCleanup(cleanupFn, failSilently = false, owner = activeWatcher) {
  if (owner) {
    let cleanups = cleanupMap.get(owner);
    if (!cleanups) cleanupMap.set(owner, cleanups = []);
    cleanups.push(cleanupFn);
  }
}
function watch$1(source, cb, options = EMPTY_OBJ) {
  const { immediate, deep, once, scheduler, augmentJob, call } = options;
  const reactiveGetter = (source2) => {
    if (deep) return source2;
    if (isShallow(source2) || deep === false || deep === 0)
      return traverse(source2, 1);
    return traverse(source2);
  };
  let effect2;
  let getter;
  let cleanup;
  let boundCleanup;
  let forceTrigger = false;
  let isMultiSource = false;
  if (isRef(source)) {
    getter = () => source.value;
    forceTrigger = isShallow(source);
  } else if (isReactive(source)) {
    getter = () => reactiveGetter(source);
    forceTrigger = true;
  } else if (isArray(source)) {
    isMultiSource = true;
    forceTrigger = source.some((s2) => isReactive(s2) || isShallow(s2));
    getter = () => source.map((s2) => {
      if (isRef(s2)) {
        return s2.value;
      } else if (isReactive(s2)) {
        return reactiveGetter(s2);
      } else if (isFunction(s2)) {
        return call ? call(s2, 2) : s2();
      } else ;
    });
  } else if (isFunction(source)) {
    if (cb) {
      getter = call ? () => call(source, 2) : source;
    } else {
      getter = () => {
        if (cleanup) {
          pauseTracking();
          try {
            cleanup();
          } finally {
            resetTracking();
          }
        }
        const currentEffect = activeWatcher;
        activeWatcher = effect2;
        try {
          return call ? call(source, 3, [boundCleanup]) : source(boundCleanup);
        } finally {
          activeWatcher = currentEffect;
        }
      };
    }
  } else {
    getter = NOOP;
  }
  if (cb && deep) {
    const baseGetter = getter;
    const depth = deep === true ? Infinity : deep;
    getter = () => traverse(baseGetter(), depth);
  }
  const scope = getCurrentScope();
  const watchHandle = () => {
    effect2.stop();
    if (scope && scope.active) {
      remove(scope.effects, effect2);
    }
  };
  if (once && cb) {
    const _cb = cb;
    cb = (...args) => {
      _cb(...args);
      watchHandle();
    };
  }
  let oldValue = isMultiSource ? new Array(source.length).fill(INITIAL_WATCHER_VALUE) : INITIAL_WATCHER_VALUE;
  const job = (immediateFirstRun) => {
    if (!(effect2.flags & 1) || !effect2.dirty && !immediateFirstRun) {
      return;
    }
    if (cb) {
      const newValue = effect2.run();
      if (deep || forceTrigger || (isMultiSource ? newValue.some((v2, i2) => hasChanged(v2, oldValue[i2])) : hasChanged(newValue, oldValue))) {
        if (cleanup) {
          cleanup();
        }
        const currentWatcher = activeWatcher;
        activeWatcher = effect2;
        try {
          const args = [
            newValue,
            // pass undefined as the old value when it's changed for the first time
            oldValue === INITIAL_WATCHER_VALUE ? void 0 : isMultiSource && oldValue[0] === INITIAL_WATCHER_VALUE ? [] : oldValue,
            boundCleanup
          ];
          oldValue = newValue;
          call ? call(cb, 3, args) : (
            // @ts-expect-error
            cb(...args)
          );
        } finally {
          activeWatcher = currentWatcher;
        }
      }
    } else {
      effect2.run();
    }
  };
  if (augmentJob) {
    augmentJob(job);
  }
  effect2 = new ReactiveEffect(getter);
  effect2.scheduler = scheduler ? () => scheduler(job, false) : job;
  boundCleanup = (fn) => onWatcherCleanup(fn, false, effect2);
  cleanup = effect2.onStop = () => {
    const cleanups = cleanupMap.get(effect2);
    if (cleanups) {
      if (call) {
        call(cleanups, 4);
      } else {
        for (const cleanup2 of cleanups) cleanup2();
      }
      cleanupMap.delete(effect2);
    }
  };
  if (cb) {
    if (immediate) {
      job(true);
    } else {
      oldValue = effect2.run();
    }
  } else if (scheduler) {
    scheduler(job.bind(null, true), true);
  } else {
    effect2.run();
  }
  watchHandle.pause = effect2.pause.bind(effect2);
  watchHandle.resume = effect2.resume.bind(effect2);
  watchHandle.stop = watchHandle;
  return watchHandle;
}
function traverse(value, depth = Infinity, seen) {
  if (depth <= 0 || !isObject(value) || value["__v_skip"]) {
    return value;
  }
  seen = seen || /* @__PURE__ */ new Map();
  if ((seen.get(value) || 0) >= depth) {
    return value;
  }
  seen.set(value, depth);
  depth--;
  if (isRef(value)) {
    traverse(value.value, depth, seen);
  } else if (isArray(value)) {
    for (let i2 = 0; i2 < value.length; i2++) {
      traverse(value[i2], depth, seen);
    }
  } else if (isSet(value) || isMap(value)) {
    value.forEach((v2) => {
      traverse(v2, depth, seen);
    });
  } else if (isPlainObject(value)) {
    for (const key in value) {
      traverse(value[key], depth, seen);
    }
    for (const key of Object.getOwnPropertySymbols(value)) {
      if (Object.prototype.propertyIsEnumerable.call(value, key)) {
        traverse(value[key], depth, seen);
      }
    }
  }
  return value;
}
/**
* @vue/runtime-core v3.5.26
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
const stack = [];
let isWarning = false;
function warn$1(msg, ...args) {
  if (isWarning) return;
  isWarning = true;
  pauseTracking();
  const instance = stack.length ? stack[stack.length - 1].component : null;
  const appWarnHandler = instance && instance.appContext.config.warnHandler;
  const trace = getComponentTrace();
  if (appWarnHandler) {
    callWithErrorHandling(
      appWarnHandler,
      instance,
      11,
      [
        // eslint-disable-next-line no-restricted-syntax
        msg + args.map((a2) => {
          var _a, _b;
          return (_b = (_a = a2.toString) == null ? void 0 : _a.call(a2)) != null ? _b : JSON.stringify(a2);
        }).join(""),
        instance && instance.proxy,
        trace.map(
          ({ vnode }) => `at <${formatComponentName(instance, vnode.type)}>`
        ).join("\n"),
        trace
      ]
    );
  } else {
    const warnArgs = [`[Vue warn]: ${msg}`, ...args];
    if (trace.length && // avoid spamming console during tests
    true) {
      warnArgs.push(`
`, ...formatTrace(trace));
    }
    console.warn(...warnArgs);
  }
  resetTracking();
  isWarning = false;
}
function getComponentTrace() {
  let currentVNode = stack[stack.length - 1];
  if (!currentVNode) {
    return [];
  }
  const normalizedStack = [];
  while (currentVNode) {
    const last = normalizedStack[0];
    if (last && last.vnode === currentVNode) {
      last.recurseCount++;
    } else {
      normalizedStack.push({
        vnode: currentVNode,
        recurseCount: 0
      });
    }
    const parentInstance = currentVNode.component && currentVNode.component.parent;
    currentVNode = parentInstance && parentInstance.vnode;
  }
  return normalizedStack;
}
function formatTrace(trace) {
  const logs = [];
  trace.forEach((entry, i2) => {
    logs.push(...i2 === 0 ? [] : [`
`], ...formatTraceEntry(entry));
  });
  return logs;
}
function formatTraceEntry({ vnode, recurseCount }) {
  const postfix = recurseCount > 0 ? `... (${recurseCount} recursive calls)` : ``;
  const isRoot = vnode.component ? vnode.component.parent == null : false;
  const open = ` at <${formatComponentName(
    vnode.component,
    vnode.type,
    isRoot
  )}`;
  const close = `>` + postfix;
  return vnode.props ? [open, ...formatProps(vnode.props), close] : [open + close];
}
function formatProps(props) {
  const res = [];
  const keys = Object.keys(props);
  keys.slice(0, 3).forEach((key) => {
    res.push(...formatProp(key, props[key]));
  });
  if (keys.length > 3) {
    res.push(` ...`);
  }
  return res;
}
function formatProp(key, value, raw) {
  if (isString(value)) {
    value = JSON.stringify(value);
    return raw ? value : [`${key}=${value}`];
  } else if (typeof value === "number" || typeof value === "boolean" || value == null) {
    return raw ? value : [`${key}=${value}`];
  } else if (isRef(value)) {
    value = formatProp(key, toRaw(value.value), true);
    return raw ? value : [`${key}=Ref<`, value, `>`];
  } else if (isFunction(value)) {
    return [`${key}=fn${value.name ? `<${value.name}>` : ``}`];
  } else {
    value = toRaw(value);
    return raw ? value : [`${key}=`, value];
  }
}
function callWithErrorHandling(fn, instance, type, args) {
  try {
    return args ? fn(...args) : fn();
  } catch (err) {
    handleError(err, instance, type);
  }
}
function callWithAsyncErrorHandling(fn, instance, type, args) {
  if (isFunction(fn)) {
    const res = callWithErrorHandling(fn, instance, type, args);
    if (res && isPromise(res)) {
      res.catch((err) => {
        handleError(err, instance, type);
      });
    }
    return res;
  }
  if (isArray(fn)) {
    const values = [];
    for (let i2 = 0; i2 < fn.length; i2++) {
      values.push(callWithAsyncErrorHandling(fn[i2], instance, type, args));
    }
    return values;
  }
}
function handleError(err, instance, type, throwInDev = true) {
  const contextVNode = instance ? instance.vnode : null;
  const { errorHandler, throwUnhandledErrorInProduction } = instance && instance.appContext.config || EMPTY_OBJ;
  if (instance) {
    let cur = instance.parent;
    const exposedInstance = instance.proxy;
    const errorInfo = `https://vuejs.org/error-reference/#runtime-${type}`;
    while (cur) {
      const errorCapturedHooks = cur.ec;
      if (errorCapturedHooks) {
        for (let i2 = 0; i2 < errorCapturedHooks.length; i2++) {
          if (errorCapturedHooks[i2](err, exposedInstance, errorInfo) === false) {
            return;
          }
        }
      }
      cur = cur.parent;
    }
    if (errorHandler) {
      pauseTracking();
      callWithErrorHandling(errorHandler, null, 10, [
        err,
        exposedInstance,
        errorInfo
      ]);
      resetTracking();
      return;
    }
  }
  logError(err, type, contextVNode, throwInDev, throwUnhandledErrorInProduction);
}
function logError(err, type, contextVNode, throwInDev = true, throwInProd = false) {
  if (throwInProd) {
    throw err;
  } else {
    console.error(err);
  }
}
const queue = [];
let flushIndex = -1;
const pendingPostFlushCbs = [];
let activePostFlushCbs = null;
let postFlushIndex = 0;
const resolvedPromise = /* @__PURE__ */ Promise.resolve();
let currentFlushPromise = null;
function nextTick(fn) {
  const p2 = currentFlushPromise || resolvedPromise;
  return fn ? p2.then(this ? fn.bind(this) : fn) : p2;
}
function findInsertionIndex(id) {
  let start = flushIndex + 1;
  let end = queue.length;
  while (start < end) {
    const middle = start + end >>> 1;
    const middleJob = queue[middle];
    const middleJobId = getId(middleJob);
    if (middleJobId < id || middleJobId === id && middleJob.flags & 2) {
      start = middle + 1;
    } else {
      end = middle;
    }
  }
  return start;
}
function queueJob(job) {
  if (!(job.flags & 1)) {
    const jobId = getId(job);
    const lastJob = queue[queue.length - 1];
    if (!lastJob || // fast path when the job id is larger than the tail
    !(job.flags & 2) && jobId >= getId(lastJob)) {
      queue.push(job);
    } else {
      queue.splice(findInsertionIndex(jobId), 0, job);
    }
    job.flags |= 1;
    queueFlush();
  }
}
function queueFlush() {
  if (!currentFlushPromise) {
    currentFlushPromise = resolvedPromise.then(flushJobs);
  }
}
function queuePostFlushCb(cb) {
  if (!isArray(cb)) {
    if (activePostFlushCbs && cb.id === -1) {
      activePostFlushCbs.splice(postFlushIndex + 1, 0, cb);
    } else if (!(cb.flags & 1)) {
      pendingPostFlushCbs.push(cb);
      cb.flags |= 1;
    }
  } else {
    pendingPostFlushCbs.push(...cb);
  }
  queueFlush();
}
function flushPreFlushCbs(instance, seen, i2 = flushIndex + 1) {
  for (; i2 < queue.length; i2++) {
    const cb = queue[i2];
    if (cb && cb.flags & 2) {
      if (instance && cb.id !== instance.uid) {
        continue;
      }
      queue.splice(i2, 1);
      i2--;
      if (cb.flags & 4) {
        cb.flags &= -2;
      }
      cb();
      if (!(cb.flags & 4)) {
        cb.flags &= -2;
      }
    }
  }
}
function flushPostFlushCbs(seen) {
  if (pendingPostFlushCbs.length) {
    const deduped = [...new Set(pendingPostFlushCbs)].sort(
      (a2, b2) => getId(a2) - getId(b2)
    );
    pendingPostFlushCbs.length = 0;
    if (activePostFlushCbs) {
      activePostFlushCbs.push(...deduped);
      return;
    }
    activePostFlushCbs = deduped;
    for (postFlushIndex = 0; postFlushIndex < activePostFlushCbs.length; postFlushIndex++) {
      const cb = activePostFlushCbs[postFlushIndex];
      if (cb.flags & 4) {
        cb.flags &= -2;
      }
      if (!(cb.flags & 8)) cb();
      cb.flags &= -2;
    }
    activePostFlushCbs = null;
    postFlushIndex = 0;
  }
}
const getId = (job) => job.id == null ? job.flags & 2 ? -1 : Infinity : job.id;
function flushJobs(seen) {
  try {
    for (flushIndex = 0; flushIndex < queue.length; flushIndex++) {
      const job = queue[flushIndex];
      if (job && !(job.flags & 8)) {
        if (false) ;
        if (job.flags & 4) {
          job.flags &= ~1;
        }
        callWithErrorHandling(
          job,
          job.i,
          job.i ? 15 : 14
        );
        if (!(job.flags & 4)) {
          job.flags &= ~1;
        }
      }
    }
  } finally {
    for (; flushIndex < queue.length; flushIndex++) {
      const job = queue[flushIndex];
      if (job) {
        job.flags &= -2;
      }
    }
    flushIndex = -1;
    queue.length = 0;
    flushPostFlushCbs();
    currentFlushPromise = null;
    if (queue.length || pendingPostFlushCbs.length) {
      flushJobs();
    }
  }
}
let currentRenderingInstance = null;
let currentScopeId = null;
function setCurrentRenderingInstance(instance) {
  const prev = currentRenderingInstance;
  currentRenderingInstance = instance;
  currentScopeId = instance && instance.type.__scopeId || null;
  return prev;
}
function withCtx(fn, ctx = currentRenderingInstance, isNonScopedSlot) {
  if (!ctx) return fn;
  if (fn._n) {
    return fn;
  }
  const renderFnWithContext = (...args) => {
    if (renderFnWithContext._d) {
      setBlockTracking(-1);
    }
    const prevInstance = setCurrentRenderingInstance(ctx);
    let res;
    try {
      res = fn(...args);
    } finally {
      setCurrentRenderingInstance(prevInstance);
      if (renderFnWithContext._d) {
        setBlockTracking(1);
      }
    }
    return res;
  };
  renderFnWithContext._n = true;
  renderFnWithContext._c = true;
  renderFnWithContext._d = true;
  return renderFnWithContext;
}
function withDirectives(vnode, directives) {
  if (currentRenderingInstance === null) {
    return vnode;
  }
  const instance = getComponentPublicInstance(currentRenderingInstance);
  const bindings = vnode.dirs || (vnode.dirs = []);
  for (let i2 = 0; i2 < directives.length; i2++) {
    let [dir, value, arg, modifiers = EMPTY_OBJ] = directives[i2];
    if (dir) {
      if (isFunction(dir)) {
        dir = {
          mounted: dir,
          updated: dir
        };
      }
      if (dir.deep) {
        traverse(value);
      }
      bindings.push({
        dir,
        instance,
        value,
        oldValue: void 0,
        arg,
        modifiers
      });
    }
  }
  return vnode;
}
function invokeDirectiveHook(vnode, prevVNode, instance, name) {
  const bindings = vnode.dirs;
  const oldBindings = prevVNode && prevVNode.dirs;
  for (let i2 = 0; i2 < bindings.length; i2++) {
    const binding = bindings[i2];
    if (oldBindings) {
      binding.oldValue = oldBindings[i2].value;
    }
    let hook = binding.dir[name];
    if (hook) {
      pauseTracking();
      callWithAsyncErrorHandling(hook, instance, 8, [
        vnode.el,
        binding,
        vnode,
        prevVNode
      ]);
      resetTracking();
    }
  }
}
function provide(key, value) {
  if (currentInstance) {
    let provides = currentInstance.provides;
    const parentProvides = currentInstance.parent && currentInstance.parent.provides;
    if (parentProvides === provides) {
      provides = currentInstance.provides = Object.create(parentProvides);
    }
    provides[key] = value;
  }
}
function inject(key, defaultValue, treatDefaultAsFactory = false) {
  const instance = getCurrentInstance();
  if (instance || currentApp) {
    let provides = currentApp ? currentApp._context.provides : instance ? instance.parent == null || instance.ce ? instance.vnode.appContext && instance.vnode.appContext.provides : instance.parent.provides : void 0;
    if (provides && key in provides) {
      return provides[key];
    } else if (arguments.length > 1) {
      return treatDefaultAsFactory && isFunction(defaultValue) ? defaultValue.call(instance && instance.proxy) : defaultValue;
    } else ;
  }
}
const ssrContextKey = /* @__PURE__ */ Symbol.for("v-scx");
const useSSRContext = () => {
  {
    const ctx = inject(ssrContextKey);
    return ctx;
  }
};
function watch(source, cb, options) {
  return doWatch(source, cb, options);
}
function doWatch(source, cb, options = EMPTY_OBJ) {
  const { immediate, deep, flush, once } = options;
  const baseWatchOptions = extend({}, options);
  const runsImmediately = cb && immediate || !cb && flush !== "post";
  let ssrCleanup;
  if (isInSSRComponentSetup) {
    if (flush === "sync") {
      const ctx = useSSRContext();
      ssrCleanup = ctx.__watcherHandles || (ctx.__watcherHandles = []);
    } else if (!runsImmediately) {
      const watchStopHandle = () => {
      };
      watchStopHandle.stop = NOOP;
      watchStopHandle.resume = NOOP;
      watchStopHandle.pause = NOOP;
      return watchStopHandle;
    }
  }
  const instance = currentInstance;
  baseWatchOptions.call = (fn, type, args) => callWithAsyncErrorHandling(fn, instance, type, args);
  let isPre = false;
  if (flush === "post") {
    baseWatchOptions.scheduler = (job) => {
      queuePostRenderEffect(job, instance && instance.suspense);
    };
  } else if (flush !== "sync") {
    isPre = true;
    baseWatchOptions.scheduler = (job, isFirstRun) => {
      if (isFirstRun) {
        job();
      } else {
        queueJob(job);
      }
    };
  }
  baseWatchOptions.augmentJob = (job) => {
    if (cb) {
      job.flags |= 4;
    }
    if (isPre) {
      job.flags |= 2;
      if (instance) {
        job.id = instance.uid;
        job.i = instance;
      }
    }
  };
  const watchHandle = watch$1(source, cb, baseWatchOptions);
  if (isInSSRComponentSetup) {
    if (ssrCleanup) {
      ssrCleanup.push(watchHandle);
    } else if (runsImmediately) {
      watchHandle();
    }
  }
  return watchHandle;
}
function instanceWatch(source, value, options) {
  const publicThis = this.proxy;
  const getter = isString(source) ? source.includes(".") ? createPathGetter(publicThis, source) : () => publicThis[source] : source.bind(publicThis, publicThis);
  let cb;
  if (isFunction(value)) {
    cb = value;
  } else {
    cb = value.handler;
    options = value;
  }
  const reset = setCurrentInstance(this);
  const res = doWatch(getter, cb.bind(publicThis), options);
  reset();
  return res;
}
function createPathGetter(ctx, path) {
  const segments = path.split(".");
  return () => {
    let cur = ctx;
    for (let i2 = 0; i2 < segments.length && cur; i2++) {
      cur = cur[segments[i2]];
    }
    return cur;
  };
}
const TeleportEndKey = /* @__PURE__ */ Symbol("_vte");
const isTeleport = (type) => type.__isTeleport;
const isTeleportDisabled = (props) => props && (props.disabled || props.disabled === "");
const isTeleportDeferred = (props) => props && (props.defer || props.defer === "");
const isTargetSVG = (target) => typeof SVGElement !== "undefined" && target instanceof SVGElement;
const isTargetMathML = (target) => typeof MathMLElement === "function" && target instanceof MathMLElement;
const resolveTarget = (props, select) => {
  const targetSelector = props && props.to;
  if (isString(targetSelector)) {
    if (!select) {
      return null;
    } else {
      const target = select(targetSelector);
      return target;
    }
  } else {
    return targetSelector;
  }
};
const TeleportImpl = {
  name: "Teleport",
  __isTeleport: true,
  process(n1, n2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized, internals) {
    const {
      mc: mountChildren,
      pc: patchChildren,
      pbc: patchBlockChildren,
      o: { insert, querySelector, createText, createComment }
    } = internals;
    const disabled = isTeleportDisabled(n2.props);
    let { shapeFlag, children, dynamicChildren } = n2;
    if (n1 == null) {
      const placeholder = n2.el = createText("");
      const mainAnchor = n2.anchor = createText("");
      insert(placeholder, container, anchor);
      insert(mainAnchor, container, anchor);
      const mount = (container2, anchor2) => {
        if (shapeFlag & 16) {
          mountChildren(
            children,
            container2,
            anchor2,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        }
      };
      const mountToTarget = () => {
        const target = n2.target = resolveTarget(n2.props, querySelector);
        const targetAnchor = prepareAnchor(target, n2, createText, insert);
        if (target) {
          if (namespace !== "svg" && isTargetSVG(target)) {
            namespace = "svg";
          } else if (namespace !== "mathml" && isTargetMathML(target)) {
            namespace = "mathml";
          }
          if (parentComponent && parentComponent.isCE) {
            (parentComponent.ce._teleportTargets || (parentComponent.ce._teleportTargets = /* @__PURE__ */ new Set())).add(target);
          }
          if (!disabled) {
            mount(target, targetAnchor);
            updateCssVars(n2, false);
          }
        }
      };
      if (disabled) {
        mount(container, mainAnchor);
        updateCssVars(n2, true);
      }
      if (isTeleportDeferred(n2.props)) {
        n2.el.__isMounted = false;
        queuePostRenderEffect(() => {
          mountToTarget();
          delete n2.el.__isMounted;
        }, parentSuspense);
      } else {
        mountToTarget();
      }
    } else {
      if (isTeleportDeferred(n2.props) && n1.el.__isMounted === false) {
        queuePostRenderEffect(() => {
          TeleportImpl.process(
            n1,
            n2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized,
            internals
          );
        }, parentSuspense);
        return;
      }
      n2.el = n1.el;
      n2.targetStart = n1.targetStart;
      const mainAnchor = n2.anchor = n1.anchor;
      const target = n2.target = n1.target;
      const targetAnchor = n2.targetAnchor = n1.targetAnchor;
      const wasDisabled = isTeleportDisabled(n1.props);
      const currentContainer = wasDisabled ? container : target;
      const currentAnchor = wasDisabled ? mainAnchor : targetAnchor;
      if (namespace === "svg" || isTargetSVG(target)) {
        namespace = "svg";
      } else if (namespace === "mathml" || isTargetMathML(target)) {
        namespace = "mathml";
      }
      if (dynamicChildren) {
        patchBlockChildren(
          n1.dynamicChildren,
          dynamicChildren,
          currentContainer,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds
        );
        traverseStaticChildren(n1, n2, true);
      } else if (!optimized) {
        patchChildren(
          n1,
          n2,
          currentContainer,
          currentAnchor,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          false
        );
      }
      if (disabled) {
        if (!wasDisabled) {
          moveTeleport(
            n2,
            container,
            mainAnchor,
            internals,
            1
          );
        } else {
          if (n2.props && n1.props && n2.props.to !== n1.props.to) {
            n2.props.to = n1.props.to;
          }
        }
      } else {
        if ((n2.props && n2.props.to) !== (n1.props && n1.props.to)) {
          const nextTarget = n2.target = resolveTarget(
            n2.props,
            querySelector
          );
          if (nextTarget) {
            moveTeleport(
              n2,
              nextTarget,
              null,
              internals,
              0
            );
          }
        } else if (wasDisabled) {
          moveTeleport(
            n2,
            target,
            targetAnchor,
            internals,
            1
          );
        }
      }
      updateCssVars(n2, disabled);
    }
  },
  remove(vnode, parentComponent, parentSuspense, { um: unmount, o: { remove: hostRemove } }, doRemove) {
    const {
      shapeFlag,
      children,
      anchor,
      targetStart,
      targetAnchor,
      target,
      props
    } = vnode;
    if (target) {
      hostRemove(targetStart);
      hostRemove(targetAnchor);
    }
    doRemove && hostRemove(anchor);
    if (shapeFlag & 16) {
      const shouldRemove = doRemove || !isTeleportDisabled(props);
      for (let i2 = 0; i2 < children.length; i2++) {
        const child = children[i2];
        unmount(
          child,
          parentComponent,
          parentSuspense,
          shouldRemove,
          !!child.dynamicChildren
        );
      }
    }
  },
  move: moveTeleport,
  hydrate: hydrateTeleport
};
function moveTeleport(vnode, container, parentAnchor, { o: { insert }, m: move }, moveType = 2) {
  if (moveType === 0) {
    insert(vnode.targetAnchor, container, parentAnchor);
  }
  const { el, anchor, shapeFlag, children, props } = vnode;
  const isReorder = moveType === 2;
  if (isReorder) {
    insert(el, container, parentAnchor);
  }
  if (!isReorder || isTeleportDisabled(props)) {
    if (shapeFlag & 16) {
      for (let i2 = 0; i2 < children.length; i2++) {
        move(
          children[i2],
          container,
          parentAnchor,
          2
        );
      }
    }
  }
  if (isReorder) {
    insert(anchor, container, parentAnchor);
  }
}
function hydrateTeleport(node, vnode, parentComponent, parentSuspense, slotScopeIds, optimized, {
  o: { nextSibling, parentNode, querySelector, insert, createText }
}, hydrateChildren) {
  function hydrateDisabledTeleport(node2, vnode2, targetStart, targetAnchor) {
    vnode2.anchor = hydrateChildren(
      nextSibling(node2),
      vnode2,
      parentNode(node2),
      parentComponent,
      parentSuspense,
      slotScopeIds,
      optimized
    );
    vnode2.targetStart = targetStart;
    vnode2.targetAnchor = targetAnchor;
  }
  const target = vnode.target = resolveTarget(
    vnode.props,
    querySelector
  );
  const disabled = isTeleportDisabled(vnode.props);
  if (target) {
    const targetNode = target._lpa || target.firstChild;
    if (vnode.shapeFlag & 16) {
      if (disabled) {
        hydrateDisabledTeleport(
          node,
          vnode,
          targetNode,
          targetNode && nextSibling(targetNode)
        );
      } else {
        vnode.anchor = nextSibling(node);
        let targetAnchor = targetNode;
        while (targetAnchor) {
          if (targetAnchor && targetAnchor.nodeType === 8) {
            if (targetAnchor.data === "teleport start anchor") {
              vnode.targetStart = targetAnchor;
            } else if (targetAnchor.data === "teleport anchor") {
              vnode.targetAnchor = targetAnchor;
              target._lpa = vnode.targetAnchor && nextSibling(vnode.targetAnchor);
              break;
            }
          }
          targetAnchor = nextSibling(targetAnchor);
        }
        if (!vnode.targetAnchor) {
          prepareAnchor(target, vnode, createText, insert);
        }
        hydrateChildren(
          targetNode && nextSibling(targetNode),
          vnode,
          target,
          parentComponent,
          parentSuspense,
          slotScopeIds,
          optimized
        );
      }
    }
    updateCssVars(vnode, disabled);
  } else if (disabled) {
    if (vnode.shapeFlag & 16) {
      hydrateDisabledTeleport(node, vnode, node, nextSibling(node));
    }
  }
  return vnode.anchor && nextSibling(vnode.anchor);
}
const Teleport = TeleportImpl;
function updateCssVars(vnode, isDisabled) {
  const ctx = vnode.ctx;
  if (ctx && ctx.ut) {
    let node, anchor;
    if (isDisabled) {
      node = vnode.el;
      anchor = vnode.anchor;
    } else {
      node = vnode.targetStart;
      anchor = vnode.targetAnchor;
    }
    while (node && node !== anchor) {
      if (node.nodeType === 1) node.setAttribute("data-v-owner", ctx.uid);
      node = node.nextSibling;
    }
    ctx.ut();
  }
}
function prepareAnchor(target, vnode, createText, insert) {
  const targetStart = vnode.targetStart = createText("");
  const targetAnchor = vnode.targetAnchor = createText("");
  targetStart[TeleportEndKey] = targetAnchor;
  if (target) {
    insert(targetStart, target);
    insert(targetAnchor, target);
  }
  return targetAnchor;
}
const leaveCbKey = /* @__PURE__ */ Symbol("_leaveCb");
const enterCbKey = /* @__PURE__ */ Symbol("_enterCb");
function useTransitionState() {
  const state = {
    isMounted: false,
    isLeaving: false,
    isUnmounting: false,
    leavingVNodes: /* @__PURE__ */ new Map()
  };
  onMounted(() => {
    state.isMounted = true;
  });
  onBeforeUnmount(() => {
    state.isUnmounting = true;
  });
  return state;
}
const TransitionHookValidator = [Function, Array];
const BaseTransitionPropsValidators = {
  mode: String,
  appear: Boolean,
  persisted: Boolean,
  // enter
  onBeforeEnter: TransitionHookValidator,
  onEnter: TransitionHookValidator,
  onAfterEnter: TransitionHookValidator,
  onEnterCancelled: TransitionHookValidator,
  // leave
  onBeforeLeave: TransitionHookValidator,
  onLeave: TransitionHookValidator,
  onAfterLeave: TransitionHookValidator,
  onLeaveCancelled: TransitionHookValidator,
  // appear
  onBeforeAppear: TransitionHookValidator,
  onAppear: TransitionHookValidator,
  onAfterAppear: TransitionHookValidator,
  onAppearCancelled: TransitionHookValidator
};
const recursiveGetSubtree = (instance) => {
  const subTree = instance.subTree;
  return subTree.component ? recursiveGetSubtree(subTree.component) : subTree;
};
const BaseTransitionImpl = {
  name: `BaseTransition`,
  props: BaseTransitionPropsValidators,
  setup(props, { slots }) {
    const instance = getCurrentInstance();
    const state = useTransitionState();
    return () => {
      const children = slots.default && getTransitionRawChildren(slots.default(), true);
      if (!children || !children.length) {
        return;
      }
      const child = findNonCommentChild(children);
      const rawProps = toRaw(props);
      const { mode } = rawProps;
      if (state.isLeaving) {
        return emptyPlaceholder(child);
      }
      const innerChild = getInnerChild$1(child);
      if (!innerChild) {
        return emptyPlaceholder(child);
      }
      let enterHooks = resolveTransitionHooks(
        innerChild,
        rawProps,
        state,
        instance,
        // #11061, ensure enterHooks is fresh after clone
        (hooks) => enterHooks = hooks
      );
      if (innerChild.type !== Comment) {
        setTransitionHooks(innerChild, enterHooks);
      }
      let oldInnerChild = instance.subTree && getInnerChild$1(instance.subTree);
      if (oldInnerChild && oldInnerChild.type !== Comment && !isSameVNodeType(oldInnerChild, innerChild) && recursiveGetSubtree(instance).type !== Comment) {
        let leavingHooks = resolveTransitionHooks(
          oldInnerChild,
          rawProps,
          state,
          instance
        );
        setTransitionHooks(oldInnerChild, leavingHooks);
        if (mode === "out-in" && innerChild.type !== Comment) {
          state.isLeaving = true;
          leavingHooks.afterLeave = () => {
            state.isLeaving = false;
            if (!(instance.job.flags & 8)) {
              instance.update();
            }
            delete leavingHooks.afterLeave;
            oldInnerChild = void 0;
          };
          return emptyPlaceholder(child);
        } else if (mode === "in-out" && innerChild.type !== Comment) {
          leavingHooks.delayLeave = (el, earlyRemove, delayedLeave) => {
            const leavingVNodesCache = getLeavingNodesForType(
              state,
              oldInnerChild
            );
            leavingVNodesCache[String(oldInnerChild.key)] = oldInnerChild;
            el[leaveCbKey] = () => {
              earlyRemove();
              el[leaveCbKey] = void 0;
              delete enterHooks.delayedLeave;
              oldInnerChild = void 0;
            };
            enterHooks.delayedLeave = () => {
              delayedLeave();
              delete enterHooks.delayedLeave;
              oldInnerChild = void 0;
            };
          };
        } else {
          oldInnerChild = void 0;
        }
      } else if (oldInnerChild) {
        oldInnerChild = void 0;
      }
      return child;
    };
  }
};
function findNonCommentChild(children) {
  let child = children[0];
  if (children.length > 1) {
    for (const c2 of children) {
      if (c2.type !== Comment) {
        child = c2;
        break;
      }
    }
  }
  return child;
}
const BaseTransition = BaseTransitionImpl;
function getLeavingNodesForType(state, vnode) {
  const { leavingVNodes } = state;
  let leavingVNodesCache = leavingVNodes.get(vnode.type);
  if (!leavingVNodesCache) {
    leavingVNodesCache = /* @__PURE__ */ Object.create(null);
    leavingVNodes.set(vnode.type, leavingVNodesCache);
  }
  return leavingVNodesCache;
}
function resolveTransitionHooks(vnode, props, state, instance, postClone) {
  const {
    appear,
    mode,
    persisted = false,
    onBeforeEnter,
    onEnter,
    onAfterEnter,
    onEnterCancelled,
    onBeforeLeave,
    onLeave,
    onAfterLeave,
    onLeaveCancelled,
    onBeforeAppear,
    onAppear,
    onAfterAppear,
    onAppearCancelled
  } = props;
  const key = String(vnode.key);
  const leavingVNodesCache = getLeavingNodesForType(state, vnode);
  const callHook2 = (hook, args) => {
    hook && callWithAsyncErrorHandling(
      hook,
      instance,
      9,
      args
    );
  };
  const callAsyncHook = (hook, args) => {
    const done = args[1];
    callHook2(hook, args);
    if (isArray(hook)) {
      if (hook.every((hook2) => hook2.length <= 1)) done();
    } else if (hook.length <= 1) {
      done();
    }
  };
  const hooks = {
    mode,
    persisted,
    beforeEnter(el) {
      let hook = onBeforeEnter;
      if (!state.isMounted) {
        if (appear) {
          hook = onBeforeAppear || onBeforeEnter;
        } else {
          return;
        }
      }
      if (el[leaveCbKey]) {
        el[leaveCbKey](
          true
          /* cancelled */
        );
      }
      const leavingVNode = leavingVNodesCache[key];
      if (leavingVNode && isSameVNodeType(vnode, leavingVNode) && leavingVNode.el[leaveCbKey]) {
        leavingVNode.el[leaveCbKey]();
      }
      callHook2(hook, [el]);
    },
    enter(el) {
      let hook = onEnter;
      let afterHook = onAfterEnter;
      let cancelHook = onEnterCancelled;
      if (!state.isMounted) {
        if (appear) {
          hook = onAppear || onEnter;
          afterHook = onAfterAppear || onAfterEnter;
          cancelHook = onAppearCancelled || onEnterCancelled;
        } else {
          return;
        }
      }
      let called = false;
      const done = el[enterCbKey] = (cancelled) => {
        if (called) return;
        called = true;
        if (cancelled) {
          callHook2(cancelHook, [el]);
        } else {
          callHook2(afterHook, [el]);
        }
        if (hooks.delayedLeave) {
          hooks.delayedLeave();
        }
        el[enterCbKey] = void 0;
      };
      if (hook) {
        callAsyncHook(hook, [el, done]);
      } else {
        done();
      }
    },
    leave(el, remove2) {
      const key2 = String(vnode.key);
      if (el[enterCbKey]) {
        el[enterCbKey](
          true
          /* cancelled */
        );
      }
      if (state.isUnmounting) {
        return remove2();
      }
      callHook2(onBeforeLeave, [el]);
      let called = false;
      const done = el[leaveCbKey] = (cancelled) => {
        if (called) return;
        called = true;
        remove2();
        if (cancelled) {
          callHook2(onLeaveCancelled, [el]);
        } else {
          callHook2(onAfterLeave, [el]);
        }
        el[leaveCbKey] = void 0;
        if (leavingVNodesCache[key2] === vnode) {
          delete leavingVNodesCache[key2];
        }
      };
      leavingVNodesCache[key2] = vnode;
      if (onLeave) {
        callAsyncHook(onLeave, [el, done]);
      } else {
        done();
      }
    },
    clone(vnode2) {
      const hooks2 = resolveTransitionHooks(
        vnode2,
        props,
        state,
        instance,
        postClone
      );
      if (postClone) postClone(hooks2);
      return hooks2;
    }
  };
  return hooks;
}
function emptyPlaceholder(vnode) {
  if (isKeepAlive(vnode)) {
    vnode = cloneVNode(vnode);
    vnode.children = null;
    return vnode;
  }
}
function getInnerChild$1(vnode) {
  if (!isKeepAlive(vnode)) {
    if (isTeleport(vnode.type) && vnode.children) {
      return findNonCommentChild(vnode.children);
    }
    return vnode;
  }
  if (vnode.component) {
    return vnode.component.subTree;
  }
  const { shapeFlag, children } = vnode;
  if (children) {
    if (shapeFlag & 16) {
      return children[0];
    }
    if (shapeFlag & 32 && isFunction(children.default)) {
      return children.default();
    }
  }
}
function setTransitionHooks(vnode, hooks) {
  if (vnode.shapeFlag & 6 && vnode.component) {
    vnode.transition = hooks;
    setTransitionHooks(vnode.component.subTree, hooks);
  } else if (vnode.shapeFlag & 128) {
    vnode.ssContent.transition = hooks.clone(vnode.ssContent);
    vnode.ssFallback.transition = hooks.clone(vnode.ssFallback);
  } else {
    vnode.transition = hooks;
  }
}
function getTransitionRawChildren(children, keepComment = false, parentKey) {
  let ret = [];
  let keyedFragmentCount = 0;
  for (let i2 = 0; i2 < children.length; i2++) {
    let child = children[i2];
    const key = parentKey == null ? child.key : String(parentKey) + String(child.key != null ? child.key : i2);
    if (child.type === Fragment) {
      if (child.patchFlag & 128) keyedFragmentCount++;
      ret = ret.concat(
        getTransitionRawChildren(child.children, keepComment, key)
      );
    } else if (keepComment || child.type !== Comment) {
      ret.push(key != null ? cloneVNode(child, { key }) : child);
    }
  }
  if (keyedFragmentCount > 1) {
    for (let i2 = 0; i2 < ret.length; i2++) {
      ret[i2].patchFlag = -2;
    }
  }
  return ret;
}
// @__NO_SIDE_EFFECTS__
function defineComponent(options, extraOptions) {
  return isFunction(options) ? (
    // #8236: extend call and options.name access are considered side-effects
    // by Rollup, so we have to wrap it in a pure-annotated IIFE.
    /* @__PURE__ */ (() => extend({ name: options.name }, extraOptions, { setup: options }))()
  ) : options;
}
function markAsyncBoundary(instance) {
  instance.ids = [instance.ids[0] + instance.ids[2]++ + "-", 0, 0];
}
const pendingSetRefMap = /* @__PURE__ */ new WeakMap();
function setRef(rawRef, oldRawRef, parentSuspense, vnode, isUnmount = false) {
  if (isArray(rawRef)) {
    rawRef.forEach(
      (r, i2) => setRef(
        r,
        oldRawRef && (isArray(oldRawRef) ? oldRawRef[i2] : oldRawRef),
        parentSuspense,
        vnode,
        isUnmount
      )
    );
    return;
  }
  if (isAsyncWrapper(vnode) && !isUnmount) {
    if (vnode.shapeFlag & 512 && vnode.type.__asyncResolved && vnode.component.subTree.component) {
      setRef(rawRef, oldRawRef, parentSuspense, vnode.component.subTree);
    }
    return;
  }
  const refValue = vnode.shapeFlag & 4 ? getComponentPublicInstance(vnode.component) : vnode.el;
  const value = isUnmount ? null : refValue;
  const { i: owner, r: ref3 } = rawRef;
  const oldRef = oldRawRef && oldRawRef.r;
  const refs = owner.refs === EMPTY_OBJ ? owner.refs = {} : owner.refs;
  const setupState = owner.setupState;
  const rawSetupState = toRaw(setupState);
  const canSetSetupRef = setupState === EMPTY_OBJ ? NO : (key) => {
    return hasOwn(rawSetupState, key);
  };
  if (oldRef != null && oldRef !== ref3) {
    invalidatePendingSetRef(oldRawRef);
    if (isString(oldRef)) {
      refs[oldRef] = null;
      if (canSetSetupRef(oldRef)) {
        setupState[oldRef] = null;
      }
    } else if (isRef(oldRef)) {
      {
        oldRef.value = null;
      }
      const oldRawRefAtom = oldRawRef;
      if (oldRawRefAtom.k) refs[oldRawRefAtom.k] = null;
    }
  }
  if (isFunction(ref3)) {
    callWithErrorHandling(ref3, owner, 12, [value, refs]);
  } else {
    const _isString = isString(ref3);
    const _isRef = isRef(ref3);
    if (_isString || _isRef) {
      const doSet = () => {
        if (rawRef.f) {
          const existing = _isString ? canSetSetupRef(ref3) ? setupState[ref3] : refs[ref3] : ref3.value;
          if (isUnmount) {
            isArray(existing) && remove(existing, refValue);
          } else {
            if (!isArray(existing)) {
              if (_isString) {
                refs[ref3] = [refValue];
                if (canSetSetupRef(ref3)) {
                  setupState[ref3] = refs[ref3];
                }
              } else {
                const newVal = [refValue];
                {
                  ref3.value = newVal;
                }
                if (rawRef.k) refs[rawRef.k] = newVal;
              }
            } else if (!existing.includes(refValue)) {
              existing.push(refValue);
            }
          }
        } else if (_isString) {
          refs[ref3] = value;
          if (canSetSetupRef(ref3)) {
            setupState[ref3] = value;
          }
        } else if (_isRef) {
          {
            ref3.value = value;
          }
          if (rawRef.k) refs[rawRef.k] = value;
        } else ;
      };
      if (value) {
        const job = () => {
          doSet();
          pendingSetRefMap.delete(rawRef);
        };
        job.id = -1;
        pendingSetRefMap.set(rawRef, job);
        queuePostRenderEffect(job, parentSuspense);
      } else {
        invalidatePendingSetRef(rawRef);
        doSet();
      }
    }
  }
}
function invalidatePendingSetRef(rawRef) {
  const pendingSetRef = pendingSetRefMap.get(rawRef);
  if (pendingSetRef) {
    pendingSetRef.flags |= 8;
    pendingSetRefMap.delete(rawRef);
  }
}
getGlobalThis().requestIdleCallback || ((cb) => setTimeout(cb, 1));
getGlobalThis().cancelIdleCallback || ((id) => clearTimeout(id));
const isAsyncWrapper = (i2) => !!i2.type.__asyncLoader;
const isKeepAlive = (vnode) => vnode.type.__isKeepAlive;
function onActivated(hook, target) {
  registerKeepAliveHook(hook, "a", target);
}
function onDeactivated(hook, target) {
  registerKeepAliveHook(hook, "da", target);
}
function registerKeepAliveHook(hook, type, target = currentInstance) {
  const wrappedHook = hook.__wdc || (hook.__wdc = () => {
    let current = target;
    while (current) {
      if (current.isDeactivated) {
        return;
      }
      current = current.parent;
    }
    return hook();
  });
  injectHook(type, wrappedHook, target);
  if (target) {
    let current = target.parent;
    while (current && current.parent) {
      if (isKeepAlive(current.parent.vnode)) {
        injectToKeepAliveRoot(wrappedHook, type, target, current);
      }
      current = current.parent;
    }
  }
}
function injectToKeepAliveRoot(hook, type, target, keepAliveRoot) {
  const injected = injectHook(
    type,
    hook,
    keepAliveRoot,
    true
    /* prepend */
  );
  onUnmounted(() => {
    remove(keepAliveRoot[type], injected);
  }, target);
}
function injectHook(type, hook, target = currentInstance, prepend = false) {
  if (target) {
    const hooks = target[type] || (target[type] = []);
    const wrappedHook = hook.__weh || (hook.__weh = (...args) => {
      pauseTracking();
      const reset = setCurrentInstance(target);
      const res = callWithAsyncErrorHandling(hook, target, type, args);
      reset();
      resetTracking();
      return res;
    });
    if (prepend) {
      hooks.unshift(wrappedHook);
    } else {
      hooks.push(wrappedHook);
    }
    return wrappedHook;
  }
}
const createHook = (lifecycle) => (hook, target = currentInstance) => {
  if (!isInSSRComponentSetup || lifecycle === "sp") {
    injectHook(lifecycle, (...args) => hook(...args), target);
  }
};
const onBeforeMount = createHook("bm");
const onMounted = createHook("m");
const onBeforeUpdate = createHook(
  "bu"
);
const onUpdated = createHook("u");
const onBeforeUnmount = createHook(
  "bum"
);
const onUnmounted = createHook("um");
const onServerPrefetch = createHook(
  "sp"
);
const onRenderTriggered = createHook("rtg");
const onRenderTracked = createHook("rtc");
function onErrorCaptured(hook, target = currentInstance) {
  injectHook("ec", hook, target);
}
const COMPONENTS = "components";
function resolveComponent(name, maybeSelfReference) {
  return resolveAsset(COMPONENTS, name, true, maybeSelfReference) || name;
}
const NULL_DYNAMIC_COMPONENT = /* @__PURE__ */ Symbol.for("v-ndc");
function resolveAsset(type, name, warnMissing = true, maybeSelfReference = false) {
  const instance = currentRenderingInstance || currentInstance;
  if (instance) {
    const Component = instance.type;
    {
      const selfName = getComponentName(
        Component,
        false
      );
      if (selfName && (selfName === name || selfName === camelize(name) || selfName === capitalize(camelize(name)))) {
        return Component;
      }
    }
    const res = (
      // local registration
      // check instance[type] first which is resolved for options API
      resolve(instance[type] || Component[type], name) || // global registration
      resolve(instance.appContext[type], name)
    );
    if (!res && maybeSelfReference) {
      return Component;
    }
    return res;
  }
}
function resolve(registry, name) {
  return registry && (registry[name] || registry[camelize(name)] || registry[capitalize(camelize(name))]);
}
function renderList(source, renderItem, cache, index) {
  let ret;
  const cached = cache;
  const sourceIsArray = isArray(source);
  if (sourceIsArray || isString(source)) {
    const sourceIsReactiveArray = sourceIsArray && isReactive(source);
    let needsWrap = false;
    let isReadonlySource = false;
    if (sourceIsReactiveArray) {
      needsWrap = !isShallow(source);
      isReadonlySource = isReadonly(source);
      source = shallowReadArray(source);
    }
    ret = new Array(source.length);
    for (let i2 = 0, l2 = source.length; i2 < l2; i2++) {
      ret[i2] = renderItem(
        needsWrap ? isReadonlySource ? toReadonly(toReactive(source[i2])) : toReactive(source[i2]) : source[i2],
        i2,
        void 0,
        cached
      );
    }
  } else if (typeof source === "number") {
    ret = new Array(source);
    for (let i2 = 0; i2 < source; i2++) {
      ret[i2] = renderItem(i2 + 1, i2, void 0, cached);
    }
  } else if (isObject(source)) {
    if (source[Symbol.iterator]) {
      ret = Array.from(
        source,
        (item, i2) => renderItem(item, i2, void 0, cached)
      );
    } else {
      const keys = Object.keys(source);
      ret = new Array(keys.length);
      for (let i2 = 0, l2 = keys.length; i2 < l2; i2++) {
        const key = keys[i2];
        ret[i2] = renderItem(source[key], key, i2, cached);
      }
    }
  } else {
    ret = [];
  }
  return ret;
}
function renderSlot(slots, name, props = {}, fallback, noSlotted) {
  if (currentRenderingInstance.ce || currentRenderingInstance.parent && isAsyncWrapper(currentRenderingInstance.parent) && currentRenderingInstance.parent.ce) {
    const hasProps = Object.keys(props).length > 0;
    if (name !== "default") props.name = name;
    return openBlock(), createBlock(
      Fragment,
      null,
      [createVNode("slot", props, fallback)],
      hasProps ? -2 : 64
    );
  }
  let slot = slots[name];
  if (slot && slot._c) {
    slot._d = false;
  }
  openBlock();
  const validSlotContent = slot && ensureValidVNode(slot(props));
  const slotKey = props.key || // slot content array of a dynamic conditional slot may have a branch
  // key attached in the `createSlots` helper, respect that
  validSlotContent && validSlotContent.key;
  const rendered = createBlock(
    Fragment,
    {
      key: (slotKey && !isSymbol(slotKey) ? slotKey : `_${name}`) + // #7256 force differentiate fallback content from actual content
      (!validSlotContent && fallback ? "_fb" : "")
    },
    validSlotContent || [],
    validSlotContent && slots._ === 1 ? 64 : -2
  );
  if (slot && slot._c) {
    slot._d = true;
  }
  return rendered;
}
function ensureValidVNode(vnodes) {
  return vnodes.some((child) => {
    if (!isVNode(child)) return true;
    if (child.type === Comment) return false;
    if (child.type === Fragment && !ensureValidVNode(child.children))
      return false;
    return true;
  }) ? vnodes : null;
}
const getPublicInstance = (i2) => {
  if (!i2) return null;
  if (isStatefulComponent(i2)) return getComponentPublicInstance(i2);
  return getPublicInstance(i2.parent);
};
const publicPropertiesMap = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ extend(/* @__PURE__ */ Object.create(null), {
    $: (i2) => i2,
    $el: (i2) => i2.vnode.el,
    $data: (i2) => i2.data,
    $props: (i2) => i2.props,
    $attrs: (i2) => i2.attrs,
    $slots: (i2) => i2.slots,
    $refs: (i2) => i2.refs,
    $parent: (i2) => getPublicInstance(i2.parent),
    $root: (i2) => getPublicInstance(i2.root),
    $host: (i2) => i2.ce,
    $emit: (i2) => i2.emit,
    $options: (i2) => resolveMergedOptions(i2),
    $forceUpdate: (i2) => i2.f || (i2.f = () => {
      queueJob(i2.update);
    }),
    $nextTick: (i2) => i2.n || (i2.n = nextTick.bind(i2.proxy)),
    $watch: (i2) => instanceWatch.bind(i2)
  })
);
const hasSetupBinding = (state, key) => state !== EMPTY_OBJ && !state.__isScriptSetup && hasOwn(state, key);
const PublicInstanceProxyHandlers = {
  get({ _: instance }, key) {
    if (key === "__v_skip") {
      return true;
    }
    const { ctx, setupState, data, props, accessCache, type, appContext } = instance;
    if (key[0] !== "$") {
      const n = accessCache[key];
      if (n !== void 0) {
        switch (n) {
          case 1:
            return setupState[key];
          case 2:
            return data[key];
          case 4:
            return ctx[key];
          case 3:
            return props[key];
        }
      } else if (hasSetupBinding(setupState, key)) {
        accessCache[key] = 1;
        return setupState[key];
      } else if (data !== EMPTY_OBJ && hasOwn(data, key)) {
        accessCache[key] = 2;
        return data[key];
      } else if (hasOwn(props, key)) {
        accessCache[key] = 3;
        return props[key];
      } else if (ctx !== EMPTY_OBJ && hasOwn(ctx, key)) {
        accessCache[key] = 4;
        return ctx[key];
      } else if (shouldCacheAccess) {
        accessCache[key] = 0;
      }
    }
    const publicGetter = publicPropertiesMap[key];
    let cssModule, globalProperties;
    if (publicGetter) {
      if (key === "$attrs") {
        track(instance.attrs, "get", "");
      }
      return publicGetter(instance);
    } else if (
      // css module (injected by vue-loader)
      (cssModule = type.__cssModules) && (cssModule = cssModule[key])
    ) {
      return cssModule;
    } else if (ctx !== EMPTY_OBJ && hasOwn(ctx, key)) {
      accessCache[key] = 4;
      return ctx[key];
    } else if (
      // global properties
      globalProperties = appContext.config.globalProperties, hasOwn(globalProperties, key)
    ) {
      {
        return globalProperties[key];
      }
    } else ;
  },
  set({ _: instance }, key, value) {
    const { data, setupState, ctx } = instance;
    if (hasSetupBinding(setupState, key)) {
      setupState[key] = value;
      return true;
    } else if (data !== EMPTY_OBJ && hasOwn(data, key)) {
      data[key] = value;
      return true;
    } else if (hasOwn(instance.props, key)) {
      return false;
    }
    if (key[0] === "$" && key.slice(1) in instance) {
      return false;
    } else {
      {
        ctx[key] = value;
      }
    }
    return true;
  },
  has({
    _: { data, setupState, accessCache, ctx, appContext, props, type }
  }, key) {
    let cssModules;
    return !!(accessCache[key] || data !== EMPTY_OBJ && key[0] !== "$" && hasOwn(data, key) || hasSetupBinding(setupState, key) || hasOwn(props, key) || hasOwn(ctx, key) || hasOwn(publicPropertiesMap, key) || hasOwn(appContext.config.globalProperties, key) || (cssModules = type.__cssModules) && cssModules[key]);
  },
  defineProperty(target, key, descriptor) {
    if (descriptor.get != null) {
      target._.accessCache[key] = 0;
    } else if (hasOwn(descriptor, "value")) {
      this.set(target, key, descriptor.value, null);
    }
    return Reflect.defineProperty(target, key, descriptor);
  }
};
function normalizePropsOrEmits(props) {
  return isArray(props) ? props.reduce(
    (normalized, p2) => (normalized[p2] = null, normalized),
    {}
  ) : props;
}
let shouldCacheAccess = true;
function applyOptions(instance) {
  const options = resolveMergedOptions(instance);
  const publicThis = instance.proxy;
  const ctx = instance.ctx;
  shouldCacheAccess = false;
  if (options.beforeCreate) {
    callHook$1(options.beforeCreate, instance, "bc");
  }
  const {
    // state
    data: dataOptions,
    computed: computedOptions,
    methods,
    watch: watchOptions,
    provide: provideOptions,
    inject: injectOptions,
    // lifecycle
    created,
    beforeMount,
    mounted,
    beforeUpdate,
    updated,
    activated,
    deactivated,
    beforeDestroy,
    beforeUnmount,
    destroyed,
    unmounted,
    render,
    renderTracked,
    renderTriggered,
    errorCaptured,
    serverPrefetch,
    // public API
    expose,
    inheritAttrs,
    // assets
    components,
    directives,
    filters
  } = options;
  const checkDuplicateProperties = null;
  if (injectOptions) {
    resolveInjections(injectOptions, ctx, checkDuplicateProperties);
  }
  if (methods) {
    for (const key in methods) {
      const methodHandler = methods[key];
      if (isFunction(methodHandler)) {
        {
          ctx[key] = methodHandler.bind(publicThis);
        }
      }
    }
  }
  if (dataOptions) {
    const data = dataOptions.call(publicThis, publicThis);
    if (!isObject(data)) ;
    else {
      instance.data = reactive(data);
    }
  }
  shouldCacheAccess = true;
  if (computedOptions) {
    for (const key in computedOptions) {
      const opt = computedOptions[key];
      const get = isFunction(opt) ? opt.bind(publicThis, publicThis) : isFunction(opt.get) ? opt.get.bind(publicThis, publicThis) : NOOP;
      const set = !isFunction(opt) && isFunction(opt.set) ? opt.set.bind(publicThis) : NOOP;
      const c2 = computed({
        get,
        set
      });
      Object.defineProperty(ctx, key, {
        enumerable: true,
        configurable: true,
        get: () => c2.value,
        set: (v2) => c2.value = v2
      });
    }
  }
  if (watchOptions) {
    for (const key in watchOptions) {
      createWatcher(watchOptions[key], ctx, publicThis, key);
    }
  }
  if (provideOptions) {
    const provides = isFunction(provideOptions) ? provideOptions.call(publicThis) : provideOptions;
    Reflect.ownKeys(provides).forEach((key) => {
      provide(key, provides[key]);
    });
  }
  if (created) {
    callHook$1(created, instance, "c");
  }
  function registerLifecycleHook(register, hook) {
    if (isArray(hook)) {
      hook.forEach((_hook) => register(_hook.bind(publicThis)));
    } else if (hook) {
      register(hook.bind(publicThis));
    }
  }
  registerLifecycleHook(onBeforeMount, beforeMount);
  registerLifecycleHook(onMounted, mounted);
  registerLifecycleHook(onBeforeUpdate, beforeUpdate);
  registerLifecycleHook(onUpdated, updated);
  registerLifecycleHook(onActivated, activated);
  registerLifecycleHook(onDeactivated, deactivated);
  registerLifecycleHook(onErrorCaptured, errorCaptured);
  registerLifecycleHook(onRenderTracked, renderTracked);
  registerLifecycleHook(onRenderTriggered, renderTriggered);
  registerLifecycleHook(onBeforeUnmount, beforeUnmount);
  registerLifecycleHook(onUnmounted, unmounted);
  registerLifecycleHook(onServerPrefetch, serverPrefetch);
  if (isArray(expose)) {
    if (expose.length) {
      const exposed = instance.exposed || (instance.exposed = {});
      expose.forEach((key) => {
        Object.defineProperty(exposed, key, {
          get: () => publicThis[key],
          set: (val) => publicThis[key] = val,
          enumerable: true
        });
      });
    } else if (!instance.exposed) {
      instance.exposed = {};
    }
  }
  if (render && instance.render === NOOP) {
    instance.render = render;
  }
  if (inheritAttrs != null) {
    instance.inheritAttrs = inheritAttrs;
  }
  if (components) instance.components = components;
  if (directives) instance.directives = directives;
  if (serverPrefetch) {
    markAsyncBoundary(instance);
  }
}
function resolveInjections(injectOptions, ctx, checkDuplicateProperties = NOOP) {
  if (isArray(injectOptions)) {
    injectOptions = normalizeInject(injectOptions);
  }
  for (const key in injectOptions) {
    const opt = injectOptions[key];
    let injected;
    if (isObject(opt)) {
      if ("default" in opt) {
        injected = inject(
          opt.from || key,
          opt.default,
          true
        );
      } else {
        injected = inject(opt.from || key);
      }
    } else {
      injected = inject(opt);
    }
    if (isRef(injected)) {
      Object.defineProperty(ctx, key, {
        enumerable: true,
        configurable: true,
        get: () => injected.value,
        set: (v2) => injected.value = v2
      });
    } else {
      ctx[key] = injected;
    }
  }
}
function callHook$1(hook, instance, type) {
  callWithAsyncErrorHandling(
    isArray(hook) ? hook.map((h2) => h2.bind(instance.proxy)) : hook.bind(instance.proxy),
    instance,
    type
  );
}
function createWatcher(raw, ctx, publicThis, key) {
  let getter = key.includes(".") ? createPathGetter(publicThis, key) : () => publicThis[key];
  if (isString(raw)) {
    const handler = ctx[raw];
    if (isFunction(handler)) {
      {
        watch(getter, handler);
      }
    }
  } else if (isFunction(raw)) {
    {
      watch(getter, raw.bind(publicThis));
    }
  } else if (isObject(raw)) {
    if (isArray(raw)) {
      raw.forEach((r) => createWatcher(r, ctx, publicThis, key));
    } else {
      const handler = isFunction(raw.handler) ? raw.handler.bind(publicThis) : ctx[raw.handler];
      if (isFunction(handler)) {
        watch(getter, handler, raw);
      }
    }
  } else ;
}
function resolveMergedOptions(instance) {
  const base = instance.type;
  const { mixins, extends: extendsOptions } = base;
  const {
    mixins: globalMixins,
    optionsCache: cache,
    config: { optionMergeStrategies }
  } = instance.appContext;
  const cached = cache.get(base);
  let resolved;
  if (cached) {
    resolved = cached;
  } else if (!globalMixins.length && !mixins && !extendsOptions) {
    {
      resolved = base;
    }
  } else {
    resolved = {};
    if (globalMixins.length) {
      globalMixins.forEach(
        (m2) => mergeOptions(resolved, m2, optionMergeStrategies, true)
      );
    }
    mergeOptions(resolved, base, optionMergeStrategies);
  }
  if (isObject(base)) {
    cache.set(base, resolved);
  }
  return resolved;
}
function mergeOptions(to, from, strats, asMixin = false) {
  const { mixins, extends: extendsOptions } = from;
  if (extendsOptions) {
    mergeOptions(to, extendsOptions, strats, true);
  }
  if (mixins) {
    mixins.forEach(
      (m2) => mergeOptions(to, m2, strats, true)
    );
  }
  for (const key in from) {
    if (asMixin && key === "expose") ;
    else {
      const strat = internalOptionMergeStrats[key] || strats && strats[key];
      to[key] = strat ? strat(to[key], from[key]) : from[key];
    }
  }
  return to;
}
const internalOptionMergeStrats = {
  data: mergeDataFn,
  props: mergeEmitsOrPropsOptions,
  emits: mergeEmitsOrPropsOptions,
  // objects
  methods: mergeObjectOptions,
  computed: mergeObjectOptions,
  // lifecycle
  beforeCreate: mergeAsArray,
  created: mergeAsArray,
  beforeMount: mergeAsArray,
  mounted: mergeAsArray,
  beforeUpdate: mergeAsArray,
  updated: mergeAsArray,
  beforeDestroy: mergeAsArray,
  beforeUnmount: mergeAsArray,
  destroyed: mergeAsArray,
  unmounted: mergeAsArray,
  activated: mergeAsArray,
  deactivated: mergeAsArray,
  errorCaptured: mergeAsArray,
  serverPrefetch: mergeAsArray,
  // assets
  components: mergeObjectOptions,
  directives: mergeObjectOptions,
  // watch
  watch: mergeWatchOptions,
  // provide / inject
  provide: mergeDataFn,
  inject: mergeInject
};
function mergeDataFn(to, from) {
  if (!from) {
    return to;
  }
  if (!to) {
    return from;
  }
  return function mergedDataFn() {
    return extend(
      isFunction(to) ? to.call(this, this) : to,
      isFunction(from) ? from.call(this, this) : from
    );
  };
}
function mergeInject(to, from) {
  return mergeObjectOptions(normalizeInject(to), normalizeInject(from));
}
function normalizeInject(raw) {
  if (isArray(raw)) {
    const res = {};
    for (let i2 = 0; i2 < raw.length; i2++) {
      res[raw[i2]] = raw[i2];
    }
    return res;
  }
  return raw;
}
function mergeAsArray(to, from) {
  return to ? [...new Set([].concat(to, from))] : from;
}
function mergeObjectOptions(to, from) {
  return to ? extend(/* @__PURE__ */ Object.create(null), to, from) : from;
}
function mergeEmitsOrPropsOptions(to, from) {
  if (to) {
    if (isArray(to) && isArray(from)) {
      return [.../* @__PURE__ */ new Set([...to, ...from])];
    }
    return extend(
      /* @__PURE__ */ Object.create(null),
      normalizePropsOrEmits(to),
      normalizePropsOrEmits(from != null ? from : {})
    );
  } else {
    return from;
  }
}
function mergeWatchOptions(to, from) {
  if (!to) return from;
  if (!from) return to;
  const merged = extend(/* @__PURE__ */ Object.create(null), to);
  for (const key in from) {
    merged[key] = mergeAsArray(to[key], from[key]);
  }
  return merged;
}
function createAppContext() {
  return {
    app: null,
    config: {
      isNativeTag: NO,
      performance: false,
      globalProperties: {},
      optionMergeStrategies: {},
      errorHandler: void 0,
      warnHandler: void 0,
      compilerOptions: {}
    },
    mixins: [],
    components: {},
    directives: {},
    provides: /* @__PURE__ */ Object.create(null),
    optionsCache: /* @__PURE__ */ new WeakMap(),
    propsCache: /* @__PURE__ */ new WeakMap(),
    emitsCache: /* @__PURE__ */ new WeakMap()
  };
}
let uid$1 = 0;
function createAppAPI(render, hydrate) {
  return function createApp2(rootComponent, rootProps = null) {
    if (!isFunction(rootComponent)) {
      rootComponent = extend({}, rootComponent);
    }
    if (rootProps != null && !isObject(rootProps)) {
      rootProps = null;
    }
    const context = createAppContext();
    const installedPlugins = /* @__PURE__ */ new WeakSet();
    const pluginCleanupFns = [];
    let isMounted = false;
    const app2 = context.app = {
      _uid: uid$1++,
      _component: rootComponent,
      _props: rootProps,
      _container: null,
      _context: context,
      _instance: null,
      version,
      get config() {
        return context.config;
      },
      set config(v2) {
      },
      use(plugin, ...options) {
        if (installedPlugins.has(plugin)) ;
        else if (plugin && isFunction(plugin.install)) {
          installedPlugins.add(plugin);
          plugin.install(app2, ...options);
        } else if (isFunction(plugin)) {
          installedPlugins.add(plugin);
          plugin(app2, ...options);
        } else ;
        return app2;
      },
      mixin(mixin) {
        {
          if (!context.mixins.includes(mixin)) {
            context.mixins.push(mixin);
          }
        }
        return app2;
      },
      component(name, component) {
        if (!component) {
          return context.components[name];
        }
        context.components[name] = component;
        return app2;
      },
      directive(name, directive) {
        if (!directive) {
          return context.directives[name];
        }
        context.directives[name] = directive;
        return app2;
      },
      mount(rootContainer, isHydrate, namespace) {
        if (!isMounted) {
          const vnode = app2._ceVNode || createVNode(rootComponent, rootProps);
          vnode.appContext = context;
          if (namespace === true) {
            namespace = "svg";
          } else if (namespace === false) {
            namespace = void 0;
          }
          {
            render(vnode, rootContainer, namespace);
          }
          isMounted = true;
          app2._container = rootContainer;
          rootContainer.__vue_app__ = app2;
          return getComponentPublicInstance(vnode.component);
        }
      },
      onUnmount(cleanupFn) {
        pluginCleanupFns.push(cleanupFn);
      },
      unmount() {
        if (isMounted) {
          callWithAsyncErrorHandling(
            pluginCleanupFns,
            app2._instance,
            16
          );
          render(null, app2._container);
          delete app2._container.__vue_app__;
        }
      },
      provide(key, value) {
        context.provides[key] = value;
        return app2;
      },
      runWithContext(fn) {
        const lastApp = currentApp;
        currentApp = app2;
        try {
          return fn();
        } finally {
          currentApp = lastApp;
        }
      }
    };
    return app2;
  };
}
let currentApp = null;
const getModelModifiers = (props, modelName) => {
  return modelName === "modelValue" || modelName === "model-value" ? props.modelModifiers : props[`${modelName}Modifiers`] || props[`${camelize(modelName)}Modifiers`] || props[`${hyphenate(modelName)}Modifiers`];
};
function emit(instance, event, ...rawArgs) {
  if (instance.isUnmounted) return;
  const props = instance.vnode.props || EMPTY_OBJ;
  let args = rawArgs;
  const isModelListener2 = event.startsWith("update:");
  const modifiers = isModelListener2 && getModelModifiers(props, event.slice(7));
  if (modifiers) {
    if (modifiers.trim) {
      args = rawArgs.map((a2) => isString(a2) ? a2.trim() : a2);
    }
    if (modifiers.number) {
      args = rawArgs.map(looseToNumber);
    }
  }
  let handlerName;
  let handler = props[handlerName = toHandlerKey(event)] || // also try camelCase event handler (#2249)
  props[handlerName = toHandlerKey(camelize(event))];
  if (!handler && isModelListener2) {
    handler = props[handlerName = toHandlerKey(hyphenate(event))];
  }
  if (handler) {
    callWithAsyncErrorHandling(
      handler,
      instance,
      6,
      args
    );
  }
  const onceHandler = props[handlerName + `Once`];
  if (onceHandler) {
    if (!instance.emitted) {
      instance.emitted = {};
    } else if (instance.emitted[handlerName]) {
      return;
    }
    instance.emitted[handlerName] = true;
    callWithAsyncErrorHandling(
      onceHandler,
      instance,
      6,
      args
    );
  }
}
const mixinEmitsCache = /* @__PURE__ */ new WeakMap();
function normalizeEmitsOptions(comp, appContext, asMixin = false) {
  const cache = asMixin ? mixinEmitsCache : appContext.emitsCache;
  const cached = cache.get(comp);
  if (cached !== void 0) {
    return cached;
  }
  const raw = comp.emits;
  let normalized = {};
  let hasExtends = false;
  if (!isFunction(comp)) {
    const extendEmits = (raw2) => {
      const normalizedFromExtend = normalizeEmitsOptions(raw2, appContext, true);
      if (normalizedFromExtend) {
        hasExtends = true;
        extend(normalized, normalizedFromExtend);
      }
    };
    if (!asMixin && appContext.mixins.length) {
      appContext.mixins.forEach(extendEmits);
    }
    if (comp.extends) {
      extendEmits(comp.extends);
    }
    if (comp.mixins) {
      comp.mixins.forEach(extendEmits);
    }
  }
  if (!raw && !hasExtends) {
    if (isObject(comp)) {
      cache.set(comp, null);
    }
    return null;
  }
  if (isArray(raw)) {
    raw.forEach((key) => normalized[key] = null);
  } else {
    extend(normalized, raw);
  }
  if (isObject(comp)) {
    cache.set(comp, normalized);
  }
  return normalized;
}
function isEmitListener(options, key) {
  if (!options || !isOn(key)) {
    return false;
  }
  key = key.slice(2).replace(/Once$/, "");
  return hasOwn(options, key[0].toLowerCase() + key.slice(1)) || hasOwn(options, hyphenate(key)) || hasOwn(options, key);
}
function markAttrsAccessed() {
}
function renderComponentRoot(instance) {
  const {
    type: Component,
    vnode,
    proxy,
    withProxy,
    propsOptions: [propsOptions],
    slots,
    attrs,
    emit: emit2,
    render,
    renderCache,
    props,
    data,
    setupState,
    ctx,
    inheritAttrs
  } = instance;
  const prev = setCurrentRenderingInstance(instance);
  let result;
  let fallthroughAttrs;
  try {
    if (vnode.shapeFlag & 4) {
      const proxyToUse = withProxy || proxy;
      const thisProxy = false ? new Proxy(proxyToUse, {
        get(target, key, receiver) {
          warn$1(
            `Property '${String(
              key
            )}' was accessed via 'this'. Avoid using 'this' in templates.`
          );
          return Reflect.get(target, key, receiver);
        }
      }) : proxyToUse;
      result = normalizeVNode(
        render.call(
          thisProxy,
          proxyToUse,
          renderCache,
          false ? shallowReadonly(props) : props,
          setupState,
          data,
          ctx
        )
      );
      fallthroughAttrs = attrs;
    } else {
      const render2 = Component;
      if (false) ;
      result = normalizeVNode(
        render2.length > 1 ? render2(
          false ? shallowReadonly(props) : props,
          false ? {
            get attrs() {
              markAttrsAccessed();
              return shallowReadonly(attrs);
            },
            slots,
            emit: emit2
          } : { attrs, slots, emit: emit2 }
        ) : render2(
          false ? shallowReadonly(props) : props,
          null
        )
      );
      fallthroughAttrs = Component.props ? attrs : getFunctionalFallthrough(attrs);
    }
  } catch (err) {
    blockStack.length = 0;
    handleError(err, instance, 1);
    result = createVNode(Comment);
  }
  let root = result;
  if (fallthroughAttrs && inheritAttrs !== false) {
    const keys = Object.keys(fallthroughAttrs);
    const { shapeFlag } = root;
    if (keys.length) {
      if (shapeFlag & (1 | 6)) {
        if (propsOptions && keys.some(isModelListener)) {
          fallthroughAttrs = filterModelListeners(
            fallthroughAttrs,
            propsOptions
          );
        }
        root = cloneVNode(root, fallthroughAttrs, false, true);
      }
    }
  }
  if (vnode.dirs) {
    root = cloneVNode(root, null, false, true);
    root.dirs = root.dirs ? root.dirs.concat(vnode.dirs) : vnode.dirs;
  }
  if (vnode.transition) {
    setTransitionHooks(root, vnode.transition);
  }
  {
    result = root;
  }
  setCurrentRenderingInstance(prev);
  return result;
}
const getFunctionalFallthrough = (attrs) => {
  let res;
  for (const key in attrs) {
    if (key === "class" || key === "style" || isOn(key)) {
      (res || (res = {}))[key] = attrs[key];
    }
  }
  return res;
};
const filterModelListeners = (attrs, props) => {
  const res = {};
  for (const key in attrs) {
    if (!isModelListener(key) || !(key.slice(9) in props)) {
      res[key] = attrs[key];
    }
  }
  return res;
};
function shouldUpdateComponent(prevVNode, nextVNode, optimized) {
  const { props: prevProps, children: prevChildren, component } = prevVNode;
  const { props: nextProps, children: nextChildren, patchFlag } = nextVNode;
  const emits = component.emitsOptions;
  if (nextVNode.dirs || nextVNode.transition) {
    return true;
  }
  if (optimized && patchFlag >= 0) {
    if (patchFlag & 1024) {
      return true;
    }
    if (patchFlag & 16) {
      if (!prevProps) {
        return !!nextProps;
      }
      return hasPropsChanged(prevProps, nextProps, emits);
    } else if (patchFlag & 8) {
      const dynamicProps = nextVNode.dynamicProps;
      for (let i2 = 0; i2 < dynamicProps.length; i2++) {
        const key = dynamicProps[i2];
        if (nextProps[key] !== prevProps[key] && !isEmitListener(emits, key)) {
          return true;
        }
      }
    }
  } else {
    if (prevChildren || nextChildren) {
      if (!nextChildren || !nextChildren.$stable) {
        return true;
      }
    }
    if (prevProps === nextProps) {
      return false;
    }
    if (!prevProps) {
      return !!nextProps;
    }
    if (!nextProps) {
      return true;
    }
    return hasPropsChanged(prevProps, nextProps, emits);
  }
  return false;
}
function hasPropsChanged(prevProps, nextProps, emitsOptions) {
  const nextKeys = Object.keys(nextProps);
  if (nextKeys.length !== Object.keys(prevProps).length) {
    return true;
  }
  for (let i2 = 0; i2 < nextKeys.length; i2++) {
    const key = nextKeys[i2];
    if (nextProps[key] !== prevProps[key] && !isEmitListener(emitsOptions, key)) {
      return true;
    }
  }
  return false;
}
function updateHOCHostEl({ vnode, parent }, el) {
  while (parent) {
    const root = parent.subTree;
    if (root.suspense && root.suspense.activeBranch === vnode) {
      root.el = vnode.el;
    }
    if (root === vnode) {
      (vnode = parent.vnode).el = el;
      parent = parent.parent;
    } else {
      break;
    }
  }
}
const internalObjectProto = {};
const createInternalObject = () => Object.create(internalObjectProto);
const isInternalObject = (obj) => Object.getPrototypeOf(obj) === internalObjectProto;
function initProps(instance, rawProps, isStateful, isSSR = false) {
  const props = {};
  const attrs = createInternalObject();
  instance.propsDefaults = /* @__PURE__ */ Object.create(null);
  setFullProps(instance, rawProps, props, attrs);
  for (const key in instance.propsOptions[0]) {
    if (!(key in props)) {
      props[key] = void 0;
    }
  }
  if (isStateful) {
    instance.props = isSSR ? props : shallowReactive(props);
  } else {
    if (!instance.type.props) {
      instance.props = attrs;
    } else {
      instance.props = props;
    }
  }
  instance.attrs = attrs;
}
function updateProps(instance, rawProps, rawPrevProps, optimized) {
  const {
    props,
    attrs,
    vnode: { patchFlag }
  } = instance;
  const rawCurrentProps = toRaw(props);
  const [options] = instance.propsOptions;
  let hasAttrsChanged = false;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (optimized || patchFlag > 0) && !(patchFlag & 16)
  ) {
    if (patchFlag & 8) {
      const propsToUpdate = instance.vnode.dynamicProps;
      for (let i2 = 0; i2 < propsToUpdate.length; i2++) {
        let key = propsToUpdate[i2];
        if (isEmitListener(instance.emitsOptions, key)) {
          continue;
        }
        const value = rawProps[key];
        if (options) {
          if (hasOwn(attrs, key)) {
            if (value !== attrs[key]) {
              attrs[key] = value;
              hasAttrsChanged = true;
            }
          } else {
            const camelizedKey = camelize(key);
            props[camelizedKey] = resolvePropValue(
              options,
              rawCurrentProps,
              camelizedKey,
              value,
              instance,
              false
            );
          }
        } else {
          if (value !== attrs[key]) {
            attrs[key] = value;
            hasAttrsChanged = true;
          }
        }
      }
    }
  } else {
    if (setFullProps(instance, rawProps, props, attrs)) {
      hasAttrsChanged = true;
    }
    let kebabKey;
    for (const key in rawCurrentProps) {
      if (!rawProps || // for camelCase
      !hasOwn(rawProps, key) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((kebabKey = hyphenate(key)) === key || !hasOwn(rawProps, kebabKey))) {
        if (options) {
          if (rawPrevProps && // for camelCase
          (rawPrevProps[key] !== void 0 || // for kebab-case
          rawPrevProps[kebabKey] !== void 0)) {
            props[key] = resolvePropValue(
              options,
              rawCurrentProps,
              key,
              void 0,
              instance,
              true
            );
          }
        } else {
          delete props[key];
        }
      }
    }
    if (attrs !== rawCurrentProps) {
      for (const key in attrs) {
        if (!rawProps || !hasOwn(rawProps, key) && true) {
          delete attrs[key];
          hasAttrsChanged = true;
        }
      }
    }
  }
  if (hasAttrsChanged) {
    trigger(instance.attrs, "set", "");
  }
}
function setFullProps(instance, rawProps, props, attrs) {
  const [options, needCastKeys] = instance.propsOptions;
  let hasAttrsChanged = false;
  let rawCastValues;
  if (rawProps) {
    for (let key in rawProps) {
      if (isReservedProp(key)) {
        continue;
      }
      const value = rawProps[key];
      let camelKey;
      if (options && hasOwn(options, camelKey = camelize(key))) {
        if (!needCastKeys || !needCastKeys.includes(camelKey)) {
          props[camelKey] = value;
        } else {
          (rawCastValues || (rawCastValues = {}))[camelKey] = value;
        }
      } else if (!isEmitListener(instance.emitsOptions, key)) {
        if (!(key in attrs) || value !== attrs[key]) {
          attrs[key] = value;
          hasAttrsChanged = true;
        }
      }
    }
  }
  if (needCastKeys) {
    const rawCurrentProps = toRaw(props);
    const castValues = rawCastValues || EMPTY_OBJ;
    for (let i2 = 0; i2 < needCastKeys.length; i2++) {
      const key = needCastKeys[i2];
      props[key] = resolvePropValue(
        options,
        rawCurrentProps,
        key,
        castValues[key],
        instance,
        !hasOwn(castValues, key)
      );
    }
  }
  return hasAttrsChanged;
}
function resolvePropValue(options, props, key, value, instance, isAbsent) {
  const opt = options[key];
  if (opt != null) {
    const hasDefault = hasOwn(opt, "default");
    if (hasDefault && value === void 0) {
      const defaultValue = opt.default;
      if (opt.type !== Function && !opt.skipFactory && isFunction(defaultValue)) {
        const { propsDefaults } = instance;
        if (key in propsDefaults) {
          value = propsDefaults[key];
        } else {
          const reset = setCurrentInstance(instance);
          value = propsDefaults[key] = defaultValue.call(
            null,
            props
          );
          reset();
        }
      } else {
        value = defaultValue;
      }
      if (instance.ce) {
        instance.ce._setProp(key, value);
      }
    }
    if (opt[
      0
      /* shouldCast */
    ]) {
      if (isAbsent && !hasDefault) {
        value = false;
      } else if (opt[
        1
        /* shouldCastTrue */
      ] && (value === "" || value === hyphenate(key))) {
        value = true;
      }
    }
  }
  return value;
}
const mixinPropsCache = /* @__PURE__ */ new WeakMap();
function normalizePropsOptions(comp, appContext, asMixin = false) {
  const cache = asMixin ? mixinPropsCache : appContext.propsCache;
  const cached = cache.get(comp);
  if (cached) {
    return cached;
  }
  const raw = comp.props;
  const normalized = {};
  const needCastKeys = [];
  let hasExtends = false;
  if (!isFunction(comp)) {
    const extendProps = (raw2) => {
      hasExtends = true;
      const [props, keys] = normalizePropsOptions(raw2, appContext, true);
      extend(normalized, props);
      if (keys) needCastKeys.push(...keys);
    };
    if (!asMixin && appContext.mixins.length) {
      appContext.mixins.forEach(extendProps);
    }
    if (comp.extends) {
      extendProps(comp.extends);
    }
    if (comp.mixins) {
      comp.mixins.forEach(extendProps);
    }
  }
  if (!raw && !hasExtends) {
    if (isObject(comp)) {
      cache.set(comp, EMPTY_ARR);
    }
    return EMPTY_ARR;
  }
  if (isArray(raw)) {
    for (let i2 = 0; i2 < raw.length; i2++) {
      const normalizedKey = camelize(raw[i2]);
      if (validatePropName(normalizedKey)) {
        normalized[normalizedKey] = EMPTY_OBJ;
      }
    }
  } else if (raw) {
    for (const key in raw) {
      const normalizedKey = camelize(key);
      if (validatePropName(normalizedKey)) {
        const opt = raw[key];
        const prop = normalized[normalizedKey] = isArray(opt) || isFunction(opt) ? { type: opt } : extend({}, opt);
        const propType = prop.type;
        let shouldCast = false;
        let shouldCastTrue = true;
        if (isArray(propType)) {
          for (let index = 0; index < propType.length; ++index) {
            const type = propType[index];
            const typeName = isFunction(type) && type.name;
            if (typeName === "Boolean") {
              shouldCast = true;
              break;
            } else if (typeName === "String") {
              shouldCastTrue = false;
            }
          }
        } else {
          shouldCast = isFunction(propType) && propType.name === "Boolean";
        }
        prop[
          0
          /* shouldCast */
        ] = shouldCast;
        prop[
          1
          /* shouldCastTrue */
        ] = shouldCastTrue;
        if (shouldCast || hasOwn(prop, "default")) {
          needCastKeys.push(normalizedKey);
        }
      }
    }
  }
  const res = [normalized, needCastKeys];
  if (isObject(comp)) {
    cache.set(comp, res);
  }
  return res;
}
function validatePropName(key) {
  if (key[0] !== "$" && !isReservedProp(key)) {
    return true;
  }
  return false;
}
const isInternalKey = (key) => key === "_" || key === "_ctx" || key === "$stable";
const normalizeSlotValue = (value) => isArray(value) ? value.map(normalizeVNode) : [normalizeVNode(value)];
const normalizeSlot = (key, rawSlot, ctx) => {
  if (rawSlot._n) {
    return rawSlot;
  }
  const normalized = withCtx((...args) => {
    if (false) ;
    return normalizeSlotValue(rawSlot(...args));
  }, ctx);
  normalized._c = false;
  return normalized;
};
const normalizeObjectSlots = (rawSlots, slots, instance) => {
  const ctx = rawSlots._ctx;
  for (const key in rawSlots) {
    if (isInternalKey(key)) continue;
    const value = rawSlots[key];
    if (isFunction(value)) {
      slots[key] = normalizeSlot(key, value, ctx);
    } else if (value != null) {
      const normalized = normalizeSlotValue(value);
      slots[key] = () => normalized;
    }
  }
};
const normalizeVNodeSlots = (instance, children) => {
  const normalized = normalizeSlotValue(children);
  instance.slots.default = () => normalized;
};
const assignSlots = (slots, children, optimized) => {
  for (const key in children) {
    if (optimized || !isInternalKey(key)) {
      slots[key] = children[key];
    }
  }
};
const initSlots = (instance, children, optimized) => {
  const slots = instance.slots = createInternalObject();
  if (instance.vnode.shapeFlag & 32) {
    const type = children._;
    if (type) {
      assignSlots(slots, children, optimized);
      if (optimized) {
        def(slots, "_", type, true);
      }
    } else {
      normalizeObjectSlots(children, slots);
    }
  } else if (children) {
    normalizeVNodeSlots(instance, children);
  }
};
const updateSlots = (instance, children, optimized) => {
  const { vnode, slots } = instance;
  let needDeletionCheck = true;
  let deletionComparisonTarget = EMPTY_OBJ;
  if (vnode.shapeFlag & 32) {
    const type = children._;
    if (type) {
      if (optimized && type === 1) {
        needDeletionCheck = false;
      } else {
        assignSlots(slots, children, optimized);
      }
    } else {
      needDeletionCheck = !children.$stable;
      normalizeObjectSlots(children, slots);
    }
    deletionComparisonTarget = children;
  } else if (children) {
    normalizeVNodeSlots(instance, children);
    deletionComparisonTarget = { default: 1 };
  }
  if (needDeletionCheck) {
    for (const key in slots) {
      if (!isInternalKey(key) && deletionComparisonTarget[key] == null) {
        delete slots[key];
      }
    }
  }
};
const queuePostRenderEffect = queueEffectWithSuspense;
function createRenderer(options) {
  return baseCreateRenderer(options);
}
function baseCreateRenderer(options, createHydrationFns) {
  const target = getGlobalThis();
  target.__VUE__ = true;
  const {
    insert: hostInsert,
    remove: hostRemove,
    patchProp: hostPatchProp,
    createElement: hostCreateElement,
    createText: hostCreateText,
    createComment: hostCreateComment,
    setText: hostSetText,
    setElementText: hostSetElementText,
    parentNode: hostParentNode,
    nextSibling: hostNextSibling,
    setScopeId: hostSetScopeId = NOOP,
    insertStaticContent: hostInsertStaticContent
  } = options;
  const patch = (n1, n2, container, anchor = null, parentComponent = null, parentSuspense = null, namespace = void 0, slotScopeIds = null, optimized = !!n2.dynamicChildren) => {
    if (n1 === n2) {
      return;
    }
    if (n1 && !isSameVNodeType(n1, n2)) {
      anchor = getNextHostNode(n1);
      unmount(n1, parentComponent, parentSuspense, true);
      n1 = null;
    }
    if (n2.patchFlag === -2) {
      optimized = false;
      n2.dynamicChildren = null;
    }
    const { type, ref: ref3, shapeFlag } = n2;
    switch (type) {
      case Text:
        processText(n1, n2, container, anchor);
        break;
      case Comment:
        processCommentNode(n1, n2, container, anchor);
        break;
      case Static:
        if (n1 == null) {
          mountStaticNode(n2, container, anchor, namespace);
        }
        break;
      case Fragment:
        processFragment(
          n1,
          n2,
          container,
          anchor,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
        break;
      default:
        if (shapeFlag & 1) {
          processElement(
            n1,
            n2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        } else if (shapeFlag & 6) {
          processComponent(
            n1,
            n2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        } else if (shapeFlag & 64) {
          type.process(
            n1,
            n2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized,
            internals
          );
        } else if (shapeFlag & 128) {
          type.process(
            n1,
            n2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized,
            internals
          );
        } else ;
    }
    if (ref3 != null && parentComponent) {
      setRef(ref3, n1 && n1.ref, parentSuspense, n2 || n1, !n2);
    } else if (ref3 == null && n1 && n1.ref != null) {
      setRef(n1.ref, null, parentSuspense, n1, true);
    }
  };
  const processText = (n1, n2, container, anchor) => {
    if (n1 == null) {
      hostInsert(
        n2.el = hostCreateText(n2.children),
        container,
        anchor
      );
    } else {
      const el = n2.el = n1.el;
      if (n2.children !== n1.children) {
        {
          hostSetText(el, n2.children);
        }
      }
    }
  };
  const processCommentNode = (n1, n2, container, anchor) => {
    if (n1 == null) {
      hostInsert(
        n2.el = hostCreateComment(n2.children || ""),
        container,
        anchor
      );
    } else {
      n2.el = n1.el;
    }
  };
  const mountStaticNode = (n2, container, anchor, namespace) => {
    [n2.el, n2.anchor] = hostInsertStaticContent(
      n2.children,
      container,
      anchor,
      namespace,
      n2.el,
      n2.anchor
    );
  };
  const moveStaticNode = ({ el, anchor }, container, nextSibling) => {
    let next;
    while (el && el !== anchor) {
      next = hostNextSibling(el);
      hostInsert(el, container, nextSibling);
      el = next;
    }
    hostInsert(anchor, container, nextSibling);
  };
  const removeStaticNode = ({ el, anchor }) => {
    let next;
    while (el && el !== anchor) {
      next = hostNextSibling(el);
      hostRemove(el);
      el = next;
    }
    hostRemove(anchor);
  };
  const processElement = (n1, n2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    if (n2.type === "svg") {
      namespace = "svg";
    } else if (n2.type === "math") {
      namespace = "mathml";
    }
    if (n1 == null) {
      mountElement(
        n2,
        container,
        anchor,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        optimized
      );
    } else {
      const customElement = !!(n1.el && n1.el._isVueCE) ? n1.el : null;
      try {
        if (customElement) {
          customElement._beginPatch();
        }
        patchElement(
          n1,
          n2,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
      } finally {
        if (customElement) {
          customElement._endPatch();
        }
      }
    }
  };
  const mountElement = (vnode, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    let el;
    let vnodeHook;
    const { props, shapeFlag, transition, dirs } = vnode;
    el = vnode.el = hostCreateElement(
      vnode.type,
      namespace,
      props && props.is,
      props
    );
    if (shapeFlag & 8) {
      hostSetElementText(el, vnode.children);
    } else if (shapeFlag & 16) {
      mountChildren(
        vnode.children,
        el,
        null,
        parentComponent,
        parentSuspense,
        resolveChildrenNamespace(vnode, namespace),
        slotScopeIds,
        optimized
      );
    }
    if (dirs) {
      invokeDirectiveHook(vnode, null, parentComponent, "created");
    }
    setScopeId(el, vnode, vnode.scopeId, slotScopeIds, parentComponent);
    if (props) {
      for (const key in props) {
        if (key !== "value" && !isReservedProp(key)) {
          hostPatchProp(el, key, null, props[key], namespace, parentComponent);
        }
      }
      if ("value" in props) {
        hostPatchProp(el, "value", null, props.value, namespace);
      }
      if (vnodeHook = props.onVnodeBeforeMount) {
        invokeVNodeHook(vnodeHook, parentComponent, vnode);
      }
    }
    if (dirs) {
      invokeDirectiveHook(vnode, null, parentComponent, "beforeMount");
    }
    const needCallTransitionHooks = needTransition(parentSuspense, transition);
    if (needCallTransitionHooks) {
      transition.beforeEnter(el);
    }
    hostInsert(el, container, anchor);
    if ((vnodeHook = props && props.onVnodeMounted) || needCallTransitionHooks || dirs) {
      queuePostRenderEffect(() => {
        vnodeHook && invokeVNodeHook(vnodeHook, parentComponent, vnode);
        needCallTransitionHooks && transition.enter(el);
        dirs && invokeDirectiveHook(vnode, null, parentComponent, "mounted");
      }, parentSuspense);
    }
  };
  const setScopeId = (el, vnode, scopeId, slotScopeIds, parentComponent) => {
    if (scopeId) {
      hostSetScopeId(el, scopeId);
    }
    if (slotScopeIds) {
      for (let i2 = 0; i2 < slotScopeIds.length; i2++) {
        hostSetScopeId(el, slotScopeIds[i2]);
      }
    }
    if (parentComponent) {
      let subTree = parentComponent.subTree;
      if (vnode === subTree || isSuspense(subTree.type) && (subTree.ssContent === vnode || subTree.ssFallback === vnode)) {
        const parentVNode = parentComponent.vnode;
        setScopeId(
          el,
          parentVNode,
          parentVNode.scopeId,
          parentVNode.slotScopeIds,
          parentComponent.parent
        );
      }
    }
  };
  const mountChildren = (children, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized, start = 0) => {
    for (let i2 = start; i2 < children.length; i2++) {
      const child = children[i2] = optimized ? cloneIfMounted(children[i2]) : normalizeVNode(children[i2]);
      patch(
        null,
        child,
        container,
        anchor,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        optimized
      );
    }
  };
  const patchElement = (n1, n2, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    const el = n2.el = n1.el;
    let { patchFlag, dynamicChildren, dirs } = n2;
    patchFlag |= n1.patchFlag & 16;
    const oldProps = n1.props || EMPTY_OBJ;
    const newProps = n2.props || EMPTY_OBJ;
    let vnodeHook;
    parentComponent && toggleRecurse(parentComponent, false);
    if (vnodeHook = newProps.onVnodeBeforeUpdate) {
      invokeVNodeHook(vnodeHook, parentComponent, n2, n1);
    }
    if (dirs) {
      invokeDirectiveHook(n2, n1, parentComponent, "beforeUpdate");
    }
    parentComponent && toggleRecurse(parentComponent, true);
    if (oldProps.innerHTML && newProps.innerHTML == null || oldProps.textContent && newProps.textContent == null) {
      hostSetElementText(el, "");
    }
    if (dynamicChildren) {
      patchBlockChildren(
        n1.dynamicChildren,
        dynamicChildren,
        el,
        parentComponent,
        parentSuspense,
        resolveChildrenNamespace(n2, namespace),
        slotScopeIds
      );
    } else if (!optimized) {
      patchChildren(
        n1,
        n2,
        el,
        null,
        parentComponent,
        parentSuspense,
        resolveChildrenNamespace(n2, namespace),
        slotScopeIds,
        false
      );
    }
    if (patchFlag > 0) {
      if (patchFlag & 16) {
        patchProps(el, oldProps, newProps, parentComponent, namespace);
      } else {
        if (patchFlag & 2) {
          if (oldProps.class !== newProps.class) {
            hostPatchProp(el, "class", null, newProps.class, namespace);
          }
        }
        if (patchFlag & 4) {
          hostPatchProp(el, "style", oldProps.style, newProps.style, namespace);
        }
        if (patchFlag & 8) {
          const propsToUpdate = n2.dynamicProps;
          for (let i2 = 0; i2 < propsToUpdate.length; i2++) {
            const key = propsToUpdate[i2];
            const prev = oldProps[key];
            const next = newProps[key];
            if (next !== prev || key === "value") {
              hostPatchProp(el, key, prev, next, namespace, parentComponent);
            }
          }
        }
      }
      if (patchFlag & 1) {
        if (n1.children !== n2.children) {
          hostSetElementText(el, n2.children);
        }
      }
    } else if (!optimized && dynamicChildren == null) {
      patchProps(el, oldProps, newProps, parentComponent, namespace);
    }
    if ((vnodeHook = newProps.onVnodeUpdated) || dirs) {
      queuePostRenderEffect(() => {
        vnodeHook && invokeVNodeHook(vnodeHook, parentComponent, n2, n1);
        dirs && invokeDirectiveHook(n2, n1, parentComponent, "updated");
      }, parentSuspense);
    }
  };
  const patchBlockChildren = (oldChildren, newChildren, fallbackContainer, parentComponent, parentSuspense, namespace, slotScopeIds) => {
    for (let i2 = 0; i2 < newChildren.length; i2++) {
      const oldVNode = oldChildren[i2];
      const newVNode = newChildren[i2];
      const container = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        oldVNode.el && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (oldVNode.type === Fragment || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !isSameVNodeType(oldVNode, newVNode) || // - In the case of a component, it could contain anything.
        oldVNode.shapeFlag & (6 | 64 | 128)) ? hostParentNode(oldVNode.el) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          fallbackContainer
        )
      );
      patch(
        oldVNode,
        newVNode,
        container,
        null,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        true
      );
    }
  };
  const patchProps = (el, oldProps, newProps, parentComponent, namespace) => {
    if (oldProps !== newProps) {
      if (oldProps !== EMPTY_OBJ) {
        for (const key in oldProps) {
          if (!isReservedProp(key) && !(key in newProps)) {
            hostPatchProp(
              el,
              key,
              oldProps[key],
              null,
              namespace,
              parentComponent
            );
          }
        }
      }
      for (const key in newProps) {
        if (isReservedProp(key)) continue;
        const next = newProps[key];
        const prev = oldProps[key];
        if (next !== prev && key !== "value") {
          hostPatchProp(el, key, prev, next, namespace, parentComponent);
        }
      }
      if ("value" in newProps) {
        hostPatchProp(el, "value", oldProps.value, newProps.value, namespace);
      }
    }
  };
  const processFragment = (n1, n2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    const fragmentStartAnchor = n2.el = n1 ? n1.el : hostCreateText("");
    const fragmentEndAnchor = n2.anchor = n1 ? n1.anchor : hostCreateText("");
    let { patchFlag, dynamicChildren, slotScopeIds: fragmentSlotScopeIds } = n2;
    if (fragmentSlotScopeIds) {
      slotScopeIds = slotScopeIds ? slotScopeIds.concat(fragmentSlotScopeIds) : fragmentSlotScopeIds;
    }
    if (n1 == null) {
      hostInsert(fragmentStartAnchor, container, anchor);
      hostInsert(fragmentEndAnchor, container, anchor);
      mountChildren(
        // #10007
        // such fragment like `<></>` will be compiled into
        // a fragment which doesn't have a children.
        // In this case fallback to an empty array
        n2.children || [],
        container,
        fragmentEndAnchor,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        optimized
      );
    } else {
      if (patchFlag > 0 && patchFlag & 64 && dynamicChildren && // #2715 the previous fragment could've been a BAILed one as a result
      // of renderSlot() with no valid children
      n1.dynamicChildren && n1.dynamicChildren.length === dynamicChildren.length) {
        patchBlockChildren(
          n1.dynamicChildren,
          dynamicChildren,
          container,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds
        );
        if (
          // #2080 if the stable fragment has a key, it's a <template v-for> that may
          //  get moved around. Make sure all root level vnodes inherit el.
          // #2134 or if it's a component root, it may also get moved around
          // as the component is being moved.
          n2.key != null || parentComponent && n2 === parentComponent.subTree
        ) {
          traverseStaticChildren(
            n1,
            n2,
            true
            /* shallow */
          );
        }
      } else {
        patchChildren(
          n1,
          n2,
          container,
          fragmentEndAnchor,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
      }
    }
  };
  const processComponent = (n1, n2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    n2.slotScopeIds = slotScopeIds;
    if (n1 == null) {
      if (n2.shapeFlag & 512) {
        parentComponent.ctx.activate(
          n2,
          container,
          anchor,
          namespace,
          optimized
        );
      } else {
        mountComponent(
          n2,
          container,
          anchor,
          parentComponent,
          parentSuspense,
          namespace,
          optimized
        );
      }
    } else {
      updateComponent(n1, n2, optimized);
    }
  };
  const mountComponent = (initialVNode, container, anchor, parentComponent, parentSuspense, namespace, optimized) => {
    const instance = initialVNode.component = createComponentInstance(
      initialVNode,
      parentComponent,
      parentSuspense
    );
    if (isKeepAlive(initialVNode)) {
      instance.ctx.renderer = internals;
    }
    {
      setupComponent(instance, false, optimized);
    }
    if (instance.asyncDep) {
      parentSuspense && parentSuspense.registerDep(instance, setupRenderEffect, optimized);
      if (!initialVNode.el) {
        const placeholder = instance.subTree = createVNode(Comment);
        processCommentNode(null, placeholder, container, anchor);
        initialVNode.placeholder = placeholder.el;
      }
    } else {
      setupRenderEffect(
        instance,
        initialVNode,
        container,
        anchor,
        parentSuspense,
        namespace,
        optimized
      );
    }
  };
  const updateComponent = (n1, n2, optimized) => {
    const instance = n2.component = n1.component;
    if (shouldUpdateComponent(n1, n2, optimized)) {
      if (instance.asyncDep && !instance.asyncResolved) {
        updateComponentPreRender(instance, n2, optimized);
        return;
      } else {
        instance.next = n2;
        instance.update();
      }
    } else {
      n2.el = n1.el;
      instance.vnode = n2;
    }
  };
  const setupRenderEffect = (instance, initialVNode, container, anchor, parentSuspense, namespace, optimized) => {
    const componentUpdateFn = () => {
      if (!instance.isMounted) {
        let vnodeHook;
        const { el, props } = initialVNode;
        const { bm, m: m2, parent, root, type } = instance;
        const isAsyncWrapperVNode = isAsyncWrapper(initialVNode);
        toggleRecurse(instance, false);
        if (bm) {
          invokeArrayFns(bm);
        }
        if (!isAsyncWrapperVNode && (vnodeHook = props && props.onVnodeBeforeMount)) {
          invokeVNodeHook(vnodeHook, parent, initialVNode);
        }
        toggleRecurse(instance, true);
        {
          if (root.ce && // @ts-expect-error _def is private
          root.ce._def.shadowRoot !== false) {
            root.ce._injectChildStyle(type);
          }
          const subTree = instance.subTree = renderComponentRoot(instance);
          patch(
            null,
            subTree,
            container,
            anchor,
            instance,
            parentSuspense,
            namespace
          );
          initialVNode.el = subTree.el;
        }
        if (m2) {
          queuePostRenderEffect(m2, parentSuspense);
        }
        if (!isAsyncWrapperVNode && (vnodeHook = props && props.onVnodeMounted)) {
          const scopedInitialVNode = initialVNode;
          queuePostRenderEffect(
            () => invokeVNodeHook(vnodeHook, parent, scopedInitialVNode),
            parentSuspense
          );
        }
        if (initialVNode.shapeFlag & 256 || parent && isAsyncWrapper(parent.vnode) && parent.vnode.shapeFlag & 256) {
          instance.a && queuePostRenderEffect(instance.a, parentSuspense);
        }
        instance.isMounted = true;
        initialVNode = container = anchor = null;
      } else {
        let { next, bu, u, parent, vnode } = instance;
        {
          const nonHydratedAsyncRoot = locateNonHydratedAsyncRoot(instance);
          if (nonHydratedAsyncRoot) {
            if (next) {
              next.el = vnode.el;
              updateComponentPreRender(instance, next, optimized);
            }
            nonHydratedAsyncRoot.asyncDep.then(() => {
              if (!instance.isUnmounted) {
                componentUpdateFn();
              }
            });
            return;
          }
        }
        let originNext = next;
        let vnodeHook;
        toggleRecurse(instance, false);
        if (next) {
          next.el = vnode.el;
          updateComponentPreRender(instance, next, optimized);
        } else {
          next = vnode;
        }
        if (bu) {
          invokeArrayFns(bu);
        }
        if (vnodeHook = next.props && next.props.onVnodeBeforeUpdate) {
          invokeVNodeHook(vnodeHook, parent, next, vnode);
        }
        toggleRecurse(instance, true);
        const nextTree = renderComponentRoot(instance);
        const prevTree = instance.subTree;
        instance.subTree = nextTree;
        patch(
          prevTree,
          nextTree,
          // parent may have changed if it's in a teleport
          hostParentNode(prevTree.el),
          // anchor may have changed if it's in a fragment
          getNextHostNode(prevTree),
          instance,
          parentSuspense,
          namespace
        );
        next.el = nextTree.el;
        if (originNext === null) {
          updateHOCHostEl(instance, nextTree.el);
        }
        if (u) {
          queuePostRenderEffect(u, parentSuspense);
        }
        if (vnodeHook = next.props && next.props.onVnodeUpdated) {
          queuePostRenderEffect(
            () => invokeVNodeHook(vnodeHook, parent, next, vnode),
            parentSuspense
          );
        }
      }
    };
    instance.scope.on();
    const effect2 = instance.effect = new ReactiveEffect(componentUpdateFn);
    instance.scope.off();
    const update = instance.update = effect2.run.bind(effect2);
    const job = instance.job = effect2.runIfDirty.bind(effect2);
    job.i = instance;
    job.id = instance.uid;
    effect2.scheduler = () => queueJob(job);
    toggleRecurse(instance, true);
    update();
  };
  const updateComponentPreRender = (instance, nextVNode, optimized) => {
    nextVNode.component = instance;
    const prevProps = instance.vnode.props;
    instance.vnode = nextVNode;
    instance.next = null;
    updateProps(instance, nextVNode.props, prevProps, optimized);
    updateSlots(instance, nextVNode.children, optimized);
    pauseTracking();
    flushPreFlushCbs(instance);
    resetTracking();
  };
  const patchChildren = (n1, n2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized = false) => {
    const c1 = n1 && n1.children;
    const prevShapeFlag = n1 ? n1.shapeFlag : 0;
    const c2 = n2.children;
    const { patchFlag, shapeFlag } = n2;
    if (patchFlag > 0) {
      if (patchFlag & 128) {
        patchKeyedChildren(
          c1,
          c2,
          container,
          anchor,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
        return;
      } else if (patchFlag & 256) {
        patchUnkeyedChildren(
          c1,
          c2,
          container,
          anchor,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
        return;
      }
    }
    if (shapeFlag & 8) {
      if (prevShapeFlag & 16) {
        unmountChildren(c1, parentComponent, parentSuspense);
      }
      if (c2 !== c1) {
        hostSetElementText(container, c2);
      }
    } else {
      if (prevShapeFlag & 16) {
        if (shapeFlag & 16) {
          patchKeyedChildren(
            c1,
            c2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        } else {
          unmountChildren(c1, parentComponent, parentSuspense, true);
        }
      } else {
        if (prevShapeFlag & 8) {
          hostSetElementText(container, "");
        }
        if (shapeFlag & 16) {
          mountChildren(
            c2,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        }
      }
    }
  };
  const patchUnkeyedChildren = (c1, c2, container, anchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    c1 = c1 || EMPTY_ARR;
    c2 = c2 || EMPTY_ARR;
    const oldLength = c1.length;
    const newLength = c2.length;
    const commonLength = Math.min(oldLength, newLength);
    let i2;
    for (i2 = 0; i2 < commonLength; i2++) {
      const nextChild = c2[i2] = optimized ? cloneIfMounted(c2[i2]) : normalizeVNode(c2[i2]);
      patch(
        c1[i2],
        nextChild,
        container,
        null,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        optimized
      );
    }
    if (oldLength > newLength) {
      unmountChildren(
        c1,
        parentComponent,
        parentSuspense,
        true,
        false,
        commonLength
      );
    } else {
      mountChildren(
        c2,
        container,
        anchor,
        parentComponent,
        parentSuspense,
        namespace,
        slotScopeIds,
        optimized,
        commonLength
      );
    }
  };
  const patchKeyedChildren = (c1, c2, container, parentAnchor, parentComponent, parentSuspense, namespace, slotScopeIds, optimized) => {
    let i2 = 0;
    const l2 = c2.length;
    let e1 = c1.length - 1;
    let e2 = l2 - 1;
    while (i2 <= e1 && i2 <= e2) {
      const n1 = c1[i2];
      const n2 = c2[i2] = optimized ? cloneIfMounted(c2[i2]) : normalizeVNode(c2[i2]);
      if (isSameVNodeType(n1, n2)) {
        patch(
          n1,
          n2,
          container,
          null,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
      } else {
        break;
      }
      i2++;
    }
    while (i2 <= e1 && i2 <= e2) {
      const n1 = c1[e1];
      const n2 = c2[e2] = optimized ? cloneIfMounted(c2[e2]) : normalizeVNode(c2[e2]);
      if (isSameVNodeType(n1, n2)) {
        patch(
          n1,
          n2,
          container,
          null,
          parentComponent,
          parentSuspense,
          namespace,
          slotScopeIds,
          optimized
        );
      } else {
        break;
      }
      e1--;
      e2--;
    }
    if (i2 > e1) {
      if (i2 <= e2) {
        const nextPos = e2 + 1;
        const anchor = nextPos < l2 ? c2[nextPos].el : parentAnchor;
        while (i2 <= e2) {
          patch(
            null,
            c2[i2] = optimized ? cloneIfMounted(c2[i2]) : normalizeVNode(c2[i2]),
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
          i2++;
        }
      }
    } else if (i2 > e2) {
      while (i2 <= e1) {
        unmount(c1[i2], parentComponent, parentSuspense, true);
        i2++;
      }
    } else {
      const s1 = i2;
      const s2 = i2;
      const keyToNewIndexMap = /* @__PURE__ */ new Map();
      for (i2 = s2; i2 <= e2; i2++) {
        const nextChild = c2[i2] = optimized ? cloneIfMounted(c2[i2]) : normalizeVNode(c2[i2]);
        if (nextChild.key != null) {
          keyToNewIndexMap.set(nextChild.key, i2);
        }
      }
      let j;
      let patched = 0;
      const toBePatched = e2 - s2 + 1;
      let moved = false;
      let maxNewIndexSoFar = 0;
      const newIndexToOldIndexMap = new Array(toBePatched);
      for (i2 = 0; i2 < toBePatched; i2++) newIndexToOldIndexMap[i2] = 0;
      for (i2 = s1; i2 <= e1; i2++) {
        const prevChild = c1[i2];
        if (patched >= toBePatched) {
          unmount(prevChild, parentComponent, parentSuspense, true);
          continue;
        }
        let newIndex;
        if (prevChild.key != null) {
          newIndex = keyToNewIndexMap.get(prevChild.key);
        } else {
          for (j = s2; j <= e2; j++) {
            if (newIndexToOldIndexMap[j - s2] === 0 && isSameVNodeType(prevChild, c2[j])) {
              newIndex = j;
              break;
            }
          }
        }
        if (newIndex === void 0) {
          unmount(prevChild, parentComponent, parentSuspense, true);
        } else {
          newIndexToOldIndexMap[newIndex - s2] = i2 + 1;
          if (newIndex >= maxNewIndexSoFar) {
            maxNewIndexSoFar = newIndex;
          } else {
            moved = true;
          }
          patch(
            prevChild,
            c2[newIndex],
            container,
            null,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
          patched++;
        }
      }
      const increasingNewIndexSequence = moved ? getSequence(newIndexToOldIndexMap) : EMPTY_ARR;
      j = increasingNewIndexSequence.length - 1;
      for (i2 = toBePatched - 1; i2 >= 0; i2--) {
        const nextIndex = s2 + i2;
        const nextChild = c2[nextIndex];
        const anchorVNode = c2[nextIndex + 1];
        const anchor = nextIndex + 1 < l2 ? (
          // #13559, #14173 fallback to el placeholder for unresolved async component
          anchorVNode.el || resolveAsyncComponentPlaceholder(anchorVNode)
        ) : parentAnchor;
        if (newIndexToOldIndexMap[i2] === 0) {
          patch(
            null,
            nextChild,
            container,
            anchor,
            parentComponent,
            parentSuspense,
            namespace,
            slotScopeIds,
            optimized
          );
        } else if (moved) {
          if (j < 0 || i2 !== increasingNewIndexSequence[j]) {
            move(nextChild, container, anchor, 2);
          } else {
            j--;
          }
        }
      }
    }
  };
  const move = (vnode, container, anchor, moveType, parentSuspense = null) => {
    const { el, type, transition, children, shapeFlag } = vnode;
    if (shapeFlag & 6) {
      move(vnode.component.subTree, container, anchor, moveType);
      return;
    }
    if (shapeFlag & 128) {
      vnode.suspense.move(container, anchor, moveType);
      return;
    }
    if (shapeFlag & 64) {
      type.move(vnode, container, anchor, internals);
      return;
    }
    if (type === Fragment) {
      hostInsert(el, container, anchor);
      for (let i2 = 0; i2 < children.length; i2++) {
        move(children[i2], container, anchor, moveType);
      }
      hostInsert(vnode.anchor, container, anchor);
      return;
    }
    if (type === Static) {
      moveStaticNode(vnode, container, anchor);
      return;
    }
    const needTransition2 = moveType !== 2 && shapeFlag & 1 && transition;
    if (needTransition2) {
      if (moveType === 0) {
        transition.beforeEnter(el);
        hostInsert(el, container, anchor);
        queuePostRenderEffect(() => transition.enter(el), parentSuspense);
      } else {
        const { leave, delayLeave, afterLeave } = transition;
        const remove22 = () => {
          if (vnode.ctx.isUnmounted) {
            hostRemove(el);
          } else {
            hostInsert(el, container, anchor);
          }
        };
        const performLeave = () => {
          if (el._isLeaving) {
            el[leaveCbKey](
              true
              /* cancelled */
            );
          }
          leave(el, () => {
            remove22();
            afterLeave && afterLeave();
          });
        };
        if (delayLeave) {
          delayLeave(el, remove22, performLeave);
        } else {
          performLeave();
        }
      }
    } else {
      hostInsert(el, container, anchor);
    }
  };
  const unmount = (vnode, parentComponent, parentSuspense, doRemove = false, optimized = false) => {
    const {
      type,
      props,
      ref: ref3,
      children,
      dynamicChildren,
      shapeFlag,
      patchFlag,
      dirs,
      cacheIndex
    } = vnode;
    if (patchFlag === -2) {
      optimized = false;
    }
    if (ref3 != null) {
      pauseTracking();
      setRef(ref3, null, parentSuspense, vnode, true);
      resetTracking();
    }
    if (cacheIndex != null) {
      parentComponent.renderCache[cacheIndex] = void 0;
    }
    if (shapeFlag & 256) {
      parentComponent.ctx.deactivate(vnode);
      return;
    }
    const shouldInvokeDirs = shapeFlag & 1 && dirs;
    const shouldInvokeVnodeHook = !isAsyncWrapper(vnode);
    let vnodeHook;
    if (shouldInvokeVnodeHook && (vnodeHook = props && props.onVnodeBeforeUnmount)) {
      invokeVNodeHook(vnodeHook, parentComponent, vnode);
    }
    if (shapeFlag & 6) {
      unmountComponent(vnode.component, parentSuspense, doRemove);
    } else {
      if (shapeFlag & 128) {
        vnode.suspense.unmount(parentSuspense, doRemove);
        return;
      }
      if (shouldInvokeDirs) {
        invokeDirectiveHook(vnode, null, parentComponent, "beforeUnmount");
      }
      if (shapeFlag & 64) {
        vnode.type.remove(
          vnode,
          parentComponent,
          parentSuspense,
          internals,
          doRemove
        );
      } else if (dynamicChildren && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !dynamicChildren.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (type !== Fragment || patchFlag > 0 && patchFlag & 64)) {
        unmountChildren(
          dynamicChildren,
          parentComponent,
          parentSuspense,
          false,
          true
        );
      } else if (type === Fragment && patchFlag & (128 | 256) || !optimized && shapeFlag & 16) {
        unmountChildren(children, parentComponent, parentSuspense);
      }
      if (doRemove) {
        remove2(vnode);
      }
    }
    if (shouldInvokeVnodeHook && (vnodeHook = props && props.onVnodeUnmounted) || shouldInvokeDirs) {
      queuePostRenderEffect(() => {
        vnodeHook && invokeVNodeHook(vnodeHook, parentComponent, vnode);
        shouldInvokeDirs && invokeDirectiveHook(vnode, null, parentComponent, "unmounted");
      }, parentSuspense);
    }
  };
  const remove2 = (vnode) => {
    const { type, el, anchor, transition } = vnode;
    if (type === Fragment) {
      {
        removeFragment(el, anchor);
      }
      return;
    }
    if (type === Static) {
      removeStaticNode(vnode);
      return;
    }
    const performRemove = () => {
      hostRemove(el);
      if (transition && !transition.persisted && transition.afterLeave) {
        transition.afterLeave();
      }
    };
    if (vnode.shapeFlag & 1 && transition && !transition.persisted) {
      const { leave, delayLeave } = transition;
      const performLeave = () => leave(el, performRemove);
      if (delayLeave) {
        delayLeave(vnode.el, performRemove, performLeave);
      } else {
        performLeave();
      }
    } else {
      performRemove();
    }
  };
  const removeFragment = (cur, end) => {
    let next;
    while (cur !== end) {
      next = hostNextSibling(cur);
      hostRemove(cur);
      cur = next;
    }
    hostRemove(end);
  };
  const unmountComponent = (instance, parentSuspense, doRemove) => {
    const { bum, scope, job, subTree, um, m: m2, a: a2 } = instance;
    invalidateMount(m2);
    invalidateMount(a2);
    if (bum) {
      invokeArrayFns(bum);
    }
    scope.stop();
    if (job) {
      job.flags |= 8;
      unmount(subTree, instance, parentSuspense, doRemove);
    }
    if (um) {
      queuePostRenderEffect(um, parentSuspense);
    }
    queuePostRenderEffect(() => {
      instance.isUnmounted = true;
    }, parentSuspense);
  };
  const unmountChildren = (children, parentComponent, parentSuspense, doRemove = false, optimized = false, start = 0) => {
    for (let i2 = start; i2 < children.length; i2++) {
      unmount(children[i2], parentComponent, parentSuspense, doRemove, optimized);
    }
  };
  const getNextHostNode = (vnode) => {
    if (vnode.shapeFlag & 6) {
      return getNextHostNode(vnode.component.subTree);
    }
    if (vnode.shapeFlag & 128) {
      return vnode.suspense.next();
    }
    const el = hostNextSibling(vnode.anchor || vnode.el);
    const teleportEnd = el && el[TeleportEndKey];
    return teleportEnd ? hostNextSibling(teleportEnd) : el;
  };
  let isFlushing = false;
  const render = (vnode, container, namespace) => {
    let instance;
    if (vnode == null) {
      if (container._vnode) {
        unmount(container._vnode, null, null, true);
        instance = container._vnode.component;
      }
    } else {
      patch(
        container._vnode || null,
        vnode,
        container,
        null,
        null,
        null,
        namespace
      );
    }
    container._vnode = vnode;
    if (!isFlushing) {
      isFlushing = true;
      flushPreFlushCbs(instance);
      flushPostFlushCbs();
      isFlushing = false;
    }
  };
  const internals = {
    p: patch,
    um: unmount,
    m: move,
    r: remove2,
    mt: mountComponent,
    mc: mountChildren,
    pc: patchChildren,
    pbc: patchBlockChildren,
    n: getNextHostNode,
    o: options
  };
  let hydrate;
  return {
    render,
    hydrate,
    createApp: createAppAPI(render)
  };
}
function resolveChildrenNamespace({ type, props }, currentNamespace) {
  return currentNamespace === "svg" && type === "foreignObject" || currentNamespace === "mathml" && type === "annotation-xml" && props && props.encoding && props.encoding.includes("html") ? void 0 : currentNamespace;
}
function toggleRecurse({ effect: effect2, job }, allowed) {
  if (allowed) {
    effect2.flags |= 32;
    job.flags |= 4;
  } else {
    effect2.flags &= -33;
    job.flags &= -5;
  }
}
function needTransition(parentSuspense, transition) {
  return (!parentSuspense || parentSuspense && !parentSuspense.pendingBranch) && transition && !transition.persisted;
}
function traverseStaticChildren(n1, n2, shallow = false) {
  const ch1 = n1.children;
  const ch2 = n2.children;
  if (isArray(ch1) && isArray(ch2)) {
    for (let i2 = 0; i2 < ch1.length; i2++) {
      const c1 = ch1[i2];
      let c2 = ch2[i2];
      if (c2.shapeFlag & 1 && !c2.dynamicChildren) {
        if (c2.patchFlag <= 0 || c2.patchFlag === 32) {
          c2 = ch2[i2] = cloneIfMounted(ch2[i2]);
          c2.el = c1.el;
        }
        if (!shallow && c2.patchFlag !== -2)
          traverseStaticChildren(c1, c2);
      }
      if (c2.type === Text) {
        if (c2.patchFlag !== -1) {
          c2.el = c1.el;
        } else {
          c2.__elIndex = i2 + // take fragment start anchor into account
          (n1.type === Fragment ? 1 : 0);
        }
      }
      if (c2.type === Comment && !c2.el) {
        c2.el = c1.el;
      }
    }
  }
}
function getSequence(arr) {
  const p2 = arr.slice();
  const result = [0];
  let i2, j, u, v2, c2;
  const len = arr.length;
  for (i2 = 0; i2 < len; i2++) {
    const arrI = arr[i2];
    if (arrI !== 0) {
      j = result[result.length - 1];
      if (arr[j] < arrI) {
        p2[i2] = j;
        result.push(i2);
        continue;
      }
      u = 0;
      v2 = result.length - 1;
      while (u < v2) {
        c2 = u + v2 >> 1;
        if (arr[result[c2]] < arrI) {
          u = c2 + 1;
        } else {
          v2 = c2;
        }
      }
      if (arrI < arr[result[u]]) {
        if (u > 0) {
          p2[i2] = result[u - 1];
        }
        result[u] = i2;
      }
    }
  }
  u = result.length;
  v2 = result[u - 1];
  while (u-- > 0) {
    result[u] = v2;
    v2 = p2[v2];
  }
  return result;
}
function locateNonHydratedAsyncRoot(instance) {
  const subComponent = instance.subTree.component;
  if (subComponent) {
    if (subComponent.asyncDep && !subComponent.asyncResolved) {
      return subComponent;
    } else {
      return locateNonHydratedAsyncRoot(subComponent);
    }
  }
}
function invalidateMount(hooks) {
  if (hooks) {
    for (let i2 = 0; i2 < hooks.length; i2++)
      hooks[i2].flags |= 8;
  }
}
function resolveAsyncComponentPlaceholder(anchorVnode) {
  if (anchorVnode.placeholder) {
    return anchorVnode.placeholder;
  }
  const instance = anchorVnode.component;
  if (instance) {
    return resolveAsyncComponentPlaceholder(instance.subTree);
  }
  return null;
}
const isSuspense = (type) => type.__isSuspense;
function queueEffectWithSuspense(fn, suspense) {
  if (suspense && suspense.pendingBranch) {
    if (isArray(fn)) {
      suspense.effects.push(...fn);
    } else {
      suspense.effects.push(fn);
    }
  } else {
    queuePostFlushCb(fn);
  }
}
const Fragment = /* @__PURE__ */ Symbol.for("v-fgt");
const Text = /* @__PURE__ */ Symbol.for("v-txt");
const Comment = /* @__PURE__ */ Symbol.for("v-cmt");
const Static = /* @__PURE__ */ Symbol.for("v-stc");
const blockStack = [];
let currentBlock = null;
function openBlock(disableTracking = false) {
  blockStack.push(currentBlock = disableTracking ? null : []);
}
function closeBlock() {
  blockStack.pop();
  currentBlock = blockStack[blockStack.length - 1] || null;
}
let isBlockTreeEnabled = 1;
function setBlockTracking(value, inVOnce = false) {
  isBlockTreeEnabled += value;
  if (value < 0 && currentBlock && inVOnce) {
    currentBlock.hasOnce = true;
  }
}
function setupBlock(vnode) {
  vnode.dynamicChildren = isBlockTreeEnabled > 0 ? currentBlock || EMPTY_ARR : null;
  closeBlock();
  if (isBlockTreeEnabled > 0 && currentBlock) {
    currentBlock.push(vnode);
  }
  return vnode;
}
function createElementBlock(type, props, children, patchFlag, dynamicProps, shapeFlag) {
  return setupBlock(
    createBaseVNode(
      type,
      props,
      children,
      patchFlag,
      dynamicProps,
      shapeFlag,
      true
    )
  );
}
function createBlock(type, props, children, patchFlag, dynamicProps) {
  return setupBlock(
    createVNode(
      type,
      props,
      children,
      patchFlag,
      dynamicProps,
      true
    )
  );
}
function isVNode(value) {
  return value ? value.__v_isVNode === true : false;
}
function isSameVNodeType(n1, n2) {
  return n1.type === n2.type && n1.key === n2.key;
}
const normalizeKey = ({ key }) => key != null ? key : null;
const normalizeRef = ({
  ref: ref3,
  ref_key,
  ref_for
}) => {
  if (typeof ref3 === "number") {
    ref3 = "" + ref3;
  }
  return ref3 != null ? isString(ref3) || isRef(ref3) || isFunction(ref3) ? { i: currentRenderingInstance, r: ref3, k: ref_key, f: !!ref_for } : ref3 : null;
};
function createBaseVNode(type, props = null, children = null, patchFlag = 0, dynamicProps = null, shapeFlag = type === Fragment ? 0 : 1, isBlockNode = false, needFullChildrenNormalization = false) {
  const vnode = {
    __v_isVNode: true,
    __v_skip: true,
    type,
    props,
    key: props && normalizeKey(props),
    ref: props && normalizeRef(props),
    scopeId: currentScopeId,
    slotScopeIds: null,
    children,
    component: null,
    suspense: null,
    ssContent: null,
    ssFallback: null,
    dirs: null,
    transition: null,
    el: null,
    anchor: null,
    target: null,
    targetStart: null,
    targetAnchor: null,
    staticCount: 0,
    shapeFlag,
    patchFlag,
    dynamicProps,
    dynamicChildren: null,
    appContext: null,
    ctx: currentRenderingInstance
  };
  if (needFullChildrenNormalization) {
    normalizeChildren(vnode, children);
    if (shapeFlag & 128) {
      type.normalize(vnode);
    }
  } else if (children) {
    vnode.shapeFlag |= isString(children) ? 8 : 16;
  }
  if (isBlockTreeEnabled > 0 && // avoid a block node from tracking itself
  !isBlockNode && // has current parent block
  currentBlock && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (vnode.patchFlag > 0 || shapeFlag & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  vnode.patchFlag !== 32) {
    currentBlock.push(vnode);
  }
  return vnode;
}
const createVNode = _createVNode;
function _createVNode(type, props = null, children = null, patchFlag = 0, dynamicProps = null, isBlockNode = false) {
  if (!type || type === NULL_DYNAMIC_COMPONENT) {
    type = Comment;
  }
  if (isVNode(type)) {
    const cloned = cloneVNode(
      type,
      props,
      true
      /* mergeRef: true */
    );
    if (children) {
      normalizeChildren(cloned, children);
    }
    if (isBlockTreeEnabled > 0 && !isBlockNode && currentBlock) {
      if (cloned.shapeFlag & 6) {
        currentBlock[currentBlock.indexOf(type)] = cloned;
      } else {
        currentBlock.push(cloned);
      }
    }
    cloned.patchFlag = -2;
    return cloned;
  }
  if (isClassComponent(type)) {
    type = type.__vccOpts;
  }
  if (props) {
    props = guardReactiveProps(props);
    let { class: klass, style: style2 } = props;
    if (klass && !isString(klass)) {
      props.class = normalizeClass(klass);
    }
    if (isObject(style2)) {
      if (isProxy(style2) && !isArray(style2)) {
        style2 = extend({}, style2);
      }
      props.style = normalizeStyle(style2);
    }
  }
  const shapeFlag = isString(type) ? 1 : isSuspense(type) ? 128 : isTeleport(type) ? 64 : isObject(type) ? 4 : isFunction(type) ? 2 : 0;
  return createBaseVNode(
    type,
    props,
    children,
    patchFlag,
    dynamicProps,
    shapeFlag,
    isBlockNode,
    true
  );
}
function guardReactiveProps(props) {
  if (!props) return null;
  return isProxy(props) || isInternalObject(props) ? extend({}, props) : props;
}
function cloneVNode(vnode, extraProps, mergeRef = false, cloneTransition = false) {
  const { props, ref: ref3, patchFlag, children, transition } = vnode;
  const mergedProps = extraProps ? mergeProps(props || {}, extraProps) : props;
  const cloned = {
    __v_isVNode: true,
    __v_skip: true,
    type: vnode.type,
    props: mergedProps,
    key: mergedProps && normalizeKey(mergedProps),
    ref: extraProps && extraProps.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      mergeRef && ref3 ? isArray(ref3) ? ref3.concat(normalizeRef(extraProps)) : [ref3, normalizeRef(extraProps)] : normalizeRef(extraProps)
    ) : ref3,
    scopeId: vnode.scopeId,
    slotScopeIds: vnode.slotScopeIds,
    children,
    target: vnode.target,
    targetStart: vnode.targetStart,
    targetAnchor: vnode.targetAnchor,
    staticCount: vnode.staticCount,
    shapeFlag: vnode.shapeFlag,
    // if the vnode is cloned with extra props, we can no longer assume its
    // existing patch flag to be reliable and need to add the FULL_PROPS flag.
    // note: preserve flag for fragments since they use the flag for children
    // fast paths only.
    patchFlag: extraProps && vnode.type !== Fragment ? patchFlag === -1 ? 16 : patchFlag | 16 : patchFlag,
    dynamicProps: vnode.dynamicProps,
    dynamicChildren: vnode.dynamicChildren,
    appContext: vnode.appContext,
    dirs: vnode.dirs,
    transition,
    // These should technically only be non-null on mounted VNodes. However,
    // they *should* be copied for kept-alive vnodes. So we just always copy
    // them since them being non-null during a mount doesn't affect the logic as
    // they will simply be overwritten.
    component: vnode.component,
    suspense: vnode.suspense,
    ssContent: vnode.ssContent && cloneVNode(vnode.ssContent),
    ssFallback: vnode.ssFallback && cloneVNode(vnode.ssFallback),
    placeholder: vnode.placeholder,
    el: vnode.el,
    anchor: vnode.anchor,
    ctx: vnode.ctx,
    ce: vnode.ce
  };
  if (transition && cloneTransition) {
    setTransitionHooks(
      cloned,
      transition.clone(cloned)
    );
  }
  return cloned;
}
function createTextVNode(text = " ", flag = 0) {
  return createVNode(Text, null, text, flag);
}
function createStaticVNode(content, numberOfNodes) {
  const vnode = createVNode(Static, null, content);
  vnode.staticCount = numberOfNodes;
  return vnode;
}
function createCommentVNode(text = "", asBlock = false) {
  return asBlock ? (openBlock(), createBlock(Comment, null, text)) : createVNode(Comment, null, text);
}
function normalizeVNode(child) {
  if (child == null || typeof child === "boolean") {
    return createVNode(Comment);
  } else if (isArray(child)) {
    return createVNode(
      Fragment,
      null,
      // #3666, avoid reference pollution when reusing vnode
      child.slice()
    );
  } else if (isVNode(child)) {
    return cloneIfMounted(child);
  } else {
    return createVNode(Text, null, String(child));
  }
}
function cloneIfMounted(child) {
  return child.el === null && child.patchFlag !== -1 || child.memo ? child : cloneVNode(child);
}
function normalizeChildren(vnode, children) {
  let type = 0;
  const { shapeFlag } = vnode;
  if (children == null) {
    children = null;
  } else if (isArray(children)) {
    type = 16;
  } else if (typeof children === "object") {
    if (shapeFlag & (1 | 64)) {
      const slot = children.default;
      if (slot) {
        slot._c && (slot._d = false);
        normalizeChildren(vnode, slot());
        slot._c && (slot._d = true);
      }
      return;
    } else {
      type = 32;
      const slotFlag = children._;
      if (!slotFlag && !isInternalObject(children)) {
        children._ctx = currentRenderingInstance;
      } else if (slotFlag === 3 && currentRenderingInstance) {
        if (currentRenderingInstance.slots._ === 1) {
          children._ = 1;
        } else {
          children._ = 2;
          vnode.patchFlag |= 1024;
        }
      }
    }
  } else if (isFunction(children)) {
    children = { default: children, _ctx: currentRenderingInstance };
    type = 32;
  } else {
    children = String(children);
    if (shapeFlag & 64) {
      type = 16;
      children = [createTextVNode(children)];
    } else {
      type = 8;
    }
  }
  vnode.children = children;
  vnode.shapeFlag |= type;
}
function mergeProps(...args) {
  const ret = {};
  for (let i2 = 0; i2 < args.length; i2++) {
    const toMerge = args[i2];
    for (const key in toMerge) {
      if (key === "class") {
        if (ret.class !== toMerge.class) {
          ret.class = normalizeClass([ret.class, toMerge.class]);
        }
      } else if (key === "style") {
        ret.style = normalizeStyle([ret.style, toMerge.style]);
      } else if (isOn(key)) {
        const existing = ret[key];
        const incoming = toMerge[key];
        if (incoming && existing !== incoming && !(isArray(existing) && existing.includes(incoming))) {
          ret[key] = existing ? [].concat(existing, incoming) : incoming;
        }
      } else if (key !== "") {
        ret[key] = toMerge[key];
      }
    }
  }
  return ret;
}
function invokeVNodeHook(hook, instance, vnode, prevVNode = null) {
  callWithAsyncErrorHandling(hook, instance, 7, [
    vnode,
    prevVNode
  ]);
}
const emptyAppContext = createAppContext();
let uid = 0;
function createComponentInstance(vnode, parent, suspense) {
  const type = vnode.type;
  const appContext = (parent ? parent.appContext : vnode.appContext) || emptyAppContext;
  const instance = {
    uid: uid++,
    vnode,
    type,
    parent,
    appContext,
    root: null,
    // to be immediately set
    next: null,
    subTree: null,
    // will be set synchronously right after creation
    effect: null,
    update: null,
    // will be set synchronously right after creation
    job: null,
    scope: new EffectScope(
      true
      /* detached */
    ),
    render: null,
    proxy: null,
    exposed: null,
    exposeProxy: null,
    withProxy: null,
    provides: parent ? parent.provides : Object.create(appContext.provides),
    ids: parent ? parent.ids : ["", 0, 0],
    accessCache: null,
    renderCache: [],
    // local resolved assets
    components: null,
    directives: null,
    // resolved props and emits options
    propsOptions: normalizePropsOptions(type, appContext),
    emitsOptions: normalizeEmitsOptions(type, appContext),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: EMPTY_OBJ,
    // inheritAttrs
    inheritAttrs: type.inheritAttrs,
    // state
    ctx: EMPTY_OBJ,
    data: EMPTY_OBJ,
    props: EMPTY_OBJ,
    attrs: EMPTY_OBJ,
    slots: EMPTY_OBJ,
    refs: EMPTY_OBJ,
    setupState: EMPTY_OBJ,
    setupContext: null,
    // suspense related
    suspense,
    suspenseId: suspense ? suspense.pendingId : 0,
    asyncDep: null,
    asyncResolved: false,
    // lifecycle hooks
    // not using enums here because it results in computed properties
    isMounted: false,
    isUnmounted: false,
    isDeactivated: false,
    bc: null,
    c: null,
    bm: null,
    m: null,
    bu: null,
    u: null,
    um: null,
    bum: null,
    da: null,
    a: null,
    rtg: null,
    rtc: null,
    ec: null,
    sp: null
  };
  {
    instance.ctx = { _: instance };
  }
  instance.root = parent ? parent.root : instance;
  instance.emit = emit.bind(null, instance);
  if (vnode.ce) {
    vnode.ce(instance);
  }
  return instance;
}
let currentInstance = null;
const getCurrentInstance = () => currentInstance || currentRenderingInstance;
let internalSetCurrentInstance;
let setInSSRSetupState;
{
  const g = getGlobalThis();
  const registerGlobalSetter = (key, setter) => {
    let setters;
    if (!(setters = g[key])) setters = g[key] = [];
    setters.push(setter);
    return (v2) => {
      if (setters.length > 1) setters.forEach((set) => set(v2));
      else setters[0](v2);
    };
  };
  internalSetCurrentInstance = registerGlobalSetter(
    `__VUE_INSTANCE_SETTERS__`,
    (v2) => currentInstance = v2
  );
  setInSSRSetupState = registerGlobalSetter(
    `__VUE_SSR_SETTERS__`,
    (v2) => isInSSRComponentSetup = v2
  );
}
const setCurrentInstance = (instance) => {
  const prev = currentInstance;
  internalSetCurrentInstance(instance);
  instance.scope.on();
  return () => {
    instance.scope.off();
    internalSetCurrentInstance(prev);
  };
};
const unsetCurrentInstance = () => {
  currentInstance && currentInstance.scope.off();
  internalSetCurrentInstance(null);
};
function isStatefulComponent(instance) {
  return instance.vnode.shapeFlag & 4;
}
let isInSSRComponentSetup = false;
function setupComponent(instance, isSSR = false, optimized = false) {
  isSSR && setInSSRSetupState(isSSR);
  const { props, children } = instance.vnode;
  const isStateful = isStatefulComponent(instance);
  initProps(instance, props, isStateful, isSSR);
  initSlots(instance, children, optimized || isSSR);
  const setupResult = isStateful ? setupStatefulComponent(instance, isSSR) : void 0;
  isSSR && setInSSRSetupState(false);
  return setupResult;
}
function setupStatefulComponent(instance, isSSR) {
  const Component = instance.type;
  instance.accessCache = /* @__PURE__ */ Object.create(null);
  instance.proxy = new Proxy(instance.ctx, PublicInstanceProxyHandlers);
  const { setup: setup2 } = Component;
  if (setup2) {
    pauseTracking();
    const setupContext = instance.setupContext = setup2.length > 1 ? createSetupContext(instance) : null;
    const reset = setCurrentInstance(instance);
    const setupResult = callWithErrorHandling(
      setup2,
      instance,
      0,
      [
        instance.props,
        setupContext
      ]
    );
    const isAsyncSetup = isPromise(setupResult);
    resetTracking();
    reset();
    if ((isAsyncSetup || instance.sp) && !isAsyncWrapper(instance)) {
      markAsyncBoundary(instance);
    }
    if (isAsyncSetup) {
      setupResult.then(unsetCurrentInstance, unsetCurrentInstance);
      if (isSSR) {
        return setupResult.then((resolvedResult) => {
          handleSetupResult(instance, resolvedResult);
        }).catch((e) => {
          handleError(e, instance, 0);
        });
      } else {
        instance.asyncDep = setupResult;
      }
    } else {
      handleSetupResult(instance, setupResult);
    }
  } else {
    finishComponentSetup(instance);
  }
}
function handleSetupResult(instance, setupResult, isSSR) {
  if (isFunction(setupResult)) {
    if (instance.type.__ssrInlineRender) {
      instance.ssrRender = setupResult;
    } else {
      instance.render = setupResult;
    }
  } else if (isObject(setupResult)) {
    instance.setupState = proxyRefs(setupResult);
  } else ;
  finishComponentSetup(instance);
}
function finishComponentSetup(instance, isSSR, skipOptions) {
  const Component = instance.type;
  if (!instance.render) {
    instance.render = Component.render || NOOP;
  }
  {
    const reset = setCurrentInstance(instance);
    pauseTracking();
    try {
      applyOptions(instance);
    } finally {
      resetTracking();
      reset();
    }
  }
}
const attrsProxyHandlers = {
  get(target, key) {
    track(target, "get", "");
    return target[key];
  }
};
function createSetupContext(instance) {
  const expose = (exposed) => {
    instance.exposed = exposed || {};
  };
  {
    return {
      attrs: new Proxy(instance.attrs, attrsProxyHandlers),
      slots: instance.slots,
      emit: instance.emit,
      expose
    };
  }
}
function getComponentPublicInstance(instance) {
  if (instance.exposed) {
    return instance.exposeProxy || (instance.exposeProxy = new Proxy(proxyRefs(markRaw(instance.exposed)), {
      get(target, key) {
        if (key in target) {
          return target[key];
        } else if (key in publicPropertiesMap) {
          return publicPropertiesMap[key](instance);
        }
      },
      has(target, key) {
        return key in target || key in publicPropertiesMap;
      }
    }));
  } else {
    return instance.proxy;
  }
}
const classifyRE = /(?:^|[-_])\w/g;
const classify = (str) => str.replace(classifyRE, (c2) => c2.toUpperCase()).replace(/[-_]/g, "");
function getComponentName(Component, includeInferred = true) {
  return isFunction(Component) ? Component.displayName || Component.name : Component.name || includeInferred && Component.__name;
}
function formatComponentName(instance, Component, isRoot = false) {
  let name = getComponentName(Component);
  if (!name && Component.__file) {
    const match = Component.__file.match(/([^/\\]+)\.\w+$/);
    if (match) {
      name = match[1];
    }
  }
  if (!name && instance) {
    const inferFromRegistry = (registry) => {
      for (const key in registry) {
        if (registry[key] === Component) {
          return key;
        }
      }
    };
    name = inferFromRegistry(instance.components) || instance.parent && inferFromRegistry(
      instance.parent.type.components
    ) || inferFromRegistry(instance.appContext.components);
  }
  return name ? classify(name) : isRoot ? `App` : `Anonymous`;
}
function isClassComponent(value) {
  return isFunction(value) && "__vccOpts" in value;
}
const computed = (getterOrOptions, debugOptions) => {
  const c2 = computed$1(getterOrOptions, debugOptions, isInSSRComponentSetup);
  return c2;
};
function h$1(type, propsOrChildren, children) {
  try {
    setBlockTracking(-1);
    const l2 = arguments.length;
    if (l2 === 2) {
      if (isObject(propsOrChildren) && !isArray(propsOrChildren)) {
        if (isVNode(propsOrChildren)) {
          return createVNode(type, null, [propsOrChildren]);
        }
        return createVNode(type, propsOrChildren);
      } else {
        return createVNode(type, null, propsOrChildren);
      }
    } else {
      if (l2 > 3) {
        children = Array.prototype.slice.call(arguments, 2);
      } else if (l2 === 3 && isVNode(children)) {
        children = [children];
      }
      return createVNode(type, propsOrChildren, children);
    }
  } finally {
    setBlockTracking(1);
  }
}
const version = "3.5.26";
/**
* @vue/runtime-dom v3.5.26
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let policy = void 0;
const tt$1 = typeof window !== "undefined" && window.trustedTypes;
if (tt$1) {
  try {
    policy = /* @__PURE__ */ tt$1.createPolicy("vue", {
      createHTML: (val) => val
    });
  } catch (e) {
  }
}
const unsafeToTrustedHTML = policy ? (val) => policy.createHTML(val) : (val) => val;
const svgNS = "http://www.w3.org/2000/svg";
const mathmlNS = "http://www.w3.org/1998/Math/MathML";
const doc = typeof document !== "undefined" ? document : null;
const templateContainer = doc && /* @__PURE__ */ doc.createElement("template");
const nodeOps = {
  insert: (child, parent, anchor) => {
    parent.insertBefore(child, anchor || null);
  },
  remove: (child) => {
    const parent = child.parentNode;
    if (parent) {
      parent.removeChild(child);
    }
  },
  createElement: (tag, namespace, is, props) => {
    const el = namespace === "svg" ? doc.createElementNS(svgNS, tag) : namespace === "mathml" ? doc.createElementNS(mathmlNS, tag) : is ? doc.createElement(tag, { is }) : doc.createElement(tag);
    if (tag === "select" && props && props.multiple != null) {
      el.setAttribute("multiple", props.multiple);
    }
    return el;
  },
  createText: (text) => doc.createTextNode(text),
  createComment: (text) => doc.createComment(text),
  setText: (node, text) => {
    node.nodeValue = text;
  },
  setElementText: (el, text) => {
    el.textContent = text;
  },
  parentNode: (node) => node.parentNode,
  nextSibling: (node) => node.nextSibling,
  querySelector: (selector) => doc.querySelector(selector),
  setScopeId(el, id) {
    el.setAttribute(id, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(content, parent, anchor, namespace, start, end) {
    const before = anchor ? anchor.previousSibling : parent.lastChild;
    if (start && (start === end || start.nextSibling)) {
      while (true) {
        parent.insertBefore(start.cloneNode(true), anchor);
        if (start === end || !(start = start.nextSibling)) break;
      }
    } else {
      templateContainer.innerHTML = unsafeToTrustedHTML(
        namespace === "svg" ? `<svg>${content}</svg>` : namespace === "mathml" ? `<math>${content}</math>` : content
      );
      const template = templateContainer.content;
      if (namespace === "svg" || namespace === "mathml") {
        const wrapper = template.firstChild;
        while (wrapper.firstChild) {
          template.appendChild(wrapper.firstChild);
        }
        template.removeChild(wrapper);
      }
      parent.insertBefore(template, anchor);
    }
    return [
      // first
      before ? before.nextSibling : parent.firstChild,
      // last
      anchor ? anchor.previousSibling : parent.lastChild
    ];
  }
};
const TRANSITION = "transition";
const ANIMATION = "animation";
const vtcKey = /* @__PURE__ */ Symbol("_vtc");
const DOMTransitionPropsValidators = {
  name: String,
  type: String,
  css: {
    type: Boolean,
    default: true
  },
  duration: [String, Number, Object],
  enterFromClass: String,
  enterActiveClass: String,
  enterToClass: String,
  appearFromClass: String,
  appearActiveClass: String,
  appearToClass: String,
  leaveFromClass: String,
  leaveActiveClass: String,
  leaveToClass: String
};
const TransitionPropsValidators = /* @__PURE__ */ extend(
  {},
  BaseTransitionPropsValidators,
  DOMTransitionPropsValidators
);
const decorate$1 = (t) => {
  t.displayName = "Transition";
  t.props = TransitionPropsValidators;
  return t;
};
const Transition = /* @__PURE__ */ decorate$1(
  (props, { slots }) => h$1(BaseTransition, resolveTransitionProps(props), slots)
);
const callHook = (hook, args = []) => {
  if (isArray(hook)) {
    hook.forEach((h2) => h2(...args));
  } else if (hook) {
    hook(...args);
  }
};
const hasExplicitCallback = (hook) => {
  return hook ? isArray(hook) ? hook.some((h2) => h2.length > 1) : hook.length > 1 : false;
};
function resolveTransitionProps(rawProps) {
  const baseProps = {};
  for (const key in rawProps) {
    if (!(key in DOMTransitionPropsValidators)) {
      baseProps[key] = rawProps[key];
    }
  }
  if (rawProps.css === false) {
    return baseProps;
  }
  const {
    name = "v",
    type,
    duration,
    enterFromClass = `${name}-enter-from`,
    enterActiveClass = `${name}-enter-active`,
    enterToClass = `${name}-enter-to`,
    appearFromClass = enterFromClass,
    appearActiveClass = enterActiveClass,
    appearToClass = enterToClass,
    leaveFromClass = `${name}-leave-from`,
    leaveActiveClass = `${name}-leave-active`,
    leaveToClass = `${name}-leave-to`
  } = rawProps;
  const durations = normalizeDuration(duration);
  const enterDuration = durations && durations[0];
  const leaveDuration = durations && durations[1];
  const {
    onBeforeEnter,
    onEnter,
    onEnterCancelled,
    onLeave,
    onLeaveCancelled,
    onBeforeAppear = onBeforeEnter,
    onAppear = onEnter,
    onAppearCancelled = onEnterCancelled
  } = baseProps;
  const finishEnter = (el, isAppear, done, isCancelled) => {
    el._enterCancelled = isCancelled;
    removeTransitionClass(el, isAppear ? appearToClass : enterToClass);
    removeTransitionClass(el, isAppear ? appearActiveClass : enterActiveClass);
    done && done();
  };
  const finishLeave = (el, done) => {
    el._isLeaving = false;
    removeTransitionClass(el, leaveFromClass);
    removeTransitionClass(el, leaveToClass);
    removeTransitionClass(el, leaveActiveClass);
    done && done();
  };
  const makeEnterHook = (isAppear) => {
    return (el, done) => {
      const hook = isAppear ? onAppear : onEnter;
      const resolve2 = () => finishEnter(el, isAppear, done);
      callHook(hook, [el, resolve2]);
      nextFrame(() => {
        removeTransitionClass(el, isAppear ? appearFromClass : enterFromClass);
        addTransitionClass(el, isAppear ? appearToClass : enterToClass);
        if (!hasExplicitCallback(hook)) {
          whenTransitionEnds(el, type, enterDuration, resolve2);
        }
      });
    };
  };
  return extend(baseProps, {
    onBeforeEnter(el) {
      callHook(onBeforeEnter, [el]);
      addTransitionClass(el, enterFromClass);
      addTransitionClass(el, enterActiveClass);
    },
    onBeforeAppear(el) {
      callHook(onBeforeAppear, [el]);
      addTransitionClass(el, appearFromClass);
      addTransitionClass(el, appearActiveClass);
    },
    onEnter: makeEnterHook(false),
    onAppear: makeEnterHook(true),
    onLeave(el, done) {
      el._isLeaving = true;
      const resolve2 = () => finishLeave(el, done);
      addTransitionClass(el, leaveFromClass);
      if (!el._enterCancelled) {
        forceReflow(el);
        addTransitionClass(el, leaveActiveClass);
      } else {
        addTransitionClass(el, leaveActiveClass);
        forceReflow(el);
      }
      nextFrame(() => {
        if (!el._isLeaving) {
          return;
        }
        removeTransitionClass(el, leaveFromClass);
        addTransitionClass(el, leaveToClass);
        if (!hasExplicitCallback(onLeave)) {
          whenTransitionEnds(el, type, leaveDuration, resolve2);
        }
      });
      callHook(onLeave, [el, resolve2]);
    },
    onEnterCancelled(el) {
      finishEnter(el, false, void 0, true);
      callHook(onEnterCancelled, [el]);
    },
    onAppearCancelled(el) {
      finishEnter(el, true, void 0, true);
      callHook(onAppearCancelled, [el]);
    },
    onLeaveCancelled(el) {
      finishLeave(el);
      callHook(onLeaveCancelled, [el]);
    }
  });
}
function normalizeDuration(duration) {
  if (duration == null) {
    return null;
  } else if (isObject(duration)) {
    return [NumberOf(duration.enter), NumberOf(duration.leave)];
  } else {
    const n = NumberOf(duration);
    return [n, n];
  }
}
function NumberOf(val) {
  const res = toNumber(val);
  return res;
}
function addTransitionClass(el, cls) {
  cls.split(/\s+/).forEach((c2) => c2 && el.classList.add(c2));
  (el[vtcKey] || (el[vtcKey] = /* @__PURE__ */ new Set())).add(cls);
}
function removeTransitionClass(el, cls) {
  cls.split(/\s+/).forEach((c2) => c2 && el.classList.remove(c2));
  const _vtc = el[vtcKey];
  if (_vtc) {
    _vtc.delete(cls);
    if (!_vtc.size) {
      el[vtcKey] = void 0;
    }
  }
}
function nextFrame(cb) {
  requestAnimationFrame(() => {
    requestAnimationFrame(cb);
  });
}
let endId = 0;
function whenTransitionEnds(el, expectedType, explicitTimeout, resolve2) {
  const id = el._endId = ++endId;
  const resolveIfNotStale = () => {
    if (id === el._endId) {
      resolve2();
    }
  };
  if (explicitTimeout != null) {
    return setTimeout(resolveIfNotStale, explicitTimeout);
  }
  const { type, timeout, propCount } = getTransitionInfo(el, expectedType);
  if (!type) {
    return resolve2();
  }
  const endEvent = type + "end";
  let ended = 0;
  const end = () => {
    el.removeEventListener(endEvent, onEnd);
    resolveIfNotStale();
  };
  const onEnd = (e) => {
    if (e.target === el && ++ended >= propCount) {
      end();
    }
  };
  setTimeout(() => {
    if (ended < propCount) {
      end();
    }
  }, timeout + 1);
  el.addEventListener(endEvent, onEnd);
}
function getTransitionInfo(el, expectedType) {
  const styles = window.getComputedStyle(el);
  const getStyleProperties = (key) => (styles[key] || "").split(", ");
  const transitionDelays = getStyleProperties(`${TRANSITION}Delay`);
  const transitionDurations = getStyleProperties(`${TRANSITION}Duration`);
  const transitionTimeout = getTimeout(transitionDelays, transitionDurations);
  const animationDelays = getStyleProperties(`${ANIMATION}Delay`);
  const animationDurations = getStyleProperties(`${ANIMATION}Duration`);
  const animationTimeout = getTimeout(animationDelays, animationDurations);
  let type = null;
  let timeout = 0;
  let propCount = 0;
  if (expectedType === TRANSITION) {
    if (transitionTimeout > 0) {
      type = TRANSITION;
      timeout = transitionTimeout;
      propCount = transitionDurations.length;
    }
  } else if (expectedType === ANIMATION) {
    if (animationTimeout > 0) {
      type = ANIMATION;
      timeout = animationTimeout;
      propCount = animationDurations.length;
    }
  } else {
    timeout = Math.max(transitionTimeout, animationTimeout);
    type = timeout > 0 ? transitionTimeout > animationTimeout ? TRANSITION : ANIMATION : null;
    propCount = type ? type === TRANSITION ? transitionDurations.length : animationDurations.length : 0;
  }
  const hasTransform = type === TRANSITION && /\b(?:transform|all)(?:,|$)/.test(
    getStyleProperties(`${TRANSITION}Property`).toString()
  );
  return {
    type,
    timeout,
    propCount,
    hasTransform
  };
}
function getTimeout(delays, durations) {
  while (delays.length < durations.length) {
    delays = delays.concat(delays);
  }
  return Math.max(...durations.map((d2, i2) => toMs(d2) + toMs(delays[i2])));
}
function toMs(s2) {
  if (s2 === "auto") return 0;
  return Number(s2.slice(0, -1).replace(",", ".")) * 1e3;
}
function forceReflow(el) {
  const targetDocument = el ? el.ownerDocument : document;
  return targetDocument.body.offsetHeight;
}
function patchClass(el, value, isSVG) {
  const transitionClasses = el[vtcKey];
  if (transitionClasses) {
    value = (value ? [value, ...transitionClasses] : [...transitionClasses]).join(" ");
  }
  if (value == null) {
    el.removeAttribute("class");
  } else if (isSVG) {
    el.setAttribute("class", value);
  } else {
    el.className = value;
  }
}
const vShowOriginalDisplay = /* @__PURE__ */ Symbol("_vod");
const vShowHidden = /* @__PURE__ */ Symbol("_vsh");
const CSS_VAR_TEXT = /* @__PURE__ */ Symbol("");
const displayRE = /(?:^|;)\s*display\s*:/;
function patchStyle(el, prev, next) {
  const style2 = el.style;
  const isCssString = isString(next);
  let hasControlledDisplay = false;
  if (next && !isCssString) {
    if (prev) {
      if (!isString(prev)) {
        for (const key in prev) {
          if (next[key] == null) {
            setStyle(style2, key, "");
          }
        }
      } else {
        for (const prevStyle of prev.split(";")) {
          const key = prevStyle.slice(0, prevStyle.indexOf(":")).trim();
          if (next[key] == null) {
            setStyle(style2, key, "");
          }
        }
      }
    }
    for (const key in next) {
      if (key === "display") {
        hasControlledDisplay = true;
      }
      setStyle(style2, key, next[key]);
    }
  } else {
    if (isCssString) {
      if (prev !== next) {
        const cssVarText = style2[CSS_VAR_TEXT];
        if (cssVarText) {
          next += ";" + cssVarText;
        }
        style2.cssText = next;
        hasControlledDisplay = displayRE.test(next);
      }
    } else if (prev) {
      el.removeAttribute("style");
    }
  }
  if (vShowOriginalDisplay in el) {
    el[vShowOriginalDisplay] = hasControlledDisplay ? style2.display : "";
    if (el[vShowHidden]) {
      style2.display = "none";
    }
  }
}
const importantRE = /\s*!important$/;
function setStyle(style2, name, val) {
  if (isArray(val)) {
    val.forEach((v2) => setStyle(style2, name, v2));
  } else {
    if (val == null) val = "";
    if (name.startsWith("--")) {
      style2.setProperty(name, val);
    } else {
      const prefixed = autoPrefix(style2, name);
      if (importantRE.test(val)) {
        style2.setProperty(
          hyphenate(prefixed),
          val.replace(importantRE, ""),
          "important"
        );
      } else {
        style2[prefixed] = val;
      }
    }
  }
}
const prefixes = ["Webkit", "Moz", "ms"];
const prefixCache = {};
function autoPrefix(style2, rawName) {
  const cached = prefixCache[rawName];
  if (cached) {
    return cached;
  }
  let name = camelize(rawName);
  if (name !== "filter" && name in style2) {
    return prefixCache[rawName] = name;
  }
  name = capitalize(name);
  for (let i2 = 0; i2 < prefixes.length; i2++) {
    const prefixed = prefixes[i2] + name;
    if (prefixed in style2) {
      return prefixCache[rawName] = prefixed;
    }
  }
  return rawName;
}
const xlinkNS = "http://www.w3.org/1999/xlink";
function patchAttr(el, key, value, isSVG, instance, isBoolean = isSpecialBooleanAttr(key)) {
  if (isSVG && key.startsWith("xlink:")) {
    if (value == null) {
      el.removeAttributeNS(xlinkNS, key.slice(6, key.length));
    } else {
      el.setAttributeNS(xlinkNS, key, value);
    }
  } else {
    if (value == null || isBoolean && !includeBooleanAttr(value)) {
      el.removeAttribute(key);
    } else {
      el.setAttribute(
        key,
        isBoolean ? "" : isSymbol(value) ? String(value) : value
      );
    }
  }
}
function patchDOMProp(el, key, value, parentComponent, attrName) {
  if (key === "innerHTML" || key === "textContent") {
    if (value != null) {
      el[key] = key === "innerHTML" ? unsafeToTrustedHTML(value) : value;
    }
    return;
  }
  const tag = el.tagName;
  if (key === "value" && tag !== "PROGRESS" && // custom elements may use _value internally
  !tag.includes("-")) {
    const oldValue = tag === "OPTION" ? el.getAttribute("value") || "" : el.value;
    const newValue = value == null ? (
      // #11647: value should be set as empty string for null and undefined,
      // but <input type="checkbox"> should be set as 'on'.
      el.type === "checkbox" ? "on" : ""
    ) : String(value);
    if (oldValue !== newValue || !("_value" in el)) {
      el.value = newValue;
    }
    if (value == null) {
      el.removeAttribute(key);
    }
    el._value = value;
    return;
  }
  let needRemove = false;
  if (value === "" || value == null) {
    const type = typeof el[key];
    if (type === "boolean") {
      value = includeBooleanAttr(value);
    } else if (value == null && type === "string") {
      value = "";
      needRemove = true;
    } else if (type === "number") {
      value = 0;
      needRemove = true;
    }
  }
  try {
    el[key] = value;
  } catch (e) {
  }
  needRemove && el.removeAttribute(attrName || key);
}
function addEventListener(el, event, handler, options) {
  el.addEventListener(event, handler, options);
}
function removeEventListener(el, event, handler, options) {
  el.removeEventListener(event, handler, options);
}
const veiKey = /* @__PURE__ */ Symbol("_vei");
function patchEvent(el, rawName, prevValue, nextValue, instance = null) {
  const invokers = el[veiKey] || (el[veiKey] = {});
  const existingInvoker = invokers[rawName];
  if (nextValue && existingInvoker) {
    existingInvoker.value = nextValue;
  } else {
    const [name, options] = parseName(rawName);
    if (nextValue) {
      const invoker = invokers[rawName] = createInvoker(
        nextValue,
        instance
      );
      addEventListener(el, name, invoker, options);
    } else if (existingInvoker) {
      removeEventListener(el, name, existingInvoker, options);
      invokers[rawName] = void 0;
    }
  }
}
const optionsModifierRE = /(?:Once|Passive|Capture)$/;
function parseName(name) {
  let options;
  if (optionsModifierRE.test(name)) {
    options = {};
    let m2;
    while (m2 = name.match(optionsModifierRE)) {
      name = name.slice(0, name.length - m2[0].length);
      options[m2[0].toLowerCase()] = true;
    }
  }
  const event = name[2] === ":" ? name.slice(3) : hyphenate(name.slice(2));
  return [event, options];
}
let cachedNow = 0;
const p = /* @__PURE__ */ Promise.resolve();
const getNow = () => cachedNow || (p.then(() => cachedNow = 0), cachedNow = Date.now());
function createInvoker(initialValue, instance) {
  const invoker = (e) => {
    if (!e._vts) {
      e._vts = Date.now();
    } else if (e._vts <= invoker.attached) {
      return;
    }
    callWithAsyncErrorHandling(
      patchStopImmediatePropagation(e, invoker.value),
      instance,
      5,
      [e]
    );
  };
  invoker.value = initialValue;
  invoker.attached = getNow();
  return invoker;
}
function patchStopImmediatePropagation(e, value) {
  if (isArray(value)) {
    const originalStop = e.stopImmediatePropagation;
    e.stopImmediatePropagation = () => {
      originalStop.call(e);
      e._stopped = true;
    };
    return value.map(
      (fn) => (e2) => !e2._stopped && fn && fn(e2)
    );
  } else {
    return value;
  }
}
const isNativeOn = (key) => key.charCodeAt(0) === 111 && key.charCodeAt(1) === 110 && // lowercase letter
key.charCodeAt(2) > 96 && key.charCodeAt(2) < 123;
const patchProp = (el, key, prevValue, nextValue, namespace, parentComponent) => {
  const isSVG = namespace === "svg";
  if (key === "class") {
    patchClass(el, nextValue, isSVG);
  } else if (key === "style") {
    patchStyle(el, prevValue, nextValue);
  } else if (isOn(key)) {
    if (!isModelListener(key)) {
      patchEvent(el, key, prevValue, nextValue, parentComponent);
    }
  } else if (key[0] === "." ? (key = key.slice(1), true) : key[0] === "^" ? (key = key.slice(1), false) : shouldSetAsProp(el, key, nextValue, isSVG)) {
    patchDOMProp(el, key, nextValue);
    if (!el.tagName.includes("-") && (key === "value" || key === "checked" || key === "selected")) {
      patchAttr(el, key, nextValue, isSVG, parentComponent, key !== "value");
    }
  } else if (
    // #11081 force set props for possible async custom element
    el._isVueCE && (/[A-Z]/.test(key) || !isString(nextValue))
  ) {
    patchDOMProp(el, camelize(key), nextValue, parentComponent, key);
  } else {
    if (key === "true-value") {
      el._trueValue = nextValue;
    } else if (key === "false-value") {
      el._falseValue = nextValue;
    }
    patchAttr(el, key, nextValue, isSVG);
  }
};
function shouldSetAsProp(el, key, value, isSVG) {
  if (isSVG) {
    if (key === "innerHTML" || key === "textContent") {
      return true;
    }
    if (key in el && isNativeOn(key) && isFunction(value)) {
      return true;
    }
    return false;
  }
  if (key === "spellcheck" || key === "draggable" || key === "translate" || key === "autocorrect") {
    return false;
  }
  if (key === "sandbox" && el.tagName === "IFRAME") {
    return false;
  }
  if (key === "form") {
    return false;
  }
  if (key === "list" && el.tagName === "INPUT") {
    return false;
  }
  if (key === "type" && el.tagName === "TEXTAREA") {
    return false;
  }
  if (key === "width" || key === "height") {
    const tag = el.tagName;
    if (tag === "IMG" || tag === "VIDEO" || tag === "CANVAS" || tag === "SOURCE") {
      return false;
    }
  }
  if (isNativeOn(key) && isString(value)) {
    return false;
  }
  return key in el;
}
const getModelAssigner = (vnode) => {
  const fn = vnode.props["onUpdate:modelValue"] || false;
  return isArray(fn) ? (value) => invokeArrayFns(fn, value) : fn;
};
function onCompositionStart(e) {
  e.target.composing = true;
}
function onCompositionEnd(e) {
  const target = e.target;
  if (target.composing) {
    target.composing = false;
    target.dispatchEvent(new Event("input"));
  }
}
const assignKey = /* @__PURE__ */ Symbol("_assign");
function castValue(value, trim, number) {
  if (trim) value = value.trim();
  if (number) value = looseToNumber(value);
  return value;
}
const vModelText = {
  created(el, { modifiers: { lazy, trim, number } }, vnode) {
    el[assignKey] = getModelAssigner(vnode);
    const castToNumber = number || vnode.props && vnode.props.type === "number";
    addEventListener(el, lazy ? "change" : "input", (e) => {
      if (e.target.composing) return;
      el[assignKey](castValue(el.value, trim, castToNumber));
    });
    if (trim || castToNumber) {
      addEventListener(el, "change", () => {
        el.value = castValue(el.value, trim, castToNumber);
      });
    }
    if (!lazy) {
      addEventListener(el, "compositionstart", onCompositionStart);
      addEventListener(el, "compositionend", onCompositionEnd);
      addEventListener(el, "change", onCompositionEnd);
    }
  },
  // set value on mounted so it's after min/max for type="range"
  mounted(el, { value }) {
    el.value = value == null ? "" : value;
  },
  beforeUpdate(el, { value, oldValue, modifiers: { lazy, trim, number } }, vnode) {
    el[assignKey] = getModelAssigner(vnode);
    if (el.composing) return;
    const elValue = (number || el.type === "number") && !/^0\d/.test(el.value) ? looseToNumber(el.value) : el.value;
    const newValue = value == null ? "" : value;
    if (elValue === newValue) {
      return;
    }
    if (document.activeElement === el && el.type !== "range") {
      if (lazy && value === oldValue) {
        return;
      }
      if (trim && el.value.trim() === newValue) {
        return;
      }
    }
    el.value = newValue;
  }
};
const systemModifiers = ["ctrl", "shift", "alt", "meta"];
const modifierGuards = {
  stop: (e) => e.stopPropagation(),
  prevent: (e) => e.preventDefault(),
  self: (e) => e.target !== e.currentTarget,
  ctrl: (e) => !e.ctrlKey,
  shift: (e) => !e.shiftKey,
  alt: (e) => !e.altKey,
  meta: (e) => !e.metaKey,
  left: (e) => "button" in e && e.button !== 0,
  middle: (e) => "button" in e && e.button !== 1,
  right: (e) => "button" in e && e.button !== 2,
  exact: (e, modifiers) => systemModifiers.some((m2) => e[`${m2}Key`] && !modifiers.includes(m2))
};
const withModifiers = (fn, modifiers) => {
  const cache = fn._withMods || (fn._withMods = {});
  const cacheKey = modifiers.join(".");
  return cache[cacheKey] || (cache[cacheKey] = ((event, ...args) => {
    for (let i2 = 0; i2 < modifiers.length; i2++) {
      const guard = modifierGuards[modifiers[i2]];
      if (guard && guard(event, modifiers)) return;
    }
    return fn(event, ...args);
  }));
};
const keyNames = {
  esc: "escape",
  space: " ",
  up: "arrow-up",
  left: "arrow-left",
  right: "arrow-right",
  down: "arrow-down",
  delete: "backspace"
};
const withKeys = (fn, modifiers) => {
  const cache = fn._withKeys || (fn._withKeys = {});
  const cacheKey = modifiers.join(".");
  return cache[cacheKey] || (cache[cacheKey] = ((event) => {
    if (!("key" in event)) {
      return;
    }
    const eventKey = hyphenate(event.key);
    if (modifiers.some(
      (k2) => k2 === eventKey || keyNames[k2] === eventKey
    )) {
      return fn(event);
    }
  }));
};
const rendererOptions = /* @__PURE__ */ extend({ patchProp }, nodeOps);
let renderer;
function ensureRenderer() {
  return renderer || (renderer = createRenderer(rendererOptions));
}
const createApp = ((...args) => {
  const app2 = ensureRenderer().createApp(...args);
  const { mount } = app2;
  app2.mount = (containerOrSelector) => {
    const container = normalizeContainer(containerOrSelector);
    if (!container) return;
    const component = app2._component;
    if (!isFunction(component) && !component.render && !component.template) {
      component.template = container.innerHTML;
    }
    if (container.nodeType === 1) {
      container.textContent = "";
    }
    const proxy = mount(container, false, resolveRootNamespace(container));
    if (container instanceof Element) {
      container.removeAttribute("v-cloak");
      container.setAttribute("data-v-app", "");
    }
    return proxy;
  };
  return app2;
});
function resolveRootNamespace(container) {
  if (container instanceof SVGElement) {
    return "svg";
  }
  if (typeof MathMLElement === "function" && container instanceof MathMLElement) {
    return "mathml";
  }
}
function normalizeContainer(container) {
  if (isString(container)) {
    const res = document.querySelector(container);
    return res;
  }
  return container;
}
var ie$1 = Object.defineProperty;
var K = Object.getOwnPropertySymbols;
var se = Object.prototype.hasOwnProperty, ae$1 = Object.prototype.propertyIsEnumerable;
var N$1 = (e, t, n) => t in e ? ie$1(e, t, { enumerable: true, configurable: true, writable: true, value: n }) : e[t] = n, d = (e, t) => {
  for (var n in t || (t = {})) se.call(t, n) && N$1(e, n, t[n]);
  if (K) for (var n of K(t)) ae$1.call(t, n) && N$1(e, n, t[n]);
  return e;
};
function l(e) {
  return e == null || e === "" || Array.isArray(e) && e.length === 0 || !(e instanceof Date) && typeof e == "object" && Object.keys(e).length === 0;
}
function c$1(e) {
  return typeof e == "function" && "call" in e && "apply" in e;
}
function s$1(e) {
  return !l(e);
}
function i(e, t = true) {
  return e instanceof Object && e.constructor === Object && (t || Object.keys(e).length !== 0);
}
function $$1(e = {}, t = {}) {
  let n = d({}, e);
  return Object.keys(t).forEach((o) => {
    let r = o;
    i(t[r]) && r in e && i(e[r]) ? n[r] = $$1(e[r], t[r]) : n[r] = t[r];
  }), n;
}
function w(...e) {
  return e.reduce((t, n, o) => o === 0 ? n : $$1(t, n), {});
}
function m(e, ...t) {
  return c$1(e) ? e(...t) : e;
}
function a(e, t = true) {
  return typeof e == "string" && (t || e !== "");
}
function z(e) {
  return s$1(e) && !isNaN(e);
}
function G(e, t) {
  if (t) {
    let n = t.test(e);
    return t.lastIndex = 0, n;
  }
  return false;
}
function H(...e) {
  return w(...e);
}
function Y$1(e) {
  return e && e.replace(/\/\*(?:(?!\*\/)[\s\S])*\*\/|[\r\n\t]+/g, "").replace(/ {2,}/g, " ").replace(/ ([{:}]) /g, "$1").replace(/([;,]) /g, "$1").replace(/ !/g, "!").replace(/: /g, ":").trim();
}
function re(e) {
  return a(e) ? e.replace(/(_)/g, "-").replace(/([a-z])([A-Z])/g, "$1-$2").toLowerCase() : e;
}
function s() {
  let r = /* @__PURE__ */ new Map();
  return { on(e, t) {
    let n = r.get(e);
    return n ? n.push(t) : n = [t], r.set(e, n), this;
  }, off(e, t) {
    let n = r.get(e);
    return n && n.splice(n.indexOf(t) >>> 0, 1), this;
  }, emit(e, t) {
    let n = r.get(e);
    n && n.forEach((i2) => {
      i2(t);
    });
  }, clear() {
    r.clear();
  } };
}
function y(t) {
  if (t) {
    let e = t.parentNode;
    return e && e instanceof ShadowRoot && e.host && (e = e.host), e;
  }
  return null;
}
function T(t) {
  return !!(t !== null && typeof t != "undefined" && t.nodeName && y(t));
}
function c(t) {
  return typeof Element != "undefined" ? t instanceof Element : t !== null && typeof t == "object" && t.nodeType === 1 && typeof t.nodeName == "string";
}
function A(t, e = {}) {
  if (c(t)) {
    let o = (n, r) => {
      var l2, d2;
      let i2 = (l2 = t == null ? void 0 : t.$attrs) != null && l2[n] ? [(d2 = t == null ? void 0 : t.$attrs) == null ? void 0 : d2[n]] : [];
      return [r].flat().reduce((s2, a2) => {
        if (a2 != null) {
          let u = typeof a2;
          if (u === "string" || u === "number") s2.push(a2);
          else if (u === "object") {
            let p2 = Array.isArray(a2) ? o(n, a2) : Object.entries(a2).map(([f, g]) => n === "style" && (g || g === 0) ? `${f.replace(/([a-z])([A-Z])/g, "$1-$2").toLowerCase()}:${g}` : g ? f : void 0);
            s2 = p2.length ? s2.concat(p2.filter((f) => !!f)) : s2;
          }
        }
        return s2;
      }, i2);
    };
    Object.entries(e).forEach(([n, r]) => {
      if (r != null) {
        let i2 = n.match(/^on(.+)/);
        i2 ? t.addEventListener(i2[1].toLowerCase(), r) : n === "p-bind" || n === "pBind" ? A(t, r) : (r = n === "class" ? [...new Set(o("class", r))].join(" ").trim() : n === "style" ? o("style", r).join(";").trim() : r, (t.$attrs = t.$attrs || {}) && (t.$attrs[n] = r), t.setAttribute(n, r));
      }
    });
  }
}
function tt() {
  return !!(typeof window != "undefined" && window.document && window.document.createElement);
}
function _t(t, e = "", o) {
  c(t) && o !== null && o !== void 0 && t.setAttribute(e, o);
}
var rt = Object.defineProperty, st = Object.defineProperties;
var nt = Object.getOwnPropertyDescriptors;
var F = Object.getOwnPropertySymbols;
var xe = Object.prototype.hasOwnProperty, be = Object.prototype.propertyIsEnumerable;
var _e = (e, t, r) => t in e ? rt(e, t, { enumerable: true, configurable: true, writable: true, value: r }) : e[t] = r, h = (e, t) => {
  for (var r in t || (t = {})) xe.call(t, r) && _e(e, r, t[r]);
  if (F) for (var r of F(t)) be.call(t, r) && _e(e, r, t[r]);
  return e;
}, $ = (e, t) => st(e, nt(t));
var v = (e, t) => {
  var r = {};
  for (var s2 in e) xe.call(e, s2) && t.indexOf(s2) < 0 && (r[s2] = e[s2]);
  if (e != null && F) for (var s2 of F(e)) t.indexOf(s2) < 0 && be.call(e, s2) && (r[s2] = e[s2]);
  return r;
};
var at = s(), N = at;
var k = /{([^}]*)}/g, ne = /(\d+\s+[\+\-\*\/]\s+\d+)/g, ie = /var\([^)]+\)/g;
function oe(e) {
  return a(e) ? e.replace(/[A-Z]/g, (t, r) => r === 0 ? t : "." + t.toLowerCase()).toLowerCase() : e;
}
function ve(e) {
  return i(e) && e.hasOwnProperty("$value") && e.hasOwnProperty("$type") ? e.$value : e;
}
function dt(e) {
  return e.replaceAll(/ /g, "").replace(/[^\w]/g, "-");
}
function Q(e = "", t = "") {
  return dt(`${a(e, false) && a(t, false) ? `${e}-` : e}${t}`);
}
function ae(e = "", t = "") {
  return `--${Q(e, t)}`;
}
function ht(e = "") {
  let t = (e.match(/{/g) || []).length, r = (e.match(/}/g) || []).length;
  return (t + r) % 2 !== 0;
}
function Y(e, t = "", r = "", s2 = [], i2) {
  if (a(e)) {
    let a2 = e.trim();
    if (ht(a2)) return;
    if (G(a2, k)) {
      let n = a2.replaceAll(k, (l2) => {
        let c2 = l2.replace(/{|}/g, "").split(".").filter((m2) => !s2.some((d2) => G(m2, d2)));
        return `var(${ae(r, re(c2.join("-")))}${s$1(i2) ? `, ${i2}` : ""})`;
      });
      return G(n.replace(ie, "0"), ne) ? `calc(${n})` : n;
    }
    return a2;
  } else if (z(e)) return e;
}
function Re(e, t, r) {
  a(t, false) && e.push(`${t}:${r};`);
}
function C(e, t) {
  return e ? `${e}{${t}}` : "";
}
function le(e, t) {
  if (e.indexOf("dt(") === -1) return e;
  function r(n, l2) {
    let o = [], c2 = 0, m2 = "", d2 = null, u = 0;
    for (; c2 <= n.length; ) {
      let g = n[c2];
      if ((g === '"' || g === "'" || g === "`") && n[c2 - 1] !== "\\" && (d2 = d2 === g ? null : g), !d2 && (g === "(" && u++, g === ")" && u--, (g === "," || c2 === n.length) && u === 0)) {
        let f = m2.trim();
        f.startsWith("dt(") ? o.push(le(f, l2)) : o.push(s2(f)), m2 = "", c2++;
        continue;
      }
      g !== void 0 && (m2 += g), c2++;
    }
    return o;
  }
  function s2(n) {
    let l2 = n[0];
    if ((l2 === '"' || l2 === "'" || l2 === "`") && n[n.length - 1] === l2) return n.slice(1, -1);
    let o = Number(n);
    return isNaN(o) ? n : o;
  }
  let i2 = [], a2 = [];
  for (let n = 0; n < e.length; n++) if (e[n] === "d" && e.slice(n, n + 3) === "dt(") a2.push(n), n += 2;
  else if (e[n] === ")" && a2.length > 0) {
    let l2 = a2.pop();
    a2.length === 0 && i2.push([l2, n]);
  }
  if (!i2.length) return e;
  for (let n = i2.length - 1; n >= 0; n--) {
    let [l2, o] = i2[n], c2 = e.slice(l2 + 3, o), m2 = r(c2, t), d2 = t(...m2);
    e = e.slice(0, l2) + d2 + e.slice(o + 1);
  }
  return e;
}
var E = (...e) => ue(S.getTheme(), ...e), ue = (e = {}, t, r, s2) => {
  if (t) {
    let { variable: i2, options: a2 } = S.defaults || {}, { prefix: n, transform: l$1 } = (e == null ? void 0 : e.options) || a2 || {}, o = G(t, k) ? t : `{${t}}`;
    return s2 === "value" || l(s2) && l$1 === "strict" ? S.getTokenValue(t) : Y(o, void 0, n, [i2.excludedKeyRegex], r);
  }
  return "";
};
function ar(e, ...t) {
  if (e instanceof Array) {
    let r = e.reduce((s2, i2, a2) => {
      var n;
      return s2 + i2 + ((n = m(t[a2], { dt: E })) != null ? n : "");
    }, "");
    return le(r, E);
  }
  return m(e, { dt: E });
}
function de(e, t = {}) {
  let r = S.defaults.variable, { prefix: s2 = r.prefix, selector: i$1 = r.selector, excludedKeyRegex: a2 = r.excludedKeyRegex } = t, n = [], l2 = [], o = [{ node: e, path: s2 }];
  for (; o.length; ) {
    let { node: m2, path: d2 } = o.pop();
    for (let u in m2) {
      let g = m2[u], f = ve(g), p2 = G(u, a2) ? Q(d2) : Q(d2, re(u));
      if (i(f)) o.push({ node: f, path: p2 });
      else {
        let y2 = ae(p2), R = Y(f, p2, s2, [a2]);
        Re(l2, y2, R);
        let T2 = p2;
        s2 && T2.startsWith(s2 + "-") && (T2 = T2.slice(s2.length + 1)), n.push(T2.replace(/-/g, "."));
      }
    }
  }
  let c2 = l2.join("");
  return { value: l2, tokens: n, declarations: c2, css: C(i$1, c2) };
}
var b = { regex: { rules: { class: { pattern: /^\.([a-zA-Z][\w-]*)$/, resolve(e) {
  return { type: "class", selector: e, matched: this.pattern.test(e.trim()) };
} }, attr: { pattern: /^\[(.*)\]$/, resolve(e) {
  return { type: "attr", selector: `:root${e},:host${e}`, matched: this.pattern.test(e.trim()) };
} }, media: { pattern: /^@media (.*)$/, resolve(e) {
  return { type: "media", selector: e, matched: this.pattern.test(e.trim()) };
} }, system: { pattern: /^system$/, resolve(e) {
  return { type: "system", selector: "@media (prefers-color-scheme: dark)", matched: this.pattern.test(e.trim()) };
} }, custom: { resolve(e) {
  return { type: "custom", selector: e, matched: true };
} } }, resolve(e) {
  let t = Object.keys(this.rules).filter((r) => r !== "custom").map((r) => this.rules[r]);
  return [e].flat().map((r) => {
    var s2;
    return (s2 = t.map((i2) => i2.resolve(r)).find((i2) => i2.matched)) != null ? s2 : this.rules.custom.resolve(r);
  });
} }, _toVariables(e, t) {
  return de(e, { prefix: t == null ? void 0 : t.prefix });
}, getCommon({ name: e = "", theme: t = {}, params: r, set: s2, defaults: i2 }) {
  var R, T2, j, O, M, z2, V;
  let { preset: a2, options: n } = t, l2, o, c2, m$1, d2, u, g;
  if (s$1(a2) && n.transform !== "strict") {
    let { primitive: L, semantic: te, extend: re2 } = a2, f = te || {}, { colorScheme: K2 } = f, A2 = v(f, ["colorScheme"]), x = re2 || {}, { colorScheme: X } = x, G2 = v(x, ["colorScheme"]), p2 = K2 || {}, { dark: U } = p2, B = v(p2, ["dark"]), y2 = X || {}, { dark: I } = y2, H2 = v(y2, ["dark"]), W = s$1(L) ? this._toVariables({ primitive: L }, n) : {}, q = s$1(A2) ? this._toVariables({ semantic: A2 }, n) : {}, Z = s$1(B) ? this._toVariables({ light: B }, n) : {}, pe = s$1(U) ? this._toVariables({ dark: U }, n) : {}, fe = s$1(G2) ? this._toVariables({ semantic: G2 }, n) : {}, ye = s$1(H2) ? this._toVariables({ light: H2 }, n) : {}, Se = s$1(I) ? this._toVariables({ dark: I }, n) : {}, [Me, ze] = [(R = W.declarations) != null ? R : "", W.tokens], [Ke, Xe] = [(T2 = q.declarations) != null ? T2 : "", q.tokens || []], [Ge, Ue] = [(j = Z.declarations) != null ? j : "", Z.tokens || []], [Be, Ie] = [(O = pe.declarations) != null ? O : "", pe.tokens || []], [He, We] = [(M = fe.declarations) != null ? M : "", fe.tokens || []], [qe, Ze] = [(z2 = ye.declarations) != null ? z2 : "", ye.tokens || []], [Fe, Je] = [(V = Se.declarations) != null ? V : "", Se.tokens || []];
    l2 = this.transformCSS(e, Me, "light", "variable", n, s2, i2), o = ze;
    let Qe = this.transformCSS(e, `${Ke}${Ge}`, "light", "variable", n, s2, i2), Ye = this.transformCSS(e, `${Be}`, "dark", "variable", n, s2, i2);
    c2 = `${Qe}${Ye}`, m$1 = [.../* @__PURE__ */ new Set([...Xe, ...Ue, ...Ie])];
    let et = this.transformCSS(e, `${He}${qe}color-scheme:light`, "light", "variable", n, s2, i2), tt2 = this.transformCSS(e, `${Fe}color-scheme:dark`, "dark", "variable", n, s2, i2);
    d2 = `${et}${tt2}`, u = [.../* @__PURE__ */ new Set([...We, ...Ze, ...Je])], g = m(a2.css, { dt: E });
  }
  return { primitive: { css: l2, tokens: o }, semantic: { css: c2, tokens: m$1 }, global: { css: d2, tokens: u }, style: g };
}, getPreset({ name: e = "", preset: t = {}, options: r, params: s2, set: i2, defaults: a2, selector: n }) {
  var f, x, p2;
  let l2, o, c2;
  if (s$1(t) && r.transform !== "strict") {
    let y2 = e.replace("-directive", ""), m$1 = t, { colorScheme: R, extend: T2, css: j } = m$1, O = v(m$1, ["colorScheme", "extend", "css"]), d2 = T2 || {}, { colorScheme: M } = d2, z2 = v(d2, ["colorScheme"]), u = R || {}, { dark: V } = u, L = v(u, ["dark"]), g = M || {}, { dark: te } = g, re2 = v(g, ["dark"]), K2 = s$1(O) ? this._toVariables({ [y2]: h(h({}, O), z2) }, r) : {}, A2 = s$1(L) ? this._toVariables({ [y2]: h(h({}, L), re2) }, r) : {}, X = s$1(V) ? this._toVariables({ [y2]: h(h({}, V), te) }, r) : {}, [G2, U] = [(f = K2.declarations) != null ? f : "", K2.tokens || []], [B, I] = [(x = A2.declarations) != null ? x : "", A2.tokens || []], [H2, W] = [(p2 = X.declarations) != null ? p2 : "", X.tokens || []], q = this.transformCSS(y2, `${G2}${B}`, "light", "variable", r, i2, a2, n), Z = this.transformCSS(y2, H2, "dark", "variable", r, i2, a2, n);
    l2 = `${q}${Z}`, o = [.../* @__PURE__ */ new Set([...U, ...I, ...W])], c2 = m(j, { dt: E });
  }
  return { css: l2, tokens: o, style: c2 };
}, getPresetC({ name: e = "", theme: t = {}, params: r, set: s2, defaults: i2 }) {
  var o;
  let { preset: a2, options: n } = t, l2 = (o = a2 == null ? void 0 : a2.components) == null ? void 0 : o[e];
  return this.getPreset({ name: e, preset: l2, options: n, params: r, set: s2, defaults: i2 });
}, getPresetD({ name: e = "", theme: t = {}, params: r, set: s2, defaults: i2 }) {
  var c2, m2;
  let a2 = e.replace("-directive", ""), { preset: n, options: l2 } = t, o = ((c2 = n == null ? void 0 : n.components) == null ? void 0 : c2[a2]) || ((m2 = n == null ? void 0 : n.directives) == null ? void 0 : m2[a2]);
  return this.getPreset({ name: a2, preset: o, options: l2, params: r, set: s2, defaults: i2 });
}, applyDarkColorScheme(e) {
  return !(e.darkModeSelector === "none" || e.darkModeSelector === false);
}, getColorSchemeOption(e, t) {
  var r;
  return this.applyDarkColorScheme(e) ? this.regex.resolve(e.darkModeSelector === true ? t.options.darkModeSelector : (r = e.darkModeSelector) != null ? r : t.options.darkModeSelector) : [];
}, getLayerOrder(e, t = {}, r, s2) {
  let { cssLayer: i2 } = t;
  return i2 ? `@layer ${m(i2.order || i2.name || "primeui", r)}` : "";
}, getCommonStyleSheet({ name: e = "", theme: t = {}, params: r, props: s2 = {}, set: i$1, defaults: a2 }) {
  let n = this.getCommon({ name: e, theme: t, params: r, set: i$1, defaults: a2 }), l2 = Object.entries(s2).reduce((o, [c2, m2]) => o.push(`${c2}="${m2}"`) && o, []).join(" ");
  return Object.entries(n || {}).reduce((o, [c2, m2]) => {
    if (i(m2) && Object.hasOwn(m2, "css")) {
      let d2 = Y$1(m2.css), u = `${c2}-variables`;
      o.push(`<style type="text/css" data-primevue-style-id="${u}" ${l2}>${d2}</style>`);
    }
    return o;
  }, []).join("");
}, getStyleSheet({ name: e = "", theme: t = {}, params: r, props: s2 = {}, set: i2, defaults: a2 }) {
  var c2;
  let n = { name: e, theme: t, params: r, set: i2, defaults: a2 }, l2 = (c2 = e.includes("-directive") ? this.getPresetD(n) : this.getPresetC(n)) == null ? void 0 : c2.css, o = Object.entries(s2).reduce((m2, [d2, u]) => m2.push(`${d2}="${u}"`) && m2, []).join(" ");
  return l2 ? `<style type="text/css" data-primevue-style-id="${e}-variables" ${o}>${Y$1(l2)}</style>` : "";
}, createTokens(e = {}, t, r = "", s2 = "", i$1 = {}) {
  let a2 = function(l$1, o = {}, c2 = []) {
    if (c2.includes(this.path)) return console.warn(`Circular reference detected at ${this.path}`), { colorScheme: l$1, path: this.path, paths: o, value: void 0 };
    c2.push(this.path), o.name = this.path, o.binding || (o.binding = {});
    let m2 = this.value;
    if (typeof this.value == "string" && k.test(this.value)) {
      let u = this.value.trim().replace(k, (g) => {
        var y2;
        let f = g.slice(1, -1), x = this.tokens[f];
        if (!x) return console.warn(`Token not found for path: ${f}`), "__UNRESOLVED__";
        let p2 = x.computed(l$1, o, c2);
        return Array.isArray(p2) && p2.length === 2 ? `light-dark(${p2[0].value},${p2[1].value})` : (y2 = p2 == null ? void 0 : p2.value) != null ? y2 : "__UNRESOLVED__";
      });
      m2 = ne.test(u.replace(ie, "0")) ? `calc(${u})` : u;
    }
    return l(o.binding) && delete o.binding, c2.pop(), { colorScheme: l$1, path: this.path, paths: o, value: m2.includes("__UNRESOLVED__") ? void 0 : m2 };
  }, n = (l2, o, c2) => {
    Object.entries(l2).forEach(([m2, d2]) => {
      let u = G(m2, t.variable.excludedKeyRegex) ? o : o ? `${o}.${oe(m2)}` : oe(m2), g = c2 ? `${c2}.${m2}` : m2;
      i(d2) ? n(d2, u, g) : (i$1[u] || (i$1[u] = { paths: [], computed: (f, x = {}, p2 = []) => {
        if (i$1[u].paths.length === 1) return i$1[u].paths[0].computed(i$1[u].paths[0].scheme, x.binding, p2);
        if (f && f !== "none") for (let y2 = 0; y2 < i$1[u].paths.length; y2++) {
          let R = i$1[u].paths[y2];
          if (R.scheme === f) return R.computed(f, x.binding, p2);
        }
        return i$1[u].paths.map((y2) => y2.computed(y2.scheme, x[y2.scheme], p2));
      } }), i$1[u].paths.push({ path: g, value: d2, scheme: g.includes("colorScheme.light") ? "light" : g.includes("colorScheme.dark") ? "dark" : "none", computed: a2, tokens: i$1 }));
    });
  };
  return n(e, r, s2), i$1;
}, getTokenValue(e, t, r) {
  var l2;
  let i2 = ((o) => o.split(".").filter((m2) => !G(m2.toLowerCase(), r.variable.excludedKeyRegex)).join("."))(t), a2 = t.includes("colorScheme.light") ? "light" : t.includes("colorScheme.dark") ? "dark" : void 0, n = [(l2 = e[i2]) == null ? void 0 : l2.computed(a2)].flat().filter((o) => o);
  return n.length === 1 ? n[0].value : n.reduce((o = {}, c2) => {
    let u = c2, { colorScheme: m2 } = u, d2 = v(u, ["colorScheme"]);
    return o[m2] = d2, o;
  }, void 0);
}, getSelectorRule(e, t, r, s2) {
  return r === "class" || r === "attr" ? C(s$1(t) ? `${e}${t},${e} ${t}` : e, s2) : C(e, C(t != null ? t : ":root,:host", s2));
}, transformCSS(e, t, r, s2, i$1 = {}, a2, n, l2) {
  if (s$1(t)) {
    let { cssLayer: o } = i$1;
    if (s2 !== "style") {
      let c2 = this.getColorSchemeOption(i$1, n);
      t = r === "dark" ? c2.reduce((m2, { type: d2, selector: u }) => (s$1(u) && (m2 += u.includes("[CSS]") ? u.replace("[CSS]", t) : this.getSelectorRule(u, l2, d2, t)), m2), "") : C(l2 != null ? l2 : ":root,:host", t);
    }
    if (o) {
      let c2 = { name: "primeui" };
      i(o) && (c2.name = m(o.name, { name: e, type: s2 })), s$1(c2.name) && (t = C(`@layer ${c2.name}`, t), a2 == null || a2.layerNames(c2.name));
    }
    return t;
  }
  return "";
} };
var S = { defaults: { variable: { prefix: "p", selector: ":root,:host", excludedKeyRegex: /^(primitive|semantic|components|directives|variables|colorscheme|light|dark|common|root|states|extend|css)$/gi }, options: { prefix: "p", darkModeSelector: "system", cssLayer: false } }, _theme: void 0, _layerNames: /* @__PURE__ */ new Set(), _loadedStyleNames: /* @__PURE__ */ new Set(), _loadingStyles: /* @__PURE__ */ new Set(), _tokens: {}, update(e = {}) {
  let { theme: t } = e;
  t && (this._theme = $(h({}, t), { options: h(h({}, this.defaults.options), t.options) }), this._tokens = b.createTokens(this.preset, this.defaults), this.clearLoadedStyleNames());
}, get theme() {
  return this._theme;
}, get preset() {
  var e;
  return ((e = this.theme) == null ? void 0 : e.preset) || {};
}, get options() {
  var e;
  return ((e = this.theme) == null ? void 0 : e.options) || {};
}, get tokens() {
  return this._tokens;
}, getTheme() {
  return this.theme;
}, setTheme(e) {
  this.update({ theme: e }), N.emit("theme:change", e);
}, getPreset() {
  return this.preset;
}, setPreset(e) {
  this._theme = $(h({}, this.theme), { preset: e }), this._tokens = b.createTokens(e, this.defaults), this.clearLoadedStyleNames(), N.emit("preset:change", e), N.emit("theme:change", this.theme);
}, getOptions() {
  return this.options;
}, setOptions(e) {
  this._theme = $(h({}, this.theme), { options: e }), this.clearLoadedStyleNames(), N.emit("options:change", e), N.emit("theme:change", this.theme);
}, getLayerNames() {
  return [...this._layerNames];
}, setLayerNames(e) {
  this._layerNames.add(e);
}, getLoadedStyleNames() {
  return this._loadedStyleNames;
}, isStyleNameLoaded(e) {
  return this._loadedStyleNames.has(e);
}, setLoadedStyleName(e) {
  this._loadedStyleNames.add(e);
}, deleteLoadedStyleName(e) {
  this._loadedStyleNames.delete(e);
}, clearLoadedStyleNames() {
  this._loadedStyleNames.clear();
}, getTokenValue(e) {
  return b.getTokenValue(this.tokens, e, this.defaults);
}, getCommon(e = "", t) {
  return b.getCommon({ name: e, theme: this.theme, params: t, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } });
}, getComponent(e = "", t) {
  let r = { name: e, theme: this.theme, params: t, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } };
  return b.getPresetC(r);
}, getDirective(e = "", t) {
  let r = { name: e, theme: this.theme, params: t, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } };
  return b.getPresetD(r);
}, getCustomPreset(e = "", t, r, s2) {
  let i2 = { name: e, preset: t, options: this.options, selector: r, params: s2, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } };
  return b.getPreset(i2);
}, getLayerOrderCSS(e = "") {
  return b.getLayerOrder(e, this.options, { names: this.getLayerNames() }, this.defaults);
}, transformCSS(e = "", t, r = "style", s2) {
  return b.transformCSS(e, t, s2, r, this.options, { layerNames: this.setLayerNames.bind(this) }, this.defaults);
}, getCommonStyleSheet(e = "", t, r = {}) {
  return b.getCommonStyleSheet({ name: e, theme: this.theme, params: t, props: r, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } });
}, getStyleSheet(e, t, r = {}) {
  return b.getStyleSheet({ name: e, theme: this.theme, params: t, props: r, defaults: this.defaults, set: { layerNames: this.setLayerNames.bind(this) } });
}, onStyleMounted(e) {
  this._loadingStyles.add(e);
}, onStyleUpdated(e) {
  this._loadingStyles.add(e);
}, onStyleLoaded(e, { name: t }) {
  this._loadingStyles.size && (this._loadingStyles.delete(t), N.emit(`theme:${t}:load`, e), !this._loadingStyles.size && N.emit("theme:load"));
} };
var FilterMatchMode = {
  STARTS_WITH: "startsWith",
  CONTAINS: "contains",
  NOT_CONTAINS: "notContains",
  ENDS_WITH: "endsWith",
  EQUALS: "equals",
  NOT_EQUALS: "notEquals",
  LESS_THAN: "lt",
  LESS_THAN_OR_EQUAL_TO: "lte",
  GREATER_THAN: "gt",
  GREATER_THAN_OR_EQUAL_TO: "gte",
  DATE_IS: "dateIs",
  DATE_IS_NOT: "dateIsNot",
  DATE_BEFORE: "dateBefore",
  DATE_AFTER: "dateAfter"
};
var style = "\n    *,\n    ::before,\n    ::after {\n        box-sizing: border-box;\n    }\n\n    .p-collapsible-enter-active {\n        animation: p-animate-collapsible-expand 0.2s ease-out;\n        overflow: hidden;\n    }\n\n    .p-collapsible-leave-active {\n        animation: p-animate-collapsible-collapse 0.2s ease-out;\n        overflow: hidden;\n    }\n\n    @keyframes p-animate-collapsible-expand {\n        from {\n            grid-template-rows: 0fr;\n        }\n        to {\n            grid-template-rows: 1fr;\n        }\n    }\n\n    @keyframes p-animate-collapsible-collapse {\n        from {\n            grid-template-rows: 1fr;\n        }\n        to {\n            grid-template-rows: 0fr;\n        }\n    }\n\n    .p-disabled,\n    .p-disabled * {\n        cursor: default;\n        pointer-events: none;\n        user-select: none;\n    }\n\n    .p-disabled,\n    .p-component:disabled {\n        opacity: dt('disabled.opacity');\n    }\n\n    .pi {\n        font-size: dt('icon.size');\n    }\n\n    .p-icon {\n        width: dt('icon.size');\n        height: dt('icon.size');\n    }\n\n    .p-overlay-mask {\n        background: var(--px-mask-background, dt('mask.background'));\n        color: dt('mask.color');\n        position: fixed;\n        top: 0;\n        left: 0;\n        width: 100%;\n        height: 100%;\n    }\n\n    .p-overlay-mask-enter-active {\n        animation: p-animate-overlay-mask-enter dt('mask.transition.duration') forwards;\n    }\n\n    .p-overlay-mask-leave-active {\n        animation: p-animate-overlay-mask-leave dt('mask.transition.duration') forwards;\n    }\n\n    @keyframes p-animate-overlay-mask-enter {\n        from {\n            background: transparent;\n        }\n        to {\n            background: var(--px-mask-background, dt('mask.background'));\n        }\n    }\n    @keyframes p-animate-overlay-mask-leave {\n        from {\n            background: var(--px-mask-background, dt('mask.background'));\n        }\n        to {\n            background: transparent;\n        }\n    }\n\n    .p-anchored-overlay-enter-active {\n        animation: p-animate-anchored-overlay-enter 300ms cubic-bezier(.19,1,.22,1);\n    }\n\n    .p-anchored-overlay-leave-active {\n        animation: p-animate-anchored-overlay-leave 300ms cubic-bezier(.19,1,.22,1);\n    }\n\n    @keyframes p-animate-anchored-overlay-enter {\n        from {\n            opacity: 0;\n            transform: scale(0.93);\n        }\n    }\n\n    @keyframes p-animate-anchored-overlay-leave {\n        to {\n            opacity: 0;\n            transform: scale(0.93);\n        }\n    }\n";
function _typeof$2(o) {
  "@babel/helpers - typeof";
  return _typeof$2 = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(o2) {
    return typeof o2;
  } : function(o2) {
    return o2 && "function" == typeof Symbol && o2.constructor === Symbol && o2 !== Symbol.prototype ? "symbol" : typeof o2;
  }, _typeof$2(o);
}
function ownKeys$2(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$2(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$2(Object(t), true).forEach(function(r2) {
      _defineProperty$2(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$2(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function _defineProperty$2(e, r, t) {
  return (r = _toPropertyKey$2(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e;
}
function _toPropertyKey$2(t) {
  var i2 = _toPrimitive$2(t, "string");
  return "symbol" == _typeof$2(i2) ? i2 : i2 + "";
}
function _toPrimitive$2(t, r) {
  if ("object" != _typeof$2(t) || !t) return t;
  var e = t[Symbol.toPrimitive];
  if (void 0 !== e) {
    var i2 = e.call(t, r);
    if ("object" != _typeof$2(i2)) return i2;
    throw new TypeError("@@toPrimitive must return a primitive value.");
  }
  return ("string" === r ? String : Number)(t);
}
function tryOnMounted(fn) {
  var sync = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : true;
  if (getCurrentInstance() && getCurrentInstance().components) onMounted(fn);
  else if (sync) fn();
  else nextTick(fn);
}
var _id = 0;
function useStyle(css3) {
  var options = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
  var isLoaded = ref(false);
  var cssRef = ref(css3);
  var styleRef = ref(null);
  var defaultDocument = tt() ? window.document : void 0;
  var _options$document = options.document, document2 = _options$document === void 0 ? defaultDocument : _options$document, _options$immediate = options.immediate, immediate = _options$immediate === void 0 ? true : _options$immediate, _options$manual = options.manual, manual = _options$manual === void 0 ? false : _options$manual, _options$name = options.name, name = _options$name === void 0 ? "style_".concat(++_id) : _options$name, _options$id = options.id, id = _options$id === void 0 ? void 0 : _options$id, _options$media = options.media, media = _options$media === void 0 ? void 0 : _options$media, _options$nonce = options.nonce, nonce = _options$nonce === void 0 ? void 0 : _options$nonce, _options$first = options.first, first = _options$first === void 0 ? false : _options$first, _options$onMounted = options.onMounted, onStyleMounted = _options$onMounted === void 0 ? void 0 : _options$onMounted, _options$onUpdated = options.onUpdated, onStyleUpdated = _options$onUpdated === void 0 ? void 0 : _options$onUpdated, _options$onLoad = options.onLoad, onStyleLoaded = _options$onLoad === void 0 ? void 0 : _options$onLoad, _options$props = options.props, props = _options$props === void 0 ? {} : _options$props;
  var stop = function stop2() {
  };
  var load2 = function load3(_css) {
    var _props = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
    if (!document2) return;
    var _styleProps = _objectSpread$2(_objectSpread$2({}, props), _props);
    var _name = _styleProps.name || name, _id2 = _styleProps.id || id, _nonce = _styleProps.nonce || nonce;
    styleRef.value = document2.querySelector('style[data-primevue-style-id="'.concat(_name, '"]')) || document2.getElementById(_id2) || document2.createElement("style");
    if (!styleRef.value.isConnected) {
      cssRef.value = _css || css3;
      A(styleRef.value, {
        type: "text/css",
        id: _id2,
        media,
        nonce: _nonce
      });
      first ? document2.head.prepend(styleRef.value) : document2.head.appendChild(styleRef.value);
      _t(styleRef.value, "data-primevue-style-id", _name);
      A(styleRef.value, _styleProps);
      styleRef.value.onload = function(event) {
        return onStyleLoaded === null || onStyleLoaded === void 0 ? void 0 : onStyleLoaded(event, {
          name: _name
        });
      };
      onStyleMounted === null || onStyleMounted === void 0 || onStyleMounted(_name);
    }
    if (isLoaded.value) return;
    stop = watch(cssRef, function(value) {
      styleRef.value.textContent = value;
      onStyleUpdated === null || onStyleUpdated === void 0 || onStyleUpdated(_name);
    }, {
      immediate: true
    });
    isLoaded.value = true;
  };
  var unload = function unload2() {
    if (!document2 || !isLoaded.value) return;
    stop();
    T(styleRef.value) && document2.head.removeChild(styleRef.value);
    isLoaded.value = false;
    styleRef.value = null;
  };
  if (immediate && !manual) tryOnMounted(load2);
  return {
    id,
    name,
    el: styleRef,
    css: cssRef,
    unload,
    load: load2,
    isLoaded: readonly(isLoaded)
  };
}
function _typeof$1(o) {
  "@babel/helpers - typeof";
  return _typeof$1 = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(o2) {
    return typeof o2;
  } : function(o2) {
    return o2 && "function" == typeof Symbol && o2.constructor === Symbol && o2 !== Symbol.prototype ? "symbol" : typeof o2;
  }, _typeof$1(o);
}
var _templateObject, _templateObject2, _templateObject3, _templateObject4;
function _slicedToArray(r, e) {
  return _arrayWithHoles(r) || _iterableToArrayLimit(r, e) || _unsupportedIterableToArray(r, e) || _nonIterableRest();
}
function _nonIterableRest() {
  throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.");
}
function _unsupportedIterableToArray(r, a2) {
  if (r) {
    if ("string" == typeof r) return _arrayLikeToArray(r, a2);
    var t = {}.toString.call(r).slice(8, -1);
    return "Object" === t && r.constructor && (t = r.constructor.name), "Map" === t || "Set" === t ? Array.from(r) : "Arguments" === t || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(t) ? _arrayLikeToArray(r, a2) : void 0;
  }
}
function _arrayLikeToArray(r, a2) {
  (null == a2 || a2 > r.length) && (a2 = r.length);
  for (var e = 0, n = Array(a2); e < a2; e++) n[e] = r[e];
  return n;
}
function _iterableToArrayLimit(r, l2) {
  var t = null == r ? null : "undefined" != typeof Symbol && r[Symbol.iterator] || r["@@iterator"];
  if (null != t) {
    var e, n, i2, u, a2 = [], f = true, o = false;
    try {
      if (i2 = (t = t.call(r)).next, 0 === l2) ;
      else for (; !(f = (e = i2.call(t)).done) && (a2.push(e.value), a2.length !== l2); f = true) ;
    } catch (r2) {
      o = true, n = r2;
    } finally {
      try {
        if (!f && null != t["return"] && (u = t["return"](), Object(u) !== u)) return;
      } finally {
        if (o) throw n;
      }
    }
    return a2;
  }
}
function _arrayWithHoles(r) {
  if (Array.isArray(r)) return r;
}
function ownKeys$1(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread$1(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys$1(Object(t), true).forEach(function(r2) {
      _defineProperty$1(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys$1(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function _defineProperty$1(e, r, t) {
  return (r = _toPropertyKey$1(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e;
}
function _toPropertyKey$1(t) {
  var i2 = _toPrimitive$1(t, "string");
  return "symbol" == _typeof$1(i2) ? i2 : i2 + "";
}
function _toPrimitive$1(t, r) {
  if ("object" != _typeof$1(t) || !t) return t;
  var e = t[Symbol.toPrimitive];
  if (void 0 !== e) {
    var i2 = e.call(t, r);
    if ("object" != _typeof$1(i2)) return i2;
    throw new TypeError("@@toPrimitive must return a primitive value.");
  }
  return ("string" === r ? String : Number)(t);
}
function _taggedTemplateLiteral(e, t) {
  return t || (t = e.slice(0)), Object.freeze(Object.defineProperties(e, { raw: { value: Object.freeze(t) } }));
}
var css = function css2(_ref) {
  var dt2 = _ref.dt;
  return "\n.p-hidden-accessible {\n    border: 0;\n    clip: rect(0 0 0 0);\n    height: 1px;\n    margin: -1px;\n    opacity: 0;\n    overflow: hidden;\n    padding: 0;\n    pointer-events: none;\n    position: absolute;\n    white-space: nowrap;\n    width: 1px;\n}\n\n.p-overflow-hidden {\n    overflow: hidden;\n    padding-right: ".concat(dt2("scrollbar.width"), ";\n}\n");
};
var classes = {};
var inlineStyles = {};
var BaseStyle = {
  name: "base",
  css,
  style,
  classes,
  inlineStyles,
  load: function load(style2) {
    var options = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
    var transform = arguments.length > 2 && arguments[2] !== void 0 ? arguments[2] : function(cs) {
      return cs;
    };
    var computedStyle = transform(ar(_templateObject || (_templateObject = _taggedTemplateLiteral(["", ""])), style2));
    return s$1(computedStyle) ? useStyle(Y$1(computedStyle), _objectSpread$1({
      name: this.name
    }, options)) : {};
  },
  loadCSS: function loadCSS() {
    var options = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
    return this.load(this.css, options);
  },
  loadStyle: function loadStyle() {
    var _this = this;
    var options = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : {};
    var style2 = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : "";
    return this.load(this.style, options, function() {
      var computedStyle = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : "";
      return S.transformCSS(options.name || _this.name, "".concat(computedStyle).concat(ar(_templateObject2 || (_templateObject2 = _taggedTemplateLiteral(["", ""])), style2)));
    });
  },
  getCommonTheme: function getCommonTheme(params) {
    return S.getCommon(this.name, params);
  },
  getComponentTheme: function getComponentTheme(params) {
    return S.getComponent(this.name, params);
  },
  getDirectiveTheme: function getDirectiveTheme(params) {
    return S.getDirective(this.name, params);
  },
  getPresetTheme: function getPresetTheme(preset, selector, params) {
    return S.getCustomPreset(this.name, preset, selector, params);
  },
  getLayerOrderThemeCSS: function getLayerOrderThemeCSS() {
    return S.getLayerOrderCSS(this.name);
  },
  getStyleSheet: function getStyleSheet() {
    var extendedCSS = arguments.length > 0 && arguments[0] !== void 0 ? arguments[0] : "";
    var props = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
    if (this.css) {
      var _css = m(this.css, {
        dt: E
      }) || "";
      var _style = Y$1(ar(_templateObject3 || (_templateObject3 = _taggedTemplateLiteral(["", "", ""])), _css, extendedCSS));
      var _props = Object.entries(props).reduce(function(acc, _ref2) {
        var _ref3 = _slicedToArray(_ref2, 2), k2 = _ref3[0], v2 = _ref3[1];
        return acc.push("".concat(k2, '="').concat(v2, '"')) && acc;
      }, []).join(" ");
      return s$1(_style) ? '<style type="text/css" data-primevue-style-id="'.concat(this.name, '" ').concat(_props, ">").concat(_style, "</style>") : "";
    }
    return "";
  },
  getCommonThemeStyleSheet: function getCommonThemeStyleSheet(params) {
    var props = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
    return S.getCommonStyleSheet(this.name, params, props);
  },
  getThemeStyleSheet: function getThemeStyleSheet(params) {
    var props = arguments.length > 1 && arguments[1] !== void 0 ? arguments[1] : {};
    var css3 = [S.getStyleSheet(this.name, params, props)];
    if (this.style) {
      var name = this.name === "base" ? "global-style" : "".concat(this.name, "-style");
      var _css = ar(_templateObject4 || (_templateObject4 = _taggedTemplateLiteral(["", ""])), m(this.style, {
        dt: E
      }));
      var _style = Y$1(S.transformCSS(name, _css));
      var _props = Object.entries(props).reduce(function(acc, _ref4) {
        var _ref5 = _slicedToArray(_ref4, 2), k2 = _ref5[0], v2 = _ref5[1];
        return acc.push("".concat(k2, '="').concat(v2, '"')) && acc;
      }, []).join(" ");
      s$1(_style) && css3.push('<style type="text/css" data-primevue-style-id="'.concat(name, '" ').concat(_props, ">").concat(_style, "</style>"));
    }
    return css3.join("");
  },
  extend: function extend2(inStyle) {
    return _objectSpread$1(_objectSpread$1({}, this), {}, {
      css: void 0,
      style: void 0
    }, inStyle);
  }
};
var PrimeVueService = s();
function _typeof(o) {
  "@babel/helpers - typeof";
  return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(o2) {
    return typeof o2;
  } : function(o2) {
    return o2 && "function" == typeof Symbol && o2.constructor === Symbol && o2 !== Symbol.prototype ? "symbol" : typeof o2;
  }, _typeof(o);
}
function ownKeys(e, r) {
  var t = Object.keys(e);
  if (Object.getOwnPropertySymbols) {
    var o = Object.getOwnPropertySymbols(e);
    r && (o = o.filter(function(r2) {
      return Object.getOwnPropertyDescriptor(e, r2).enumerable;
    })), t.push.apply(t, o);
  }
  return t;
}
function _objectSpread(e) {
  for (var r = 1; r < arguments.length; r++) {
    var t = null != arguments[r] ? arguments[r] : {};
    r % 2 ? ownKeys(Object(t), true).forEach(function(r2) {
      _defineProperty(e, r2, t[r2]);
    }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function(r2) {
      Object.defineProperty(e, r2, Object.getOwnPropertyDescriptor(t, r2));
    });
  }
  return e;
}
function _defineProperty(e, r, t) {
  return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e;
}
function _toPropertyKey(t) {
  var i2 = _toPrimitive(t, "string");
  return "symbol" == _typeof(i2) ? i2 : i2 + "";
}
function _toPrimitive(t, r) {
  if ("object" != _typeof(t) || !t) return t;
  var e = t[Symbol.toPrimitive];
  if (void 0 !== e) {
    var i2 = e.call(t, r);
    if ("object" != _typeof(i2)) return i2;
    throw new TypeError("@@toPrimitive must return a primitive value.");
  }
  return ("string" === r ? String : Number)(t);
}
var defaultOptions = {
  ripple: false,
  inputStyle: null,
  inputVariant: null,
  locale: {
    startsWith: "Starts with",
    contains: "Contains",
    notContains: "Not contains",
    endsWith: "Ends with",
    equals: "Equals",
    notEquals: "Not equals",
    noFilter: "No Filter",
    lt: "Less than",
    lte: "Less than or equal to",
    gt: "Greater than",
    gte: "Greater than or equal to",
    dateIs: "Date is",
    dateIsNot: "Date is not",
    dateBefore: "Date is before",
    dateAfter: "Date is after",
    clear: "Clear",
    apply: "Apply",
    matchAll: "Match All",
    matchAny: "Match Any",
    addRule: "Add Rule",
    removeRule: "Remove Rule",
    accept: "Yes",
    reject: "No",
    choose: "Choose",
    upload: "Upload",
    cancel: "Cancel",
    completed: "Completed",
    pending: "Pending",
    fileSizeTypes: ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"],
    dayNames: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    dayNamesShort: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    dayNamesMin: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"],
    monthNames: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    monthNamesShort: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    chooseYear: "Choose Year",
    chooseMonth: "Choose Month",
    chooseDate: "Choose Date",
    prevDecade: "Previous Decade",
    nextDecade: "Next Decade",
    prevYear: "Previous Year",
    nextYear: "Next Year",
    prevMonth: "Previous Month",
    nextMonth: "Next Month",
    prevHour: "Previous Hour",
    nextHour: "Next Hour",
    prevMinute: "Previous Minute",
    nextMinute: "Next Minute",
    prevSecond: "Previous Second",
    nextSecond: "Next Second",
    am: "am",
    pm: "pm",
    today: "Today",
    weekHeader: "Wk",
    firstDayOfWeek: 0,
    showMonthAfterYear: false,
    dateFormat: "mm/dd/yy",
    weak: "Weak",
    medium: "Medium",
    strong: "Strong",
    passwordPrompt: "Enter a password",
    emptyFilterMessage: "No results found",
    searchMessage: "{0} results are available",
    selectionMessage: "{0} items selected",
    emptySelectionMessage: "No selected item",
    emptySearchMessage: "No results found",
    fileChosenMessage: "{0} files",
    noFileChosenMessage: "No file chosen",
    emptyMessage: "No available options",
    aria: {
      trueLabel: "True",
      falseLabel: "False",
      nullLabel: "Not Selected",
      star: "1 star",
      stars: "{star} stars",
      selectAll: "All items selected",
      unselectAll: "All items unselected",
      close: "Close",
      previous: "Previous",
      next: "Next",
      navigation: "Navigation",
      scrollTop: "Scroll Top",
      moveTop: "Move Top",
      moveUp: "Move Up",
      moveDown: "Move Down",
      moveBottom: "Move Bottom",
      moveToTarget: "Move to Target",
      moveToSource: "Move to Source",
      moveAllToTarget: "Move All to Target",
      moveAllToSource: "Move All to Source",
      pageLabel: "Page {page}",
      firstPageLabel: "First Page",
      lastPageLabel: "Last Page",
      nextPageLabel: "Next Page",
      prevPageLabel: "Previous Page",
      rowsPerPageLabel: "Rows per page",
      jumpToPageDropdownLabel: "Jump to Page Dropdown",
      jumpToPageInputLabel: "Jump to Page Input",
      selectRow: "Row Selected",
      unselectRow: "Row Unselected",
      expandRow: "Row Expanded",
      collapseRow: "Row Collapsed",
      showFilterMenu: "Show Filter Menu",
      hideFilterMenu: "Hide Filter Menu",
      filterOperator: "Filter Operator",
      filterConstraint: "Filter Constraint",
      editRow: "Row Edit",
      saveEdit: "Save Edit",
      cancelEdit: "Cancel Edit",
      listView: "List View",
      gridView: "Grid View",
      slide: "Slide",
      slideNumber: "{slideNumber}",
      zoomImage: "Zoom Image",
      zoomIn: "Zoom In",
      zoomOut: "Zoom Out",
      rotateRight: "Rotate Right",
      rotateLeft: "Rotate Left",
      listLabel: "Option List"
    }
  },
  filterMatchModeOptions: {
    text: [FilterMatchMode.STARTS_WITH, FilterMatchMode.CONTAINS, FilterMatchMode.NOT_CONTAINS, FilterMatchMode.ENDS_WITH, FilterMatchMode.EQUALS, FilterMatchMode.NOT_EQUALS],
    numeric: [FilterMatchMode.EQUALS, FilterMatchMode.NOT_EQUALS, FilterMatchMode.LESS_THAN, FilterMatchMode.LESS_THAN_OR_EQUAL_TO, FilterMatchMode.GREATER_THAN, FilterMatchMode.GREATER_THAN_OR_EQUAL_TO],
    date: [FilterMatchMode.DATE_IS, FilterMatchMode.DATE_IS_NOT, FilterMatchMode.DATE_BEFORE, FilterMatchMode.DATE_AFTER]
  },
  zIndex: {
    modal: 1100,
    overlay: 1e3,
    menu: 1e3,
    tooltip: 1100
  },
  theme: void 0,
  unstyled: false,
  pt: void 0,
  ptOptions: {
    mergeSections: true,
    mergeProps: false
  },
  csp: {
    nonce: void 0
  }
};
var PrimeVueSymbol = Symbol();
function setup(app2, options) {
  var PrimeVue2 = {
    config: reactive(options)
  };
  app2.config.globalProperties.$primevue = PrimeVue2;
  app2.provide(PrimeVueSymbol, PrimeVue2);
  clearConfig();
  setupConfig(app2, PrimeVue2);
  return PrimeVue2;
}
var stopWatchers = [];
function clearConfig() {
  N.clear();
  stopWatchers.forEach(function(fn) {
    return fn === null || fn === void 0 ? void 0 : fn();
  });
  stopWatchers = [];
}
function setupConfig(app2, PrimeVue2) {
  var isThemeChanged = ref(false);
  var loadCommonTheme = function loadCommonTheme2() {
    var _PrimeVue$config;
    if (((_PrimeVue$config = PrimeVue2.config) === null || _PrimeVue$config === void 0 ? void 0 : _PrimeVue$config.theme) === "none") return;
    if (!S.isStyleNameLoaded("common")) {
      var _BaseStyle$getCommonT, _PrimeVue$config2;
      var _ref = ((_BaseStyle$getCommonT = BaseStyle.getCommonTheme) === null || _BaseStyle$getCommonT === void 0 ? void 0 : _BaseStyle$getCommonT.call(BaseStyle)) || {}, primitive = _ref.primitive, semantic = _ref.semantic, global2 = _ref.global, style2 = _ref.style;
      var styleOptions = {
        nonce: (_PrimeVue$config2 = PrimeVue2.config) === null || _PrimeVue$config2 === void 0 || (_PrimeVue$config2 = _PrimeVue$config2.csp) === null || _PrimeVue$config2 === void 0 ? void 0 : _PrimeVue$config2.nonce
      };
      BaseStyle.load(primitive === null || primitive === void 0 ? void 0 : primitive.css, _objectSpread({
        name: "primitive-variables"
      }, styleOptions));
      BaseStyle.load(semantic === null || semantic === void 0 ? void 0 : semantic.css, _objectSpread({
        name: "semantic-variables"
      }, styleOptions));
      BaseStyle.load(global2 === null || global2 === void 0 ? void 0 : global2.css, _objectSpread({
        name: "global-variables"
      }, styleOptions));
      BaseStyle.loadStyle(_objectSpread({
        name: "global-style"
      }, styleOptions), style2);
      S.setLoadedStyleName("common");
    }
  };
  N.on("theme:change", function(newTheme) {
    if (!isThemeChanged.value) {
      app2.config.globalProperties.$primevue.config.theme = newTheme;
      isThemeChanged.value = true;
    }
  });
  var stopConfigWatcher = watch(PrimeVue2.config, function(newValue, oldValue) {
    PrimeVueService.emit("config:change", {
      newValue,
      oldValue
    });
  }, {
    immediate: true,
    deep: true
  });
  var stopRippleWatcher = watch(function() {
    return PrimeVue2.config.ripple;
  }, function(newValue, oldValue) {
    PrimeVueService.emit("config:ripple:change", {
      newValue,
      oldValue
    });
  }, {
    immediate: true,
    deep: true
  });
  var stopThemeWatcher = watch(function() {
    return PrimeVue2.config.theme;
  }, function(newValue, oldValue) {
    if (!isThemeChanged.value) {
      S.setTheme(newValue);
    }
    if (!PrimeVue2.config.unstyled) {
      loadCommonTheme();
    }
    isThemeChanged.value = false;
    PrimeVueService.emit("config:theme:change", {
      newValue,
      oldValue
    });
  }, {
    immediate: true,
    deep: false
  });
  var stopUnstyledWatcher = watch(function() {
    return PrimeVue2.config.unstyled;
  }, function(newValue, oldValue) {
    if (!newValue && PrimeVue2.config.theme) {
      loadCommonTheme();
    }
    PrimeVueService.emit("config:unstyled:change", {
      newValue,
      oldValue
    });
  }, {
    immediate: true,
    deep: true
  });
  stopWatchers.push(stopConfigWatcher);
  stopWatchers.push(stopRippleWatcher);
  stopWatchers.push(stopThemeWatcher);
  stopWatchers.push(stopUnstyledWatcher);
}
var PrimeVue = {
  install: function install(app2, options) {
    var configOptions = H(defaultOptions, options);
    setup(app2, configOptions);
  }
};
const _hoisted_1$k = { class: "filter-chip__text" };
const _hoisted_2$g = {
  key: 0,
  class: "filter-chip__count"
};
const _sfc_main$l = /* @__PURE__ */ defineComponent({
  __name: "FilterChip",
  props: {
    label: {},
    count: {},
    variant: {},
    removable: { type: Boolean }
  },
  emits: ["remove"],
  setup(__props) {
    const props = __props;
    const variantClass = computed(() => {
      return props.variant ? `filter-chip--${props.variant}` : "";
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("span", {
        class: normalizeClass(["filter-chip", variantClass.value])
      }, [
        createBaseVNode("span", _hoisted_1$k, toDisplayString(__props.label), 1),
        __props.count !== void 0 ? (openBlock(), createElementBlock("span", _hoisted_2$g, "(" + toDisplayString(__props.count) + ")", 1)) : createCommentVNode("", true),
        __props.removable ? (openBlock(), createElementBlock("button", {
          key: 1,
          class: "filter-chip__remove",
          onClick: _cache[0] || (_cache[0] = withModifiers(($event) => _ctx.$emit("remove"), ["stop"])),
          type: "button"
        }, " × ")) : createCommentVNode("", true)
      ], 2);
    };
  }
});
const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};
const FilterChip = /* @__PURE__ */ _export_sfc(_sfc_main$l, [["__scopeId", "data-v-7e36267d"]]);
const _sfc_main$k = /* @__PURE__ */ defineComponent({
  __name: "EditButton",
  emits: ["click"],
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("button", {
        class: "edit-button",
        type: "button",
        onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("click"))
      }, [..._cache[1] || (_cache[1] = [
        createBaseVNode("svg", {
          class: "edit-button__icon",
          viewBox: "0 0 16 16",
          fill: "currentColor"
        }, [
          createBaseVNode("path", { d: "M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5L13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293l6.5-6.5zm-9.761 5.175l-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z" })
        ], -1),
        createBaseVNode("span", { class: "edit-button__text" }, "Edit", -1)
      ])]);
    };
  }
});
const EditButton = /* @__PURE__ */ _export_sfc(_sfc_main$k, [["__scopeId", "data-v-8da8aa4b"]]);
const _hoisted_1$j = { class: "section" };
const _hoisted_2$f = { class: "section__header" };
const _hoisted_3$d = { class: "section__content" };
const _hoisted_4$c = {
  key: 0,
  class: "section__placeholder"
};
const _hoisted_5$a = {
  key: 1,
  class: "section__chips"
};
const _sfc_main$j = /* @__PURE__ */ defineComponent({
  __name: "BaseModelSection",
  props: {
    selected: {},
    models: {}
  },
  emits: ["edit"],
  setup(__props) {
    const props = __props;
    const getCount = (name) => {
      const model = props.models.find((m2) => m2.name === name);
      return model == null ? void 0 : model.count;
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$j, [
        createBaseVNode("div", _hoisted_2$f, [
          _cache[1] || (_cache[1] = createBaseVNode("span", { class: "section__title" }, "BASE MODEL", -1)),
          createVNode(EditButton, {
            onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("edit"))
          })
        ]),
        createBaseVNode("div", _hoisted_3$d, [
          __props.selected.length === 0 ? (openBlock(), createElementBlock("div", _hoisted_4$c, " All models ")) : (openBlock(), createElementBlock("div", _hoisted_5$a, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(__props.selected, (name) => {
              return openBlock(), createBlock(FilterChip, {
                key: name,
                label: name,
                count: getCount(name),
                variant: "neutral"
              }, null, 8, ["label", "count"]);
            }), 128))
          ]))
        ])
      ]);
    };
  }
});
const BaseModelSection = /* @__PURE__ */ _export_sfc(_sfc_main$j, [["__scopeId", "data-v-12f059e2"]]);
const _hoisted_1$i = { class: "section" };
const _hoisted_2$e = { class: "section__columns" };
const _hoisted_3$c = { class: "section__column" };
const _hoisted_4$b = { class: "section__column-header" };
const _hoisted_5$9 = { class: "section__column-content" };
const _hoisted_6$9 = {
  key: 0,
  class: "section__empty"
};
const _hoisted_7$7 = {
  key: 1,
  class: "section__chips"
};
const _hoisted_8$6 = { class: "section__column" };
const _hoisted_9$4 = { class: "section__column-header" };
const _hoisted_10$4 = { class: "section__column-content" };
const _hoisted_11$3 = {
  key: 0,
  class: "section__empty"
};
const _hoisted_12$3 = {
  key: 1,
  class: "section__chips"
};
const _sfc_main$i = /* @__PURE__ */ defineComponent({
  __name: "TagsSection",
  props: {
    includeTags: {},
    excludeTags: {}
  },
  emits: ["edit-include", "edit-exclude"],
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$i, [
        _cache[4] || (_cache[4] = createBaseVNode("div", { class: "section__header" }, [
          createBaseVNode("span", { class: "section__title" }, "TAGS")
        ], -1)),
        createBaseVNode("div", _hoisted_2$e, [
          createBaseVNode("div", _hoisted_3$c, [
            createBaseVNode("div", _hoisted_4$b, [
              _cache[2] || (_cache[2] = createBaseVNode("span", { class: "section__column-title section__column-title--include" }, "INCLUDE", -1)),
              createVNode(EditButton, {
                onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("edit-include"))
              })
            ]),
            createBaseVNode("div", _hoisted_5$9, [
              __props.includeTags.length === 0 ? (openBlock(), createElementBlock("div", _hoisted_6$9, " None ")) : (openBlock(), createElementBlock("div", _hoisted_7$7, [
                (openBlock(true), createElementBlock(Fragment, null, renderList(__props.includeTags, (tag) => {
                  return openBlock(), createBlock(FilterChip, {
                    key: tag,
                    label: tag,
                    variant: "include"
                  }, null, 8, ["label"]);
                }), 128))
              ]))
            ])
          ]),
          createBaseVNode("div", _hoisted_8$6, [
            createBaseVNode("div", _hoisted_9$4, [
              _cache[3] || (_cache[3] = createBaseVNode("span", { class: "section__column-title section__column-title--exclude" }, "EXCLUDE", -1)),
              createVNode(EditButton, {
                onClick: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("edit-exclude"))
              })
            ]),
            createBaseVNode("div", _hoisted_10$4, [
              __props.excludeTags.length === 0 ? (openBlock(), createElementBlock("div", _hoisted_11$3, " None ")) : (openBlock(), createElementBlock("div", _hoisted_12$3, [
                (openBlock(true), createElementBlock(Fragment, null, renderList(__props.excludeTags, (tag) => {
                  return openBlock(), createBlock(FilterChip, {
                    key: tag,
                    label: tag,
                    variant: "exclude"
                  }, null, 8, ["label"]);
                }), 128))
              ]))
            ])
          ])
        ])
      ]);
    };
  }
});
const TagsSection = /* @__PURE__ */ _export_sfc(_sfc_main$i, [["__scopeId", "data-v-b869b780"]]);
const _hoisted_1$h = { class: "section" };
const _hoisted_2$d = { class: "section__columns" };
const _hoisted_3$b = { class: "section__column" };
const _hoisted_4$a = { class: "section__column-header" };
const _hoisted_5$8 = { class: "section__content" };
const _hoisted_6$8 = {
  key: 0,
  class: "section__paths"
};
const _hoisted_7$6 = {
  key: 1,
  class: "section__empty"
};
const _hoisted_8$5 = { class: "section__column" };
const _hoisted_9$3 = { class: "section__column-header" };
const _hoisted_10$3 = { class: "section__content" };
const _hoisted_11$2 = {
  key: 0,
  class: "section__paths"
};
const _hoisted_12$2 = {
  key: 1,
  class: "section__empty"
};
const _sfc_main$h = /* @__PURE__ */ defineComponent({
  __name: "FoldersSection",
  props: {
    includeFolders: {},
    excludeFolders: {}
  },
  emits: ["update:includeFolders", "update:excludeFolders", "edit-include", "edit-exclude"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const truncatePath = (path) => {
      if (path.length <= 20) return path;
      return "..." + path.slice(-17);
    };
    const removeInclude = (path) => {
      emit2("update:includeFolders", props.includeFolders.filter((p2) => p2 !== path));
    };
    const removeExclude = (path) => {
      emit2("update:excludeFolders", props.excludeFolders.filter((p2) => p2 !== path));
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$h, [
        _cache[6] || (_cache[6] = createBaseVNode("div", { class: "section__header" }, [
          createBaseVNode("span", { class: "section__title" }, "FOLDERS")
        ], -1)),
        createBaseVNode("div", _hoisted_2$d, [
          createBaseVNode("div", _hoisted_3$b, [
            createBaseVNode("div", _hoisted_4$a, [
              _cache[3] || (_cache[3] = createBaseVNode("span", { class: "section__column-title section__column-title--include" }, "INCLUDE", -1)),
              createBaseVNode("button", {
                type: "button",
                class: "section__edit-btn section__edit-btn--include",
                onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("edit-include"))
              }, [..._cache[2] || (_cache[2] = [
                createBaseVNode("svg", {
                  viewBox: "0 0 16 16",
                  fill: "currentColor"
                }, [
                  createBaseVNode("path", { d: "M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z" })
                ], -1)
              ])])
            ]),
            createBaseVNode("div", _hoisted_5$8, [
              __props.includeFolders.length > 0 ? (openBlock(), createElementBlock("div", _hoisted_6$8, [
                (openBlock(true), createElementBlock(Fragment, null, renderList(__props.includeFolders, (path) => {
                  return openBlock(), createBlock(FilterChip, {
                    key: path,
                    label: truncatePath(path),
                    variant: "path",
                    removable: "",
                    onRemove: ($event) => removeInclude(path)
                  }, null, 8, ["label", "onRemove"]);
                }), 128))
              ])) : (openBlock(), createElementBlock("div", _hoisted_7$6, " No folders selected "))
            ])
          ]),
          createBaseVNode("div", _hoisted_8$5, [
            createBaseVNode("div", _hoisted_9$3, [
              _cache[5] || (_cache[5] = createBaseVNode("span", { class: "section__column-title section__column-title--exclude" }, "EXCLUDE", -1)),
              createBaseVNode("button", {
                type: "button",
                class: "section__edit-btn section__edit-btn--exclude",
                onClick: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("edit-exclude"))
              }, [..._cache[4] || (_cache[4] = [
                createBaseVNode("svg", {
                  viewBox: "0 0 16 16",
                  fill: "currentColor"
                }, [
                  createBaseVNode("path", { d: "M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5l1.647-1.646a.5.5 0 0 0 0-.708l-3-3zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z" })
                ], -1)
              ])])
            ]),
            createBaseVNode("div", _hoisted_10$3, [
              __props.excludeFolders.length > 0 ? (openBlock(), createElementBlock("div", _hoisted_11$2, [
                (openBlock(true), createElementBlock(Fragment, null, renderList(__props.excludeFolders, (path) => {
                  return openBlock(), createBlock(FilterChip, {
                    key: path,
                    label: truncatePath(path),
                    variant: "path",
                    removable: "",
                    onRemove: ($event) => removeExclude(path)
                  }, null, 8, ["label", "onRemove"]);
                }), 128))
              ])) : (openBlock(), createElementBlock("div", _hoisted_12$2, " No folders selected "))
            ])
          ])
        ])
      ]);
    };
  }
});
const FoldersSection = /* @__PURE__ */ _export_sfc(_sfc_main$h, [["__scopeId", "data-v-af9caf84"]]);
const _hoisted_1$g = { class: "section" };
const _hoisted_2$c = { class: "section__toggles" };
const _hoisted_3$a = { class: "toggle-item" };
const _hoisted_4$9 = ["aria-checked"];
const _hoisted_5$7 = { class: "toggle-item" };
const _hoisted_6$7 = ["aria-checked"];
const _sfc_main$g = /* @__PURE__ */ defineComponent({
  __name: "LicenseSection",
  props: {
    noCreditRequired: { type: Boolean },
    allowSelling: { type: Boolean }
  },
  emits: ["update:noCreditRequired", "update:allowSelling"],
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$g, [
        _cache[6] || (_cache[6] = createBaseVNode("div", { class: "section__header" }, [
          createBaseVNode("span", { class: "section__title" }, "LICENSE")
        ], -1)),
        createBaseVNode("div", _hoisted_2$c, [
          createBaseVNode("label", _hoisted_3$a, [
            _cache[3] || (_cache[3] = createBaseVNode("span", { class: "toggle-item__label" }, "No Credit Required", -1)),
            createBaseVNode("button", {
              type: "button",
              class: normalizeClass(["toggle-switch", { "toggle-switch--active": __props.noCreditRequired }]),
              onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("update:noCreditRequired", !__props.noCreditRequired)),
              role: "switch",
              "aria-checked": __props.noCreditRequired
            }, [..._cache[2] || (_cache[2] = [
              createBaseVNode("span", { class: "toggle-switch__track" }, null, -1),
              createBaseVNode("span", { class: "toggle-switch__thumb" }, null, -1)
            ])], 10, _hoisted_4$9)
          ]),
          createBaseVNode("label", _hoisted_5$7, [
            _cache[5] || (_cache[5] = createBaseVNode("span", { class: "toggle-item__label" }, "Allow Selling", -1)),
            createBaseVNode("button", {
              type: "button",
              class: normalizeClass(["toggle-switch", { "toggle-switch--active": __props.allowSelling }]),
              onClick: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("update:allowSelling", !__props.allowSelling)),
              role: "switch",
              "aria-checked": __props.allowSelling
            }, [..._cache[4] || (_cache[4] = [
              createBaseVNode("span", { class: "toggle-switch__track" }, null, -1),
              createBaseVNode("span", { class: "toggle-switch__thumb" }, null, -1)
            ])], 10, _hoisted_6$7)
          ])
        ])
      ]);
    };
  }
});
const LicenseSection = /* @__PURE__ */ _export_sfc(_sfc_main$g, [["__scopeId", "data-v-dea4adf6"]]);
const _hoisted_1$f = { class: "preview" };
const _hoisted_2$b = { class: "preview__title" };
const _hoisted_3$9 = ["disabled"];
const _hoisted_4$8 = {
  key: 0,
  class: "preview__tooltip"
};
const _hoisted_5$6 = { class: "preview__tooltip-content" };
const _hoisted_6$6 = ["src"];
const _hoisted_7$5 = {
  key: 1,
  class: "preview__thumb preview__thumb--placeholder"
};
const _hoisted_8$4 = { class: "preview__name" };
const _hoisted_9$2 = {
  key: 0,
  class: "preview__more"
};
const _hoisted_10$2 = {
  key: 0,
  class: "preview__empty"
};
const _sfc_main$f = /* @__PURE__ */ defineComponent({
  __name: "LoraPoolPreview",
  props: {
    items: {},
    matchCount: {},
    isLoading: { type: Boolean }
  },
  emits: ["refresh"],
  setup(__props) {
    const showTooltip = ref(false);
    const onImageError = (event) => {
      const img = event.target;
      img.style.display = "none";
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$f, [
        createBaseVNode("div", {
          class: "preview__header",
          onMouseenter: _cache[1] || (_cache[1] = ($event) => showTooltip.value = true),
          onMouseleave: _cache[2] || (_cache[2] = ($event) => showTooltip.value = false)
        }, [
          createBaseVNode("span", _hoisted_2$b, "Matching LoRAs: " + toDisplayString(__props.matchCount.toLocaleString()), 1),
          createBaseVNode("button", {
            type: "button",
            class: normalizeClass(["preview__refresh", { "preview__refresh--loading": __props.isLoading }]),
            onClick: _cache[0] || (_cache[0] = withModifiers(($event) => _ctx.$emit("refresh"), ["stop"])),
            disabled: __props.isLoading
          }, [..._cache[3] || (_cache[3] = [
            createBaseVNode("svg", {
              class: "preview__refresh-icon",
              viewBox: "0 0 16 16",
              fill: "currentColor"
            }, [
              createBaseVNode("path", { d: "M11.534 7h3.932a.25.25 0 0 1 .192.41l-1.966 2.36a.25.25 0 0 1-.384 0l-1.966-2.36a.25.25 0 0 1 .192-.41zm-11 2h3.932a.25.25 0 0 0 .192-.41L2.692 6.23a.25.25 0 0 0-.384 0L.342 8.59A.25.25 0 0 0 .534 9z" }),
              createBaseVNode("path", {
                "fill-rule": "evenodd",
                d: "M8 3c-1.552 0-2.94.707-3.857 1.818a.5.5 0 1 1-.771-.636A6.002 6.002 0 0 1 13.917 7H12.9A5.002 5.002 0 0 0 8 3zM3.1 9a5.002 5.002 0 0 0 8.757 2.182.5.5 0 1 1 .771.636A6.002 6.002 0 0 1 2.083 9H3.1z"
              })
            ], -1)
          ])], 10, _hoisted_3$9)
        ], 32),
        createVNode(Transition, { name: "tooltip" }, {
          default: withCtx(() => [
            showTooltip.value && __props.items.length > 0 ? (openBlock(), createElementBlock("div", _hoisted_4$8, [
              createBaseVNode("div", _hoisted_5$6, [
                (openBlock(true), createElementBlock(Fragment, null, renderList(__props.items.slice(0, 5), (item) => {
                  return openBlock(), createElementBlock("div", {
                    key: item.file_path,
                    class: "preview__item"
                  }, [
                    item.preview_url ? (openBlock(), createElementBlock("img", {
                      key: 0,
                      src: item.preview_url,
                      class: "preview__thumb",
                      onError: onImageError
                    }, null, 40, _hoisted_6$6)) : (openBlock(), createElementBlock("div", _hoisted_7$5, [..._cache[4] || (_cache[4] = [
                      createBaseVNode("svg", {
                        viewBox: "0 0 16 16",
                        fill: "currentColor"
                      }, [
                        createBaseVNode("path", { d: "M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z" }),
                        createBaseVNode("path", { d: "M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z" })
                      ], -1)
                    ])])),
                    createBaseVNode("span", _hoisted_8$4, toDisplayString(item.model_name || item.file_name), 1)
                  ]);
                }), 128)),
                __props.matchCount > 5 ? (openBlock(), createElementBlock("div", _hoisted_9$2, " +" + toDisplayString((__props.matchCount - 5).toLocaleString()) + " more ", 1)) : createCommentVNode("", true)
              ])
            ])) : createCommentVNode("", true)
          ]),
          _: 1
        }),
        __props.items.length === 0 && !__props.isLoading ? (openBlock(), createElementBlock("div", _hoisted_10$2, " No matching LoRAs ")) : createCommentVNode("", true)
      ]);
    };
  }
});
const LoraPoolPreview = /* @__PURE__ */ _export_sfc(_sfc_main$f, [["__scopeId", "data-v-6a4b50a1"]]);
const _hoisted_1$e = { class: "summary-view" };
const _hoisted_2$a = { class: "summary-view__filters" };
const _sfc_main$e = /* @__PURE__ */ defineComponent({
  __name: "LoraPoolSummaryView",
  props: {
    selectedBaseModels: {},
    availableBaseModels: {},
    includeTags: {},
    excludeTags: {},
    includeFolders: {},
    excludeFolders: {},
    noCreditRequired: { type: Boolean },
    allowSelling: { type: Boolean },
    previewItems: {},
    matchCount: {},
    isLoading: { type: Boolean }
  },
  emits: ["open-modal", "update:includeFolders", "update:excludeFolders", "update:noCreditRequired", "update:allowSelling", "refresh"],
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$e, [
        createBaseVNode("div", _hoisted_2$a, [
          createVNode(BaseModelSection, {
            selected: __props.selectedBaseModels,
            models: __props.availableBaseModels,
            onEdit: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("open-modal", "baseModels"))
          }, null, 8, ["selected", "models"]),
          createVNode(TagsSection, {
            "include-tags": __props.includeTags,
            "exclude-tags": __props.excludeTags,
            onEditInclude: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("open-modal", "includeTags")),
            onEditExclude: _cache[2] || (_cache[2] = ($event) => _ctx.$emit("open-modal", "excludeTags"))
          }, null, 8, ["include-tags", "exclude-tags"]),
          createVNode(FoldersSection, {
            "include-folders": __props.includeFolders,
            "exclude-folders": __props.excludeFolders,
            "onUpdate:includeFolders": _cache[3] || (_cache[3] = ($event) => _ctx.$emit("update:includeFolders", $event)),
            "onUpdate:excludeFolders": _cache[4] || (_cache[4] = ($event) => _ctx.$emit("update:excludeFolders", $event)),
            onEditInclude: _cache[5] || (_cache[5] = ($event) => _ctx.$emit("open-modal", "includeFolders")),
            onEditExclude: _cache[6] || (_cache[6] = ($event) => _ctx.$emit("open-modal", "excludeFolders"))
          }, null, 8, ["include-folders", "exclude-folders"]),
          createVNode(LicenseSection, {
            "no-credit-required": __props.noCreditRequired,
            "allow-selling": __props.allowSelling,
            "onUpdate:noCreditRequired": _cache[7] || (_cache[7] = ($event) => _ctx.$emit("update:noCreditRequired", $event)),
            "onUpdate:allowSelling": _cache[8] || (_cache[8] = ($event) => _ctx.$emit("update:allowSelling", $event))
          }, null, 8, ["no-credit-required", "allow-selling"])
        ]),
        createVNode(LoraPoolPreview, {
          items: __props.previewItems,
          "match-count": __props.matchCount,
          "is-loading": __props.isLoading,
          onRefresh: _cache[9] || (_cache[9] = ($event) => _ctx.$emit("refresh"))
        }, null, 8, ["items", "match-count", "is-loading"])
      ]);
    };
  }
});
const LoraPoolSummaryView = /* @__PURE__ */ _export_sfc(_sfc_main$e, [["__scopeId", "data-v-328e7526"]]);
const _hoisted_1$d = { class: "lora-pool-modal__header" };
const _hoisted_2$9 = { class: "lora-pool-modal__title-container" };
const _hoisted_3$8 = { class: "lora-pool-modal__title" };
const _hoisted_4$7 = {
  key: 0,
  class: "lora-pool-modal__subtitle"
};
const _hoisted_5$5 = {
  key: 0,
  class: "lora-pool-modal__search"
};
const _hoisted_6$5 = { class: "lora-pool-modal__body" };
const _sfc_main$d = /* @__PURE__ */ defineComponent({
  __name: "ModalWrapper",
  props: {
    visible: { type: Boolean },
    title: {},
    subtitle: {},
    modalClass: {}
  },
  emits: ["close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const close = () => {
      emit2("close");
    };
    const handleKeydown = (e) => {
      if (e.key === "Escape" && props.visible) {
        close();
      }
    };
    onMounted(() => {
      document.addEventListener("keydown", handleKeydown);
    });
    onUnmounted(() => {
      document.removeEventListener("keydown", handleKeydown);
    });
    watch(() => props.visible, (isVisible) => {
      if (isVisible) {
        document.body.style.overflow = "hidden";
      } else {
        document.body.style.overflow = "";
      }
    });
    return (_ctx, _cache) => {
      return openBlock(), createBlock(Teleport, { to: "body" }, [
        createVNode(Transition, { name: "modal" }, {
          default: withCtx(() => [
            __props.visible ? (openBlock(), createElementBlock("div", {
              key: 0,
              class: "lora-pool-modal-backdrop",
              onClick: withModifiers(close, ["self"]),
              onKeydown: withKeys(close, ["esc"])
            }, [
              createBaseVNode("div", {
                class: normalizeClass(["lora-pool-modal", __props.modalClass]),
                role: "dialog",
                "aria-modal": "true"
              }, [
                createBaseVNode("div", _hoisted_1$d, [
                  createBaseVNode("div", _hoisted_2$9, [
                    createBaseVNode("h3", _hoisted_3$8, toDisplayString(__props.title), 1),
                    __props.subtitle ? (openBlock(), createElementBlock("p", _hoisted_4$7, toDisplayString(__props.subtitle), 1)) : createCommentVNode("", true)
                  ]),
                  createBaseVNode("button", {
                    class: "lora-pool-modal__close",
                    onClick: close,
                    type: "button",
                    "aria-label": "Close"
                  }, " × ")
                ]),
                _ctx.$slots.search ? (openBlock(), createElementBlock("div", _hoisted_5$5, [
                  renderSlot(_ctx.$slots, "search", {}, void 0, true)
                ])) : createCommentVNode("", true),
                createBaseVNode("div", _hoisted_6$5, [
                  renderSlot(_ctx.$slots, "default", {}, void 0, true)
                ])
              ], 2)
            ], 32)) : createCommentVNode("", true)
          ]),
          _: 3
        })
      ]);
    };
  }
});
const ModalWrapper = /* @__PURE__ */ _export_sfc(_sfc_main$d, [["__scopeId", "data-v-fce76ca8"]]);
const _hoisted_1$c = { class: "search-container" };
const _hoisted_2$8 = { class: "model-list" };
const _hoisted_3$7 = ["checked", "onChange"];
const _hoisted_4$6 = { class: "model-checkbox-visual" };
const _hoisted_5$4 = {
  key: 0,
  class: "check-icon",
  viewBox: "0 0 16 16",
  fill: "currentColor"
};
const _hoisted_6$4 = { class: "model-name" };
const _hoisted_7$4 = { class: "model-count" };
const _hoisted_8$3 = {
  key: 0,
  class: "no-results"
};
const _sfc_main$c = /* @__PURE__ */ defineComponent({
  __name: "BaseModelModal",
  props: {
    visible: { type: Boolean },
    models: {},
    selected: {}
  },
  emits: ["close", "update:selected"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const searchQuery = ref("");
    const searchInputRef = ref(null);
    const filteredModels = computed(() => {
      if (!searchQuery.value) {
        return props.models;
      }
      const query = searchQuery.value.toLowerCase();
      return props.models.filter((m2) => m2.name.toLowerCase().includes(query));
    });
    const isSelected = (name) => {
      return props.selected.includes(name);
    };
    const toggleModel = (name) => {
      const newSelected = isSelected(name) ? props.selected.filter((n) => n !== name) : [...props.selected, name];
      emit2("update:selected", newSelected);
    };
    const onSearch = () => {
    };
    const clearSearch = () => {
      var _a;
      searchQuery.value = "";
      (_a = searchInputRef.value) == null ? void 0 : _a.focus();
    };
    watch(() => props.visible, (isVisible) => {
      if (isVisible) {
        nextTick(() => {
          var _a;
          (_a = searchInputRef.value) == null ? void 0 : _a.focus();
        });
      }
    });
    return (_ctx, _cache) => {
      return openBlock(), createBlock(ModalWrapper, {
        visible: __props.visible,
        title: "Select Base Models",
        subtitle: "Choose which base models to include in your filter",
        onClose: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("close"))
      }, {
        search: withCtx(() => [
          createBaseVNode("div", _hoisted_1$c, [
            _cache[3] || (_cache[3] = createBaseVNode("svg", {
              class: "search-icon",
              viewBox: "0 0 16 16",
              fill: "currentColor"
            }, [
              createBaseVNode("path", { d: "M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z" })
            ], -1)),
            withDirectives(createBaseVNode("input", {
              ref_key: "searchInputRef",
              ref: searchInputRef,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => searchQuery.value = $event),
              type: "text",
              class: "search-input",
              placeholder: "Search models...",
              onInput: onSearch
            }, null, 544), [
              [vModelText, searchQuery.value]
            ]),
            searchQuery.value ? (openBlock(), createElementBlock("button", {
              key: 0,
              type: "button",
              class: "clear-button",
              onClick: clearSearch
            }, [..._cache[2] || (_cache[2] = [
              createBaseVNode("svg", {
                viewBox: "0 0 16 16",
                fill: "currentColor"
              }, [
                createBaseVNode("path", { d: "M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z" })
              ], -1)
            ])])) : createCommentVNode("", true)
          ])
        ]),
        default: withCtx(() => [
          createBaseVNode("div", _hoisted_2$8, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(filteredModels.value, (model) => {
              return openBlock(), createElementBlock("label", {
                key: model.name,
                class: "model-item"
              }, [
                createBaseVNode("input", {
                  type: "checkbox",
                  checked: isSelected(model.name),
                  onChange: ($event) => toggleModel(model.name),
                  class: "model-checkbox"
                }, null, 40, _hoisted_3$7),
                createBaseVNode("span", _hoisted_4$6, [
                  isSelected(model.name) ? (openBlock(), createElementBlock("svg", _hoisted_5$4, [..._cache[4] || (_cache[4] = [
                    createBaseVNode("path", { d: "M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z" }, null, -1)
                  ])])) : createCommentVNode("", true)
                ]),
                createBaseVNode("span", _hoisted_6$4, toDisplayString(model.name), 1),
                createBaseVNode("span", _hoisted_7$4, "(" + toDisplayString(model.count) + ")", 1)
              ]);
            }), 128)),
            filteredModels.value.length === 0 ? (openBlock(), createElementBlock("div", _hoisted_8$3, " No models found ")) : createCommentVNode("", true)
          ])
        ]),
        _: 1
      }, 8, ["visible"]);
    };
  }
});
const BaseModelModal = /* @__PURE__ */ _export_sfc(_sfc_main$c, [["__scopeId", "data-v-e02ca44a"]]);
const _hoisted_1$b = { class: "search-container" };
const _hoisted_2$7 = { class: "tags-container" };
const _hoisted_3$6 = ["onClick"];
const _hoisted_4$5 = {
  key: 0,
  class: "no-results"
};
const _sfc_main$b = /* @__PURE__ */ defineComponent({
  __name: "TagsModal",
  props: {
    visible: { type: Boolean },
    tags: {},
    selected: {},
    variant: {}
  },
  emits: ["close", "update:selected"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const title = computed(
      () => props.variant === "include" ? "Include Tags" : "Exclude Tags"
    );
    const subtitle = computed(
      () => props.variant === "include" ? "Select tags that items must have" : "Select tags that items must NOT have"
    );
    const searchQuery = ref("");
    const searchInputRef = ref(null);
    const filteredTags = computed(() => {
      if (!searchQuery.value) {
        return props.tags;
      }
      const query = searchQuery.value.toLowerCase();
      return props.tags.filter((t) => t.tag.toLowerCase().includes(query));
    });
    const isSelected = (tag) => {
      return props.selected.includes(tag);
    };
    const toggleTag = (tag) => {
      const newSelected = isSelected(tag) ? props.selected.filter((t) => t !== tag) : [...props.selected, tag];
      emit2("update:selected", newSelected);
    };
    const clearSearch = () => {
      var _a;
      searchQuery.value = "";
      (_a = searchInputRef.value) == null ? void 0 : _a.focus();
    };
    watch(() => props.visible, (isVisible) => {
      if (isVisible) {
        nextTick(() => {
          var _a;
          (_a = searchInputRef.value) == null ? void 0 : _a.focus();
        });
      }
    });
    return (_ctx, _cache) => {
      return openBlock(), createBlock(ModalWrapper, {
        visible: __props.visible,
        title: title.value,
        subtitle: subtitle.value,
        "modal-class": __props.variant === "exclude" ? "tags-modal--exclude" : "tags-modal--include",
        onClose: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("close"))
      }, {
        search: withCtx(() => [
          createBaseVNode("div", _hoisted_1$b, [
            _cache[3] || (_cache[3] = createBaseVNode("svg", {
              class: "search-icon",
              viewBox: "0 0 16 16",
              fill: "currentColor"
            }, [
              createBaseVNode("path", { d: "M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z" })
            ], -1)),
            withDirectives(createBaseVNode("input", {
              ref_key: "searchInputRef",
              ref: searchInputRef,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => searchQuery.value = $event),
              type: "text",
              class: "search-input",
              placeholder: "Search tags..."
            }, null, 512), [
              [vModelText, searchQuery.value]
            ]),
            searchQuery.value ? (openBlock(), createElementBlock("button", {
              key: 0,
              type: "button",
              class: "clear-button",
              onClick: clearSearch
            }, [..._cache[2] || (_cache[2] = [
              createBaseVNode("svg", {
                viewBox: "0 0 16 16",
                fill: "currentColor"
              }, [
                createBaseVNode("path", { d: "M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z" })
              ], -1)
            ])])) : createCommentVNode("", true)
          ])
        ]),
        default: withCtx(() => [
          createBaseVNode("div", _hoisted_2$7, [
            (openBlock(true), createElementBlock(Fragment, null, renderList(filteredTags.value, (tag) => {
              return openBlock(), createElementBlock("button", {
                key: tag.tag,
                type: "button",
                class: normalizeClass(["tag-chip", { "tag-chip--selected": isSelected(tag.tag) }]),
                onClick: ($event) => toggleTag(tag.tag)
              }, toDisplayString(tag.tag), 11, _hoisted_3$6);
            }), 128)),
            filteredTags.value.length === 0 ? (openBlock(), createElementBlock("div", _hoisted_4$5, " No tags found ")) : createCommentVNode("", true)
          ])
        ]),
        _: 1
      }, 8, ["visible", "title", "subtitle", "modal-class"]);
    };
  }
});
const TagsModal = /* @__PURE__ */ _export_sfc(_sfc_main$b, [["__scopeId", "data-v-110d6f7d"]]);
const _hoisted_1$a = { class: "tree-node" };
const _hoisted_2$6 = {
  key: 1,
  class: "tree-node__toggle-spacer"
};
const _hoisted_3$5 = { class: "tree-node__checkbox-label" };
const _hoisted_4$4 = ["checked"];
const _hoisted_5$3 = {
  key: 0,
  class: "tree-node__check-icon",
  viewBox: "0 0 16 16",
  fill: "currentColor"
};
const _hoisted_6$3 = { class: "tree-node__label" };
const _hoisted_7$3 = {
  key: 0,
  class: "tree-node__children"
};
const _sfc_main$a = /* @__PURE__ */ defineComponent({
  __name: "FolderTreeNode",
  props: {
    node: {},
    selected: {},
    expanded: {},
    variant: {},
    depth: {}
  },
  emits: ["toggle-expand", "toggle-select"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const hasChildren = computed(() => props.node.children && props.node.children.length > 0);
    const isExpanded = computed(() => props.expanded.has(props.node.key));
    const isSelected = computed(() => props.selected.includes(props.node.key));
    const handleRowClick = (e) => {
      const target = e.target;
      if (target.closest(".tree-node__checkbox-label")) {
        return;
      }
      emit2("toggle-select", props.node.key);
    };
    return (_ctx, _cache) => {
      const _component_FolderTreeNode = resolveComponent("FolderTreeNode", true);
      return openBlock(), createElementBlock("div", _hoisted_1$a, [
        createBaseVNode("div", {
          class: normalizeClass(["tree-node__item", [
            `tree-node__item--${__props.variant}`,
            { "tree-node__item--selected": isSelected.value }
          ]]),
          style: normalizeStyle({ paddingLeft: `${__props.depth * 16 + 8}px` }),
          onClick: handleRowClick
        }, [
          hasChildren.value ? (openBlock(), createElementBlock("button", {
            key: 0,
            type: "button",
            class: "tree-node__toggle",
            onClick: _cache[0] || (_cache[0] = withModifiers(($event) => _ctx.$emit("toggle-expand", __props.node.key), ["stop"]))
          }, [
            (openBlock(), createElementBlock("svg", {
              class: normalizeClass(["tree-node__toggle-icon", { "tree-node__toggle-icon--expanded": isExpanded.value }]),
              viewBox: "0 0 16 16",
              fill: "currentColor"
            }, [..._cache[4] || (_cache[4] = [
              createBaseVNode("path", { d: "M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z" }, null, -1)
            ])], 2))
          ])) : (openBlock(), createElementBlock("span", _hoisted_2$6)),
          createBaseVNode("label", _hoisted_3$5, [
            createBaseVNode("input", {
              type: "checkbox",
              class: "tree-node__checkbox",
              checked: isSelected.value,
              onChange: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("toggle-select", __props.node.key))
            }, null, 40, _hoisted_4$4),
            createBaseVNode("span", {
              class: normalizeClass(["tree-node__checkbox-visual", `tree-node__checkbox-visual--${__props.variant}`])
            }, [
              isSelected.value ? (openBlock(), createElementBlock("svg", _hoisted_5$3, [..._cache[5] || (_cache[5] = [
                createBaseVNode("path", { d: "M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z" }, null, -1)
              ])])) : createCommentVNode("", true)
            ], 2)
          ]),
          _cache[6] || (_cache[6] = createBaseVNode("svg", {
            class: "tree-node__folder-icon",
            viewBox: "0 0 16 16",
            fill: "currentColor"
          }, [
            createBaseVNode("path", { d: "M.54 3.87.5 3a2 2 0 0 1 2-2h3.672a2 2 0 0 1 1.414.586l.828.828A2 2 0 0 0 9.828 3H14a2 2 0 0 1 2 2v1.5a.5.5 0 0 1-1 0V5a1 1 0 0 0-1-1H9.828a3 3 0 0 1-2.12-.879l-.83-.828A1 1 0 0 0 6.172 2H2.5a1 1 0 0 0-1 .981l.006.139C1.72 3.042 1.95 3 2.19 3h5.396l.707.707a1 1 0 0 0 .707.293H14.5a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0V5H9a2 2 0 0 1-1.414-.586l-.828-.828A1 1 0 0 0 6.172 3H2.19a1.5 1.5 0 0 0-1.69.87z" }),
            createBaseVNode("path", { d: "M1.5 4.5h13a.5.5 0 0 1 .5.5v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V5a.5.5 0 0 1 .5-.5z" })
          ], -1)),
          createBaseVNode("span", _hoisted_6$3, toDisplayString(__props.node.label), 1)
        ], 6),
        hasChildren.value && isExpanded.value ? (openBlock(), createElementBlock("div", _hoisted_7$3, [
          (openBlock(true), createElementBlock(Fragment, null, renderList(__props.node.children, (child) => {
            return openBlock(), createBlock(_component_FolderTreeNode, {
              key: child.key,
              node: child,
              selected: __props.selected,
              expanded: __props.expanded,
              variant: __props.variant,
              depth: __props.depth + 1,
              onToggleExpand: _cache[2] || (_cache[2] = ($event) => _ctx.$emit("toggle-expand", $event)),
              onToggleSelect: _cache[3] || (_cache[3] = ($event) => _ctx.$emit("toggle-select", $event))
            }, null, 8, ["node", "selected", "expanded", "variant", "depth"]);
          }), 128))
        ])) : createCommentVNode("", true)
      ]);
    };
  }
});
const FolderTreeNode = /* @__PURE__ */ _export_sfc(_sfc_main$a, [["__scopeId", "data-v-90187dd4"]]);
const _hoisted_1$9 = { class: "search-container" };
const _hoisted_2$5 = { class: "folder-tree" };
const _hoisted_3$4 = {
  key: 1,
  class: "no-results"
};
const _sfc_main$9 = /* @__PURE__ */ defineComponent({
  __name: "FoldersModal",
  props: {
    visible: { type: Boolean },
    folders: {},
    selected: {},
    variant: {}
  },
  emits: ["close", "update:selected"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const searchQuery = ref("");
    const expandedKeys = ref(/* @__PURE__ */ new Set());
    const filteredFolders = computed(() => {
      if (!searchQuery.value) {
        return props.folders;
      }
      const query = searchQuery.value.toLowerCase();
      return filterTree(props.folders, query);
    });
    const filterTree = (nodes, query) => {
      const result = [];
      for (const node of nodes) {
        const matches = node.key.toLowerCase().includes(query) || node.label.toLowerCase().includes(query);
        const filteredChildren = node.children ? filterTree(node.children, query) : [];
        if (matches || filteredChildren.length > 0) {
          result.push({
            ...node,
            children: filteredChildren.length > 0 ? filteredChildren : node.children
          });
          if (searchQuery.value && filteredChildren.length > 0) {
            expandedKeys.value.add(node.key);
          }
        }
      }
      return result;
    };
    const toggleExpand = (key) => {
      if (expandedKeys.value.has(key)) {
        expandedKeys.value.delete(key);
      } else {
        expandedKeys.value.add(key);
      }
      expandedKeys.value = new Set(expandedKeys.value);
    };
    const toggleSelect = (key) => {
      const newSelected = props.selected.includes(key) ? props.selected.filter((k2) => k2 !== key) : [...props.selected, key];
      emit2("update:selected", newSelected);
    };
    watch(() => props.visible, (isVisible) => {
      if (isVisible) {
        searchQuery.value = "";
        expandedKeys.value = /* @__PURE__ */ new Set();
      }
    });
    return (_ctx, _cache) => {
      return openBlock(), createBlock(ModalWrapper, {
        visible: __props.visible,
        title: __props.variant === "include" ? "Include Folders" : "Exclude Folders",
        subtitle: __props.variant === "include" ? "Select folders to include in the filter" : "Select folders to exclude from the filter",
        onClose: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("close"))
      }, {
        search: withCtx(() => [
          createBaseVNode("div", _hoisted_1$9, [
            _cache[2] || (_cache[2] = createBaseVNode("svg", {
              class: "search-icon",
              viewBox: "0 0 16 16",
              fill: "currentColor"
            }, [
              createBaseVNode("path", { d: "M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z" })
            ], -1)),
            withDirectives(createBaseVNode("input", {
              "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => searchQuery.value = $event),
              type: "text",
              class: "search-input",
              placeholder: "Search folders..."
            }, null, 512), [
              [vModelText, searchQuery.value]
            ])
          ])
        ]),
        default: withCtx(() => [
          createBaseVNode("div", _hoisted_2$5, [
            filteredFolders.value.length > 0 ? (openBlock(true), createElementBlock(Fragment, { key: 0 }, renderList(filteredFolders.value, (node) => {
              return openBlock(), createBlock(FolderTreeNode, {
                key: node.key,
                node,
                selected: __props.selected,
                expanded: expandedKeys.value,
                variant: __props.variant,
                depth: 0,
                onToggleExpand: toggleExpand,
                onToggleSelect: toggleSelect
              }, null, 8, ["node", "selected", "expanded", "variant"]);
            }), 128)) : (openBlock(), createElementBlock("div", _hoisted_3$4, " No folders found "))
          ])
        ]),
        _: 1
      }, 8, ["visible", "title", "subtitle"]);
    };
  }
});
const FoldersModal = /* @__PURE__ */ _export_sfc(_sfc_main$9, [["__scopeId", "data-v-046dcbf4"]]);
function useLoraPoolApi() {
  const isLoading = ref(false);
  const fetchBaseModels = async (limit = 50) => {
    try {
      const response = await fetch(`/api/lm/loras/base-models?limit=${limit}`);
      const data = await response.json();
      return data.base_models || [];
    } catch (error) {
      console.error("[LoraPoolApi] Failed to fetch base models:", error);
      return [];
    }
  };
  const fetchTags = async (limit = 100) => {
    try {
      const response = await fetch(`/api/lm/loras/top-tags?limit=${limit}`);
      const data = await response.json();
      return data.tags || [];
    } catch (error) {
      console.error("[LoraPoolApi] Failed to fetch tags:", error);
      return [];
    }
  };
  const fetchFolderTree = async () => {
    try {
      const response = await fetch("/api/lm/loras/unified-folder-tree");
      const data = await response.json();
      return transformFolderTree(data.tree || {});
    } catch (error) {
      console.error("[LoraPoolApi] Failed to fetch folder tree:", error);
      return [];
    }
  };
  const transformFolderTree = (tree, parentPath = "") => {
    if (!tree || typeof tree !== "object") {
      return [];
    }
    return Object.entries(tree).map(([name, children]) => {
      const path = parentPath ? `${parentPath}/${name}` : name;
      const childNodes = transformFolderTree(children, path);
      return {
        key: path,
        label: name,
        children: childNodes.length > 0 ? childNodes : void 0
      };
    });
  };
  const fetchLoras = async (params) => {
    var _a, _b, _c, _d;
    isLoading.value = true;
    try {
      const urlParams = new URLSearchParams();
      urlParams.set("page", String(params.page || 1));
      urlParams.set("page_size", String(params.pageSize || 6));
      (_a = params.baseModels) == null ? void 0 : _a.forEach((bm) => urlParams.append("base_model", bm));
      (_b = params.tagsInclude) == null ? void 0 : _b.forEach((tag) => urlParams.append("tag_include", tag));
      (_c = params.tagsExclude) == null ? void 0 : _c.forEach((tag) => urlParams.append("tag_exclude", tag));
      if (params.foldersInclude && params.foldersInclude.length > 0) {
        params.foldersInclude.forEach((folder) => urlParams.append("folder_include", folder));
        urlParams.set("recursive", "true");
      }
      (_d = params.foldersExclude) == null ? void 0 : _d.forEach((folder) => urlParams.append("folder_exclude", folder));
      if (params.noCreditRequired !== void 0) {
        urlParams.set("credit_required", String(!params.noCreditRequired));
      }
      if (params.allowSelling !== void 0) {
        urlParams.set("allow_selling_generated_content", String(params.allowSelling));
      }
      const response = await fetch(`/api/lm/loras/list?${urlParams}`);
      const data = await response.json();
      return {
        items: data.items || [],
        total: data.total || 0
      };
    } catch (error) {
      console.error("[LoraPoolApi] Failed to fetch loras:", error);
      return { items: [], total: 0 };
    } finally {
      isLoading.value = false;
    }
  };
  return {
    isLoading,
    fetchBaseModels,
    fetchTags,
    fetchFolderTree,
    fetchLoras
  };
}
function useLoraPoolState(widget) {
  const api = useLoraPoolApi();
  const selectedBaseModels = ref([]);
  const includeTags = ref([]);
  const excludeTags = ref([]);
  const includeFolders = ref([]);
  const excludeFolders = ref([]);
  const noCreditRequired = ref(false);
  const allowSelling = ref(false);
  const availableBaseModels = ref([]);
  const availableTags = ref([]);
  const folderTree = ref([]);
  const previewItems = ref([]);
  const matchCount = ref(0);
  const isLoading = computed(() => api.isLoading.value);
  const buildConfig = () => {
    const config = {
      version: 2,
      filters: {
        baseModels: selectedBaseModels.value,
        tags: {
          include: includeTags.value,
          exclude: excludeTags.value
        },
        folders: {
          include: includeFolders.value,
          exclude: excludeFolders.value
        },
        license: {
          noCreditRequired: noCreditRequired.value,
          allowSelling: allowSelling.value
        }
      },
      preview: {
        matchCount: matchCount.value,
        lastUpdated: Date.now()
      }
    };
    if (widget.updateConfig) {
      widget.updateConfig(config);
    } else {
      widget.value = config;
    }
    return config;
  };
  const migrateConfig = (legacy) => {
    var _a, _b, _c, _d, _e2;
    return {
      version: 2,
      filters: {
        baseModels: legacy.filters.baseModels || [],
        tags: {
          include: ((_a = legacy.filters.tags) == null ? void 0 : _a.include) || [],
          exclude: ((_b = legacy.filters.tags) == null ? void 0 : _b.exclude) || []
        },
        folders: {
          include: ((_c = legacy.filters.folder) == null ? void 0 : _c.path) ? [legacy.filters.folder.path] : [],
          exclude: []
        },
        license: {
          noCreditRequired: ((_d = legacy.filters.license) == null ? void 0 : _d.noCreditRequired) ?? false,
          allowSelling: ((_e2 = legacy.filters.license) == null ? void 0 : _e2.allowSellingGeneratedContent) ?? false
        }
      },
      preview: legacy.preview || { matchCount: 0, lastUpdated: 0 }
    };
  };
  const restoreFromConfig = (rawConfig) => {
    var _a, _b, _c, _d, _e2, _f;
    const config = rawConfig.version === 1 ? migrateConfig(rawConfig) : rawConfig;
    if (!(config == null ? void 0 : config.filters)) return;
    const { filters, preview } = config;
    const updateIfChanged = (refValue, newValue) => {
      if (JSON.stringify(refValue.value) !== JSON.stringify(newValue)) {
        refValue.value = newValue;
      }
    };
    updateIfChanged(selectedBaseModels, filters.baseModels || []);
    updateIfChanged(includeTags, ((_a = filters.tags) == null ? void 0 : _a.include) || []);
    updateIfChanged(excludeTags, ((_b = filters.tags) == null ? void 0 : _b.exclude) || []);
    updateIfChanged(includeFolders, ((_c = filters.folders) == null ? void 0 : _c.include) || []);
    updateIfChanged(excludeFolders, ((_d = filters.folders) == null ? void 0 : _d.exclude) || []);
    updateIfChanged(noCreditRequired, ((_e2 = filters.license) == null ? void 0 : _e2.noCreditRequired) ?? false);
    updateIfChanged(allowSelling, ((_f = filters.license) == null ? void 0 : _f.allowSelling) ?? false);
    matchCount.value = (preview == null ? void 0 : preview.matchCount) || 0;
  };
  const fetchFilterOptions = async () => {
    const [baseModels, tags, folders] = await Promise.all([
      api.fetchBaseModels(),
      api.fetchTags(),
      api.fetchFolderTree()
    ]);
    availableBaseModels.value = baseModels;
    availableTags.value = tags;
    folderTree.value = folders;
  };
  const refreshPreview = async () => {
    const result = await api.fetchLoras({
      baseModels: selectedBaseModels.value,
      tagsInclude: includeTags.value,
      tagsExclude: excludeTags.value,
      foldersInclude: includeFolders.value,
      foldersExclude: excludeFolders.value,
      noCreditRequired: noCreditRequired.value || void 0,
      allowSelling: allowSelling.value || void 0,
      pageSize: 6
    });
    previewItems.value = result.items;
    matchCount.value = result.total;
    buildConfig();
  };
  let filterTimeout = null;
  const onFilterChange = () => {
    if (filterTimeout) clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => {
      refreshPreview();
    }, 300);
  };
  watch([
    selectedBaseModels,
    includeTags,
    excludeTags,
    includeFolders,
    excludeFolders,
    noCreditRequired,
    allowSelling
  ], onFilterChange, { deep: true });
  return {
    // Filter state
    selectedBaseModels,
    includeTags,
    excludeTags,
    includeFolders,
    excludeFolders,
    noCreditRequired,
    allowSelling,
    // Available options
    availableBaseModels,
    availableTags,
    folderTree,
    // Preview state
    previewItems,
    matchCount,
    isLoading,
    // Actions
    buildConfig,
    restoreFromConfig,
    fetchFilterOptions,
    refreshPreview
  };
}
function useModalState() {
  const activeModal = ref(null);
  const isOpen = computed(() => activeModal.value !== null);
  const openModal = (modal) => {
    activeModal.value = modal;
  };
  const closeModal = () => {
    activeModal.value = null;
  };
  const isModalOpen = (modal) => {
    return activeModal.value === modal;
  };
  return {
    activeModal,
    isOpen,
    openModal,
    closeModal,
    isModalOpen
  };
}
const _hoisted_1$8 = { class: "lora-pool-widget" };
const _sfc_main$8 = /* @__PURE__ */ defineComponent({
  __name: "LoraPoolWidget",
  props: {
    widget: {},
    node: {}
  },
  setup(__props) {
    const props = __props;
    const state = useLoraPoolState(props.widget);
    const modalState = useModalState();
    const openModal = (modal) => {
      modalState.openModal(modal);
    };
    onMounted(async () => {
      props.widget.serializeValue = async () => {
        const config = state.buildConfig();
        console.log("[LoraPoolWidget] Serializing config:", config);
        return config;
      };
      props.widget.onSetValue = (v2) => {
        state.restoreFromConfig(v2);
        state.refreshPreview();
      };
      if (props.widget.value) {
        console.log("[LoraPoolWidget] Restoring from saved value:", props.widget.value);
        state.restoreFromConfig(props.widget.value);
      }
      await state.fetchFilterOptions();
      await state.refreshPreview();
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$8, [
        createVNode(LoraPoolSummaryView, {
          "selected-base-models": unref(state).selectedBaseModels.value,
          "available-base-models": unref(state).availableBaseModels.value,
          "include-tags": unref(state).includeTags.value,
          "exclude-tags": unref(state).excludeTags.value,
          "include-folders": unref(state).includeFolders.value,
          "exclude-folders": unref(state).excludeFolders.value,
          "no-credit-required": unref(state).noCreditRequired.value,
          "allow-selling": unref(state).allowSelling.value,
          "preview-items": unref(state).previewItems.value,
          "match-count": unref(state).matchCount.value,
          "is-loading": unref(state).isLoading.value,
          onOpenModal: openModal,
          "onUpdate:includeFolders": _cache[0] || (_cache[0] = ($event) => unref(state).includeFolders.value = $event),
          "onUpdate:excludeFolders": _cache[1] || (_cache[1] = ($event) => unref(state).excludeFolders.value = $event),
          "onUpdate:noCreditRequired": _cache[2] || (_cache[2] = ($event) => unref(state).noCreditRequired.value = $event),
          "onUpdate:allowSelling": _cache[3] || (_cache[3] = ($event) => unref(state).allowSelling.value = $event),
          onRefresh: unref(state).refreshPreview
        }, null, 8, ["selected-base-models", "available-base-models", "include-tags", "exclude-tags", "include-folders", "exclude-folders", "no-credit-required", "allow-selling", "preview-items", "match-count", "is-loading", "onRefresh"]),
        createVNode(BaseModelModal, {
          visible: unref(modalState).isModalOpen("baseModels"),
          models: unref(state).availableBaseModels.value,
          selected: unref(state).selectedBaseModels.value,
          onClose: unref(modalState).closeModal,
          "onUpdate:selected": _cache[4] || (_cache[4] = ($event) => unref(state).selectedBaseModels.value = $event)
        }, null, 8, ["visible", "models", "selected", "onClose"]),
        createVNode(TagsModal, {
          visible: unref(modalState).isModalOpen("includeTags"),
          tags: unref(state).availableTags.value,
          selected: unref(state).includeTags.value,
          variant: "include",
          onClose: unref(modalState).closeModal,
          "onUpdate:selected": _cache[5] || (_cache[5] = ($event) => unref(state).includeTags.value = $event)
        }, null, 8, ["visible", "tags", "selected", "onClose"]),
        createVNode(TagsModal, {
          visible: unref(modalState).isModalOpen("excludeTags"),
          tags: unref(state).availableTags.value,
          selected: unref(state).excludeTags.value,
          variant: "exclude",
          onClose: unref(modalState).closeModal,
          "onUpdate:selected": _cache[6] || (_cache[6] = ($event) => unref(state).excludeTags.value = $event)
        }, null, 8, ["visible", "tags", "selected", "onClose"]),
        createVNode(FoldersModal, {
          visible: unref(modalState).isModalOpen("includeFolders"),
          folders: unref(state).folderTree.value,
          selected: unref(state).includeFolders.value,
          variant: "include",
          onClose: unref(modalState).closeModal,
          "onUpdate:selected": _cache[7] || (_cache[7] = ($event) => unref(state).includeFolders.value = $event)
        }, null, 8, ["visible", "folders", "selected", "onClose"]),
        createVNode(FoldersModal, {
          visible: unref(modalState).isModalOpen("excludeFolders"),
          folders: unref(state).folderTree.value,
          selected: unref(state).excludeFolders.value,
          variant: "exclude",
          onClose: unref(modalState).closeModal,
          "onUpdate:selected": _cache[8] || (_cache[8] = ($event) => unref(state).excludeFolders.value = $event)
        }, null, 8, ["visible", "folders", "selected", "onClose"])
      ]);
    };
  }
});
const LoraPoolWidget = /* @__PURE__ */ _export_sfc(_sfc_main$8, [["__scopeId", "data-v-7d3f681d"]]);
const _hoisted_1$7 = { class: "last-used-preview" };
const _hoisted_2$4 = { class: "last-used-preview__content" };
const _hoisted_3$3 = ["src", "onError"];
const _hoisted_4$3 = {
  key: 1,
  class: "last-used-preview__thumb last-used-preview__thumb--placeholder"
};
const _hoisted_5$2 = { class: "last-used-preview__info" };
const _hoisted_6$2 = { class: "last-used-preview__name" };
const _hoisted_7$2 = { class: "last-used-preview__strength" };
const _hoisted_8$2 = {
  key: 0,
  class: "last-used-preview__more"
};
const _sfc_main$7 = /* @__PURE__ */ defineComponent({
  __name: "LastUsedPreview",
  props: {
    loras: {}
  },
  setup(__props) {
    const props = __props;
    const displayLoras = computed(() => props.loras.slice(0, 5));
    const previewUrls = ref({});
    const fetchPreviewUrl = async (loraName) => {
      try {
        const response = await fetch(`/api/lm/loras/preview-url?name=${encodeURIComponent(loraName)}`);
        if (response.ok) {
          const data = await response.json();
          if (data.preview_url) {
            previewUrls.value[loraName] = data.preview_url;
          }
        }
      } catch (error) {
      }
    };
    props.loras.forEach((lora) => {
      fetchPreviewUrl(lora.name);
    });
    const onImageError = (loraName) => {
      previewUrls.value[loraName] = "";
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$7, [
        createBaseVNode("div", _hoisted_2$4, [
          (openBlock(true), createElementBlock(Fragment, null, renderList(displayLoras.value, (lora) => {
            return openBlock(), createElementBlock("div", {
              key: lora.name,
              class: "last-used-preview__item"
            }, [
              previewUrls.value[lora.name] ? (openBlock(), createElementBlock("img", {
                key: 0,
                src: previewUrls.value[lora.name],
                class: "last-used-preview__thumb",
                onError: ($event) => onImageError(lora.name)
              }, null, 40, _hoisted_3$3)) : (openBlock(), createElementBlock("div", _hoisted_4$3, [..._cache[0] || (_cache[0] = [
                createBaseVNode("svg", {
                  viewBox: "0 0 16 16",
                  fill: "currentColor"
                }, [
                  createBaseVNode("path", { d: "M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z" }),
                  createBaseVNode("path", { d: "M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z" })
                ], -1)
              ])])),
              createBaseVNode("div", _hoisted_5$2, [
                createBaseVNode("span", _hoisted_6$2, toDisplayString(lora.name), 1),
                createBaseVNode("span", _hoisted_7$2, " M: " + toDisplayString(lora.strength) + toDisplayString(lora.clipStrength !== void 0 ? ` / C: ${lora.clipStrength}` : ""), 1)
              ])
            ]);
          }), 128)),
          __props.loras.length > 5 ? (openBlock(), createElementBlock("div", _hoisted_8$2, " +" + toDisplayString((__props.loras.length - 5).toLocaleString()) + " more LoRAs ", 1)) : createCommentVNode("", true)
        ])
      ]);
    };
  }
});
const LastUsedPreview = /* @__PURE__ */ _export_sfc(_sfc_main$7, [["__scopeId", "data-v-b940502e"]]);
const _hoisted_1$6 = { class: "slider-handle__value" };
const _sfc_main$6 = /* @__PURE__ */ defineComponent({
  __name: "SingleSlider",
  props: {
    min: {},
    max: {},
    value: {},
    step: {},
    defaultRange: {},
    disabled: { type: Boolean, default: false }
  },
  emits: ["update:value"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const trackEl = ref(null);
    const dragging = ref(false);
    const activePointerId = ref(null);
    const percent = computed(() => {
      const range = props.max - props.min;
      return (props.value - props.min) / range * 100;
    });
    const defaultMinPercent = computed(() => {
      if (!props.defaultRange) return 0;
      const range = props.max - props.min;
      return (props.defaultRange.min - props.min) / range * 100;
    });
    const defaultMaxPercent = computed(() => {
      if (!props.defaultRange) return 100;
      const range = props.max - props.min;
      return (props.defaultRange.max - props.min) / range * 100;
    });
    const formatValue = (val) => {
      if (Number.isInteger(val)) return val.toString();
      return val.toFixed(stepToDecimals(props.step));
    };
    const stepToDecimals = (step) => {
      const str = step.toString();
      const decimalIndex = str.indexOf(".");
      return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1;
    };
    const snapToStep = (value) => {
      const steps = Math.round((value - props.min) / props.step);
      return Math.max(props.min, Math.min(props.max, props.min + steps * props.step));
    };
    const startDrag = (event) => {
      if (props.disabled) return;
      event.preventDefault();
      event.stopPropagation();
      dragging.value = true;
      activePointerId.value = event.pointerId;
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      updateValue(event);
    };
    const onDrag = (event) => {
      if (!dragging.value) return;
      event.stopPropagation();
      updateValue(event);
    };
    const updateValue = (event) => {
      if (!trackEl.value || !dragging.value) return;
      const rect = trackEl.value.getBoundingClientRect();
      const percent2 = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const rawValue = props.min + percent2 * (props.max - props.min);
      const value = snapToStep(rawValue);
      emit2("update:value", value);
    };
    const onWheel = (event) => {
      var _a;
      if (props.disabled) return;
      const rect = (_a = trackEl.value) == null ? void 0 : _a.getBoundingClientRect();
      if (!rect) return;
      const rootRect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rootRect.left || event.clientX > rootRect.right || event.clientY < rootRect.top || event.clientY > rootRect.bottom) return;
      event.preventDefault();
      const delta = event.deltaY > 0 ? -1 : 1;
      const newValue = snapToStep(props.value + delta * props.step);
      emit2("update:value", newValue);
    };
    const stopDrag = (event) => {
      if (!dragging.value) return;
      if (event) {
        event.stopPropagation();
        const target = event.currentTarget;
        if (activePointerId.value !== null) {
          target.releasePointerCapture(activePointerId.value);
        }
      }
      dragging.value = false;
      activePointerId.value = null;
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", {
        class: normalizeClass(["single-slider", { disabled: __props.disabled, "is-dragging": dragging.value }]),
        "data-capture-wheel": "true",
        onWheel
      }, [
        createBaseVNode("div", {
          class: "slider-track",
          ref_key: "trackEl",
          ref: trackEl
        }, [
          _cache[0] || (_cache[0] = createBaseVNode("div", { class: "slider-track__bg" }, null, -1)),
          createBaseVNode("div", {
            class: "slider-track__active",
            style: normalizeStyle({ width: percent.value + "%" })
          }, null, 4),
          __props.defaultRange ? (openBlock(), createElementBlock("div", {
            key: 0,
            class: "slider-track__default",
            style: normalizeStyle({
              left: defaultMinPercent.value + "%",
              width: defaultMaxPercent.value - defaultMinPercent.value + "%"
            })
          }, null, 4)) : createCommentVNode("", true)
        ], 512),
        createBaseVNode("div", {
          class: "slider-handle",
          style: normalizeStyle({ left: percent.value + "%" }),
          onPointerdown: withModifiers(startDrag, ["stop"]),
          onPointermove: withModifiers(onDrag, ["stop"]),
          onPointerup: withModifiers(stopDrag, ["stop"]),
          onPointercancel: withModifiers(stopDrag, ["stop"])
        }, [
          _cache[1] || (_cache[1] = createBaseVNode("div", { class: "slider-handle__thumb" }, null, -1)),
          createBaseVNode("div", _hoisted_1$6, toDisplayString(formatValue(__props.value)), 1)
        ], 36)
      ], 34);
    };
  }
});
const SingleSlider = /* @__PURE__ */ _export_sfc(_sfc_main$6, [["__scopeId", "data-v-2db219ac"]]);
const _hoisted_1$5 = { class: "slider-handle__value" };
const _hoisted_2$3 = { class: "slider-handle__value" };
const _sfc_main$5 = /* @__PURE__ */ defineComponent({
  __name: "DualRangeSlider",
  props: {
    min: {},
    max: {},
    valueMin: {},
    valueMax: {},
    step: {},
    defaultRange: {},
    disabled: { type: Boolean, default: false },
    scaleMode: { default: "linear" },
    segments: { default: () => [] },
    allowEqualValues: { type: Boolean, default: false }
  },
  emits: ["update:valueMin", "update:valueMax"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const trackEl = ref(null);
    const dragging = ref(null);
    const activePointerId = ref(null);
    const effectiveSegments = computed(() => {
      if (props.scaleMode === "segmented" && props.segments.length > 0) {
        return props.segments;
      }
      return [];
    });
    const minPercent = computed(() => {
      if (props.scaleMode === "segmented" && effectiveSegments.value.length > 0) {
        return valueToPercent(props.valueMin);
      }
      const range = props.max - props.min;
      return (props.valueMin - props.min) / range * 100;
    });
    const maxPercent = computed(() => {
      if (props.scaleMode === "segmented" && effectiveSegments.value.length > 0) {
        return valueToPercent(props.valueMax);
      }
      const range = props.max - props.min;
      return (props.valueMax - props.min) / range * 100;
    });
    const defaultMinPercent = computed(() => {
      if (!props.defaultRange) return 0;
      const range = props.max - props.min;
      return (props.defaultRange.min - props.min) / range * 100;
    });
    const defaultMaxPercent = computed(() => {
      if (!props.defaultRange) return 100;
      if (props.scaleMode === "segmented" && effectiveSegments.value.length > 0) {
        return valueToPercent(props.defaultRange.max);
      }
      const range = props.max - props.min;
      return (props.defaultRange.max - props.min) / range * 100;
    });
    const valueToPercent = (value) => {
      const segments = effectiveSegments.value;
      if (segments.length === 0) {
        const range = props.max - props.min;
        return (value - props.min) / range * 100;
      }
      let accumulatedPercent = 0;
      for (const seg of segments) {
        if (value >= seg.max) {
          accumulatedPercent += seg.widthPercent;
        } else if (value >= seg.min) {
          const segRange = seg.max - seg.min;
          const valueInSeg = value - seg.min;
          accumulatedPercent += valueInSeg / segRange * seg.widthPercent;
          return accumulatedPercent;
        } else {
          break;
        }
      }
      return accumulatedPercent;
    };
    const percentToValue = (percent) => {
      const segments = effectiveSegments.value;
      if (segments.length === 0) {
        const range = props.max - props.min;
        return props.min + percent / 100 * range;
      }
      let accumulatedPercent = 0;
      for (const seg of segments) {
        const segEndPercent = accumulatedPercent + seg.widthPercent;
        if (percent <= segEndPercent) {
          const segRange = seg.max - seg.min;
          const percentInSeg = (percent - accumulatedPercent) / seg.widthPercent;
          return seg.min + percentInSeg * segRange;
        }
        accumulatedPercent = segEndPercent;
      }
      return props.max;
    };
    const getSegmentStyle = (seg, index) => {
      let leftPercent = 0;
      for (let i2 = 0; i2 < index; i2++) {
        leftPercent += effectiveSegments.value[i2].widthPercent;
      }
      return {
        left: leftPercent + "%",
        width: seg.widthPercent + "%"
      };
    };
    const formatValue = (val) => {
      if (Number.isInteger(val)) return val.toString();
      return val.toFixed(stepToDecimals(props.step));
    };
    const stepToDecimals = (step) => {
      const str = step.toString();
      const decimalIndex = str.indexOf(".");
      return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1;
    };
    const snapToStep = (value, segmentMultiplier) => {
      const effectiveStep = segmentMultiplier ? props.step * segmentMultiplier : props.step;
      const steps = Math.round((value - props.min) / effectiveStep);
      return Math.max(props.min, Math.min(props.max, props.min + steps * effectiveStep));
    };
    const startDrag = (handle, event) => {
      if (props.disabled) return;
      event.preventDefault();
      event.stopPropagation();
      dragging.value = handle;
      activePointerId.value = event.pointerId;
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      updateValue(event);
    };
    const onDrag = (event) => {
      if (!dragging.value) return;
      event.stopPropagation();
      updateValue(event);
    };
    const updateValue = (event) => {
      if (!trackEl.value || !dragging.value) return;
      const rect = trackEl.value.getBoundingClientRect();
      const percent = Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100));
      const rawValue = percentToValue(percent);
      const multiplier = getSegmentStepMultiplier(rawValue);
      const value = snapToStep(rawValue, multiplier);
      if (dragging.value === "min") {
        const maxMultiplier = getSegmentStepMultiplier(props.valueMax);
        const maxAllowed = props.allowEqualValues ? props.valueMax : props.valueMax - props.step * maxMultiplier;
        const newValue = Math.min(value, maxAllowed);
        emit2("update:valueMin", newValue);
      } else {
        const minMultiplier = getSegmentStepMultiplier(props.valueMin);
        const minAllowed = props.allowEqualValues ? props.valueMin : props.valueMin + props.step * minMultiplier;
        const newValue = Math.max(value, minAllowed);
        emit2("update:valueMax", newValue);
      }
    };
    const getSegmentStepMultiplier = (value) => {
      if (props.scaleMode !== "segmented" || effectiveSegments.value.length === 0) {
        return 1;
      }
      for (const seg of effectiveSegments.value) {
        if (value >= seg.min && value < seg.max) {
          return seg.wheelStepMultiplier || 1;
        }
      }
      return 1;
    };
    const onWheel = (event) => {
      var _a;
      if (props.disabled) return;
      const rect = (_a = trackEl.value) == null ? void 0 : _a.getBoundingClientRect();
      if (!rect) return;
      const rootRect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rootRect.left || event.clientX > rootRect.right || event.clientY < rootRect.top || event.clientY > rootRect.bottom) return;
      event.preventDefault();
      const delta = event.deltaY > 0 ? -1 : 1;
      const relativeX = event.clientX - rect.left;
      const rangeWidth = rect.width;
      const minPixel = minPercent.value / 100 * rangeWidth;
      const maxPixel = maxPercent.value / 100 * rangeWidth;
      if (relativeX < minPixel) {
        const multiplier = getSegmentStepMultiplier(props.valueMin);
        const effectiveStep = props.step * multiplier;
        const newValue = snapToStep(props.valueMin + delta * effectiveStep, multiplier);
        const maxMultiplier = getSegmentStepMultiplier(props.valueMax);
        const maxAllowed = props.allowEqualValues ? props.valueMax : props.valueMax - props.step * maxMultiplier;
        emit2("update:valueMin", Math.min(newValue, maxAllowed));
      } else if (relativeX > maxPixel) {
        const multiplier = getSegmentStepMultiplier(props.valueMax);
        const effectiveStep = props.step * multiplier;
        const newValue = snapToStep(props.valueMax + delta * effectiveStep, multiplier);
        const minMultiplier = getSegmentStepMultiplier(props.valueMin);
        const minAllowed = props.allowEqualValues ? props.valueMin : props.valueMin + props.step * minMultiplier;
        emit2("update:valueMax", Math.max(newValue, minAllowed));
      } else {
        const minMultiplier = getSegmentStepMultiplier(props.valueMin);
        const maxMultiplier = getSegmentStepMultiplier(props.valueMax);
        const newMin = snapToStep(props.valueMin - delta * props.step * minMultiplier, minMultiplier);
        const newMax = snapToStep(props.valueMax + delta * props.step * maxMultiplier, maxMultiplier);
        if (newMin < props.valueMin) {
          emit2("update:valueMin", Math.max(newMin, props.min));
          emit2("update:valueMax", Math.min(newMax, props.max));
        } else {
          const maxAllowed = props.allowEqualValues ? newMax : newMax - props.step * minMultiplier;
          if (newMin <= maxAllowed) {
            emit2("update:valueMin", newMin);
            emit2("update:valueMax", newMax);
          }
        }
      }
    };
    const stopDrag = (event) => {
      if (!dragging.value) return;
      if (event) {
        event.stopPropagation();
        const target = event.currentTarget;
        if (activePointerId.value !== null) {
          target.releasePointerCapture(activePointerId.value);
        }
      }
      dragging.value = null;
      activePointerId.value = null;
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", {
        class: normalizeClass(["dual-range-slider", { disabled: __props.disabled, "is-dragging": dragging.value !== null, "has-segments": __props.scaleMode === "segmented" && effectiveSegments.value.length > 0 }]),
        "data-capture-wheel": "true",
        onWheel
      }, [
        createBaseVNode("div", {
          class: "slider-track",
          ref_key: "trackEl",
          ref: trackEl
        }, [
          _cache[2] || (_cache[2] = createBaseVNode("div", { class: "slider-track__bg" }, null, -1)),
          __props.scaleMode === "segmented" && effectiveSegments.value.length > 0 ? (openBlock(true), createElementBlock(Fragment, { key: 0 }, renderList(effectiveSegments.value, (seg, index) => {
            return openBlock(), createElementBlock("div", {
              key: "segment-" + index,
              class: normalizeClass(["slider-track__segment", {
                "slider-track__segment--common": seg.wheelStepMultiplier && seg.wheelStepMultiplier < 1,
                "slider-track__segment--expanded": seg.wheelStepMultiplier && seg.wheelStepMultiplier < 1
              }]),
              style: normalizeStyle(getSegmentStyle(seg, index))
            }, null, 6);
          }), 128)) : createCommentVNode("", true),
          createBaseVNode("div", {
            class: "slider-track__active",
            style: normalizeStyle({ left: minPercent.value + "%", width: maxPercent.value - minPercent.value + "%" })
          }, null, 4),
          __props.defaultRange ? (openBlock(), createElementBlock("div", {
            key: 1,
            class: "slider-track__default",
            style: normalizeStyle({
              left: defaultMinPercent.value + "%",
              width: defaultMaxPercent.value - defaultMinPercent.value + "%"
            })
          }, null, 4)) : createCommentVNode("", true)
        ], 512),
        createBaseVNode("div", {
          class: "slider-handle slider-handle--min",
          style: normalizeStyle({ left: minPercent.value + "%" }),
          onPointerdown: _cache[0] || (_cache[0] = withModifiers(($event) => startDrag("min", $event), ["stop"])),
          onPointermove: withModifiers(onDrag, ["stop"]),
          onPointerup: withModifiers(stopDrag, ["stop"]),
          onPointercancel: withModifiers(stopDrag, ["stop"])
        }, [
          _cache[3] || (_cache[3] = createBaseVNode("div", { class: "slider-handle__thumb" }, null, -1)),
          createBaseVNode("div", _hoisted_1$5, toDisplayString(formatValue(__props.valueMin)), 1)
        ], 36),
        createBaseVNode("div", {
          class: "slider-handle slider-handle--max",
          style: normalizeStyle({ left: maxPercent.value + "%" }),
          onPointerdown: _cache[1] || (_cache[1] = withModifiers(($event) => startDrag("max", $event), ["stop"])),
          onPointermove: withModifiers(onDrag, ["stop"]),
          onPointerup: withModifiers(stopDrag, ["stop"]),
          onPointercancel: withModifiers(stopDrag, ["stop"])
        }, [
          _cache[4] || (_cache[4] = createBaseVNode("div", { class: "slider-handle__thumb" }, null, -1)),
          createBaseVNode("div", _hoisted_2$3, toDisplayString(formatValue(__props.valueMax)), 1)
        ], 36)
      ], 34);
    };
  }
});
const DualRangeSlider = /* @__PURE__ */ _export_sfc(_sfc_main$5, [["__scopeId", "data-v-05ce9afb"]]);
const _hoisted_1$4 = { class: "randomizer-settings" };
const _hoisted_2$2 = { class: "setting-section" };
const _hoisted_3$2 = { class: "count-mode-tabs" };
const _hoisted_4$2 = ["checked"];
const _hoisted_5$1 = ["checked"];
const _hoisted_6$1 = { class: "slider-container" };
const _hoisted_7$1 = { class: "setting-section" };
const _hoisted_8$1 = { class: "slider-container" };
const _hoisted_9$1 = { class: "setting-section" };
const _hoisted_10$1 = { class: "section-header-with-toggle" };
const _hoisted_11$1 = ["aria-checked"];
const _hoisted_12$1 = { class: "setting-section" };
const _hoisted_13$1 = { class: "section-header-with-toggle" };
const _hoisted_14$1 = { class: "setting-label" };
const _hoisted_15$1 = ["aria-checked"];
const _hoisted_16$1 = { class: "setting-section" };
const _hoisted_17$1 = { class: "roll-buttons-with-tooltip" };
const _hoisted_18$1 = { class: "roll-buttons" };
const _hoisted_19$1 = ["disabled"];
const _hoisted_20 = ["disabled"];
const _hoisted_21 = ["disabled"];
const _sfc_main$4 = /* @__PURE__ */ defineComponent({
  __name: "LoraRandomizerSettingsView",
  props: {
    countMode: {},
    countFixed: {},
    countMin: {},
    countMax: {},
    modelStrengthMin: {},
    modelStrengthMax: {},
    useCustomClipRange: { type: Boolean },
    clipStrengthMin: {},
    clipStrengthMax: {},
    rollMode: {},
    isRolling: { type: Boolean },
    isClipStrengthDisabled: { type: Boolean },
    lastUsed: {},
    currentLoras: {},
    canReuseLast: { type: Boolean },
    useRecommendedStrength: { type: Boolean },
    recommendedStrengthScaleMin: {},
    recommendedStrengthScaleMax: {}
  },
  emits: ["update:countMode", "update:countFixed", "update:countMin", "update:countMax", "update:modelStrengthMin", "update:modelStrengthMax", "update:useCustomClipRange", "update:clipStrengthMin", "update:clipStrengthMax", "update:rollMode", "update:useRecommendedStrength", "update:recommendedStrengthScaleMin", "update:recommendedStrengthScaleMax", "generate-fixed", "always-randomize", "reuse-last"],
  setup(__props) {
    const strengthSegments = [
      { min: -10, max: -2, widthPercent: 20 },
      { min: -2, max: 2, widthPercent: 60, wheelStepMultiplier: 0.5 },
      { min: 2, max: 10, widthPercent: 20 }
    ];
    const showTooltip = ref(false);
    const areLorasEqual = (a2, b2) => {
      if (!a2 || !b2) return false;
      if (a2.length !== b2.length) return false;
      const sortedA = [...a2].sort((x, y2) => x.name.localeCompare(y2.name));
      const sortedB = [...b2].sort((x, y2) => x.name.localeCompare(y2.name));
      return sortedA.every(
        (lora, i2) => lora.name === sortedB[i2].name && lora.strength === sortedB[i2].strength && lora.clipStrength === sortedB[i2].clipStrength
      );
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$4, [
        _cache[29] || (_cache[29] = createBaseVNode("div", { class: "settings-header" }, [
          createBaseVNode("h3", { class: "settings-title" }, "RANDOMIZER SETTINGS")
        ], -1)),
        createBaseVNode("div", _hoisted_2$2, [
          _cache[20] || (_cache[20] = createBaseVNode("label", { class: "setting-label" }, "LoRA Count", -1)),
          createBaseVNode("div", _hoisted_3$2, [
            createBaseVNode("label", {
              class: normalizeClass(["count-mode-tab", { active: __props.countMode === "fixed" }])
            }, [
              createBaseVNode("input", {
                type: "radio",
                name: "count-mode",
                value: "fixed",
                checked: __props.countMode === "fixed",
                onChange: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("update:countMode", "fixed"))
              }, null, 40, _hoisted_4$2),
              _cache[18] || (_cache[18] = createBaseVNode("span", { class: "count-mode-tab-label" }, "Fixed", -1))
            ], 2),
            createBaseVNode("label", {
              class: normalizeClass(["count-mode-tab", { active: __props.countMode === "range" }])
            }, [
              createBaseVNode("input", {
                type: "radio",
                name: "count-mode",
                value: "range",
                checked: __props.countMode === "range",
                onChange: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("update:countMode", "range"))
              }, null, 40, _hoisted_5$1),
              _cache[19] || (_cache[19] = createBaseVNode("span", { class: "count-mode-tab-label" }, "Range", -1))
            ], 2)
          ]),
          createBaseVNode("div", _hoisted_6$1, [
            __props.countMode === "fixed" ? (openBlock(), createBlock(SingleSlider, {
              key: 0,
              min: 1,
              max: 10,
              value: __props.countFixed,
              step: 1,
              "default-range": { min: 1, max: 5 },
              "onUpdate:value": _cache[2] || (_cache[2] = ($event) => _ctx.$emit("update:countFixed", $event))
            }, null, 8, ["value"])) : (openBlock(), createBlock(DualRangeSlider, {
              key: 1,
              min: 1,
              max: 10,
              "value-min": __props.countMin,
              "value-max": __props.countMax,
              step: 1,
              "default-range": { min: 1, max: 5 },
              "allow-equal-values": true,
              "onUpdate:valueMin": _cache[3] || (_cache[3] = ($event) => _ctx.$emit("update:countMin", $event)),
              "onUpdate:valueMax": _cache[4] || (_cache[4] = ($event) => _ctx.$emit("update:countMax", $event))
            }, null, 8, ["value-min", "value-max"]))
          ])
        ]),
        createBaseVNode("div", _hoisted_7$1, [
          _cache[21] || (_cache[21] = createBaseVNode("label", { class: "setting-label" }, "Model Strength Range", -1)),
          createBaseVNode("div", _hoisted_8$1, [
            createVNode(DualRangeSlider, {
              min: -10,
              max: 10,
              "value-min": __props.modelStrengthMin,
              "value-max": __props.modelStrengthMax,
              step: 0.1,
              "default-range": { min: -2, max: 3 },
              "scale-mode": "segmented",
              segments: strengthSegments,
              "allow-equal-values": true,
              "onUpdate:valueMin": _cache[5] || (_cache[5] = ($event) => _ctx.$emit("update:modelStrengthMin", $event)),
              "onUpdate:valueMax": _cache[6] || (_cache[6] = ($event) => _ctx.$emit("update:modelStrengthMax", $event))
            }, null, 8, ["value-min", "value-max"])
          ])
        ]),
        createBaseVNode("div", _hoisted_9$1, [
          createBaseVNode("div", _hoisted_10$1, [
            _cache[23] || (_cache[23] = createBaseVNode("label", { class: "setting-label" }, " Preset Strength Scale ", -1)),
            createBaseVNode("button", {
              type: "button",
              class: normalizeClass(["toggle-switch", { "toggle-switch--active": __props.useRecommendedStrength }]),
              onClick: _cache[7] || (_cache[7] = ($event) => _ctx.$emit("update:useRecommendedStrength", !__props.useRecommendedStrength)),
              role: "switch",
              "aria-checked": __props.useRecommendedStrength,
              title: "Use scaled preset strength when enabled"
            }, [..._cache[22] || (_cache[22] = [
              createBaseVNode("span", { class: "toggle-switch__track" }, null, -1),
              createBaseVNode("span", { class: "toggle-switch__thumb" }, null, -1)
            ])], 10, _hoisted_11$1)
          ]),
          createBaseVNode("div", {
            class: normalizeClass(["slider-container", { "slider-container--disabled": !__props.useRecommendedStrength }])
          }, [
            createVNode(DualRangeSlider, {
              min: 0,
              max: 2,
              "value-min": __props.recommendedStrengthScaleMin,
              "value-max": __props.recommendedStrengthScaleMax,
              step: 0.1,
              "default-range": { min: 0.5, max: 1 },
              disabled: !__props.useRecommendedStrength,
              "allow-equal-values": true,
              "onUpdate:valueMin": _cache[8] || (_cache[8] = ($event) => _ctx.$emit("update:recommendedStrengthScaleMin", $event)),
              "onUpdate:valueMax": _cache[9] || (_cache[9] = ($event) => _ctx.$emit("update:recommendedStrengthScaleMax", $event))
            }, null, 8, ["value-min", "value-max", "disabled"])
          ], 2)
        ]),
        createBaseVNode("div", _hoisted_12$1, [
          createBaseVNode("div", _hoisted_13$1, [
            createBaseVNode("label", _hoisted_14$1, " Clip Strength Range - " + toDisplayString(__props.useCustomClipRange ? "Custom Range" : "Use Model Strength"), 1),
            createBaseVNode("button", {
              type: "button",
              class: normalizeClass(["toggle-switch", { "toggle-switch--active": __props.useCustomClipRange }]),
              onClick: _cache[10] || (_cache[10] = ($event) => _ctx.$emit("update:useCustomClipRange", !__props.useCustomClipRange)),
              role: "switch",
              "aria-checked": __props.useCustomClipRange,
              title: "Use custom clip strength range when enabled, otherwise use model strength"
            }, [..._cache[24] || (_cache[24] = [
              createBaseVNode("span", { class: "toggle-switch__track" }, null, -1),
              createBaseVNode("span", { class: "toggle-switch__thumb" }, null, -1)
            ])], 10, _hoisted_15$1)
          ]),
          createBaseVNode("div", {
            class: normalizeClass(["slider-container", { "slider-container--disabled": __props.isClipStrengthDisabled }])
          }, [
            createVNode(DualRangeSlider, {
              min: -10,
              max: 10,
              "value-min": __props.clipStrengthMin,
              "value-max": __props.clipStrengthMax,
              step: 0.1,
              "default-range": { min: -1, max: 2 },
              "scale-mode": "segmented",
              segments: strengthSegments,
              disabled: __props.isClipStrengthDisabled,
              "allow-equal-values": true,
              "onUpdate:valueMin": _cache[11] || (_cache[11] = ($event) => _ctx.$emit("update:clipStrengthMin", $event)),
              "onUpdate:valueMax": _cache[12] || (_cache[12] = ($event) => _ctx.$emit("update:clipStrengthMax", $event))
            }, null, 8, ["value-min", "value-max", "disabled"])
          ], 2)
        ]),
        createBaseVNode("div", _hoisted_16$1, [
          _cache[28] || (_cache[28] = createBaseVNode("label", { class: "setting-label" }, "Roll Mode", -1)),
          createBaseVNode("div", _hoisted_17$1, [
            createBaseVNode("div", _hoisted_18$1, [
              createBaseVNode("button", {
                class: normalizeClass(["roll-button", { selected: __props.rollMode === "fixed" }]),
                disabled: __props.isRolling,
                onClick: _cache[13] || (_cache[13] = ($event) => _ctx.$emit("generate-fixed"))
              }, [..._cache[25] || (_cache[25] = [
                createStaticVNode('<svg class="roll-button__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-v-f7a531b6><rect x="2" y="2" width="20" height="20" rx="5" data-v-f7a531b6></rect><circle cx="12" cy="12" r="3" data-v-f7a531b6></circle><circle cx="6" cy="8" r="1.5" data-v-f7a531b6></circle><circle cx="18" cy="16" r="1.5" data-v-f7a531b6></circle></svg><span class="roll-button__text" data-v-f7a531b6>Generate Fixed</span>', 2)
              ])], 10, _hoisted_19$1),
              createBaseVNode("button", {
                class: normalizeClass(["roll-button", { selected: __props.rollMode === "always" }]),
                disabled: __props.isRolling,
                onClick: _cache[14] || (_cache[14] = ($event) => _ctx.$emit("always-randomize"))
              }, [..._cache[26] || (_cache[26] = [
                createStaticVNode('<svg class="roll-button__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-v-f7a531b6><path d="M21 12a9 9 0 1 1-6.219-8.56" data-v-f7a531b6></path><path d="M21 3v5h-5" data-v-f7a531b6></path><circle cx="12" cy="12" r="3" data-v-f7a531b6></circle><circle cx="6" cy="8" r="1.5" data-v-f7a531b6></circle><circle cx="18" cy="16" r="1.5" data-v-f7a531b6></circle></svg><span class="roll-button__text" data-v-f7a531b6>Always Randomize</span>', 2)
              ])], 10, _hoisted_20),
              createBaseVNode("button", {
                class: normalizeClass(["roll-button", { selected: __props.rollMode === "fixed" && __props.canReuseLast && areLorasEqual(__props.currentLoras, __props.lastUsed) }]),
                disabled: !__props.canReuseLast,
                onMouseenter: _cache[15] || (_cache[15] = ($event) => showTooltip.value = true),
                onMouseleave: _cache[16] || (_cache[16] = ($event) => showTooltip.value = false),
                onClick: _cache[17] || (_cache[17] = ($event) => _ctx.$emit("reuse-last"))
              }, [..._cache[27] || (_cache[27] = [
                createBaseVNode("svg", {
                  class: "roll-button__icon",
                  viewBox: "0 0 24 24",
                  fill: "none",
                  stroke: "currentColor",
                  "stroke-width": "2",
                  "stroke-linecap": "round",
                  "stroke-linejoin": "round"
                }, [
                  createBaseVNode("path", { d: "M9 14 4 9l5-5" }),
                  createBaseVNode("path", { d: "M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5v0a5.5 5.5 0 0 1-5.5 5.5H11" })
                ], -1),
                createBaseVNode("span", { class: "roll-button__text" }, "Reuse Last", -1)
              ])], 42, _hoisted_21)
            ]),
            createVNode(Transition, { name: "tooltip" }, {
              default: withCtx(() => [
                showTooltip.value && __props.lastUsed && __props.lastUsed.length > 0 ? (openBlock(), createBlock(LastUsedPreview, {
                  key: 0,
                  loras: __props.lastUsed
                }, null, 8, ["loras"])) : createCommentVNode("", true)
              ]),
              _: 1
            })
          ])
        ])
      ]);
    };
  }
});
const LoraRandomizerSettingsView = /* @__PURE__ */ _export_sfc(_sfc_main$4, [["__scopeId", "data-v-f7a531b6"]]);
function useLoraRandomizerState(widget) {
  const countMode = ref("range");
  const countFixed = ref(3);
  const countMin = ref(2);
  const countMax = ref(5);
  const modelStrengthMin = ref(0);
  const modelStrengthMax = ref(1);
  const useCustomClipRange = ref(false);
  const clipStrengthMin = ref(0);
  const clipStrengthMax = ref(1);
  const rollMode = ref("fixed");
  const isRolling = ref(false);
  const useRecommendedStrength = ref(false);
  const recommendedStrengthScaleMin = ref(0.5);
  const recommendedStrengthScaleMax = ref(1);
  const lastUsed = ref(null);
  const executionSeed = ref(null);
  const nextSeed = ref(null);
  const buildConfig = () => ({
    count_mode: countMode.value,
    count_fixed: countFixed.value,
    count_min: countMin.value,
    count_max: countMax.value,
    model_strength_min: modelStrengthMin.value,
    model_strength_max: modelStrengthMax.value,
    use_same_clip_strength: !useCustomClipRange.value,
    clip_strength_min: clipStrengthMin.value,
    clip_strength_max: clipStrengthMax.value,
    roll_mode: rollMode.value,
    last_used: lastUsed.value,
    use_recommended_strength: useRecommendedStrength.value,
    recommended_strength_scale_min: recommendedStrengthScaleMin.value,
    recommended_strength_scale_max: recommendedStrengthScaleMax.value,
    execution_seed: executionSeed.value,
    next_seed: nextSeed.value
  });
  const generateNewSeed = () => {
    executionSeed.value = nextSeed.value;
    nextSeed.value = Math.floor(Math.random() * 2147483647);
  };
  const initializeNextSeed = () => {
    if (nextSeed.value === null) {
      nextSeed.value = Math.floor(Math.random() * 2147483647);
    }
  };
  const restoreFromConfig = (config) => {
    countMode.value = config.count_mode || "range";
    countFixed.value = config.count_fixed || 3;
    countMin.value = config.count_min || 2;
    countMax.value = config.count_max || 5;
    modelStrengthMin.value = config.model_strength_min ?? 0;
    modelStrengthMax.value = config.model_strength_max ?? 1;
    useCustomClipRange.value = !(config.use_same_clip_strength ?? true);
    clipStrengthMin.value = config.clip_strength_min ?? 0;
    clipStrengthMax.value = config.clip_strength_max ?? 1;
    const rawRollMode = config.roll_mode;
    if (rawRollMode === "frontend") {
      rollMode.value = "fixed";
    } else if (rawRollMode === "backend") {
      rollMode.value = "always";
    } else if (rawRollMode === "fixed" || rawRollMode === "always") {
      rollMode.value = rawRollMode;
    } else {
      rollMode.value = "fixed";
    }
    lastUsed.value = config.last_used || null;
    useRecommendedStrength.value = config.use_recommended_strength ?? false;
    recommendedStrengthScaleMin.value = config.recommended_strength_scale_min ?? 0.5;
    recommendedStrengthScaleMax.value = config.recommended_strength_scale_max ?? 1;
  };
  const rollLoras = async (poolConfig, lockedLoras) => {
    try {
      isRolling.value = true;
      const config = buildConfig();
      const requestBody = {
        model_strength_min: config.model_strength_min,
        model_strength_max: config.model_strength_max,
        use_same_clip_strength: !useCustomClipRange.value,
        clip_strength_min: config.clip_strength_min,
        clip_strength_max: config.clip_strength_max,
        locked_loras: lockedLoras,
        use_recommended_strength: config.use_recommended_strength,
        recommended_strength_scale_min: config.recommended_strength_scale_min,
        recommended_strength_scale_max: config.recommended_strength_scale_max
      };
      if (config.count_mode === "fixed") {
        requestBody.count = config.count_fixed;
      } else {
        requestBody.count_min = config.count_min;
        requestBody.count_max = config.count_max;
      }
      if (poolConfig) {
        requestBody.pool_config = poolConfig.filters || {};
      }
      const response = await fetch("/api/lm/loras/random-sample", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(requestBody)
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to fetch random LoRAs");
      }
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || "Failed to get random LoRAs");
      }
      return data.loras || [];
    } catch (error) {
      console.error("[LoraRandomizerState] Error rolling LoRAs:", error);
      throw error;
    } finally {
      isRolling.value = false;
    }
  };
  const useLastUsed = () => {
    if (lastUsed.value && lastUsed.value.length > 0) {
      return lastUsed.value;
    }
    return null;
  };
  const isClipStrengthDisabled = computed(() => !useCustomClipRange.value);
  const isRecommendedStrengthEnabled = computed(() => useRecommendedStrength.value);
  watch([
    countMode,
    countFixed,
    countMin,
    countMax,
    modelStrengthMin,
    modelStrengthMax,
    useCustomClipRange,
    clipStrengthMin,
    clipStrengthMax,
    rollMode,
    useRecommendedStrength,
    recommendedStrengthScaleMin,
    recommendedStrengthScaleMax
  ], () => {
    const config = buildConfig();
    if (widget.updateConfig) {
      widget.updateConfig(config);
    } else {
      widget.value = config;
    }
  }, { deep: true });
  return {
    // State refs
    countMode,
    countFixed,
    countMin,
    countMax,
    modelStrengthMin,
    modelStrengthMax,
    useCustomClipRange,
    clipStrengthMin,
    clipStrengthMax,
    rollMode,
    isRolling,
    lastUsed,
    useRecommendedStrength,
    recommendedStrengthScaleMin,
    recommendedStrengthScaleMax,
    executionSeed,
    nextSeed,
    // Computed
    isClipStrengthDisabled,
    isRecommendedStrengthEnabled,
    // Methods
    buildConfig,
    restoreFromConfig,
    rollLoras,
    useLastUsed,
    generateNewSeed,
    initializeNextSeed
  };
}
const _hoisted_1$3 = { class: "lora-randomizer-widget" };
const _sfc_main$3 = /* @__PURE__ */ defineComponent({
  __name: "LoraRandomizerWidget",
  props: {
    widget: {},
    node: {}
  },
  setup(__props) {
    const props = __props;
    const state = useLoraRandomizerState(props.widget);
    const HAS_EXECUTED = Symbol("HAS_EXECUTED");
    const currentLoras = ref([]);
    const isMounted = ref(false);
    const canReuseLast = computed(() => {
      const lastUsed = state.lastUsed.value;
      if (!lastUsed || lastUsed.length === 0) return false;
      return !areLorasEqual(currentLoras.value, lastUsed);
    });
    const areLorasEqual = (a2, b2) => {
      if (a2.length !== b2.length) return false;
      const sortedA = [...a2].sort((x, y2) => x.name.localeCompare(y2.name));
      const sortedB = [...b2].sort((x, y2) => x.name.localeCompare(y2.name));
      return sortedA.every(
        (lora, i2) => lora.name === sortedB[i2].name && lora.strength === sortedB[i2].strength && lora.clipStrength === sortedB[i2].clipStrength
      );
    };
    const handleGenerateFixed = async () => {
      var _a, _b, _c;
      try {
        const poolConfig = ((_b = (_a = props.node).getPoolConfig) == null ? void 0 : _b.call(_a)) || null;
        const lorasWidget = (_c = props.node.widgets) == null ? void 0 : _c.find((w2) => w2.name === "loras");
        const lockedLoras = ((lorasWidget == null ? void 0 : lorasWidget.value) || []).filter((lora) => lora.locked === true);
        const randomLoras = await state.rollLoras(poolConfig, lockedLoras);
        if (lorasWidget) {
          lorasWidget.value = randomLoras;
          currentLoras.value = randomLoras;
        }
        state.rollMode.value = "fixed";
      } catch (error) {
        console.error("[LoraRandomizerWidget] Error generating fixed LoRAs:", error);
        alert("Failed to generate LoRAs: " + error.message);
      }
    };
    const handleAlwaysRandomize = async () => {
      var _a, _b, _c;
      try {
        const poolConfig = ((_b = (_a = props.node).getPoolConfig) == null ? void 0 : _b.call(_a)) || null;
        const lorasWidget = (_c = props.node.widgets) == null ? void 0 : _c.find((w2) => w2.name === "loras");
        const lockedLoras = ((lorasWidget == null ? void 0 : lorasWidget.value) || []).filter((lora) => lora.locked === true);
        const randomLoras = await state.rollLoras(poolConfig, lockedLoras);
        if (lorasWidget) {
          lorasWidget.value = randomLoras;
          currentLoras.value = randomLoras;
        }
        state.rollMode.value = "always";
      } catch (error) {
        console.error("[LoraRandomizerWidget] Error generating random LoRAs:", error);
        alert("Failed to generate LoRAs: " + error.message);
      }
    };
    const handleReuseLast = () => {
      var _a;
      const lastUsedLoras = state.useLastUsed();
      if (lastUsedLoras) {
        const lorasWidget = (_a = props.node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "loras");
        if (lorasWidget) {
          lorasWidget.value = lastUsedLoras;
          currentLoras.value = lastUsedLoras;
        }
        state.rollMode.value = "fixed";
      }
    };
    watch(() => {
      var _a, _b;
      return (_b = (_a = props.node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "loras")) == null ? void 0 : _b.value;
    }, (newVal) => {
      if (isMounted.value) {
        if (newVal && Array.isArray(newVal)) {
          currentLoras.value = newVal;
        }
      }
    }, { immediate: true, deep: true });
    onMounted(async () => {
      var _a, _b;
      const lorasWidget = (_a = props.node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "loras");
      if (lorasWidget) {
        const currentWidgetValue = lorasWidget.value;
        if (currentWidgetValue && Array.isArray(currentWidgetValue) && currentWidgetValue.length > 0) {
          currentLoras.value = currentWidgetValue;
        }
      }
      isMounted.value = true;
      props.widget.serializeValue = async () => {
        const config = state.buildConfig();
        return config;
      };
      props.widget.onSetValue = (v2) => {
        state.restoreFromConfig(v2);
      };
      if (props.widget.value) {
        state.restoreFromConfig(props.widget.value);
      }
      props.widget.beforeQueued = () => {
        if (state.rollMode.value === "always") {
          if (props.widget[HAS_EXECUTED]) {
            state.generateNewSeed();
          } else {
            state.initializeNextSeed();
            props.widget[HAS_EXECUTED] = true;
          }
          const config = state.buildConfig();
          if (props.widget.updateConfig) {
            props.widget.updateConfig(config);
          } else {
            props.widget.value = config;
          }
        }
      };
      const originalOnExecuted = (_b = props.node.onExecuted) == null ? void 0 : _b.bind(props.node);
      props.node.onExecuted = function(output) {
        var _a2;
        console.log("[LoraRandomizerWidget] Node executed with output:", output);
        if ((output == null ? void 0 : output.last_used) !== void 0) {
          state.lastUsed.value = output.last_used;
          console.log(`[LoraRandomizerWidget] Updated last_used: ${output.last_used ? output.last_used.length : 0} LoRAs`);
        }
        const lorasWidget2 = (_a2 = props.node.widgets) == null ? void 0 : _a2.find((w2) => w2.name === "loras");
        if (lorasWidget2 && (output == null ? void 0 : output.loras) && Array.isArray(output.loras)) {
          console.log("[LoraRandomizerWidget] Received loras data from backend:", output.loras);
          lorasWidget2.value = output.loras;
          currentLoras.value = output.loras;
        }
        if (originalOnExecuted) {
          return originalOnExecuted(output);
        }
      };
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$3, [
        createVNode(LoraRandomizerSettingsView, {
          "count-mode": unref(state).countMode.value,
          "count-fixed": unref(state).countFixed.value,
          "count-min": unref(state).countMin.value,
          "count-max": unref(state).countMax.value,
          "model-strength-min": unref(state).modelStrengthMin.value,
          "model-strength-max": unref(state).modelStrengthMax.value,
          "use-custom-clip-range": unref(state).useCustomClipRange.value,
          "clip-strength-min": unref(state).clipStrengthMin.value,
          "clip-strength-max": unref(state).clipStrengthMax.value,
          "roll-mode": unref(state).rollMode.value,
          "is-rolling": unref(state).isRolling.value,
          "is-clip-strength-disabled": unref(state).isClipStrengthDisabled.value,
          "last-used": unref(state).lastUsed.value,
          "current-loras": currentLoras.value,
          "can-reuse-last": canReuseLast.value,
          "use-recommended-strength": unref(state).useRecommendedStrength.value,
          "recommended-strength-scale-min": unref(state).recommendedStrengthScaleMin.value,
          "recommended-strength-scale-max": unref(state).recommendedStrengthScaleMax.value,
          "onUpdate:countMode": _cache[0] || (_cache[0] = ($event) => unref(state).countMode.value = $event),
          "onUpdate:countFixed": _cache[1] || (_cache[1] = ($event) => unref(state).countFixed.value = $event),
          "onUpdate:countMin": _cache[2] || (_cache[2] = ($event) => unref(state).countMin.value = $event),
          "onUpdate:countMax": _cache[3] || (_cache[3] = ($event) => unref(state).countMax.value = $event),
          "onUpdate:modelStrengthMin": _cache[4] || (_cache[4] = ($event) => unref(state).modelStrengthMin.value = $event),
          "onUpdate:modelStrengthMax": _cache[5] || (_cache[5] = ($event) => unref(state).modelStrengthMax.value = $event),
          "onUpdate:useCustomClipRange": _cache[6] || (_cache[6] = ($event) => unref(state).useCustomClipRange.value = $event),
          "onUpdate:clipStrengthMin": _cache[7] || (_cache[7] = ($event) => unref(state).clipStrengthMin.value = $event),
          "onUpdate:clipStrengthMax": _cache[8] || (_cache[8] = ($event) => unref(state).clipStrengthMax.value = $event),
          "onUpdate:rollMode": _cache[9] || (_cache[9] = ($event) => unref(state).rollMode.value = $event),
          "onUpdate:useRecommendedStrength": _cache[10] || (_cache[10] = ($event) => unref(state).useRecommendedStrength.value = $event),
          "onUpdate:recommendedStrengthScaleMin": _cache[11] || (_cache[11] = ($event) => unref(state).recommendedStrengthScaleMin.value = $event),
          "onUpdate:recommendedStrengthScaleMax": _cache[12] || (_cache[12] = ($event) => unref(state).recommendedStrengthScaleMax.value = $event),
          onGenerateFixed: handleGenerateFixed,
          onAlwaysRandomize: handleAlwaysRandomize,
          onReuseLast: handleReuseLast
        }, null, 8, ["count-mode", "count-fixed", "count-min", "count-max", "model-strength-min", "model-strength-max", "use-custom-clip-range", "clip-strength-min", "clip-strength-max", "roll-mode", "is-rolling", "is-clip-strength-disabled", "last-used", "current-loras", "can-reuse-last", "use-recommended-strength", "recommended-strength-scale-min", "recommended-strength-scale-max"])
      ]);
    };
  }
});
const LoraRandomizerWidget = /* @__PURE__ */ _export_sfc(_sfc_main$3, [["__scopeId", "data-v-45df1002"]]);
const _hoisted_1$2 = { class: "cycler-settings" };
const _hoisted_2$1 = { class: "setting-section progress-section" };
const _hoisted_3$1 = { class: "progress-display" };
const _hoisted_4$1 = { class: "progress-info" };
const _hoisted_5 = ["title"];
const _hoisted_6 = { class: "progress-counter" };
const _hoisted_7 = { class: "progress-index" };
const _hoisted_8 = { class: "progress-total" };
const _hoisted_9 = ["disabled"];
const _hoisted_10 = { class: "setting-section" };
const _hoisted_11 = { class: "index-input-container" };
const _hoisted_12 = ["max", "value", "disabled"];
const _hoisted_13 = { class: "index-hint" };
const _hoisted_14 = { class: "setting-section" };
const _hoisted_15 = { class: "slider-container" };
const _hoisted_16 = { class: "setting-section" };
const _hoisted_17 = { class: "section-header-with-toggle" };
const _hoisted_18 = { class: "setting-label" };
const _hoisted_19 = ["aria-checked"];
const _sfc_main$2 = /* @__PURE__ */ defineComponent({
  __name: "LoraCyclerSettingsView",
  props: {
    currentIndex: {},
    totalCount: {},
    currentLoraName: {},
    currentLoraFilename: {},
    modelStrength: {},
    clipStrength: {},
    useCustomClipRange: { type: Boolean },
    isClipStrengthDisabled: { type: Boolean },
    isLoading: { type: Boolean }
  },
  emits: ["update:currentIndex", "update:modelStrength", "update:clipStrength", "update:useCustomClipRange", "refresh"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit2 = __emit;
    const tempIndex = ref("");
    const onIndexInput = (event) => {
      const input = event.target;
      tempIndex.value = input.value;
    };
    const onIndexBlur = (event) => {
      const input = event.target;
      const value = parseInt(input.value, 10);
      if (!isNaN(value)) {
        const clampedValue = Math.max(1, Math.min(value, props.totalCount || 1));
        emit2("update:currentIndex", clampedValue);
        input.value = clampedValue.toString();
      } else {
        input.value = props.currentIndex.toString();
      }
      tempIndex.value = "";
    };
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$2, [
        _cache[10] || (_cache[10] = createBaseVNode("div", { class: "settings-header" }, [
          createBaseVNode("h3", { class: "settings-title" }, "CYCLER SETTINGS")
        ], -1)),
        createBaseVNode("div", _hoisted_2$1, [
          createBaseVNode("div", _hoisted_3$1, [
            createBaseVNode("div", _hoisted_4$1, [
              _cache[4] || (_cache[4] = createBaseVNode("span", { class: "progress-label" }, "Next LoRA:", -1)),
              createBaseVNode("span", {
                class: "progress-name",
                title: __props.currentLoraFilename
              }, toDisplayString(__props.currentLoraName || "None"), 9, _hoisted_5)
            ]),
            createBaseVNode("div", _hoisted_6, [
              createBaseVNode("span", _hoisted_7, toDisplayString(__props.currentIndex), 1),
              _cache[6] || (_cache[6] = createBaseVNode("span", { class: "progress-separator" }, "/", -1)),
              createBaseVNode("span", _hoisted_8, toDisplayString(__props.totalCount), 1),
              createBaseVNode("button", {
                class: "refresh-button",
                disabled: __props.isLoading,
                onClick: _cache[0] || (_cache[0] = ($event) => _ctx.$emit("refresh")),
                title: "Refresh list"
              }, [
                (openBlock(), createElementBlock("svg", {
                  class: normalizeClass(["refresh-icon", { spinning: __props.isLoading }]),
                  viewBox: "0 0 24 24",
                  fill: "none",
                  stroke: "currentColor",
                  "stroke-width": "2",
                  "stroke-linecap": "round",
                  "stroke-linejoin": "round"
                }, [..._cache[5] || (_cache[5] = [
                  createBaseVNode("path", { d: "M21 12a9 9 0 1 1-6.219-8.56" }, null, -1),
                  createBaseVNode("path", { d: "M21 3v5h-5" }, null, -1)
                ])], 2))
              ], 8, _hoisted_9)
            ])
          ])
        ]),
        createBaseVNode("div", _hoisted_10, [
          _cache[7] || (_cache[7] = createBaseVNode("label", { class: "setting-label" }, "Starting Index", -1)),
          createBaseVNode("div", _hoisted_11, [
            createBaseVNode("input", {
              type: "number",
              class: "index-input",
              min: 1,
              max: __props.totalCount || 1,
              value: __props.currentIndex,
              disabled: __props.totalCount === 0,
              onInput: onIndexInput,
              onBlur: onIndexBlur
            }, null, 40, _hoisted_12),
            createBaseVNode("span", _hoisted_13, "1 - " + toDisplayString(__props.totalCount || 1), 1)
          ])
        ]),
        createBaseVNode("div", _hoisted_14, [
          _cache[8] || (_cache[8] = createBaseVNode("label", { class: "setting-label" }, "Model Strength", -1)),
          createBaseVNode("div", _hoisted_15, [
            createVNode(SingleSlider, {
              min: -10,
              max: 10,
              value: __props.modelStrength,
              step: 0.1,
              "default-range": { min: 0.5, max: 1.5 },
              "onUpdate:value": _cache[1] || (_cache[1] = ($event) => _ctx.$emit("update:modelStrength", $event))
            }, null, 8, ["value"])
          ])
        ]),
        createBaseVNode("div", _hoisted_16, [
          createBaseVNode("div", _hoisted_17, [
            createBaseVNode("label", _hoisted_18, " Clip Strength - " + toDisplayString(__props.useCustomClipRange ? "Custom Value" : "Use Model Strength"), 1),
            createBaseVNode("button", {
              type: "button",
              class: normalizeClass(["toggle-switch", { "toggle-switch--active": __props.useCustomClipRange }]),
              onClick: _cache[2] || (_cache[2] = ($event) => _ctx.$emit("update:useCustomClipRange", !__props.useCustomClipRange)),
              role: "switch",
              "aria-checked": __props.useCustomClipRange,
              title: "Use custom clip strength when enabled, otherwise use model strength"
            }, [..._cache[9] || (_cache[9] = [
              createBaseVNode("span", { class: "toggle-switch__track" }, null, -1),
              createBaseVNode("span", { class: "toggle-switch__thumb" }, null, -1)
            ])], 10, _hoisted_19)
          ]),
          createBaseVNode("div", {
            class: normalizeClass(["slider-container", { "slider-container--disabled": __props.isClipStrengthDisabled }])
          }, [
            createVNode(SingleSlider, {
              min: -10,
              max: 10,
              value: __props.clipStrength,
              step: 0.1,
              "default-range": { min: 0.5, max: 1.5 },
              disabled: __props.isClipStrengthDisabled,
              "onUpdate:value": _cache[3] || (_cache[3] = ($event) => _ctx.$emit("update:clipStrength", $event))
            }, null, 8, ["value", "disabled"])
          ], 2)
        ])
      ]);
    };
  }
});
const LoraCyclerSettingsView = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-af73e0cf"]]);
function useLoraCyclerState(widget) {
  const currentIndex = ref(1);
  const totalCount = ref(0);
  const poolConfigHash = ref("");
  const modelStrength = ref(1);
  const clipStrength = ref(1);
  const useCustomClipRange = ref(false);
  const sortBy = ref("filename");
  const currentLoraName = ref("");
  const currentLoraFilename = ref("");
  const isLoading = ref(false);
  const executionIndex = ref(null);
  const nextIndex = ref(null);
  const buildConfig = () => ({
    current_index: currentIndex.value,
    total_count: totalCount.value,
    pool_config_hash: poolConfigHash.value,
    model_strength: modelStrength.value,
    clip_strength: clipStrength.value,
    use_same_clip_strength: !useCustomClipRange.value,
    sort_by: sortBy.value,
    current_lora_name: currentLoraName.value,
    current_lora_filename: currentLoraFilename.value,
    execution_index: executionIndex.value,
    next_index: nextIndex.value
  });
  const restoreFromConfig = (config) => {
    currentIndex.value = config.current_index || 1;
    totalCount.value = config.total_count || 0;
    poolConfigHash.value = config.pool_config_hash || "";
    modelStrength.value = config.model_strength ?? 1;
    clipStrength.value = config.clip_strength ?? 1;
    useCustomClipRange.value = !(config.use_same_clip_strength ?? true);
    sortBy.value = config.sort_by || "filename";
    currentLoraName.value = config.current_lora_name || "";
    currentLoraFilename.value = config.current_lora_filename || "";
  };
  const generateNextIndex = () => {
    executionIndex.value = nextIndex.value;
    const current = executionIndex.value ?? currentIndex.value;
    let next = current + 1;
    if (totalCount.value > 0 && next > totalCount.value) {
      next = 1;
    }
    nextIndex.value = next;
  };
  const initializeNextIndex = () => {
    if (nextIndex.value === null) {
      let next = currentIndex.value + 1;
      if (totalCount.value > 0 && next > totalCount.value) {
        next = 1;
      }
      nextIndex.value = next;
    }
  };
  const hashPoolConfig = (poolConfig) => {
    if (!poolConfig || !poolConfig.filters) {
      return "";
    }
    try {
      return btoa(JSON.stringify(poolConfig.filters));
    } catch {
      return "";
    }
  };
  const fetchCyclerList = async (poolConfig) => {
    try {
      isLoading.value = true;
      const requestBody = {
        sort_by: sortBy.value
      };
      if (poolConfig == null ? void 0 : poolConfig.filters) {
        requestBody.pool_config = poolConfig.filters;
      }
      const response = await fetch("/api/lm/loras/cycler-list", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(requestBody)
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to fetch cycler list");
      }
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || "Failed to get cycler list");
      }
      return data.loras || [];
    } catch (error) {
      console.error("[LoraCyclerState] Error fetching cycler list:", error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  };
  const refreshList = async (poolConfig) => {
    try {
      const newHash = hashPoolConfig(poolConfig);
      const hashChanged = newHash !== poolConfigHash.value;
      const loraList = await fetchCyclerList(poolConfig);
      totalCount.value = loraList.length;
      if (hashChanged) {
        currentIndex.value = 1;
        poolConfigHash.value = newHash;
      }
      if (currentIndex.value > totalCount.value) {
        currentIndex.value = Math.max(1, totalCount.value);
      }
      if (loraList.length > 0 && currentIndex.value > 0) {
        const currentLora = loraList[currentIndex.value - 1];
        if (currentLora) {
          currentLoraName.value = sortBy.value === "filename" ? currentLora.file_name : currentLora.model_name || currentLora.file_name;
          currentLoraFilename.value = currentLora.file_name;
        }
      } else {
        currentLoraName.value = "";
        currentLoraFilename.value = "";
      }
      return loraList;
    } catch (error) {
      console.error("[LoraCyclerState] Error refreshing list:", error);
      throw error;
    }
  };
  const setIndex = (index) => {
    if (index >= 1 && index <= totalCount.value) {
      currentIndex.value = index;
    }
  };
  const isClipStrengthDisabled = computed(() => !useCustomClipRange.value);
  watch(modelStrength, (newValue) => {
    if (!useCustomClipRange.value) {
      clipStrength.value = newValue;
    }
  });
  watch([
    currentIndex,
    totalCount,
    poolConfigHash,
    modelStrength,
    clipStrength,
    useCustomClipRange,
    sortBy,
    currentLoraName,
    currentLoraFilename
  ], () => {
    const config = buildConfig();
    if (widget.updateConfig) {
      widget.updateConfig(config);
    } else {
      widget.value = config;
    }
  }, { deep: true });
  return {
    // State refs
    currentIndex,
    totalCount,
    poolConfigHash,
    modelStrength,
    clipStrength,
    useCustomClipRange,
    sortBy,
    currentLoraName,
    currentLoraFilename,
    isLoading,
    executionIndex,
    nextIndex,
    // Computed
    isClipStrengthDisabled,
    // Methods
    buildConfig,
    restoreFromConfig,
    hashPoolConfig,
    fetchCyclerList,
    refreshList,
    setIndex,
    generateNextIndex,
    initializeNextIndex
  };
}
const _hoisted_1$1 = { class: "lora-cycler-widget" };
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "LoraCyclerWidget",
  props: {
    widget: {},
    node: {}
  },
  setup(__props) {
    const props = __props;
    const state = useLoraCyclerState(props.widget);
    const HAS_EXECUTED = Symbol("HAS_EXECUTED");
    const lastPoolConfigHash = ref("");
    const isMounted = ref(false);
    const getPoolConfig = () => {
      if (props.node.getPoolConfig) {
        return props.node.getPoolConfig();
      }
      return null;
    };
    const handleIndexUpdate = async (newIndex) => {
      state.setIndex(newIndex);
      try {
        const poolConfig = getPoolConfig();
        const loraList = await state.fetchCyclerList(poolConfig);
        if (loraList.length > 0 && newIndex > 0 && newIndex <= loraList.length) {
          const currentLora = loraList[newIndex - 1];
          if (currentLora) {
            state.currentLoraName.value = currentLora.file_name;
            state.currentLoraFilename.value = currentLora.file_name;
          }
        }
      } catch (error) {
        console.error("[LoraCyclerWidget] Error updating index:", error);
      }
    };
    const handleUseCustomClipRangeChange = (newValue) => {
      state.useCustomClipRange.value = newValue;
      if (!newValue) {
        state.clipStrength.value = state.modelStrength.value;
      }
    };
    const handleRefresh = async () => {
      try {
        const poolConfig = getPoolConfig();
        await state.refreshList(poolConfig);
      } catch (error) {
        console.error("[LoraCyclerWidget] Error refreshing:", error);
      }
    };
    const checkPoolConfigChanges = async () => {
      if (!isMounted.value) return;
      const poolConfig = getPoolConfig();
      const newHash = state.hashPoolConfig(poolConfig);
      if (newHash !== lastPoolConfigHash.value) {
        console.log("[LoraCyclerWidget] Pool config changed, refreshing list");
        lastPoolConfigHash.value = newHash;
        try {
          await state.refreshList(poolConfig);
        } catch (error) {
          console.error("[LoraCyclerWidget] Error on pool config change:", error);
        }
      }
    };
    onMounted(async () => {
      var _a;
      props.widget.serializeValue = async () => {
        return state.buildConfig();
      };
      props.widget.onSetValue = (v2) => {
        state.restoreFromConfig(v2);
      };
      if (props.widget.value) {
        state.restoreFromConfig(props.widget.value);
      }
      props.widget.beforeQueued = () => {
        if (props.widget[HAS_EXECUTED]) {
          state.generateNextIndex();
        } else {
          state.initializeNextIndex();
          props.widget[HAS_EXECUTED] = true;
        }
        const config = state.buildConfig();
        if (props.widget.updateConfig) {
          props.widget.updateConfig(config);
        } else {
          props.widget.value = config;
        }
      };
      isMounted.value = true;
      try {
        const poolConfig = getPoolConfig();
        lastPoolConfigHash.value = state.hashPoolConfig(poolConfig);
        await state.refreshList(poolConfig);
      } catch (error) {
        console.error("[LoraCyclerWidget] Error on initial load:", error);
      }
      const originalOnExecuted = (_a = props.node.onExecuted) == null ? void 0 : _a.bind(props.node);
      props.node.onExecuted = function(output) {
        console.log("[LoraCyclerWidget] Node executed with output:", output);
        if ((output == null ? void 0 : output.next_index) !== void 0) {
          const val = Array.isArray(output.next_index) ? output.next_index[0] : output.next_index;
          state.currentIndex.value = val;
        }
        if ((output == null ? void 0 : output.total_count) !== void 0) {
          const val = Array.isArray(output.total_count) ? output.total_count[0] : output.total_count;
          state.totalCount.value = val;
        }
        if ((output == null ? void 0 : output.current_lora_name) !== void 0) {
          const val = Array.isArray(output.current_lora_name) ? output.current_lora_name[0] : output.current_lora_name;
          state.currentLoraName.value = val;
        }
        if ((output == null ? void 0 : output.current_lora_filename) !== void 0) {
          const val = Array.isArray(output.current_lora_filename) ? output.current_lora_filename[0] : output.current_lora_filename;
          state.currentLoraFilename.value = val;
        }
        if ((output == null ? void 0 : output.next_lora_name) !== void 0) {
          const val = Array.isArray(output.next_lora_name) ? output.next_lora_name[0] : output.next_lora_name;
          state.currentLoraName.value = val;
        }
        if ((output == null ? void 0 : output.next_lora_filename) !== void 0) {
          const val = Array.isArray(output.next_lora_filename) ? output.next_lora_filename[0] : output.next_lora_filename;
          state.currentLoraFilename.value = val;
        }
        if (originalOnExecuted) {
          return originalOnExecuted(output);
        }
      };
      const checkInterval = setInterval(checkPoolConfigChanges, 1e3);
      props.widget.onRemoveCleanup = () => {
        clearInterval(checkInterval);
      };
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1$1, [
        createVNode(LoraCyclerSettingsView, {
          "current-index": unref(state).currentIndex.value,
          "total-count": unref(state).totalCount.value,
          "current-lora-name": unref(state).currentLoraName.value,
          "current-lora-filename": unref(state).currentLoraFilename.value,
          "model-strength": unref(state).modelStrength.value,
          "clip-strength": unref(state).clipStrength.value,
          "use-custom-clip-range": unref(state).useCustomClipRange.value,
          "is-clip-strength-disabled": unref(state).isClipStrengthDisabled.value,
          "is-loading": unref(state).isLoading.value,
          "onUpdate:currentIndex": handleIndexUpdate,
          "onUpdate:modelStrength": _cache[0] || (_cache[0] = ($event) => unref(state).modelStrength.value = $event),
          "onUpdate:clipStrength": _cache[1] || (_cache[1] = ($event) => unref(state).clipStrength.value = $event),
          "onUpdate:useCustomClipRange": handleUseCustomClipRangeChange,
          onRefresh: handleRefresh
        }, null, 8, ["current-index", "total-count", "current-lora-name", "current-lora-filename", "model-strength", "clip-strength", "use-custom-clip-range", "is-clip-strength-disabled", "is-loading"])
      ]);
    };
  }
});
const LoraCyclerWidget = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-95dec8bd"]]);
const _hoisted_1 = { class: "json-display-widget" };
const _hoisted_2 = {
  class: "json-content",
  ref: "contentRef"
};
const _hoisted_3 = ["innerHTML"];
const _hoisted_4 = {
  key: 1,
  class: "placeholder"
};
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "JsonDisplayWidget",
  props: {
    widget: {},
    node: {}
  },
  setup(__props) {
    const props = __props;
    const metadata = ref(null);
    const hasMetadata = computed(
      () => metadata.value !== null && Object.keys(metadata.value).length > 0
    );
    const highlightedJson = computed(() => {
      if (!metadata.value) return "";
      const jsonStr = JSON.stringify(metadata.value, null, 2);
      return syntaxHighlight(jsonStr);
    });
    const colors = {
      key: "#6ad6f5",
      // Light blue for keys
      string: "#98c379",
      // Soft green for strings
      number: "#e5c07b",
      // Amber for numbers
      boolean: "#c678dd",
      // Purple for booleans
      null: "#7f848e"
      // Gray for null
    };
    function syntaxHighlight(json) {
      json = json.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return json.replace(
        /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        (match) => {
          let color = colors.number;
          if (/^"/.test(match)) {
            if (/:$/.test(match)) {
              color = colors.key;
              match = match.replace(/:$/, "");
              return `<span style="color:${color};">${match}</span>:`;
            } else {
              color = colors.string;
            }
          } else if (/true|false/.test(match)) {
            color = colors.boolean;
          } else if (/null/.test(match)) {
            color = colors.null;
          }
          return `<span style="color:${color};">${match}</span>`;
        }
      );
    }
    onMounted(() => {
      var _a;
      props.widget.serializeValue = async () => null;
      props.widget.onSetValue = (v2) => {
        if (v2 && typeof v2 === "object") {
          metadata.value = v2;
        }
      };
      if (props.widget.value && typeof props.widget.value === "object") {
        metadata.value = props.widget.value;
      }
      const originalOnExecuted = (_a = props.node.onExecuted) == null ? void 0 : _a.bind(props.node);
      props.node.onExecuted = function(output) {
        if ((output == null ? void 0 : output.metadata) !== void 0) {
          let metadataValue = output.metadata;
          if (Array.isArray(metadataValue)) {
            metadataValue = metadataValue[0];
          }
          if (typeof metadataValue === "string") {
            try {
              metadataValue = JSON.parse(metadataValue);
            } catch (e) {
              console.error("[JsonDisplayWidget] Failed to parse JSON:", e);
            }
          }
          metadata.value = metadataValue;
        }
        if (originalOnExecuted) {
          return originalOnExecuted(output);
        }
      };
    });
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createBaseVNode("div", _hoisted_2, [
          hasMetadata.value ? (openBlock(), createElementBlock("pre", {
            key: 0,
            innerHTML: highlightedJson.value
          }, null, 8, _hoisted_3)) : (openBlock(), createElementBlock("div", _hoisted_4, "No metadata available"))
        ], 512)
      ]);
    };
  }
});
const JsonDisplayWidget = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-0f202476"]]);
const LORA_PROVIDER_NODE_TYPES$1 = [
  "Lora Stacker (LoraManager)",
  "Lora Randomizer (LoraManager)",
  "Lora Cycler (LoraManager)"
];
function getActiveLorasFromNodeByType(node) {
  const comfyClass = node == null ? void 0 : node.comfyClass;
  if (comfyClass === "Lora Cycler (LoraManager)") {
    return extractFromCyclerConfig(node);
  }
  return extractFromLorasWidget(node);
}
function extractFromLorasWidget(node) {
  var _a;
  const activeLoraNames = /* @__PURE__ */ new Set();
  const lorasWidget = node.lorasWidget || ((_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "loras"));
  if (lorasWidget == null ? void 0 : lorasWidget.value) {
    lorasWidget.value.forEach((lora) => {
      if (lora.active) {
        activeLoraNames.add(lora.name);
      }
    });
  }
  return activeLoraNames;
}
function extractFromCyclerConfig(node) {
  var _a, _b;
  const activeLoraNames = /* @__PURE__ */ new Set();
  const cyclerWidget = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "cycler_config");
  if ((_b = cyclerWidget == null ? void 0 : cyclerWidget.value) == null ? void 0 : _b.current_lora_filename) {
    activeLoraNames.add(cyclerWidget.value.current_lora_filename);
  }
  return activeLoraNames;
}
function isNodeActive(mode) {
  return mode === void 0 || mode === 0 || mode === 3;
}
function setupModeChangeHandler(node, onModeChange) {
  let _mode = node.mode;
  Object.defineProperty(node, "mode", {
    get() {
      return _mode;
    },
    set(value) {
      const oldValue = _mode;
      _mode = value;
      if (oldValue !== value) {
        onModeChange(value, oldValue);
      }
    }
  });
}
function createModeChangeCallback(node, updateDownstreamLoaders, nodeSpecificCallback) {
  return (newMode, _oldMode) => {
    const isNodeCurrentlyActive = isNodeActive(newMode);
    const activeLoraNames = isNodeCurrentlyActive ? getActiveLorasFromNodeByType(node) : /* @__PURE__ */ new Set();
    if (nodeSpecificCallback) {
      nodeSpecificCallback(activeLoraNames);
    }
    updateDownstreamLoaders(node);
  };
}
const app = {};
const ROOT_GRAPH_ID = "root";
const LORA_PROVIDER_NODE_TYPES = [
  "Lora Stacker (LoraManager)",
  "Lora Randomizer (LoraManager)",
  "Lora Cycler (LoraManager)"
];
function isLoraProviderNode(comfyClass) {
  return LORA_PROVIDER_NODE_TYPES.includes(comfyClass);
}
function isMapLike(collection) {
  return collection && typeof collection.entries === "function" && typeof collection.values === "function";
}
function getGraphId(graph) {
  return (graph == null ? void 0 : graph.id) ?? ROOT_GRAPH_ID;
}
function getNodeGraphId(node) {
  if (!node) {
    return ROOT_GRAPH_ID;
  }
  return getGraphId(node.graph || app.graph);
}
function getNodeReference(node) {
  if (!node) {
    return null;
  }
  return {
    node_id: node.id,
    graph_id: getNodeGraphId(node)
  };
}
function getNodeKey(node) {
  if (!node) {
    return null;
  }
  return `${getNodeGraphId(node)}:${node.id}`;
}
function getLinkFromGraph(graph, linkId) {
  if (!graph || graph.links == null) {
    return null;
  }
  if (isMapLike(graph.links)) {
    return graph.links.get(linkId) || null;
  }
  return graph.links[linkId] || null;
}
function getConnectedInputStackers(node) {
  var _a, _b;
  const connectedStackers = [];
  if (!(node == null ? void 0 : node.inputs)) {
    return connectedStackers;
  }
  for (const input of node.inputs) {
    if (input.name !== "lora_stack" || !input.link) {
      continue;
    }
    const link = getLinkFromGraph(node.graph, input.link);
    if (!link) {
      continue;
    }
    const sourceNode = (_b = (_a = node.graph) == null ? void 0 : _a.getNodeById) == null ? void 0 : _b.call(_a, link.origin_id);
    if (sourceNode && isLoraProviderNode(sourceNode.comfyClass)) {
      connectedStackers.push(sourceNode);
    }
  }
  return connectedStackers;
}
function getConnectedTriggerToggleNodes(node) {
  var _a, _b, _c;
  const connectedNodes = [];
  if (!(node == null ? void 0 : node.outputs)) {
    return connectedNodes;
  }
  for (const output of node.outputs) {
    if (!((_a = output == null ? void 0 : output.links) == null ? void 0 : _a.length)) {
      continue;
    }
    for (const linkId of output.links) {
      const link = getLinkFromGraph(node.graph, linkId);
      if (!link) {
        continue;
      }
      const targetNode = (_c = (_b = node.graph) == null ? void 0 : _b.getNodeById) == null ? void 0 : _c.call(_b, link.target_id);
      if (targetNode && targetNode.comfyClass === "TriggerWord Toggle (LoraManager)") {
        connectedNodes.push(targetNode);
      }
    }
  }
  return connectedNodes;
}
function getActiveLorasFromNode(node) {
  var _a, _b;
  const activeLoraNames = /* @__PURE__ */ new Set();
  if (node.comfyClass === "Lora Cycler (LoraManager)") {
    const cyclerWidget = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "cycler_config");
    if ((_b = cyclerWidget == null ? void 0 : cyclerWidget.value) == null ? void 0 : _b.current_lora_filename) {
      activeLoraNames.add(cyclerWidget.value.current_lora_filename);
    }
    return activeLoraNames;
  }
  let lorasWidget = node.lorasWidget;
  if (!lorasWidget && node.widgets) {
    lorasWidget = node.widgets.find((w2) => w2.name === "loras");
  }
  if (lorasWidget && lorasWidget.value) {
    lorasWidget.value.forEach((lora) => {
      if (lora.active) {
        activeLoraNames.add(lora.name);
      }
    });
  }
  return activeLoraNames;
}
function collectActiveLorasFromChain(node, visited = /* @__PURE__ */ new Set()) {
  const nodeKey = getNodeKey(node);
  if (!nodeKey) {
    return /* @__PURE__ */ new Set();
  }
  if (visited.has(nodeKey)) {
    return /* @__PURE__ */ new Set();
  }
  visited.add(nodeKey);
  const isNodeActive2 = node.mode === void 0 || node.mode === 0 || node.mode === 3;
  const allActiveLoraNames = isNodeActive2 ? getActiveLorasFromNode(node) : /* @__PURE__ */ new Set();
  const inputStackers = getConnectedInputStackers(node);
  for (const stacker of inputStackers) {
    const stackerLoras = collectActiveLorasFromChain(stacker, visited);
    stackerLoras.forEach((name) => allActiveLoraNames.add(name));
  }
  return allActiveLoraNames;
}
function updateConnectedTriggerWords(node, loraNames) {
  const connectedNodes = getConnectedTriggerToggleNodes(node);
  if (connectedNodes.length > 0) {
    const nodeIds = connectedNodes.map((connectedNode) => getNodeReference(connectedNode)).filter((reference) => reference !== null);
    if (nodeIds.length === 0) {
      return;
    }
    fetch("/api/lm/loras/get_trigger_words", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lora_names: Array.from(loraNames),
        node_ids: nodeIds
      })
    }).catch((err) => console.error("Error fetching trigger words:", err));
  }
}
function getConnectedPoolConfigNode(node) {
  var _a, _b;
  if (!(node == null ? void 0 : node.inputs)) {
    return null;
  }
  for (const input of node.inputs) {
    if (input.name !== "pool_config" || !input.link) {
      continue;
    }
    const link = getLinkFromGraph(node.graph, input.link);
    if (!link) {
      continue;
    }
    const sourceNode = (_b = (_a = node.graph) == null ? void 0 : _a.getNodeById) == null ? void 0 : _b.call(_a, link.origin_id);
    if (sourceNode && sourceNode.comfyClass === "Lora Pool (LoraManager)") {
      return sourceNode;
    }
  }
  return null;
}
function getPoolConfigFromConnectedNode(node) {
  var _a;
  const poolNode = getConnectedPoolConfigNode(node);
  if (!poolNode) {
    return null;
  }
  const isNodeActive2 = poolNode.mode === void 0 || poolNode.mode === 0 || poolNode.mode === 3;
  if (!isNodeActive2) {
    return null;
  }
  const poolWidget = (_a = poolNode.widgets) == null ? void 0 : _a.find((w2) => w2.name === "pool_config");
  return (poolWidget == null ? void 0 : poolWidget.value) || null;
}
function updateDownstreamLoaders$1(startNode, visited = /* @__PURE__ */ new Set()) {
  var _a, _b;
  const nodeKey = getNodeKey(startNode);
  if (!nodeKey || visited.has(nodeKey)) return;
  visited.add(nodeKey);
  if (startNode.outputs) {
    for (const output of startNode.outputs) {
      if (output.links) {
        for (const linkId of output.links) {
          const link = getLinkFromGraph(startNode.graph, linkId);
          if (link) {
            const targetNode = (_b = (_a = startNode.graph) == null ? void 0 : _a.getNodeById) == null ? void 0 : _b.call(_a, link.target_id);
            if (targetNode && targetNode.comfyClass === "Lora Loader (LoraManager)") {
              const allActiveLoraNames = collectActiveLorasFromChain(targetNode);
              updateConnectedTriggerWords(targetNode, allActiveLoraNames);
            } else if (targetNode && isLoraProviderNode(targetNode.comfyClass)) {
              updateDownstreamLoaders$1(targetNode, visited);
            }
          }
        }
      }
    }
  }
}
const LORA_POOL_WIDGET_MIN_WIDTH = 500;
const LORA_POOL_WIDGET_MIN_HEIGHT = 400;
const LORA_RANDOMIZER_WIDGET_MIN_WIDTH = 500;
const LORA_RANDOMIZER_WIDGET_MIN_HEIGHT = 448;
const LORA_RANDOMIZER_WIDGET_MAX_HEIGHT = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT;
const LORA_CYCLER_WIDGET_MIN_WIDTH = 380;
const LORA_CYCLER_WIDGET_MIN_HEIGHT = 314;
const LORA_CYCLER_WIDGET_MAX_HEIGHT = LORA_CYCLER_WIDGET_MIN_HEIGHT;
const JSON_DISPLAY_WIDGET_MIN_WIDTH = 300;
const JSON_DISPLAY_WIDGET_MIN_HEIGHT = 200;
function forwardMiddleMouseToCanvas(container) {
  if (!container) return;
  container.addEventListener("pointerdown", (event) => {
    if (event.button === 1) {
      const canvas = app$1.canvas;
      if (canvas && typeof canvas.processMouseDown === "function") {
        canvas.processMouseDown(event);
      }
    }
  });
  container.addEventListener("pointermove", (event) => {
    if ((event.buttons & 4) === 4) {
      const canvas = app$1.canvas;
      if (canvas && typeof canvas.processMouseMove === "function") {
        canvas.processMouseMove(event);
      }
    }
  });
  container.addEventListener("pointerup", (event) => {
    if (event.button === 1) {
      const canvas = app$1.canvas;
      if (canvas && typeof canvas.processMouseUp === "function") {
        canvas.processMouseUp(event);
      }
    }
  });
}
const vueApps = /* @__PURE__ */ new Map();
let addLorasWidgetCache = null;
function createLoraPoolWidget(node) {
  const container = document.createElement("div");
  container.id = `lora-pool-widget-${node.id}`;
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.overflow = "hidden";
  forwardMiddleMouseToCanvas(container);
  let internalValue;
  const widget = node.addDOMWidget(
    "pool_config",
    "LORA_POOL_CONFIG",
    container,
    {
      getValue() {
        return internalValue;
      },
      setValue(v2) {
        internalValue = v2;
        if (typeof widget.onSetValue === "function") {
          widget.onSetValue(v2);
        }
      },
      serialize: true,
      // Per dev guide: providing getMinHeight via options allows the system to
      // skip expensive DOM measurements during rendering loop, improving performance
      getMinHeight() {
        return LORA_POOL_WIDGET_MIN_HEIGHT;
      }
    }
  );
  widget.updateConfig = (v2) => {
    internalValue = v2;
  };
  const vueApp = createApp(LoraPoolWidget, {
    widget,
    node
  });
  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  });
  vueApp.mount(container);
  vueApps.set(node.id, vueApp);
  widget.computeLayoutSize = () => {
    const minWidth = LORA_POOL_WIDGET_MIN_WIDTH;
    const minHeight = LORA_POOL_WIDGET_MIN_HEIGHT;
    return { minHeight, minWidth };
  };
  widget.onRemove = () => {
    const vueApp2 = vueApps.get(node.id);
    if (vueApp2) {
      vueApp2.unmount();
      vueApps.delete(node.id);
    }
  };
  return { widget };
}
function createLoraRandomizerWidget(node) {
  const container = document.createElement("div");
  container.id = `lora-randomizer-widget-${node.id}`;
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.overflow = "hidden";
  forwardMiddleMouseToCanvas(container);
  let internalValue;
  const widget = node.addDOMWidget(
    "randomizer_config",
    "RANDOMIZER_CONFIG",
    container,
    {
      getValue() {
        return internalValue;
      },
      setValue(v2) {
        internalValue = v2;
        console.log("randomizer widget value update: ", internalValue);
        if (typeof widget.onSetValue === "function") {
          widget.onSetValue(v2);
        }
      },
      serialize: true,
      getMinHeight() {
        return LORA_RANDOMIZER_WIDGET_MIN_HEIGHT;
      }
    }
  );
  widget.updateConfig = (v2) => {
    internalValue = v2;
  };
  node.getPoolConfig = () => getPoolConfigFromConnectedNode(node);
  widget.onRoll = (randomLoras) => {
    const lorasWidget = node.widgets.find((w2) => w2.name === "loras");
    if (lorasWidget) {
      lorasWidget.value = randomLoras;
    }
  };
  const vueApp = createApp(LoraRandomizerWidget, {
    widget,
    node
  });
  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  });
  vueApp.mount(container);
  vueApps.set(node.id + 1e4, vueApp);
  widget.computeLayoutSize = () => {
    const minWidth = LORA_RANDOMIZER_WIDGET_MIN_WIDTH;
    const minHeight = LORA_RANDOMIZER_WIDGET_MIN_HEIGHT;
    const maxHeight = LORA_RANDOMIZER_WIDGET_MAX_HEIGHT;
    return { minHeight, minWidth, maxHeight };
  };
  widget.onRemove = () => {
    const vueApp2 = vueApps.get(node.id + 1e4);
    if (vueApp2) {
      vueApp2.unmount();
      vueApps.delete(node.id + 1e4);
    }
  };
  return { widget };
}
function createLoraCyclerWidget(node) {
  const container = document.createElement("div");
  container.id = `lora-cycler-widget-${node.id}`;
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.overflow = "hidden";
  forwardMiddleMouseToCanvas(container);
  let internalValue;
  const widget = node.addDOMWidget(
    "cycler_config",
    "CYCLER_CONFIG",
    container,
    {
      getValue() {
        return internalValue;
      },
      setValue(v2) {
        const oldFilename = internalValue == null ? void 0 : internalValue.current_lora_filename;
        internalValue = v2;
        if (typeof widget.onSetValue === "function") {
          widget.onSetValue(v2);
        }
        if (oldFilename !== (v2 == null ? void 0 : v2.current_lora_filename)) {
          updateDownstreamLoaders$1(node);
        }
      },
      serialize: true,
      getMinHeight() {
        return LORA_CYCLER_WIDGET_MIN_HEIGHT;
      }
    }
  );
  widget.updateConfig = (v2) => {
    const oldFilename = internalValue == null ? void 0 : internalValue.current_lora_filename;
    internalValue = v2;
    if (oldFilename !== (v2 == null ? void 0 : v2.current_lora_filename)) {
      updateDownstreamLoaders$1(node);
    }
  };
  node.getPoolConfig = () => getPoolConfigFromConnectedNode(node);
  const vueApp = createApp(LoraCyclerWidget, {
    widget,
    node
  });
  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  });
  vueApp.mount(container);
  vueApps.set(node.id + 3e4, vueApp);
  widget.computeLayoutSize = () => {
    const minWidth = LORA_CYCLER_WIDGET_MIN_WIDTH;
    const minHeight = LORA_CYCLER_WIDGET_MIN_HEIGHT;
    const maxHeight = LORA_CYCLER_WIDGET_MAX_HEIGHT;
    return { minHeight, minWidth, maxHeight };
  };
  widget.onRemove = () => {
    const vueApp2 = vueApps.get(node.id + 3e4);
    if (vueApp2) {
      vueApp2.unmount();
      vueApps.delete(node.id + 3e4);
    }
  };
  return { widget };
}
function createJsonDisplayWidget(node) {
  const container = document.createElement("div");
  container.id = `json-display-widget-${node.id}`;
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.overflow = "hidden";
  forwardMiddleMouseToCanvas(container);
  let internalValue;
  const widget = node.addDOMWidget(
    "metadata",
    "JSON_DISPLAY",
    container,
    {
      getValue() {
        return internalValue;
      },
      setValue(v2) {
        internalValue = v2;
        if (typeof widget.onSetValue === "function") {
          widget.onSetValue(v2);
        }
      },
      serialize: false,
      // Display-only widget - don't save metadata in workflows
      getMinHeight() {
        return JSON_DISPLAY_WIDGET_MIN_HEIGHT;
      }
    }
  );
  const vueApp = createApp(JsonDisplayWidget, {
    widget,
    node
  });
  vueApp.use(PrimeVue, {
    unstyled: true,
    ripple: false
  });
  vueApp.mount(container);
  vueApps.set(node.id + 2e4, vueApp);
  widget.computeLayoutSize = () => {
    const minWidth = JSON_DISPLAY_WIDGET_MIN_WIDTH;
    const minHeight = JSON_DISPLAY_WIDGET_MIN_HEIGHT;
    return { minHeight, minWidth };
  };
  widget.onRemove = () => {
    const vueApp2 = vueApps.get(node.id + 2e4);
    if (vueApp2) {
      vueApp2.unmount();
      vueApps.delete(node.id + 2e4);
    }
  };
  return { widget };
}
app$1.registerExtension({
  name: "LoraManager.VueWidgets",
  getCustomWidgets() {
    return {
      // @ts-ignore
      LORA_POOL_CONFIG(node) {
        return createLoraPoolWidget(node);
      },
      // @ts-ignore
      RANDOMIZER_CONFIG(node) {
        return createLoraRandomizerWidget(node);
      },
      // @ts-ignore
      CYCLER_CONFIG(node) {
        return createLoraCyclerWidget(node);
      },
      // @ts-ignore
      async LORAS(node) {
        if (!addLorasWidgetCache) {
          const module = await import(
            /* @vite-ignore */
            "../loras_widget.js"
          );
          addLorasWidgetCache = module.addLorasWidget;
        }
        const isRandomizerNode = node.comfyClass === "Lora Randomizer (LoraManager)";
        const callback = isRandomizerNode ? () => {
          updateDownstreamLoaders$1(node);
        } : null;
        return addLorasWidgetCache(node, "loras", { isRandomizerNode }, callback);
      }
    };
  },
  // Add display-only widget to Debug Metadata node
  // Register mode change handlers for LoRA provider nodes
  // @ts-ignore
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const comfyClass = nodeType.comfyClass;
    if (LORA_PROVIDER_NODE_TYPES$1.includes(comfyClass)) {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function() {
        originalOnNodeCreated == null ? void 0 : originalOnNodeCreated.apply(this, arguments);
        const nodeSpecificCallback = comfyClass === "Lora Stacker (LoraManager)" ? (activeLoraNames) => updateConnectedTriggerWords(this, activeLoraNames) : void 0;
        const onModeChange = createModeChangeCallback(this, updateDownstreamLoaders$1, nodeSpecificCallback);
        setupModeChangeHandler(this, onModeChange);
      };
    }
    if (nodeData.name === "Debug Metadata (LoraManager)") {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function() {
        onNodeCreated == null ? void 0 : onNodeCreated.apply(this, []);
        createJsonDisplayWidget(this);
      };
    }
  }
});
//# sourceMappingURL=lora-manager-widgets.js.map
