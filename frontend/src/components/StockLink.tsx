import { useState } from 'react'
import { Boxes } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useStockLink } from '../hooks/useStockLink'
import { listenForStockReady, openStockWindow } from '../lib/stockHandoff'

interface StockLinkProps {
  variant: 'desktop' | 'mobile'
  className?: string
}

/**
 * Link "Estoque" do menu. Aparece só na sessão do mercado Brasil e só quando o
 * servidor confirmou (`can_access_stock`) E devolveu a origem do Estoque
 * (`/stock/link`); 403/503 escondem o item. É um botão, não um NavLink: o
 * clique abre o Estoque com `window.open` (mantendo `opener`) e responde ao
 * `postMessage` do Estoque com a autorização.
 */
export function StockLink({ variant, className = '' }: StockLinkProps) {
  const { user } = useAuth()
  const visible = Boolean(
    user && user.active_market === 'BR' && user.can_access_stock && !user.must_change_password,
  )
  const link = useStockLink(user?.id, visible)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!visible || !link.data) return null
  const origin = link.data

  function handleClick() {
    setError(null)
    setBusy(true)
    try {
      const popup = openStockWindow(origin)
      listenForStockReady({
        origin,
        popup,
        onSent: () => setBusy(false),
        onError: () => {
          setBusy(false)
          setError('Não foi possível entrar no Estoque agora.')
        },
      })
      // Evita cliques repetidos enquanto a janela abre; depois libera o botão.
      window.setTimeout(() => setBusy(false), 5_000)
    } catch (err) {
      setBusy(false)
      setError(err instanceof Error ? err.message : 'Não foi possível abrir o Estoque.')
    }
  }

  const errorNote = error ? (
    <span role="alert" className="text-[11px] font-medium text-terracotta">{error}</span>
  ) : null

  if (variant === 'mobile') {
    return (
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        aria-label="Estoque"
        className={`flex shrink-0 flex-col items-center gap-0.5 min-w-[60px] min-h-[44px] justify-center px-2 text-muted-3 transition-colors ${className}`}
      >
        <Boxes className="w-5 h-5" />
        <span className="text-[11px] font-semibold uppercase tracking-wider">Estoque</span>
        {errorNote}
      </button>
    )
  }
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={handleClick} disabled={busy} aria-label="Estoque" className={className}>
        Estoque
      </button>
      {errorNote}
    </span>
  )
}
