import { useState, useRef, useEffect } from 'react'
import { Search, Eye, Trash2, FileText, X, ImageIcon, PenLine } from 'lucide-react'
import { useOrders, useDeleteOrder } from '../hooks/useOrders'
import { useClients } from '../hooks/useClients'
import { useRepresentatives } from '../hooks/useRepresentatives'
import { useProducts } from '../hooks/useProducts'
import { useOptionals } from '../hooks/useOptionals'
import { generateOrderPDF } from '../lib/generatePDF'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import type { Order, OptionalColor, Product } from '../types'

function fmt(n: number) {
  return Number(n).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

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
  onClose,
}: {
  order: Order
  clientName: string
  repName: string
  allOptionals: OptionalColor[]
  products: Product[]
  onClose: () => void
}) {
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [sigModalOpen, setSigModalOpen] = useState(false)
  const [sigData, setSigData] = useState<string | null>(() => localStorage.getItem(`signature_${order.code}`))
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)

  useEffect(() => {
    if (!sigModalOpen || !canvasRef.current) return
    const canvas = canvasRef.current
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
      e.preventDefault()
      isDrawingRef.current = true
      const { x, y } = getXY(e)
      ctx.beginPath()
      ctx.moveTo(x, y)
    }
    function onMove(e: TouchEvent | MouseEvent) {
      e.preventDefault()
      if (!isDrawingRef.current) return
      const { x, y } = getXY(e)
      ctx.lineTo(x, y)
      ctx.stroke()
    }
    function onEnd() { isDrawingRef.current = false }

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
  }, [sigModalOpen])

  function clearCanvas() {
    const canvas = canvasRef.current!
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
  }

  function confirmSig() {
    const data = canvasRef.current!.toDataURL('image/png')
    localStorage.setItem(`signature_${order.code}`, data)
    setSigData(data)
    setSigModalOpen(false)
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
            <p className="text-[#8b6914] font-bold">R$ {fmt(order.total_value)}</p>
          </div>
          {order.notes && (
            <div className="col-span-2 bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg p-3">
              <p className="text-xs text-[#9d8d81] mb-1">Observações</p>
              <p className="text-[#4a3f38]">{order.notes}</p>
            </div>
          )}
        </div>

        <h4 className="text-xs font-semibold text-[#9d8d81] uppercase tracking-wider mb-2">Itens</h4>
        <div className="border border-[#e8e0d6] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
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
                  <td className="px-3 py-2 text-right text-[#4a3f38]">R$ {fmt(item.unit_price)}</td>
                  <td className="px-3 py-2 text-right font-medium text-[#2c2420]">R$ {fmt(item.qty * item.unit_price)}</td>
                </tr>
              )})}
            </tbody>
            <tfoot>
              <tr className="border-t border-[#e8e0d6] bg-[#f8f6f2]">
                <td colSpan={6} className="px-3 py-2 text-right text-sm text-[#4a3f38] font-medium">Total</td>
                <td className="px-3 py-2 text-right text-[#8b6914] font-bold">R$ {fmt(order.total_value)}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* Seção de assinatura */}
        <div className="mt-5 pt-4 border-t border-[#e8e0d6]">
          {sigData ? (
            <div className="flex flex-col items-center gap-2">
              <p className="text-xs text-[#9d8d81] uppercase tracking-wider font-semibold">Assinatura do Cliente / Contratado</p>
              <img src={sigData} alt="Assinatura" className="max-h-20 max-w-xs border-b border-[#c8bdb5] pb-1" />
              <button
                onClick={() => { setSigModalOpen(true) }}
                className="text-xs text-[#9d8d81] hover:text-[#8b6914] underline transition-colors"
              >
                Reasinar
              </button>
            </div>
          ) : (
            <button
              onClick={() => setSigModalOpen(true)}
              className="w-full flex items-center justify-center gap-2 py-2.5 border border-dashed border-[#c8a84b] text-[#8b6914] rounded-xl hover:bg-[#fdf9f0] transition-colors text-sm font-medium"
            >
              <PenLine className="w-4 h-4" />
              Assinar Pedido
            </button>
          )}
        </div>

        {/* Modal de captura de assinatura */}
        {sigModalOpen && (
          <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/80 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-base font-semibold text-[#2c2420]">Assinatura do Cliente</h4>
                <button onClick={() => setSigModalOpen(false)} className="text-[#9d8d81] hover:text-[#2c2420]"><X className="w-5 h-5" /></button>
              </div>
              <p className="text-xs text-[#9d8d81] mb-3">Assine no campo abaixo com o mouse ou dedo.</p>
              <canvas
                ref={canvasRef}
                width={420}
                height={160}
                className="w-full border border-[#e8e0d6] rounded-xl bg-[#fafaf9] cursor-crosshair touch-none"
              />
              <div className="flex gap-2 mt-4">
                <button
                  onClick={clearCanvas}
                  className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
                >
                  Limpar
                </button>
                <button
                  onClick={() => setSigModalOpen(false)}
                  className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={confirmSig}
                  className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-medium hover:bg-[#7a5c10] transition-colors"
                >
                  Confirmar
                </button>
              </div>
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

// ── Main ──────────────────────────────────────────────────────────────────────

export default function PedidosPage() {
  const { data: orders = [], isLoading } = useOrders()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: products = [] } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const deleteM = useDeleteOrder()

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
      <div className="max-w-7xl mx-auto px-8 py-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[#2c2420] font-medium">
            Pedidos Finalizados
            <span className="ml-2 text-xs bg-[#f0ece6] text-[#8b6914] px-2 py-0.5 rounded-full">{orders.length}</span>
          </h2>
          <div className="relative w-72">
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
          <div className="overflow-x-auto rounded-xl border border-[#e8e0d6]">
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
                    <td className="px-4 py-3 text-right font-semibold text-[#2c2420]">R$ {fmt(order.total_value)}</td>
                    <td className="px-4 py-3 text-[#8a7a6e] text-xs">{fmtDate(order.created_at)}</td>
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
                    <td colSpan={8} className="px-4 py-10 text-center text-[#9d8d81]">
                      {filter ? 'Nenhum pedido encontrado com este filtro.' : 'Nenhum pedido finalizado ainda.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {viewing && (
        <OrderDetailModal
          order={viewing}
          clientName={clientMap[viewing.client_id] ?? viewing.client_id}
          repName={viewing.rep_id ? (repMap[viewing.rep_id] ?? '') : ''}
          allOptionals={allOptionals}
          products={products}
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
