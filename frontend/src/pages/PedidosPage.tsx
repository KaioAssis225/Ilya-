import { useState, useEffect } from 'react'
import { DialogPanel } from '../components/Dialog'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Search, Eye, Trash2, FileText, X, ImageIcon, PenLine, CheckCircle, Clock, History, Filter, Lock, Ban, ChevronDown } from 'lucide-react'
import { useOrders, useOrder, useDeleteOrder, useFinalizeOrder, useCancelOrder, useGlobalOrderHistory } from '../hooks/useOrders'
import { useProductsByCodes } from '../hooks/useProducts'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { useOptionalCategories } from '../hooks/useOptionalCategories'
import { useAuth } from '../hooks/useAuth'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import { SafePrice } from '../components/SafePrice'
import api from '../lib/api'
import type { Order, OrderHistory, OrderSummary, Product, Client, Representative } from '../types'
import { formatDimensions } from '../lib/measurements'
import { useLocale } from '../hooks/useLocale'
import { optionalName, optionalCategoryLabel } from '../lib/optionalLabels'
import { choiceValue } from '../lib/optionalApplications'
import { optionalMatchesLegacyName } from '../lib/optionalGroups'
import { formatArea } from '../lib/areaProduct'

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('pt-BR')
}

function fmtDateTime(s: string) {
  return new Date(s).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function itemsSummary(order: OrderSummary) {
  // O resumo da API nÃ£o traz `sold_by_area`: quantidades fracionÃ¡rias sÃ£o a
  // Ãºnica pista segura. Um tapete com quantidade inteira continua como CODE(n).
  const locale = order.market_code === 'EU' ? 'en-GB' : 'pt-BR'
  return order.items.map((item) => {
    const qty = Number(item.qty)
    return `${item.product_code}(${Number.isInteger(qty) ? qty : formatArea(qty, locale)})`
  }).join(', ')
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

const ACTION_LABEL: Record<string, string> = {
  created: 'Criado',
  edited: 'Editado',
  finalized: 'Finalizado',
  cancelled: 'Cancelado',
}

const ACTION_DOT: Record<string, string> = {
  created: 'bg-olive',
  edited: 'bg-gold',
  finalized: 'bg-info',
  cancelled: 'bg-terracotta',
}

const ACTION_BADGE: Record<string, string> = {
  created: 'bg-olive/10 text-olive',
  edited: 'bg-gold/10 text-gold',
  finalized: 'bg-info-soft text-info',
  cancelled: 'bg-terracotta/10 text-terracotta',
}

// ── Audit Timeline ─────────────────────────────────────────────────────────────

function AuditTimeline({ history }: { history: OrderHistory[] }) {
  if (history.length === 0) {
    return <p className="text-xs text-muted text-center py-6">Nenhum registro de auditoria.</p>
  }
  return (
    <div className="space-y-0">
      {history.map((h, idx) => (
        <div key={h.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className={`w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0 ${ACTION_DOT[h.action] ?? 'bg-faint'}`} />
            {idx < history.length - 1 && <div className="w-px flex-1 bg-line my-1" />}
          </div>
          <div className="pb-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${ACTION_BADGE[h.action] ?? 'bg-bg-2 text-muted'}`}>
                {ACTION_LABEL[h.action] ?? h.action}
              </span>
              {h.user && <span className="text-xs text-ink-2 font-medium">{h.user.full_name}</span>}
              <span className="text-[11px] text-muted-3 ml-auto whitespace-nowrap">{fmtDateTime(h.created_at)}</span>
            </div>
            {h.details && <p className="text-xs text-ink-3 mt-0.5 break-words">{h.details}</p>}
            {h.items_snapshot?.map((item, itemIndex) => <div key={itemIndex} className="text-xs text-ink-3 mt-1">
              <strong>{item.product_code}</strong>
              {Object.entries(item.legacy_optionals).map(([category, value]) => <span key={category} className="block">{category}: {value}</span>)}
              {item.applications.map((choice, choiceIndex) => <span key={choiceIndex} className="block">
                {choice.component_name ? `${choice.component_name} — ` : ''}{choice.application_name}: {choiceValue(choice, false)}
              </span>)}
              {item.comment && <span className="block break-words">Comentário: {item.comment}</span>}
            </div>)}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Finalize Modal ─────────────────────────────────────────────────────────────

function FinalizeModal({ order, onClose }: { order: OrderSummary; onClose: () => void }) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const finalizeM = useFinalizeOrder()

  async function handleSubmit() {
    setLoading(true)
    try {
      await finalizeM.mutateAsync({ id: order.id, external_code: code.trim() || undefined })
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <DialogPanel onClose={onClose} className="modal-panel w-full max-w-md p-6 mx-4">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-ink">Finalizar Pedido</h3>
          <button type="button" onClick={onClose} aria-label="Fechar" className="btn-icon -mr-2">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-sm text-ink-2 mb-4">
          Pedido <span className="font-mono font-semibold text-gold">{order.code}</span> será marcado como finalizado e não poderá mais ser editado.
        </p>
        <label className="block space-y-1 mb-5">
          <span className="text-xs text-muted font-medium">Código Externo (opcional)</span>
          <input
            className="input w-full"
            placeholder="Ex: ERP-12345"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Cancelar</button>
          <button className="btn-primary" disabled={loading} onClick={handleSubmit}>
            {loading ? 'Finalizando...' : 'Finalizar Pedido'}
          </button>
        </div>
      </DialogPanel>
    </div>
  )
}

// ── Cancel Modal ───────────────────────────────────────────────────────────────

function CancelModal({ order, onClose }: { order: OrderSummary; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const cancelM = useCancelOrder()

  async function handleSubmit() {
    setLoading(true)
    try {
      await cancelM.mutateAsync({ id: order.id, reason: reason.trim() || undefined })
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <DialogPanel onClose={onClose} className="modal-panel w-full max-w-md p-6 mx-4">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-ink">Cancelar Pedido</h3>
          <button type="button" onClick={onClose} aria-label="Fechar" className="btn-icon -mr-2">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-sm text-ink-2 mb-4">
          Pedido <span className="font-mono font-semibold text-gold">{order.code}</span> será marcado como cancelado e não poderá mais ser editado ou finalizado.
        </p>
        <label className="block space-y-1 mb-5">
          <span className="text-xs text-muted font-medium">Motivo (opcional)</span>
          <input
            className="input w-full"
            placeholder="Ex: cliente desistiu"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Voltar</button>
          <button className="flex items-center gap-1.5 px-4 py-2 bg-terracotta text-white rounded-lg text-sm font-semibold hover:bg-terracotta-700 transition-colors disabled:opacity-60" disabled={loading} onClick={handleSubmit}>
            {loading ? 'Cancelando...' : 'Cancelar Pedido'}
          </button>
        </div>
      </DialogPanel>
    </div>
  )
}

// ── Modal de detalhes ─────────────────────────────────────────────────────────

function OrderDetailModal({
  order: orderLight, clientName, repName,
  userRole,
  onClose, onEdit, onFinalize, onCancel,
}: {
  order: OrderSummary; clientName: string; repName: string
  userRole: string
  onClose: () => void; onEdit: () => void; onFinalize: () => void; onCancel: () => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { locale } = useLocale()
  const optionalEnglish = locale === 'en-GB'
  const {
    data: orderDetail,
    isError: detailError,
    refetch: retryOrderDetail,
  } = useOrder(orderLight.id)
  const order: Order = orderDetail ?? {
    ...orderLight,
    price_list_code: 'lojista',
    locale: orderLight.market_code === 'EU' ? 'pt-PT' : 'pt-BR',
    total_ipi: 0,
    external_code: null,
    notes: null,
    items: [],
    history: [],
    updated_at: orderLight.created_at,
  }
  const viewLocale = order.market_code === 'EU' ? locale : 'pt-BR'
  const isEuOrder = order.market_code === 'EU'
  const viewText = (pt: string, en: string) => isEuOrder && locale === 'en-GB' ? en : pt
  const { data: products = [] } = useProductsByCodes(
    orderDetail?.items.map((item) => item.product_code) ?? [],
    !!orderDetail,
  )
  const optionalCategories = orderDetail
    ? Array.from(
        new Set(
          orderDetail.items.flatMap((item) => [
            ...Object.keys(item.opt_categories),
            ...(item.optional_choices ?? []).map((choice) => choice.category_code),
          ]).filter(Boolean),
        ),
      )
    : []
  const { data: allOptionals = [] } = useOptionalsForCategories(
    optionalCategories,
    !!orderDetail,
  )
  const { data: optCategories = [] } = useOptionalCategories()
  const catLabel = (code: string) => optionalCategoryLabel(optCategories.find(c => c.code === code)?.name ?? code, optionalEnglish)
  const [tab, setTab] = useState<'details' | 'history'>('details')
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [expandedOptionalItems, setExpandedOptionalItems] = useState<Set<string>>(() => new Set())
  const [revisionError, setRevisionError] = useState(false)
  const [revisionLoading, setRevisionLoading] = useState(false)

  // Representante também edita/finaliza os próprios pedidos (backend valida a posse)
  // O papel legado "vendedor" com vínculo é uma conta de cliente, não um usuário interno.
  const canManage = userRole === 'admin'
    || userRole === 'representante'
    || userRole === 'produtos'
    || userRole === 'vendedor'
  const canRevise = userRole === 'admin' || userRole === 'representante'
    || userRole === 'vendedor'

  function parseOptCategories(cats: Record<string, string>): { label: string; swatch: string | null; thumbnail: string | null }[] {
    return Object.entries(cats).map(([cat, color]) => {
      const optional = allOptionals.find(o => o.category === cat && optionalMatchesLegacyName(o, color))
      return {
        label: `${catLabel(cat)} — ${optionalName(color, optionalEnglish)}`,
        swatch: optional?.photo_url ?? optional?.thumbnail_url ?? null,
        thumbnail: optional?.thumbnail_url ?? optional?.photo_url ?? null,
      }
    })
  }

  const optionalItemIds = order.items
    .filter((item) => Object.keys(item.opt_categories).length > 0 || (item.optional_choices?.length ?? 0) > 0)
    .map((item) => item.id)
  const allOptionalsExpanded = optionalItemIds.length > 0
    && optionalItemIds.every((itemId) => expandedOptionalItems.has(itemId))

  function toggleAllOptionals() {
    setExpandedOptionalItems(allOptionalsExpanded ? new Set() : new Set(optionalItemIds))
  }

  function toggleItemOptionals(itemId: string) {
    setExpandedOptionalItems((current) => {
      const next = new Set(current)
      if (next.has(itemId)) next.delete(itemId)
      else next.add(itemId)
      return next
    })
  }

  if (detailError) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <DialogPanel onClose={onClose} className="modal-panel w-full max-w-md p-8">
          <p className="text-sm text-terracotta text-center">
            Não foi possível carregar os detalhes deste pedido.
          </p>
          <div className="flex justify-center gap-3 mt-5">
            <button className="btn-secondary" onClick={onClose}>Fechar</button>
            <button className="btn-primary" onClick={() => void retryOrderDetail()}>
              Tentar novamente
            </button>
          </div>
        </DialogPanel>
      </div>
    )
  }

  if (!orderDetail) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <DialogPanel onClose={onClose} className="modal-panel w-full max-w-2xl p-10">
          <div className="flex items-center justify-center gap-3 text-sm text-muted" role="status">
            <span className="w-5 h-5 rounded-full border-2 border-gold/25 border-t-gold animate-spin" />
            Carregando detalhes do pedido…
          </div>
        </DialogPanel>
      </div>
    )
  }

  return (
    <div className="modal-overlay overflow-y-auto" onClick={onClose}>
      {/* Mais largo no desktop: a tabela de itens (com os opcionais abertos)
          pede ~950px; com max-w-2xl (672px) quantidade, imposto, subtotal e o
          total ficavam fora da área visível. */}
      <DialogPanel onClose={onClose} className="modal-panel relative w-full max-w-2xl lg:max-w-5xl p-6 my-4">
        {/* Header — em tela estreita as ações descem para a própria linha em vez
            de vazarem o painel; o X fica ancorado no canto para não ser
            empurrado para fora junto com elas. */}
        <button onClick={onClose} className="absolute top-5 right-5 z-10 text-muted hover:text-ink" aria-label="Fechar"><X className="w-5 h-5" /></button>
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4 pr-8">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-semibold text-ink">{order.code}</h3>
              {order.is_finalized
                ? <span className="flex items-center gap-1 text-[11px] font-bold bg-success-soft text-success border border-success/25 px-1.5 py-0.5 rounded-full"><Lock className="w-2.5 h-2.5" /> Finalizado</span>
                : order.is_cancelled
                ? <span className="flex items-center gap-1 text-[11px] font-bold bg-danger-soft text-danger border border-danger/25 px-1.5 py-0.5 rounded-full"><Ban className="w-2.5 h-2.5" /> Cancelado</span>
                : <span className="text-[11px] font-bold bg-warning-soft text-warning border border-warning/25 px-1.5 py-0.5 rounded-full">{viewText('Em andamento', 'In progress')}</span>
              }
            </div>
            <p className="text-sm text-ink-3">{viewText('Orçamento:', 'Quote:')} <span className="text-gold">{order.orc_id}</span>
              {order.external_code && <span className="ml-2 font-mono text-xs text-ink-2">· {order.external_code}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap sm:justify-end shrink-0">
            {canRevise && order.is_finalized && !order.is_cancelled && (
              <button disabled={revisionLoading} onClick={async () => {
                setRevisionLoading(true); setRevisionError(false)
                try {
                  const response = await api.post<Order>(`/orders/${order.id}/revision`)
                  await queryClient.invalidateQueries({ queryKey: ['orders'] })
                  onClose()
                  navigate(`/orcamentos?edit=${response.data.id}`)
                } catch { setRevisionError(true) } finally { setRevisionLoading(false) }
              }} className="btn-secondary text-xs disabled:opacity-50">{revisionLoading ? viewText('Criando revisão...', 'Creating revision...') : viewText('Criar revisão', 'Create revision')}</button>
            )}
            {canManage && !order.is_finalized && !order.is_cancelled && (
              <>
                <button onClick={onEdit} className="flex items-center gap-1.5 px-3 py-1.5 border border-line text-ink-2 rounded-lg text-xs font-medium hover:bg-bg-2 transition-colors">
                  <PenLine className="w-3.5 h-3.5" /> Editar
                </button>
                <button onClick={onCancel} className="flex items-center gap-1.5 px-3 py-1.5 border border-terracotta text-terracotta rounded-lg text-xs font-semibold hover:bg-danger-soft transition-colors">
                  <Ban className="w-3.5 h-3.5" /> Cancelar
                </button>
                <button onClick={onFinalize} className="flex items-center gap-1.5 px-3 py-1.5 bg-gold text-white rounded-lg text-xs font-semibold hover:bg-gold-600 transition-colors">
                  <CheckCircle className="w-3.5 h-3.5" /> Finalizar
                </button>
              </>
            )}
          </div>
        </div>
        {revisionError && <p role="alert" className="text-xs font-medium text-danger mb-3">Não foi possível criar a revisão. Verifique a disponibilidade atual dos produtos e preços.</p>}
        {order.supersedes_order_id && <p className="text-xs text-muted mb-3">Revisão {order.revision_number} de um pedido anterior.</p>}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-line mb-4">
          {(['details', 'history'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-xs font-semibold transition-colors ${tab === t ? 'text-gold border-b-2 border-gold -mb-px' : 'text-muted hover:text-ink-2'}`}>
              {t === 'details' ? viewText('Detalhes', 'Details') : viewText('Histórico', 'History')}
            </button>
          ))}
        </div>

        {tab === 'history' && (
          <div className="pt-1"><AuditTimeline history={order.history} /></div>
        )}

        {tab === 'details' && (
          <>
            <div className="grid grid-cols-2 gap-3 text-sm mb-5">
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">{viewText('Cliente', 'Client')}</p><p className="text-ink font-medium">{clientName}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">{viewText('Representante', 'Representative')}</p><p className="text-ink font-medium">{repName || '—'}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">{viewText('Data', 'Date')}</p><p className="text-ink">{new Date(order.created_at).toLocaleDateString(viewLocale)}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3">
                <p className="text-xs text-muted mb-1">{Number(order.total_ipi) > 0 ? viewText(`Total com ${order.market_code === 'EU' ? 'IVA' : 'IPI'}`, `Total with ${order.market_code === 'EU' ? 'VAT' : 'IPI'}`) : 'Total'}</p>
                <p className="text-gold font-bold"><SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} currency={order.currency} locale={viewLocale} /></p>
              </div>
              {order.notes && (
                <div className="col-span-2 bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">{viewText('Observações', 'Notes')}</p><p className="text-ink-2">{order.notes}</p></div>
              )}
            </div>

            <div className="flex items-center justify-between gap-3 mb-2">
              <h4 className="text-xs font-semibold text-ink-3 uppercase tracking-wider">{viewText('Itens', 'Items')}</h4>
              {optionalItemIds.length > 0 && (
                <button
                  type="button"
                  aria-expanded={allOptionalsExpanded}
                  onClick={toggleAllOptionals}
                  className="inline-flex items-center gap-1 text-xs font-medium text-gold hover:text-gold-600 transition-colors"
                >
                  {allOptionalsExpanded
                    ? viewText('Ocultar opcionais', 'Hide options')
                    : viewText('Mostrar todos os opcionais', 'Show all options')}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${allOptionalsExpanded ? 'rotate-180' : ''}`} aria-hidden="true" />
                </button>
              )}
            </div>
            <div className="border border-line rounded-xl overflow-x-auto">
              <table className="w-full min-w-[700px] text-sm">
                <thead className="bg-surface-2">
                  <tr>
                    <th className="px-3 py-2 w-10"></th>
                    <th className="px-3 py-2 text-left text-xs text-muted">{viewText('Produto', 'Product')}</th>
                    <th className="px-3 py-2 text-left text-xs text-muted">Dim. ({order.market_code === 'EU' ? '″' : 'm'})</th>
                    <th className="px-3 py-2 text-left text-xs text-muted">{viewText('Opcionais', 'Options')}</th>
                    <th className="px-3 py-2 text-center text-xs text-muted">{viewText('Qtd', 'Qty')}</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">{viewText('Preço Base', 'Base price')}</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">{viewText('Desconto', 'Discount')}</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">{order.market_code === 'EU' ? 'IVA' : 'IPI'}</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">{viewText('Subtotal', 'Subtotal')}</th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => {
                    const photoUrl = products.find(p => p.product_code === item.product_code)?.photo_url ?? null
                    return (
                      <tr key={item.id} className="border-t border-line">
                        <td className="px-2 py-2" style={{ width: '40px', minWidth: '40px' }}>
                          {photoUrl
                            ? <img src={photoUrl} alt="" onClick={() => setActivePhotoModal(photoUrl)} className="object-cover rounded-lg border border-line cursor-pointer hover:opacity-80 transition-opacity" style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }} />
                            : <div className="bg-bg-2 rounded-lg flex items-center justify-center" style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }}><ImageIcon className="w-4 h-4 text-faint" /></div>
                          }
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-gold font-mono text-xs">{item.product_code}</span>
                          <div className="text-ink-2 text-xs mt-0.5 max-w-[150px] truncate">{isEuOrder ? (products.find(p => p.product_code === item.product_code)?.description_en ?? item.description) : item.description}</div>
                          {item.observacao && <div className="text-[10px] text-gold italic mt-0.5 max-w-[150px] truncate">{item.observacao}</div>}
                          {item.comment && <div className="text-[10px] text-ink-2 mt-0.5 max-w-[220px] whitespace-pre-line break-words">
                            <span className="font-semibold">{optionalEnglish ? 'Comment' : 'Comentário'}:</span> {item.comment}
                          </div>}
                        </td>
                        <td className="px-3 py-2 text-ink-3 text-xs min-w-[120px]">
                          {item.sold_by_area ? '—' : formatDimensions(item, order.market_code, viewLocale)}
                        </td>
                        <td className="px-3 py-2 text-ink-3 text-xs">
                          {(() => {
                            const parsed = parseOptCategories(item.opt_categories)
                            const choices = item.optional_choices ?? []
                            if (parsed.length === 0 && choices.length === 0) return '—'
                            const choiceDetails = choices.map((choice) => {
                              const applicationName = isEuOrder && choice.application_name_en
                                ? choice.application_name_en
                                : choice.application_name
                              const label = `${choice.component_name ? `${choice.component_name} — ` : ''}${applicationName}: ${choiceValue(choice, optionalEnglish)}`
                              const optional = allOptionals.find((candidate) => candidate.id === choice.optional_id)
                              return {
                                choice,
                                label,
                                thumbnail: optional?.thumbnail_url ?? optional?.photo_url ?? null,
                                photo: optional?.photo_url ?? optional?.thumbnail_url ?? null,
                              }
                            })
                            const optionals = [
                              ...parsed.map((optional) => ({ key: `legacy-${optional.label}`, label: optional.label, thumbnail: optional.thumbnail, photo: optional.swatch })),
                              ...choiceDetails.map(({ choice, label, thumbnail, photo }) => ({ key: `choice-${choice.id}`, label, thumbnail, photo })),
                            ]
                            const isExpanded = expandedOptionalItems.has(item.id)
                            const detailsId = `order-item-optionals-${item.id}`
                            const countLabel = `${optionals.length} ${viewText(optionals.length === 1 ? 'opcional' : 'opcionais', optionals.length === 1 ? 'option' : 'options')}`
                            return (
                              <div className="min-w-[150px]">
                                <div className="flex items-center gap-2">
                                  <div className="flex items-center -space-x-1">
                                    {optionals.map((optional) => (
                                      <button
                                        key={optional.key}
                                        type="button"
                                        title={optional.label}
                                        aria-label={optional.label}
                                        disabled={!optional.photo}
                                        onClick={() => optional.photo && setActivePhotoModal(optional.photo)}
                                        className="relative w-7 h-7 flex-shrink-0 overflow-hidden rounded border border-line bg-white text-[10px] font-semibold text-muted disabled:cursor-default"
                                      >
                                        {optional.thumbnail
                                          ? <img src={optional.thumbnail} alt={optional.label} className="w-full h-full rounded object-cover" />
                                          : <span className="flex w-full h-full items-center justify-center bg-bg-2" aria-hidden="true">{optional.label.trim().charAt(0).toUpperCase()}</span>
                                        }
                                      </button>
                                    ))}
                                  </div>
                                  <button
                                    type="button"
                                    aria-expanded={isExpanded}
                                    aria-controls={detailsId}
                                    onClick={() => toggleItemOptionals(item.id)}
                                    className="inline-flex items-center gap-1 whitespace-nowrap font-medium text-gold hover:text-gold-600 transition-colors"
                                  >
                                    {countLabel}
                                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} aria-hidden="true" />
                                  </button>
                                </div>
                                {isExpanded && (
                                  <div id={detailsId} className="mt-2 space-y-1">
                                    {parsed.map((optional) => (
                                      <div key={optional.label}>
                                        <OptionalWithPreview label={optional.label} swatch={optional.swatch} />
                                      </div>
                                    ))}
                                    {choiceDetails.map(({ choice, label }) => (
                                      <div key={choice.id} className="text-xs">{label}</div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )
                          })()}
                        </td>
                        <td className="px-3 py-2 text-center text-ink">{item.sold_by_area ? formatArea(item.qty, viewLocale) : item.qty}</td>
                        <td className="px-3 py-2 text-right text-xs text-ink-2 font-semibold whitespace-nowrap">
                          <SafePrice value={Number(item.unit_price)} currency={order.currency} locale={viewLocale} />
                        </td>
                        <td className="px-3 py-2 text-right align-middle">
                          {Number(item.discount) > 0 ? (
                            <span className="text-[9px] bg-gold-wash text-gold border border-line-note px-1 py-0.5 rounded font-medium">-{Number(item.discount)}%</span>
                          ) : <span className="text-xs text-muted">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right align-middle whitespace-nowrap">
                          {Number(item.ipi_rate) > 0
                            ? <span className="text-xs font-semibold text-gold">{Number(item.ipi_rate)}%</span>
                            : <span className="text-xs text-muted">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-ink whitespace-nowrap">
                          {/* Portugal: IVA só no fecho da tabela; Brasil: IPI na linha. */}
                          <SafePrice value={item.qty * Number(item.unit_price) * (1 - Number(item.discount) / 100) * (order.market_code === 'EU' ? 1 : 1 + Number(item.ipi_rate) / 100)} currency={order.currency} locale={viewLocale} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  {order.market_code === 'EU' && Number(order.total_ipi) > 0 && (
                    <>
                      <tr className="border-t border-line bg-bg">
                        <td colSpan={8} className="px-3 pt-2.5 pb-1 text-right text-xs text-muted uppercase tracking-wider">Subtotal</td>
                        <td className="px-3 pt-2.5 pb-1 text-right text-sm text-ink whitespace-nowrap"><SafePrice value={Number(order.total_value)} currency={order.currency} locale={viewLocale} /></td>
                      </tr>
                      <tr className="bg-bg">
                        <td colSpan={8} className="px-3 py-1 text-right text-xs text-muted uppercase tracking-wider">{viewText('IVA', 'VAT')}</td>
                        <td className="px-3 py-1 text-right text-sm text-ink whitespace-nowrap"><SafePrice value={Number(order.total_ipi)} currency={order.currency} locale={viewLocale} /></td>
                      </tr>
                    </>
                  )}
                  <tr className="border-t border-line bg-bg">
                    <td colSpan={8} className="px-3 py-2.5 text-right text-sm text-ink-2 font-semibold uppercase tracking-wider">{viewText('Valor Total', 'Total value')}</td>
                    <td className="px-3 py-2.5 text-right text-gold font-bold text-base">
                      <SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} currency={order.currency} locale={viewLocale} />
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}

        {activePhotoModal && (
          <div className="fixed inset-0 z-modal-sub flex items-center justify-center bg-scrim/75 backdrop-blur-sm" onClick={() => setActivePhotoModal(null)}>
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <img src={activePhotoModal} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-line" />
              <button onClick={() => setActivePhotoModal(null)} className="absolute -top-3 -right-3 bg-white border border-line rounded-full w-11 h-11 flex items-center justify-center shadow-md text-muted hover:text-ink transition-colors"><X className="w-4 h-4" /></button>
            </div>
          </div>
        )}
      </DialogPanel>
    </div>
  )
}

// ── Mobile order card ───────────────────────────────────────────────────────

function MobileOrderCard({
  order, clientName, repName, onView, onPDF, onFinalize, onDelete, pdfLoading,
}: {
  order: OrderSummary; clientName: string; repName: string
  onView: () => void; onPDF: () => void; onFinalize?: () => void; onDelete?: () => void
  pdfLoading: boolean
}) {
  return (
    <div className="bg-white border border-line rounded-xl shadow-sm overflow-hidden">
      <div className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="font-mono font-semibold text-gold text-sm">{order.code}</span>
            <span className="font-mono text-[10px] text-muted-3 ml-2">{order.orc_id}</span>
            <p className="text-sm font-medium text-ink truncate mt-1">{clientName}</p>
            <p className="text-xs text-ink-3 truncate">{repName}</p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-sm font-bold text-ink"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} currency={order.currency} locale={order.market_code === 'EU' ? 'pt-PT' : 'pt-BR'} /></p>
            <p className="text-[10px] text-muted-3 mt-0.5">{fmtDate(order.created_at)}</p>
          </div>
        </div>
        <div className="mt-2">
          {order.items.length > 0 && <p className="mb-2 truncate text-xs text-ink-3">{itemsSummary(order)}</p>}
          <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-1.5 py-0.5 rounded-full ${order.is_finalized ? 'bg-success-soft text-success' : order.is_cancelled ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning'}`}>
            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : order.is_cancelled ? <Ban className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
            {order.is_finalized ? 'Finalizado' : order.is_cancelled ? 'Cancelado' : 'Em andamento'}
          </span>
        </div>
      </div>
      <div className="flex border-t border-bg-2 divide-x divide-bg-2">
        <button onClick={onView} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-ink-2 active:bg-bg transition-colors" style={{ touchAction: 'manipulation' }} aria-label="Visualizar"><Eye className="w-4 h-4 text-gold" /> Ver</button>
        <button disabled={pdfLoading} onClick={onPDF} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-ink-2 active:bg-bg transition-colors disabled:opacity-50" style={{ touchAction: 'manipulation' }}><FileText className="w-4 h-4 text-gold" /> {pdfLoading ? 'Gerando…' : 'PDF'}</button>
        {onFinalize && (
          <button onClick={onFinalize} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-success active:bg-success-soft transition-colors" style={{ touchAction: 'manipulation' }} aria-label="Finalizar pedido"><CheckCircle className="w-4 h-4" /> Finalizar</button>
        )}
        {onDelete && (
          <button onClick={onDelete} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-terracotta active:bg-danger-soft transition-colors" style={{ touchAction: 'manipulation' }} aria-label="Excluir"><Trash2 className="w-4 h-4" /> Excluir</button>
        )}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PedidosPage() {
  const { user } = useAuth()
  const { locale } = useLocale()
  const isEnglish = locale === 'en-GB'
  const navigate = useNavigate()
  const isInternalSeller = user?.role === 'vendedor' && !user.linked_id
  const canManage = user?.role === 'admin' || user?.role === 'representante' || user?.role === 'produtos' || isInternalSeller
  const canViewGlobalAudit = user?.role === 'admin' || isInternalSeller
  const canDelete = user?.role === 'admin'
  const [requestedTab, setActiveTab] = useState<'orders' | 'audit'>('orders')
  // Aba efetiva derivada no render: sem permissão de auditoria o usuário nunca
  // permanece na aba de auditoria (dispensa o reset via efeito).
  const activeTab: 'orders' | 'audit' = canViewGlobalAudit ? requestedTab : 'orders'
  const isAuditActive = activeTab === 'audit'
  const [filter, setFilter] = useState('')
  const [filterClient, setFilterClient] = useState('')
  const [filterRep, setFilterRep] = useState('')
  const [filterStatus, setFilterStatus] = useState<'in_progress' | 'finalized' | 'cancelled' | ''>('')
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [cursorPager, setCursorPager] = useState<{ key: string | null; stack: Array<string | undefined> }>({ key: null, stack: [undefined] })
  const [historyCursorStack, setHistoryCursorStack] = useState<Array<string | undefined>>([undefined])
  const [pdfOrderId, setPdfOrderId] = useState<string | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const debouncedFilter = useDebouncedValue(filter.trim(), 300)
  const debouncedClient = useDebouncedValue(filterClient.trim(), 300)
  const debouncedRep = useDebouncedValue(filterRep.trim(), 300)
  // A paginação pertence a um conjunto de filtros: quando os filtros mudam, a
  // pilha de cursores é reiniciada durante o render (sem efeito/estado extra).
  const filtersKey = JSON.stringify([debouncedFilter, debouncedClient, debouncedRep, filterStatus, filterDateFrom, filterDateTo])
  const cursorStack: Array<string | undefined> = cursorPager.key === filtersKey ? cursorPager.stack : [undefined]
  const setCursorStack = (update: (current: Array<string | undefined>) => Array<string | undefined>) => {
    const base = cursorPager.key === filtersKey ? cursorPager.stack : [undefined]
    setCursorPager({ key: filtersKey, stack: update(base) })
  }
  const currentCursor = cursorStack[cursorStack.length - 1]
  const { data: ordersPage, isLoading } = useOrders({
    cursor: currentCursor,
    limit: 50,
    q: debouncedFilter,
    client_name: debouncedClient,
    rep_name: debouncedRep,
    status: filterStatus,
    date_from: filterDateFrom,
    date_to: filterDateTo,
  })
  const orders = ordersPage?.items ?? []
  const { data: optCategoriesList = [] } = useOptionalCategories()
  const pdfCatLabel = (code: string) => optCategoriesList.find(c => c.code === code)?.name ?? code
  const historyCursor = historyCursorStack[historyCursorStack.length - 1]
  const {
    data: globalHistoryPage,
    isLoading: isHistoryLoading,
  } = useGlobalOrderHistory(
    historyCursor,
    isAuditActive,
  )
  const globalHistory = globalHistoryPage?.items ?? []
  const deleteM = useDeleteOrder()

  async function handlePDF(orderLight: OrderSummary) {
    if (pdfOrderId) return
    setPdfOrderId(orderLight.id)
    setPdfError(null)
    try {
      const order = (await api.get<Order>(`/orders/${orderLight.id}`)).data
      const codes = Array.from(
        new Set(order.items.map((item) => item.product_code)),
      )
      const batches = Array.from(
        { length: Math.ceil(codes.length / 100) },
        (_, index) => codes.slice(index * 100, (index + 1) * 100),
      )
      const [pdfModule, clientResponse, repResponse, productsResponses] = await Promise.all([
        import('../lib/generatePDF'),
        api.get<Client>(`/clients/${orderLight.client_id}`),
        orderLight.rep_id
          ? api.get<Representative>(`/representatives/${orderLight.rep_id}`)
          : Promise.resolve(null),
        Promise.all(
          batches.map((productCodes) =>
            api.post<Product[]>('/products/batch', {
              product_codes: productCodes,
            }),
          ),
        ),
      ])
      // A listagem não traz os blobs de assinatura; o PDF trabalha com o detalhe completo.
      const client = clientResponse.data
      const rep = repResponse?.data ?? null
      const products = productsResponses.flatMap((response) => response.data)
      await pdfModule.generateOrderPDF(
        order,
        client,
        rep,
        products,
        pdfCatLabel,
        order.market_code === 'EU' ? locale : undefined,
      )
    } catch {
      setPdfError('Não foi possível gerar o PDF. Tente novamente.')
    } finally {
      setPdfOrderId(null)
    }
  }

  const [viewing, setViewing] = useState<OrderSummary | null>(null)
  const [deleting, setDeleting] = useState<OrderSummary | null>(null)
  const [finalizing, setFinalizing] = useState<OrderSummary | null>(null)
  const [canceling, setCanceling] = useState<OrderSummary | null>(null)


  const filtered = orders

  const hasFilters = !!(filterClient || filterRep || filterStatus || filterDateFrom || filterDateTo)

  return (
    <div className="min-h-screen bg-bg text-ink">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-5 md:py-6 space-y-4 pb-24 md:pb-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl text-ink font-medium">
              {isAuditActive ? (isEnglish ? 'General audit' : 'Auditoria Geral') : (isEnglish ? 'Orders' : 'Pedidos')}
              <span className="ml-2 text-xs bg-bg-2 text-gold px-2 py-0.5 rounded-full">
                {isEnglish ? 'On this page' : 'Nesta página'}: {isAuditActive ? globalHistory.length : orders.length}
              </span>
            </h1>
            {canViewGlobalAudit && (
              <div className="flex gap-1 border border-line rounded-lg p-0.5 bg-white">
                <button onClick={() => setActiveTab('orders')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${activeTab === 'orders' ? 'bg-gold text-white' : 'text-muted hover:text-ink-2'}`}>{isEnglish ? 'Orders' : 'Pedidos'}</button>
                <button onClick={() => setActiveTab('audit')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${activeTab === 'audit' ? 'bg-gold text-white' : 'text-muted hover:text-ink-2'}`}>
                  <History className="w-3 h-3" /> {isEnglish ? 'Audit' : 'Auditoria'}
                </button>
              </div>
            )}
          </div>

          {!isAuditActive && (
            <div className="flex items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
                <input aria-label={isEnglish ? 'Filter orders by client or number' : 'Filtrar pedidos por cliente ou número'} className="input pl-9" placeholder={isEnglish ? 'Filter by client, order...' : 'Filtrar por cliente, pedido...'} value={filter} onChange={(e) => setFilter(e.target.value)} />
              </div>
              <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center gap-1.5 px-3 py-2 border rounded-lg text-xs font-medium transition-colors ${hasFilters ? 'border-gold text-gold bg-gold-wash' : 'border-line text-muted hover:border-faint'}`}>
                <Filter className="w-3.5 h-3.5" /> {isEnglish ? 'Filters' : 'Filtros'}{hasFilters && <span className="w-1.5 h-1.5 rounded-full bg-gold" />}
              </button>
            </div>
          )}
        </div>

        {pdfError && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-danger/25 bg-danger-soft px-4 py-2 text-sm text-danger" role="alert">
            <span>{pdfError}</span>
            <button className="text-xs font-semibold" onClick={() => setPdfError(null)}>
              Fechar
            </button>
          </div>
        )}

        {/* Advanced filters */}
        {!isAuditActive && showFilters && (
          <div className="bg-white border border-line rounded-xl p-4 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
            <div className="space-y-1">
              <label htmlFor="orders-client-filter" className="text-xs text-muted font-medium uppercase tracking-wider">Cliente</label>
              <input
                id="orders-client-filter"
                className="input text-xs w-full"
                value={filterClient}
                onChange={(e) => setFilterClient(e.target.value)}
                placeholder="Nome do cliente"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="orders-rep-filter" className="text-xs text-muted font-medium uppercase tracking-wider">Representante</label>
              <input
                id="orders-rep-filter"
                className="input text-xs w-full"
                value={filterRep}
                onChange={(e) => setFilterRep(e.target.value)}
                placeholder="Nome do representante"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="orders-status-filter" className="text-xs text-muted font-medium uppercase tracking-wider">Status</label>
              <select
                id="orders-status-filter"
                className="input text-xs w-full"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value as 'in_progress' | 'finalized' | 'cancelled' | '')}
              >
                <option value="">Todos</option>
                <option value="in_progress">Em andamento</option>
                <option value="finalized">Finalizados</option>
                <option value="cancelled">Cancelados</option>
              </select>
            </div>
            <div className="space-y-1">
              <label htmlFor="orders-date-from" className="text-xs text-muted font-medium uppercase tracking-wider">Data Inicial</label>
              <input id="orders-date-from" type="date" className="input text-xs w-full" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label htmlFor="orders-date-to" className="text-xs text-muted font-medium uppercase tracking-wider">Data Final</label>
              <input id="orders-date-to" type="date" className="input text-xs w-full" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} />
            </div>
            {hasFilters && (
              <div className="col-span-2 md:col-span-3 xl:col-span-5 flex justify-end">
                <button onClick={() => { setFilterClient(''); setFilterRep(''); setFilterStatus(''); setFilterDateFrom(''); setFilterDateTo('') }} className="px-2 text-xs text-terracotta hover:text-terracotta-700 transition-colors">Limpar filtros</button>
              </div>
            )}
          </div>
        )}

        {/* Audit tab */}
        {isAuditActive && (
          <>
            <div className="bg-white border border-line rounded-xl p-5">
              {isHistoryLoading
                ? <p className="text-xs text-muted text-center py-6">Carregando auditoria…</p>
                : <AuditTimeline history={globalHistory} />
              }
            </div>
            <div className="flex items-center justify-between gap-3 pt-1">
              <span className="text-xs text-muted">
                Página {historyCursorStack.length} · {globalHistory.length} registro{globalHistory.length === 1 ? '' : 's'}
              </span>
              <div className="flex items-center gap-2">
                <button
                  className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40"
                  disabled={historyCursorStack.length === 1 || isHistoryLoading}
                  onClick={() => setHistoryCursorStack((current) => current.slice(0, -1))}
                >
                  Anterior
                </button>
                <button
                  className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40"
                  disabled={!globalHistoryPage?.hasMore || !globalHistoryPage.nextCursor || isHistoryLoading}
                  onClick={() => {
                    if (globalHistoryPage?.nextCursor) {
                      setHistoryCursorStack((current) => [...current, globalHistoryPage.nextCursor!])
                    }
                  }}
                >
                  Próxima
                </button>
              </div>
            </div>
          </>
        )}

        {/* Orders tab */}
        {!isAuditActive && (
          isLoading ? (
            <div aria-busy="true" aria-label="Carregando pedidos">
              {/* Esqueleto no mesmo formato do conteúdo final de cada viewport:
                  cartões no mobile, linhas de tabela a partir de md (sem CLS). */}
              <div className="flex flex-col gap-3 md:hidden">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="rounded-xl border border-line bg-white p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="h-4 w-24 rounded bg-line-soft animate-pulse" />
                      <div className="h-5 w-20 rounded-full bg-line-soft animate-pulse" />
                    </div>
                    <div className="h-4 w-3/4 rounded bg-line-soft animate-pulse" />
                    <div className="h-4 w-1/2 rounded bg-line-soft animate-pulse" />
                    <div className="h-10 rounded-lg bg-line-soft animate-pulse" />
                  </div>
                ))}
              </div>
              <div className="hidden md:block rounded-xl border border-line bg-white overflow-hidden">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4 px-4 py-3.5 border-b border-bg-2 last:border-0">
                    <div className="h-4 w-20 rounded bg-line-soft animate-pulse" />
                    <div className="h-4 w-24 rounded bg-line-soft animate-pulse" />
                    <div className="h-4 flex-1 rounded bg-line-soft animate-pulse" />
                    <div className="h-4 w-16 rounded bg-line-soft animate-pulse" />
                    <div className="h-5 w-24 rounded-full bg-line-soft animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-3 md:hidden">
                {filtered.map((order) => (
                  <MobileOrderCard
                    key={order.id}
                    order={order}
                    clientName={order.client_name}
                    repName={order.rep_name ?? '—'}
                    onView={() => setViewing(order)}
                    onPDF={() => handlePDF(order)}
                    onFinalize={canManage && !order.is_finalized && !order.is_cancelled ? () => setFinalizing(order) : undefined}
                    onDelete={canDelete ? () => setDeleting(order) : undefined}
                    pdfLoading={pdfOrderId === order.id}
                  />
                ))}
                {filtered.length === 0 && (
                  <div className="rounded-xl border border-line bg-white px-4 py-12 text-center">
                    {filter || hasFilters ? (
                      <p className="text-ink-3 text-sm">Nenhum pedido encontrado com este filtro.</p>
                    ) : (
                      <>
                        <p className="text-ink-3 text-sm">{isEnglish ? 'No orders yet.' : 'Nenhum pedido ainda.'}</p>
                        {canManage && <button onClick={() => navigate('/orcamentos')} className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 bg-gold text-white rounded-lg text-sm font-semibold hover:bg-gold-600 transition-colors">{isEnglish ? 'Create first order' : 'Criar primeiro pedido'}</button>}
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Superfície branca própria: sem ela a tabela herdava o fundo da
                  página (linho no tema EU) e o conteúdo não se destacava. */}
              <div className="hidden md:block overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead className="bg-surface-2">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Order' : 'Pedido'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Quote' : 'Orçamento'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Client' : 'Cliente'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Representative' : 'Representante'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Items' : 'Itens'}</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Total' : 'Total'}</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Date' : 'Data'}</th>
                      <th className="px-4 py-3 text-center text-xs font-semibold text-ink-3 uppercase">{isEnglish ? 'Status' : 'Status'}</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((order) => (
                      <tr key={order.id} className="table-row">
                        <td className="px-4 py-3 font-mono text-gold whitespace-nowrap">{order.code}</td>
                        <td className="px-4 py-3 font-mono text-ink-3 text-xs whitespace-nowrap">{order.orc_id}</td>
                        <td className="px-4 py-3 text-ink">{order.client_name}</td>
                        <td className="px-4 py-3 text-ink-3">{order.rep_name ?? '—'}</td>
                        <td className="px-4 py-3 text-ink-3 text-xs max-w-[160px] truncate">{itemsSummary(order)}</td>
                        <td className="px-4 py-3 text-right font-semibold text-ink whitespace-nowrap"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} currency={order.currency} locale={order.market_code === 'EU' ? 'pt-PT' : 'pt-BR'} /></td>
                        <td className="px-4 py-3 text-ink-3 text-xs whitespace-nowrap">{fmtDate(order.created_at)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full ${order.is_finalized ? 'bg-success-soft text-success' : order.is_cancelled ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning'}`}>
                            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : order.is_cancelled ? <Ban className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
                            {order.is_finalized ? 'Finalizado' : order.is_cancelled ? 'Cancelado' : 'Em andamento'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-0.5 items-center">
                            <button type="button" title="Ver detalhes" aria-label={`Ver detalhes do pedido ${order.code}`} className="btn-icon" onClick={() => setViewing(order)}><Eye className="w-4 h-4" /></button>
                            <button type="button" disabled={pdfOrderId === order.id} title={pdfOrderId === order.id ? 'Gerando PDF…' : 'Gerar PDF'} aria-label={`Gerar PDF do pedido ${order.code}`} className="btn-icon hover:text-mineral" onClick={() => handlePDF(order)}><FileText className="w-4 h-4" /></button>
                            {canManage && !order.is_finalized && !order.is_cancelled && (
                              <button type="button" title="Finalizar pedido" aria-label={`Finalizar pedido ${order.code}`} className="btn-icon hover:text-success" onClick={() => setFinalizing(order)}><CheckCircle className="w-4 h-4" /></button>
                            )}
                            {canManage && !order.is_finalized && !order.is_cancelled && (
                              <>
                                <button type="button" title="Editar" aria-label={`Editar pedido ${order.code}`} className="btn-icon" onClick={() => navigate(`/orcamentos?edit=${order.id}`)}><PenLine className="w-4 h-4" /></button>
                                <button type="button" title="Cancelar" aria-label={`Cancelar pedido ${order.code}`} className="btn-icon hover:text-terracotta" onClick={() => setCanceling(order)}><Ban className="w-4 h-4" /></button>
                              </>
                            )}
                            {canDelete && (
                              <button type="button" title="Excluir" aria-label={`Excluir pedido ${order.code}`} className="btn-icon hover:text-danger" onClick={() => setDeleting(order)}><Trash2 className="w-4 h-4" /></button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr><td colSpan={9} className="px-4 py-12 text-center">
                        {filter || hasFilters ? (
                          <span className="text-ink-3">Nenhum pedido encontrado com este filtro.</span>
                        ) : (
                          <div className="flex flex-col items-center gap-3">
                            <span className="text-ink-3">{isEnglish ? 'No orders yet.' : 'Nenhum pedido ainda.'}</span>
                            {canManage && <button onClick={() => navigate('/orcamentos')} className="inline-flex items-center gap-1.5 px-4 py-2 bg-gold text-white rounded-lg text-sm font-semibold hover:bg-gold-600 transition-colors">{isEnglish ? 'Create first order' : 'Criar primeiro pedido'}</button>}
                          </div>
                        )}
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between gap-3 pt-1">
                <span className="text-xs text-muted">
                  Página {cursorStack.length} · {orders.length} registro{orders.length === 1 ? '' : 's'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40"
                    disabled={cursorStack.length === 1 || isLoading}
                    onClick={() => setCursorStack((current) => current.slice(0, -1))}
                  >
                    Anterior
                  </button>
                  <button
                    className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-40"
                    disabled={!ordersPage?.hasMore || !ordersPage.nextCursor || isLoading}
                    onClick={() => {
                      if (ordersPage?.nextCursor) {
                        setCursorStack((current) => [...current, ordersPage.nextCursor!])
                      }
                    }}
                  >
                    Próxima
                  </button>
                </div>
              </div>
            </>
          )
        )}
      </div>

      {viewing && (
        <OrderDetailModal
          key={viewing.id}
          order={orders.find(o => o.id === viewing.id) ?? viewing}
          clientName={viewing.client_name}
          repName={viewing.rep_name ?? ''}
          userRole={user?.role ?? ''}
          onClose={() => setViewing(null)}
          onEdit={() => { setViewing(null); navigate(`/orcamentos?edit=${viewing.id}`) }}
          onFinalize={() => { setFinalizing(viewing); setViewing(null) }}
          onCancel={() => { setCanceling(viewing); setViewing(null) }}
        />
      )}

      {finalizing && <FinalizeModal order={finalizing} onClose={() => setFinalizing(null)} />}
      {canceling && <CancelModal order={canceling} onClose={() => setCanceling(null)} />}

      {deleting && (
        <div className="modal-overlay" onClick={() => setDeleting(null)}>
          <DialogPanel onClose={() => setDeleting(null)} className="modal-panel w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-ink mb-2">Confirmar exclusão</h3>
            <p className="text-ink-2 mb-6">Excluir pedido <span className="text-gold font-mono">{deleting.code}</span>? Esta ação não pode ser desfeita.</p>
            <div className="flex justify-end gap-3">
              <button className="btn-secondary" onClick={() => setDeleting(null)}>Cancelar</button>
              <button className="btn-danger" onClick={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}>Excluir</button>
            </div>
          </DialogPanel>
        </div>
      )}
    </div>
  )
}
