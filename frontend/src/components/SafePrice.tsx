interface SafePriceProps {
  value: number
  className?: string
  prefix?: string
  currency?: string
  locale?: string
}

export function SafePrice({ value, className, prefix, currency = 'BRL', locale = 'pt-BR' }: SafePriceProps) {
  const formatted = prefix !== undefined
    ? `${prefix}${Number(value).toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value))

  return (
    <span className={`select-text tabular-nums ${className ?? ''}`}>
      {formatted}
    </span>
  )
}
