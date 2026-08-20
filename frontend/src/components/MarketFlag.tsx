export type MarketCode = 'BR' | 'EU'

export function MarketFlag({ market, className = 'h-3.5 w-5', animated = false }: { market: MarketCode; className?: string; animated?: boolean }) {
  const svgClassName = `${className}${animated ? ' market-flag-build' : ''}`
  if (market === 'EU') {
    return (
      <svg viewBox="0 0 30 20" className={svgClassName} role="img" aria-label="Bandeira de Portugal">
        <rect className="market-flag-field" width="30" height="20" rx="1.5" fill="#C8102E" />
        <rect className="market-flag-panel" width="12" height="20" rx="1.5" fill="#046A38" />
        <g className="market-flag-symbol">
          <circle cx="12" cy="10" r="3.2" fill="#FFCC29" />
          <circle cx="12" cy="10" r="1.8" fill="#fff" />
          <path d="M10.8 8.6h2.4v2.8h-2.4z" fill="#C8102E" />
        </g>
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 30 20" className={svgClassName} role="img" aria-label="Bandeira do Brasil">
      <rect className="market-flag-field" width="30" height="20" rx="1.5" fill="#009C3B" />
      <path className="market-flag-panel" d="M15 3 26 10 15 17 4 10Z" fill="#FFDF00" />
      <g className="market-flag-symbol">
        <circle cx="15" cy="10" r="4.1" fill="#002776" />
        <path d="M11.3 9.2c2.7-.7 5.4-.2 7.4 1.3" fill="none" stroke="#fff" strokeWidth=".7" />
      </g>
    </svg>
  )
}
