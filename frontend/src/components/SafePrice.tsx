import { useRef, useEffect } from 'react'

interface SafePriceProps {
  value: number
  className?: string
  prefix?: string
}

export function SafePrice({ value, className, prefix = 'R$ ' }: SafePriceProps) {
  const spanRef = useRef<HTMLSpanElement>(null)
  const formatted = `${prefix}${Number(value).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  useEffect(() => {
    const el = spanRef.current
    if (!el) return
    const observer = new MutationObserver(() => {
      if (el.textContent !== formatted) {
        el.textContent = formatted
      }
    })
    observer.observe(el, { childList: true, characterData: true, subtree: true })
    return () => observer.disconnect()
  }, [formatted])

  return (
    <span
      ref={spanRef}
      className={className}
      style={{ userSelect: 'none', pointerEvents: 'none' }}
    >
      {formatted}
    </span>
  )
}
