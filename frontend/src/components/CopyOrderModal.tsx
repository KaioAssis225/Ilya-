import { useState } from 'react'
import { useNavigate } from 'react-router'
import { X } from 'lucide-react'
import { DialogPanel } from './Dialog'
import type { Order } from '../types'

/** Copiar pedido/orçamento: escolhe os itens e abre a tela de Orçamento como um
 *  orçamento NOVO já preenchido. Nada é criado aqui: a criação acontece ao
 *  confirmar o orçamento nessa tela, com preço, desconto e imposto recalculados
 *  pelo servidor. */
export function CopyOrderModal({ order, english, onClose }: {
  order: Order
  english: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<Set<string>>(() => new Set(order.items.map(item => item.id)))
  const t = (pt: string, en: string) => english ? en : pt
  const allSelected = order.items.length > 0 && selected.size === order.items.length

  function toggle(id: string) {
    setSelected(previous => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function handleContinue() {
    const itemIds = order.items.filter(item => selected.has(item.id)).map(item => item.id)
    onClose()
    navigate(`/orcamentos?copy=${order.id}&items=${itemIds.join(',')}`)
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
        <p className="text-sm text-ink-2 mb-3">
          {t(
            'Escolha os itens. Eles abrem em um orçamento novo para você revisar e confirmar; os preços e descontos são recalculados com as regras de hoje.',
            'Choose the items. They open in a new quote for you to review and confirm; prices and discounts are recalculated with today’s rules.',
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
        <div className="flex gap-3 justify-end">
          <button type="button" className="btn-secondary" onClick={onClose}>{t('Cancelar', 'Cancel')}</button>
          <button type="button" className="btn-primary" disabled={selected.size === 0} onClick={handleContinue}>
            {t('Continuar', 'Continue')}
          </button>
        </div>
      </DialogPanel>
    </div>
  )
}
