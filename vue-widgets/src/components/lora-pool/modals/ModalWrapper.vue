<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="visible"
        class="lora-pool-modal-backdrop"
        @click.self="close"
        @keydown.esc="close"
      >
        <div class="lora-pool-modal" :class="modalClass" role="dialog" aria-modal="true">
          <div class="lora-pool-modal__header">
            <div class="lora-pool-modal__title-container">
              <h3 class="lora-pool-modal__title">{{ title }}</h3>
              <p v-if="subtitle" class="lora-pool-modal__subtitle">{{ subtitle }}</p>
            </div>
            <button
              class="lora-pool-modal__close"
              @click="close"
              type="button"
              aria-label="Close"
            >
              &times;
            </button>
          </div>
          <div v-if="$slots.search" class="lora-pool-modal__search">
            <slot name="search"></slot>
          </div>
          <div class="lora-pool-modal__body">
            <slot></slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  visible: boolean
  title: string
  subtitle?: string
  modalClass?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const close = () => {
  emit('close')
}

// Handle escape key globally
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && props.visible) {
    close()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

// Prevent body scroll when modal is open
watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.lora-pool-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(2px);
}

.lora-pool-modal {
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

.lora-pool-modal__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-color, #444);
}

.lora-pool-modal__title-container {
  flex: 1;
}

.lora-pool-modal__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--fg-color, #fff);
  margin: 0;
}

.lora-pool-modal__subtitle {
  font-size: 12px;
  color: var(--fg-color, #fff);
  opacity: 0.6;
  margin: 4px 0 0 0;
}

.lora-pool-modal__close {
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

.lora-pool-modal__close:hover {
  opacity: 1;
  background: var(--comfy-input-bg, #333);
}

.lora-pool-modal__search {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color, #444);
}

.lora-pool-modal__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 16px;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .lora-pool-modal,
.modal-leave-active .lora-pool-modal {
  transition: transform 0.2s ease;
}

.modal-enter-from .lora-pool-modal,
.modal-leave-to .lora-pool-modal {
  transform: scale(0.95);
}
</style>
