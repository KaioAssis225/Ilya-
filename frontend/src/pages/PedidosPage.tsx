import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Search, Eye, Trash2, FileText, X, ImageIcon, FileSignature, Link, PenLine, Bell, CheckCircle, Clock, History, Filter, Lock } from 'lucide-react'
import { useOrders, useOrder, useDeleteOrder, useFinalizeOrder, useGlobalOrderHistory } from '../hooks/useOrders'
import { useClients } from '../hooks/useClients'
import { useRepresentatives } from '../hooks/useRepresentatives'
import { useProducts } from '../hooks/useProducts'
import { useOptionals } from '../hooks/useOptionals'
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
  created: 'bg-[#648261]',
  edited: 'bg-[#8b6914]',
  finalized: 'bg-[#2c5282]',
}

const ACTION_BADGE: Record<string, string> = {
  created: 'bg-[#648261]/10 text-[#648261]',
  edited: 'bg-[#8b6914]/10 text-[#8b6914]',
  finalized: 'bg-[#2c5282]/10 text-[#2c5282]',
}

// ── Audit Timeline ─────────────────────────────────────────────────────────────

function AuditTimeline({ history }: { history: OrderHistory[] }) {
  if (history.length === 0) {
    return <p className="text-xs text-[#9d8d81] text-center py-6">Nenhum registro de auditoria.</p>
  }
  return (
    <div className="space-y-0">
      {history.map((h, idx) => (
        <div key={h.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className={`w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0 ${ACTION_DOT[h.action] ?? 'bg-[#c8bdb5]'}`} />
            {idx < history.length - 1 && <div className="w-px flex-1 bg-[#e8e0d6] my-1" />}
          </div>
          <div className="pb-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${ACTION_BADGE[h.action] ?? 'bg-gray-100 text-gray-600'}`}>
                {ACTION_LABEL[h.action] ?? h.action}
              </span>
              {h.user && <span className="text-xs text-[#4a3f38] font-medium">{h.user.full_name}</span>}
              <span className="text-[10px] text-[#a89a8e] ml-auto whitespace-nowrap">{fmtDateTime(h.created_at)}</span>
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
          <h3 className="text-base font-semibold text-[#2c2420]">Finalizar Pedido</h3>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420] w-9 h-9 flex items-center justify-center">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-sm text-[#4a3f38] mb-4">
          Pedido <span className="font-mono font-semibold text-[#8b6914]">{order.code}</span> será marcado como finalizado e não poderá mais ser editado.
        </p>
        <label className="block space-y-1 mb-5">
          <span className="text-xs text-[#9d8d81] font-medium">Código Externo (opcional)</span>
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
  const [sigError, setSigError] = useState(false)
  const [notifyLoading, setNotifyLoading] = useState(false)
  const [notifyDone, setNotifyDone] = useState(false)
  const [notifyError, setNotifyError] = useState(false)
  const clientCanvasRef = useRef<HTMLCanvasElement>(null)
  const clientIsDrawingRef = useRef(false)

  const canManage = userRole === 'admin' || userRole === 'vendedor'
  const profileSig = localStorage.getItem(`profile_signature_${userId}`)
  const isContractSigned = !!(order.rep_signed || order.rep_signature || localStorage.getItem(`signature_rep_${order.code}`))
  const isClientSigned = !!(order.client_signed || order.client_signature || localStorage.getItem(`signature_cli_${order.code}`))
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

  async function handleNotifyClient() {
    setNotifyLoading(true); setNotifyError(false)
    try { await api.post(`/orders/${order.id}/notify-client`); setNotifyDone(true) } catch { setNotifyError(true) }
    setNotifyLoading(false)
  }

  function parseOptValue(value: string | null): { label: string; swatch: string | null } | null {
    if (!value) return null
    const slash = value.indexOf('/')
    if (slash !== -1) {
      const cat = value.slice(0, slash); const color = value.slice(slash + 1)
      const catLabels: Record<string, string> = { madeira_teka: 'Madeira Teka', madeira_freijo: 'Madeira Freijó', tecido_faixa_1: 'Faixa 1', tecido_faixa_2: 'Faixa 2', couro_soleta: 'Couro Soleta', couro_pele: 'Couro Pele' }
      return { label: `${catLabels[cat] ?? cat} — ${color}`, swatch: allOptionals.find(o => o.category === cat && o.color_name === color)?.photo_url ?? null }
    }
    return { label: value, swatch: allOptionals.find(o => o.color_name === value)?.photo_url ?? null }
  }

  return (
    <div className="modal-overlay overflow-y-auto" onClick={onClose}>
      <div className="modal-panel w-full max-w-2xl p-6 my-4" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-[#2c2420]">{order.code}</h3>
              {order.is_finalized
                ? <span className="flex items-center gap-1 text-[10px] font-bold bg-green-50 text-green-700 border border-green-200 px-1.5 py-0.5 rounded-full"><Lock className="w-2.5 h-2.5" /> Finalizado</span>
                : <span className="text-[10px] font-bold bg-yellow-50 text-yellow-700 border border-yellow-200 px-1.5 py-0.5 rounded-full">Em andamento</span>
              }
            </div>
            <p className="text-sm text-[#8a7a6e]">Orçamento: <span className="text-[#8b6914]">{order.orc_id}</span>
              {order.external_code && <span className="ml-2 font-mono text-xs text-[#4a3f38]">· {order.external_code}</span>}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canManage && !order.is_finalized && (
              <>
                <button onClick={onEdit} className="flex items-center gap-1.5 px-3 py-1.5 border border-[#e8e0d6] text-[#4a3f38] rounded-lg text-xs font-medium hover:bg-[#f0ece6] transition-colors">
                  <PenLine className="w-3.5 h-3.5" /> Editar
                </button>
                <button onClick={onFinalize} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#8b6914] text-white rounded-lg text-xs font-semibold hover:bg-[#725510] transition-colors">
                  <CheckCircle className="w-3.5 h-3.5" /> Finalizar
                </button>
              </>
            )}
            <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420]"><X className="w-5 h-5" /></button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-[#e8e0d6] mb-4">
          {(['details', 'history'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-xs font-semibold transition-colors ${tab === t ? 'text-[#8b6914] border-b-2 border-[#8b6914] -mb-px' : 'text-[#9d8d81] hover:text-[#4a3f38]'}`}>
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
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3"><p className="text-xs text-[#9d8d81] mb-1">Cliente</p><p className="text-[#2c2420] font-medium">{clientName}</p></div>
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3"><p className="text-xs text-[#9d8d81] mb-1">Representante</p><p className="text-[#2c2420] font-medium">{repName || '—'}</p></div>
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3"><p className="text-xs text-[#9d8d81] mb-1">Data</p><p className="text-[#2c2420]">{fmtDate(order.created_at)}</p></div>
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
                <p className="text-xs text-[#9d8d81] mb-1">{Number(order.total_ipi) > 0 ? 'Total com IPI' : 'Total'}</p>
                <p className="text-[#8b6914] font-bold"><SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></p>
              </div>
              {order.notes && (
                <div className="col-span-2 bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3"><p className="text-xs text-[#9d8d81] mb-1">Observações</p><p className="text-[#4a3f38]">{order.notes}</p></div>
              )}
            </div>

            <h4 className="text-xs font-semibold text-[#9d8d81] uppercase tracking-wider mb-2">Itens</h4>
            <div className="border border-[#e8e0d6] rounded-xl overflow-x-auto">
              <table className="w-full min-w-[700px] text-sm">
                <thead className="bg-[#f0ece6]">
                  <tr>
                    <th className="px-3 py-2 w-10"></th>
                    <th className="px-3 py-2 text-left text-xs text-[#9d8d81]">Produto</th>
                    <th className="px-3 py-2 text-left text-xs text-[#9d8d81]">Dim. (m)</th>
                    <th className="px-3 py-2 text-left text-xs text-[#9d8d81]">Opcionais</th>
                    <th className="px-3 py-2 text-center text-xs text-[#9d8d81]">Qtd</th>
                    <th className="px-3 py-2 text-right text-xs text-[#9d8d81]">Preço Base</th>
                    <th className="px-3 py-2 text-right text-xs text-[#9d8d81]">Desconto</th>
                    <th className="px-3 py-2 text-right text-xs text-[#9d8d81]">IPI</th>
                    <th className="px-3 py-2 text-right text-xs text-[#9d8d81]">Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => {
                    const photoUrl = products.find(p => p.product_code === item.product_code)?.photo_url ?? null
                    const fmtM = (v: number) => Number(v).toFixed(2).replace('.', ',')
                    return (
                      <tr key={item.id} className="border-t border-[#e8e0d6]">
                        <td className="px-2 py-2" style={{ width: '40px', minWidth: '40px' }}>
                          {photoUrl
                            ? <img src={photoUrl} alt="" onClick={() => setActivePhotoModal(photoUrl)} className="object-cover rounded-lg border border-[#e8e0d6] cursor-pointer hover:opacity-80 transition-opacity" style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }} />
                            : <div className="bg-[#f0ece6] rounded-lg flex items-center justify-center" style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }}><ImageIcon className="w-4 h-4 text-[#c8bdb5]" /></div>
                          }
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-[#8b6914] font-mono text-xs">{item.product_code}</span>
                          <div className="text-[#4a3f38] text-xs mt-0.5 max-w-[150px] truncate">{item.description}</div>
                          {item.observacao && <div className="text-[10px] text-[#8b6914] italic mt-0.5 max-w-[150px] truncate">{item.observacao}</div>}
                        </td>
                        <td className="px-3 py-2 text-[#8a7a6e] text-xs whitespace-nowrap">
                          {item.is_circular ? `Ø ${fmtM(item.largura)} × A ${fmtM(item.altura)} m` : `L ${fmtM(item.largura)} × P ${fmtM(item.profundidade)} × A ${fmtM(item.altura)} m`}
                        </td>
                        <td className="px-3 py-2 text-[#8a7a6e] text-xs">
                          {(() => {
                            const parsed = [item.opt_aluminio, item.opt_madeira, item.opt_tecido, item.opt_couro, item.opt_corda].map(parseOptValue).filter(Boolean) as { label: string; swatch: string | null }[]
                            if (parsed.length === 0) return '—'
                            return parsed.map((p, i) => <span key={p.label}>{i > 0 && <span className="mx-1 text-[#c8bdb5]">·</span>}<OptionalWithPreview label={p.label} swatch={p.swatch} /></span>)
                          })()}
                        </td>
                        <td className="px-3 py-2 text-center text-[#2c2420]">{item.qty}</td>
                        <td className="px-3 py-2 text-right text-xs text-[#4a3f38] font-semibold whitespace-nowrap">
                          <SafePrice value={Number(item.unit_price)} />
                        </td>
                        <td className="px-3 py-2 text-right align-middle">
                          {Number(item.discount) > 0 ? (
                            <span className="text-[9px] bg-[#fdf0d0] text-[#8b6914] border border-[#e8d8a0] px-1 py-0.5 rounded font-medium">-{Number(item.discount)}%</span>
                          ) : <span className="text-xs text-[#c8bdb5]">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right align-middle whitespace-nowrap">
                          {Number(item.ipi_rate) > 0
                            ? <span className="text-xs font-semibold text-[#8b6914]">{Number(item.ipi_rate)}%</span>
                            : <span className="text-xs text-[#c8bdb5]">—</span>}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-[#2c2420] whitespace-nowrap">
                          <SafePrice value={item.qty * Number(item.unit_price) * (1 - Number(item.discount) / 100) * (1 + Number(item.ipi_rate) / 100)} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-[#e8e0d6] bg-[#f8f6f2]">
                    <td colSpan={8} className="px-3 py-2.5 text-right text-sm text-[#4a3f38] font-semibold uppercase tracking-wider">Valor Total</td>
                    <td className="px-3 py-2.5 text-right text-[#8b6914] font-bold text-base">
                      <SafePrice value={Number(order.total_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} />
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Assinaturas */}
            <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[#9d8d81] uppercase tracking-wider font-semibold">Assinaturas</span>
                  <span className="flex items-center gap-1 text-xs"><span className={`w-2.5 h-2.5 rounded-full inline-block ${isContractSigned ? 'bg-green-500' : 'bg-yellow-400'}`} /><span className="text-[#9d8d81]">REP</span></span>
                  <span className="flex items-center gap-1 text-xs"><span className={`w-2.5 h-2.5 rounded-full inline-block ${isClientSigned ? 'bg-green-500' : 'bg-yellow-400'}`} /><span className="text-[#9d8d81]">CLI</span></span>
                </div>
                {!isClientUser && (
                  <button disabled={signLinkLoading} onClick={async () => { setSignLinkLoading(true); try { const res = await api.post<{ token: string; url: string }>(`/orders/${order.id}/generate-sign-token`); setSignLink(window.location.origin + res.data.url) } catch { /* ignore */ } finally { setSignLinkLoading(false) } }} className="flex items-center gap-1.5 px-3 py-1.5 border border-[#c8a84b] text-[#8b6914] rounded-lg text-xs font-medium hover:bg-[#fdf9f0] transition-colors disabled:opacity-50">
                    <Link className="w-3.5 h-3.5" />{signLinkLoading ? 'Gerando...' : 'Gerar Link'}
                  </button>
                )}
              </div>
              {signLink && (
                <div className="flex items-center gap-2 mt-2">
                  <input readOnly value={signLink} className="flex-1 text-xs px-2 py-1.5 border border-[#e8e0d6] rounded-lg bg-[#f8f6f2] text-[#4a3f38] font-mono truncate" />
                  <button onClick={() => navigator.clipboard.writeText(signLink)} className="px-2 py-1.5 text-xs border border-[#e8e0d6] rounded-lg text-[#9d8d81] hover:text-[#8b6914] transition-colors whitespace-nowrap">Copiar</button>
                </div>
              )}
              {canSignAsClient && (
                <div className="mt-3">
                  <button onClick={() => { setSigError(false); setClientSigOpen(true) }} className="flex items-center gap-1.5 px-3 py-1.5 border border-[#9d8d81] text-[#4a3f38] rounded-lg text-xs font-medium hover:bg-[#f0ece6] transition-colors">
                    <PenLine className="w-3.5 h-3.5" /> Assinar como Cliente
                  </button>
                </div>
              )}
              {showNotifyBtn && (
                <div className="mt-2">
                  {notifyDone
                    ? <div className="flex items-center gap-1.5 text-xs text-green-600"><CheckCircle className="w-3.5 h-3.5" /> Notificação enviada ao cliente.</div>
                    : <>
                        <button disabled={notifyLoading || !clientHasAccount} onClick={handleNotifyClient} title={!clientHasAccount ? 'Cliente não possui conta no sistema' : undefined} className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium transition-colors ${clientHasAccount ? 'border-[#c8a84b] text-[#8b6914] hover:bg-[#fdf9f0] disabled:opacity-50' : 'border-[#e8e0d6] text-[#c8bdb5] cursor-not-allowed'}`}>
                          <Bell className="w-3.5 h-3.5" />{notifyLoading ? 'Enviando...' : 'Notificar Cliente'}
                        </button>
                        {notifyError && <p className="text-[10px] text-red-500 mt-1">Erro ao enviar notificação.</p>}
                      </>
                  }
                </div>
              )}
            </div>

            {canSignContract && (isClientUser ? !isClientSigned : !isContractSigned) && (
              <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
                {profileSig
                  ? <button onClick={() => { setSigError(false); setConfirmSign(true) }} className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#8b6914] text-white rounded-xl hover:bg-[#7a5c10] transition-colors text-sm font-semibold shadow-sm">
                      <FileSignature className="w-4 h-4" />{isClientUser ? 'Assinar como Cliente' : 'Assinar como Representante'}
                    </button>
                  : <p className="text-xs text-center text-[#9d8d81] py-2">Configure sua assinatura em <span className="text-[#8b6914] font-medium">Minha Conta</span> para assinar contratos.</p>
                }
              </div>
            )}

            {(order.rep_signature || order.client_signature) && (
              <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
                <p className="text-xs font-semibold text-[#9d8d81] uppercase tracking-wider mb-3">Assinaturas do Contrato</p>
                <div className="flex gap-4">
                  <div className="flex-1 text-center">
                    {order.rep_signature ? <img src={order.rep_signature} alt="Assinatura Representante" className="max-h-16 w-full object-contain pb-1" /> : <div className="h-16" />}
                    <div className="border-t border-[#c8bdb5] pt-1"><p className="text-[10px] text-[#9d8d81]">Representante / Ilya</p></div>
                  </div>
                  <div className="flex-1 text-center">
                    {order.client_signature ? <img src={order.client_signature} alt="Assinatura Cliente" className="max-h-16 w-full object-contain pb-1" /> : <div className="h-16" />}
                    <div className="border-t border-[#c8bdb5] pt-1"><p className="text-[10px] text-[#9d8d81]">Cliente / Contratado</p></div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Canvas assinatura cliente */}
        {clientSigOpen && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3"><h4 className="text-base font-semibold text-[#2c2420]">Assinatura do Cliente</h4><button onClick={() => setClientSigOpen(false)} className="text-[#9d8d81] hover:text-[#2c2420]"><X className="w-4 h-4" /></button></div>
              <p className="text-xs text-[#9d8d81] mb-3">Peça ao cliente para assinar no campo abaixo.</p>
              <canvas ref={clientCanvasRef} width={420} height={160} className="w-full border border-[#e8e0d6] rounded-xl bg-[#fafaf9] cursor-crosshair touch-none" />
              <div className="flex gap-2 mt-4">
                <button onClick={() => clientCanvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)} className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors">Limpar</button>
                <button onClick={handleSaveClientSig} disabled={clientSaving} className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-semibold hover:bg-[#7a5c10] transition-colors disabled:opacity-60">{clientSaving ? 'Salvando...' : 'Confirmar Assinatura'}</button>
              </div>
              {sigError && <p className="text-xs text-red-500 mt-3">Falha ao salvar a assinatura no servidor. Verifique a conexão e tente novamente.</p>}
            </div>
          </div>
        )}

        {confirmSign && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
              <h4 className="text-base font-semibold text-[#2c2420] mb-2">Confirmar Assinatura</h4>
              <p className="text-sm text-[#4a3f38] mb-5">Deseja aplicar sua assinatura para o Pedido <span className="text-[#8b6914] font-mono font-semibold">#{order.code}</span>?</p>
              {sigError && <p className="text-xs text-red-500 mb-4">Falha ao salvar a assinatura no servidor. Verifique a conexão e tente novamente.</p>}
              <div className="flex gap-3">
                <button onClick={() => setConfirmSign(false)} className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors">Cancelar</button>
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
                }} className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-semibold hover:bg-[#7a5c10] transition-colors">Confirmar</button>
              </div>
            </div>
          </div>
        )}

        {isSigning && (
          <div className="fixed inset-0 z-[400] flex flex-col items-center justify-center bg-[#1a1410]/88 backdrop-blur-sm">
            <div className="absolute w-[520px] h-[520px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(139,105,20,0.28) 0%, transparent 68%)', animation: 'pulseRadial 2.2s ease-in-out infinite' }} />
            <p className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", backgroundImage: 'linear-gradient(90deg, #7a5a10 0%, #c8952e 25%, #f5d78e 50%, #c8952e 75%, #7a5a10 100%)', backgroundSize: '200% auto', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', animation: 'lightSweep 2.4s linear infinite' }}>ILYA</p>
            <p className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-[#c8952e]" style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}>Gerando Assinatura</p>
            <div className="mt-9 w-52 h-[1px] bg-[#8b6914]/25 overflow-hidden rounded-full"><div className="h-full rounded-full" style={{ background: 'linear-gradient(90deg, #7a5a10, #f5d78e, #7a5a10)', animation: 'progressLine 3s linear forwards' }} /></div>
          </div>
        )}

        {activePhotoModal && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#1a1410]/75 backdrop-blur-sm" onClick={() => setActivePhotoModal(null)}>
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <img src={activePhotoModal} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-[#e8e0d6]" />
              <button onClick={() => setActivePhotoModal(null)} className="absolute -top-3 -right-3 bg-white border border-[#e8e0d6] rounded-full w-8 h-8 flex items-center justify-center shadow-md text-[#9d8d81] hover:text-[#2c2420] transition-colors"><X className="w-4 h-4" /></button>
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
    <div className="bg-white border border-[#e8e0d6] rounded-xl shadow-sm overflow-hidden">
      <div className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="font-mono font-semibold text-[#8b6914] text-sm">{order.code}</span>
            <span className="font-mono text-[10px] text-[#a89a8e] ml-2">{order.orc_id}</span>
            <p className="text-sm font-medium text-[#2c2420] truncate mt-1">{clientName}</p>
            <p className="text-xs text-[#8a7a6e] truncate">{repName}</p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-sm font-bold text-[#2c2420]"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></p>
            <p className="text-[10px] text-[#a89a8e] mt-0.5">{fmtDate(order.created_at)}</p>
          </div>
        </div>
        <div className="mt-2">
          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${order.is_finalized ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
            {order.is_finalized ? 'Finalizado' : 'Em andamento'}
          </span>
        </div>
      </div>
      <div className="flex border-t border-[#f0ece6] divide-x divide-[#f0ece6]">
        <button onClick={onView} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#4a3f38] active:bg-[#f8f6f2] transition-colors" style={{ touchAction: 'manipulation' }}><Eye className="w-4 h-4 text-[#8b6914]" /> Ver</button>
        <button onClick={onPDF} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#4a3f38] active:bg-[#f8f6f2] transition-colors" style={{ touchAction: 'manipulation' }}><FileText className="w-4 h-4 text-[#8b6914]" /> PDF</button>
        <button onClick={onDelete} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#b25e50] active:bg-[#fbf2f0] transition-colors" style={{ touchAction: 'manipulation' }}><Trash2 className="w-4 h-4" /> Excluir</button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PedidosPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canManage = user?.role === 'admin' || user?.role === 'vendedor'
  const { data: orders = [], isLoading } = useOrders()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: products = [] } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const { data: globalHistory = [] } = useGlobalOrderHistory(canManage)
  const deleteM = useDeleteOrder()
  const canSignContract = user?.role === 'representante' || (user?.role === 'vendedor' && !!user?.linked_id)

  async function handlePDF(orderLight: Order) {
    const client = clients.find((c) => c.id === orderLight.client_id)
    if (!client) return
    const rep = orderLight.rep_id ? (reps.find((r) => r.id === orderLight.rep_id) ?? null) : null
    // A listagem não traz os blobs de assinatura (V-M7); busca o detalhe completo p/ o PDF.
    const order = (await api.get<Order>(`/orders/${orderLight.id}`)).data
    await generateOrderPDF(order, client, rep, products)
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
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420]">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-5 md:py-6 space-y-4 pb-24 md:pb-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-[#2c2420] font-medium">
              {activeTab === 'orders' ? 'Pedidos' : 'Auditoria Geral'}
              <span className="ml-2 text-xs bg-[#f0ece6] text-[#8b6914] px-2 py-0.5 rounded-full">
                {activeTab === 'orders' ? orders.length : globalHistory.length}
              </span>
            </h2>
            {canManage && (
              <div className="flex gap-1 border border-[#e8e0d6] rounded-lg p-0.5 bg-white">
                <button onClick={() => setActiveTab('orders')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${activeTab === 'orders' ? 'bg-[#8b6914] text-white' : 'text-[#9d8d81] hover:text-[#4a3f38]'}`}>Pedidos</button>
                <button onClick={() => setActiveTab('audit')} className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${activeTab === 'audit' ? 'bg-[#8b6914] text-white' : 'text-[#9d8d81] hover:text-[#4a3f38]'}`}>
                  <History className="w-3 h-3" /> Auditoria
                </button>
              </div>
            )}
          </div>

          {activeTab === 'orders' && (
            <div className="flex items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a89a8e]" />
                <input className="input pl-9" placeholder="Filtrar por cliente, pedido..." value={filter} onChange={(e) => setFilter(e.target.value)} />
              </div>
              <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center gap-1.5 px-3 py-2 border rounded-lg text-xs font-medium transition-colors ${hasFilters ? 'border-[#8b6914] text-[#8b6914] bg-[#fdf9f0]' : 'border-[#e8e0d6] text-[#9d8d81] hover:border-[#c8bdb5]'}`}>
                <Filter className="w-3.5 h-3.5" /> Filtros{hasFilters && <span className="w-1.5 h-1.5 rounded-full bg-[#8b6914]" />}
              </button>
            </div>
          )}
        </div>

        {/* Advanced filters */}
        {activeTab === 'orders' && showFilters && (
          <div className="bg-white border border-[#e8e0d6] rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-[#9d8d81] font-medium uppercase tracking-wider">Cliente</label>
              <select className="input text-xs w-full" value={filterClient} onChange={(e) => setFilterClient(e.target.value)}>
                <option value="">Todos</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-[#9d8d81] font-medium uppercase tracking-wider">Representante</label>
              <select className="input text-xs w-full" value={filterRep} onChange={(e) => setFilterRep(e.target.value)}>
                <option value="">Todos</option>
                {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-[#9d8d81] font-medium uppercase tracking-wider">Data Inicial</label>
              <input type="date" className="input text-xs w-full" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-[#9d8d81] font-medium uppercase tracking-wider">Data Final</label>
              <input type="date" className="input text-xs w-full" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} />
            </div>
            {hasFilters && (
              <div className="col-span-2 md:col-span-4 flex justify-end">
                <button onClick={() => { setFilterClient(''); setFilterRep(''); setFilterDateFrom(''); setFilterDateTo('') }} className="text-xs text-[#b25e50] hover:text-[#8a3a2e] transition-colors">Limpar filtros</button>
              </div>
            )}
          </div>
        )}

        {/* Audit tab */}
        {activeTab === 'audit' && (
          <div className="bg-white border border-[#e8e0d6] rounded-xl p-5">
            <AuditTimeline history={globalHistory} />
          </div>
        )}

        {/* Orders tab */}
        {activeTab === 'orders' && (
          isLoading ? <p className="text-[#9d8d81] text-sm">Carregando...</p> : (
            <>
              <div className="flex flex-col gap-3 md:hidden">
                {filtered.map((order) => (
                  <MobileOrderCard key={order.id} order={order} clientName={clientMap[order.client_id] ?? order.client_id.slice(0, 8)} repName={order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'} onView={() => setViewing(order)} onPDF={() => handlePDF(order)} onDelete={() => setDeleting(order)} />
                ))}
                {filtered.length === 0 && <div className="rounded-xl border border-[#e8e0d6] bg-white px-4 py-12 text-center text-[#9d8d81] text-sm">{filter || hasFilters ? 'Nenhum pedido encontrado com este filtro.' : 'Nenhum pedido ainda.'}</div>}
              </div>

              <div className="hidden md:block overflow-x-auto rounded-xl border border-[#e8e0d6]">
                <table className="w-full text-sm">
                  <thead className="bg-[#f0ece6]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Pedido</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Orçamento</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Cliente</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Representante</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Itens</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-[#9d8d81] uppercase">Total</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Data</th>
                      <th className="px-4 py-3 text-center text-xs font-semibold text-[#9d8d81] uppercase">Status</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((order) => (
                      <tr key={order.id} className="table-row">
                        <td className="px-4 py-3 font-mono text-[#8b6914]">{order.code}</td>
                        <td className="px-4 py-3 font-mono text-[#8a7a6e] text-xs">{order.orc_id}</td>
                        <td className="px-4 py-3 text-[#2c2420]">{clientMap[order.client_id] ?? order.client_id.slice(0, 8)}</td>
                        <td className="px-4 py-3 text-[#8a7a6e]">{order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'}</td>
                        <td className="px-4 py-3 text-[#8a7a6e] text-xs max-w-[160px] truncate">{itemsSummary(order)}</td>
                        <td className="px-4 py-3 text-right font-semibold text-[#2c2420]"><SafePrice value={Number(order.total_with_ipi) > 0 ? Number(order.total_with_ipi) : Number(order.total_value)} /></td>
                        <td className="px-4 py-3 text-[#8a7a6e] text-xs">{fmtDate(order.created_at)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${order.is_finalized ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
                            {order.is_finalized ? <Lock className="w-2.5 h-2.5" /> : <Clock className="w-2.5 h-2.5" />}
                            {order.is_finalized ? 'Finalizado' : 'Em andamento'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1.5 items-center">
                            <button title="Ver detalhes" className="text-[#9d8d81] hover:text-[#8b6914] transition-colors p-1" onClick={() => setViewing(order)}><Eye className="w-4 h-4" /></button>
                            <button title="Gerar PDF" className="text-[#9d8d81] hover:text-blue-500 transition-colors p-1" onClick={() => handlePDF(order)}><FileText className="w-4 h-4" /></button>
                            {canManage && !order.is_finalized && (
                              <button title="Editar" className="text-[#9d8d81] hover:text-[#8b6914] transition-colors p-1" onClick={() => navigate(`/orcamentos?edit=${order.id}`)}><PenLine className="w-4 h-4" /></button>
                            )}
                            <button title="Excluir" className="text-[#9d8d81] hover:text-red-500 transition-colors p-1" onClick={() => setDeleting(order)}><Trash2 className="w-4 h-4" /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr><td colSpan={9} className="px-4 py-10 text-center text-[#9d8d81]">{filter || hasFilters ? 'Nenhum pedido encontrado com este filtro.' : 'Nenhum pedido ainda.'}</td></tr>
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
            <h3 className="text-lg font-semibold text-[#2c2420] mb-2">Confirmar exclusão</h3>
            <p className="text-[#4a3f38] mb-6">Excluir pedido <span className="text-[#8b6914] font-mono">{deleting.code}</span>? Esta ação não pode ser desfeita.</p>
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
