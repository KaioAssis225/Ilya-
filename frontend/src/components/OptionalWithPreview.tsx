import { useEffect, useRef, useState } from 'react'
import { OptionalSwatchImage } from './OptionalSwatchImage'

interface Props {
  label: string
  swatch: string | null
}

// Prévia do acabamento: hover no desktop, toque alterna no tablet/celular.
// O popup usa posição fixa calculada na abertura — dentro de tabelas com
// overflow-x-auto um `absolute bottom-full` era cortado pelo container.
export function OptionalWithPreview({ label, swatch }: Props) {
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  function handleOpen() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const below = rect.top < 160
    setPos({ x: rect.left + rect.width / 2, y: below ? rect.bottom + 8 : rect.top - 8, below })
  }
  const handleClose = () => setPos(null)

  useEffect(() => {
    if (!pos) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose() }
    const onPointer = (e: PointerEvent) => {
      if (!triggerRef.current?.contains(e.target as Node)) handleClose()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer)
    window.addEventListener('scroll', handleClose, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer)
      window.removeEventListener('scroll', handleClose, true)
    }
  }, [pos])

  const text = (
    <span className="border-b border-dotted border-gold text-ink text-xs leading-tight">{label}</span>
  )

  if (!swatch) return <span className="inline-flex items-center gap-1">{text}</span>
  const optional = { color_name: label, photo_url: swatch, thumbnail_url: swatch, photo_variants: null }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex items-center gap-1 cursor-help rounded-sm text-left"
        aria-expanded={pos !== null}
        aria-label={`Ver acabamento ${label}`}
        onMouseEnter={handleOpen}
        onMouseLeave={handleClose}
        onBlur={handleClose}
        // Toque emula mouseenter antes do click: abrir (e não alternar) evita
        // que o popup feche no mesmo toque. Fecha por Escape, blur ou toque fora.
        onClick={handleOpen}
      >
        <OptionalSwatchImage optional={optional} variant="thumb" displaySize={16} decorative className="h-4 w-4 flex-shrink-0 rounded border border-line" />
        {text}
      </button>
      {pos && (
        <span
          role="tooltip"
          className="fixed z-dropdown flex flex-col items-center bg-white shadow-xl rounded-lg p-2 border border-line pointer-events-none"
          style={{
            left: pos.x,
            top: pos.y,
            transform: pos.below ? 'translateX(-50%)' : 'translate(-50%, -100%)',
          }}
        >
          <OptionalSwatchImage optional={optional} variant="gallery" displaySize={96} className="h-24 w-24 rounded-lg" />
          <span className="text-xs text-ink mt-1.5 text-center font-medium whitespace-nowrap">{label}</span>
        </span>
      )}
    </>
  )
}
