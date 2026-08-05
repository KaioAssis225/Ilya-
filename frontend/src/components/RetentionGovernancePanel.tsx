import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  FileCheck2,
  FileSearch,
  LockKeyhole,
  Plus,
  ShieldAlert,
  UnlockKeyhole,
  UserRoundX,
  X,
} from 'lucide-react'
import api from '../lib/api'

type HoldSubjectType = 'client' | 'representative' | 'order'
type CandidateSubjectType =
  | HoldSubjectType
  | 'notification'
  | 'signature_invitation'
  | 'integration_outbox'
  | 'privacy_event'

type LegalHold = {
  id: string
  subject_type: HoldSubjectType
  subject_id: string
  reason: string
  expires_at: string | null
  released_at: string | null
  release_reason: string | null
  created_at: string
  active: boolean
}

type RetentionCategory = {
  status: 'evaluated' | 'not_evaluated'
  candidates: number
  due?: number
  blocked_by_legal_hold?: number
  retention_days?: number
  retention_years_after_end?: number
  reference_field?: string
  proposed_action?: string
  reason?: string
}

type RetentionCandidate = {
  subject_type: CandidateSubjectType
  subject_id: string
  reference_at: string
  proposed_action: string
  category?: string
}

type RetentionReview = {
  id: string
  status: 'draft' | 'approved'
  policy_version: string
  evaluated_at: string
  candidate_count: number
  truncated: boolean
  summary: Record<string, RetentionCategory>
  candidates: RetentionCandidate[]
  approved_at: string | null
  created_at: string
}

type HoldModalState = {
  subject_type: HoldSubjectType
  subject_id: string
}

const SUBJECT_LABEL: Record<CandidateSubjectType, string> = {
  client: 'Cliente',
  representative: 'Representante',
  order: 'Pedido/orçamento',
  notification: 'Notificação',
  signature_invitation: 'Convite de assinatura',
  integration_outbox: 'Evento de integração',
  privacy_event: 'Evento de privacidade',
}

const CATEGORY_LABEL: Record<string, string> = {
  clients: 'Clientes sem pedido',
  open_orders: 'Orçamentos/pedidos abertos',
  closed_orders: 'Pedidos finalizados/cancelados',
  representatives: 'Representantes',
  notifications_read: 'Notificações lidas',
  notifications_unread: 'Notificações não lidas',
  signature_invitations: 'Convites de assinatura',
  outbox_delivered: 'Webhooks entregues',
  outbox_dead_letter: 'Webhooks com falha definitiva',
  privacy_events: 'Eventos de privacidade',
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function errorDetail(error: unknown, fallback: string) {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (
        typeof item === 'object' && item && 'msg' in item
          ? String(item.msg)
          : String(item)
      ))
      .join(' ')
  }
  return fallback
}

export default function RetentionGovernancePanel() {
  const [reviews, setReviews] = useState<RetentionReview[]>([])
  const [holds, setHolds] = useState<LegalHold[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [holdModal, setHoldModal] = useState<HoldModalState | null>(null)
  const [holdReason, setHoldReason] = useState('')
  const [holdExpiresAt, setHoldExpiresAt] = useState('')
  const [approveReview, setApproveReview] = useState<RetentionReview | null>(null)
  const [releaseHold, setReleaseHold] = useState<LegalHold | null>(null)
  const [password, setPassword] = useState('')
  const [releaseReason, setReleaseReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [endRelationship, setEndRelationship] = useState(false)
  const [representativeId, setRepresentativeId] = useState('')
  const [relationshipEndedAt, setRelationshipEndedAt] = useState('')
  const [relationshipReason, setRelationshipReason] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [reviewResponse, holdResponse] = await Promise.all([
        api.get<RetentionReview[]>('/privacy/retention-reviews?limit=20'),
        api.get<LegalHold[]>('/privacy/legal-holds?active_only=true&limit=100'),
      ])
      setReviews(reviewResponse.data)
      setHolds(holdResponse.data)
      setSelectedId((current) => (
        current && reviewResponse.data.some((item) => item.id === current)
          ? current
          : reviewResponse.data[0]?.id ?? null
      ))
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível carregar a governança de retenção.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const selected = useMemo(
    () => reviews.find((item) => item.id === selectedId) ?? null,
    [reviews, selectedId],
  )

  function showNotice(message: string) {
    setNotice(message)
    window.setTimeout(() => setNotice(null), 4000)
  }

  async function generateDryRun() {
    setGenerating(true)
    setError(null)
    try {
      const response = await api.post<RetentionReview>(
        '/privacy/retention-reviews/dry-run',
        {},
      )
      await load()
      setSelectedId(response.data.id)
      showNotice('Simulação concluída. Nenhum registro foi alterado.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível gerar a simulação.'))
    } finally {
      setGenerating(false)
    }
  }

  function openHold(subjectType: HoldSubjectType = 'client', subjectId = '') {
    setHoldReason('')
    setHoldExpiresAt('')
    setHoldModal({ subject_type: subjectType, subject_id: subjectId })
    setError(null)
  }

  async function createHold(event: React.FormEvent) {
    event.preventDefault()
    if (!holdModal) return
    setSaving(true)
    setError(null)
    try {
      await api.post('/privacy/legal-holds', {
        ...holdModal,
        reason: holdReason,
        expires_at: holdExpiresAt
          ? new Date(holdExpiresAt).toISOString()
          : null,
      })
      setHoldModal(null)
      await load()
      showNotice('Legal hold criado. O registro ficará fora das simulações.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível criar o legal hold.'))
    } finally {
      setSaving(false)
    }
  }

  async function approve(event: React.FormEvent) {
    event.preventDefault()
    if (!approveReview) return
    setSaving(true)
    setError(null)
    try {
      await api.post(
        `/privacy/retention-reviews/${approveReview.id}/approve`,
        { password },
      )
      setApproveReview(null)
      setPassword('')
      await load()
      showNotice('Relatório aprovado. Nenhum descarte foi executado.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível aprovar o relatório.'))
    } finally {
      setSaving(false)
    }
  }

  async function release(event: React.FormEvent) {
    event.preventDefault()
    if (!releaseHold) return
    setSaving(true)
    setError(null)
    try {
      await api.post(
        `/privacy/legal-holds/${releaseHold.id}/release`,
        { password, reason: releaseReason },
      )
      setReleaseHold(null)
      setPassword('')
      setReleaseReason('')
      await load()
      showNotice('Legal hold liberado e operação auditada.')
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível liberar o legal hold.'))
    } finally {
      setSaving(false)
    }
  }

  async function closeRepresentativeRelationship(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const response = await api.post<{
        deactivated_users: number
      }>(`/privacy/representatives/${representativeId}/relationship-end`, {
        ended_at: new Date(relationshipEndedAt).toISOString(),
        reason: relationshipReason,
        password,
      })
      setEndRelationship(false)
      setRepresentativeId('')
      setRelationshipEndedAt('')
      setRelationshipReason('')
      setPassword('')
      await load()
      showNotice(
        `Vínculo encerrado. ${response.data.deactivated_users} acesso(s) revogado(s).`,
      )
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível encerrar o vínculo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="mt-8 space-y-4" aria-labelledby="retention-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="retention-heading" className="flex items-center gap-2 text-xl font-semibold text-ink">
            <ShieldAlert className="h-5 w-5 text-gold" />
            Governança de retenção
          </h2>
          <p className="mt-1 text-sm text-muted">
            Simulação e bloqueios legais. Esta área não possui exclusão automática.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => {
              setEndRelationship(true)
              setPassword('')
              setError(null)
            }}
            className="btn-secondary flex items-center gap-2"
          >
            <UserRoundX className="h-4 w-4" /> Encerrar vínculo
          </button>
          <button type="button" onClick={() => openHold()} className="btn-secondary flex items-center gap-2">
            <Plus className="h-4 w-4" /> Legal hold
          </button>
          <button
            type="button"
            onClick={generateDryRun}
            disabled={generating}
            className="btn-primary flex items-center gap-2 disabled:opacity-60"
          >
            <FileSearch className="h-4 w-4" />
            {generating ? 'Simulando…' : 'Gerar simulação'}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-gold/30 bg-gold/5 px-4 py-3 text-sm text-ink-2">
        Aprovar confirma somente a revisão do relatório. Clientes, representantes,
        pedidos e orçamentos permanecem intactos.
      </div>

      {error && <p role="alert" className="rounded-lg bg-terracotta/10 px-4 py-3 text-sm text-terracotta">{error}</p>}
      {notice && <p role="status" className="rounded-lg bg-olive/10 px-4 py-3 text-sm text-olive">{notice}</p>}

      {loading ? (
        <div className="rounded-2xl border border-line bg-white p-8 text-center text-sm text-muted">
          Carregando governança…
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
          <div className="space-y-4">
            <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-ink">Relatórios recentes</h3>
              {reviews.length === 0 ? (
                <p className="py-5 text-center text-sm text-muted">Nenhuma simulação gerada.</p>
              ) : (
                <div className="space-y-2">
                  {reviews.map((review) => (
                    <button
                      type="button"
                      key={review.id}
                      onClick={() => setSelectedId(review.id)}
                      className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                        selectedId === review.id
                          ? 'border-gold bg-gold/5'
                          : 'border-line hover:bg-bg'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium text-ink">
                          {formatDate(review.created_at)}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                          review.status === 'approved'
                            ? 'bg-olive/10 text-olive'
                            : 'bg-mineral/10 text-mineral'
                        }`}>
                          {review.status === 'approved' ? 'Aprovado' : 'Rascunho'}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {review.candidate_count} candidato(s)
                        {review.truncated ? ' · fotografia truncada' : ''}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selected && (
              <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-ink">Resultado da simulação</h3>
                    <p className="mt-1 text-xs text-muted">
                      Política {selected.policy_version} · avaliada em {formatDate(selected.evaluated_at)}
                    </p>
                  </div>
                  {selected.status === 'draft' && (
                    <button
                      type="button"
                      disabled={selected.truncated}
                      onClick={() => {
                        setPassword('')
                        setApproveReview(selected)
                        setError(null)
                      }}
                      className="btn-secondary flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <FileCheck2 className="h-4 w-4" /> Aprovar relatório
                    </button>
                  )}
                </div>

                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {Object.entries(selected.summary).map(([key, category]) => (
                    <div key={key} className="rounded-xl border border-line bg-bg/60 p-3">
                      <p className="text-xs font-semibold text-ink">{CATEGORY_LABEL[key] ?? key}</p>
                      {category.status === 'evaluated' ? (
                        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                          <div><strong className="block text-base text-ink">{category.due ?? 0}</strong><span className="text-[10px] text-muted">Vencidos</span></div>
                          <div><strong className="block text-base text-gold">{category.blocked_by_legal_hold ?? 0}</strong><span className="text-[10px] text-muted">Bloqueados</span></div>
                          <div><strong className="block text-base text-mineral">{category.candidates}</strong><span className="text-[10px] text-muted">Candidatos</span></div>
                        </div>
                      ) : (
                        <p className="mt-2 text-xs text-muted">
                          Não avaliado: falta registrar a data de encerramento do vínculo.
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-4">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Candidatos da fotografia
                  </h4>
                  {selected.candidates.length === 0 ? (
                    <p className="py-4 text-sm text-muted">Nenhum candidato nesta simulação.</p>
                  ) : (
                    <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
                      {selected.candidates.slice(0, 100).map((candidate) => (
                        <div key={`${candidate.subject_type}-${candidate.subject_id}`} className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-ink">
                              {SUBJECT_LABEL[candidate.subject_type]}
                            </p>
                            <p className="truncate font-mono text-[10px] text-muted">{candidate.subject_id}</p>
                            <p className="text-[10px] text-muted">Referência: {formatDate(candidate.reference_at)}</p>
                          </div>
                          {(['client', 'representative', 'order'] as CandidateSubjectType[]).includes(candidate.subject_type) && (
                            <button
                              type="button"
                              onClick={() => openHold(candidate.subject_type as HoldSubjectType, candidate.subject_id)}
                              className="shrink-0 text-xs font-medium text-gold hover:text-gold-600"
                            >
                              Bloquear
                            </button>
                          )}
                        </div>
                      ))}
                      {selected.candidates.length > 100 && (
                        <p className="text-center text-xs text-muted">
                          Mostrando 100 de {selected.candidates.length} registros.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <LockKeyhole className="h-4 w-4 text-gold" /> Legal holds ativos
              </h3>
              <span className="text-xs text-muted">{holds.length}</span>
            </div>
            {holds.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">Nenhum bloqueio ativo.</p>
            ) : (
              <div className="mt-3 space-y-2">
                {holds.map((hold) => (
                  <div key={hold.id} className="rounded-xl border border-line p-3">
                    <p className="text-xs font-semibold text-ink">{SUBJECT_LABEL[hold.subject_type]}</p>
                    <p className="mt-1 break-all font-mono text-[10px] text-muted">{hold.subject_id}</p>
                    <p className="mt-2 text-xs text-ink-2">{hold.reason}</p>
                    <p className="mt-2 text-[10px] text-muted">
                      Expira: {hold.expires_at ? formatDate(hold.expires_at) : 'sem expiração automática'}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setPassword('')
                        setReleaseReason('')
                        setReleaseHold(hold)
                        setError(null)
                      }}
                      className="mt-3 flex items-center gap-1 text-xs font-medium text-mineral hover:text-ink"
                    >
                      <UnlockKeyhole className="h-3.5 w-3.5" /> Liberar hold
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {holdModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 px-4 backdrop-blur-sm">
          <form onSubmit={createHold} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Criar legal hold</h3>
              <button type="button" onClick={() => setHoldModal(null)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Tipo de registro</span>
              <select
                className="input"
                value={holdModal.subject_type}
                onChange={(event) => setHoldModal({
                  ...holdModal,
                  subject_type: event.target.value as HoldSubjectType,
                })}
              >
                <option value="client">Cliente</option>
                <option value="representative">Representante</option>
                <option value="order">Pedido/orçamento</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">ID do registro</span>
              <input
                className="input font-mono text-xs"
                value={holdModal.subject_id}
                onChange={(event) => setHoldModal({ ...holdModal, subject_id: event.target.value })}
                required
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Motivo objetivo</span>
              <textarea className="input min-h-24" value={holdReason} onChange={(event) => setHoldReason(event.target.value)} minLength={5} maxLength={2000} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Expiração opcional</span>
              <input className="input" type="datetime-local" value={holdExpiresAt} onChange={(event) => setHoldExpiresAt(event.target.value)} />
            </label>
            <p className="text-xs text-muted">Não inclua documentos ou dados pessoais desnecessários no motivo.</p>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setHoldModal(null)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Salvando…' : 'Criar hold'}</button>
            </div>
          </form>
        </div>
      )}

      {endRelationship && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 px-4 backdrop-blur-sm">
          <form onSubmit={closeRepresentativeRelationship} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Encerrar vínculo do representante</h3>
              <button type="button" onClick={() => setEndRelationship(false)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <p className="text-sm text-ink-2">
              A ação registra o marco de retenção e desativa imediatamente os acessos vinculados.
            </p>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">ID do representante</span>
              <input className="input font-mono text-xs" value={representativeId} onChange={(event) => setRepresentativeId(event.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Data e hora do encerramento</span>
              <input className="input" type="datetime-local" max={new Date().toISOString().slice(0, 16)} value={relationshipEndedAt} onChange={(event) => setRelationshipEndedAt(event.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Justificativa</span>
              <textarea className="input min-h-20" value={relationshipReason} onChange={(event) => setRelationshipReason(event.target.value)} minLength={5} maxLength={2000} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Sua senha atual</span>
              <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required autoComplete="current-password" />
            </label>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setEndRelationship(false)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Encerrando…' : 'Encerrar vínculo'}</button>
            </div>
          </form>
        </div>
      )}

      {approveReview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 px-4 backdrop-blur-sm">
          <form onSubmit={approve} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Aprovar relatório</h3>
              <button type="button" onClick={() => setApproveReview(null)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <p className="text-sm text-ink-2">
              Confirme a revisão de {approveReview.candidate_count} candidato(s).
              Nenhum dado será descartado.
            </p>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Sua senha atual</span>
              <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required autoComplete="current-password" />
            </label>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setApproveReview(null)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Aprovando…' : 'Aprovar'}</button>
            </div>
          </form>
        </div>
      )}

      {releaseHold && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 px-4 backdrop-blur-sm">
          <form onSubmit={release} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-ink">Liberar legal hold</h3>
              <button type="button" onClick={() => setReleaseHold(null)} className="text-muted hover:text-ink"><X className="h-5 w-5" /></button>
            </div>
            <p className="text-sm text-ink-2">
              O registro voltará a ser considerado nas próximas simulações.
            </p>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Justificativa da liberação</span>
              <textarea className="input min-h-20" value={releaseReason} onChange={(event) => setReleaseReason(event.target.value)} minLength={5} maxLength={2000} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Sua senha atual</span>
              <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required autoComplete="current-password" />
            </label>
            {error && <p role="alert" className="text-xs text-terracotta">{error}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={() => setReleaseHold(null)} className="btn-secondary flex-1">Cancelar</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1 disabled:opacity-60">{saving ? 'Liberando…' : 'Liberar hold'}</button>
            </div>
          </form>
        </div>
      )}
    </section>
  )
}
