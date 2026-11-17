import { useEffect, useState } from 'react'
import type { AxiosInstance } from 'axios'
import { Percent } from 'lucide-react'
import api from '../lib/api'
import platformApi from '../lib/platformApi'
import { formatRate, parseRateInput } from '../lib/euVatRate'
import type { EuVatRateView } from '../lib/euVatRate'

type Scope = 'market' | 'platform'

const ENDPOINT: Record<Scope, string> = {
  market: '/markets/EU/vat-rate',
  platform: '/markets/EU/vat-rate/platform',
}

function client(scope: Scope): AxiosInstance {
  return scope === 'platform' ? platformApi : api
}

function detail(error: unknown, fallback: string) {
  const value = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof value === 'string' ? value : fallback
}

function formatDate(iso: string) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

/**
 * Tela única do IVA de Portugal: uma taxa só, aplicada apenas no total final
 * do orçamento/pedido. Fica na Administração do EU e na Plataforma. O servidor
 * decide quem pode alterar; aqui só se esconde o botão de quem não pode.
 */
export default function EuVatRatePanel({ scope }: { scope: Scope }) {
  const [view, setView] = useState<EuVatRateView | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const response = await client(scope).get<EuVatRateView>(ENDPOINT[scope])
        if (cancelled) return
        setView(response.data)
        setDraft(response.data.vat_rate === null ? '' : String(Number(response.data.vat_rate)))
      } catch (requestError) {
        if (!cancelled) setError(detail(requestError, 'Não foi possível carregar a taxa de IVA.'))
      }
    })()
    return () => { cancelled = true }
  }, [scope])

  const parsed = parseRateInput(draft)
  const unchanged = view?.vat_rate != null && parsed !== null && Number(view.vat_rate) === parsed

  async function save() {
    if (parsed === null || !view) return
    const message = `Alterar o IVA de ${formatRate(view.vat_rate)} para ${formatRate(parsed)}? `
      + 'Vale para orçamentos novos ou recalculados; pedidos já finalizados não mudam.'
    if (!window.confirm(message)) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const response = await client(scope).put<EuVatRateView>(ENDPOINT[scope], { vat_rate: parsed })
      setView(response.data)
      setDraft(String(Number(response.data.vat_rate)))
      setNotice('Taxa de IVA salva.')
    } catch (requestError) {
      setError(detail(requestError, 'Não foi possível salvar a taxa de IVA.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mb-6 rounded-2xl border border-line bg-white p-5 shadow-sm" aria-labelledby={`eu-vat-title-${scope}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`eu-vat-title-${scope}`} className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Percent className="h-4 w-4 text-gold" aria-hidden="true" /> IVA de Portugal (taxa única)
          </h2>
          <p className="mt-1 max-w-xl text-xs text-muted">
            O IVA é cobrado uma só vez, sobre o total do orçamento ou pedido (já com os descontos). Não existe IVA por produto.
            Pedidos finalizados guardam a taxa que usaram e não mudam quando a taxa é alterada.
          </p>
        </div>
        <div className="text-right">
          <span className="block text-xs text-muted">Taxa atual</span>
          <strong className="font-display text-2xl text-ink" data-testid="eu-vat-current">{formatRate(view?.vat_rate)}</strong>
        </div>
      </div>

      {view?.can_edit && (
        <form
          className="mt-4 flex flex-wrap items-end gap-3"
          onSubmit={(event) => { event.preventDefault(); void save() }}
        >
          <label className="flex flex-col gap-1 text-xs text-muted">
            Taxa de IVA (%)
            <input
              className="input w-36"
              inputMode="decimal"
              value={draft}
              onChange={(event) => { setDraft(event.target.value); setNotice(null) }}
              aria-invalid={draft !== '' && parsed === null}
              aria-describedby={`eu-vat-help-${scope}`}
            />
          </label>
          <button type="submit" className="btn-primary" disabled={busy || parsed === null || unchanged}>
            {busy ? 'Salvando…' : 'Salvar'}
          </button>
          <span id={`eu-vat-help-${scope}`} className="text-xs text-muted">Entre 0 e 100, com até duas casas decimais.</span>
        </form>
      )}

      {error && <p role="alert" className="mt-3 text-sm font-medium text-danger">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-olive">{notice}</p>}

      {view?.can_edit && view.history.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[420px] text-xs">
            <caption className="mb-1 text-left font-semibold text-ink">Últimas alterações</caption>
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 text-left font-medium">Quando</th>
                <th className="py-1 pr-3 text-left font-medium">Quem</th>
                <th className="py-1 text-left font-medium">De → Para</th>
              </tr>
            </thead>
            <tbody>
              {view.history.map((event, index) => (
                <tr key={`${event.changed_at}-${index}`} className="border-t border-line">
                  <td className="py-1 pr-3 text-ink-2">{formatDate(event.changed_at)}</td>
                  <td className="py-1 pr-3 text-ink-2">{event.changed_by ?? '—'}</td>
                  <td className="py-1 tabular-nums text-ink-2">{formatRate(event.old_rate)} → {formatRate(event.new_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
