import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRightLeft,
  ArrowUpRight,
  Boxes,
  Check,
  Edit3,
  Image as ImageIcon,
  PackagePlus,
  Plus,
  Search,
  Trash2,
  Warehouse,
  X,
} from 'lucide-react'
import { useNavigate } from 'react-router'
import { useAuth } from '../hooks/useAuth'
import { useLocale } from '../hooks/useLocale'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { useOrders } from '../hooks/useOrders'
import { useProductsByCodes } from '../hooks/useProducts'
import {
  type ShowroomBox,
  type ShowroomItem,
  type ShowroomOptionalChoice,
  type ShowroomOptionalChoiceInput,
  type ShowroomPriceList,
  type ShowroomProduct,
  useAddShowroomItem,
  useCreateShowroomBox,
  useDeleteShowroomBox,
  useRemoveShowroomItem,
  useShowroomBoxes,
  useShowroomProducts,
  useShowroomTransfers,
  useTransferShowroomItem,
  type ShowroomTransfer,
  useUpdateShowroomBox,
  useUpdateShowroomItem,
} from '../hooks/useShowrooms'
import {
  allowedForApplication,
  allowsCustomFor,
  applicationName,
  customOptionLabel,
  CUSTOM_OPTION,
  productApplications,
} from '../lib/optionalApplications'
import { optionalCategoryLabel, optionalName } from '../lib/optionalLabels'
import { addShowroomItemToCart } from '../lib/showroomCart'
import type { OptionalColor, Product } from '../types'

const PRICE_OPTIONS: ShowroomPriceList[] = ['lojista', 'arquiteto', 'corporativo', 'pvp']

const TEXT = {
  'pt-PT': {
    stock: 'Estoque', stockLocation: 'Local Estoque', editLocation: 'Editar local',
    close: 'Fechar', locationName: 'Nome da box', priceList: 'Tabela de preço',
    priceHelp: 'A tabela escolhida define todos os valores desta box.', cancel: 'Cancelar',
    save: 'Salvar box', saving: 'Salvando…', open: 'Abrir', products: 'Produtos',
    productConfigurations: 'configurações de produto', totalValue: 'Valor total', pieces: 'peças',
    loadingBoxes: 'Carregando boxes', loadError: 'Não foi possível carregar o estoque.',
    retry: 'Tentar novamente', noBoxes: 'Nenhuma box criada',
    noBoxesHelp: 'Crie uma box para cada local de estoque, feira ou exposição.',
    createFirst: 'Criar primeiro local', boxesLabel: 'Boxes do estoque', allBoxes: 'Todas as boxes',
    deleteBox: 'Excluir box', valuesBy: 'Valores calculados pela tabela', quantity: 'Quantidade',
    productsHere: 'Produtos nesta box', emptyBox: 'Esta box ainda está vazia',
    emptyBoxHelp: 'Use a pesquisa para adicionar o primeiro produto.', product: 'Produto',
    unit: 'Unitário', total: 'Total', actions: 'Ações', remove: 'Remover', perUnit: 'por unidade',
    searchProducts: 'Buscar produtos', searchPlaceholder: 'Código ou nome', searching: 'Buscando produtos…',
    searchError: 'Não foi possível consultar os produtos.', noProducts: 'Nenhum produto encontrado.',
    configure: 'Configurar', configureProduct: 'Configurar produto', chooseFinishes: 'Escolha os opcionais',
    optionalChoiceHelp: 'Cada combinação será guardada como uma linha separada.',
    loadingProduct: 'Carregando configuração…', productError: 'Não foi possível carregar os opcionais deste produto.',
    noFinishes: 'Este produto não possui opcionais configuráveis.', required: 'Obrigatório',
    chooseOption: 'Escolha uma opção', addToStock: 'Adicionar ao estoque', adding: 'Adicionando…',
    added: 'Adicionado', quantityOf: 'Quantidade de', noOptionals: 'Sem opcionais',
    saveError: 'Não foi possível salvar a box.', deleteError: 'Não foi possível excluir a box.',
    addError: 'Não foi possível adicionar o produto.', removeError: 'Não foi possível remover o produto.',
    confirmDelete: (name: string) => `Excluir a box “${name}” e todos os produtos dela?`,
    confirmRemove: (code: string) => `Remover ${code} desta box?`,
    requiredPending: (count: number) => `${count} opcional(is) obrigatório(s) sem escolha: o item será guardado como pendente.`,
    updateError: 'Não foi possível alterar a quantidade.',
    transfer: 'Transferência', transferTitle: 'Transferir peças', transferHelp: 'A quantidade sai desta box e entra no destino escolhido.',
    transferProduct: 'Produto', transferQuantity: 'Quantidade a transferir',
    transferMax: (count: number) => `Máximo: ${count} (saldo da box)`,
    transferTo: 'Destino', toBox: 'Outra box', toOrder: 'Orçamento existente', toNewOrder: 'Novo orçamento',
    destBox: 'Box de destino', destOrder: 'Orçamento em aberto', newOrderHelp: 'A peça vai para a aba Novo orçamento, com produto, opcionais e quantidade já preenchidos. O saldo só baixa do estoque quando você salvar o orçamento; se desistir, nada sai da box.', goNewOrder: 'Levar para Novo orçamento',
    chooseOne: 'Escolha...', noOtherBoxes: 'Não há outra box. Crie uma antes de transferir.',
    noOpenOrders: 'Nenhum orçamento em aberto. Orçamentos já realizados ou cancelados não aparecem.',
    doTransfer: 'Transferir', transferring: 'Transferindo...', transferError: 'Não foi possível transferir.',
    transferNeedsItems: 'Adicione produtos à box para transferir.',
    transferDone: (quantity: number, code: string, where: string) => `${quantity} x ${code} transferido(s) para ${where}.`,
    recentTransfers: 'Transferências recentes', noTransfers: 'Nenhuma transferência ainda.',
    orderWord: 'Orçamento',
  },
  'en-GB': {
    stock: 'Stock', stockLocation: 'Stock location', editLocation: 'Edit location',
    close: 'Close', locationName: 'Box name', priceList: 'Price list',
    priceHelp: 'The selected price list defines every value in this box.', cancel: 'Cancel',
    save: 'Save box', saving: 'Saving…', open: 'Open', products: 'Products',
    productConfigurations: 'product configurations', totalValue: 'Total value', pieces: 'pieces',
    loadingBoxes: 'Loading boxes', loadError: 'The stock could not be loaded.',
    retry: 'Try again', noBoxes: 'No boxes created',
    noBoxesHelp: 'Create a box for each stock location, fair or exhibition.',
    createFirst: 'Create first location', boxesLabel: 'Stock boxes', allBoxes: 'All boxes',
    deleteBox: 'Delete box', valuesBy: 'Values calculated using the', quantity: 'Quantity',
    productsHere: 'Products in this box', emptyBox: 'This box is still empty',
    emptyBoxHelp: 'Use search to add the first product.', product: 'Product',
    unit: 'Unit price', total: 'Total', actions: 'Actions', remove: 'Remove', perUnit: 'per unit',
    searchProducts: 'Search products', searchPlaceholder: 'Code or name', searching: 'Searching products…',
    searchError: 'Products could not be searched.', noProducts: 'No products found.',
    configure: 'Configure', configureProduct: 'Configure product', chooseFinishes: 'Choose finishes',
    optionalChoiceHelp: 'Each combination is stored as a separate line.',
    loadingProduct: 'Loading configuration…', productError: 'This product’s finishes could not be loaded.',
    noFinishes: 'This product has no configurable finishes.', required: 'Required',
    chooseOption: 'Choose an option', addToStock: 'Add to stock', adding: 'Adding…',
    added: 'Added', quantityOf: 'Quantity of', noOptionals: 'No finishes',
    saveError: 'The box could not be saved.', deleteError: 'The box could not be deleted.',
    addError: 'The product could not be added.', removeError: 'The product could not be removed.',
    confirmDelete: (name: string) => `Delete “${name}” and every product in it?`,
    confirmRemove: (code: string) => `Remove ${code} from this box?`,
    requiredPending: (count: number) => `${count} required finish(es) not chosen: the item will be saved as pending.`,
    updateError: 'The quantity could not be changed.',
    transfer: 'Transfer', transferTitle: 'Transfer pieces', transferHelp: 'The quantity leaves this box and enters the chosen destination.',
    transferProduct: 'Product', transferQuantity: 'Quantity to transfer',
    transferMax: (count: number) => `Maximum: ${count} (box balance)`,
    transferTo: 'Destination', toBox: 'Another box', toOrder: 'Existing quote', toNewOrder: 'New quote',
    destBox: 'Destination box', destOrder: 'Open quote', newOrderHelp: 'The piece goes to the New quote tab with product, finishes and quantity filled in. Stock is only deducted when you save the quote; if you give up, nothing leaves the box.', goNewOrder: 'Take to New quote',
    chooseOne: 'Choose...', noOtherBoxes: 'There is no other box. Create one before transferring.',
    noOpenOrders: 'No open quotes. Finalised or cancelled quotes are not listed.',
    doTransfer: 'Transfer', transferring: 'Transferring...', transferError: 'The transfer could not be completed.',
    transferNeedsItems: 'Add products to the box to transfer.',
    transferDone: (quantity: number, code: string, where: string) => `${quantity} x ${code} transferred to ${where}.`,
    recentTransfers: 'Recent transfers', noTransfers: 'No transfers yet.',
    orderWord: 'Quote',
  },
} as const

function priceLabel(code: ShowroomPriceList, english: boolean) {
  if (!english) return { lojista: 'Lojista', arquiteto: 'Arquiteto', corporativo: 'Corporativo', pvp: 'PVP' }[code]
  return { lojista: 'Retailer', arquiteto: 'Architect', corporativo: 'Corporate', pvp: 'RRP' }[code]
}

function money(value: number | string, locale: 'pt-PT' | 'en-GB') {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(Number(value))
}

function errorDetail(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: string | Array<{ msg?: string }> } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg).filter(Boolean).join(' ') || fallback
  return fallback
}

function QuantityField({ boxId, item, label, onError }: { boxId: string; item: ShowroomItem; label: string; onError: (message: string) => void }) {
  const { locale } = useLocale()
  const update = useUpdateShowroomItem()
  const [draft, setDraft] = useState<string | null>(null)
  const value = draft ?? String(item.quantity)

  function commit() {
    const quantity = Math.max(1, Math.floor(Number(value) || 1))
    setDraft(null)
    if (quantity !== item.quantity) update.mutate({ boxId, itemId: item.item_id, quantity }, { onError: error => onError(errorDetail(error, TEXT[locale].updateError)) })
  }

  return (
    <input
      aria-label={`${label} ${item.product_code}`}
      className="input h-10 w-20 text-center tabular-nums"
      type="number"
      min="1"
      max="1000000"
      inputMode="numeric"
      value={value}
      disabled={update.isPending}
      onChange={event => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}
    />
  )
}

function BoxDialog({ box, onClose }: { box?: ShowroomBox; onClose: () => void }) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const english = locale === 'en-GB'
  const create = useCreateShowroomBox()
  const update = useUpdateShowroomBox()
  const [name, setName] = useState(box?.name ?? '')
  const [priceList, setPriceList] = useState<ShowroomPriceList>(box?.price_list_code ?? 'lojista')
  const [error, setError] = useState<string | null>(null)
  const pending = create.isPending || update.isPending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      if (box) await update.mutateAsync({ id: box.id, name: name.trim(), price_list_code: priceList })
      else await create.mutateAsync({ name: name.trim(), price_list_code: priceList })
      onClose()
    } catch (requestError) {
      setError(errorDetail(requestError, tx.saveError))
    }
  }

  return (
    <div className="modal-overlay fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" role="presentation">
      <form className="modal-panel w-full max-w-md p-5" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="box-dialog-title">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="box-dialog-title" className="font-display text-2xl font-semibold text-ink">{box ? tx.editLocation : tx.stockLocation}</h2>
            <p className="mt-1 text-sm text-muted">{tx.priceHelp}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={tx.close} className="btn-icon -mr-2 -mt-2"><X className="h-5 w-5" /></button>
        </div>
        <div className="mt-5 space-y-4">
          <label className="flex flex-col gap-1.5">
            <span className="type-label">{tx.locationName}</span>
            <input autoFocus required maxLength={120} className="input" placeholder={english ? 'E.g. Portugal stock' : 'Ex.: Estoque Portugal'} value={name} onChange={event => setName(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="type-label">{tx.priceList}</span>
            <select className="input" value={priceList} onChange={event => setPriceList(event.target.value as ShowroomPriceList)}>
              {PRICE_OPTIONS.map(code => <option key={code} value={code}>{priceLabel(code, english)}</option>)}
            </select>
          </label>
          {error && <p role="alert" className="rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta">{error}</p>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>{tx.cancel}</button>
          <button type="submit" className="btn-primary" disabled={pending || !name.trim()}>{pending ? tx.saving : tx.save}</button>
        </div>
      </form>
    </div>
  )
}

function BoxCard({ box, onOpen }: { box: ShowroomBox; onOpen: () => void }) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const english = locale === 'en-GB'
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`${tx.open} ${box.name}`}
      className="group min-h-64 overflow-hidden rounded-2xl border border-line bg-white text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-gold/35 hover:shadow-lg hover:shadow-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/35"
    >
      <span className="flex h-full flex-col">
        <span className="flex items-start justify-between gap-4 p-5">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-surface-warm text-gold ring-1 ring-gold/10"><Warehouse className="h-5 w-5" /></span>
          <span className="rounded-full bg-gold/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-gold">{priceLabel(box.price_list_code, english)}</span>
        </span>
        <span className="flex-1 px-5">
          <strong className="block font-display text-2xl font-semibold leading-tight text-ink">{box.name}</strong>
          <span className="mt-2 block text-sm text-muted">{box.item_count} {tx.productConfigurations}</span>
        </span>
        <span className="mt-5 grid grid-cols-[1fr_auto] items-end gap-4 border-t border-line bg-surface-2/70 px-5 py-4">
          <span><span className="type-label block">{tx.totalValue}</span><span className="mt-1 block font-display text-2xl font-semibold tabular-nums text-ink">{money(box.total_value, locale)}</span></span>
          <span className="flex items-center gap-3">
            <span className="text-right"><span className="block text-xl font-semibold tabular-nums text-ink">{box.total_quantity}</span><span className="type-meta">{tx.pieces}</span></span>
            <span className="grid h-9 w-9 place-items-center rounded-full border border-line bg-white text-gold transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"><ArrowUpRight className="h-4 w-4" /></span>
          </span>
        </span>
      </span>
    </button>
  )
}

function choiceLabel(choice: ShowroomOptionalChoice, english: boolean) {
  const application = english && choice.application_name_en?.trim()
    ? choice.application_name_en
    : choice.application_name
  const label = application || optionalCategoryLabel(choice.category_name, english)
  return choice.component_name ? `${choice.component_name} — ${label}` : label
}

function ItemChoices({ choices, english, noOptionals }: { choices: ShowroomOptionalChoice[]; english: boolean; noOptionals: string }) {
  if (choices.length === 0) return <span className="type-meta">{noOptionals}</span>
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {choices.map(choice => (
        <span key={`${choice.application_id ?? choice.category_code}:${choice.optional_id ?? 'custom'}`} className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-ink-2">
          {choice.thumbnail_url && <img src={choice.thumbnail_url} alt="" className="h-4 w-4 rounded object-cover" />}
          <strong className="truncate font-semibold text-gold">{choiceLabel(choice, english)}</strong>
          <span className="truncate">{choice.custom ? customOptionLabel(english) : optionalName(choice.optional_name, english)}</span>
        </span>
      ))}
    </div>
  )
}

interface FinishSlot {
  key: string
  label: string
  required: boolean
  options: OptionalColor[]
  /** "Customizado" só nas aplicações; o seletor antigo por categoria não tem. */
  allowCustom: boolean
  choice: (optionalId: string) => ShowroomOptionalChoiceInput
}

function ProductConfigurationForm({
  product,
  candidate,
  boxId,
  onClose,
  onAdded,
}: {
  product: Product
  candidate: ShowroomProduct
  boxId: string
  onClose: () => void
  onAdded: () => void
}) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const english = locale === 'en-GB'
  const addItem = useAddShowroomItem()
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [quantity, setQuantity] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const applications = useMemo(() => productApplications(product), [product])
  const applicationCategories = useMemo(() => new Set(applications.map(({ application }) => application.category_code)), [applications])
  const directCategories = useMemo(() => Array.from(new Set(product.optionals.map(option => option.category))), [product.optionals])
  const freeCategories = useMemo(() => (product.all_optionals_categories ?? '').split(',').map(value => value.trim()).filter(Boolean), [product.all_optionals_categories])
  const legacyCategories = useMemo(() => Array.from(new Set([...directCategories, ...freeCategories])).filter(category => !applicationCategories.has(category)), [applicationCategories, directCategories, freeCategories])
  const fetchedCategories = useMemo(() => Array.from(new Set([
    ...applications.filter(({ application }) => application.allow_all).map(({ application }) => application.category_code),
    ...freeCategories,
  ])), [applications, freeCategories])
  const { data: fetchedOptionals = [] } = useOptionalsForCategories(fetchedCategories)
  const slots = useMemo<FinishSlot[]>(() => [
    ...applications.map(({ application, componentName }) => ({
      key: `application:${application.id}`,
      label: `${componentName ? `${componentName} — ` : ''}${applicationName(application, english)}`,
      required: application.required,
      options: allowedForApplication(application, fetchedOptionals),
      allowCustom: allowsCustomFor(allowedForApplication(application, fetchedOptionals)),
      choice: (optionalId: string) => optionalId === CUSTOM_OPTION
        ? { application_id: application.id, custom: true }
        : { application_id: application.id, optional_id: optionalId },
    })),
    ...legacyCategories.map(category => ({
      key: `category:${category}`,
      label: optionalCategoryLabel(category, english),
      required: false,
      options: freeCategories.includes(category)
        ? fetchedOptionals.filter(option => option.category === category)
        : product.optionals.filter(option => option.category === category),
      allowCustom: false,
      choice: (optionalId: string) => ({ category_code: category, optional_id: optionalId }),
    })),
  ], [applications, english, fetchedOptionals, freeCategories, legacyCategories, product.optionals])

  const pendingRequired = slots.filter(slot => slot.required && !selected[slot.key]).length

  async function submit() {
    const optionalChoices = slots.flatMap(slot => selected[slot.key] ? [slot.choice(selected[slot.key])] : [])
    setError(null)
    try {
      await addItem.mutateAsync({ boxId, productId: product.id, quantity, optionalChoices })
      onAdded()
      onClose()
    } catch (requestError) {
      setError(errorDetail(requestError, tx.addError))
    }
  }

  return (
    <div className="modal-panel flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="configure-product-title">
      <div className="flex items-start gap-3 border-b border-line p-5">
        <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">
          {candidate.thumbnail_url ? <img src={candidate.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="type-code">{candidate.product_code}</p>
          <h2 id="configure-product-title" className="font-display text-2xl font-semibold leading-tight text-ink">{candidate.description}</h2>
          <p className="mt-1 text-sm font-semibold tabular-nums text-gold">{money(candidate.unit_price, locale)}</p>
        </div>
        <button type="button" onClick={onClose} aria-label={tx.close} className="btn-icon -mr-2 -mt-2"><X className="h-5 w-5" /></button>
      </div>
      <div className="overflow-y-auto p-5">
        <div className="mb-5 flex items-end gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-xl font-semibold text-ink">{tx.chooseFinishes}</h3>
            <p className="mt-1 text-xs text-muted">{tx.optionalChoiceHelp}</p>
          </div>
          <label className="w-24 shrink-0"><span className="type-label block">{tx.quantity}</span><input className="input mt-1 w-full text-center" type="number" min="1" max="1000000" value={quantity} onChange={event => setQuantity(Math.max(1, Number(event.target.value) || 1))} /></label>
        </div>

        {slots.length === 0 ? (
          <p className="rounded-xl bg-surface-2 px-4 py-3 text-sm text-muted">{tx.noFinishes}</p>
        ) : (
          <div className="space-y-5">
            {slots.map(slot => (
              <fieldset key={slot.key}>
                <legend className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
                  {slot.label}
                  {slot.required && <span className="rounded bg-gold/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-gold">{tx.required}</span>}
                </legend>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {slot.options.map(option => {
                    const active = selected[slot.key] === option.id
                    return (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => { setSelected(current => ({ ...current, [slot.key]: current[slot.key] === option.id ? '' : option.id })); setError(null) }}
                        className={`flex min-h-12 items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/30 ${active ? 'border-gold bg-gold/10 text-ink' : 'border-line bg-white text-ink-2 hover:border-gold/35'}`}
                      >
                        <span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-lg bg-bg ring-1 ring-line">
                          {option.thumbnail_url ? <img src={option.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-3.5 w-3.5 text-muted-3" />}
                        </span>
                        <span className="min-w-0 flex-1 break-words font-medium leading-snug">{optionalName(option.color_name, english)}</span>
                        {active && <Check className="h-4 w-4 shrink-0 text-gold" />}
                      </button>
                    )
                  })}
                  {slot.allowCustom && (
                    <button
                      type="button"
                      aria-pressed={selected[slot.key] === CUSTOM_OPTION}
                      onClick={() => { setSelected(current => ({ ...current, [slot.key]: current[slot.key] === CUSTOM_OPTION ? '' : CUSTOM_OPTION })); setError(null) }}
                      className={`flex min-h-12 items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/30 ${selected[slot.key] === CUSTOM_OPTION ? 'border-gold bg-gold/10 text-ink' : 'border-line bg-white text-ink-2 hover:border-gold/35'}`}
                    >
                      <span className="min-w-0 flex-1 break-words font-medium leading-snug">{customOptionLabel(english)}</span>
                      {selected[slot.key] === CUSTOM_OPTION && <Check className="h-4 w-4 shrink-0 text-gold" />}
                    </button>
                  )}
                </div>
              </fieldset>
            ))}
          </div>
        )}
      </div>
      {/* Fora da área rolável: o erro do servidor precisa ficar à vista ao lado do botão. */}
      {pendingRequired > 0 && !error && <p className="border-t border-line bg-surface-2 px-5 pt-3 text-xs text-muted">{tx.requiredPending(pendingRequired)}</p>}
      {error && <p role="alert" className="mx-4 mt-3 rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta">{error}</p>}
      <div className="flex justify-end gap-2 border-t border-line bg-surface-2 p-4">
        <button type="button" className="btn-secondary" onClick={onClose}>{tx.cancel}</button>
        <button type="button" className="btn-primary" disabled={addItem.isPending} onClick={() => void submit()}>{addItem.isPending ? tx.adding : tx.addToStock}</button>
      </div>
    </div>
  )
}

function ProductConfigurationDialog({ candidate, boxId, onClose }: { candidate: ShowroomProduct; boxId: string; onClose: () => void }) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const productQuery = useProductsByCodes([candidate.product_code])
  const product = productQuery.data?.[0]
  return (
    <div className="modal-overlay fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" role="presentation">
      {product ? (
        <ProductConfigurationForm product={product} candidate={candidate} boxId={boxId} onClose={onClose} onAdded={() => undefined} />
      ) : (
        <div className="modal-panel w-full max-w-md p-6 text-center" role="dialog" aria-modal="true">
          <button type="button" onClick={onClose} aria-label={tx.close} className="btn-icon ml-auto"><X className="h-5 w-5" /></button>
          <p className={`mt-4 text-sm ${productQuery.isError ? 'text-terracotta' : 'text-muted'}`}>{productQuery.isError ? tx.productError : tx.loadingProduct}</p>
        </div>
      )}
    </div>
  )
}

function itemLabel(item: ShowroomItem, english: boolean) {
  const choices = (item.optional_choices ?? []).map(choice => `${choiceLabel(choice, english)}: ${choice.custom ? customOptionLabel(english) : optionalName(choice.optional_name, english)}`)
  return `${item.product_code} - ${item.description}${choices.length ? ` (${choices.join('; ')})` : ''} - ${item.quantity}`
}

type TransferMode = 'box' | 'order' | 'new_order'

function TransferDialog({ box, boxes, onClose, onDone }: { box: ShowroomBox; boxes: ShowroomBox[]; onClose: () => void; onDone: (message: string) => void }) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const english = locale === 'en-GB'
  const transfer = useTransferShowroomItem()
  const { user } = useAuth()
  const navigate = useNavigate()
  const otherBoxes = boxes.filter(candidate => candidate.id !== box.id)
  const [itemId, setItemId] = useState(box.items[0]?.item_id ?? '')
  const [quantityText, setQuantityText] = useState('1')
  const [mode, setMode] = useState<TransferMode>(otherBoxes.length > 0 ? 'box' : 'order')
  const [destinationBoxId, setDestinationBoxId] = useState('')
  const [orderId, setOrderId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const item = box.items.find(candidate => candidate.item_id === itemId)
  const quantity = Math.floor(Number(quantityText))
  const overBalance = Boolean(item) && quantity > (item?.quantity ?? 0)
  const validQuantity = Number.isInteger(quantity) && quantity >= 1 && !overBalance
  const ordersQuery = useOrders({ status: 'in_progress', limit: 100 })
  const openOrders = (ordersQuery.data?.items ?? []).filter(order => !order.is_cancelled && !order.is_finalized)
  const destinationReady = mode === 'box' ? Boolean(destinationBoxId) : mode === 'order' ? Boolean(orderId) : true

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!item || !validQuantity || !destinationReady) return
    setError(null)
    if (mode === 'new_order') {
      // Não cria orçamento nem tira nada da box: leva a peça para a aba Novo orçamento.
      if (!user) return
      addShowroomItemToCart(user.id, item, quantity, box.name)
      onClose()
      navigate('/orcamentos')
      return
    }
    const destination = mode === 'box'
      ? { type: 'box' as const, box_id: destinationBoxId }
      : { type: 'order' as const, order_id: orderId }
    try {
      const result = await transfer.mutateAsync({ boxId: box.id, itemId: item.item_id, quantity, destination })
      const done = result.transfer
      const where = done.destination_type === 'box'
        ? (done.destination_box_name ?? '')
        : `${tx.orderWord.toLowerCase()} ${done.destination_order_code ?? ''}`.trim()
      onDone(tx.transferDone(done.quantity, done.product_code, where))
      onClose()
    } catch (requestError) {
      setError(errorDetail(requestError, tx.transferError))
    }
  }

  const modes: Array<[TransferMode, string]> = [['box', tx.toBox], ['order', tx.toOrder], ['new_order', tx.toNewOrder]]
  return (
    <div className="modal-overlay fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" role="presentation">
      <form className="modal-panel flex max-h-[calc(100vh-2rem)] w-full max-w-lg flex-col overflow-hidden" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="transfer-dialog-title">
        <div className="flex items-start justify-between gap-4 border-b border-line p-5">
          <div>
            <h2 id="transfer-dialog-title" className="font-display text-2xl font-semibold text-ink">{tx.transferTitle}</h2>
            <p className="mt-1 text-sm text-muted">{tx.transferHelp}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={tx.close} className="btn-icon -mr-2 -mt-2"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 overflow-y-auto p-5">
          <label className="flex flex-col gap-1.5">
            <span className="type-label">{tx.transferProduct}</span>
            <select className="input" aria-label={tx.transferProduct} value={itemId} onChange={event => { setItemId(event.target.value); setQuantityText('1') }}>
              {box.items.map(candidate => <option key={candidate.item_id} value={candidate.item_id}>{itemLabel(candidate, english)}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="type-label">{tx.transferQuantity}</span>
            <input className="input w-32 text-center tabular-nums" aria-label={tx.transferQuantity} type="number" min="1" max={item?.quantity ?? 1} inputMode="numeric" value={quantityText} onChange={event => setQuantityText(event.target.value)} />
            <span className={`text-xs ${overBalance ? 'text-terracotta' : 'text-muted'}`}>{tx.transferMax(item?.quantity ?? 0)}</span>
          </label>
          <fieldset>
            <legend className="type-label mb-2">{tx.transferTo}</legend>
            <div className="grid grid-cols-3 gap-2">
              {modes.map(([value, label]) => (
                <button key={value} type="button" aria-pressed={mode === value} onClick={() => { setMode(value); setError(null) }}
                  className={`min-h-11 rounded-xl border px-2 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/30 ${mode === value ? 'border-gold bg-gold/10 text-ink' : 'border-line bg-white text-ink-2 hover:border-gold/35'}`}>{label}</button>
              ))}
            </div>
          </fieldset>
          {mode === 'box' && (otherBoxes.length === 0
            ? <p className="rounded-xl bg-surface-2 px-4 py-3 text-sm text-muted">{tx.noOtherBoxes}</p>
            : <label className="flex flex-col gap-1.5"><span className="type-label">{tx.destBox}</span>
              <select className="input" aria-label={tx.destBox} value={destinationBoxId} onChange={event => setDestinationBoxId(event.target.value)}>
                <option value="">{tx.chooseOne}</option>
                {otherBoxes.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
              </select></label>)}
          {mode === 'order' && (
            <label className="flex flex-col gap-1.5"><span className="type-label">{tx.destOrder}</span>
              <select className="input" aria-label={tx.destOrder} value={orderId} onChange={event => setOrderId(event.target.value)}>
                <option value="">{tx.chooseOne}</option>
                {openOrders.map(order => <option key={order.id} value={order.id}>{`${order.code} - ${order.client_name}`}</option>)}
              </select>
              {!ordersQuery.isLoading && openOrders.length === 0 && <span className="text-xs text-muted">{tx.noOpenOrders}</span>}
            </label>
          )}
          {mode === 'new_order' && <p className="rounded-xl bg-surface-2 px-4 py-3 text-sm text-ink-2">{tx.newOrderHelp}</p>}
        </div>
        {error && <p role="alert" className="mx-4 mt-3 rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-line bg-surface-2 p-4">
          <button type="button" className="btn-secondary" onClick={onClose}>{tx.cancel}</button>
          <button type="submit" className="btn-primary" disabled={transfer.isPending || !item || !validQuantity || !destinationReady}>{transfer.isPending ? tx.transferring : mode === 'new_order' ? tx.goNewOrder : tx.doTransfer}</button>
        </div>
      </form>
    </div>
  )
}

function TransferHistory({ boxId }: { boxId: string }) {
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const query = useShowroomTransfers(boxId)
  const rows: ShowroomTransfer[] = (query.data ?? []).slice(0, 10)
  function destination(row: ShowroomTransfer) {
    return row.destination_type === 'box' ? (row.destination_box_name ?? '') : `${tx.orderWord} ${row.destination_order_code ?? ''}`.trim()
  }
  return (
    <section className="mt-5 overflow-hidden rounded-2xl border border-line bg-white shadow-sm" aria-labelledby="box-transfers-title">
      <div className="border-b border-line px-5 py-4 sm:px-6"><h3 id="box-transfers-title" className="font-display text-xl font-semibold text-ink">{tx.recentTransfers}</h3></div>
      {rows.length === 0 ? <p className="px-5 py-6 text-sm text-muted sm:px-6">{tx.noTransfers}</p> : (
        <ul className="divide-y divide-line">
          {rows.map(row => (
            <li key={row.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 py-3 text-sm sm:px-6">
              <span className="font-medium text-ink"><span className="type-code">{row.product_code}</span> x {row.quantity}</span>
              <span className="text-ink-2">{row.source_box_name} {'->'} {destination(row)}</span>
              <span className="type-meta">{new Date(row.created_at).toLocaleString(locale)} - {row.created_by_name}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export default function ShowroomsPage() {
  const { user } = useAuth()
  const { locale } = useLocale()
  const tx = TEXT[locale]
  const english = locale === 'en-GB'
  const boxesQuery = useShowroomBoxes()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [candidate, setCandidate] = useState<ShowroomProduct | null>(null)
  const [dialog, setDialog] = useState<'create' | 'edit' | 'transfer' | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const removeItem = useRemoveShowroomItem()
  const removeBox = useDeleteShowroomBox()
  const boxes = boxesQuery.data ?? []
  const selected = selectedId ? boxes.find(box => box.id === selectedId) : undefined
  const productsQuery = useShowroomProducts(selected?.price_list_code, search)

  if (!user?.can_manage_showrooms || user.active_market !== 'EU') return null

  function openBox(id: string) {
    setSearch('')
    setMessage(null)
    setNotice(null)
    setSelectedId(id)
  }

  function closeBox() {
    setSearch('')
    setMessage(null)
    setSelectedId(null)
  }

  async function confirmDeleteBox() {
    if (!selected || !window.confirm(tx.confirmDelete(selected.name))) return
    setMessage(null)
    try {
      await removeBox.mutateAsync(selected.id)
      setSelectedId(null)
    } catch (error) {
      setMessage(errorDetail(error, tx.deleteError))
    }
  }

  async function removeProduct(item: ShowroomItem) {
    if (!selected || !window.confirm(tx.confirmRemove(item.product_code))) return
    setMessage(null)
    try {
      await removeItem.mutateAsync({ boxId: selected.id, itemId: item.item_id })
    } catch (error) {
      setMessage(errorDetail(error, tx.removeError))
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 pb-28 md:px-6 md:py-7 md:pb-10 lg:px-8">
      <h1 className="sr-only">{tx.stock}</h1>
      {notice && <p role="status" className="mb-4 rounded-xl border border-gold/30 bg-white px-4 py-3 text-sm text-ink shadow-sm">{notice}</p>}
      {message && <p role="alert" className="mb-4 rounded-xl border border-terracotta/20 bg-white px-4 py-3 text-sm text-terracotta shadow-sm">{message}</p>}

      {boxesQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label={tx.loadingBoxes}>{[0, 1, 2].map(item => <div key={item} className="h-64 animate-pulse rounded-2xl border border-line bg-white shadow-sm" />)}</div>
      ) : boxesQuery.isError ? (
        <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-line bg-white p-8 text-center shadow-sm"><p className="text-sm text-terracotta">{tx.loadError}</p><button className="btn-secondary mt-4" onClick={() => boxesQuery.refetch()}>{tx.retry}</button></div>
      ) : boxes.length === 0 ? (
        <div className="flex min-h-80 flex-col items-center justify-center rounded-2xl border border-line bg-white p-8 text-center shadow-sm">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-warm text-gold"><Boxes className="h-6 w-6" /></span>
          <h2 className="mt-5 font-display text-2xl font-semibold text-ink">{tx.noBoxes}</h2><p className="mt-2 max-w-md text-sm leading-relaxed text-muted">{tx.noBoxesHelp}</p>
          <button className="btn-primary mt-6 inline-flex items-center gap-2" onClick={() => setDialog('create')}><Plus className="h-4 w-4" /> {tx.createFirst}</button>
        </div>
      ) : !selected ? (
        <><div className="mb-5 flex justify-end"><button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setDialog('create')}><Plus className="h-4 w-4" /> {tx.stockLocation}</button></div><section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label={tx.boxesLabel}>{boxes.map(box => <BoxCard key={box.id} box={box} onOpen={() => openBox(box.id)} />)}</section></>
      ) : (
        <div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <button type="button" onClick={closeBox} className="btn-secondary inline-flex items-center gap-2"><ArrowLeft className="h-4 w-4" /> {tx.allBoxes}</button>
            <div className="flex items-center gap-2"><button type="button" className="btn-secondary inline-flex items-center gap-2 disabled:opacity-50" onClick={() => setDialog('transfer')} disabled={selected.items.length === 0} title={selected.items.length === 0 ? tx.transferNeedsItems : undefined}><ArrowRightLeft className="h-4 w-4" /> {tx.transfer}</button><button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => setDialog('edit')}><Edit3 className="h-4 w-4" /> {tx.editLocation}</button><button type="button" className="grid min-h-11 min-w-11 place-items-center rounded-lg border border-line bg-white text-muted shadow-sm transition-colors hover:border-terracotta/30 hover:bg-terracotta/10 hover:text-terracotta focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta/30" onClick={() => void confirmDeleteBox()} aria-label={tx.deleteBox}><Trash2 className="h-4 w-4" /></button></div>
          </div>

          <section className="overflow-hidden rounded-2xl border border-line bg-white shadow-sm" aria-labelledby="selected-box-title">
            <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-5 sm:px-6"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2.5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-warm text-gold"><Warehouse className="h-5 w-5" /></span><h2 id="selected-box-title" className="font-display text-3xl font-semibold leading-tight text-ink sm:text-4xl">{selected.name}</h2></div><p className="mt-2 text-sm text-muted">{tx.valuesBy} {priceLabel(selected.price_list_code, english)}.</p></div><span className="rounded-full bg-gold/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-gold">{priceLabel(selected.price_list_code, english)}</span></div>
            <div className="grid grid-cols-2 border-t border-line bg-surface-2/70 sm:grid-cols-[1fr_1fr_1.5fr]"><div className="px-5 py-4 sm:px-6"><span className="type-label block">{tx.products}</span><strong className="mt-1 block text-2xl font-semibold tabular-nums text-ink">{selected.item_count}</strong></div><div className="border-l border-line px-5 py-4 sm:px-6"><span className="type-label block">{tx.quantity}</span><strong className="mt-1 block text-2xl font-semibold tabular-nums text-ink">{selected.total_quantity}</strong></div><div className="col-span-2 border-t border-line px-5 py-4 sm:col-span-1 sm:border-l sm:border-t-0 sm:px-6 sm:text-right"><span className="type-label block">{tx.totalValue}</span><strong className="mt-1 block font-display text-3xl font-semibold tabular-nums text-gold">{money(selected.total_value, locale)}</strong></div></div>
          </section>

          <div className="relative z-10 mt-5">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-3" />
            <input className="input h-12 w-full pl-10 shadow-sm" type="search" aria-label={tx.searchProducts} placeholder={tx.searchPlaceholder} value={search} onChange={event => setSearch(event.target.value)} />
            {search.trim() && (
              <div className="absolute left-0 right-0 top-full mt-2 max-h-80 overflow-y-auto rounded-xl border border-line bg-white shadow-xl">
                {productsQuery.isLoading ? <p className="p-5 text-center text-sm text-muted">{tx.searching}</p> : productsQuery.isError ? <p className="p-5 text-center text-sm text-terracotta">{tx.searchError}</p> : productsQuery.data?.length === 0 ? <p className="p-5 text-center text-sm text-muted">{tx.noProducts}</p> : productsQuery.data?.map(product => (
                  <button key={product.id} type="button" aria-label={`${tx.configure} ${product.product_code}`} onClick={() => { setCandidate(product); setSearch('') }} className="flex w-full items-center gap-3 border-b border-line p-3 text-left transition-colors last:border-0 hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-gold/30">
                    <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-lg bg-bg ring-1 ring-line">{product.thumbnail_url ? <img src={product.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-4 w-4 text-muted-3" />}</span>
                    <span className="min-w-0 flex-1"><span className="type-code block">{product.product_code}</span><span className="block truncate text-sm font-medium text-ink">{product.description}</span></span>
                    <span className="shrink-0 text-sm font-semibold tabular-nums text-gold">{money(product.unit_price, locale)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <section className="mt-5 overflow-hidden rounded-2xl border border-line bg-white shadow-sm" aria-labelledby="box-products-title">
            <div className="border-b border-line px-5 py-4 sm:px-6"><h3 id="box-products-title" className="font-display text-xl font-semibold text-ink">{tx.productsHere}</h3></div>
            {selected.items.length === 0 ? (
              <div className="flex min-h-64 flex-col items-center justify-center px-5 py-12 text-center"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-muted-3"><PackagePlus className="h-5 w-5" /></span><p className="mt-4 text-sm font-semibold text-ink">{tx.emptyBox}</p><p className="mt-1 max-w-xs text-xs leading-relaxed text-muted">{tx.emptyBoxHelp}</p></div>
            ) : (
              <><div className="hidden overflow-x-auto md:block"><table className="w-full text-sm"><thead className="bg-surface-2 text-xs uppercase tracking-wider text-muted"><tr><th className="px-5 py-3 text-left sm:px-6">{tx.product}</th><th className="px-4 py-3 text-center">{tx.quantity}</th><th className="px-4 py-3 text-right">{tx.unit}</th><th className="px-4 py-3 text-right">{tx.total}</th><th className="w-14 px-3 py-3"><span className="sr-only">{tx.actions}</span></th></tr></thead><tbody className="divide-y divide-line">{selected.items.map(item => <tr key={item.item_id} className="align-top transition-colors hover:bg-surface-2/60"><td className="px-5 py-3.5 sm:px-6"><div className="flex items-start gap-3"><div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0"><span className="type-code">{item.product_code}</span><p className="max-w-sm truncate font-medium text-ink">{item.description}</p><ItemChoices choices={item.optional_choices ?? []} english={english} noOptionals={tx.noOptionals} /></div></div></td><td className="px-4 py-3.5 text-center"><QuantityField boxId={selected.id} item={item} label={tx.quantityOf} onError={setMessage} /></td><td className="px-4 py-3.5 text-right tabular-nums text-ink-2">{money(item.unit_price, locale)}</td><td className="px-4 py-3.5 text-right font-semibold tabular-nums text-ink">{money(item.line_total, locale)}</td><td className="px-3 py-3.5"><button className="grid min-h-11 min-w-11 place-items-center rounded-lg text-muted transition-colors hover:bg-terracotta/10 hover:text-terracotta" aria-label={`${tx.remove} ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>
              <div className="divide-y divide-line md:hidden">{selected.items.map(item => <article key={item.item_id} className="p-4"><div className="flex gap-3"><div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0 flex-1"><p className="type-code">{item.product_code}</p><p className="line-clamp-2 text-sm font-medium text-ink">{item.description}</p><ItemChoices choices={item.optional_choices ?? []} english={english} noOptionals={tx.noOptionals} /></div><button className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:text-terracotta" aria-label={`${tx.remove} ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></div><div className="mt-4 grid grid-cols-[auto_1fr] items-end gap-4 border-t border-line pt-3"><QuantityField boxId={selected.id} item={item} label={tx.quantityOf} onError={setMessage} /><div className="text-right"><p className="type-meta">{money(item.unit_price, locale)} {tx.perUnit}</p><p className="mt-0.5 font-semibold tabular-nums text-ink">{money(item.line_total, locale)}</p></div></div></article>)}</div></>
            )}
          </section>
          <TransferHistory boxId={selected.id} />
        </div>
      )}

      {dialog === 'transfer' && selected && <TransferDialog box={selected} boxes={boxes} onClose={() => setDialog(null)} onDone={setNotice} />}
      {dialog === 'create' && <BoxDialog onClose={() => setDialog(null)} />}
      {dialog === 'edit' && selected && <BoxDialog box={selected} onClose={() => setDialog(null)} />}
      {candidate && selected && <ProductConfigurationDialog candidate={candidate} boxId={selected.id} onClose={() => setCandidate(null)} />}
    </div>
  )
}
