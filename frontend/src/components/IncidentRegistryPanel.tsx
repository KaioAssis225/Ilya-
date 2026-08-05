import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Plus, X } from 'lucide-react'
import api from '../lib/api'

type IncidentStatus = 'investigating' | 'contained' | 'closed'

type PrivacyIncident = {
  id: string
  known_at: string
  status: IncidentStatus
  description: string
  data_categories: string[]
  affected_subjects_count: number | null
  risk_assessment: string
  mitigation_measures: string
  anpd_notified: boolean
  subjects_notified: boolean
  notification_details: string | null
  non_notification_reason: string | null
  closed_at: string | null
  retain_until: string
  created_at: string
}

const STATUS_LABEL: Record<IncidentStatus, string> = {
  investigating: 'Em investigação',
  contained: 'Contido',
  closed: 'Encerrado',
}

const EMPTY_FORM = {
  known_at: '',
  description: '',
  data_categories: '',
  affected_subjects_count: '',
  risk_assessment: '',
  mitigation_measures: '',
  anpd_notified: false,
  subjects_notified: false,
  notification_details: '',
  non_notification_reason: '',
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function errorDetail(error: unknown, fallback: string) {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

export default function IncidentRegistryPanel() {
  const [incidents, setIncidents] = useState<PrivacyIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [closingIncident, setClosingIncident] = useState<PrivacyIncident | null>(null)
  const [rootCause, setRootCause] = useState('')
  const [correctiveActions, setCorrectiveActions] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.get<PrivacyIncident[]>('/privacy/incidents')
      setIncidents(response.data)
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível carregar os incidentes.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function showNotice(message: string) {
    setNotice(message)
    window.setTimeout(() => setNotice(null), 4000)
  }

  async function createIncident(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.post('/privacy/incidents', {
        ...form,
        known_at: new Date(form.known_at).toISOString(),
        data_categories: form.data_categories
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        affected_subjects_count: form.affected_subjects_count
          ? Number(form.affected_subjects_count)
          : null,
        notification_details: form.notification_details || null,
        non_notification_reason: form.non_notification_reason || null,
      })
      setShowForm(false)
      setForm(EMPTY_FORM)
      await load()
      showNotice('Incidente registrado e retenção mínima de cinco anos aplicada.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível registrar o incidente.'))
    } finally {
      setSaving(false)
    }
  }

  async function changeStatus(incident: PrivacyIncident, status: IncidentStatus) {
    setSaving(true)
    setError(null)
    try {
      await api.patch(`/privacy/incidents/${incident.id}`, { status })
      await load()
      showNotice(`Incidente marcado como ${STATUS_LABEL[status].toLowerCase()}.`)
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível atualizar o incidente.'))
    } finally {
      setSaving(false)
    }
  }

  async function closeIncident(event: React.FormEvent) {
    event.preventDefault()
    if (!closingIncident) return
    setSaving(true)
    setError(null)
    try {
      await api.patch(`/privacy/incidents/${closingIncident.id}`, {
        status: 'closed',
        root_cause: rootCause,
        corrective_actions: correctiveActions,
      })
      setClosingIncident(null)
      setRootCause('')
      setCorrectiveActions('')
      await load()
      showNotice('Incidente encerrado com causa raiz e ações corretivas registradas.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível encerrar o incidente.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="mt-8 space-y-4" aria-labelledby="incident-registry-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="incident-registry-heading" className="flex items-center gap-2 text-xl font-semibold text-ink">
            <AlertTriangle className="h-5 w-5 text-terracotta" />
            Registro de incidentes LGPD
          </h2>
          <p className="mt-1 text-sm text-muted">
            Incidentes comunicados ou não devem permanecer registrados por pelo menos cinco anos.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setForm(EMPTY_FORM)
            setError(null)
            setShowForm(true)
          }}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="h-4 w-4" /> Registrar incidente
        </button>
      </div>

      {error && <p role="alert" className="rounded-lg bg-terracotta/10 px-4 py-3 text-sm text-terracotta">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-olive/10 px-4 py-3 text-sm text-olive">{notice}</p>}

      <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
        {loading ? (
          <p className="py-6 text-center text-sm text-muted">Carregando incidentes…</p>
        ) : incidents.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">Nenhum incidente registrado.</p>
        ) : (
          <div className="space-y-3">
            {incidents.map((incident) => (
              <article key={incident.id} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Ciência em {formatDate(incident.known_at)}
                    </p>
                    <p className="mt-1 text-sm text-ink">{incident.description}</p>
                    <p className="mt-2 text-xs text-muted">
                      Dados: {incident.data_categories.join(', ')} · Titulares: {incident.affected_subjects_count ?? 'em apuração'}
                    </p>
                  </div>
                  <span className="rounded-full bg-mineral/10 px-2.5 py-1 text-xs font-semibold text-mineral">
                    {STATUS_LABEL[incident.status]}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-ink-2 md:grid-cols-2">
                  <p><strong>Risco:</strong> {incident.risk_assessment}</p>
                  <p><strong>Mitigação:</strong> {incident.mitigation_measures}</p>
                  <p>ANPD: {incident.anpd_notified ? 'comunicada' : 'não comunicada'}</p>
                  <p>Titulares: {incident.subjects_notified ? 'comunicados' : 'não comunicados'}</p>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
                  <span className="text-[11px] text-muted">
                    Guarda mínima até {formatDate(incident.retain_until)}
                  </span>
                  <div className="flex gap-2">
                    {incident.status === 'investigating' && (
                      <button type="button" disabled={saving} onClick={() => changeStatus(incident, 'contained')} className="btn-secondary text-xs">
                        Marcar contido
                      </button>
                    )}
                    {incident.status !== 'closed' && (
                      <button type="button" disabled={saving} onClick={() => {
                        setClosingIncident(incident)
                        setRootCause('')
                        setCorrectiveActions('')
                        setError(null)
                      }} className="btn-secondary flex items-center gap-1 text-xs">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Encerrar
                      </button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-scrim/60 px-4 py-8 backdrop-blur-sm">
          <form onSubmit={createIncident} className="w-full max-w-2xl space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Registrar incidente com dados pessoais</h3>
              <button type="button" onClick={() => setShowForm(false)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Data e hora da ciência *</span>
              <input className="input" type="datetime-local" max={new Date().toISOString().slice(0, 16)} value={form.known_at} onChange={(event) => setForm({ ...form, known_at: event.target.value })} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Descrição geral das circunstâncias *</span>
              <textarea className="input min-h-24" minLength={10} maxLength={5000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Categorias de dados, separadas por vírgula *</span>
                <input className="input" value={form.data_categories} onChange={(event) => setForm({ ...form, data_categories: event.target.value })} placeholder="contato, endereço, pedidos" required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Quantidade de titulares</span>
                <input className="input" type="number" min="0" value={form.affected_subjects_count} onChange={(event) => setForm({ ...form, affected_subjects_count: event.target.value })} />
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Avaliação de risco e possíveis danos *</span>
              <textarea className="input min-h-20" minLength={10} maxLength={5000} value={form.risk_assessment} onChange={(event) => setForm({ ...form, risk_assessment: event.target.value })} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Medidas de correção e mitigação *</span>
              <textarea className="input min-h-20" minLength={5} maxLength={5000} value={form.mitigation_measures} onChange={(event) => setForm({ ...form, mitigation_measures: event.target.value })} required />
            </label>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={form.anpd_notified} onChange={(event) => setForm({ ...form, anpd_notified: event.target.checked })} className="h-4 w-4 accent-gold" />
                ANPD comunicada
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={form.subjects_notified} onChange={(event) => setForm({ ...form, subjects_notified: event.target.checked })} className="h-4 w-4 accent-gold" />
                Titulares comunicados
              </label>
            </div>
            {(form.anpd_notified || form.subjects_notified) ? (
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Forma, data e conteúdo das comunicações *</span>
                <textarea className="input min-h-20" maxLength={5000} value={form.notification_details} onChange={(event) => setForm({ ...form, notification_details: event.target.value })} required />
              </label>
            ) : (
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Motivo da ausência de comunicação *</span>
                <textarea className="input min-h-20" maxLength={5000} value={form.non_notification_reason} onChange={(event) => setForm({ ...form, non_notification_reason: event.target.value })} required />
              </label>
            )}
            <p className="text-xs text-muted">
              Registre referências de evidências, não senhas, tokens, documentos completos ou dados pessoais desnecessários.
            </p>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Registrando…' : 'Registrar incidente'}</button>
            </div>
          </form>
        </div>
      )}

      {closingIncident && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 px-4 backdrop-blur-sm">
          <form onSubmit={closeIncident} className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Encerrar incidente</h3>
              <button type="button" onClick={() => setClosingIncident(null)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <p className="text-sm text-ink-2">{closingIncident.description}</p>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Causa raiz *</span>
              <textarea className="input min-h-24" minLength={5} maxLength={5000} value={rootCause} onChange={(event) => setRootCause(event.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Ações corretivas, responsáveis e prazos *</span>
              <textarea className="input min-h-24" minLength={5} maxLength={5000} value={correctiveActions} onChange={(event) => setCorrectiveActions(event.target.value)} required />
            </label>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setClosingIncident(null)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Encerrando…' : 'Encerrar incidente'}</button>
            </div>
          </form>
        </div>
      )}
    </section>
  )
}
