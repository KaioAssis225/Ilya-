export type ModalCloseReason = 'backdrop' | 'escape' | 'close-button'

export function shouldCloseModal(reason: ModalCloseReason, closeOnlyByButton: boolean): boolean {
  return !closeOnlyByButton || reason === 'close-button'
}
