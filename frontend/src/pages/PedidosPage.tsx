import { useState } from 'react'
import { Search, Eye, Trash2, FileText, X } from 'lucide-react'
import { useOrders, useDeleteOrder } from '../hooks/useOrders'
import { useClients } from '../hooks/useClients'
import { useRepresentatives } from '../hooks/useRepresentatives'
import { useProducts } from '../hooks/useProducts'
import { generateOrderPDF } from '../lib/generatePDF'
import type { Order } from '../types'

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
  onClose,
}: {
  order: Order
  clientName: string
  repName: string
  onClose: () => void
}) {
  return (
    <div className="modal-overlay overflow-y-auto" onClick={onClose}>
      <div
        className="modal-panel w-full max-w-2xl p-6 my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold text-stone-100">{order.code}</h3>
            <p className="text-sm text-stone-400">Orçamento: <span className="text-yellow-400">{order.orc_id}</span></p>
          </div>
          <button onClick={onClose} className="text-stone-400 hover:text-white mt-1"><X className="w-5 h-5" /></button>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm mb-5">
          <div className="bg-stone-800 rounded-lg p-3">
            <p className="text-xs text-stone-400 mb-1">Cliente</p>
            <p className="text-stone-100 font-medium">{clientName}</p>
          </div>
          <div className="bg-stone-800 rounded-lg p-3">
            <p className="text-xs text-stone-400 mb-1">Representante</p>
            <p className="text-stone-100 font-medium">{repName || '—'}</p>
          </div>
          <div className="bg-stone-800 rounded-lg p-3">
            <p className="text-xs text-stone-400 mb-1">Data</p>
            <p className="text-stone-100">{fmtDate(order.created_at)}</p>
          </div>
          <div className="bg-stone-800 rounded-lg p-3">
            <p className="text-xs text-stone-400 mb-1">Total</p>
            <p className="text-yellow-400 font-bold">R$ {fmt(order.total_value)}</p>
          </div>
          {order.notes && (
            <div className="col-span-2 bg-stone-800 rounded-lg p-3">
              <p className="text-xs text-stone-400 mb-1">Observações</p>
              <p className="text-stone-300">{order.notes}</p>
            </div>
          )}
        </div>

        <h4 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Itens</h4>
        <div className="border border-stone-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-stone-800/60">
              <tr>
                <th className="px-3 py-2 text-left text-xs text-stone-400">Produto</th>
                <th className="px-3 py-2 text-left text-xs text-stone-400">Dim. (cm)</th>
                <th className="px-3 py-2 text-left text-xs text-stone-400">Opcionais</th>
                <th className="px-3 py-2 text-center text-xs text-stone-400">Qtd</th>
                <th className="px-3 py-2 text-right text-xs text-stone-400">Unit.</th>
                <th className="px-3 py-2 text-right text-xs text-stone-400">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.id} className="border-t border-stone-800">
                  <td className="px-3 py-2">
                    <span className="text-yellow-400 font-mono text-xs">{item.product_code}</span>
                    <div className="text-stone-300 text-xs mt-0.5 max-w-[150px] truncate">{item.description}</div>
                  </td>
                  <td className="px-3 py-2 text-stone-400 text-xs">{item.altura}×{item.largura}×{item.profundidade}</td>
                  <td className="px-3 py-2 text-stone-400 text-xs">
                    {[item.opt_aluminio, item.opt_tecido, item.opt_corda].filter(Boolean).join(' · ') || '—'}
                  </td>
                  <td className="px-3 py-2 text-center text-stone-200">{item.qty}</td>
                  <td className="px-3 py-2 text-right text-stone-300">R$ {fmt(item.unit_price)}</td>
                  <td className="px-3 py-2 text-right font-medium text-stone-100">R$ {fmt(item.qty * item.unit_price)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-stone-700 bg-stone-800/30">
                <td colSpan={5} className="px-3 py-2 text-right text-sm text-stone-300 font-medium">Total</td>
                <td className="px-3 py-2 text-right text-yellow-400 font-bold">R$ {fmt(order.total_value)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
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
    <div className="min-h-screen bg-stone-950 text-stone-100">
      <div className="max-w-7xl mx-auto px-8 py-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-stone-200 font-medium">
            Pedidos Finalizados
            <span className="ml-2 text-xs bg-stone-700 text-yellow-400 px-2 py-0.5 rounded-full">{orders.length}</span>
          </h2>
          <div className="relative w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-500" />
            <input
              className="input pl-9"
              placeholder="Filtrar por cliente, pedido ou orçamento..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
        </div>

        {isLoading ? (
          <p className="text-stone-500 text-sm">Carregando...</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-stone-800">
            <table className="w-full text-sm">
              <thead className="bg-stone-800/60">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Pedido</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Orçamento</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Cliente</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Representante</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Itens</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-stone-400 uppercase">Total</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase">Data</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((order) => (
                  <tr key={order.id} className="table-row">
                    <td className="px-4 py-3 font-mono text-yellow-400">{order.code}</td>
                    <td className="px-4 py-3 font-mono text-stone-400 text-xs">{order.orc_id}</td>
                    <td className="px-4 py-3 text-stone-200">{clientMap[order.client_id] ?? order.client_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-stone-400">{order.rep_id ? (repMap[order.rep_id] ?? '—') : '—'}</td>
                    <td className="px-4 py-3 text-stone-400 text-xs max-w-[160px] truncate">{itemsSummary(order)}</td>
                    <td className="px-4 py-3 text-right font-medium text-stone-100">R$ {fmt(order.total_value)}</td>
                    <td className="px-4 py-3 text-stone-400 text-xs">{fmtDate(order.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          title="Ver detalhes"
                          className="text-stone-400 hover:text-yellow-400 transition-colors"
                          onClick={() => setViewing(order)}
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          title="Gerar PDF"
                          className="text-stone-400 hover:text-blue-400 transition-colors"
                          onClick={() => handlePDF(order)}
                        >
                          <FileText className="w-4 h-4" />
                        </button>
                        <button
                          title="Excluir"
                          className="text-stone-400 hover:text-red-400 transition-colors"
                          onClick={() => setDeleting(order)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-stone-500">
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
          onClose={() => setViewing(null)}
        />
      )}

      {deleting && (
        <div className="modal-overlay" onClick={() => setDeleting(null)}>
          <div className="modal-panel w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-stone-100 mb-2">Confirmar exclusão</h3>
            <p className="text-stone-300 mb-6">
              Excluir pedido <span className="text-yellow-400 font-mono">{deleting.code}</span>?
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
