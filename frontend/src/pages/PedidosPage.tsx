import { useState, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Search, Eye, Trash2, FileText, X, ImageIcon, FileSignature, Link, PenLine, Bell, CheckCircle } from 'lucide-react'
import { useOrders, useDeleteOrder } from '../hooks/useOrders'
import { useClients } from '../hooks/useClients'
import { useRepresentatives } from '../hooks/useRepresentatives'
import { useProducts } from '../hooks/useProducts'
import { useOptionals } from '../hooks/useOptionals'
import { useAuth } from '../hooks/useAuth'
import { generateOrderPDF } from '../lib/generatePDF'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import { SafePrice } from '../components/SafePrice'
import api from '../lib/api'
import type { Order, OptionalColor, Product, Client } from '../types'

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('pt-BR')
}

function itemsSummary(order: Order) {
  return order.items.map((i) => `${i.product_code}(${i.qty})`).join(', ')
}

// ── Modal de detalhes ─────────────────────────────────────────────────────────

function OrderDetailModal({
  order,
  clientName,
  repName,
  allOptionals,
  products,
  userId,
  userRole,
  canSignContract,
  clientObj,
  onClose,
}: {
  order: Order
  clientName: string
  repName: string
  allOptionals: OptionalColor[]
  products: Product[]
  userId: string
  userRole: string
  canSignContract: boolean
  clientObj: Client | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const isClientUser = userRole === 'vendedor'
  const sigKey = isClientUser ? `signature_cli_${order.code}` : `signature_rep_${order.code}`
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [confirmSign, setConfirmSign] = useState(false)
  const [isSigning, setIsSigning] = useState(false)
  const [signLink, setSignLink] = useState<string | null>(null)
  const [signLinkLoading, setSignLinkLoading] = useState(false)
  const [clientSigOpen, setClientSigOpen] = useState(false)
  const [clientSaving, setClientSaving] = useState(false)
  const [notifyLoading, setNotifyLoading] = useState(false)
  const [notifyDone, setNotifyDone] = useState(false)
  const [notifyError, setNotifyError] = useState(false)
  const clientCanvasRef = useRef<HTMLCanvasElement>(null)
  const clientIsDrawingRef = useRef(false)

  const profileSig = localStorage.getItem(`profile_signature_${userId}`)
  const isContractSigned = !!(order.rep_signature || localStorage.getItem(`signature_rep_${order.code}`))
  const isClientSigned = !!(order.client_signature || localStorage.getItem(`signature_cli_${order.code}`))
  const canSignAsClient = (userRole === 'representante' || userRole === 'admin') && !isClientSigned
  const showNotifyBtn = userRole === 'representante' || userRole === 'admin'
  const clientHasAccount = !!clientObj?.has_user

  useEffect(() => {
    if (!clientSigOpen || !clientCanvasRef.current) return
    const canvas = clientCanvasRef.current
    const ctx = canvas.getContext('2d')!
    ctx.strokeStyle = '#2c2420'
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    function getXY(e: TouchEvent | MouseEvent) {
      const rect = canvas.getBoundingClientRect()
      if ('touches' in e) {
        return { x: (e as TouchEvent).touches[0].clientX - rect.left, y: (e as TouchEvent).touches[0].clientY - rect.top }
      }
      return { x: (e as MouseEvent).clientX - rect.left, y: (e as MouseEvent).clientY - rect.top }
    }
    function onStart(e: TouchEvent | MouseEvent) {
      e.preventDefault(); clientIsDrawingRef.current = true
      const { x, y } = getXY(e); ctx.beginPath(); ctx.moveTo(x, y)
    }
    function onMove(e: TouchEvent | MouseEvent) {
      e.preventDefault(); if (!clientIsDrawingRef.current) return
      const { x, y } = getXY(e); ctx.lineTo(x, y); ctx.stroke()
    }
    function onEnd() { clientIsDrawingRef.current = false }

    canvas.addEventListener('mousedown', onStart)
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseup', onEnd)
    canvas.addEventListener('touchstart', onStart, { passive: false })
    canvas.addEventListener('touchmove', onMove, { passive: false })
    canvas.addEventListener('touchend', onEnd)
    return () => {
      canvas.removeEventListener('mousedown', onStart)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseup', onEnd)
      canvas.removeEventListener('touchstart', onStart)
      canvas.removeEventListener('touchmove', onMove)
      canvas.removeEventListener('touchend', onEnd)
    }
  }, [clientSigOpen])

  async function handleSaveClientSig() {
    if (!clientCanvasRef.current) return
    const data = clientCanvasRef.current.toDataURL('image/png')
    setClientSaving(true)
    try {
      await api.post(`/orders/${order.id}/sign-client`, { signature: data })
    } catch { /* persist locally even if API fails */ }
    localStorage.setItem(`signature_cli_${order.code}`, data)
    queryClient.invalidateQueries({ queryKey: ['orders'] })
    setClientSaving(false)
    setClientSigOpen(false)
  }

  async function handleNotifyClient() {
    setNotifyLoading(true)
    setNotifyError(false)
    try {
      await api.post(`/orders/${order.id}/notify-client`)
      setNotifyDone(true)
    } catch {
      setNotifyError(true)
    }
    setNotifyLoading(false)
  }

  // Values may be "category/color" (qualified) or plain color names
  function parseOptValue(value: string | null): { label: string; swatch: string | null } | null {
    if (!value) return null
    const slash = value.indexOf('/')
    if (slash !== -1) {
      const cat = value.slice(0, slash)
      const color = value.slice(slash + 1)
      const catLabels: Record<string, string> = {
        madeira_teka: 'Madeira Teka', madeira_freijo: 'Madeira Freijó',
        tecido_faixa_1: 'Faixa 1', tecido_faixa_2: 'Faixa 2',
        couro_soleta: 'Couro Soleta', couro_pele: 'Couro Pele',
      }
      const label = `${catLabels[cat] ?? cat} — ${color}`
      const swatch = allOptionals.find(o => o.category === cat && o.color_name === color)?.photo_url ?? null
      return { label, swatch }
    }
    const swatch = allOptionals.find(o => o.color_name === value)?.photo_url ?? null
    return { label: value, swatch }
  }

  return (
    <div className="modal-overlay overflow-y-auto" onClick={onClose}>
      <div
        className="modal-panel w-full max-w-2xl p-6 my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold text-[#2c2420]">{order.code}</h3>
            <p className="text-sm text-[#8a7a6e]">Orçamento: <span className="text-[#8b6914]">{order.orc_id}</span></p>
          </div>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420] mt-1"><X className="w-5 h-5" /></button>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm mb-5">
          <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
            <p className="text-xs text-[#9d8d81] mb-1">Cliente</p>
            <p className="text-[#2c2420] font-medium">{clientName}</p>
          </div>
          <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
            <p className="text-xs text-[#9d8d81] mb-1">Representante</p>
            <p className="text-[#2c2420] font-medium">{repName || '—'}</p>
          </div>
          <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
            <p className="text-xs text-[#9d8d81] mb-1">Data</p>
            <p className="text-[#2c2420]">{fmtDate(order.created_at)}</p>
          </div>
          <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
            <p className="text-xs text-[#9d8d81] mb-1">Total</p>
            <p className="text-[#8b6914] font-bold"><SafePrice value={Number(order.total_value)} /></p>
          </div>
          {order.notes && (
            <div className="col-span-2 bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
              <p className="text-xs text-[#9d8d81] mb-1">Observações</p>
              <p className="text-[#4a3f38]">{order.notes}</p>
            </div>
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
                <th className="px-3 py-2 text-right text-xs text-[#9d8d81]">Unit.</th>
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
                      ? <img src={photoUrl} alt="" onClick={() => setActivePhotoModal(photoUrl)}
                          className="object-cover rounded-lg border border-[#e8e0d6] cursor-pointer hover:opacity-80 transition-opacity"
                          style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }} />
                      : <div className="bg-[#f0ece6] rounded-lg flex items-center justify-center"
                          style={{ width: '36px', height: '36px', minWidth: '36px', minHeight: '36px' }}>
                          <ImageIcon className="w-4 h-4 text-[#c8bdb5]" />
                        </div>
                    }
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-[#8b6914] font-mono text-xs">{item.product_code}</span>
                    <div className="text-[#4a3f38] text-xs mt-0.5 max-w-[150px] truncate">{item.description}</div>
                  </td>
                  <td className="px-3 py-2 text-[#8a7a6e] text-xs whitespace-nowrap">
                    {item.is_circular
                      ? `Ø ${fmtM(item.largura)} × A ${fmtM(item.altura)} m`
                      : `L ${fmtM(item.largura)} × P ${fmtM(item.profundidade)} × A ${fmtM(item.altura)} m`}
                  </td>
                  <td className="px-3 py-2 text-[#8a7a6e] text-xs">
                    {(() => {
                      const rawVals = [item.opt_aluminio, item.opt_madeira, item.opt_tecido, item.opt_couro, item.opt_corda]
                      const parsed = rawVals.map(parseOptValue).filter(Boolean) as { label: string; swatch: string | null }[]
                      if (parsed.length === 0) return '—'
                      return parsed.map((p, i) => (
                        <span key={i}>
                          {i > 0 && <span className="mx-1 text-[#c8bdb5]">·</span>}
                          <OptionalWithPreview label={p.label} swatch={p.swatch} />
                        </span>
                      ))
                    })()}
                  </td>
                  <td className="px-3 py-2 text-center text-[#2c2420]">{item.qty}</td>
                  <td className="px-3 py-2 text-right text-[#4a3f38]"><SafePrice value={Number(item.unit_price)} /></td>
                  <td className="px-3 py-2 text-right font-medium text-[#2c2420]"><SafePrice value={item.qty * Number(item.unit_price)} /></td>
                </tr>
              )})}
            </tbody>
            <tfoot>
              <tr className="border-t border-[#e8e0d6] bg-[#f8f6f2]">
                <td colSpan={6} className="px-3 py-2 text-right text-sm text-[#4a3f38] font-medium">Total</td>
                <td className="px-3 py-2 text-right text-[#8b6914] font-bold"><SafePrice value={Number(order.total_value)} /></td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* Gerar Link de Assinatura */}
        <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#9d8d81] uppercase tracking-wider font-semibold">Assinaturas</span>
              <span className="flex items-center gap-1 text-xs">
                <span title="Representante" className={`w-2.5 h-2.5 rounded-full inline-block ${order.rep_signature ? 'bg-green-500' : 'bg-red-400'}`} />
                <span className="text-[#9d8d81]">REP</span>
              </span>
              <span className="flex items-center gap-1 text-xs">
                <span title="Cliente" className={`w-2.5 h-2.5 rounded-full inline-block ${order.client_signature ? 'bg-green-500' : 'bg-red-400'}`} />
                <span className="text-[#9d8d81]">CLI</span>
              </span>
            </div>
            {!isClientUser && (
              <button
                disabled={signLinkLoading}
                onClick={async () => {
                  setSignLinkLoading(true)
                  try {
                    const res = await api.post<{ token: string; url: string; expires_in: number }>(`/orders/${order.id}/generate-sign-token`)
                    setSignLink(window.location.origin + res.data.url)
                  } catch {
                    // ignore
                  } finally {
                    setSignLinkLoading(false)
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-[#c8a84b] text-[#8b6914] rounded-lg text-xs font-medium hover:bg-[#fdf9f0] transition-colors disabled:opacity-50"
              >
                <Link className="w-3.5 h-3.5" />
                {signLinkLoading ? 'Gerando...' : 'Gerar Link'}
              </button>
            )}
          </div>
          {signLink && (
            <div className="flex items-center gap-2 mt-2">
              <input
                readOnly
                value={signLink}
                className="flex-1 text-xs px-2 py-1.5 border border-[#e8e0d6] rounded-lg bg-[#f8f6f2] text-[#4a3f38] font-mono truncate"
              />
              <button
                onClick={() => navigator.clipboard.writeText(signLink)}
                className="px-2 py-1.5 text-xs border border-[#e8e0d6] rounded-lg text-[#9d8d81] hover:text-[#8b6914] hover:border-[#c8a84b] transition-colors whitespace-nowrap"
              >
                Copiar
              </button>
            </div>
          )}

          {/* Assinar como Cliente (presencialmente) */}
          {canSignAsClient && (
            <div className="mt-3">
              <button
                onClick={() => setClientSigOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-[#9d8d81] text-[#4a3f38] rounded-lg text-xs font-medium hover:bg-[#f0ece6] transition-colors"
              >
                <PenLine className="w-3.5 h-3.5" />
                Assinar como Cliente
              </button>
            </div>
          )}

          {/* Notificar Cliente */}
          {showNotifyBtn && (
            <div className="mt-2">
              {notifyDone ? (
                <div className="flex items-center gap-1.5 text-xs text-green-600">
                  <CheckCircle className="w-3.5 h-3.5" />
                  Notificação enviada ao cliente.
                </div>
              ) : (
                <>
                  <button
                    disabled={notifyLoading || !clientHasAccount}
                    onClick={handleNotifyClient}
                    title={!clientHasAccount ? 'Cliente não possui conta no sistema' : 'Enviar notificação de assinatura ao cliente'}
                    className={`flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-xs font-medium transition-colors ${
                      clientHasAccount
                        ? 'border-[#c8a84b] text-[#8b6914] hover:bg-[#fdf9f0] disabled:opacity-50'
                        : 'border-[#e8e0d6] text-[#c8bdb5] cursor-not-allowed'
                    }`}
                  >
                    <Bell className="w-3.5 h-3.5" />
                    {notifyLoading ? 'Enviando...' : 'Notificar Cliente'}
                  </button>
                  {notifyError && (
                    <p className="text-[10px] text-red-500 mt-1">Erro ao enviar notificação.</p>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Assinar Contrato — representante ou cliente */}
        {canSignContract && (isClientUser ? !isClientSigned : !isContractSigned) && (
          <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
            {profileSig ? (
              <button
                onClick={() => setConfirmSign(true)}
                className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#8b6914] text-white rounded-xl hover:bg-[#7a5c10] transition-colors text-sm font-semibold shadow-sm"
              >
                <FileSignature className="w-4 h-4" />
                {isClientUser ? 'Assinar como Cliente' : 'Assinar como Representante'}
              </button>
            ) : (
              <p className="text-xs text-center text-[#9d8d81] py-2">
                Configure sua assinatura em <span className="text-[#8b6914] font-medium">Minha Conta</span> para assinar contratos.
              </p>
            )}
          </div>
        )}

        {/* Assinaturas do Contrato — display duplo */}
        {(order.rep_signature || order.client_signature) && (
          <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
            <p className="text-xs font-semibold text-[#9d8d81] uppercase tracking-wider mb-3">Assinaturas do Contrato</p>
            <div className="flex gap-4">
              <div className="flex-1 text-center">
                {order.rep_signature
                  ? <img src={order.rep_signature} alt="Assinatura Representante" className="max-h-16 w-full object-contain pb-1" />
                  : <div className="h-16" />
                }
                <div className="border-t border-[#c8bdb5] pt-1">
                  <p className="text-[10px] text-[#9d8d81]">Representante / Ilya</p>
                </div>
              </div>
              <div className="flex-1 text-center">
                {order.client_signature
                  ? <img src={order.client_signature} alt="Assinatura Cliente" className="max-h-16 w-full object-contain pb-1" />
                  : <div className="h-16" />
                }
                <div className="border-t border-[#c8bdb5] pt-1">
                  <p className="text-[10px] text-[#9d8d81]">Cliente / Contratado</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Canvas de assinatura do cliente (coleta presencial) */}
        {clientSigOpen && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-base font-semibold text-[#2c2420]">Assinatura do Cliente</h4>
                <button onClick={() => setClientSigOpen(false)} className="text-[#9d8d81] hover:text-[#2c2420]"><X className="w-4 h-4" /></button>
              </div>
              <p className="text-xs text-[#9d8d81] mb-3">Peça ao cliente para assinar no campo abaixo.</p>
              <canvas
                ref={clientCanvasRef}
                width={420}
                height={160}
                className="w-full border border-[#e8e0d6] rounded-xl bg-[#fafaf9] cursor-crosshair touch-none"
              />
              <div className="flex gap-2 mt-4">
                <button
                  onClick={() => clientCanvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)}
                  className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
                >
                  Limpar
                </button>
                <button
                  onClick={handleSaveClientSig}
                  disabled={clientSaving}
                  className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-semibold hover:bg-[#7a5c10] transition-colors disabled:opacity-60"
                >
                  {clientSaving ? 'Salvando...' : 'Confirmar Assinatura'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Confirm sign dialog */}
        {confirmSign && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
              <h4 className="text-base font-semibold text-[#2c2420] mb-2">Confirmar Assinatura</h4>
              <p className="text-sm text-[#4a3f38] mb-5">
                Deseja aplicar sua assinatura registrada para assinar o contrato do Pedido{' '}
                <span className="text-[#8b6914] font-mono font-semibold">#{order.code}</span>?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmSign(false)}
                  className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={async () => {
                    setConfirmSign(false)
                    setIsSigning(true)
                    const endpoint = isClientUser
                      ? `/orders/${order.id}/sign-client`
                      : `/orders/${order.id}/sign-representative`
                    try {
                      await api.post(endpoint, { signature: profileSig })
                    } catch {
                      // persist locally even if API fails
                    }
                    localStorage.setItem(sigKey, profileSig!)
                    queryClient.invalidateQueries({ queryKey: ['orders'] })
                    setIsSigning(false)
                  }}
                  className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-semibold hover:bg-[#7a5c10] transition-colors"
                >
                  Confirmar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Signing loading overlay */}
        {isSigning && (
          <div className="fixed inset-0 z-[400] flex flex-col items-center justify-center bg-[#1a1410]/88 backdrop-blur-sm">
            <div
              className="absolute w-[520px] h-[520px] rounded-full pointer-events-none"
              style={{
                background: 'radial-gradient(circle, rgba(139,105,20,0.28) 0%, transparent 68%)',
                animation: 'pulseRadial 2.2s ease-in-out infinite',
              }}
            />
            <p
              className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none"
              style={{
                fontFamily: "'Cormorant Garamond', Georgia, serif",
                backgroundImage: 'linear-gradient(90deg, #7a5a10 0%, #c8952e 25%, #f5d78e 50%, #c8952e 75%, #7a5a10 100%)',
                backgroundSize: '200% auto',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                animation: 'lightSweep 2.4s linear infinite',
              }}
            >
              ILYA
            </p>
            <p
              className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-[#c8952e]"
              style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}
            >
              Gerando Assinatura
            </p>
            <div className="mt-9 w-52 h-[1px] bg-[#8b6914]/25 overflow-hidden rounded-full">
              <div
                className="h-full rounded-full"
                style={{
                  background: 'linear-gradient(90deg, #7a5a10, #f5d78e, #7a5a10)',
                  animation: 'progressLine 3s linear forwards',
                }}
              />
            </div>
          </div>
        )}

        {activePhotoModal && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#1a1410]/75 backdrop-blur-sm"
            onClick={() => setActivePhotoModal(null)}>
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <img src={activePhotoModal} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-[#e8e0d6]" />
              <button
                onClick={() => setActivePhotoModal(null)}
                className="absolute -top-3 -right-3 bg-white border border-[#e8e0d6] rounded-full w-8 h-8 flex items-center justify-center shadow-md text-[#9d8d81] hover:text-[#2c2420] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Mobile order card ───────────────────────────────────────────────────────

function SigDot({ signed, label }: { signed: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-2.5 h-2.5 rounded-full inline-block ${signed ? 'bg-green-500' : 'bg-red-400'}`} />
      <span className="text-[10px] text-[#9d8d81] font-medium">{label}</span>
    </span>
  )
}

function MobileOrderCard({
  order, clientName, repName, onView, onPDF, onDelete,
}: {
  order: Order
  clientName: string
  repName: string
  onView: () => void
  onPDF: () => void
  onDelete: () => void
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
            <p className="text-sm font-bold text-[#2c2420]"><SafePrice value={Number(order.total_value)} /></p>
            <p className="text-[10px] text-[#a89a8e] mt-0.5">{fmtDate(order.created_at)}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 mt-3">
          <SigDot signed={!!order.rep_signature} label="REP" />
          <SigDot signed={!!order.client_signature} label="CLI" />
        </div>
      </div>

      <div className="flex border-t border-[#f0ece6] divide-x divide-[#f0ece6]">
        <button
          onClick={onView}
          className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#4a3f38] active:bg-[#f8f6f2] transition-colors"
          style={{ touchAction: 'manipulation' }}
        >
          <Eye className="w-4 h-4 text-[#8b6914]" /> Ver
        </button>
        <button
          onClick={onPDF}
          className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#4a3f38] active:bg-[#f8f6f2] transition-colors"
          style={{ touchAction: 'manipulation' }}
        >
          <FileText className="w-4 h-4 text-[#8b6914]" /> PDF
        </button>
        <button
          onClick={onDelete}
          className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium text-[#b25e50] active:bg-[#fbf2f0] transition-colors"
          style={{ touchAction: 'manipulation' }}
        >
          <Trash2 className="w-4 h-4" /> Excluir
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PedidosPage() {
  const { user } = useAuth()
  const { data: orders = [], isLoading } = useOrders()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: products = [] } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const deleteM = useDeleteOrder()

  const canSignContract = user?.role === 'representante' || (user?.role === 'vendedor' && !!user?.linked_id)

  async function handlePDF(order: Order) {
    const client = clients.find((c) => c.id === order.client_id)
    if (!client) return
    const rep = order.rep_id ? (reps.find((r) => r.id === order.rep_id) ?? null) : null
    await generateOrderPDF(order, client, rep, products)
  }

  const [filter, setFilter] = useState('')
  const [viewing, setViewing] = useState<Order | null>(null)
  const [deleting, setDeleting] = useState<Order | null>(null)

  const clientMap = Object.fromEntries(clients.map((c) => [c.id, c.name]))
  const clientObjMap = Object.fromEntries(clients.map((c) => [c.id, c]))
  const repMap = Object.fromEntries(reps.map((r) => [r.id, r.name]))

  const filtered = orders.filter((o) => {
    const q = filter.toLowerCase()
    const clientName = (clientMap[o.client_id] ?? '').toLowerCase()
    return (
      o.code.toLowerCase().includes(q) ||
      o.orc_id.toLowerCase().includes(q) ||
      clientName.includes(q)
    )
  })

  return (
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420]">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-5 md:py-6 space-y-4 pb-24 md:pb-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-[#2c2420] font-medium">
            Pedidos Finalizados
            <span className="ml-2 text-xs bg-[#f0ece6] text-[#8b6914] px-2 py-0.5 rounded-full">{orders.length}</span>
          </h2>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a89a8e]" />
            <input
              className="input pl-9"
              placeholder="Filtrar por cliente, pedido ou orçamento..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
        </div>

        {isLoading ? (
          <p className="text-[#9d8d81] text-sm">Carregando...</p>
        ) : (
          <>
          {/* ── Mobile: card list ───────────────────────────────────── */}
          <div className="flex flex-col gap-3 md:hidden">
            {filtered.map((order) => (
              <MobileOrderCard
                key={order.id}
                order={order}
                clientName={clientMap[order.client_id] ?? order.client_id.slice(0, 8)}
                repName={order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'}
                onView={() => setViewing(order)}
                onPDF={() => handlePDF(order)}
                onDelete={() => setDeleting(order)}
              />
            ))}
            {filtered.length === 0 && (
              <div className="rounded-xl border border-[#e8e0d6] bg-white px-4 py-12 text-center text-[#9d8d81] text-sm">
                {filter ? 'Nenhum pedido encontrado com este filtro.' : 'Nenhum pedido finalizado ainda.'}
              </div>
            )}
          </div>

          {/* ── Desktop: table ──────────────────────────────────────── */}
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
                  <th className="px-4 py-3 text-center text-xs font-semibold text-[#9d8d81] uppercase">Assinaturas</th>
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
                    <td className="px-4 py-3 text-right font-semibold text-[#2c2420]"><SafePrice value={Number(order.total_value)} /></td>
                    <td className="px-4 py-3 text-[#8a7a6e] text-xs">{fmtDate(order.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        <span title="Representante" className={`w-2.5 h-2.5 rounded-full inline-block ${order.rep_signature ? 'bg-green-500' : 'bg-red-400'}`} />
                        <span className="text-[10px] text-[#9d8d81]">REP</span>
                        <span title="Cliente" className={`w-2.5 h-2.5 rounded-full inline-block ${order.client_signature ? 'bg-green-500' : 'bg-red-400'}`} />
                        <span className="text-[10px] text-[#9d8d81]">CLI</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button title="Ver detalhes" className="text-[#9d8d81] hover:text-[#8b6914] transition-colors" onClick={() => setViewing(order)}>
                          <Eye className="w-4 h-4" />
                        </button>
                        <button title="Gerar PDF" className="text-[#9d8d81] hover:text-blue-500 transition-colors" onClick={() => handlePDF(order)}>
                          <FileText className="w-4 h-4" />
                        </button>
                        <button title="Excluir" className="text-[#9d8d81] hover:text-red-500 transition-colors" onClick={() => setDeleting(order)}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-10 text-center text-[#9d8d81]">
                      {filter ? 'Nenhum pedido encontrado com este filtro.' : 'Nenhum pedido finalizado ainda.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </>
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
        />
      )}

      {deleting && (
        <div className="modal-overlay" onClick={() => setDeleting(null)}>
          <div className="modal-panel w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-[#2c2420] mb-2">Confirmar exclusão</h3>
            <p className="text-[#4a3f38] mb-6">
              Excluir pedido <span className="text-[#8b6914] font-mono">{deleting.code}</span>?
              Esta ação não pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button className="btn-secondary" onClick={() => setDeleting(null)}>Cancelar</button>
              <button
                className="btn-danger"
                onClick={async () => {
                  await deleteM.mutateAsync(deleting.id)
                  setDeleting(null)
                }}
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
