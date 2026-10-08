import { useEffect, useRef, useState } from 'react'

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

  function open() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const below = rect.top < 160
    setPos({ x: rect.left + rect.width / 2, y: below ? rect.bottom + 8 : rect.top - 8, below })
  }
  const close = () => setPos(null)

  useEffect(() => {
    if (!pos) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onPointer = (e: PointerEvent) => {
      if (!triggerRef.current?.contains(e.target as Node)) close()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer)
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer)
      window.removeEventListener('scroll', close, true)
    }
  }, [pos])

  const text = (
    <span className="border-b border-dotted border-gold text-ink text-xs leading-tight">{label}</span>
  )

  if (!swatch) return <span className="inline-flex items-center gap-1">{text}</span>

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex items-center gap-1 cursor-help rounded-sm text-left"
        aria-expanded={pos !== null}
        aria-label={`Ver acabamento ${label}`}
        onMouseEnter={open}
        onMouseLeave={close}
        onBlur={close}
        // Toque emula mouseenter antes do click: abrir (e não alternar) evita
        // que o popup feche no mesmo toque. Fecha por Escape, blur ou toque fora.
        onClick={open}
      >
        <img src={swatch} alt="" className="w-4 h-4 rounded object-cover border border-line flex-shrink-0" />
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
          <img src={swatch} alt={label} className="w-24 h-24 rounded-lg object-cover" />
          <span className="text-xs text-ink mt-1.5 text-center font-medium whitespace-nowrap">{label}</span>
        </span>
      )}
    </>
  )
}
