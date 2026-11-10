import { useEffect, useState } from 'react'
import { UserCheck } from 'lucide-react'
import { useClientsDashboard, type ClientContactFilter, type ClientContactRow } from '../hooks/useDashboard'
import { useCadastroText } from '../hooks/useCadastroText'

const PAGE_SIZE = 50

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

function ContactBadge({ contacted }: { contacted: boolean }) {
  const tx = useCadastroText()
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
        contacted ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'
      }`}
    >
      {contacted ? tx('Contactado') : tx('Não contactado')}
    </span>
  )
}

function mainContact(row: ClientContactRow, fallback: string) {
  return [row.contact_name, row.phone, row.email].filter(Boolean).join(' · ') || fallback
}

/**
 * Dashboard de Clientes (Portugal): quem já foi contactado e quem falta.
 * Contadores, filtro e busca vêm do servidor, que já limita a lista à carteira
 * do usuário (representante só vê os próprios clientes).
 */
export default function ClientesDashboardPage() {
  const tx = useCadastroText()
  const [filter, setFilter] = useState<ClientContactFilter>('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const debouncedQuery = useDebouncedValue(query.trim(), 300)
  // Mudou o filtro ou a busca: volta para a primeira página (durante o render,
  // sem efeito) — a página antiga pode nem existir no novo resultado.
  const resultKey = `${filter}|${debouncedQuery}`
  const [pageKey, setPageKey] = useState(resultKey)
  if (pageKey !== resultKey) {
    setPageKey(resultKey)
    setPage(0)
  }

  const { data, isLoading, isError } = useClientsDashboard({
    contacted: filter,
    q: debouncedQuery || undefined,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  })

  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil((data?.filtered_total ?? 0) / PAGE_SIZE))
  const filters: [ClientContactFilter, string][] = [
    ['all', tx('Todos')],
    ['yes', tx('Contactados')],
    ['no', tx('Não contactados')],
  ]
  const kpis: [string, string, number | string][] = [
    ['total', tx('Total de clientes'), total],
    ['contacted', tx('Contactados'), data?.contacted ?? 0],
    ['pending', tx('Não contactados'), data?.not_contacted ?? 0],
    ['pct', tx('% contactados'), `${(data?.contacted_pct ?? 0).toLocaleString('pt-PT', { maximumFractionDigits: 1 })}%`],
  ]

  return (
    <div className="min-h-screen bg-bg">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold text-ink flex items-center gap-2">
            <UserCheck className="w-6 h-6 text-gold" /> {tx('Clientes')}
          </h1>
          <p className="text-sm text-muted mt-1">{tx('Quem já foi contactado e quem ainda falta contactar.')}</p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 border border-line rounded-xl bg-white overflow-hidden mb-6" aria-label={tx('Indicadores')}>
          {kpis.map(([key, label, value], i) => (
            <div
              key={key}
              data-testid={`kpi-${key}`}
              className={`p-4 border-line ${i % 2 === 0 ? 'max-md:border-r' : ''} ${i < 2 ? 'max-md:border-b' : ''} ${i < 3 ? 'md:border-r' : ''}`}
            >
              <span className="text-xs text-muted">{label}</span>
              <strong className="block mt-2 text-xl text-ink tabular-nums">{value}</strong>
            </div>
          ))}
        </div>

        <div className="flex flex-col md:flex-row md:items-center gap-3 mb-4">
          <div role="group" aria-label={tx('Filtro de contacto')} className="inline-flex w-full md:w-auto p-1 rounded-xl border border-line bg-white">
            {filters.map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
                className={`flex-1 md:flex-none min-h-11 px-4 rounded-lg text-sm font-semibold transition-colors ${filter === value ? 'bg-gold text-white' : 'text-ink-2 hover:bg-bg'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            className="input md:max-w-xs md:ml-auto"
            type="search"
            aria-label={tx('Buscar por nome ou contato...')}
            placeholder={tx('Buscar por nome ou contato...')}
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>

        <div className="bg-white border border-line rounded-xl overflow-hidden">
          {isError ? (
            <p role="alert" className="py-10 text-center text-sm text-danger">{tx('Não foi possível carregar os clientes.')}</p>
          ) : isLoading ? (
            <p className="py-10 text-center text-sm text-muted">{tx('Carregando...')}</p>
          ) : (data?.items.length ?? 0) === 0 ? (
            <p className="py-10 text-center text-sm text-muted">{tx('Nenhum registro encontrado.')}</p>
          ) : (
            <>
              <table className="hidden md:table w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted uppercase tracking-wider border-b border-line">
                    <th className="py-3 px-4">{tx('Cliente')}</th>
                    <th className="py-3 px-4">{tx('Contato principal')}</th>
                    <th className="py-3 px-4">{tx('Representante')}</th>
                    <th className="py-3 px-4">{tx('Estado do contacto')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map(row => (
                    <tr key={row.id} className="border-t border-line first:border-t-0">
                      <td className="py-3 px-4">
                        <span className="block font-medium text-ink">{row.name}</span>
                        <span className="block text-xs text-muted">{[row.city, row.country].filter(Boolean).join(', ')}</span>
                      </td>
                      <td className="py-3 px-4 text-ink-2">{mainContact(row, tx('Não informado'))}</td>
                      <td className="py-3 px-4 text-ink-2">{row.rep_name ?? tx('Sem representante')}</td>
                      <td className="py-3 px-4"><ContactBadge contacted={row.contacted} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="md:hidden divide-y divide-line">
                {data?.items.map(row => (
                  <li key={row.id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <span className="font-medium text-ink break-words min-w-0">{row.name}</span>
                      <ContactBadge contacted={row.contacted} />
                    </div>
                    <p className="mt-1 text-xs text-muted">{[row.city, row.country].filter(Boolean).join(', ')}</p>
                    <p className="mt-2 text-xs text-ink-2 break-words">{mainContact(row, tx('Não informado'))}</p>
                    <p className="mt-0.5 text-xs text-muted-2">{tx('Representante')}: {row.rep_name ?? tx('Sem representante')}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {pages > 1 && (
          <div className="flex items-center justify-between mt-4 text-sm text-ink-2">
            <button type="button" className="min-h-11 px-4 border border-line rounded-xl disabled:opacity-50" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
              {tx('Anterior')}
            </button>
            <span>{tx('Página')} {page + 1} {tx('de')} {pages}</span>
            <button type="button" className="min-h-11 px-4 border border-line rounded-xl disabled:opacity-50" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>
              {tx('Próximo')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
