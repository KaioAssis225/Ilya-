import { useState, useMemo, useCallback, useEffect } from 'react'
import { Download, LayoutDashboard } from 'lucide-react'
import { useDashboardOverview, DASHBOARD_REGIONS } from '../hooks/useDashboard'
import { useRepresentative, useRepresentativesPage } from '../hooks/useRepresentatives'
import DashboardIntro from '../components/DashboardIntro'

const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const integer = new Intl.NumberFormat('pt-BR')

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

function fmtCompact(v: number) {
  if (v >= 1e6) return `R$ ${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
  if (v >= 1e3) return `R$ ${Math.round(v / 1e3)} mil`
  return currency.format(v)
}

function fmtAxis(key: string, granularity: string) {
  if (granularity === 'month') {
    const [y, m] = key.split('-')
    return `${m}/${y.slice(2)}`
  }
  const d = new Date(key + 'T12:00:00')
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit' }).format(d)
}

function todayISO(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}

type MetricKey = 'revenue_total' | 'revenue_finalized' | 'revenue_open' | 'revenue_cancelled' | 'orders_total' | 'orders_finalized' | 'orders_open' | 'orders_cancelled'

const METRIC_CONFIG: Record<MetricKey, { label: string; small: string; kind: 'revenue' | 'orders' }> = {
  revenue_total: { label: 'Receita total', small: 'Todos os pedidos', kind: 'revenue' },
  revenue_finalized: { label: 'Receita finalizada', small: 'Pedidos faturados', kind: 'revenue' },
  revenue_open: { label: 'Receita em aberto', small: 'Aguardando finalização', kind: 'revenue' },
  revenue_cancelled: { label: 'Receita cancelada', small: 'Cancelamentos totais', kind: 'revenue' },
  orders_total: { label: 'Pedidos total', small: 'Todos os status', kind: 'orders' },
  orders_finalized: { label: 'Pedidos finalizados', small: 'Faturados', kind: 'orders' },
  orders_open: { label: 'Pedidos em aberto', small: 'Aguardando finalização', kind: 'orders' },
  orders_cancelled: { label: 'Pedidos cancelados', small: 'Cancelados totalmente', kind: 'orders' },
}

function DashboardChart({ series, activeMetric, granularity }: {
  series: { key: string; revenue: number; orders: number }[]
  activeMetric: MetricKey
  granularity: string
}) {
  const kind = METRIC_CONFIG[activeMetric].kind
  const values = series.map(p => (kind === 'revenue' ? p.revenue : p.orders))
  const max = Math.max(...values, 1) * 1.15
  const width = 1000, height = 260, left = 64, top = 20

  if (series.length === 0) {
    return <p className="py-16 text-center text-sm text-muted">Nenhum pedido encontrado para os filtros selecionados.</p>
  }

  const step = series.length === 1 ? width : width / (series.length - 1)
  const coords = values.map((v, i) => [left + i * step, top + height - (v / max) * height])
  const showEvery = Math.max(1, Math.ceil(series.length / 7))

  return (
    <svg viewBox={`0 0 ${left + width + 20} ${height + top + 50}`} className="w-full h-auto max-h-[340px]" role="img" aria-label={`Gráfico de ${METRIC_CONFIG[activeMetric].label}`}>
      {[0, 1, 2, 3, 4].map(i => {
        const y = top + (height / 4) * i
        const value = max - (max / 4) * i
        return (
          <g key={i}>
            <line x1={left} y1={y} x2={left + width} y2={y} stroke="#e8e0d6" strokeWidth={1} />
            <text x={4} y={y + 4} fontSize={11} fill="#9d8d81">{kind === 'revenue' ? fmtCompact(value) : integer.format(Math.round(value))}</text>
          </g>
        )
      })}
      {series.map((p, i) => (
        (i % showEvery === 0 || i === series.length - 1) && (
          <text key={p.key} x={coords[i][0]} y={height + top + 24} textAnchor="middle" fontSize={11} fill="#9d8d81">
            {fmtAxis(p.key, granularity)}
          </text>
        )
      ))}
      {kind === 'revenue' ? (
        <>
          <path
            d={`${coords.map((c, i) => `${i ? 'L' : 'M'}${c[0]} ${c[1]}`).join(' ')} L${coords.at(-1)![0]} ${top + height} L${coords[0][0]} ${top + height} Z`}
            fill="#8b691418"
          />
          <path d={coords.map((c, i) => `${i ? 'L' : 'M'}${c[0]} ${c[1]}`).join(' ')} fill="none" stroke="#8b6914" strokeWidth={3} />
          {coords.map((c, i) => <circle key={i} cx={c[0]} cy={c[1]} r={4} fill="#8b6914" />)}
        </>
      ) : (
        coords.map((c, i) => {
          const barWidth = Math.min(48, (width / series.length) * 0.65)
          return <rect key={i} x={c[0] - barWidth / 2} y={c[1]} width={barWidth} height={top + height - c[1]} rx={3} fill="#8b6914" />
        })
      )}
    </svg>
  )
}

export default function DashboardPage() {
  const [startDate, setStartDate] = useState(todayISO(-29))
  const [endDate, setEndDate] = useState(todayISO())
  const [repId, setRepId] = useState('')
  const [repQuery, setRepQuery] = useState('')
  const [region, setRegion] = useState('')
  const [activeMetric, setActiveMetric] = useState<MetricKey>('revenue_total')
  const [repsExpanded, setRepsExpanded] = useState(false)
  const [productsExpanded, setProductsExpanded] = useState(false)
  // Bloco 95: animação de entrada toda vez que a página monta (toda vez que
  // o usuário entra no módulo), não apenas na primeira visita da sessão.
  const [showIntro, setShowIntro] = useState(true)
  const hideIntro = useCallback(() => setShowIntro(false), [])

  const debouncedRepQuery = useDebouncedValue(repQuery.trim(), 300)
  const { data: repsPage, isFetching: repsLoading } = useRepresentativesPage({
    skip: 0,
    limit: 20,
    q: debouncedRepQuery || undefined,
    include_total: false,
    sort_by: 'name',
    sort_dir: 'asc',
  })
  const { data: selectedRep } = useRepresentative(repId, !!repId)
  const reps = [
    ...(selectedRep ? [selectedRep] : []),
    ...(repsPage?.items ?? []).filter((rep) => rep.id !== selectedRep?.id),
  ]
  const { data, isLoading } = useDashboardOverview({ start_date: startDate, end_date: endDate, rep_id: repId || undefined, region: region || undefined })

  const chartTotal = useMemo(() => {
    if (!data) return 0
    const kind = METRIC_CONFIG[activeMetric].kind
    return data.chart.reduce((sum, p) => sum + (kind === 'revenue' ? p.revenue : p.orders), 0)
  }, [data, activeMetric])

  function clearFilters() {
    setStartDate(todayISO(-29))
    setEndDate(todayISO())
    setRepId('')
    setRepQuery('')
    setRegion('')
  }

  function exportCsv() {
    if (!data) return
    const lines = [
      'Métrica;Valor',
      `Receita total;${data.metrics.revenue_total}`,
      `Receita finalizada;${data.metrics.revenue_finalized}`,
      `Receita em aberto;${data.metrics.revenue_open}`,
      `Receita cancelada;${data.metrics.revenue_cancelled}`,
      `Pedidos total;${data.metrics.orders_total}`,
      `Pedidos finalizados;${data.metrics.orders_finalized}`,
      `Pedidos em aberto;${data.metrics.orders_open}`,
      `Pedidos cancelados;${data.metrics.orders_cancelled}`,
      '',
      'Representante;Pedidos;Receita',
      ...data.representatives.map(r => `${r.name};${r.orders};${r.revenue}`),
      '',
      'Código;Descrição;Quantidade;Receita',
      ...data.products.map(p => `${p.product_code};${p.description};${p.quantity};${p.revenue}`),
    ]
    const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `dashboard-bi_${startDate}_${endDate}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="min-h-screen bg-bg">
      {showIntro && (
        <DashboardIntro
          revenueTotal={data ? data.metrics.revenue_total : null}
          ordersTotal={data ? data.metrics.orders_total : null}
          onDone={hideIntro}
        />
      )}
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-ink flex items-center gap-2" style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}>
              <LayoutDashboard className="w-6 h-6 text-gold" /> Dashboard BI Comercial
            </h2>
            <p className="text-sm text-muted mt-1">Receitas e pedidos consolidados</p>
          </div>
          <button
            onClick={exportCsv}
            disabled={!data}
            className="flex items-center gap-2 px-4 py-2 border border-line text-ink-2 rounded-xl text-sm font-medium hover:bg-white transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" /> Exportar CSV
          </button>
        </div>

        {/* Filtros */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end mb-2">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted font-semibold">Data inicial</span>
            <input type="date" className="input" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted font-semibold">Data final</span>
            <input type="date" className="input" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted font-semibold">Região</span>
            <select className="input" value={region} onChange={e => setRegion(e.target.value)}>
              <option value="">Todas</option>
              {DASHBOARD_REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 col-span-2 md:col-span-1">
            <span className="text-xs text-muted font-semibold">Representante</span>
            <input
              className="input"
              placeholder="Buscar..."
              value={repQuery}
              onChange={e => setRepQuery(e.target.value)}
            />
            <select className="input" value={repId} onChange={e => setRepId(e.target.value)}>
              <option value="">Todos</option>
              {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            {repsLoading && <span className="text-[11px] text-muted">Buscando…</span>}
          </label>
          <button onClick={clearFilters} className="text-xs text-gold hover:underline text-left md:text-center py-2">Limpar filtros</button>
        </div>
        {data && (
          <p className="text-right text-[11px] text-muted mb-4">
            {new Date(data.start_date + 'T12:00:00').toLocaleDateString('pt-BR')} a {new Date(data.end_date + 'T12:00:00').toLocaleDateString('pt-BR')}
            {region && ` · ${region}`}
            {repId && ` · ${selectedRep?.name ?? reps.find(r => r.id === repId)?.name ?? ''}`}
          </p>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 border border-line rounded-xl bg-white overflow-hidden mb-6">
          {(Object.keys(METRIC_CONFIG) as MetricKey[]).map((key, i) => {
            const config = METRIC_CONFIG[key]
            const value = data?.metrics[key] ?? 0
            const selected = activeMetric === key
            return (
              <button
                key={key}
                onClick={() => setActiveMetric(key)}
                className={`text-left p-4 border-line ${i % 4 !== 3 ? 'border-r' : ''} ${i < 4 ? 'border-b' : ''} transition-colors ${selected ? 'bg-[#fdf9f0]' : 'hover:bg-bg'}`}
                style={selected ? { boxShadow: 'inset 0 3px #8b6914' } : undefined}
              >
                <span className="text-xs text-muted">{config.label}</span>
                <strong className="block my-2 text-xl text-ink tabular-nums">
                  {config.kind === 'revenue' ? currency.format(value) : integer.format(value)}
                </strong>
                <small className="text-[11px] text-muted">{config.small}</small>
              </button>
            )
          })}
        </div>

        {/* Gráfico */}
        <div className="bg-white border border-line rounded-xl p-4 md:p-5 mb-6">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <h3 className="text-base font-semibold text-ink">{METRIC_CONFIG[activeMetric].label}</h3>
              <p className="text-xs text-muted mt-0.5">
                Evolução {data?.granularity === 'day' ? 'diária' : data?.granularity === 'week' ? 'semanal' : 'mensal'} em {METRIC_CONFIG[activeMetric].kind === 'revenue' ? 'reais' : 'número de pedidos'}
              </p>
            </div>
            <span className="text-gold font-bold text-base whitespace-nowrap">
              {METRIC_CONFIG[activeMetric].kind === 'revenue' ? currency.format(chartTotal) : `${integer.format(chartTotal)} pedidos`}
            </span>
          </div>
          {isLoading ? (
            <p className="py-16 text-center text-sm text-muted">Carregando…</p>
          ) : (
            <DashboardChart series={data?.chart ?? []} activeMetric={activeMetric} granularity={data?.granularity ?? 'day'} />
          )}
        </div>

        {/* Tabelas de ranking */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white border border-line rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-ink">Desempenho por Representante</h3>
                <p className="text-[11px] text-muted mt-0.5">Pedidos e receita no período filtrado</p>
              </div>
              {(data?.representatives.length ?? 0) > 5 && (
                <button onClick={() => setRepsExpanded(v => !v)} className="text-xs text-gold hover:underline flex-shrink-0">
                  {repsExpanded ? 'Mostrar 5' : 'Detalhar'}
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] text-muted uppercase tracking-wider">
                    <th className="py-2">Nome</th>
                    <th className="py-2 text-right">Pedidos</th>
                    <th className="py-2 text-right">Receita</th>
                  </tr>
                </thead>
                <tbody>
                  {(repsExpanded ? data?.representatives : data?.representatives.slice(0, 5))?.map(r => (
                    <tr key={r.name} className="border-t border-line">
                      <td className="py-2 text-ink">{r.name}</td>
                      <td className="py-2 text-right text-ink-2 tabular-nums">{integer.format(r.orders)}</td>
                      <td className="py-2 text-right text-ink font-medium tabular-nums">{currency.format(r.revenue)}</td>
                    </tr>
                  ))}
                  {!data?.representatives.length && (
                    <tr><td colSpan={3} className="py-6 text-center text-muted text-xs">Nenhum resultado</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white border border-line rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-ink">Desempenho por Produto</h3>
                <p className="text-[11px] text-muted mt-0.5">Quantidade e receita no período filtrado</p>
              </div>
              {(data?.products.length ?? 0) > 5 && (
                <button onClick={() => setProductsExpanded(v => !v)} className="text-xs text-gold hover:underline flex-shrink-0">
                  {productsExpanded ? 'Mostrar 5' : 'Detalhar'}
                </button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] text-muted uppercase tracking-wider">
                    <th className="py-2">Código</th>
                    <th className="py-2">Descrição</th>
                    <th className="py-2 text-right">Qtd.</th>
                    <th className="py-2 text-right">Receita</th>
                  </tr>
                </thead>
                <tbody>
                  {(productsExpanded ? data?.products : data?.products.slice(0, 5))?.map(p => (
                    <tr key={p.product_code} className="border-t border-line">
                      <td className="py-2 font-mono text-xs text-gold">{p.product_code}</td>
                      <td className="py-2 text-ink truncate max-w-[160px]">{p.description}</td>
                      <td className="py-2 text-right text-ink-2 tabular-nums">{integer.format(p.quantity)}</td>
                      <td className="py-2 text-right text-ink font-medium tabular-nums">{currency.format(p.revenue)}</td>
                    </tr>
                  ))}
                  {!data?.products.length && (
                    <tr><td colSpan={4} className="py-6 text-center text-muted text-xs">Nenhum resultado</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
