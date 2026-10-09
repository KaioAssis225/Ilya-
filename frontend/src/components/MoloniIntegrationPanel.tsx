import { useEffect, useState } from 'react'
import platformApi from '../lib/platformApi'

type MoloniStatus = {
  configured: boolean
  active: boolean
  enabled: boolean
  company_id: number | null
  jobs: Record<'pending' | 'processing' | 'delivered' | 'dead_letter', number>
  tax_mappings: Array<{ vat_rate: string; moloni_tax_id: number }>
}

type MappingDraft = { vat_rate: string; moloni_tax_id: string }

function detail(error: unknown, fallback: string) {
  const value = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof value === 'string' ? value : fallback
}

export default function MoloniIntegrationPanel() {
  const [status, setStatus] = useState<MoloniStatus | null>(null)
  const [companyId, setCompanyId] = useState('')
  const [mappings, setMappings] = useState<MappingDraft[]>([{ vat_rate: '23', moloni_tax_id: '' }])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function load() {
    const response = await platformApi.get<MoloniStatus>('/integrations/moloni/status')
    setStatus(response.data)
    if (response.data.company_id) setCompanyId(String(response.data.company_id))
    if (response.data.tax_mappings.length) {
      setMappings(response.data.tax_mappings.map(item => ({ vat_rate: item.vat_rate, moloni_tax_id: String(item.moloni_tax_id) })))
    }
  }

  useEffect(() => { load().catch(() => setError('Não foi possível carregar a integração Moloni.')) }, [])

  async function connect() {
    setBusy(true); setError(null); setNotice(null)
    try {
      const response = await platformApi.post<{ authorization_url: string }>('/integrations/moloni/connect', { company_id: Number(companyId) })
      window.location.assign(response.data.authorization_url)
    } catch (requestError) {
      setError(detail(requestError, 'Não foi possível iniciar a conexão Moloni.'))
      setBusy(false)
    }
  }

  async function saveMappings() {
    setBusy(true); setError(null); setNotice(null)
    try {
      await platformApi.put('/integrations/moloni/tax-mappings', {
        mappings: mappings.map(item => ({ vat_rate: Number(item.vat_rate), moloni_tax_id: Number(item.moloni_tax_id) })),
      })
      setNotice('Mapeamento de IVA salvo.')
      await load()
    } catch (requestError) {
      setError(detail(requestError, 'Não foi possível salvar os impostos Moloni.'))
    } finally { setBusy(false) }
  }

  return <section className="rounded-2xl border border-line bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="font-semibold text-ink">Moloni · pedidos EU</h2><p className="mt-1 text-xs text-muted">O Ilya cria um orçamento em rascunho no Moloni para cada pedido EU finalizado.</p></div>
      <span className={status?.active && status?.enabled ? 'text-sm text-emerald-700' : 'text-sm text-muted'}>{status?.active && status?.enabled ? 'Pronto para configurar' : 'Ainda não conectado'}</span>
    </div>
    {error && <p className="mt-4 rounded-xl border border-terracotta/30 bg-white p-3 text-sm text-terracotta">{error}</p>}
    {notice && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
    {!status?.active && <div className="mt-4 flex flex-wrap items-end gap-3"><label className="flex min-w-56 flex-col gap-1"><span className="text-xs text-muted">ID da empresa Moloni</span><input className="input" inputMode="numeric" value={companyId} onChange={event => setCompanyId(event.target.value)} /></label><button className="btn-primary" disabled={busy || !Number(companyId)} onClick={connect}>{busy ? 'Abrindo…' : 'Conectar Moloni'}</button></div>}
    {status?.active && <div className="mt-5 space-y-4">
      <div className="rounded-xl bg-surface-2 p-4 text-sm"><strong>Empresa conectada:</strong> {status.company_id}<br /><span className="text-muted">Fila: pendentes {status.jobs.pending} · enviados {status.jobs.delivered} · com falha {status.jobs.dead_letter}</span></div>
      <div><h3 className="font-medium text-ink">Mapeamento fiscal</h3><p className="mt-1 text-xs text-muted">Informe o ID do imposto já criado no Moloni para cada IVA utilizado pelos produtos EU.</p></div>
      <div className="space-y-2">{mappings.map((mapping, index) => <div key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><label className="flex flex-col gap-1"><span className="text-xs text-muted">IVA (%)</span><input className="input" inputMode="decimal" value={mapping.vat_rate} onChange={event => setMappings(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, vat_rate: event.target.value } : row))} /></label><label className="flex flex-col gap-1"><span className="text-xs text-muted">ID de imposto Moloni</span><input className="input" inputMode="numeric" value={mapping.moloni_tax_id} onChange={event => setMappings(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, moloni_tax_id: event.target.value } : row))} /></label><button className="self-end min-h-11 text-sm text-terracotta" disabled={mappings.length === 1} onClick={() => setMappings(rows => rows.filter((_, rowIndex) => rowIndex !== index))}>Remover</button></div>)}</div>
      <div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => setMappings(rows => [...rows, { vat_rate: '', moloni_tax_id: '' }])}>Adicionar IVA</button><button className="btn-primary" disabled={busy || mappings.some(item => !Number(item.vat_rate) && item.vat_rate !== '0' || !Number(item.moloni_tax_id))} onClick={saveMappings}>{busy ? 'Salvando…' : 'Salvar impostos'}</button></div>
    </div>}
  </section>
}
