import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Trash2, X } from 'lucide-react'
import { useLocale } from '../hooks/useLocale'
import { optionalName, optionalCategoryLabel } from '../lib/optionalLabels'
import type { OptionalColor } from '../types'
import { OptionalSwatchImage } from './OptionalSwatchImage'

export function OptionalBenchPanel({
  items,
  categoryLabel,
  onRemove,
  onMove,
  onClear,
  expanded,
  onExpandedChange,
}: {
  items: OptionalColor[]
  categoryLabel: (code: string) => string
  onRemove: (optional: OptionalColor) => void
  onMove: (optional: OptionalColor, direction: -1 | 1) => void
  onClear: () => void
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const { locale } = useLocale()
  const english = locale === 'en-GB'
  if (items.length === 0) return null

  return (
    <aside
      aria-label={english ? 'Finish comparison bench' : 'Bancada de comparação de opcionais'}
      className="optional-bench-position fixed inset-x-0 z-drawer border-t border-line bg-white/95 shadow-[0_-12px_32px_rgba(44,36,32,0.12)] backdrop-blur-md"
    >
      <div className="mx-auto max-w-7xl px-4 pb-safe md:px-8">
        <div className="flex min-h-14 items-center gap-3 py-2">
          <button
            type="button"
            onClick={() => onExpandedChange(!expanded)}
            className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-lg text-left"
            aria-expanded={expanded}
          >
            <span className="flex -space-x-2" aria-hidden="true">
              {items.map(optional => (
                <OptionalSwatchImage
                  key={optional.id}
                  optional={optional}
                  variant="gallery"
                  displaySize={40}
                  decorative
                  className="h-10 w-10 rounded-lg border-2 border-white shadow-sm"
                />
              ))}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">
                {english ? `Side by side · ${items.length}/4` : `Lado a lado · ${items.length}/4`}
              </span>
              <span className="block text-xs text-muted">
                {items.length === 1
                  ? (english ? 'Add another finish to compare.' : 'Adicione outra amostra para comparar.')
                  : (expanded ? (english ? 'Collapse bench' : 'Recolher bancada') : (english ? 'Expand bench' : 'Expandir bancada'))}
              </span>
            </span>
            {expanded ? <ChevronDown className="ml-auto h-5 w-5 text-muted" /> : <ChevronUp className="ml-auto h-5 w-5 text-muted" />}
          </button>
          <button type="button" onClick={onClear} className="btn-secondary shrink-0 px-3" aria-label={english ? 'Clear comparison bench' : 'Limpar bancada'}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">{english ? 'Clear' : 'Limpar'}</span>
          </button>
        </div>

        {expanded && (
          <div className="flex snap-x gap-3 overflow-x-auto border-t border-line-soft py-3 md:justify-center md:gap-4">
            {items.map((optional, index) => (
              <article key={optional.id} className="min-w-[calc(50vw-1.75rem)] snap-start sm:min-w-[220px] md:min-w-[180px] md:max-w-[260px] md:flex-1">
                <div className="relative">
                  <OptionalSwatchImage
                    optional={optional}
                    variant="zoom"
                    displaySize={320}
                    responsive={false}
                    priority={index < 2}
                    className="w-full rounded-xl border border-line"
                  />
                  <button
                    type="button"
                    onClick={() => onRemove(optional)}
                    className="btn-icon absolute right-1.5 top-1.5 bg-white/95 shadow-sm"
                    aria-label={english ? `Remove ${optionalName(optional.color_name, english)}` : `Remover ${optionalName(optional.color_name, english)}`}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                <div className="pt-2">
                  <p className="text-sm font-semibold leading-snug text-ink [overflow-wrap:anywhere]">{optionalName(optional.color_name, english)}</p>
                  <p className="mt-0.5 text-xs text-muted">{optionalCategoryLabel(categoryLabel(optional.category), english)}</p>
                  <div className="mt-1 flex gap-1">
                    <button
                      type="button"
                      onClick={() => onMove(optional, -1)}
                      disabled={index === 0}
                      className="btn-icon"
                      aria-label={english ? `Move ${optionalName(optional.color_name, english)} left` : `Mover ${optionalName(optional.color_name, english)} para a esquerda`}
                    >
                      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onMove(optional, 1)}
                      disabled={index === items.length - 1}
                      className="btn-icon"
                      aria-label={english ? `Move ${optionalName(optional.color_name, english)} right` : `Mover ${optionalName(optional.color_name, english)} para a direita`}
                    >
                      <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
