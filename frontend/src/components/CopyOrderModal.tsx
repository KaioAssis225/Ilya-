import { useState } from 'react'
import { useNavigate } from 'react-router'
import { X } from 'lucide-react'
import { DialogPanel } from './Dialog'
import { useCopyOrder } from '../hooks/useOrders'
import type { Order, OrderCopyResult } from '../types'

/** Copiar pedido: escolhe itens e cria um orçamento novo (rascunho).
 *  Preço, desconto e imposto são recalculados pelo servidor. */
export function CopyOrderModal({ order, english, onClose }: {
  order: Order
  english: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const copyM = useCopyOrder()
  const [selected, setSelected] = useState<Set<string>>(() => new Set(order.items.map(item => item.id)))
  const [error, setError] = useState('')
  const [result, setResult] = useState<OrderCopyResult | null>(null)
  const t = (pt: string, en: string) => english ? en : pt
  const sourceLabel = order.is_finalized
    ? t('pedido', 'order')
    : t('orçamento', 'quote')
  const allSelected = order.items.length > 0 && selected.size === order.items.length

  function toggle(id: string) {
    setSelected(previous => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function openCopy(copied: Order) {
    onClose()
    navigate(`/orcamentos?edit=${copied.id}`)
  }

  async function handleCopy() {
    setError('')
    try {
      const copied = await copyM.mutateAsync({
        id: order.id,
        item_ids: order.items.filter(item => selected.has(item.id)).map(item => item.id),
      })
      if (copied.skipped.length > 0) setResult(copied)
      else openCopy(copied.order)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t(`Não foi possível copiar o ${sourceLabel}. Tente novamente.`, `Could not copy the ${sourceLabel}. Please try again.`))
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <DialogPanel onClose={onClose} className="modal-panel w-full max-w-lg p-6 mx-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-ink">
            {order.is_finalized ? t('Copiar pedido', 'Copy order') : t('Copiar orçamento', 'Copy quote')}
          </h3>
          <button type="button" onClick={onClose} aria-label={t('Fechar', 'Close')} className="btn-icon -mr-2">
            <X className="w-4 h-4" />
          </button>
        </div>
        {result ? (
          <>
            <p className="text-sm text-ink-2 mb-3">
              {t(`Orçamento ${result.order.code} criado. Estes itens não foram copiados:`, `Quote ${result.order.code} created. These items were not copied:`)}
            </p>
            <ul role="alert" className="mb-5 space-y-1 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-xs text-warning">
              {result.skipped.map(row => <li key={`${row.product_code}-${row.reason}`}><span className="font-mono font-semibold">{row.product_code}</span>: {row.reason}</li>)}
            </ul>
            <div className="flex justify-end">
              <button type="button" className="btn-primary" onClick={() => openCopy(result.order)}>{t('Abrir orçamento', 'Open quote')}</button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-ink-2 mb-3">
              {t(
                'Escolha os itens para criar um orçamento novo. Os preços e descontos são recalculados com as regras de hoje.',
                'Choose the items for a new quote. Prices and discounts are recalculated with today’s rules.',
              )}
            </p>
            <label className="flex items-center gap-2 border-b border-line pb-2 mb-2 text-sm font-medium text-ink">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => setSelected(allSelected ? new Set() : new Set(order.items.map(item => item.id)))}
              />
              {t('Selecionar todos', 'Select all')}
            </label>
            <ul className="max-h-72 space-y-1 overflow-y-auto mb-4">
              {order.items.map(item => (
                <li key={item.id}>
                  <label className="flex items-start gap-2 rounded-md px-1 py-1.5 text-sm hover:bg-bg-2">
                    <input type="checkbox" className="mt-0.5" checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
                    <span className="min-w-0">
                      <span className="font-mono text-xs text-gold">{item.special_code ?? item.product_code}</span>{item.is_special && <span className="ml-1 rounded bg-gold-soft px-1 py-0.5 text-[9px] font-bold text-gold">ESPECIAL</span>}
                      <span className="block truncate text-ink-2">{item.description}</span>
                    </span>
                    <span className="ml-auto whitespace-nowrap text-xs text-ink-3">{t('Qtd', 'Qty')} {item.qty}</span>
                  </label>
                </li>
              ))}
            </ul>
            {error ? <div role="alert" className="mb-4 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm text-danger">{error}</div> : null}
            <div className="flex gap-3 justify-end">
              <button type="button" className="btn-secondary" onClick={onClose}>{t('Cancelar', 'Cancel')}</button>
              <button type="button" className="btn-primary" disabled={selected.size === 0 || copyM.isPending} onClick={handleCopy}>
                {copyM.isPending ? t('Copiando...', 'Copying...') : t('Criar orçamento', 'Create quote')}
              </button>
            </div>
          </>
        )}
      </DialogPanel>
    </div>
  )
}
