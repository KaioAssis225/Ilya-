import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Search, Eye, Trash2, FileText, X, ImageIcon, FileSignature, Link, PenLine, Bell, CheckCircle, Clock, History, Filter, Lock } from 'lucide-react'
import { useOrders, useOrder, useDeleteOrder, useFinalizeOrder, useGlobalOrderHistory } from '../hooks/useOrders'
import { useClients } from '../hooks/useClients'
import { useRepresentatives } from '../hooks/useRepresentatives'
import { useProducts } from '../hooks/useProducts'
import { useOptionals } from '../hooks/useOptionals'
import { useOptionalCategories } from '../hooks/useOptionalCategories'
import { useAuth } from '../hooks/useAuth'
import { generateOrderPDF } from '../lib/generatePDF'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import { SafePrice } from '../components/SafePrice'
import api from '../lib/api'
import type { Order, OrderHistory, OptionalColor, Product, Client } from '../types'

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('pt-BR')
}

function fmtDateTime(s: string) {
  return new Date(s).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function itemsSummary(order: Order) {
  return order.items.map((i) => `${i.product_code}(${i.qty})`).join(', ')
}

const ACTION_LABEL: Record<string, string> = {
  created: 'Criado',
  edited: 'Editado',
  finalized: 'Finalizado',
}

const ACTION_DOT: Record<string, string> = {
  created: 'bg-olive',
  edited: 'bg-gold',
  finalized: 'bg-[#2c5282]',
}

const ACTION_BADGE: Record<string, string> = {
  created: 'bg-olive/10 text-olive',
  edited: 'bg-gold/10 text-gold',
  finalized: 'bg-[#2c5282]/10 text-[#2c5282]',
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
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${ACTION_BADGE[h.action] ?? 'bg-gray-100 text-gray-600'}`}>
                {ACTION_LABEL[h.action] ?? h.action}
              </span>
              {h.user && <span className="text-xs text-ink-2 font-medium">{h.user.full_name}</span>}
              <span className="text-[10px] text-muted-3 ml-auto whitespace-nowrap">{fmtDateTime(h.created_at)}</span>
            </div>
            {h.details && <p className="text-xs text-[#6b5d55] mt-0.5 break-words">{h.details}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Finalize Modal ─────────────────────────────────────────────────────────────

function FinalizeModal({ order, onClose }: { order: Order; onClose: () => void }) {
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
      <div className="modal-panel w-full max-w-md p-6 mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-semibold text-ink">Finalizar Pedido</h3>
          <button onClick={onClose} className="text-muted hover:text-ink w-9 h-9 flex items-center justify-center">
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
      </div>
    </div>
  )
}

// ── Modal de detalhes ─────────────────────────────────────────────────────────

function OrderDetailModal({
  order: orderLight, clientName, repName, allOptionals, products,
  userId, userRole, canSignContract, clientObj,
  onClose, onEdit, onFinalize,
}: {
  order: Order; clientName: string; repName: string
  allOptionals: OptionalColor[]; products: Product[]
  userId: string; userRole: string; canSignContract: boolean; clientObj: Client | null
  onClose: () => void; onEdit: () => void; onFinalize: () => void
}) {
  const queryClient = useQueryClient()
  // A listagem não traz os blobs de assinatura (V-M7); busca o detalhe completo.
  const { data: orderDetail } = useOrder(orderLight.id)
  const order = orderDetail ?? orderLight
  const { data: optCategories = [] } = useOptionalCategories()
  const catLabel = (code: string) => optCategories.find(c => c.code === code)?.name ?? code
  const isClientUser = userRole === 'vendedor'
  const sigKey = isClientUser ? `signature_cli_${order.code}` : `signature_rep_${order.code}`
  const [tab, setTab] = useState<'details' | 'history'>('details')
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [confirmSign, setConfirmSign] = useState(false)
  const [isSigning, setIsSigning] = useState(false)
  const [signLink, setSignLink] = useState<string | null>(null)
  const [signLinkLoading, setSignLinkLoading] = useState(false)
  const [clientSigOpen, setClientSigOpen] = useState(false)
  const [clientSaving, setClientSaving] = useState(false)
  const [repSigOpen, setRepSigOpen] = useState(false)
  const [repSaving, setRepSaving] = useState(false)
  const [sigError, setSigError] = useState(false)
  const [notifyLoading, setNotifyLoading] = useState(false)
  const [notifyDone, setNotifyDone] = useState(false)
  const [notifyError, setNotifyError] = useState(false)
  const clientCanvasRef = useRef<HTMLCanvasElement>(null)
  const clientIsDrawingRef = useRef(false)
  const repCanvasRef = useRef<HTMLCanvasElement>(null)
  const repIsDrawingRef = useRef(false)

  // Representante também edita/finaliza os próprios pedidos (backend valida a posse)
  const canManage = userRole === 'admin' || userRole === 'vendedor' || userRole === 'representante'
  const profileSig = localStorage.getItem(`profile_signature_${userId}`)
  const isContractSigned = !!(order.rep_signed || order.rep_signature)
  const isClientSigned = !!(order.client_signed || order.client_signature)
  const canSignAsClient = (userRole === 'representante' || userRole === 'admin') && !isClientSigned
  const showNotifyBtn = userRole === 'representante' || userRole === 'admin'
  const clientHasAccount = !!clientObj?.has_user

  useEffect(() => {
    if (!clientSigOpen || !clientCanvasRef.current) return
    const canvas = clientCanvasRef.current
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height) // limpa assinatura anterior ao reabrir (V-M9)
    ctx.strokeStyle = '#2c2420'; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'
    function getXY(e: TouchEvent | MouseEvent) {
      const rect = canvas.getBoundingClientRect()
      if ('touches' in e) return { x: (e as TouchEvent).touches[0].clientX - rect.left, y: (e as TouchEvent).touches[0].clientY - rect.top }
      return { x: (e as MouseEvent).clientX - rect.left, y: (e as MouseEvent).clientY - rect.top }
    }
    function onStart(e: TouchEvent | MouseEvent) { e.preventDefault(); clientIsDrawingRef.current = true; const { x, y } = getXY(e); ctx.beginPath(); ctx.moveTo(x, y) }
    function onMove(e: TouchEvent | MouseEvent) { e.preventDefault(); if (!clientIsDrawingRef.current) return; const { x, y } = getXY(e); ctx.lineTo(x, y); ctx.stroke() }
    function onEnd() { clientIsDrawingRef.current = false }
    canvas.addEventListener('mousedown', onStart); canvas.addEventListener('mousemove', onMove); canvas.addEventListener('mouseup', onEnd)
    canvas.addEventListener('touchstart', onStart, { passive: false }); canvas.addEventListener('touchmove', onMove, { passive: false }); canvas.addEventListener('touchend', onEnd)
    return () => {
      canvas.removeEventListener('mousedown', onStart); canvas.removeEventListener('mousemove', onMove); canvas.removeEventListener('mouseup', onEnd)
      canvas.removeEventListener('touchstart', onStart); canvas.removeEventListener('touchmove', onMove); canvas.removeEventListener('touchend', onEnd)
    }
  }, [clientSigOpen])

  // Bloco 81: canvas de assinatura "na hora" para representante sem profileSig configurado
  useEffect(() => {
    if (!repSigOpen || !repCanvasRef.current) return
    const canvas = repCanvasRef.current
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.strokeStyle = '#2c2420'; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'
    function getXY(e: TouchEvent | MouseEvent) {
      const rect = canvas.getBoundingClientRect()
      if ('touches' in e) return { x: (e as TouchEvent).touches[0].clientX - rect.left, y: (e as TouchEvent).touches[0].clientY - rect.top }
      return { x: (e as MouseEvent).clientX - rect.left, y: (e as MouseEvent).clientY - rect.top }
    }
    function onStart(e: TouchEvent | MouseEvent) { e.preventDefault(); repIsDrawingRef.current = true; const { x, y } = getXY(e); ctx.beginPath(); ctx.moveTo(x, y) }
    function onMove(e: TouchEvent | MouseEvent) { e.preventDefault(); if (!repIsDrawingRef.current) return; const { x, y } = getXY(e); ctx.lineTo(x, y); ctx.stroke() }
    function onEnd() { repIsDrawingRef.current = false }
    canvas.addEventListener('mousedown', onStart); canvas.addEventListener('mousemove', onMove); canvas.addEventListener('mouseup', onEnd)
    canvas.addEventListener('touchstart', onStart, { passive: false }); canvas.addEventListener('touchmove', onMove, { passive: false }); canvas.addEventListener('touchend', onEnd)
    return () => {
      canvas.removeEventListener('mousedown', onStart); canvas.removeEventListener('mousemove', onMove); canvas.removeEventListener('mouseup', onEnd)
      canvas.removeEventListener('touchstart', onStart); canvas.removeEventListener('touchmove', onMove); canvas.removeEventListener('touchend', onEnd)
    }
  }, [repSigOpen])

  async function handleSaveClientSig() {
    if (!clientCanvasRef.current) return
    const data = clientCanvasRef.current.toDataURL('image/png')
    setClientSaving(true); setSigError(false)
    try {
      await api.post(`/orders/${order.id}/sign-client`, { signature: data })
      localStorage.setItem(`signature_cli_${order.code}`, data)
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setClientSigOpen(false)
    } catch {
      setSigError(true)
    } finally {
      setClientSaving(false)
    }
  }

  // Bloco 81: assina "na hora" e salva a assinatura no perfil (profile_signature_${userId})
  // para reuso automático em próximos pedidos, sem exigir configuração prévia em Minha Conta.
  async function handleSaveRepSig() {
    if (!repCanvasRef.current) return
    const data = repCanvasRef.current.toDataURL('image/png')
    setRepSaving(true); setSigError(false)
    try {
      localStorage.setItem(`profile_signature_${userId}`, data)
      await api.post(`/orders/${order.id}/sign-representative`, { signature: data })
      localStorage.setItem(sigKey, data)
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setRepSigOpen(false)
    } catch {
      setSigError(true)
    } finally {
      setRepSaving(false)
    }
  }

  async function handleNotifyClient() {
    setNotifyLoading(true); setNotifyError(false)
    try { await api.post(`/orders/${order.id}/notify-client`); setNotifyDone(true) } catch { setNotifyError(true) }
    setNotifyLoading(false)
  }

  function parseOptCategories(cats: Record<string, string>): { label: string; swatch: string | null }[] {
    return Object.entries(cats).map(([cat, color]) => ({
      label: `${catLabel(cat)} — ${color}`,
      swatch: allOptionals.find(o => o.category === cat && o.color_name === color)?.photo_url ?? null,
    }))
  }

  return (
    <div className="modal-overlay overflow-y-auto" onClick={onClose}>
      <div className="modal-panel w-full max-w-2xl p-6 my-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-ink">{order.code}</h3>
              {order.is_finalized
                ? <span className="flex items-center gap-1 text-[10px] font-bold bg-green-50 text-green-700 border border-green-200 px-1.5 py-0.5 rounded-full"><Lock className="w-2.5 h-2.5" /> Finalizado</span>
                : <span className="text-[10px] font-bold bg-yellow-50 text-yellow-700 border border-yellow-200 px-1.5 py-0.5 rounded-full">Em andamento</span>
              }
            </div>
            <p className="text-sm text-ink-3">Orçamento: <span className="text-gold">{order.orc_id}</span>
              {order.external_code && <span className="ml-2 font-mono text-xs text-ink-2">· {order.external_code}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canManage && !order.is_finalized && (
              <>
                <button onClick={onEdit} className="flex items-center gap-1.5 px-3 py-1.5 border border-line text-ink-2 rounded-lg text-xs font-medium hover:bg-bg-2 transition-colors">
                  <PenLine className="w-3.5 h-3.5" /> Editar
                </button>
                <button onClick={onFinalize} className="flex items-center gap-1.5 px-3 py-1.5 bg-gold text-white rounded-lg text-xs font-semibold hover:bg-gold-600 transition-colors">
                  <CheckCircle className="w-3.5 h-3.5" /> Finalizar
                </button>
              </>
            )}
            <button onClick={onClose} className="text-muted hover:text-ink" aria-label="Fechar"><X className="w-5 h-5" /></button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-line mb-4">
          {(['details', 'history'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-xs font-semibold transition-colors ${tab === t ? 'text-gold border-b-2 border-gold -mb-px' : 'text-muted hover:text-ink-2'}`}>
              {t === 'details' ? 'Detalhes' : 'Histórico'}
            </button>
          ))}
        </div>

        {tab === 'history' && (
          <div className="pt-1"><AuditTimeline history={order.history} /></div>
        )}

        {tab === 'details' && (
          <>
            <div className="grid grid-cols-2 gap-3 text-sm mb-5">
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">Cliente</p><p className="text-ink font-medium">{clientName}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">Representante</p><p className="text-ink font-medium">{repName || '—'}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">Data</p><p className="text-ink">{fmtDate(order.created_at)}</p></div>
              <div className="bg-bg border border-line rounded-lg p-3">
                <p className="text-xs text-muted mb-1">{Number(order.total_ipi) > 0 ? 'Total com IPI' : 'Total'}</p>
                <p className="text-gold font-bold"><SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></p>
              </div>
              {order.notes && (
                <div className="col-span-2 bg-bg border border-line rounded-lg p-3"><p className="text-xs text-muted mb-1">Observações</p><p className="text-ink-2">{order.notes}</p></div>
              )}
            </div>

            <h4 className="text-xs font-semibold text-ink-3 uppercase tracking-wider mb-2">Itens</h4>
            <div className="border border-line rounded-xl overflow-x-auto">
              <table className="w-full min-w-[700px] text-sm">
                <thead className="bg-bg-2">
                  <tr>
                    <th className="px-3 py-2 w-10"></th>
                    <th className="px-3 py-2 text-left text-xs text-muted">Produto</th>
                    <th className="px-3 py-2 text-left text-xs text-muted">Dim. (m)</th>
                    <th className="px-3 py-2 text-left text-xs text-muted">Opcionais</th>
                    <th className="px-3 py-2 text-center text-xs text-muted">Qtd</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">Preço Base</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">Desconto</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">IPI</th>
                    <th className="px-3 py-2 text-right text-xs text-muted">Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => {
                    const photoUrl = products.find(p => p.product_code === item.product_code)?.photo_url ?? null
                    const fmtM = (v: number) => Number(v).toFixed(2).replace('.', ',')
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
                          <div className="text-ink-2 text-xs mt-0.5 max-w-[150px] truncate">{item.description}</div>
                          {item.observacao && <div className="text-[10px] text-gold italic mt-0.5 max-w-[150px] truncate">{item.observacao}</div>}
                        </td>
                        <td className="px-3 py-2 text-ink-3 text-xs whitespace-nowrap">
                          {item.is_circular ? `Ø ${fmtM(item.largura)} × A ${fmtM(item.altura)} m` : `L ${fmtM(item.largura)} × P ${fmtM(item.profundidade)} × A ${fmtM(item.altura)} m`}
                        </td>
                        <td className="px-3 py-2 text-ink-3 text-xs">
                          {(() => {
                            const parsed = parseOptCategories(item.opt_categories)
                            if (parsed.length === 0) return '—'
                            return parsed.map((p, i) => <span key={p.label}>{i > 0 && <span className="mx-1 text-faint">·</span>}<OptionalWithPreview label={p.label} swatch={p.swatch} /></span>)
                          })()}
                        </td>
                        <td className="px-3 py-2 text-center text-ink">{item.qty}</td>
                        <td className="px-3 py-2 text-right text-xs text-ink-2 font-semibold whitespace-nowrap">
                          <SafePrice value={Number(item.unit_price)} />
                        </td>
                        <td className="px-3 py-2 text-right align-middle">
                          {Number(item.discount) > 0 ? (
                            <span className="text-[9px] bg-[#fdf0d0] text-gold border border-[#e8d8a0] px-1 py-0.5 rounded font-medium">-{Number(item.discount)}%</span>
                          ) : <span className="text-xs text-faint">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right align-middle whitespace-nowrap">
                          {Number(item.ipi_rate) > 0
                            ? <span className="text-xs font-semibold text-gold">{Number(item.ipi_rate)}%</span>
                            : <span className="text-xs text-faint">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-ink whitespace-nowrap">
                          <SafePrice value={item.qty * Number(item.unit_price) * (1 - Number(item.discount) / 100) * (1 + Number(item.ipi_rate) / 100)} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line bg-bg">
                    <td colSpan={8} className="px-3 py-2.5 text-right text-sm text-ink-2 font-semibold uppercase tracking-wider">Valor Total</td>
                    <td className="px-3 py-2.5 text-right text-gold font-bold text-base">
                      <SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} />
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Assinaturas */}
            <div className="mt-5 pt-4 border-t border-line">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted uppercase tracking-wider font-semibold">Assinaturas</span>
                  <span className="flex items-center gap-1 text-xs">{isContractSigned ? <CheckCircle className="w-3 h-3 text-green-600" /> : <Clock className="w-3 h-3 text-yellow-600" />}<span className="text-ink-3">REP {isContractSigned ? 'assinado' : 'pendente'}</span></span>
                  <span className="flex items-center gap-1 text-xs">{isClientSigned ? <CheckCircle className="w-3 h-3 text-green-600" /> : <Clock className="w-3 h-3 text-yellow-600" />}<span className="text-ink-3">CLI {isClientSigned ? 'assinado' : 'pendente'}</span></span>
                </div>
                {!isClientUser && (
                  <button disabled={signLinkLoading} onClick={async () => { setSignLinkLoading(true); try { const res = await api.post<{ token: string; url: string }>(`/orders/${order.id}/generate-sign-token`); setSignLink(window.location.origin + res.data.url) } catch { /* ignore */ } finally { setSignLinkLoading(false) } }} className="flex items-center gap-1.5 px-3 py-1.5 border border-gold-soft text-gold rounded-lg text-xs font-medium hover:bg-[#fdf9f0] transition-colors disabled:opacity-50">
                    <Link className="w-3.5 h-3.5" />{signLinkLoading ? 'Gerando...' : 'Gerar Link'}
                  </button>
                )}
              </div>
              {signLink && (
                <div className="flex items-center gap-2 mt-2">
                  <input readOnly value={signLink} className="flex-1 text-xs px-2 py-1.5 border border-line rounded-lg bg-bg text-ink-2 font-mono truncate" />
                  <button onClick={() => navigator.clipboard.writeText(signLink)} className="px-2 py-1.5 text-xs border border-line rounded-lg text-muted hover:text-gold transition-colors whitespace-nowrap">Copiar</button>
                </div>
              )}
              {canSignAsClient && (
                <div className="mt-3">
                  <button onClick={() => { setSigError(false); setClientSigOpen(true) }} className="flex items-center gap-1.5 px-3 py-1.5 border border-muted text-ink-2 rounded-lg text-xs font-medium hover:bg-bg-2 transition-colors">
                    <PenLine className="w-3.5 h-3.5" /> Assinar como Cliente
                  </button>
                </div>
              )}
              {showNotifyBtn && (
                <div className="mt-2">
                  {notifyDone
                    ? <div className="flex items-center gap-1.5 text-xs text-green-600"><CheckCircle className="w-3.5 h-3.5" /> Notificação enviada ao cliente.</div>
                    : <>
                        <button disabled={notifyLoading || !clientHasAccount} onClick={handleNotifyClient} title={!clientHasAccount ? 'Cliente não possui conta no sistema' : undefined} className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium transition-colors ${clientHasAccount ? 'border-gold-soft text-gold hover:bg-[#fdf9f0] disabled:opacity-50' : 'border-line text-faint cursor-not-allowed'}`}>
                          <Bell className="w-3.5 h-3.5" />{notifyLoading ? 'Enviando...' : 'Notificar Cliente'}
                        </button>
                        {notifyError && <p className="text-[10px] text-red-500 mt-1">Erro ao enviar notificação.</p>}
                      </>
                  }
                </div>
              )}
            </div>

            {canSignContract && (isClientUser ? !isClientSigned : !isContractSigned) && (
              <div className="mt-5 pt-4 border-t border-line">
                {profileSig
                  ? <button onClick={() => { setSigError(false); setConfirmSign(true) }} className="w-full flex items-center justify-center gap-2 py-2.5 bg-gold text-white rounded-xl hover:bg-gold-600 transition-colors text-sm font-semibold shadow-sm">
                      <FileSignature className="w-4 h-4" />{isClientUser ? 'Assinar como Cliente' : 'Assinar como Representante'}
                    </button>
                  : !isClientUser
                    ? <button onClick={() => { setSigError(false); setRepSigOpen(true) }} className="w-full flex items-center justify-center gap-2 py-2.5 bg-gold text-white rounded-xl hover:bg-gold-600 transition-colors text-sm font-semibold shadow-sm">
                        <FileSignature className="w-4 h-4" />Assinar Agora
                      </button>
                    : <p className="text-xs text-center text-muted py-2">Configure sua assinatura em <span className="text-gold font-medium">Minha Conta</span> para assinar contratos.</p>
                }
              </div>
            )}

            {(order.rep_signature || order.client_signature) && (
              <div className="mt-5 pt-4 border-t border-line">
                <p className="text-xs font-semibold text-ink-3 uppercase tracking-wider mb-3">Assinaturas do Contrato</p>
                <div className="flex gap-4">
                  <div className="flex-1 text-center">
                    {order.rep_signature ? <img src={order.rep_signature} alt="Assinatura Representante" className="max-h-16 w-full object-contain pb-1" /> : <div className="h-16" />}
                    <div className="border-t border-faint pt-1"><p className="text-[10px] text-muted">Representante / Ilya</p></div>
                  </div>
                  <div className="flex-1 text-center">
                    {order.client_signature ? <img src={order.client_signature} alt="Assinatura Cliente" className="max-h-16 w-full object-contain pb-1" /> : <div className="h-16" />}
                    <div className="border-t border-faint pt-1"><p className="text-[10px] text-muted">Cliente / Contratado</p></div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Canvas assinatura cliente */}
        {clientSigOpen && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3"><h4 className="text-base font-semibold text-ink">Assinatura do Cliente</h4><button onClick={() => setClientSigOpen(false)} className="text-muted hover:text-ink"><X className="w-4 h-4" /></button></div>
              <p className="text-xs text-muted mb-3">Peça ao cliente para assinar no campo abaixo.</p>
              <canvas ref={clientCanvasRef} width={420} height={160} className="w-full border border-line rounded-xl bg-[#fafaf9] cursor-crosshair touch-none" />
              <div className="flex gap-2 mt-4">
                <button onClick={() => clientCanvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Limpar</button>
                <button onClick={handleSaveClientSig} disabled={clientSaving} className="btn-primary flex-1">{clientSaving ? 'Salvando...' : 'Confirmar Assinatura'}</button>
              </div>
              {sigError && <p className="text-xs text-red-500 mt-3">Falha ao salvar a assinatura no servidor. Verifique a conexão e tente novamente.</p>}
            </div>
          </div>
        )}

        {/* Bloco 81: canvas de assinatura "na hora" para representante sem perfil configurado */}
        {repSigOpen && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3"><h4 className="text-base font-semibold text-ink">Sua Assinatura</h4><button onClick={() => setRepSigOpen(false)} className="text-muted hover:text-ink"><X className="w-4 h-4" /></button></div>
              <p className="text-xs text-muted mb-3">Assine no campo abaixo. Sua assinatura será salva para os próximos pedidos.</p>
              <canvas ref={repCanvasRef} width={420} height={160} className="w-full border border-line rounded-xl bg-[#fafaf9] cursor-crosshair touch-none" />
              <div className="flex gap-2 mt-4">
                <button onClick={() => repCanvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Limpar</button>
                <button onClick={handleSaveRepSig} disabled={repSaving} className="btn-primary flex-1">{repSaving ? 'Salvando...' : 'Confirmar Assinatura'}</button>
              </div>
              {sigError && <p className="text-xs text-red-500 mt-3">Falha ao salvar a assinatura no servidor. Verifique a conexão e tente novamente.</p>}
            </div>
          </div>
        )}

        {confirmSign && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
              <h4 className="text-base font-semibold text-ink mb-2">Confirmar Assinatura</h4>
              <p className="text-sm text-ink-2 mb-5">Deseja aplicar sua assinatura para o Pedido <span className="text-gold font-mono font-semibold">#{order.code}</span>?</p>
              {sigError && <p className="text-xs text-red-500 mb-4">Falha ao salvar a assinatura no servidor. Verifique a conexão e tente novamente.</p>}
              <div className="flex gap-3">
                <button onClick={() => setConfirmSign(false)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                <button onClick={async () => {
                  setIsSigning(true); setSigError(false)
                  try {
                    await api.post(isClientUser ? `/orders/${order.id}/sign-client` : `/orders/${order.id}/sign-representative`, { signature: profileSig })
                    localStorage.setItem(sigKey, profileSig!)
                    queryClient.invalidateQueries({ queryKey: ['orders'] })
                    setConfirmSign(false)
                  } catch {
                    setSigError(true)
                  } finally {
                    setIsSigning(false)
                  }
                }} className="btn-primary flex-1">Confirmar</button>
              </div>
            </div>
          </div>
        )}

        {isSigning && (
          <div className="fixed inset-0 z-[400] flex flex-col items-center justify-center bg-bg/90 backdrop-blur-sm">
            <div className="absolute w-[520px] h-[520px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(139,105,20,0.18) 0%, transparent 68%)', animation: 'pulseRadial 2.2s ease-in-out infinite' }} />
            <p className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", backgroundImage: 'linear-gradient(90deg, #5a4508 0%, #8b6914 25%, #c8952e 50%, #8b6914 75%, #5a4508 100%)', backgroundSize: '200% auto', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', animation: 'lightSweep 2.4s linear infinite' }}>ILYA</p>
            <p className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-gold" style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}>Gerando Assinatura</p>
            <div className="mt-9 w-52 h-[1px] bg-gold/25 overflow-hidden rounded-full"><div className="h-full rounded-full" style={{ background: 'linear-gradient(90deg, #5a4508, #c8952e, #5a4508)', animation: 'progressLine 3s linear forwards' }} /></div>
          </div>
        )}

        {activePhotoModal && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-scrim/75 backdrop-blur-sm" onClick={() => setActivePhotoModal(null)}>
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <img src={activePhotoModal} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-line" />
              <button onClick={() => setActivePhotoModal(null)} className="absolute -top-3 -right-3 bg-white border border-line rounded-full w-11 h-11 flex items-center justify-center shadow-md text-muted hover:text-ink transition-colors"><X className="w-4 h-4" /></button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Mobile order card ───────────────────────────────────────────────────────

function MobileOrderCard({
  order, clientName, repName, onView, onPDF, onDelete,
}: {
  order: Order; clientName: string; repName: string
  onView: () => void; onPDF: () => void; onDelete: () => void
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
            <p className="text-sm font-bold text-ink"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></p>
            <p className="text-[10px] text-muted-3 mt-0.5">{fmtDate(order.created_at)}</p>
          </div>
        </div>
        <div className="mt-2">
          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${order.is_finalized ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
            {order.is_finalized ? 'Finalizado' : 'Em andamento'}
          </span>
        </div>
      </div>
      <div className="flex border-t border-bg-2 divide-x divide-bg-2">
        <button onClick={onView} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-ink-2 active:bg-bg transition-colors" style={{ touchAction: 'manipulation' }} aria-label="Visualizar"><Eye className="w-4 h-4 text-gold" /> Ver</button>
        <button onClick={onPDF} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-ink-2 active:bg-bg transition-colors" style={{ touchAction: 'manipulation' }}><FileText className="w-4 h-4 text-gold" /> PDF</button>
        <button onClick={onDelete} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-terracotta active:bg-[#fbf2f0] transition-colors" style={{ touchAction: 'manipulation' }} aria-label="Excluir"><Trash2 className="w-4 h-4" /> Excluir</button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PedidosPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canManage = user?.role === 'admin' || user?.role === 'vendedor' || user?.role === 'representante'
  const { data: orders = [], isLoading } = useOrders()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: products = [] } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const { data: optCategoriesList = [] } = useOptionalCategories()
  const pdfCatLabel = (code: string) => optCategoriesList.find(c => c.code === code)?.name ?? code
  const { data: globalHistory = [] } = useGlobalOrderHistory(canManage)
  const deleteM = useDeleteOrder()
  const canSignContract = user?.role === 'representante' || (user?.role === 'vendedor' && !!user?.linked_id)

  async function handlePDF(orderLight: Order) {
    const client = clients.find((c) => c.id === orderLight.client_id)
    if (!client) return
    const rep = orderLight.rep_id ? (reps.find((r) => r.id === orderLight.rep_id) ?? null) : null
    // A listagem não traz os blobs de assinatura (V-M7); busca o detalhe completo p/ o PDF.
    const order = (await api.get<Order>(`/orders/${orderLight.id}`)).data
    await generateOrderPDF(order, client, rep, products, pdfCatLabel)
  }

  const [activeTab, setActiveTab] = useState<'orders' | 'audit'>('orders')
  const [filter, setFilter] = useState('')
  const [filterClient, setFilterClient] = useState('')
  const [filterRep, setFilterRep] = useState('')
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [viewing, setViewing] = useState<Order | null>(null)
  const [deleting, setDeleting] = useState<Order | null>(null)
  const [finalizing, setFinalizing] = useState<Order | null>(null)

  const clientMap = Object.fromEntries(clients.map((c) => [c.id, c.name]))
  const clientObjMap = Object.fromEntries(clients.map((c) => [c.id, c]))
  const repMap = Object.fromEntries(reps.map((r) => [r.id, r.name]))

  const filtered = orders.filter((o) => {
    const q = filter.toLowerCase()
    const clientName = (clientMap[o.client_id] ?? '').toLowerCase()
    return (
      (o.code.toLowerCase().includes(q) || o.orc_id.toLowerCase().includes(q) || clientName.includes(q)) &&
      (!filterClient || o.client_id === filterClient) &&
      (!filterRep || o.rep_id === filterRep) &&
      (!filterDateFrom || o.created_at >= filterDateFrom) &&
      (!filterDateTo || o.created_at <= filterDateTo + 'T23:59:59')
    )
  })

  const hasFilters = !!(filterClient || filterRep || filterDateFrom || filterDateTo)

  return (
    <div className="min-h-screen bg-bg text-ink">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-5 md:py-6 space-y-4 pb-24 md:pb-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-ink font-medium">
              {activeTab === 'orders' ? 'Pedidos' : 'Auditoria Geral'}
              <span className="ml-2 text-xs bg-bg-2 text-gold px-2 py-0.5 rounded-full">
                {activeTab === 'orders' ? orders.length : globalHistory.length}
              </span>
            </h2>
            {canManage && (
              <div className="flex gap-1 border border-line rounded-lg p-0.5 bg-white">
                <button onClick={() => setActiveTab('orders')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${activeTab === 'orders' ? 'bg-gold text-white' : 'text-muted hover:text-ink-2'}`}>Pedidos</button>
                <button onClick={() => setActiveTab('audit')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${activeTab === 'audit' ? 'bg-gold text-white' : 'text-muted hover:text-ink-2'}`}>
                  <History className="w-3 h-3" /> Auditoria
                </button>
              </div>
            )}
          </div>

          {activeTab === 'orders' && (
            <div className="flex items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
                <input className="input pl-9" placeholder="Filtrar por cliente, pedido..." value={filter} onChange={(e) => setFilter(e.target.value)} />
              </div>
              <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center gap-1.5 px-3 py-2 border rounded-lg text-xs font-medium transition-colors ${hasFilters ? 'border-gold text-gold bg-[#fdf9f0]' : 'border-line text-muted hover:border-faint'}`}>
                <Filter className="w-3.5 h-3.5" /> Filtros{hasFilters && <span className="w-1.5 h-1.5 rounded-full bg-gold" />}
              </button>
            </div>
          )}
        </div>

        {/* Advanced filters */}
        {activeTab === 'orders' && showFilters && (
          <div className="bg-white border border-line rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-muted font-medium uppercase tracking-wider">Cliente</label>
              <select className="input text-xs w-full" value={filterClient} onChange={(e) => setFilterClient(e.target.value)}>
                <option value="">Todos</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-muted font-medium uppercase tracking-wider">Representante</label>
              <select className="input text-xs w-full" value={filterRep} onChange={(e) => setFilterRep(e.target.value)}>
                <option value="">Todos</option>
                {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-muted font-medium uppercase tracking-wider">Data Inicial</label>
              <input type="date" className="input text-xs w-full" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-muted font-medium uppercase tracking-wider">Data Final</label>
              <input type="date" className="input text-xs w-full" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} />
            </div>
            {hasFilters && (
              <div className="col-span-2 md:col-span-4 flex justify-end">
                <button onClick={() => { setFilterClient(''); setFilterRep(''); setFilterDateFrom(''); setFilterDateTo('') }} className="text-xs text-terracotta hover:text-[#8a3a2e] transition-colors">Limpar filtros</button>
              </div>
            )}
          </div>
        )}

        {/* Audit tab */}
        {activeTab === 'audit' && (
          <div className="bg-white border border-line rounded-xl p-5">
            <AuditTimeline history={globalHistory} />
          </div>
        )}

        {/* Orders tab */}
        {activeTab === 'orders' && (
          isLoading ? (
            <div className="rounded-xl border border-line overflow-hidden" aria-busy="true" aria-label="Carregando pedidos">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3.5 border-b border-bg-2 last:border-0">
                  <div className="h-4 w-20 rounded bg-[#efe9e1] animate-pulse" />
                  <div className="h-4 w-24 rounded bg-[#efe9e1] animate-pulse hidden sm:block" />
                  <div className="h-4 flex-1 rounded bg-[#efe9e1] animate-pulse" />
                  <div className="h-4 w-16 rounded bg-[#efe9e1] animate-pulse hidden md:block" />
                  <div className="h-5 w-24 rounded-full bg-[#efe9e1] animate-pulse" />
                </div>
              ))}
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-3 md:hidden">
                {filtered.map((order) => (
                  <MobileOrderCard key={order.id} order={order} clientName={clientMap[order.client_id] ?? order.client_id.slice(0, 8)} repName={order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'} onView={() => setViewing(order)} onPDF={() => handlePDF(order)} onDelete={() => setDeleting(order)} />
                ))}
                {filtered.length === 0 && (
                  <div className="rounded-xl border border-line bg-white px-4 py-12 text-center">
                    {filter || hasFilters ? (
                      <p className="text-ink-3 text-sm">Nenhum pedido encontrado com este filtro.</p>
                    ) : (
                      <>
                        <p className="text-ink-3 text-sm">Nenhum pedido ainda.</p>
                        {canManage && <button onClick={() => navigate('/orcamentos')} className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 bg-gold text-white rounded-lg text-sm font-semibold hover:bg-gold-600 transition-colors">Criar primeiro pedido</button>}
                      </>
                    )}
                  </div>
                )}
              </div>

              <div className="hidden md:block overflow-x-auto rounded-xl border border-line">
                <table className="w-full text-sm">
                  <thead className="bg-bg-2">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Pedido</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Orçamento</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Cliente</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Representante</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Itens</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-ink-3 uppercase">Total</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-ink-3 uppercase">Data</th>
                      <th className="px-4 py-3 text-center text-xs font-semibold text-ink-3 uppercase">Status</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((order) => (
                      <tr key={order.id} className="table-row">
                        <td className="px-4 py-3 font-mono text-gold">{order.code}</td>
                        <td className="px-4 py-3 font-mono text-ink-3 text-xs">{order.orc_id}</td>
                        <td className="px-4 py-3 text-ink">{clientMap[order.client_id] ?? order.client_id.slice(0, 8)}</td>
                        <td className="px-4 py-3 text-ink-3">{order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'}</td>
                        <td className="px-4 py-3 text-ink-3 text-xs max-w-[160px] truncate">{itemsSummary(order)}</td>
                        <td className="px-4 py-3 text-right font-semibold text-ink"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></td>
                        <td className="px-4 py-3 text-ink-3 text-xs">{fmtDate(order.created_at)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${order.is_finalized ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
                            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
                            {order.is_finalized ? 'Finalizado' : 'Em andamento'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1.5 items-center">
                            <button title="Ver detalhes" className="text-muted hover:text-gold transition-colors p-1" onClick={() => setViewing(order)}><Eye className="w-4 h-4" /></button>
                            <button title="Gerar PDF" className="text-muted hover:text-blue-500 transition-colors p-1" onClick={() => handlePDF(order)}><FileText className="w-4 h-4" /></button>
                            {canManage && !order.is_finalized && (
                              <button title="Editar" className="text-muted hover:text-gold transition-colors p-1" onClick={() => navigate(`/orcamentos?edit=${order.id}`)}><PenLine className="w-4 h-4" /></button>
                            )}
                            <button title="Excluir" className="text-muted hover:text-red-500 transition-colors p-1" onClick={() => setDeleting(order)}><Trash2 className="w-4 h-4" /></button>
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
                            <span className="text-ink-3">Nenhum pedido ainda.</span>
                            {canManage && <button onClick={() => navigate('/orcamentos')} className="inline-flex items-center gap-1.5 px-4 py-2 bg-gold text-white rounded-lg text-sm font-semibold hover:bg-gold-600 transition-colors">Criar primeiro pedido</button>}
                          </div>
                        )}
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )
        )}
      </div>

      {viewing && (
        <OrderDetailModal
          order={orders.find(o => o.id === viewing.id) ?? viewing}
          clientName={clientMap[viewing.client_id] ?? viewing.client_id}
          repName={viewing.rep_id ? (repMap[viewing.rep_id] ?? '') : ''}
          allOptionals={allOptionals}
          products={products}
          userId={user?.id ?? ''}
          userRole={user?.role ?? ''}
          canSignContract={!!canSignContract}
          clientObj={clientObjMap[viewing.client_id] ?? null}
          onClose={() => setViewing(null)}
          onEdit={() => { setViewing(null); navigate(`/orcamentos?edit=${viewing.id}`) }}
          onFinalize={() => { setFinalizing(viewing); setViewing(null) }}
        />
      )}

      {finalizing && <FinalizeModal order={finalizing} onClose={() => setFinalizing(null)} />}

      {deleting && (
        <div className="modal-overlay" onClick={() => setDeleting(null)}>
          <div className="modal-panel w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-ink mb-2">Confirmar exclusão</h3>
            <p className="text-ink-2 mb-6">Excluir pedido <span className="text-gold font-mono">{deleting.code}</span>? Esta ação não pode ser desfeita.</p>
            <div className="flex justify-end gap-3">
              <button className="btn-secondary" onClick={() => setDeleting(null)}>Cancelar</button>
              <button className="btn-danger" onClick={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}>Excluir</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
