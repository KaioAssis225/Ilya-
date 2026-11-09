import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type TouchEvent } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ProductPhoto } from '../types'

const SWIPE_THRESHOLD_PX = 40

interface ProductGalleryProps {
  photos: ProductPhoto[]
  english: boolean
  /** Renderiza a imagem grande da foto atual (o chamador mantém o efeito miniatura -> original). */
  renderImage: (photo: ProductPhoto) => ReactNode
  /** Pede o pré-carregamento do original das fotos vizinhas. */
  onPreload?: (url: string) => void
  /** Só para quem edita produtos: mostra "Definir como principal" na foto atual (se não for a principal). */
  onMakePrimary?: (photo: ProductPhoto) => void
  makePrimaryBusy?: boolean
  makePrimaryError?: string | null
}

function initialPhotoId(photos: ProductPhoto[]) {
  return (photos.find(photo => photo.is_primary) ?? photos[0])?.id ?? null
}

/**
 * Galeria navegável do detalhe do produto: imagem grande, setas, teclado
 * (←/→/Home/End), deslizar no celular e faixa de miniaturas. Abre na principal.
 * A foto atual é guardada por id, então recarregar a lista não muda a posição.
 */
export function ProductGallery({
  photos, english, renderImage, onPreload, onMakePrimary, makePrimaryBusy = false, makePrimaryError = null,
}: ProductGalleryProps) {
  const [selectedId, setSelectedId] = useState<string | null>(() => initialPhotoId(photos))
  const touchStartX = useRef<number | null>(null)
  const count = photos.length
  const found = photos.findIndex(photo => photo.id === selectedId)
  const index = found >= 0 ? found : Math.max(0, photos.findIndex(photo => photo.is_primary))
  const current = photos[index]

  const go = (target: number) => setSelectedId(photos[((target % count) + count) % count].id)

  useEffect(() => {
    if (!onPreload || count < 2) return
    for (const neighbour of [photos[(index + 1) % count], photos[(index - 1 + count) % count]]) {
      if (neighbour?.photo_url) onPreload(neighbour.photo_url)
    }
  }, [count, index, onPreload, photos])

  if (!current) return null

  const label = {
    previous: english ? 'Previous photo' : 'Foto anterior',
    next: english ? 'Next photo' : 'Próxima foto',
    gallery: english ? 'Product photos' : 'Fotos do produto',
    photo: (position: number) => english ? `Photo ${position} of ${count}` : `Foto ${position} de ${count}`,
    makePrimary: english ? 'Set as main photo' : 'Definir como principal',
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, () => void> = {
      ArrowLeft: () => go(index - 1),
      ArrowRight: () => go(index + 1),
      Home: () => go(0),
      End: () => go(count - 1),
    }
    const action = keys[event.key]
    if (!action) return
    event.preventDefault()
    action()
  }

  function onTouchEnd(event: TouchEvent<HTMLDivElement>) {
    const start = touchStartX.current
    touchStartX.current = null
    if (start === null) return
    const delta = event.changedTouches[0].clientX - start
    if (Math.abs(delta) >= SWIPE_THRESHOLD_PX) go(index + (delta < 0 ? 1 : -1))
  }

  return (
    <div
      role="group"
      aria-roledescription="carousel"
      aria-label={label.gallery}
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="flex h-[40vh] w-full flex-col gap-3 outline-none focus-visible:ring-2 focus-visible:ring-gold/40 md:h-full"
    >
      <div
        className="relative min-h-0 flex-1"
        onTouchStart={event => { touchStartX.current = event.touches[0].clientX }}
        onTouchEnd={onTouchEnd}
        style={{ touchAction: 'pan-y' }}
      >
        <div key={current.id} className="h-full w-full" aria-live="polite">
          {renderImage(current)}
        </div>
        {count > 1 && (
          <>
            <button
              type="button"
              onClick={() => go(index - 1)}
              aria-label={label.previous}
              className="absolute left-1 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 text-ink-2 shadow-sm backdrop-blur-sm transition-colors hover:text-ink"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => go(index + 1)}
              aria-label={label.next}
              className="absolute right-1 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 text-ink-2 shadow-sm backdrop-blur-sm transition-colors hover:text-ink"
            >
              <ChevronRight className="h-5 w-5" aria-hidden="true" />
            </button>
            <span className="absolute bottom-1 right-2 rounded-full bg-white/85 px-2 py-0.5 text-[11px] font-medium tabular-nums text-ink-2">
              {index + 1}/{count}
            </span>
          </>
        )}
      </div>
      {onMakePrimary && !current.is_primary && (
        <button
          type="button"
          disabled={makePrimaryBusy}
          onClick={() => onMakePrimary(current)}
          className="btn-secondary min-h-11 flex-shrink-0 self-center px-4 text-xs"
        >
          {label.makePrimary}
        </button>
      )}
      {makePrimaryError && <p role="alert" className="flex-shrink-0 text-center text-xs font-medium text-danger">{makePrimaryError}</p>}
      <div role="tablist" aria-label={label.gallery} className="flex flex-shrink-0 gap-2 overflow-x-auto pb-1">
        {photos.map((photo, position) => (
          <button
            key={photo.id}
            type="button"
            role="tab"
            aria-selected={photo.id === current.id}
            aria-label={label.photo(position + 1)}
            onClick={() => setSelectedId(photo.id)}
            className={`h-14 w-14 flex-shrink-0 overflow-hidden rounded-lg border bg-white transition-colors ${
              photo.id === current.id ? 'border-gold ring-1 ring-gold/50' : 'border-line hover:border-ink-2/40'
            }`}
          >
            {(photo.thumbnail_url ?? photo.photo_url) && (
              <img
                src={(photo.thumbnail_url ?? photo.photo_url)!}
                alt=""
                loading="lazy"
                decoding="async"
                className="h-full w-full object-contain"
              />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
