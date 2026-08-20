import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { MarketFlag, type MarketCode } from './MarketFlag'
import { MarketTransition } from './MarketTransition'

const LABELS: Record<MarketCode, string> = { BR: 'Brasil', EU: 'Portugal' }

export function MarketSwitcher() {
  const { user, switchMarket } = useAuth()
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState<MarketCode | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', closeOutside)
    document.addEventListener('keydown', closeEscape)
    return () => {
      document.removeEventListener('mousedown', closeOutside)
      document.removeEventListener('keydown', closeEscape)
    }
  }, [open])

  if (!user) return null
  const canSwitch = user.allowed_markets.length > 1

  async function choose(market: MarketCode) {
    if (market === user?.active_market) {
      setOpen(false)
      return
    }
    setOpen(false)
    setSwitching(market)
    try {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      if (!reduceMotion) await new Promise(resolve => window.setTimeout(resolve, 1650))
      await switchMarket(market)
    } finally {
      setSwitching(null)
    }
  }

  if (!canSwitch) {
    return (
      <span className="inline-flex h-11 w-11 items-center justify-center" title={`Ambiente ${LABELS[user.active_market]}`}>
        <MarketFlag market={user.active_market} className="h-4 w-6 shadow-sm" />
      </span>
    )
  }

  return (
    <div ref={rootRef} className="relative">
      {switching && (
        <MarketTransition market={switching} />
      )}
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        className="inline-flex h-11 min-w-11 items-center justify-center gap-1 rounded-lg hover:bg-bg-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
        aria-label={`Ambiente ${LABELS[user.active_market]}. Trocar ambiente`}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={switching !== null}
      >
        <MarketFlag market={user.active_market} className="h-4 w-6 shadow-sm" />
        <ChevronDown className={`h-3 w-3 text-muted transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-48 overflow-hidden rounded-xl border border-line bg-white py-1.5 shadow-lg" role="menu" aria-label="Escolher ambiente">
          {user.allowed_markets.map(market => (
            <button
              key={market}
              type="button"
              role="menuitemradio"
              aria-checked={market === user.active_market}
              disabled={switching !== null}
              onClick={() => void choose(market)}
              className="flex min-h-11 w-full items-center gap-3 px-3.5 text-left text-sm text-ink hover:bg-bg-2 focus-visible:bg-bg-2 focus-visible:outline-none disabled:opacity-60"
            >
              <MarketFlag market={market} className="h-4 w-6 shadow-sm" />
              <span className="flex-1 font-medium">{LABELS[market]}</span>
              {market === user.active_market && <Check className="h-4 w-4 text-gold" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
