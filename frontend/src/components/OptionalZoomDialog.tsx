import { X } from 'lucide-react'
import { DialogPanel } from './Dialog'
import { OptionalSwatchImage } from './OptionalSwatchImage'
import type { OptionalColor } from '../types'
import { useLocale } from '../hooks/useLocale'

export function OptionalZoomDialog({
  optional,
  type,
  onClose,
}: {
  optional: OptionalColor
  type: string
  onClose: () => void
}) {
  const { locale } = useLocale()

  return (
    <div
      className="modal-overlay z-modal-sub items-center"
      onClick={event => { if (event.target === event.currentTarget) onClose() }}
    >
      <DialogPanel
        onClose={onClose}
        label={`${type}: ${optional.color_name}`}
        className="modal-panel relative my-auto w-full max-w-[min(90vw,704px)] p-4 sm:p-6"
      >
        <button
          type="button"
          onClick={onClose}
          className="btn-icon absolute right-2 top-2 z-10 bg-white/95 shadow-sm sm:right-3 sm:top-3"
          aria-label={locale === 'en-GB' ? 'Close' : 'Fechar'}
          autoFocus
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
        <OptionalSwatchImage
          optional={optional}
          variant="zoom"
          displaySize={640}
          priority
          responsive={false}
          className="mx-auto w-full max-w-[min(80vw,640px)] rounded-xl"
        />
        <div className="px-1 pb-1 pt-4 text-center">
          <h2 className="text-xl leading-tight text-ink sm:text-2xl">{optional.color_name}</h2>
          <p className="mt-1 text-sm text-muted">{type}</p>
        </div>
      </DialogPanel>
    </div>
  )
}
