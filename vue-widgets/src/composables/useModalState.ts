import { ref, computed } from 'vue'

export type ModalType = 'baseModels' | 'includeTags' | 'excludeTags' | null

export function useModalState() {
  const activeModal = ref<ModalType>(null)

  const isOpen = computed(() => activeModal.value !== null)

  const openModal = (modal: ModalType) => {
    activeModal.value = modal
  }

  const closeModal = () => {
    activeModal.value = null
  }

  const isModalOpen = (modal: ModalType) => {
    return activeModal.value === modal
  }

  return {
    activeModal,
    isOpen,
    openModal,
    closeModal,
    isModalOpen
  }
}

export type ModalStateReturn = ReturnType<typeof useModalState>
