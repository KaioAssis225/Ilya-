import { Dialog } from './Dialog'

/**
 * Pop-up "Confirmar o catálogo", usado ao criar um orçamento novo: tanto na
 * tela de Orçamento quanto ao copiar um orçamento/pedido existente.
 */
export function CatalogConfirmDialog({ catalogLabel, priceListLabel, english, onBack, onConfirm }: {
  catalogLabel: string
  priceListLabel: string
  english: boolean
  onBack: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog
      title={english ? 'Confirm the catalogue' : 'Confirmar o catálogo'}
      onClose={onBack}
      className="max-w-md"
      layer="sub"
    >
      <p className="text-sm text-ink" data-testid="catalog-confirmation">
        {english ? 'This quote will be made in the ' : 'Este orçamento será feito no catálogo '}
        <strong className="font-semibold">{catalogLabel}</strong>
        {english ? ' catalogue, ' : ', '}
        {english ? 'price list ' : 'tabela '}
        <strong className="font-semibold">{priceListLabel}</strong>
        {english ? '. Is that correct?' : '. Está correto?'}
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onBack}>{english ? 'Back' : 'Voltar'}</button>
        <button type="button" className="btn-primary" onClick={onConfirm}>{english ? 'Confirm' : 'Confirmar'}</button>
      </div>
    </Dialog>
  )
}
