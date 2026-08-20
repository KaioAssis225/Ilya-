import { useRef, useEffect } from 'react'

interface SafePriceProps {
  value: number
  className?: string
  prefix?: string
  currency?: string
  locale?: string
}

export function SafePrice({ value, className, prefix, currency = 'BRL', locale = 'pt-BR' }: SafePriceProps) {
  const spanRef = useRef<HTMLSpanElement>(null)
  const formatted = prefix !== undefined
    ? `${prefix}${Number(value).toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value))

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
