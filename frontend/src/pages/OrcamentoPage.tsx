import { useState, useRef, useEffect, useId } from 'react'
import { Link, useSearchParams } from 'react-router'
import api from '../lib/api'
import { Search, Plus, X, Trash2, ShoppingCart, CheckCircle, ImageIcon, Clipboard, Minus, ChevronUp, Lock, PenLine, CircleAlert, MessageSquare } from 'lucide-react'
import { useProductsByCodes, useProductsPage } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useClient, useClientsPage, useCreateClient } from '../hooks/useClients'
import { useRepresentative, useRepresentativesPage, useCreateRepresentative } from '../hooks/useRepresentatives'
import { useCreateOrder, useUpdateOrder, useOrder } from '../hooks/useOrders'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { useOptionalCategories } from '../hooks/useOptionalCategories'
import { SafePrice } from '../components/SafePrice'
import { NumberField } from '../components/NumberField'
import { BrandLoadingOverlay } from '../components/BrandLoadingOverlay'
import { OptionalCombobox } from '../components/OptionalCombobox'
import { OptionalSwatchImage } from '../components/OptionalSwatchImage'
import { QuantityInput } from '../components/QuantityInput'
import { useAuth } from '../hooks/useAuth'
import { useLocale } from '../hooks/useLocale'
import { isConjuntoType } from '../lib/productType'
import {
  cartStorageKey,
  notifyCartChanged,
  readCartPriceList,
  removeCartPriceList,
  writeCartPriceList,
  type PriceListCode,
} from '../lib/cart'
import { allowedForApplication, allowsCustomFor, allowsCustomOption, applicationName, CUSTOM_LEGACY_VALUE, CUSTOM_OPTION, customOptionLabel, formatChoice, isCustomChoice, isLegacyCustom, productApplications, requiredApplicationProgress, validateApplicationChoices } from '../lib/optionalApplications'
import { formatBrazilianPhone, PHONE_INPUT_MAX_LENGTH } from '../lib/phone'
import { normalizePersonPayload, parseApiError } from '../lib/personForm'
import type { Product, Client, Representative, ClientCreate, OptionalColor, OptionalChoice, OptionalChoiceInput } from '../types'
import { formatDimensions } from '../lib/measurements'
import { areaLimit, formatArea, isAreaProduct, normalizeAreaQty, normalizeRugPieces, previewArea } from '../lib/areaProduct'
import { hasOptionalPhoto, optionalMedia } from '../lib/optionalMedia'
import { optionalName, optionalCategoryLabel } from '../lib/optionalLabels'
import { optionalMatchesLegacyName } from '../lib/optionalGroups'
import { orderMaxDiscount } from '../lib/discountRules'

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

// Acabamentos de um componente de conjunto: "Alumínio: Taupe · Teka: Polywood"
function compFinishes(
  optionals: { category: string; color_name: string }[],
  catLabel: (code: string) => string,
  english = false,
): string {
  const cats = Array.from(new Set(optionals.map(o => o.category)))
  return cats
    .map(cat => `${catLabel(cat)}: ${optionalName(optionals.find(o => o.category === cat)!.color_name, english)}`)
    .join(' · ')
}

function dimLabel(p: Product, market: 'BR' | 'EU', locale: 'pt-BR' | 'pt-PT' | 'en-GB') {
  // Conjunto é o agrupador comercial; as medidas pertencem exclusivamente aos
  // componentes internos e não devem aparecer como 0 × 0 × 0 no item-pai.
  if (isAreaProduct(p) || p.is_set || isConjuntoType(p.type) || p.components.length > 0) return null
  return formatDimensions(p, market, locale)
}

// ── Autocomplete ──────────────────────────────────────────────────────────────

function Autocomplete<T extends { id: string }>({
  searchPlaceholder, items, value, query, getLabel, getSearch, onChange, onClear, displayPlaceholder, showQuickAdd, onQuickAdd, onQueryChange, isLoading = false
}: {
  searchPlaceholder: string; items: T[]; value: T | null; query: string
  getLabel: (item: T) => string; getSearch: (item: T) => string
  onChange: (item: T) => void; onClear: () => void; displayPlaceholder?: string
  showQuickAdd?: boolean; onQuickAdd?: () => void
  onQueryChange: (query: string) => void; isLoading?: boolean
}) {
  const isEnglish = useLocale().locale === 'en-GB'
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const ref = useRef<HTMLDivElement>(null)
  const listboxId = useId()

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = items.filter((i) => getSearch(i).toLowerCase().includes(query.toLowerCase()))
  const visibleItems = filtered.slice(0, 15)

  function choose(item: T) {
    onChange(item)
    onQueryChange('')
    setOpen(false)
    setActiveIndex(-1)
  }

  return (
    <div ref={ref} className="space-y-1 w-full">
      <div className="flex gap-2">
        <div className="input flex items-center justify-between bg-surface-quiet border border-line px-3 py-1.5 rounded-lg text-sm flex-1 min-w-0 min-h-11">
          <span className={`${value ? 'text-ink font-medium' : 'text-muted-3'} truncate flex-1 min-w-0`}>
            {value ? getLabel(value) : (displayPlaceholder ?? (isEnglish ? 'None' : 'Nenhum'))}
          </span>
          {value && (
            <button
              type="button"
              onClick={() => {
                onClear()
                onQueryChange('')
                setOpen(false)
              }}
              className="text-muted hover:text-ink transition-colors w-11 h-11 flex items-center justify-center"
              aria-label={isEnglish ? 'Clear selection' : 'Limpar seleção'}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        {showQuickAdd && onQuickAdd && (
          <button type="button" onClick={onQuickAdd} className="btn-secondary px-2.5 flex-shrink-0 min-h-11 border border-line hover:bg-bg rounded-lg transition-colors flex items-center justify-center min-w-11" aria-label={isEnglish ? 'Add new' : 'Cadastrar novo'}>
            <Plus className="w-4 h-4 text-muted" />
          </button>
        )}
      </div>
      <div className="relative">
        <input
          className="input w-full text-sm sm:text-xs placeholder:text-muted border border-line rounded-lg px-3 py-2.5 sm:py-1.5 focus:outline-none focus:ring-1 focus:ring-gold bg-white"
          placeholder={searchPlaceholder}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
          value={query}
          onChange={(e) => {
            onQueryChange(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault()
              setOpen(true)
              setActiveIndex(current => Math.min(visibleItems.length - 1, current + 1))
            } else if (event.key === 'ArrowUp') {
              event.preventDefault()
              setActiveIndex(current => Math.max(0, current - 1))
            } else if (event.key === 'Enter' && open && activeIndex >= 0 && visibleItems[activeIndex]) {
              event.preventDefault()
              choose(visibleItems[activeIndex])
            } else if (event.key === 'Escape') {
              setOpen(false)
              setActiveIndex(-1)
            }
          }}
        />
        {open && (isLoading || filtered.length > 0 || query.length > 0) && (
          <ul id={listboxId} role="listbox" className="absolute z-30 w-full mt-1 bg-white border border-line rounded-xl overflow-hidden shadow-xl max-h-48 overflow-y-auto">
            {isLoading && (
              <li className="px-3 py-2 text-xs text-muted">{isEnglish ? 'Searching…' : 'Buscando…'}</li>
            )}
            {visibleItems.map((item, index) => (
              <li key={item.id} id={`${listboxId}-option-${index}`} role="option" aria-selected={activeIndex === index}
                className={`px-3 py-2.5 text-xs text-ink cursor-pointer transition-colors ${activeIndex === index ? 'bg-bg' : 'hover:bg-bg'}`}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseDown={() => choose(item)}>
                {getLabel(item)}
              </li>
            ))}
            {!isLoading && filtered.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted">{isEnglish ? 'No results.' : 'Nenhum resultado.'}</li>
            )}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Modal de cadastro rápido ──────────────────────────────────────────────────

const emptyPerson = (market: 'BR' | 'EU'): ClientCreate => ({
  name: '', phone: '', email: '', cpf_cnpj: '', tax_id: '',
  country: market === 'BR' ? 'BR' : 'PT', region: '',
  cep: '', numero: '', address: '', city: '', state: market === 'BR' ? '' : '--',
})

// Máscara alterna em 11 dígitos; o backend guarda só os dígitos.
function formatCpfCnpj(value: string): string {
  const d = value.replace(/\D/g, '').slice(0, 14)
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, '$1.$2')
      .replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2')
  }
  return d
    .replace(/^(\d{2})(\d)/, '$1.$2')
    .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/\.(\d{3})(\d)/, '.$1/$2')
    .replace(/(\d{4})(\d{1,2})$/, '$1-$2')
}

function QuickRegisterModal({ title, entityType, market, onSave, onClose }: {
  title: string; entityType: 'client' | 'rep'; market: 'BR' | 'EU'; onSave: (data: ClientCreate) => Promise<void>; onClose: () => void
}) {
  const isEnglish = useLocale().locale === 'en-GB'
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })
  const [form, setForm] = useState<ClientCreate>(() => emptyPerson(market))
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [cepLoading, setCepLoading] = useState(false)
  const [cepError, setCepError] = useState(false)
  const cepAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => cepAbortRef.current?.abort(), [])

  useEffect(() => {
    const returnFocus = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    const focusable = panel?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
    focusable?.[0]?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
      if (event.key !== 'Tab' || !focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => { document.removeEventListener('keydown', handleKeyDown); returnFocus?.focus() }
  }, [])

  async function handleCepBlur() {
    const clean = form.cep.replace(/\D/g, '')
    // Brasil: CEP de 8 dígitos (ViaCEP). Portugal: código postal 0000-000
    // (GeoAPI.pt pelo backend) — antes o cadastro rápido EU não consultava nada.
    if (clean.length !== (market === 'BR' ? 8 : 7)) return
    cepAbortRef.current?.abort()
    const controller = new AbortController()
    cepAbortRef.current = controller
    setCepLoading(true); setCepError(false)
    try {
      const path = market === 'BR' ? `/utils/cep/${clean}` : `/utils/postal-code/${clean}`
      const { data } = await api.get(path, { signal: controller.signal })
      setForm((f) => ({
        ...f,
        address: data.logradouro
          ? `${data.logradouro}${data.bairro ? ', ' + data.bairro : ''}`
          : f.address,
        city: data.localidade || f.city,
        state: market === 'BR' ? data.uf : '--',
        region: market === 'EU' ? (data.regiao || f.region) : f.region,
      }))
    } catch {
      // Requisição abortada (unmount / novo CEP) não é erro real (V-F2/M4).
      if (!controller.signal.aborted) setCepError(true)
    } finally {
      if (!controller.signal.aborted) setCepLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaveError(null)
    setSaving(true)
    try {
      await onSave(normalizePersonPayload(form))
      onClose()
    } catch (err) {
      // Sem este catch a recusa da API sumia no `finally` e o modal ficava
      // aberto sem explicação — parecia que o botão não fazia nada.
      setSaveError(parseApiError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="quick-register-title">
      <div ref={panelRef} className="modal-panel w-full max-w-lg p-4 sm:p-6 mx-4 max-h-[calc(100dvh-2rem)] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 id="quick-register-title" className="text-lg font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-ink w-11 h-11 flex items-center justify-center" aria-label={isEnglish ? 'Close' : 'Fechar'}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="sm:col-span-2 flex flex-col gap-1">
            <span className="text-xs text-muted">{isEnglish ? 'Name *' : 'Nome *'}</span>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{isEnglish ? 'Phone *' : 'Telefone *'}</span>
            <input className="input" value={form.phone} maxLength={market === 'BR' ? PHONE_INPUT_MAX_LENGTH : 20} onChange={(e) => setForm({ ...form, phone: market === 'BR' ? formatBrazilianPhone(e.target.value) : e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{isEnglish ? 'Email' : 'E-mail'}</span>
            <input className="input" type="email" value={form.email ?? ''} onChange={(e) => setForm({ ...form, email: e.target.value || null })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{market === 'EU' ? 'VAT / Tax ID' : 'CPF/CNPJ'}</span>
            <input className="input" value={market === 'EU' ? (form.tax_id ?? '') : (form.cpf_cnpj ?? '')} onChange={(e) => market === 'EU' ? setForm({ ...form, tax_id: e.target.value }) : setForm({ ...form, cpf_cnpj: formatCpfCnpj(e.target.value) })} maxLength={market === 'EU' ? 40 : 18} />
          </label>
          <label className="flex flex-col gap-1 relative">
            <span className="text-xs text-muted">{market === 'EU' ? (isEnglish ? 'Postcode *' : 'Código postal *') : 'CEP *'}</span>
            <input
              className="input"
              value={form.cep}
              inputMode="numeric"
              placeholder={market === 'EU' ? '0000-000' : '00000-000'}
              onChange={(e) => {
                const digits = e.target.value.replace(/\D/g, '').slice(0, market === 'BR' ? 8 : 7)
                const split = market === 'BR' ? 5 : 4
                setForm({ ...form, cep: digits.length > split ? `${digits.slice(0, split)}-${digits.slice(split)}` : digits })
              }}
              onBlur={handleCepBlur}
              maxLength={market === 'BR' ? 9 : 8}
              required
            />
            {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-gold animate-pulse">...</span>}
            {cepError && <span className="text-xs leading-snug font-medium text-danger">{isEnglish ? 'Postcode not found or service unavailable.' : market === 'EU' ? 'Código postal não encontrado ou serviço indisponível.' : 'CEP não encontrado ou serviço indisponível.'}</span>}
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{isEnglish ? 'Number' : 'Número'}</span>
            <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: e.target.value })} />
          </label>
          <label className="sm:col-span-2 flex flex-col gap-1">
            <span className="text-xs text-muted">{isEnglish ? 'Address *' : 'Endereço *'}</span>
            <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{market === 'EU' ? (isEnglish ? 'Town/City *' : 'Localidade *') : 'Cidade *'}</span>
            <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required />
          </label>
          {market === 'BR' ? <label className="flex flex-col gap-1"><span className="text-xs text-muted">UF *</span><input className="input" maxLength={2} value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value.toUpperCase() })} required /></label> : <><label className="flex flex-col gap-1"><span className="text-xs text-muted">{isEnglish ? 'Launch country' : 'País da primeira liberação'}</span><input className="input" value="PT" readOnly aria-readonly="true" /></label><label className="sm:col-span-2 flex flex-col gap-1"><span className="text-xs text-muted">{isEnglish ? 'Region' : 'Região'}</span><input className="input" value={form.region ?? ''} onChange={(e) => setForm({ ...form, region: e.target.value })} /></label></>}
          {entityType === 'client' && (
            <div className="sm:col-span-2 flex flex-col gap-1.5">
              <span className="text-xs text-muted">{isEnglish ? 'Billing profile *' : 'Perfil de faturamento *'}</span>
              <div className="flex gap-2">
                {(market === 'EU' ? ['lojista', 'corporativo', 'pvp', 'arquiteto'] as const : ['lojista', 'corporativo'] as const).map((profile) => (
                  <button
                    key={profile}
                    type="button"
                    onClick={() => setForm({ ...form, price_profile: profile })}
                    className={`flex-1 min-h-11 lg:min-h-0 py-2 rounded-lg border text-sm font-medium capitalize transition-colors ${
                      (form.price_profile ?? 'lojista') === profile
                        ? 'bg-gold text-white border-gold'
                        : 'border-line text-ink-3 hover:border-faint'
                    }`}
                  >
                    {profile}
                  </button>
                ))}
              </div>
            </div>
          )}
          {saveError && (
            <p role="alert" className="sm:col-span-2 text-sm font-medium text-danger bg-danger-soft border border-danger/25 rounded-lg px-3 py-2">
              {saveError}
            </p>
          )}
          <div className="sm:col-span-2 flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-1">
            <button type="button" className="btn-secondary" onClick={onClose}>{isEnglish ? 'Cancel' : 'Cancelar'}</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? (isEnglish ? 'Saving...' : 'Salvando...') : (isEnglish ? 'Save' : 'Salvar')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Carrinho ──────────────────────────────────────────────────────────────────

interface CartItem {
  line_id: string
  product_code: string
  qty: number
  sold_by_area?: boolean
  area_width_m?: number | null
  area_depth_m?: number | null
  area_pieces?: number
  discount: number
  opt_categories: Partial<Record<string, string>>
  optional_choices: OptionalChoiceInput[]
  source_order_item_id?: string
  preserve_optional_choices?: boolean
  saved_choices?: OptionalChoice[]
  /** Comentário do item; undefined com a caixa fechada. */
  comment?: string
  _product: Product
}

type PersistedCartItem = Omit<CartItem, '_product'>
const EMPTY_PRODUCTS: Product[] = []

function readPersistedCart(userId?: string, market: 'BR' | 'EU' = 'BR'): PersistedCartItem[] {
  if (!userId) return []
  try {
    const raw = localStorage.getItem(cartStorageKey(userId, market))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is PersistedCartItem =>
      !!item
      && typeof item.product_code === 'string'
      && Number.isFinite(Number(item.qty))
      && typeof item.opt_categories === 'object'
    ).map(item => ({ ...item, line_id: item.line_id || crypto.randomUUID(), optional_choices: Array.isArray(item.optional_choices) ? item.optional_choices : [] }))
  } catch {
    return []
  }
}

function initialLegacyOptionCategories(product: Product): Partial<Record<string, string>> {
  const freeCategories = new Set((product.all_optionals_categories ?? '').split(',').filter(Boolean))
  const categories: Partial<Record<string, string>> = {}
  for (const optional of product.optionals) {
    if (!(optional.category in categories) && !freeCategories.has(optional.category)) {
      categories[optional.category] = optional.color_name
    }
  }
  return categories
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDone, variant = 'success' }: { message: string; onDone: () => void; variant?: 'success' | 'error' }) {
  useEffect(() => {
    const t = setTimeout(onDone, 4000)
    return () => clearTimeout(t)
  }, [onDone])
  return variant === 'error' ? (
    // Canto superior direito: embaixo o toast cobria a barra de fechamento
    // móvel e disputava o canto com o FAB do Dashboard.
    <div role="alert" aria-live="assertive" className="fixed top-20 right-4 lg:right-8 z-toast flex items-center gap-3 bg-white border border-danger/30 text-danger px-5 py-3 rounded-xl shadow-xl toast max-w-sm">
      <X className="w-5 h-5 flex-shrink-0" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  ) : (
    <div role="status" aria-live="polite" className="fixed top-20 right-4 lg:right-8 z-toast flex items-center gap-3 bg-white border border-success/30 text-success px-5 py-3 rounded-xl shadow-xl toast">
      <CheckCircle className="w-5 h-5" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}

// ── Opcionais interativos no carrinho ─────────────────────────────────────────

function OptionalSelectors({ item, allOptionals, onChange, onPreview, catLabel, allowCustom }: {
  item: CartItem
  allowCustom: boolean
  allOptionals: OptionalColor[]
  onChange: (cat: string, value: string | null) => void
  onPreview: (photoUrl: string, label: string) => void
  catLabel: (code: string) => string
}) {
  const isEnglish = useLocale().locale === 'en-GB'
  const freeCats = new Set((item._product.all_optionals_categories ?? '').split(',').filter(Boolean))
  const productCats = Array.from(new Set(item._product.optionals.map(o => o.category)))
  const allCats = Array.from(new Set([...productCats, ...Array.from(freeCats)]))
  if (allCats.length === 0) return null
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {allCats.map(cat => {
        const isFree = freeCats.has(cat)
        const available = isFree
          ? allOptionals.filter(o => o.category === cat)
          : item._product.optionals.filter(o => o.category === cat)
        const currentValue = item.opt_categories[cat] ?? ''
        const custom = isLegacyCustom(currentValue)
        const currentOpt = available.find(o => optionalMatchesLegacyName(o, currentValue))
        return (
          <div key={cat} className="flex max-w-full min-w-0 min-h-11 lg:min-h-0 items-center gap-1 bg-surface-quiet border border-bg-2 rounded-md px-1.5 py-0.5 focus-within:ring-2 focus-within:ring-gold/40 focus-within:border-gold/60">
            <span className="type-label whitespace-nowrap">{catLabel(cat)}:</span>
            {currentOpt && hasOptionalPhoto(currentOpt) && (
              <button
                type="button"
                onClick={() => {
                  const source = optionalMedia(currentOpt, 'zoom').src
                  if (source) onPreview(source, optionalName(currentOpt.color_name, isEnglish))
                }}
                className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 lg:h-5 lg:w-5"
                aria-label={isEnglish ? `View photo of ${optionalName(currentOpt.color_name, true)}` : `Ver foto de ${currentOpt.color_name}`}
              >
                <OptionalSwatchImage optional={currentOpt} variant="thumb" displaySize={14} decorative className="h-3.5 w-3.5 rounded" />
              </button>
            )}
            <OptionalCombobox
              value={custom ? CUSTOM_OPTION : currentValue}
              onChange={value => onChange(cat, value === CUSTOM_OPTION ? CUSTOM_LEGACY_VALUE : value || null)}
              onPreview={onPreview}
              label={catLabel(cat)}
              placeholder="—"
              options={[
                ...available.map(option => ({
                  value: option.color_name,
                  label: optionalName(option.color_name, isEnglish),
                  photoUrl: option.photo_url,
                  optional: option,
                })),
                ...(allowCustom && allowsCustomFor(available) ? [{ value: CUSTOM_OPTION, label: customOptionLabel(isEnglish), photoUrl: null }] : []),
              ]}
              className="min-w-0 max-w-[240px]"
            />
          </div>
        )
      })}
    </div>
  )
}

// Comentário livre do item no pedido. O botão fica ao lado de excluir; a caixa
// fecha pelo botão só enquanto está vazia, para não esconder o que foi escrito.
function ItemCommentToggle({ comment, label, english, onToggle }: {
  comment: string | undefined
  label: string
  english: boolean
  onToggle: () => void
}) {
  const filled = Boolean(comment?.trim())
  return <button
    type="button"
    onClick={onToggle}
    aria-expanded={comment !== undefined}
    aria-label={english ? `Comment on ${label}` : `Comentário de ${label}`}
    title={english ? 'Item comment' : 'Comentário do item'}
    className={`w-11 h-11 flex items-center justify-center flex-shrink-0 transition-colors ${comment !== undefined ? 'text-gold' : 'text-muted hover:text-gold'}`}
    style={{ touchAction: 'manipulation' }}
  >
    <MessageSquare className="w-4 h-4" fill={filled ? 'currentColor' : 'none'} />
  </button>
}

function ItemCommentBox({ comment, english, onChange }: {
  comment: string | undefined
  english: boolean
  onChange: (comment: string) => void
}) {
  if (comment === undefined) return null
  return <label className="mt-2 block">
    <span className="type-label text-xs block mb-1">{english ? 'Item comment' : 'Comentário do item'}</span>
    <textarea
      value={comment}
      onChange={event => onChange(event.target.value)}
      maxLength={1000}
      rows={2}
      autoFocus={!comment}
      placeholder={english ? 'Write a comment about this item' : 'Escreva um comentário sobre este item'}
      className="w-full min-w-0 resize-y rounded-md border border-line bg-white px-2 py-1.5 text-xs leading-snug text-ink placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-gold/35"
    />
  </label>
}

function ApplicationSelectors({ product, choices, allOptionals, onChange, onPreview, english, allowCustom }: {
  product: Product
  allowCustom: boolean
  choices: CartItem['optional_choices']
  allOptionals: OptionalColor[]
  onChange: (applicationId: string, choice: OptionalChoiceInput | null) => void
  onPreview: (photoUrl: string, label: string) => void
  english: boolean
}) {
  const entries = productApplications(product)
  if (!entries.length) return null
  const progress = requiredApplicationProgress(product, choices, allOptionals)
  const errors = validateApplicationChoices(product, choices, allOptionals)
  const groups = new Map<string, { categoryName: string; entries: typeof entries }>()
  for (const entry of entries) {
    const existing = groups.get(entry.application.category_code)
    if (existing) existing.entries.push(entry)
    else groups.set(entry.application.category_code, {
      categoryName: optionalCategoryLabel(entry.application.category_name, english),
      entries: [entry],
    })
  }
  return <section className="mt-2 space-y-1.5" aria-label={english ? 'Optional applications' : 'Aplicações do opcional'}>
    {progress.total > 0 && <div className="flex items-center justify-between gap-3 text-[11px]" aria-live="polite">
        <span className={`inline-flex items-center gap-1.5 font-semibold ${progress.missing > 0 ? 'text-warning' : 'text-success'}`}>
          {progress.missing > 0 ? <CircleAlert className="h-3 w-3" aria-hidden="true" /> : <CheckCircle className="h-3 w-3" aria-hidden="true" />}
          {progress.missing > 0
            ? (english ? `${progress.missing} required ${progress.missing === 1 ? 'choice' : 'choices'} remaining` : `${progress.missing} ${progress.missing === 1 ? 'escolha obrigatória pendente' : 'escolhas obrigatórias pendentes'}`)
            : (english ? 'Required options complete' : 'Opcionais obrigatórios completos')}
        </span>
        <span className="tabular-nums text-ink-3">{progress.filled}/{progress.total}</span>
    </div>}
    {Array.from(groups.entries()).map(([categoryCode, group]) => <div key={categoryCode} className="space-y-1">
      <h3 className="px-1 text-[10px] font-semibold uppercase tracking-wide text-gold">{group.categoryName}</h3>
      {group.entries.map(({ application, componentName }) => {
        const choice = choices.find(candidate => candidate.application_id === application.id)
        const custom = choice ? isCustomChoice(choice) : false
        const value = custom ? CUSTOM_OPTION : choice?.optional_id ?? ''
        const missing = application.required && !value
        const options = allowedForApplication(application, allOptionals)
        const selected = options.find(option => option.id === value)
        const preview = selected ? optionalMedia(selected, 'thumb').src : null
        const areaName = `${componentName ? `${componentName} — ` : ''}${applicationName(application, english)}`
        return <div key={application.id} className={`grid min-h-11 min-w-0 grid-cols-[minmax(128px,0.9fr)_minmax(0,1.1fr)] items-stretch rounded-md border bg-white focus-within:ring-2 focus-within:ring-gold/35 lg:min-h-9 ${missing ? 'border-warning/60' : 'border-line'}`}>
          <span className="flex min-w-0 items-center border-r border-line px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-gold">
            <span className="break-words leading-snug">{areaName}{application.required && <span className="ml-0.5 text-warning" aria-label={english ? 'Required' : 'Obrigatório'}>•</span>}</span>
          </span>
          <span className="flex min-w-0 items-center">
            {preview && selected && <button
              type="button"
              onClick={() => {
                const source = selected.photo_variants
                  ? optionalMedia(selected, 'zoom').src
                  : selected.photo_url ?? selected.thumbnail_url ?? preview
                if (source) onPreview(source, optionalName(selected.color_name, english))
              }}
              className="ml-1 flex h-11 w-11 flex-shrink-0 items-center justify-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 lg:h-9 lg:w-9"
              aria-label={english ? `View photo of ${optionalName(selected.color_name, true)}` : `Ver foto de ${selected.color_name}`}
            >
              <OptionalSwatchImage optional={selected} variant="thumb" displaySize={20} decorative className="h-5 w-5 rounded" />
            </button>}
            <OptionalCombobox
              value={value}
              onChange={next => onChange(application.id, next === CUSTOM_OPTION
                ? { application_id: application.id, custom_text: '' }
                : next ? { application_id: application.id, optional_id: next } : null)}
              onPreview={onPreview}
              label={`${group.categoryName}: ${areaName}`}
              placeholder={english ? 'Choose an option' : 'Escolha uma opção'}
              invalid={missing}
              options={[
                ...options.map(option => ({
                  value: option.id,
                  label: optionalName(option.color_name, english),
                  photoUrl: option.thumbnail_url ?? option.photo_url,
                  previewUrl: option.photo_url ?? option.thumbnail_url,
                  optional: option,
                })),
                ...(allowCustom && allowsCustomFor(options) ? [{ value: CUSTOM_OPTION, label: customOptionLabel(english), photoUrl: null }] : []),
              ]}
              className="min-w-0 flex-1 px-2 py-1 text-[11px] font-medium"
            />
          </span>
        </div>
      })}
    </div>)}
    {errors.filter(error => !error.endsWith('escolha obrigatória')).map((error, index) => <p key={index} className="text-xs text-danger" role="alert">{error}</p>)}
  </section>
}

function ApplicationStatus({ product, choices, allOptionals, english }: {
  product: Product
  choices: CartItem['optional_choices']
  allOptionals: OptionalColor[]
  english: boolean
}) {
  const progress = requiredApplicationProgress(product, choices, allOptionals)
  if (progress.total === 0) return null
  return progress.missing > 0
    ? <span className="mt-1 inline-flex items-center gap-1 rounded-md bg-warning-soft px-1.5 py-0.5 text-[10px] font-semibold text-warning">
        <CircleAlert className="h-3 w-3" aria-hidden="true" />
        {english ? `${progress.missing} pending` : `${progress.missing} ${progress.missing === 1 ? 'pendente' : 'pendentes'}`}
      </span>
    : <span className="mt-1 inline-flex items-center gap-1 rounded-md bg-success-soft px-1.5 py-0.5 text-[10px] font-semibold text-success">
        <CheckCircle className="h-3 w-3" aria-hidden="true" />
        {english ? 'Options complete' : 'Opcionais completos'}
      </span>
}

// ── Lightbox de foto ──────────────────────────────────────────────────────────

function PhotoLightbox({ url, onClose }: { url: string; onClose: () => void }) {
  const isEnglish = useLocale().locale === 'en-GB'
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })
  useEffect(() => {
    const returnFocus = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onCloseRef.current() }
    document.addEventListener('keydown', handleKeyDown)
    return () => { document.removeEventListener('keydown', handleKeyDown); returnFocus?.focus() }
  }, [])
  return (
    <div className="fixed inset-0 z-modal-sub flex items-center justify-center bg-scrim/75 backdrop-blur-sm"
      onClick={onClose} role="dialog" aria-modal="true" aria-label={isEnglish ? 'Enlarged product photo' : 'Foto ampliada do produto'}>
      <div className="relative mx-4" onClick={(e) => e.stopPropagation()}>
        <img src={url} alt={isEnglish ? 'Enlarged product' : 'Produto ampliado'} className="max-w-[min(480px,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-line" />
        <button
          ref={closeRef}
          onClick={onClose}
          className="absolute -top-3 -right-3 bg-white border border-line rounded-full w-11 h-11 flex items-center justify-center shadow-md text-muted hover:text-ink transition-colors"
          aria-label={isEnglish ? 'Close enlarged photo' : 'Fechar foto ampliada'}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

// Preço efetivo conforme o perfil de faturamento do cliente (Bloco 62).
// Sem cliente selecionado, usa o preço de lojista por padrão.
function effectivePrice(product: Product, profile: string | undefined): number {
  // Bloco 96: a API omite (null) o preço que a role logada não pode ver. O
  // perfil pedido aqui é sempre o que o servidor liberou, então o `?? 0` só
  // protege a prévia de quebrar — o valor faturado é recalculado no backend.
  const price = product.market_prices?.[profile ?? 'lojista']
    ?? (profile === 'corporativo' ? product.price_corporativo : product.price_lojista)
  return price ?? 0
}

// ── Mobile cart card ──────────────────────────────────────────────────────────

function RugMeasureFields({ item, english, locale, qtyLimitWarning, onAreaDimensionsChange }: {
  item: CartItem
  english: boolean
  locale: string
  qtyLimitWarning: boolean
  onAreaDimensionsChange: (lineId: string, width: number | null, depth: number | null) => void
}) {
  const width = item.area_width_m ?? null
  const depth = item.area_depth_m ?? null
  const pieces = item.area_pieces ?? 1
  const preview = previewArea(width, depth)
  const maximumArea = areaLimit(item._product)
  const legacyNoMeasurements = Boolean(item.source_order_item_id && width == null && depth == null)
  const warning = qtyLimitWarning || (preview != null && maximumArea != null && preview > maximumArea)

  // Mesmo desenho das outras colunas da linha (rótulo em cima, campo compacto
  // embaixo): dois campos estreitos sem as setas do input numérico.
  const dimensionInput = 'input w-14 text-center text-xs border border-line rounded-lg px-1 py-1 bg-white text-ink [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'

  return (
    <div>
      {/* L × P é a medida de cada peça; a quantidade de peças fica na coluna Qtd. */}
      <span className="type-label text-xs block mb-1 whitespace-nowrap">{english ? 'W × D (m)' : 'L × P (m)'}</span>
      <div className="flex items-center gap-1">
        <NumberField
          value={width}
          step="0.01"
          min="0.01"
          aria-label={english ? 'Width in metres' : 'Largura em metros'}
          className={dimensionInput}
          onValueChange={(value) => onAreaDimensionsChange(item.line_id, value > 0 ? value : null, depth)}
        />
        <span className="text-xs text-muted" aria-hidden="true">×</span>
        <NumberField
          value={depth}
          step="0.01"
          min="0.01"
          aria-label={english ? 'Depth in metres' : 'Profundidade em metros'}
          className={dimensionInput}
          onValueChange={(value) => onAreaDimensionsChange(item.line_id, width, value > 0 ? value : null)}
        />
      </div>
      {preview != null ? (
        <p className="mt-0.5 text-[10px] text-muted whitespace-nowrap" aria-live="polite">
          = {formatArea(preview, locale)}{pieces > 1 && <> × {pieces} = {formatArea(normalizeAreaQty(preview * pieces), locale)}</>}
        </p>
      ) : legacyNoMeasurements ? (
        <p className="mt-0.5 text-[10px] text-muted whitespace-nowrap">
          {formatArea(item.qty, locale)} <span className="text-warning">({english ? 'no measurements on record' : 'medidas não registradas'})</span>
        </p>
      ) : (
        <p className="mt-0.5 text-[10px] font-semibold text-warning whitespace-nowrap" aria-live="polite">{english ? 'Enter W × D' : 'Informe L × P'}</p>
      )}
      {maximumArea !== null && (
        <p className={`mt-0.5 text-[10px] whitespace-nowrap ${warning ? 'text-warning font-semibold' : 'text-muted'}`}>
          {english ? 'max.' : 'máx.'} {formatArea(maximumArea, locale)}
        </p>
      )}
    </div>
  )
}

function MobileCartCard({
  item, onQtyChange, onAreaDimensionsChange, onAreaPiecesChange, qtyLimitWarning, onDiscountChange, maxDiscount, onRemove, onPhotoClick, onPreview, allOptionals, optionalsReady, onOptChange, onApplicationChange, onEditApplications, onToggleComment, onCommentChange, priceProfile, catLabel, currency, locale
}: {
  item: CartItem
  onQtyChange: (code: string, qty: number) => void
  onAreaDimensionsChange: (lineId: string, width: number | null, depth: number | null) => void
  onAreaPiecesChange: (lineId: string, pieces: number) => void
  qtyLimitWarning: boolean
  onDiscountChange: (code: string, discount: number) => void
  maxDiscount: number
  onRemove: (code: string) => void
  onPhotoClick: (url: string) => void
  onPreview: (photoUrl: string, label: string) => void
  allOptionals: OptionalColor[]
  optionalsReady: boolean
  onOptChange: (cat: string, value: string | null) => void
  onApplicationChange: (applicationId: string, choice: OptionalChoiceInput | null) => void
  onEditApplications: () => void
  onToggleComment: () => void
  onCommentChange: (comment: string) => void
  priceProfile: string
  catLabel: (code: string) => string
  currency: string
  locale: string
}) {
  const isEnglish = useLocale().locale === 'en-GB'
  const measurementMarket = currency === 'EUR' ? 'EU' : 'BR'
  const allowCustom = allowsCustomOption(measurementMarket) && optionalsReady
  const measurementLocale = locale === 'en-GB' ? 'en-GB' : locale === 'pt-PT' ? 'pt-PT' : 'pt-BR'
  const subtotal = item.qty * effectivePrice(item._product, priceProfile) * (1 - (item.discount || 0) / 100)
  const hasDiscount = item.discount > 0
  const soldByArea = isAreaProduct(item._product)
  const pieces = item.area_pieces ?? 1

  return (
    <div className="bg-white border border-line rounded-xl p-3.5 shadow-sm">
      {/* Top: thumbnail + info + trash */}
      <div className="flex gap-3">
        {item._product.photo_url
          ? <button type="button" onClick={() => onPhotoClick(item._product.photo_url!)} className="w-14 h-14 rounded-lg flex-shrink-0" aria-label={isEnglish ? `Enlarge photo of ${item._product.description}` : `Ampliar foto de ${item._product.description}`}>
              <img src={item._product.thumbnail_url ?? item._product.photo_url} alt="" loading="lazy" decoding="async" className="w-full h-full object-cover rounded-lg border border-line active:opacity-70 transition-opacity" />
            </button>
          : <div className="w-14 h-14 bg-bg-2 rounded-lg flex items-center justify-center flex-shrink-0">
              <ImageIcon className="w-5 h-5 text-faint" />
            </div>
        }
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="type-code">{item.product_code}</span>
              <p className="text-xs font-semibold text-ink leading-snug mt-0.5 line-clamp-2">{item._product.description}</p>
              {!item.preserve_optional_choices && <ApplicationStatus product={item._product} choices={item.optional_choices} allOptionals={allOptionals} english={isEnglish} />}
              {item._product.components.length > 0 && (
                <ul className="mt-0.5 space-y-0.5">
                  {item._product.components.map((comp) => (
                    <li key={comp.id} className="text-[11px] text-ink-3 leading-snug">
                      • {comp.qty}x {comp.description} ({formatDimensions(comp, measurementMarket, measurementLocale)})
                      {comp.optionals.length > 0 && (
                        <span className="block text-muted pl-2.5 break-words">{compFinishes(comp.optionals, catLabel, locale === 'en-GB')}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {item._product.observacao && (
                <p className="text-[11px] leading-snug text-gold italic mt-1 line-clamp-2">{item._product.observacao}</p>
              )}
              {soldByArea && <div className="mt-2"><RugMeasureFields item={item} english={isEnglish} locale={measurementLocale} qtyLimitWarning={qtyLimitWarning} onAreaDimensionsChange={onAreaDimensionsChange} /></div>}
            </div>
            <div className="flex flex-shrink-0">
              <ItemCommentToggle comment={item.comment} label={item._product.description} english={isEnglish} onToggle={onToggleComment} />
              <button
                onClick={() => onRemove(item.line_id)}
                className="text-muted active:text-danger transition-colors w-11 h-11 flex items-center justify-center flex-shrink-0"
                style={{ touchAction: 'manipulation' }}
                aria-label={isEnglish ? `Remove ${item._product.description} from quote` : `Remover ${item._product.description} do orçamento`}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
          <OptionalSelectors item={item} allOptionals={allOptionals} onChange={onOptChange} onPreview={onPreview} catLabel={catLabel} allowCustom={allowCustom} />
          {item.preserve_optional_choices ? <div className="mt-2 text-xs text-ink-2">
            {(item.saved_choices ?? []).map(choice => <p key={choice.id} className="break-words">{formatChoice(choice, isEnglish)}</p>)}
            <button type="button" className="text-gold underline mt-1" onClick={onEditApplications}>{isEnglish ? 'Change optional applications' : 'Alterar aplicações do opcional'}</button>
          </div> : <ApplicationSelectors product={item._product} choices={item.optional_choices} allOptionals={allOptionals} onChange={onApplicationChange} onPreview={onPreview} english={isEnglish} allowCustom={allowCustom} />}
          <ItemCommentBox comment={item.comment} english={isEnglish} onChange={onCommentChange} />
        </div>
      </div>

      {/* Bottom: qty +/- | desconto | subtotal — paridade com a tabela desktop:
          o representante no showroom concede desconto pelo tablet/celular. O
          teto é o do usuário; o servidor revalida contra cliente/representante. */}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 mt-3 pt-3 border-t border-bg-2">
        {/* Qty stepper: no tapete conta o número de peças iguais. */}
        <div>
          <label htmlFor={`mobile-qty-${item.line_id}`} className="type-label block mb-1 text-center">{isEnglish ? 'Qty' : 'Qtd'}</label>
          <div className="flex items-center gap-0 border border-line rounded-lg overflow-hidden">
            <button
              onClick={() => soldByArea ? onAreaPiecesChange(item.line_id, Math.max(1, pieces - 1)) : onQtyChange(item.line_id, Math.max(1, item.qty - 1))}
              className="w-11 h-11 flex items-center justify-center text-muted active:bg-bg-2 transition-colors"
              style={{ touchAction: 'manipulation' }}
              aria-label={soldByArea ? (isEnglish ? `Decrease number of pieces of ${item._product.description}` : `Diminuir número de peças de ${item._product.description}`) : (isEnglish ? `Decrease quantity of ${item._product.description}` : `Diminuir quantidade de ${item._product.description}`)}
            >
              <Minus className="w-3.5 h-3.5" />
            </button>
            <span className="w-9 text-center text-sm font-semibold text-ink" aria-live="polite">{soldByArea ? pieces : item.qty}</span>
            <button
              onClick={() => soldByArea ? onAreaPiecesChange(item.line_id, pieces + 1) : onQtyChange(item.line_id, item.qty + 1)}
              className="w-11 h-11 flex items-center justify-center text-muted active:bg-bg-2 transition-colors"
              style={{ touchAction: 'manipulation' }}
              aria-label={soldByArea ? (isEnglish ? `Increase number of pieces of ${item._product.description}` : `Aumentar número de peças de ${item._product.description}`) : (isEnglish ? `Increase quantity of ${item._product.description}` : `Aumentar quantidade de ${item._product.description}`)}
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Desconto percentual */}
        <div className="flex items-center gap-1.5">
          <label htmlFor={`mobile-disc-${item.line_id}`} className="type-label">
            {isEnglish ? 'Disc. %' : 'Desc. %'}
          </label>
          <NumberField
            id={`mobile-disc-${item.line_id}`}
            min={0}
            max={maxDiscount}
            step="any"
            value={item.discount}
            placeholder="0"
            disabled={maxDiscount <= 0}
            aria-label={isEnglish ? `Discount on ${item._product.description}` : `Desconto em ${item._product.description}`}
            className="input w-16 text-center text-sm px-1.5 py-1.5 disabled:opacity-50"
            onValueChange={(v) => onDiscountChange(item.line_id, Math.min(maxDiscount, Math.max(0, v)))}
          />
        </div>

        {/* Pricing */}
        <div className="text-right ml-auto">
          {hasDiscount && (
            <p className="text-[10px] text-muted line-through"><SafePrice value={effectivePrice(item._product, priceProfile) * item.qty} currency={currency} locale={locale} /></p>
          )}
          {hasDiscount && (
            <span className="text-[10px] bg-gold/10 text-gold font-semibold px-1.5 py-0.5 rounded-full">
              -{item.discount}%
            </span>
          )}
          <p className="text-sm font-bold text-ink mt-0.5"><SafePrice value={subtotal} currency={currency} locale={locale} /></p>
        </div>
      </div>
    </div>
  )
}

// ── Formulário de configuração (usado no aside e no drawer) ───────────────────

function LockedField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <span className="type-label block">{label}</span>
      <div className="flex items-center gap-2 bg-bg border border-line rounded-lg px-3 py-2 h-[36px]">
        <Lock className="w-3 h-3 text-faint flex-shrink-0" />
        <span className="text-sm font-medium text-ink truncate flex-1">{value}</span>
      </div>
    </div>
  )
}

function OrderForm({
  reps, clients, selectedRep, selectedClient, notes,
  repQuery, clientQuery,
  onRepChange, onClientChange, onNotesChange,
  onRepSearch, onClientSearch, repsLoading, clientsLoading,
  onQuickAddRep, onQuickAddClient,
  budgetCode, cart, onSubmit, isGenerating,
  repLocked, clientLocked,
  editMode, editCode, isEnglish,
}: {
  reps: Representative[]; clients: Client[]
  selectedRep: Representative | null; selectedClient: Client | null; notes: string
  repQuery: string; clientQuery: string
  onRepChange: (r: Representative | null) => void
  onClientChange: (c: Client | null) => void
  onNotesChange: (n: string) => void
  onRepSearch: (query: string) => void
  onClientSearch: (query: string) => void
  repsLoading?: boolean
  clientsLoading?: boolean
  onQuickAddRep: () => void; onQuickAddClient: () => void
  budgetCode: string; cart: CartItem[]
  onSubmit: () => void; isGenerating: boolean
  repLocked?: boolean; clientLocked?: boolean
  editMode?: boolean; editCode?: string
  isEnglish?: boolean
}) {
  const missingAreaDimensions = cart.some(item => isAreaProduct(item._product) && !item.source_order_item_id && (item.area_width_m == null || item.area_depth_m == null))
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-line-soft">
        <h2 className="text-base font-semibold text-ink">{editMode ? (isEnglish ? 'Edit Order' : 'Editar Pedido') : (isEnglish ? 'New Quote' : 'Novo Orçamento')}</h2>
        <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold tracking-wider ${editMode ? 'bg-gold/10 text-gold' : 'bg-olive/10 text-olive'}`}>
          {editMode ? editCode : budgetCode}
        </span>
      </div>

      {repLocked ? (
        <LockedField
          label={isEnglish ? 'Representative' : 'Representante'}
          value={selectedRep ? `${selectedRep.name} — ${selectedRep.city}/${selectedRep.state}` : '—'}
        />
      ) : (
        <div className="space-y-1">
          <span className="type-label block">{isEnglish ? 'Representative' : 'Representante'}</span>
          <Autocomplete
            searchPlaceholder={isEnglish ? 'Search representative...' : 'Buscar representante...'}
            items={reps}
            value={selectedRep}
            query={repQuery}
            getLabel={(r) => `${r.name} — ${r.city}/${r.state}`}
            getSearch={(r) => `${r.name} ${r.email} ${r.city}`}
            onChange={onRepChange}
            onClear={() => onRepChange(null)}
            onQueryChange={onRepSearch}
            isLoading={repsLoading}
            displayPlaceholder={isEnglish ? 'No representative' : 'Nenhum'}
            showQuickAdd
            onQuickAdd={onQuickAddRep}
          />
        </div>
      )}

      {clientLocked && selectedClient ? (
        <LockedField label={isEnglish ? 'Client' : 'Cliente'} value={`${selectedClient.name} — ${selectedClient.city}/${selectedClient.state}`} />
      ) : (
        <div className="space-y-1">
          <span className="type-label block">{isEnglish ? 'Client' : 'Cliente'}</span>
          <Autocomplete
            searchPlaceholder={isEnglish ? 'Search client...' : 'Buscar cliente...'}
            items={clients}
            value={selectedClient}
            query={clientQuery}
            getLabel={(c) => `${c.name} — ${c.city}/${c.state}`}
            getSearch={(c) => `${c.name} ${c.email} ${c.city}`}
            onChange={onClientChange}
            onClear={() => onClientChange(null)}
            onQueryChange={onClientSearch}
            isLoading={clientsLoading}
            displayPlaceholder={isEnglish ? 'Select a client...' : 'Selecione o cliente...'}
            showQuickAdd
            onQuickAdd={onQuickAddClient}
          />
        </div>
      )}

      <div className="space-y-1">
        <span className="type-label block">{isEnglish ? 'Notes' : 'Observações'}</span>
        <textarea
          className="input resize-none text-xs"
          rows={3}
          placeholder={isEnglish ? 'Quote notes...' : 'Observações do orçamento...'}
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
        />
      </div>


      {(!selectedClient || cart.length === 0) && !isGenerating && (
        <p className="type-meta text-center -mt-1">
          {cart.length === 0 ? (isEnglish ? 'Add at least one product to the quote.' : 'Adicione ao menos um produto ao orçamento.') : (isEnglish ? 'Select a client to continue.' : 'Selecione um cliente para continuar.')}
        </p>
      )}
      <button
        onClick={onSubmit}
        disabled={!selectedClient || cart.length === 0 || missingAreaDimensions || isGenerating}
        style={{ touchAction: 'manipulation' }}
        className="w-full py-3.5 rounded-lg text-xs font-bold tracking-widest text-white transition-all bg-gold hover:bg-gold-600 active:bg-gold-700 disabled:bg-faint disabled:cursor-not-allowed uppercase shadow-sm active:scale-[0.98] active:opacity-85"
      >
        {editMode ? (isEnglish ? 'Save Changes' : 'Salvar Alterações') : (isEnglish ? 'Finalize Quote' : 'Finalizar Orçamento')}
      </button>
    </div>
  )
}

// ── Bottom Drawer (mobile) ────────────────────────────────────────────────────

function BottomDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const isEnglish = useLocale().locale === 'en-GB'
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onCloseRef.current = onClose })
  useEffect(() => {
    if (!open) return
    const returnFocus = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const panel = panelRef.current
    const focusable = panel?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
    focusable?.[0]?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
      if (event.key !== 'Tab' || !focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
      returnFocus?.focus()
    }
  }, [open])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-drawer flex items-end lg:hidden" role="dialog" aria-modal="true" aria-labelledby="budget-drawer-title">
      <div className="fixed inset-0 bg-scrim/40 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div ref={panelRef} className="relative w-full bg-white rounded-t-2xl shadow-2xl max-h-[90vh] overflow-y-auto overscroll-contain">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h2 id="budget-drawer-title" className="text-sm font-semibold text-ink">{isEnglish ? 'Quote Settings' : 'Configurar Orçamento'}</h2>
          <button onClick={onClose} className="w-11 h-11 flex items-center justify-center text-muted hover:text-ink" aria-label={isEnglish ? 'Close quote settings' : 'Fechar configuração do orçamento'}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 pb-32">{children}</div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function OrcamentoPage() {
  const { user } = useAuth()
  const { locale: europeanLocale } = useLocale()
  const isEnglish = europeanLocale === 'en-GB'
  const userId = user?.id ?? ''
  const market = user?.active_market ?? 'BR'
  const currency = market === 'EU' ? 'EUR' : 'BRL'
  const locale = market === 'EU' ? europeanLocale : 'pt-BR'
  const taxLabel = market === 'EU' ? (isEnglish ? 'VAT' : 'IVA') : 'IPI'
  const cartKey = cartStorageKey(userId, market)
  const clientStorageKey = `orcamento_client_id:${userId}:${market}`
  const repStorageKey = `orcamento_rep_id:${userId}:${market}`
  const [searchParams, setSearchParams] = useSearchParams()
  const editId = searchParams.get('edit')

  // Locking flags
  const isRep = user?.role === 'representante'
  // cliente-final: role própria `cliente` (ou legado `vendedor`+linked_id)
  const isClientUser = user?.role === 'cliente' || (user?.role === 'vendedor' && !!user?.linked_id)
  const fixedOrderRepId = !editId && user?.role === 'admin' ? user.order_rep_id : null
  const repLocked = isRep || isClientUser || !!fixedOrderRepId
  const clientLocked = isClientUser

  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [selectedRep, setSelectedRep] = useState<Representative | null>(null)
  const [notes, setNotes] = useState('')
  const [cart, setCart] = useState<CartItem[]>([])
  const [persistedCart] = useState<PersistedCartItem[]>(
    () => readPersistedCart(user?.id, user?.active_market),
  )
  const [selectedEuPriceList, setSelectedEuPriceList] = useState<PriceListCode | null>(
    () => editId ? null : readCartPriceList(user?.id, user?.active_market),
  )
  // sessionStorage (não localStorage): sobrevive a trocar de aba dentro do app
  // e a um F5, mas some quando a aba fecha — não volta pré-preenchido amanhã.
  const [savedClientId, setSavedClientId] = useState(
    () => sessionStorage.getItem(clientStorageKey) ?? '',
  )
  // null = nenhuma preferência gravada; vazio = remoção explícita.
  const [savedRepId, setSavedRepId] = useState<string | null>(
    () => localStorage.getItem(repStorageKey),
  )
  const [cartHydrated, setCartHydrated] = useState(false)
  const [configureCode, setConfigureCode] = useState(searchParams.get('configure'))
  const [productQuery, setProductQuery] = useState(searchParams.get('configure') ?? '')
  const [clientQuery, setClientQuery] = useState('')
  const [repQuery, setRepQuery] = useState('')
  const [productOpen, setProductOpen] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [selectedChoices, setSelectedChoices] = useState<CartItem['optional_choices']>([])
  const [cartFilter, setCartFilter] = useState('')
  const [toast, setToast] = useState<{ message: string; variant: 'success' | 'error' } | null>(null)
  const [quickModal, setQuickModal] = useState<'client' | 'rep' | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [qtyLimitWarnings, setQtyLimitWarnings] = useState<Set<string>>(() => new Set())
  const productRef = useRef<HTMLDivElement>(null)
  const itemsSectionRef = useRef<HTMLElement>(null)
  // Último `?configure=` já processado. O ajuste de estado correspondente roda
  // durante o render (padrão do React para reagir a dados que chegam depois),
  // não dentro de um efeito — evita renders em cascata.
  const [handledConfigureCode, setHandledConfigureCode] = useState<string | null>(null)
  const setSearchParamsRef = useRef(setSearchParams)
  useEffect(() => { setSearchParamsRef.current = setSearchParams })

  const debouncedProductQuery = useDebouncedValue(productQuery.trim(), 300)
  const debouncedClientQuery = useDebouncedValue(clientQuery.trim(), 300)
  const debouncedRepQuery = useDebouncedValue(repQuery.trim(), 300)

  const editOrderQuery = useOrder(editId ?? '')
  const editOrder = editOrderQuery.data
  const productSearch = useProductsPage({
    skip: 0,
    limit: 15,
    q: debouncedProductQuery || undefined,
    include_total: false,
    sort_by: 'product_code',
    sort_dir: 'asc',
  })
  const products = productSearch.data?.items ?? EMPTY_PRODUCTS
  // `?configure=CODE` (link vindo de outra página) adiciona o produto uma única
  // vez. O ajuste de estado acontece durante o render — e não dentro de um
  // efeito, que dispararia renders em cascata.
  if (configureCode && cartHydrated && handledConfigureCode !== configureCode) {
    const configureProduct = products.find(item => item.product_code === configureCode)
    if (configureProduct) {
      setHandledConfigureCode(configureCode)
      setCart(previous => [...previous, {
        line_id: crypto.randomUUID(),
        product_code: configureProduct.product_code,
        qty: 1,
        sold_by_area: isAreaProduct(configureProduct),
        ...(isAreaProduct(configureProduct) ? { area_width_m: null, area_depth_m: null, area_pieces: 1 } : {}),
        discount: 0,
        opt_categories: initialLegacyOptionCategories(configureProduct),
        optional_choices: [],
        _product: configureProduct,
      }])
      setSelectedProduct(null)
      setSelectedChoices([])
      setCartFilter('')
      setProductQuery('')
      setConfigureCode(null)
    }
  }

  useEffect(() => {
    if (!handledConfigureCode) return
    setSearchParamsRef.current({}, { replace: true })
    const frame = window.requestAnimationFrame(() => {
      itemsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      itemsSectionRef.current?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [handledConfigureCode])
  const clientSearch = useClientsPage({
    skip: 0,
    limit: 15,
    q: debouncedClientQuery || undefined,
    include_total: false,
    sort_by: 'name',
    sort_dir: 'asc',
  })
  const clients = clientSearch.data?.items ?? []
  const repSearch = useRepresentativesPage({
    skip: 0,
    limit: 15,
    q: debouncedRepQuery || undefined,
    include_total: false,
    sort_by: 'name',
    sort_dir: 'asc',
  })
  const reps = repSearch.data?.items ?? []

  const neededProductCodes = Array.from(new Set([
    ...(!editId ? persistedCart.map((item) => item.product_code) : []),
    ...(editOrder?.items.map((item) => item.product_code) ?? []),
    ...cart.map((item) => item.product_code),
  ]))
  const resolvedProductQuery = useProductsByCodes(
    neededProductCodes,
    neededProductCodes.length > 0,
  )
  const resolvedProducts = resolvedProductQuery.data ?? EMPTY_PRODUCTS

  const freeOptionalCategories = Array.from(new Set(
    [...cart, ...(selectedProduct ? [{ _product: selectedProduct }] : [])].flatMap((item) => [
      ...productApplications(item._product).filter(entry => entry.application.allow_all).map(entry => entry.application.category_code),
      ...(
      (item._product.all_optionals_categories ?? '')
        .split(',')
        .map((category) => category.trim())
        .filter(Boolean)
      ),
    ]),
  ))
  const { data: allOptionals = [], isSuccess: freeOptionalsLoaded } = useOptionalsForCategories(
    freeOptionalCategories,
    freeOptionalCategories.length > 0,
  )
  // Sem a lista do servidor não dá para saber se há acabamento ILYA, então
  // Customizado só aparece depois que ela carrega.
  const optionalsReady = freeOptionalCategories.length === 0 || freeOptionalsLoaded
  const { data: optCategories = [] } = useOptionalCategories()
  const catLabel = (code: string) => optionalCategoryLabel(optCategories.find(c => c.code === code)?.name ?? code, locale === 'en-GB')

  const targetClientId = (
    (isClientUser ? user?.linked_id : null)
    || editOrder?.client_id
    || (!editId && !clientLocked ? savedClientId : '')
    || ''
  )
  const resolvedClientQuery = useClient(
    targetClientId,
    !!targetClientId,
  )
  const resolvedClient = resolvedClientQuery.data
  const targetRepId = (
    (isRep ? user?.rep_id : null)
    || editOrder?.rep_id
    || fixedOrderRepId
    || (
      !editId && !repLocked
        ? (
          savedRepId !== null
            ? savedRepId
            : selectedClient?.rep_id ?? resolvedClient?.rep_id
        )
        : resolvedClient?.rep_id
    )
    || ''
  )
  const resolvedRepQuery = useRepresentative(
    targetRepId,
    !!targetRepId,
  )
  const resolvedRep = resolvedRepQuery.data

  const createOrderM = useCreateOrder()
  const updateOrderM = useUpdateOrder()
  const createClientM = useCreateClient()
  const createRepM = useCreateRepresentative()

  // Com cliente escolhido, o orçamento fecha na tabela de faturamento dele (o
  // servidor recusa outra). Pedido em edição mantém a tabela com que foi
  // feito. Sem cliente, o seletor EU só serve para consultar preços.
  const clientDefaultPriceProfile = selectedClient?.price_profile ?? 'lojista'
  const lockedEuPriceList: PriceListCode | null = market === 'EU'
    ? ((editOrder?.price_list_code as PriceListCode | undefined) ?? selectedClient?.price_profile ?? null)
    : null
  const priceProfile: PriceListCode = market === 'EU'
    ? (lockedEuPriceList ?? selectedEuPriceList ?? 'lojista')
    : (clientDefaultPriceProfile === 'pvp' || clientDefaultPriceProfile === 'arquiteto'
        ? 'lojista'
        : clientDefaultPriceProfile)
  const priceProfileLabel = {
    lojista: 'Lojista',
    corporativo: 'Corporativo',
    pvp: 'PVP',
    arquiteto: 'Arquiteto',
  }[priceProfile]
  const maxDiscount = orderMaxDiscount(
    market,
    priceProfile,
    user?.role,
    user?.max_discount ?? 0,
  )

  function selectEuPriceList(next: PriceListCode) {
    setSelectedEuPriceList(next)
    if (!editId) writeCartPriceList(userId, market, next)
  }

  function clearDraftPriceList() {
    setSelectedEuPriceList(null)
    removeCartPriceList(userId, market)
  }

  useEffect(() => {
    // A troca do cliente pode mudar a tabela e precisa reduzir descontos já
    // presentes no carrinho antes que o orçamento seja enviado.
    // oxlint-disable-next-line react/set-state-in-effect
    setCart(previous => previous.map(item => (
      item.discount > maxDiscount ? { ...item, discount: maxDiscount } : item
    )))
  }, [maxDiscount])

  function handleClientChange(client: Client | null) {
    const clientId = client?.id ?? ''
    setSelectedClient(client)
    setSavedClientId(clientId)
    if (!repLocked && savedRepId === null) setSelectedRep(null)
    if (clientId) sessionStorage.setItem(clientStorageKey, clientId)
    else sessionStorage.removeItem(clientStorageKey)
  }

  function handleRepChange(rep: Representative | null) {
    const repId = rep?.id ?? ''
    setSelectedRep(rep)
    setSavedRepId(repId)
    if (repId) localStorage.setItem(repStorageKey, repId)
    else localStorage.setItem(repStorageKey, '')
  }

  function resetSavedSelections() {
    setSelectedClient(null)
    setSelectedRep(null)
    setSavedClientId('')
    setSavedRepId(null)
    sessionStorage.removeItem(clientStorageKey)
    localStorage.removeItem(repStorageKey)
  }

  // O carrinho salvo resolve somente os SKUs necessários, sem baixar o catálogo.
  if (!cartHydrated && !editId) {
    if (persistedCart.length === 0) {
      setCartHydrated(true)
    } else if (resolvedProductQuery.isSuccess) {
      const productMap = new Map(
        resolvedProducts.map((product) => [product.product_code, product]),
      )
      setCart(
        persistedCart
          .filter((item) => productMap.has(item.product_code))
          .map((item) => ({
            ...item,
            sold_by_area: isAreaProduct(productMap.get(item.product_code)!),
            line_id: item.line_id || crypto.randomUUID(),
            optional_choices: item.optional_choices ?? [],
            _product: productMap.get(item.product_code)!,
          })),
      )
      setCartHydrated(true)
    }
  }

  useEffect(() => {
    if (editId || !cartHydrated) return
    const serializable = cart.map(({ _product, ...rest }) => ({
      ...rest,
      sold_by_area: isAreaProduct(_product),
    }))
    localStorage.setItem(cartKey, JSON.stringify(serializable))
    notifyCartChanged()
  }, [cart, cartHydrated, cartKey, editId])

  // Sincroniza _product com dados frescos da API (garante observacao e preço atualizados)
  const [prevResolvedProducts, setPrevResolvedProducts] = useState<typeof resolvedProducts | null>(null)
  if (prevResolvedProducts !== resolvedProducts) {
    setPrevResolvedProducts(resolvedProducts)
    if (resolvedProducts.length > 0) {
      const productMap = new Map(
        resolvedProducts.map((product) => [product.product_code, product]),
      )
      setCart(prev => prev.map(item => ({
        ...item,
        sold_by_area: isAreaProduct(productMap.get(item.product_code) ?? item._product),
        _product: productMap.get(item.product_code) ?? item._product,
      })))
    }
  }

  // Pré-preenche contas vinculadas e restaura seleções por ID.
  if (!editId && resolvedClient && !selectedClient) {
    setSelectedClient(resolvedClient)
  }
  if (!editId && resolvedRep && !selectedRep) {
    setSelectedRep(resolvedRep)
  }

  // Pre-populate cart + client + rep when editing an existing order.
  // BUG-02 (Bloco 88): refetches em background do React Query trocam a identidade
  // de editOrder e re-disparavam este efeito, sobrescrevendo edições em andamento
  // do carrinho — o estado garante que cada pedido só popule o formulário uma vez.
  const [loadedEditOrderId, setLoadedEditOrderId] = useState<string | null>(null)
  if (!editId && loadedEditOrderId !== null) setLoadedEditOrderId(null)
  if (editOrder && resolvedProductQuery.isSuccess && resolvedClient) {
    if (!editOrder.rep_id || resolvedRep) {
      if (loadedEditOrderId !== editOrder.id) {
        setLoadedEditOrderId(editOrder.id)
        const productMap = new Map(
          resolvedProducts.map((product) => [product.product_code, product]),
        )
        const cartItems: CartItem[] = editOrder.items
          .map(item => {
            const product = productMap.get(item.product_code)
            if (!product) return null
            return {
              product_code: item.product_code,
              line_id: item.id,
              qty: item.qty,
              sold_by_area: item.sold_by_area ?? isAreaProduct(product),
              area_width_m: item.area_width_m == null ? null : Number(item.area_width_m),
              area_depth_m: item.area_depth_m == null ? null : Number(item.area_depth_m),
              area_pieces: Number(item.area_pieces ?? 1),
              discount: Number(item.discount),
              opt_categories: item.opt_categories,
              optional_choices: (item.optional_choices ?? []).filter(choice => choice.application_id && (choice.optional_id || isCustomChoice(choice))).map(choice => isCustomChoice(choice)
                ? { application_id: choice.application_id!, custom_text: choice.custom_text }
                : { application_id: choice.application_id!, optional_id: choice.optional_id! }),
              source_order_item_id: item.id,
              preserve_optional_choices: true,
              saved_choices: item.optional_choices ?? [],
              comment: item.comment ?? undefined,
              _product: product,
            }
          })
          .filter(Boolean) as CartItem[]
        setCart(cartItems)
        setSelectedClient(resolvedClient)
        setSelectedRep(editOrder.rep_id ? resolvedRep ?? null : null)
        setNotes(editOrder.notes ?? '')
        setCartHydrated(true)
      }
    }
  }

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (productRef.current && !productRef.current.contains(e.target as Node)) setProductOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filteredProducts = products.filter((p) =>
    `${p.product_code} ${p.description}`.toLowerCase().includes(productQuery.toLowerCase())
  )

  function updateOptCategory(lineId: string, cat: string, value: string | null) {
    setCart(prev => prev.map(i => {
      if (i.line_id !== lineId) return i
      const updated = { ...i.opt_categories }
      if (!value) delete updated[cat]
      else updated[cat] = value
      return { ...i, opt_categories: updated, preserve_optional_choices: false }
    }))
  }

  function updateApplicationChoice(lineId: string, applicationId: string, choice: OptionalChoiceInput | null) {
    setCart(previous => previous.map(item => item.line_id !== lineId ? item : {
      ...item,
      preserve_optional_choices: false,
      optional_choices: [
        ...item.optional_choices.filter(candidate => candidate.application_id !== applicationId),
        ...(choice ? [choice] : []),
      ],
    }))
  }

  function editApplications(lineId: string) {
    setCart(previous => previous.map(item => item.line_id === lineId ? { ...item, preserve_optional_choices: false } : item))
  }

  function handleAddProductToCart() {
    if (!cartHydrated || !selectedProduct) return
    const errors = validateApplicationChoices(selectedProduct, selectedChoices, allOptionals)
    if (errors.length) { setToast({ message: errors[0], variant: 'error' }); return }
    const auto_categories = initialLegacyOptionCategories(selectedProduct)
    const areaProduct = isAreaProduct(selectedProduct)
    setCart((prev) => {
      const signature = JSON.stringify({ legacy: auto_categories, choices: [...selectedChoices].sort((a, b) => a.application_id.localeCompare(b.application_id)) })
      const existing = prev.find((i) => i.product_code === selectedProduct.product_code && i.discount === 0 &&
        JSON.stringify({ legacy: i.opt_categories, choices: [...i.optional_choices].sort((a, b) => a.application_id.localeCompare(b.application_id)) }) === signature)
      if (existing && !areaProduct) {
        return prev.map((i) => i.line_id === existing.line_id ? { ...i, qty: i.qty + 1 } : i)
      }
      return [...prev, {
        line_id: crypto.randomUUID(),
        product_code: selectedProduct.product_code,
        qty: 1,
        sold_by_area: areaProduct,
        ...(areaProduct ? { area_width_m: null, area_depth_m: null, area_pieces: 1 } : {}),
        discount: 0,
        opt_categories: auto_categories,
        optional_choices: selectedChoices,
        _product: selectedProduct,
      }]
    })
    setSelectedProduct(null)
    setSelectedChoices([])
    setProductQuery('')
  }

  function updateQty(lineId: string, qty: number) {
    const item = cart.find((candidate) => candidate.line_id === lineId)
    if (!item || !Number.isFinite(qty)) return
    const soldByArea = isAreaProduct(item._product)
    const maximumArea = areaLimit(item._product)
    if (soldByArea && qty < 0.01) return
    if (!soldByArea && qty < 1) return

    const overLimit = soldByArea && maximumArea !== null && qty > maximumArea
    const normalized = soldByArea
      ? Math.min(maximumArea ?? Number.POSITIVE_INFINITY, normalizeAreaQty(qty))
      : Math.max(1, Math.round(qty))
    setQtyLimitWarnings((current) => {
      const next = new Set(current)
      if (overLimit) next.add(lineId)
      else next.delete(lineId)
      return next
    })
    setCart((prev) => prev.map((candidate) => candidate.line_id === lineId ? { ...candidate, qty: normalized, sold_by_area: soldByArea } : candidate))
  }

  function updateAreaDimensions(lineId: string, width: number | null, depth: number | null) {
    const item = cart.find((candidate) => candidate.line_id === lineId)
    if (!item) return

    const nextWidth = width != null && width > 0 ? width : null
    const nextDepth = depth != null && depth > 0 ? depth : null
    const area = previewArea(nextWidth, nextDepth)
    const nextQty = area != null ? normalizeAreaQty(area * (item.area_pieces ?? 1)) : item.qty
    const maximumArea = areaLimit(item._product)
    const overLimit = area != null && maximumArea !== null && area > maximumArea

    setQtyLimitWarnings((current) => {
      const next = new Set(current)
      if (overLimit) next.add(lineId)
      else next.delete(lineId)
      return next
    })
    setCart((previous) => previous.map((candidate) => candidate.line_id === lineId ? {
      ...candidate,
      area_width_m: nextWidth,
      area_depth_m: nextDepth,
      qty: nextQty,
      sold_by_area: true,
    } : candidate))
  }

  function updateAreaPieces(lineId: string, value: number) {
    const item = cart.find((candidate) => candidate.line_id === lineId)
    if (!item) return
    const pieces = normalizeRugPieces(value)
    const currentPieces = item.area_pieces ?? 1
    const areaPerPiece = previewArea(item.area_width_m, item.area_depth_m)
      ?? normalizeAreaQty(item.qty / currentPieces)
    setCart((previous) => previous.map((candidate) => candidate.line_id === lineId ? {
      ...candidate,
      area_pieces: pieces,
      qty: normalizeAreaQty(areaPerPiece * pieces),
    } : candidate))
  }

  // Desconto por item — mesmo caminho para tabela desktop e cartão mobile. O
  // chamador já limita ao teto do usuário; o servidor revalida no envio.
  function updateDiscount(lineId: string, discount: number) {
    setCart((prev) => prev.map((i) => i.line_id === lineId ? { ...i, discount } : i))
  }

  function updateComment(lineId: string, comment: string | undefined) {
    setCart(previous => previous.map(item => item.line_id === lineId ? { ...item, comment } : item))
  }

  function toggleComment(lineId: string) {
    const current = cart.find(item => item.line_id === lineId)?.comment
    if (current === undefined) updateComment(lineId, '')
    else if (!current.trim()) updateComment(lineId, undefined)
  }

  function removeItem(lineId: string) {
    setCart((prev) => prev.filter((i) => i.line_id !== lineId))
    setQtyLimitWarnings((current) => {
      const next = new Set(current)
      next.delete(lineId)
      return next
    })
  }

  const filteredCart = cart.filter((item) =>
    `${item.product_code} ${item._product.description}`.toLowerCase().includes(cartFilter.toLowerCase())
  )

  const { data: productTypes = [] } = useProductTypes()

  const total = cart.reduce((sum, i) => {
    return sum + i.qty * effectivePrice(i._product, priceProfile) * (1 - (i.discount || 0) / 100)
  }, 0)

  // Brasil: IPI do grupo do tipo. Portugal: IVA aprovado do próprio produto,
  // o mesmo que o servidor grava no pedido (o grupo EU tem IPI 0).
  const taxRate = (product: Product) => product.market_code === 'EU'
    ? Number(product.vat_rate ?? 0)
    : Number(productTypes.find(t => t.name === product.type)?.group?.ipi ?? 0)

  const ipiTotal = cart.reduce((sum, i) => {
    const rate = taxRate(i._product)
    const subtotal = i.qty * effectivePrice(i._product, priceProfile) * (1 - (i.discount || 0) / 100)
    return sum + subtotal * rate / 100
  }, 0)

  const totalWithIpi = total + ipiTotal
  const cartUnitCount = cart.reduce((sum, item) => sum + (isAreaProduct(item._product) ? (item.area_pieces ?? 1) : item.qty), 0)

  // O código definitivo é atribuído atomicamente pelo PostgreSQL ao salvar.
  // Não é possível prevê-lo por contagem sem criar colisões em uso concorrente.
  const budgetCode = isEnglish ? 'Assigned on save' : 'Gerado ao salvar'

  const itemsPayload = cart.map((item) => {
    const { product_code, qty, discount, opt_categories, optional_choices, source_order_item_id, preserve_optional_choices, comment, _product } = item
    const areaProduct = isAreaProduct(_product)
    const width = item.area_width_m
    const depth = item.area_depth_m
    const base = {
      product_code,
      discount: discount || 0,
      opt_categories: opt_categories as Record<string, string>,
      optional_choices,
      source_order_item_id,
      preserve_optional_choices,
      comment: comment?.trim() || null,
    }
    // Tapete com medidas não manda qty: o servidor calcula L × P × peças.
    if (areaProduct && width != null && depth != null) {
      return { ...base, area_width_m: width, area_depth_m: depth, area_pieces: normalizeRugPieces(item.area_pieces ?? 1) }
    }
    if (areaProduct) {
      return { ...base, qty: normalizeAreaQty(qty), area_pieces: normalizeRugPieces(item.area_pieces ?? 1) }
    }
    return { ...base, qty: Math.max(1, Math.round(qty)) }
  })
  const repIdForSubmit = editId
    ? selectedRep?.id ?? null
    : selectedRep?.id ?? (targetRepId || null)

  async function handleSubmit() {
    if (!cartHydrated || !selectedClient || cart.length === 0) return
    const error = cart.filter(item => !item.preserve_optional_choices).flatMap(item => validateApplicationChoices(item._product, item.optional_choices, allOptionals))[0]
    if (error) { setToast({ message: error, variant: 'error' }); return }
    const missingAreaDimensions = cart.some(item => isAreaProduct(item._product) && !item.source_order_item_id && (item.area_width_m == null || item.area_depth_m == null))
    if (missingAreaDimensions) {
      setToast({
        message: isEnglish ? 'Enter width × depth for every rug.' : 'Informe largura × profundidade de todos os tapetes.',
        variant: 'error',
      })
      return
    }
    setIsGenerating(true)
    try {
      if (editId) {
        await Promise.all([
          updateOrderM.mutateAsync({
            id: editId,
            data: {
              rep_id: repIdForSubmit,
              price_list_code: market === 'EU' ? priceProfile : undefined,
              notes: notes || null,
              items: itemsPayload,
            },
          }),
          new Promise<void>((r) => setTimeout(r, 1500)),
        ])
        setToast({ message: isEnglish ? 'Order updated successfully!' : 'Pedido atualizado com sucesso!', variant: 'success' })
        setSearchParams({})
      } else {
        await Promise.all([
          createOrderM.mutateAsync({
            client_id: selectedClient.id,
            rep_id: repIdForSubmit,
            price_list_code: market === 'EU' ? priceProfile : undefined,
            notes: notes || null,
            items: itemsPayload,
            locale: market === 'EU' ? europeanLocale : undefined,
          }),
          new Promise<void>((r) => setTimeout(r, 3000)),
        ])
        setToast({ message: isEnglish ? 'Quote finalised successfully!' : 'Orçamento finalizado com sucesso!', variant: 'success' })
      }
      setCart([])
      localStorage.removeItem(cartKey)
      clearDraftPriceList()
      notifyCartChanged()
      resetSavedSelections()
      setNotes('')
      setDrawerOpen(false)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setToast({ message: detail ?? (isEnglish ? 'Error processing the order. Please try again.' : 'Erro ao processar o pedido. Tente novamente.'), variant: 'error' })
    } finally {
      setIsGenerating(false)
    }
  }

  // Product search card (shared between desktop and a potential mobile add section)
  const productSearchCard = (
    <div className="bg-surface-warm border border-line-warm rounded-xl p-4 space-y-3.5">
      <span className="type-label text-gold block">{isEnglish ? 'Add Product' : 'Adicionar Produto'}</span>
      {!cartHydrated && (
        <div className="rounded-lg border border-line-warm bg-white px-3 py-2 text-xs text-muted">
          {editId && editOrderQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>{isEnglish ? 'Could not load the order for editing.' : 'Não foi possível carregar o pedido para edição.'}</span>
              <button
                type="button"
                onClick={() => void editOrderQuery.refetch()}
                className="min-h-11 lg:min-h-0 shrink-0 font-semibold text-gold hover:underline"
              >
                {isEnglish ? 'Try again' : 'Tentar novamente'}
              </button>
            </div>
          ) : editId && resolvedClientQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>{isEnglish ? "Could not load this order's client." : 'Não foi possível carregar o cliente deste pedido.'}</span>
              <button
                type="button"
                onClick={() => void resolvedClientQuery.refetch()}
                className="min-h-11 lg:min-h-0 shrink-0 font-semibold text-gold hover:underline"
              >
                {isEnglish ? 'Try again' : 'Tentar novamente'}
              </button>
            </div>
          ) : editId && resolvedRepQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>{isEnglish ? "Could not load this order's representative." : 'Não foi possível carregar o representante deste pedido.'}</span>
              <button
                type="button"
                onClick={() => void resolvedRepQuery.refetch()}
                className="min-h-11 lg:min-h-0 shrink-0 font-semibold text-gold hover:underline"
              >
                {isEnglish ? 'Try again' : 'Tentar novamente'}
              </button>
            </div>
          ) : resolvedProductQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>{isEnglish ? 'Could not restore the products. The saved cart was kept.' : 'Não foi possível restaurar os produtos. O carrinho salvo foi preservado.'}</span>
              <button
                type="button"
                onClick={() => void resolvedProductQuery.refetch()}
                className="min-h-11 lg:min-h-0 shrink-0 font-semibold text-gold hover:underline"
              >
                {isEnglish ? 'Try again' : 'Tentar novamente'}
              </button>
            </div>
          ) : (
            <span>{isEnglish ? 'Restoring quote products…' : 'Restaurando produtos do orçamento…'}</span>
          )}
        </div>
      )}
      <div ref={productRef} className="relative">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
          <input
            aria-label={isEnglish ? 'Search for a product to add to the quote' : 'Buscar produto para adicionar ao orçamento'}
            className="input pl-8 w-full text-xs bg-white border border-line rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gold"
            placeholder={isEnglish ? 'Search product by code or description' : 'Buscar produto por codigo ou desc'}
            value={productQuery}
            disabled={!cartHydrated}
            onChange={(e) => { setProductQuery(e.target.value); setProductOpen(true) }}
            onFocus={() => { if (cartHydrated) setProductOpen(true) }}
          />
        </div>
        {cartHydrated && productOpen && (
          <ul className="absolute left-0 right-0 z-30 mt-1 bg-white border border-line rounded-xl overflow-hidden shadow-xl max-h-52 overflow-y-auto">
            {productSearch.isFetching && (
              <li className="px-3 py-2 text-xs text-muted">{isEnglish ? 'Searching…' : 'Buscando…'}</li>
            )}
            {filteredProducts.slice(0, 15).map((p) => (
              <li
                key={p.id}
                className="min-h-11 lg:min-h-0 px-3 py-2 text-xs hover:bg-bg cursor-pointer flex items-center gap-2 transition-colors border-b border-surface-2"
                onMouseDown={() => { setSelectedProduct(p); setSelectedChoices([]); setProductQuery(''); setProductOpen(false) }}
              >
                {p.photo_url
                  ? <img src={p.thumbnail_url ?? p.photo_url} alt="" loading="lazy" decoding="async" className="w-8 h-8 rounded object-cover border border-line flex-shrink-0" />
                  : <ImageIcon className="w-8 h-8 text-faint flex-shrink-0" />}
                <div className="truncate">
                  <span className="text-gold font-mono font-medium">{p.product_code}</span>
                  <span className="text-ink ml-1.5 font-medium">{p.description}</span>
                  {dimLabel(p, market, locale) && <div className="type-meta font-mono mt-0.5">{dimLabel(p, market, locale)}</div>}
                </div>
              </li>
            ))}
            {!productSearch.isFetching && filteredProducts.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted">
                {isEnglish ? 'No products found.' : 'Nenhum produto encontrado.'}
              </li>
            )}
          </ul>
        )}
      </div>
      {selectedProduct && (
        <div className="bg-white border border-line-warm rounded-lg p-2.5 flex gap-2.5 shadow-sm relative">
          <button type="button" onClick={() => setSelectedProduct(null)}
            className="absolute top-0 right-0 text-muted hover:text-danger transition-colors w-11 h-11 lg:top-1.5 lg:right-1.5 lg:w-7 lg:h-7 flex items-center justify-center">
            <X className="w-3.5 h-3.5" />
          </button>
          {selectedProduct.photo_url
            ? <button type="button" onClick={() => setActivePhotoModal(selectedProduct.photo_url!)} className="w-12 h-12 rounded flex-shrink-0" aria-label={isEnglish ? `Enlarge photo of ${selectedProduct.description}` : `Ampliar foto de ${selectedProduct.description}`}>
                <img src={selectedProduct.thumbnail_url ?? selectedProduct.photo_url} alt="" decoding="async" className="w-full h-full object-cover rounded border border-line hover:opacity-80 transition-opacity" />
              </button>
            : <div className="w-12 h-12 bg-bg-2 rounded flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-faint" /></div>
          }
          <div className="text-[11px] pr-5 flex-1 min-w-0">
            <p className="text-gold font-mono font-semibold">{selectedProduct.product_code}</p>
            <p className="text-ink font-medium truncate">{selectedProduct.description}</p>
            <p className="text-gold font-bold mt-0.5"><SafePrice value={effectivePrice(selectedProduct, priceProfile)} currency={currency} locale={locale} /></p>
          </div>
        </div>
      )}
      {selectedProduct && <ApplicationSelectors
        product={selectedProduct} choices={selectedChoices} allOptionals={allOptionals} english={isEnglish}
        allowCustom={allowsCustomOption(market) && optionalsReady}
        onPreview={photoUrl => setActivePhotoModal(photoUrl)}
        onChange={(applicationId, choice) => setSelectedChoices(previous => [
          ...previous.filter(candidate => candidate.application_id !== applicationId),
          ...(choice ? [choice] : []),
        ])}
      />}
      <button
        type="button"
        onClick={handleAddProductToCart}
        disabled={!cartHydrated || !selectedProduct}
        style={{ touchAction: 'manipulation' }}
        className="w-full min-h-11 lg:min-h-0 py-2.5 rounded-lg text-xs font-semibold tracking-wider text-white transition-all bg-gold hover:bg-gold-600 active:bg-gold-700 disabled:bg-faint disabled:cursor-not-allowed flex items-center justify-center gap-1.5 shadow-sm active:scale-[0.98]"
      >
        {isEnglish ? 'ADD TO QUOTE' : 'ADICIONAR AO ORÇAMENTO'}
      </button>
    </div>
  )

  return (
    <div className="min-h-screen bg-bg text-ink">
      <h1 className="sr-only">{isEnglish ? 'New Quote' : 'Novo Orçamento'}</h1>
      {editId && editOrder && (
        <div className="bg-gold text-white px-4 lg:px-8 py-2.5 flex items-center gap-2.5">
          <PenLine className="w-4 h-4 flex-shrink-0" />
          <span className="text-xs font-semibold tracking-wide">
            {isEnglish ? 'Editing Order: ' : 'Editando Pedido: '}<span className="font-mono">{editOrder.code}</span>
          </span>
          <button
            onClick={() => {
              setSearchParams({})
              setCart([])
              setCartHydrated(true)
              resetSavedSelections()
              setNotes('')
              localStorage.removeItem(cartKey)
              clearDraftPriceList()
              notifyCartChanged()
            }}
            className="ml-auto min-h-11 lg:min-h-0 px-2 text-white/70 hover:text-white text-xs underline"
          >
            {isEnglish ? 'Cancel editing' : 'Cancelar edição'}
          </button>
        </div>
      )}
      <div className="max-w-[1600px] mx-auto px-4 lg:px-8 py-4 lg:py-6 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_360px] gap-6 pb-28 lg:pb-6">

        {/* ── Mobile: product search card ────────────────────────────────── */}
        <div className="lg:hidden">{productSearchCard}</div>

        {/* ── Items Panel ──────────────────────────────────────────────────── */}
        <section ref={itemsSectionRef} tabIndex={-1} aria-labelledby="budget-items-title" className="bg-white border border-line rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[400px] lg:min-h-[550px] focus:outline-none">
          <div className="px-4 lg:px-6 py-3.5 lg:py-4 border-b border-line flex flex-col gap-3 bg-white flex-shrink-0 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
              <h2 id="budget-items-title" className="text-sm font-semibold text-gold uppercase tracking-wider flex items-center gap-2">
                <ShoppingCart className="w-4 h-4" /> {isEnglish ? 'Quote Items' : 'Itens do Orçamento'}
              </h2>
              {market === 'EU' && lockedEuPriceList ? (
                <output
                  aria-live="polite"
                  aria-label={isEnglish ? `Client price list: ${priceProfileLabel}` : `Tabela do cliente: ${priceProfileLabel}`}
                  title={isEnglish ? 'Set by the client record' : 'Definida no cadastro do cliente'}
                  className="inline-flex min-h-8 items-center overflow-hidden rounded-lg border border-line bg-surface-2 text-[10px] uppercase tracking-wider"
                >
                  <span className="px-2.5 text-muted inline-flex items-center gap-1">
                    <Lock className="w-3 h-3" aria-hidden="true" />
                    {isEnglish ? 'Client price list' : 'Tabela do cliente'}
                  </span>
                  <strong className="self-stretch border-l border-line bg-white px-2.5 inline-flex items-center font-semibold text-gold">
                    {priceProfileLabel}
                  </strong>
                </output>
              ) : market === 'EU' ? (
                <label className="inline-flex min-h-8 items-center overflow-hidden rounded-lg border border-line bg-surface-2 text-[10px] uppercase tracking-wider">
                  <span className="px-2.5 text-muted">{isEnglish ? 'Price list' : 'Tabela de preço'}</span>
                  <select
                    aria-label={isEnglish ? 'Quote price list' : 'Tabela de preço do orçamento'}
                    value={priceProfile}
                    onChange={(event) => selectEuPriceList(event.target.value as PriceListCode)}
                    className="self-stretch border-0 border-l border-line bg-white px-2.5 font-semibold text-gold outline-none"
                  >
                    {/* A API omite o preço das tabelas que a conta não vê; só
                        oferece as que os itens trazem (e a já escolhida). */}
                    {(['lojista', 'arquiteto', 'corporativo', 'pvp'] as const)
                      .filter(code => code === priceProfile || cart.length === 0
                        || cart.some(item => item._product.market_prices?.[code] != null))
                      .map(code => (
                        <option key={code} value={code}>
                          {{ lojista: 'Lojista', arquiteto: 'Arquiteto', corporativo: 'Corporativo', pvp: 'PVP' }[code]}
                        </option>
                      ))}
                  </select>
                </label>
              ) : (
                <output
                  aria-live="polite"
                  aria-label={isEnglish ? `Price checked: ${priceProfileLabel}` : `Preço consultado: ${priceProfileLabel}`}
                  className="inline-flex min-h-8 items-center overflow-hidden rounded-lg border border-line bg-surface-2 text-[10px] uppercase tracking-wider"
                >
                  <span className="px-2.5 text-muted">{isEnglish ? 'Price checked' : 'Preço consultado'}</span>
                  <strong className="self-stretch border-l border-line bg-white px-2.5 inline-flex items-center font-semibold text-gold">
                    {priceProfileLabel}
                  </strong>
                </output>
              )}
            </div>
            <div className="flex items-center gap-2">
              {cart.length > 0 && (
                <button
                  onClick={() => { setCart([]); localStorage.removeItem(cartKey); clearDraftPriceList(); notifyCartChanged() }}
                  className="min-h-11 lg:min-h-0 text-xs text-terracotta hover:text-terracotta-700 border border-terracotta-soft hover:border-terracotta px-2.5 py-1.5 rounded-lg transition-colors"
                  style={{ touchAction: 'manipulation' }}
                >
                  {isEnglish ? 'Clear' : 'Limpar'}
                </button>
              )}
              <div className="relative w-36 lg:w-52">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
                  <input
                    className="input pl-8 w-full text-xs border border-line rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-gold bg-white"
                    aria-label={isEnglish ? 'Search quote items' : 'Buscar nos itens do orçamento'}
                    placeholder={isEnglish ? 'Search items...' : 'Buscar itens...'}
                  value={cartFilter}
                  onChange={(e) => setCartFilter(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* A lista desktop reorganiza a faixa numérica em vez de criar
              rolagem horizontal nas larguras entre 1024 e 1180px. */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden">
            {filteredCart.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-muted space-y-3">
                <Clipboard className="w-10 h-10 text-faint stroke-[1.2]" />
                <p className="text-sm font-medium text-ink-3">
                  {cart.length === 0 ? (isEnglish ? 'Your quote is empty.' : 'Seu orçamento ainda está vazio.') : (isEnglish ? 'No items match your search.' : 'Nenhum item corresponde à busca.')}
                </p>
                {cart.length === 0 ? (
                  <Link to="/produtos" className="btn-secondary min-h-11 px-4 inline-flex items-center justify-center text-xs">
                    {isEnglish ? 'Choose products' : 'Escolher produtos'}
                  </Link>
                ) : (
                  <button type="button" onClick={() => setCartFilter('')} className="btn-secondary min-h-11 px-4 text-xs">
                    {isEnglish ? 'Clear search' : 'Limpar busca'}
                  </button>
                )}
              </div>
            ) : (
              <>
                {/* ── Mobile cards ─────────────────────────────── */}
                <div className="flex flex-col gap-3 p-3 lg:hidden">
                  {filteredCart.map((item) => (
                    <MobileCartCard
                      key={item.line_id}
                      item={item}
                      onQtyChange={updateQty}
                      onAreaDimensionsChange={updateAreaDimensions}
                      onAreaPiecesChange={updateAreaPieces}
                      qtyLimitWarning={qtyLimitWarnings.has(item.line_id)}
                      onDiscountChange={updateDiscount}
                      maxDiscount={maxDiscount}
                      onRemove={removeItem}
                      onPhotoClick={setActivePhotoModal}
                      onPreview={photoUrl => setActivePhotoModal(photoUrl)}
                      allOptionals={allOptionals}
                      optionalsReady={optionalsReady}
                      onOptChange={(cat, val) => updateOptCategory(item.line_id, cat, val)}
                      onApplicationChange={(appId, choice) => updateApplicationChoice(item.line_id, appId, choice)}
                      onEditApplications={() => editApplications(item.line_id)}
                      onToggleComment={() => toggleComment(item.line_id)}
                      onCommentChange={comment => updateComment(item.line_id, comment)}
                      priceProfile={priceProfile}
                      catLabel={catLabel}
                      currency={currency}
                      locale={locale}
                    />
                  ))}
                </div>

                {/* ── Desktop item list ────────────────────────── */}
                <ul className="hidden lg:block divide-y divide-line">
                  {filteredCart.map((item) => {
                    const ipiRate = taxRate(item._product)
                    const subtotal = item.qty * effectivePrice(item._product, priceProfile) * (1 - (item.discount || 0) / 100)
                    // Brasil: IPI entra na linha. Portugal: IVA só no fecho
                    // (Subtotal → IVA → Total), como numa fatura.
                    const lineTotal = market === 'EU' ? subtotal : subtotal * (1 + ipiRate / 100)
                    const soldByArea = isAreaProduct(item._product)
                    return (
                      <li
                        key={item.line_id}
                        aria-label={`${item.product_code} ${item._product.description}`}
                        className="grid gap-4 px-4 lg:px-6 py-4 hover:bg-surface-2 transition-colors xl:grid-cols-[minmax(0,1fr)_auto]"
                      >
                        <div className="flex min-w-0 gap-3">
                          {item._product.photo_url
                            ? <button type="button" onClick={() => setActivePhotoModal(item._product.photo_url!)} className="w-12 h-12 min-w-12 rounded-lg" aria-label={isEnglish ? `Enlarge photo of ${item._product.description}` : `Ampliar foto de ${item._product.description}`}>
                                <img src={item._product.thumbnail_url ?? item._product.photo_url} alt="" loading="lazy" decoding="async" className="w-full h-full object-cover rounded-lg border border-line hover:opacity-80 transition-opacity" />
                              </button>
                            : <div className="bg-bg-2 rounded-lg flex items-center justify-center"
                                style={{ width: '48px', height: '48px', minWidth: '48px', minHeight: '48px' }}>
                                <ImageIcon className="w-5 h-5 text-faint" />
                              </div>
                          }
                          <div className="flex-1 min-w-0">
                            <span className="type-code">{item.product_code}</span>
                            <span className="text-ink ml-2 text-sm font-medium leading-snug break-words">{item._product.description}</span>
                            {!item.preserve_optional_choices && <div><ApplicationStatus product={item._product} choices={item.optional_choices} allOptionals={allOptionals} english={isEnglish} /></div>}
                            {item._product.components.length > 0 && (
                              <ul className="mt-0.5 space-y-0.5">
                                {item._product.components.map((comp) => (
                                  <li key={comp.id} className="text-[11px] text-ink-3 leading-snug">
                                    • {comp.qty}x {comp.description} ({formatDimensions(comp, market, locale)})
                                    {comp.optionals.length > 0 && (
                                      <span className="block text-muted pl-2.5 break-words">{compFinishes(comp.optionals, catLabel, locale === 'en-GB')}</span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            )}
                            {item._product.observacao && (
                              <div className="text-[11px] leading-snug text-gold italic mt-1">{item._product.observacao}</div>
                            )}
                            {dimLabel(item._product, market, locale) && (
                              <div className="type-meta font-mono mt-1">{dimLabel(item._product, market, locale)}</div>
                            )}
                            {soldByArea && <div className="mt-2"><RugMeasureFields item={item} english={isEnglish} locale={locale} qtyLimitWarning={qtyLimitWarnings.has(item.line_id)} onAreaDimensionsChange={updateAreaDimensions} /></div>}
                            <OptionalSelectors item={item} allOptionals={allOptionals} onChange={(cat, val) => updateOptCategory(item.line_id, cat, val)} onPreview={photoUrl => setActivePhotoModal(photoUrl)} catLabel={catLabel} allowCustom={allowsCustomOption(market) && optionalsReady} />
                            {item.preserve_optional_choices && <div className="mt-2 text-xs text-ink-2">
                              {(item.saved_choices ?? []).map(choice => <p key={choice.id} className="break-words">{formatChoice(choice, isEnglish)}</p>)}
                              <button type="button" className="text-gold underline mt-1" onClick={() => editApplications(item.line_id)}>{isEnglish ? 'Change optional applications' : 'Alterar aplicações do opcional'}</button>
                            </div>}
                            {!item.preserve_optional_choices && <ApplicationSelectors product={item._product} choices={item.optional_choices} allOptionals={allOptionals} onChange={(appId, choice) => updateApplicationChoice(item.line_id, appId, choice)} onPreview={photoUrl => setActivePhotoModal(photoUrl)} english={isEnglish} allowCustom={allowsCustomOption(market) && optionalsReady} />}
                            <ItemCommentBox comment={item.comment} english={isEnglish} onChange={comment => updateComment(item.line_id, comment)} />
                          </div>
                        </div>

                        {/* Em 2xl qtd, preços, subtotal, comentário e excluir cabem numa linha (~540px). */}
                        <div className="flex flex-wrap content-start items-start gap-x-5 gap-y-2 xl:justify-end xl:max-w-[440px] 2xl:max-w-[600px]">
                          <div>
                            <label className="type-label text-xs block mb-1" htmlFor={`desktop-qty-${item.line_id}`}>{isEnglish ? 'Qty' : 'Qtd'}</label>
                            <QuantityInput
                              id={`desktop-qty-${item.line_id}`}
                              value={soldByArea ? (item.area_pieces ?? 1) : item.qty}
                              allowDecimal={false}
                              max={soldByArea ? 1000 : null}
                              ariaLabel={soldByArea ? (isEnglish ? `Number of pieces — ${item._product.description}` : `Número de peças — ${item._product.description}`) : (isEnglish ? `Qty — ${item._product.description}` : `Qtd — ${item._product.description}`)}
                              className="input w-20 text-center text-xs border border-line rounded-lg py-1 bg-white text-ink"
                              onCommit={(qty) => soldByArea ? updateAreaPieces(item.line_id, qty) : updateQty(item.line_id, qty)}
                            />
                          </div>
                          <div>
                            <span className="type-label text-xs block mb-1 whitespace-nowrap">{isEnglish ? 'Base Price' : 'Preço base'}</span>
                            <div className="text-ink-2 text-xs font-semibold whitespace-nowrap min-h-8 flex items-center">
                              <SafePrice value={effectivePrice(item._product, priceProfile)} currency={currency} locale={locale} />
                              {soldByArea && <span className="ml-0.5 font-normal text-muted">/m²</span>}
                            </div>
                          </div>
                          <div>
                            <span className="type-label text-xs block mb-1 whitespace-nowrap">{isEnglish ? 'Discount (%)' : 'Desconto (%)'}</span>
                            <NumberField
                              min={0} max={maxDiscount}
                              aria-label={isEnglish ? `Discount on ${item._product.description}` : `Desconto em ${item._product.description}`}
                              className="input w-16 text-center text-xs border border-line rounded-lg px-1.5 py-1 bg-white text-ink"
                              value={item.discount}
                              placeholder="0"
                              disabled={maxDiscount <= 0}
                              onValueChange={(v) => updateDiscount(item.line_id, Math.min(maxDiscount, Math.max(0, v)))}
                            />
                            {item.discount > 0 && (
                              <p className="text-[9px] text-muted mt-0.5 text-center whitespace-nowrap">
                                <span>− </span><SafePrice value={effectivePrice(item._product, priceProfile) * item.discount / 100} currency={currency} locale={locale} />
                              </p>
                            )}
                          </div>
                          {market === 'BR' && (
                            <div>
                              <span className="type-label text-xs block mb-1 whitespace-nowrap">IPI</span>
                              <div className="min-h-8 flex items-center whitespace-nowrap">
                                {ipiRate > 0
                                  ? <span className="text-xs font-semibold text-gold">{ipiRate}%</span>
                                  : <span className="text-xs text-muted">—</span>
                                }
                              </div>
                            </div>
                          )}
                          <div className="flex items-end gap-2">
                            <div>
                              <span className="type-label text-xs block mb-1 whitespace-nowrap">Subtotal</span>
                              <div className="min-h-11 flex items-center text-xs font-bold text-ink tabular-nums whitespace-nowrap">
                                <SafePrice value={lineTotal} currency={currency} locale={locale} />
                              </div>
                            </div>
                            <ItemCommentToggle comment={item.comment} label={item._product.description} english={isEnglish} onToggle={() => toggleComment(item.line_id)} />
                            <button onClick={() => removeItem(item.line_id)} className="text-muted hover:text-danger transition-colors w-11 h-11 flex items-center justify-center" aria-label={isEnglish ? `Remove ${item._product.description} from quote` : `Remover ${item._product.description} do orçamento`}>
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </>
            )}
          </div>

          {/* Desktop summary footer */}
          {cart.length > 0 && (
            <div className="hidden lg:flex bg-surface-2 border-t border-line px-6 py-4 justify-between items-center flex-shrink-0">
              <div className="flex gap-4 text-xs text-muted-2">
                <div><span>{isEnglish ? 'Items: ' : 'Itens: '}</span><span className="font-semibold text-ink">{cartUnitCount}</span></div>
                <div><span>{isEnglish ? 'Products: ' : 'Produtos: '}</span><span className="font-semibold text-ink">{cart.length}</span></div>
              </div>
              <div className="flex items-center gap-2">
                {market === 'EU' && ipiTotal > 0 && (
                  <div className="flex items-center gap-4 mr-4 text-xs text-muted-2">
                    <div><span>Subtotal: </span><span className="font-semibold text-ink tabular-nums"><SafePrice value={total} currency={currency} locale={locale} /></span></div>
                    <div><span>{taxLabel}: </span><span className="font-semibold text-ink tabular-nums"><SafePrice value={ipiTotal} currency={currency} locale={locale} /></span></div>
                  </div>
                )}
                <span className="text-ink font-semibold text-xs uppercase tracking-wider">{isEnglish ? 'Quote Total:' : 'Total do Orçamento:'}</span>
                <span className="text-gold font-bold text-base"><SafePrice value={totalWithIpi} currency={currency} locale={locale} /></span>
              </div>
            </div>
          )}
        </section>

        {/* ── Desktop Sidebar (hidden on mobile) ───────────────────────── */}
        <aside className="hidden lg:block space-y-5">
          <div className="bg-white border border-line rounded-xl p-5 shadow-sm space-y-4">
            <fieldset
              disabled={!!editId && !cartHydrated}
              className="m-0 min-w-0 border-0 p-0 disabled:opacity-60"
            >
              <OrderForm
                reps={reps} clients={clients}
                selectedRep={selectedRep} selectedClient={selectedClient} notes={notes}
                repQuery={repQuery} clientQuery={clientQuery}
                onRepChange={handleRepChange} onClientChange={handleClientChange} onNotesChange={setNotes}
                onRepSearch={setRepQuery} onClientSearch={setClientQuery}
                repsLoading={repSearch.isFetching} clientsLoading={clientSearch.isFetching}
                onQuickAddRep={() => setQuickModal('rep')} onQuickAddClient={() => setQuickModal('client')}
                budgetCode={budgetCode} cart={cart}
                onSubmit={handleSubmit} isGenerating={isGenerating}
                repLocked={repLocked} clientLocked={clientLocked}
                editMode={!!editId} editCode={editOrder?.code} isEnglish={isEnglish}
              />
            </fieldset>
            {productSearchCard}
          </div>
        </aside>
      </div>

      {/* ── Mobile fixed bottom bar ──────────────────────────────────────────
          Vai até `lg` porque a sidebar do formulário só aparece em 1024px: entre
          768 e 1023 esta barra é o ÚNICO acesso ao pedido. Já o `bottom-16`
          existe só para desviar do nav inferior, que é `md:hidden` — a partir de
          768px não há nav embaixo, e sem o `md:bottom-4` a barra ficaria
          flutuando sobre um vão vazio de 64px no tablet. */}
      <div className="lg:hidden fixed bottom-16 md:bottom-4 inset-x-0 z-sticky-nav px-4 pb-2">
        <button
          onClick={() => setDrawerOpen(true)}
          style={{ touchAction: 'manipulation' }}
          className="w-full flex items-center justify-between bg-gold text-white px-5 py-3.5 rounded-xl shadow-xl active:scale-[0.98] active:opacity-90 transition-all"
        >
          <div className="flex items-center gap-2">
            <ChevronUp className="w-4 h-4" />
            <span className="text-sm font-semibold">
              {cart.length > 0
                ? (isEnglish
                  ? `View Summary (${cartUnitCount} ${cartUnitCount === 1 ? 'item' : 'items'})`
                  : `Ver Resumo (${cartUnitCount} ${cartUnitCount === 1 ? 'item' : 'itens'})`)
                : (isEnglish ? 'Quote Settings' : 'Configurar Orçamento')}
            </span>
          </div>
          {cart.length > 0 && (
            <span className="text-sm font-bold"><SafePrice value={totalWithIpi} currency={currency} locale={locale} /></span>
          )}
        </button>
      </div>

      {/* ── Mobile bottom drawer ───────────────────────────────────────────── */}
      <BottomDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <fieldset
          disabled={!!editId && !cartHydrated}
          className="m-0 min-w-0 border-0 p-0 disabled:opacity-60"
        >
          <OrderForm
            reps={reps} clients={clients}
            selectedRep={selectedRep} selectedClient={selectedClient} notes={notes}
            repQuery={repQuery} clientQuery={clientQuery}
            onRepChange={handleRepChange} onClientChange={handleClientChange} onNotesChange={setNotes}
            onRepSearch={setRepQuery} onClientSearch={setClientQuery}
            repsLoading={repSearch.isFetching} clientsLoading={clientSearch.isFetching}
            onQuickAddRep={() => { setDrawerOpen(false); setQuickModal('rep') }}
            onQuickAddClient={() => { setDrawerOpen(false); setQuickModal('client') }}
            budgetCode={budgetCode} cart={cart}
            onSubmit={handleSubmit} isGenerating={isGenerating}
            repLocked={repLocked} clientLocked={clientLocked}
            editMode={!!editId} editCode={editOrder?.code} isEnglish={isEnglish}
          />
        </fieldset>
      </BottomDrawer>

      {quickModal === 'client' && (
        <QuickRegisterModal
          market={user?.active_market ?? 'BR'}
          title={isEnglish ? 'New Client' : 'Novo Cliente'}
          entityType="client"
          onSave={async (data) => { await createClientM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}
      {quickModal === 'rep' && !isRep && (
        <QuickRegisterModal
          market={user?.active_market ?? 'BR'}
          title={isEnglish ? 'New Representative' : 'Novo Representante'}
          entityType="rep"
          onSave={async (data) => { await createRepM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}

      {toast && <Toast message={toast.message} variant={toast.variant} onDone={() => setToast(null)} />}
      {activePhotoModal && <PhotoLightbox url={activePhotoModal} onClose={() => setActivePhotoModal(null)} />}

      {/* ── Overlay de Geração Premium ─────────────────────────────── */}
      {isGenerating && (
        <BrandLoadingOverlay
          wordmark={market === 'EU' ? 'IBTW' : 'ILYA'}
          label={isEnglish ? 'Generating Quote' : 'Gerando Orçamento'}
        />
      )}
    </div>
  )
}
