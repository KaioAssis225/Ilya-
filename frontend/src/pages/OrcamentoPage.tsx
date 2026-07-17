import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../lib/api'
import { Search, Plus, X, Trash2, ShoppingCart, CheckCircle, ImageIcon, Clipboard, Minus, ChevronUp, Lock, PenLine } from 'lucide-react'
import { useProductsByCodes, useProductsPage } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useClient, useClientsPage, useCreateClient } from '../hooks/useClients'
import { useRepresentative, useRepresentativesPage, useCreateRepresentative } from '../hooks/useRepresentatives'
import { useCreateOrder, useUpdateOrder, useOrder } from '../hooks/useOrders'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { useOptionalCategories } from '../hooks/useOptionalCategories'
import { SafePrice } from '../components/SafePrice'
import { useAuth } from '../hooks/useAuth'
import { isConjuntoType } from '../lib/productType'
import type { Product, Client, Representative, ClientCreate, OptionalColor } from '../types'

function fmtM(v: number) { return Number(v).toFixed(2).replace('.', ',') }

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
  catLabel: (code: string) => string
): string {
  const cats = Array.from(new Set(optionals.map(o => o.category)))
  return cats
    .map(cat => `${catLabel(cat)}: ${optionals.find(o => o.category === cat)!.color_name}`)
    .join(' · ')
}

function dimLabel(p: Product) {
  // Conjunto é o agrupador comercial; as medidas pertencem exclusivamente aos
  // componentes internos e não devem aparecer como 0 × 0 × 0 no item-pai.
  if (p.is_set || isConjuntoType(p.type) || p.components.length > 0) return null
  return p.is_circular
    ? `Ø ${fmtM(p.largura)} × A ${fmtM(p.altura)} m`
    : `L ${fmtM(p.largura)} × P ${fmtM(p.profundidade)} × A ${fmtM(p.altura)} m`
}

// ── Autocomplete ──────────────────────────────────────────────────────────────

function Autocomplete<T extends { id: string }>({
  searchPlaceholder, items, value, query, getLabel, getSearch, onChange, onClear, displayPlaceholder = "Nenhum", showQuickAdd, onQuickAdd, onQueryChange, isLoading = false
}: {
  searchPlaceholder: string; items: T[]; value: T | null; query: string
  getLabel: (item: T) => string; getSearch: (item: T) => string
  onChange: (item: T) => void; onClear: () => void; displayPlaceholder?: string
  showQuickAdd?: boolean; onQuickAdd?: () => void
  onQueryChange: (query: string) => void; isLoading?: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = items.filter((i) => getSearch(i).toLowerCase().includes(query.toLowerCase()))

  return (
    <div ref={ref} className="space-y-1 w-full">
      <div className="flex gap-2">
        <div className="input flex items-center justify-between bg-[#fcfbfa] border border-line px-3 py-1.5 rounded-lg text-sm flex-1 min-w-0 h-[36px]">
          <span className={`${value ? 'text-ink font-medium' : 'text-muted-3'} truncate flex-1 min-w-0`}>
            {value ? getLabel(value) : displayPlaceholder}
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
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        {showQuickAdd && onQuickAdd && (
          <button type="button" onClick={onQuickAdd} className="btn-secondary px-2.5 flex-shrink-0 h-[36px] border border-line hover:bg-bg rounded-lg transition-colors flex items-center justify-center min-w-[44px]">
            <Plus className="w-4 h-4 text-muted" />
          </button>
        )}
      </div>
      <div className="relative">
        <input
          className="input w-full text-xs placeholder:text-faint border border-line rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-gold bg-white"
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => {
            onQueryChange(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
        />
        {open && (isLoading || filtered.length > 0 || query.length > 0) && (
          <ul className="absolute z-30 w-full mt-1 bg-white border border-line rounded-xl overflow-hidden shadow-xl max-h-48 overflow-y-auto">
            {isLoading && (
              <li className="px-3 py-2 text-xs text-muted">Buscando…</li>
            )}
            {filtered.slice(0, 15).map((item) => (
              <li key={item.id} className="px-3 py-2 text-xs text-ink hover:bg-bg cursor-pointer transition-colors"
                onMouseDown={() => {
                  onChange(item)
                  onQueryChange('')
                  setOpen(false)
                }}>
                {getLabel(item)}
              </li>
            ))}
            {!isLoading && filtered.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted">Nenhum resultado.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Modal de cadastro rápido ──────────────────────────────────────────────────

const EMPTY_PERSON: ClientCreate = {
  name: '', phone: '', email: '',
  cep: '', numero: '', address: '', city: '', state: '',
}

function QuickRegisterModal({ title, onSave, onClose }: {
  title: string; onSave: (data: ClientCreate) => Promise<void>; onClose: () => void
}) {
  const [form, setForm] = useState<ClientCreate>(EMPTY_PERSON)
  const [saving, setSaving] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)
  const [cepError, setCepError] = useState(false)
  const cepAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => cepAbortRef.current?.abort(), [])

  async function handleCepBlur() {
    const clean = form.cep.replace(/\D/g, '')
    if (clean.length !== 8) return
    cepAbortRef.current?.abort()
    const controller = new AbortController()
    cepAbortRef.current = controller
    setCepLoading(true); setCepError(false)
    try {
      const { data } = await api.get(`/utils/cep/${clean}`, { signal: controller.signal })
      setForm((f) => ({
        ...f,
        address: `${data.logradouro}${data.bairro ? ', ' + data.bairro : ''}`,
        city: data.localidade,
        state: data.uf,
      }))
    } catch {
      // Requisição abortada (unmount / novo CEP) não é erro real (V-F2/M4).
      if (!controller.signal.aborted) setCepError(true)
    } finally {
      if (!controller.signal.aborted) setCepLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setSaving(true)
    try { await onSave(form); onClose() } finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel w-full max-w-lg p-6 mx-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-ink w-11 h-11 flex items-center justify-center" aria-label="Fechar"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs text-muted">Nome *</span>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">Telefone *</span>
            <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">E-mail *</span>
            <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1 relative">
            <span className="text-xs text-muted">CEP *</span>
            <input className="input" value={form.cep} onChange={(e) => setForm({ ...form, cep: e.target.value })} onBlur={handleCepBlur} maxLength={9} required />
            {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-gold animate-pulse">...</span>}
            {cepError && <span className="text-[10px] text-red-500">CEP não encontrado ou serviço indisponível.</span>}
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">Número</span>
            <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: e.target.value })} />
          </label>
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs text-muted">Endereço *</span>
            <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">Cidade *</span>
            <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">UF *</span>
            <input className="input" maxLength={2} value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value.toUpperCase() })} required />
          </label>
          <div className="col-span-2 flex justify-end gap-3 pt-1">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={saving}>Salvar</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Carrinho ──────────────────────────────────────────────────────────────────

interface CartItem {
  product_code: string
  qty: number
  discount: number
  opt_categories: Partial<Record<string, string>>
  _product: Product
}

type PersistedCartItem = Omit<CartItem, '_product'>
const EMPTY_PRODUCTS: Product[] = []

function readPersistedCart(): PersistedCartItem[] {
  try {
    const raw = localStorage.getItem('carrinho_orcamento')
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is PersistedCartItem =>
      !!item
      && typeof item.product_code === 'string'
      && Number.isFinite(Number(item.qty))
      && typeof item.opt_categories === 'object'
    )
  } catch {
    return []
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDone, variant = 'success' }: { message: string; onDone: () => void; variant?: 'success' | 'error' }) {
  useEffect(() => {
    const t = setTimeout(onDone, 4000)
    return () => clearTimeout(t)
  }, [onDone])
  return variant === 'error' ? (
    <div role="alert" aria-live="assertive" className="fixed bottom-24 lg:bottom-6 right-4 lg:right-6 z-50 flex items-center gap-3 bg-white border border-red-200 text-red-700 px-5 py-3 rounded-xl shadow-xl toast max-w-sm">
      <X className="w-5 h-5 flex-shrink-0" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  ) : (
    <div role="status" aria-live="polite" className="fixed bottom-24 lg:bottom-6 right-4 lg:right-6 z-50 flex items-center gap-3 bg-white border border-green-200 text-green-700 px-5 py-3 rounded-xl shadow-xl toast">
      <CheckCircle className="w-5 h-5" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}

// ── Opcionais interativos no carrinho ─────────────────────────────────────────

function OptionalSelectors({ item, allOptionals, onChange, catLabel }: {
  item: CartItem
  allOptionals: OptionalColor[]
  onChange: (cat: string, value: string | null) => void
  catLabel: (code: string) => string
}) {
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
        const currentOpt = available.find(o => o.color_name === currentValue)
        return (
          <div key={cat} className="flex items-center gap-1 bg-[#fcfbfa] border border-bg-2 rounded-md px-1.5 py-0.5">
            <span className="text-[10px] text-muted font-medium whitespace-nowrap">{catLabel(cat)}:</span>
            {currentOpt?.photo_url && (
              <img src={currentOpt.photo_url} alt="" className="w-3.5 h-3.5 rounded object-cover flex-shrink-0" />
            )}
            <select
              value={currentValue}
              onChange={(e) => onChange(cat, e.target.value || null)}
              className="text-[10px] text-ink bg-transparent border-none outline-none cursor-pointer"
              style={{ maxWidth: '100px' }}
            >
              <option value="">—</option>
              {available.map(opt => (
                <option key={opt.id} value={opt.color_name}>{opt.color_name}</option>
              ))}
            </select>
          </div>
        )
      })}
    </div>
  )
}

// ── Lightbox de foto ──────────────────────────────────────────────────────────

function PhotoLightbox({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-scrim/75 backdrop-blur-sm"
      onClick={onClose}>
      <div className="relative mx-4" onClick={(e) => e.stopPropagation()}>
        <img src={url} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-line" />
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 bg-white border border-line rounded-full w-11 h-11 flex items-center justify-center shadow-md text-muted hover:text-ink transition-colors"
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
  return profile === 'corporativo' ? product.price_corporativo : product.price_lojista
}

// ── Mobile cart card ──────────────────────────────────────────────────────────

function MobileCartCard({
  item, onQtyChange, onRemove, onPhotoClick, allOptionals, onOptChange, priceProfile, catLabel
}: {
  item: CartItem
  onQtyChange: (code: string, qty: number) => void
  onRemove: (code: string) => void
  onPhotoClick: (url: string) => void
  allOptionals: OptionalColor[]
  onOptChange: (cat: string, value: string | null) => void
  priceProfile: string
  catLabel: (code: string) => string
}) {
  const subtotal = item.qty * effectivePrice(item._product, priceProfile) * (1 - (item.discount || 0) / 100)
  const hasDiscount = item.discount > 0

  return (
    <div className="bg-white border border-line rounded-xl p-3.5 shadow-sm">
      {/* Top: thumbnail + info + trash */}
      <div className="flex gap-3">
        {item._product.photo_url
          ? <img
              src={item._product.photo_url} alt=""
              onClick={() => onPhotoClick(item._product.photo_url!)}
              className="w-14 h-14 object-cover rounded-lg border border-line flex-shrink-0 cursor-pointer active:opacity-70 transition-opacity"
              style={{ minWidth: '56px', minHeight: '56px' }}
            />
          : <div className="w-14 h-14 bg-bg-2 rounded-lg flex items-center justify-center flex-shrink-0">
              <ImageIcon className="w-5 h-5 text-faint" />
            </div>
        }
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="text-[11px] text-gold font-mono font-semibold">{item.product_code}</span>
              <p className="text-xs font-semibold text-ink leading-snug mt-0.5 line-clamp-2">{item._product.description}</p>
              {item._product.components.length > 0 && (
                <ul className="mt-0.5 space-y-0.5">
                  {item._product.components.map((comp) => (
                    <li key={comp.id} className="text-[10px] text-ink-3 leading-snug">
                      • {comp.qty}x {comp.description} ({comp.is_circular
                        ? `Ø ${fmtM(comp.largura)} × A ${fmtM(comp.altura)} m`
                        : `L ${fmtM(comp.largura)} × P ${fmtM(comp.profundidade)} × A ${fmtM(comp.altura)} m`})
                      {comp.optionals.length > 0 && (
                        <span className="block text-muted pl-2.5">{compFinishes(comp.optionals, catLabel)}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {item._product.observacao && (
                <p className="text-[10px] text-gold italic mt-0.5 line-clamp-2">{item._product.observacao}</p>
              )}
            </div>
            <button
              onClick={() => onRemove(item.product_code)}
              className="text-faint active:text-red-500 transition-colors w-11 h-11 flex items-center justify-center flex-shrink-0"
              style={{ touchAction: 'manipulation' }}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
          <OptionalSelectors item={item} allOptionals={allOptionals} onChange={onOptChange} catLabel={catLabel} />
        </div>
      </div>

      {/* Bottom: qty +/- | price / discount / subtotal */}
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-bg-2">
        {/* Qty stepper */}
        <div className="flex items-center gap-0 border border-line rounded-lg overflow-hidden">
          <button
            onClick={() => onQtyChange(item.product_code, Math.max(1, item.qty - 1))}
            className="w-9 h-9 flex items-center justify-center text-muted active:bg-bg-2 transition-colors"
            style={{ touchAction: 'manipulation' }}
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <span className="w-9 text-center text-sm font-semibold text-ink">{item.qty}</span>
          <button
            onClick={() => onQtyChange(item.product_code, item.qty + 1)}
            className="w-9 h-9 flex items-center justify-center text-muted active:bg-bg-2 transition-colors"
            style={{ touchAction: 'manipulation' }}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Pricing */}
        <div className="text-right">
          {hasDiscount && (
            <p className="text-[10px] text-faint line-through"><SafePrice value={effectivePrice(item._product, priceProfile) * item.qty} /></p>
          )}
          {hasDiscount && (
            <span className="text-[10px] bg-gold/10 text-gold font-semibold px-1.5 py-0.5 rounded-full">
              -{item.discount}%
            </span>
          )}
          <p className="text-sm font-bold text-ink mt-0.5"><SafePrice value={subtotal} /></p>
        </div>
      </div>
    </div>
  )
}

// ── Formulário de configuração (usado no aside e no drawer) ───────────────────

function LockedField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <span className="text-[10px] font-bold text-muted uppercase tracking-wider block">{label}</span>
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
  editMode, editCode,
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
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-[#f3ede6]">
        <h2 className="text-base font-semibold text-ink">{editMode ? 'Editar Pedido' : 'Novo Orçamento'}</h2>
        <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold tracking-wider ${editMode ? 'bg-gold/10 text-gold' : 'bg-olive/10 text-olive'}`}>
          {editMode ? editCode : budgetCode}
        </span>
      </div>

      {repLocked ? (
        <LockedField
          label="Representante"
          value={selectedRep ? `${selectedRep.name} — ${selectedRep.city}/${selectedRep.state}` : '—'}
        />
      ) : (
        <div className="space-y-1">
          <span className="text-[10px] font-bold text-muted uppercase tracking-wider block">Representante</span>
          <Autocomplete
            searchPlaceholder="Buscar representante..."
            items={reps}
            value={selectedRep}
            query={repQuery}
            getLabel={(r) => `${r.name} — ${r.city}/${r.state}`}
            getSearch={(r) => `${r.name} ${r.email} ${r.city}`}
            onChange={onRepChange}
            onClear={() => onRepChange(null)}
            onQueryChange={onRepSearch}
            isLoading={repsLoading}
            displayPlaceholder="Nenhum"
            showQuickAdd
            onQuickAdd={onQuickAddRep}
          />
        </div>
      )}

      {clientLocked && selectedClient ? (
        <LockedField label="Cliente" value={`${selectedClient.name} — ${selectedClient.city}/${selectedClient.state}`} />
      ) : (
        <div className="space-y-1">
          <span className="text-[10px] font-bold text-muted uppercase tracking-wider block">Cliente</span>
          <Autocomplete
            searchPlaceholder="Buscar cliente..."
            items={clients}
            value={selectedClient}
            query={clientQuery}
            getLabel={(c) => `${c.name} — ${c.city}/${c.state}`}
            getSearch={(c) => `${c.name} ${c.email} ${c.city}`}
            onChange={onClientChange}
            onClear={() => onClientChange(null)}
            onQueryChange={onClientSearch}
            isLoading={clientsLoading}
            displayPlaceholder="Selecione o cliente..."
            showQuickAdd
            onQuickAdd={onQuickAddClient}
          />
        </div>
      )}

      <div className="space-y-1">
        <span className="text-[10px] font-bold text-muted uppercase tracking-wider block">Observações</span>
        <textarea
          className="input resize-none text-xs"
          rows={3}
          placeholder="Observações do orçamento..."
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
        />
      </div>


      {(!selectedClient || cart.length === 0) && !isGenerating && (
        <p className="text-[10px] text-muted text-center -mt-1">
          {cart.length === 0 ? 'Adicione ao menos um produto ao orçamento.' : 'Selecione um cliente para continuar.'}
        </p>
      )}
      <button
        onClick={onSubmit}
        disabled={!selectedClient || cart.length === 0 || isGenerating}
        style={{ touchAction: 'manipulation' }}
        className="w-full py-3.5 rounded-lg text-xs font-bold tracking-widest text-white transition-all bg-gold hover:bg-[#725510] disabled:bg-faint disabled:cursor-not-allowed uppercase shadow-sm active:scale-[0.98] active:opacity-85"
      >
        {editMode ? 'Salvar Alterações' : 'Finalizar Orçamento'}
      </button>
    </div>
  )
}

// ── Bottom Drawer (mobile) ────────────────────────────────────────────────────

function BottomDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] flex items-end lg:hidden">
      <div className="fixed inset-0 bg-scrim/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full bg-white rounded-t-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <span className="text-sm font-semibold text-ink">Configurar Orçamento</span>
          <button onClick={onClose} className="w-11 h-11 flex items-center justify-center text-muted">
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
  const [searchParams, setSearchParams] = useSearchParams()
  const editId = searchParams.get('edit')

  // Locking flags
  const isRep = user?.role === 'representante'
  // cliente-final: role própria `cliente` (ou legado `vendedor`+linked_id)
  const isClientUser = user?.role === 'cliente' || (user?.role === 'vendedor' && !!user?.linked_id)
  const repLocked = isRep || isClientUser
  const clientLocked = isClientUser

  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [selectedRep, setSelectedRep] = useState<Representative | null>(null)
  const [notes, setNotes] = useState('')
  const [cart, setCart] = useState<CartItem[]>([])
  const [persistedCart] = useState<PersistedCartItem[]>(readPersistedCart)
  const [savedClientId, setSavedClientId] = useState(() => localStorage.getItem('orcamento_client_id') ?? '')
  // null = nenhuma preferência gravada; vazio = remoção explícita.
  const [savedRepId, setSavedRepId] = useState<string | null>(() => localStorage.getItem('orcamento_rep_id'))
  const [cartHydrated, setCartHydrated] = useState(false)
  const [productQuery, setProductQuery] = useState('')
  const [clientQuery, setClientQuery] = useState('')
  const [repQuery, setRepQuery] = useState('')
  const [productOpen, setProductOpen] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [cartFilter, setCartFilter] = useState('')
  const [toast, setToast] = useState<{ message: string; variant: 'success' | 'error' } | null>(null)
  const [quickModal, setQuickModal] = useState<'client' | 'rep' | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const productRef = useRef<HTMLDivElement>(null)

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
    cart.flatMap((item) =>
      (item._product.all_optionals_categories ?? '')
        .split(',')
        .map((category) => category.trim())
        .filter(Boolean)
    ),
  ))
  const { data: allOptionals = [] } = useOptionalsForCategories(
    freeOptionalCategories,
    freeOptionalCategories.length > 0,
  )
  const { data: optCategories = [] } = useOptionalCategories()
  const catLabel = (code: string) => optCategories.find(c => c.code === code)?.name ?? code

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

  // Perfil de faturamento do cliente selecionado; sem cliente, usa lojista (Bloco 62)
  const priceProfile = selectedClient?.price_profile ?? 'lojista'

  function handleClientChange(client: Client | null) {
    const clientId = client?.id ?? ''
    setSelectedClient(client)
    setSavedClientId(clientId)
    if (!repLocked && savedRepId === null) setSelectedRep(null)
    if (clientId) localStorage.setItem('orcamento_client_id', clientId)
    else localStorage.removeItem('orcamento_client_id')
  }

  function handleRepChange(rep: Representative | null) {
    const repId = rep?.id ?? ''
    setSelectedRep(rep)
    setSavedRepId(repId)
    if (repId) localStorage.setItem('orcamento_rep_id', repId)
    else localStorage.setItem('orcamento_rep_id', '')
  }

  function resetSavedSelections() {
    setSelectedClient(null)
    setSelectedRep(null)
    setSavedClientId('')
    setSavedRepId(null)
    localStorage.removeItem('orcamento_client_id')
    localStorage.removeItem('orcamento_rep_id')
  }

  // O carrinho salvo resolve somente os SKUs necessários, sem baixar o catálogo.
  useEffect(() => {
    if (cartHydrated || editId) return
    if (persistedCart.length === 0) {
      setCartHydrated(true)
      return
    }
    if (!resolvedProductQuery.isSuccess) return
    const productMap = new Map(
      resolvedProducts.map((product) => [product.product_code, product]),
    )
    setCart(
      persistedCart
        .filter((item) => productMap.has(item.product_code))
        .map((item) => ({
          ...item,
          _product: productMap.get(item.product_code)!,
        })),
    )
    setCartHydrated(true)
  }, [
    cartHydrated,
    editId,
    persistedCart,
    resolvedProductQuery.isSuccess,
    resolvedProducts,
  ])

  useEffect(() => {
    if (editId || !cartHydrated) return
    const serializable = cart.map(({ _product, ...rest }) => rest)
    localStorage.setItem('carrinho_orcamento', JSON.stringify(serializable))
  }, [cart, cartHydrated, editId])

  // Sincroniza _product com dados frescos da API (garante observacao e preço atualizados)
  useEffect(() => {
    if (resolvedProducts.length === 0) return
    const productMap = new Map(
      resolvedProducts.map((product) => [product.product_code, product]),
    )
    setCart(prev => prev.map(item => ({
      ...item,
      _product: productMap.get(item.product_code) ?? item._product,
    })))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedProducts])

  // Pré-preenche contas vinculadas e restaura seleções por ID.
  useEffect(() => {
    if (!editId && resolvedClient && !selectedClient) {
      setSelectedClient(resolvedClient)
    }
    if (!editId && resolvedRep && !selectedRep) {
      setSelectedRep(resolvedRep)
    }
  }, [editId, resolvedClient, resolvedRep, selectedClient, selectedRep])

  // Pre-populate cart + client + rep when editing an existing order.
  // BUG-02 (Bloco 88): refetches em background do React Query trocam a identidade
  // de editOrder e re-disparavam este efeito, sobrescrevendo edições em andamento
  // do carrinho — o ref garante que cada pedido só popule o formulário uma vez.
  const editOrderLoadedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!editOrder || !resolvedProductQuery.isSuccess || !resolvedClient) return
    if (editOrder.rep_id && !resolvedRep) return
    if (editOrderLoadedRef.current === editOrder.id) return
    editOrderLoadedRef.current = editOrder.id
    const productMap = new Map(
      resolvedProducts.map((product) => [product.product_code, product]),
    )
    const cartItems: CartItem[] = editOrder.items
      .map(item => {
        const product = productMap.get(item.product_code)
        if (!product) return null
        return {
          product_code: item.product_code,
          qty: item.qty,
          discount: Number(item.discount),
          opt_categories: item.opt_categories,
          _product: product,
        }
      })
      .filter(Boolean) as CartItem[]
    setCart(cartItems)
    setSelectedClient(resolvedClient)
    setSelectedRep(editOrder.rep_id ? resolvedRep ?? null : null)
    setNotes(editOrder.notes ?? '')
    setCartHydrated(true)
  }, [
    editOrder,
    resolvedClient,
    resolvedProductQuery.isSuccess,
    resolvedProducts,
    resolvedRep,
  ])

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

  function updateOptCategory(code: string, cat: string, value: string | null) {
    setCart(prev => prev.map(i => {
      if (i.product_code !== code) return i
      const updated = { ...i.opt_categories }
      if (!value) delete updated[cat]
      else updated[cat] = value
      return { ...i, opt_categories: updated }
    }))
  }

  function handleAddProductToCart() {
    if (!cartHydrated || !selectedProduct) return
    const freeCats = new Set((selectedProduct.all_optionals_categories ?? '').split(',').filter(Boolean))
    const auto_categories: Partial<Record<string, string>> = {}
    for (const opt of selectedProduct.optionals) {
      // Don't pre-select for "all" categories — user picks freely in the cart
      if (!(opt.category in auto_categories) && !freeCats.has(opt.category)) {
        auto_categories[opt.category] = opt.color_name
      }
    }
    setCart((prev) => {
      const existing = prev.find((i) => i.product_code === selectedProduct.product_code)
      if (existing) {
        return prev.map((i) => i.product_code === selectedProduct.product_code ? { ...i, qty: i.qty + 1 } : i)
      }
      return [...prev, {
        product_code: selectedProduct.product_code,
        qty: 1,
        discount: 0,
        opt_categories: auto_categories,
        _product: selectedProduct,
      }]
    })
    setSelectedProduct(null)
    setProductQuery('')
  }

  function updateQty(code: string, qty: number) {
    if (qty < 1) return
    setCart((prev) => prev.map((i) => i.product_code === code ? { ...i, qty } : i))
  }

  function removeItem(code: string) {
    setCart((prev) => prev.filter((i) => i.product_code !== code))
  }

  const filteredCart = cart.filter((item) =>
    `${item.product_code} ${item._product.description}`.toLowerCase().includes(cartFilter.toLowerCase())
  )

  const { data: productTypes = [] } = useProductTypes()

  const total = cart.reduce((sum, i) => {
    return sum + i.qty * effectivePrice(i._product, priceProfile) * (1 - (i.discount || 0) / 100)
  }, 0)

  const ipiTotal = cart.reduce((sum, i) => {
    const pt = productTypes.find(t => t.name === i._product.type)
    const rate = Number(pt?.group?.ipi ?? 0)
    const subtotal = i.qty * effectivePrice(i._product, priceProfile) * (1 - (i.discount || 0) / 100)
    return sum + subtotal * rate / 100
  }, 0)

  const totalWithIpi = total + ipiTotal

  // O código definitivo é atribuído atomicamente pelo PostgreSQL ao salvar.
  // Não é possível prevê-lo por contagem sem criar colisões em uso concorrente.
  const budgetCode = 'Gerado ao salvar'

  const itemsPayload = cart.map(({ product_code, qty, discount, opt_categories }) => ({
    product_code,
    qty,
    discount: discount || 0,
    opt_categories: opt_categories as Record<string, string>,
  }))
  const repIdForSubmit = editId
    ? selectedRep?.id ?? null
    : selectedRep?.id ?? (targetRepId || null)

  async function handleSubmit() {
    if (!cartHydrated || !selectedClient || cart.length === 0) return
    setIsGenerating(true)
    try {
      if (editId) {
        await Promise.all([
          updateOrderM.mutateAsync({
            id: editId,
            data: {
              rep_id: repIdForSubmit,
              notes: notes || null,
              items: itemsPayload,
            },
          }),
          new Promise<void>((r) => setTimeout(r, 1500)),
        ])
        setToast({ message: 'Pedido atualizado com sucesso!', variant: 'success' })
        setSearchParams({})
      } else {
        await Promise.all([
          createOrderM.mutateAsync({
            client_id: selectedClient.id,
            rep_id: repIdForSubmit,
            notes: notes || null,
            items: itemsPayload,
          }),
          new Promise<void>((r) => setTimeout(r, 3000)),
        ])
        setToast({ message: 'Orçamento finalizado com sucesso!', variant: 'success' })
      }
      setCart([])
      localStorage.removeItem('carrinho_orcamento')
      resetSavedSelections()
      editOrderLoadedRef.current = null
      setNotes('')
      setDrawerOpen(false)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setToast({ message: detail ?? 'Erro ao processar o pedido. Tente novamente.', variant: 'error' })
    } finally {
      setIsGenerating(false)
    }
  }

  // Product search card (shared between desktop and a potential mobile add section)
  const productSearchCard = (
    <div className="bg-[#f5ede3] border border-[#e8dccb] rounded-xl p-4 space-y-3.5">
      <span className="text-[10px] font-bold text-gold uppercase tracking-wider block">Adicionar Produto</span>
      {!cartHydrated && (
        <div className="rounded-lg border border-[#e8dccb] bg-white px-3 py-2 text-xs text-muted">
          {editId && editOrderQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>Não foi possível carregar o pedido para edição.</span>
              <button
                type="button"
                onClick={() => void editOrderQuery.refetch()}
                className="shrink-0 font-semibold text-gold hover:underline"
              >
                Tentar novamente
              </button>
            </div>
          ) : editId && resolvedClientQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>Não foi possível carregar o cliente deste pedido.</span>
              <button
                type="button"
                onClick={() => void resolvedClientQuery.refetch()}
                className="shrink-0 font-semibold text-gold hover:underline"
              >
                Tentar novamente
              </button>
            </div>
          ) : editId && resolvedRepQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>Não foi possível carregar o representante deste pedido.</span>
              <button
                type="button"
                onClick={() => void resolvedRepQuery.refetch()}
                className="shrink-0 font-semibold text-gold hover:underline"
              >
                Tentar novamente
              </button>
            </div>
          ) : resolvedProductQuery.isError ? (
            <div className="flex items-center justify-between gap-3">
              <span>Não foi possível restaurar os produtos. O carrinho salvo foi preservado.</span>
              <button
                type="button"
                onClick={() => void resolvedProductQuery.refetch()}
                className="shrink-0 font-semibold text-gold hover:underline"
              >
                Tentar novamente
              </button>
            </div>
          ) : (
            <span>Restaurando produtos do orçamento…</span>
          )}
        </div>
      )}
      <div ref={productRef} className="relative">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
          <input
            className="input pl-8 w-full text-xs bg-white border border-line rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gold"
            placeholder="Buscar produto por codigo ou desc"
            value={productQuery}
            disabled={!cartHydrated}
            onChange={(e) => { setProductQuery(e.target.value); setProductOpen(true) }}
            onFocus={() => { if (cartHydrated) setProductOpen(true) }}
          />
        </div>
        {cartHydrated && productOpen && (
          <ul className="absolute left-0 right-0 z-30 mt-1 bg-white border border-line rounded-xl overflow-hidden shadow-xl max-h-52 overflow-y-auto">
            {productSearch.isFetching && (
              <li className="px-3 py-2 text-xs text-muted">Buscando…</li>
            )}
            {filteredProducts.slice(0, 15).map((p) => (
              <li
                key={p.id}
                className="px-3 py-2 text-xs hover:bg-bg cursor-pointer flex items-center gap-2 transition-colors border-b border-[#fbfaf9]"
                onMouseDown={() => { setSelectedProduct(p); setProductQuery(''); setProductOpen(false) }}
              >
                {p.photo_url
                  ? <img src={p.photo_url} alt="" className="w-8 h-8 rounded object-cover border border-line flex-shrink-0" />
                  : <ImageIcon className="w-8 h-8 text-faint flex-shrink-0" />}
                <div className="truncate">
                  <span className="text-gold font-mono font-medium">{p.product_code}</span>
                  <span className="text-ink ml-1.5 font-medium">{p.description}</span>
                  {dimLabel(p) && <div className="text-[9px] text-muted">{dimLabel(p)}</div>}
                </div>
              </li>
            ))}
            {!productSearch.isFetching && filteredProducts.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted">
                Nenhum produto encontrado.
              </li>
            )}
          </ul>
        )}
      </div>
      {selectedProduct && (
        <div className="bg-white border border-[#e8dccb] rounded-lg p-2.5 flex gap-2.5 shadow-sm relative">
          <button type="button" onClick={() => setSelectedProduct(null)}
            className="absolute top-1.5 right-1.5 text-muted hover:text-red-500 transition-colors w-7 h-7 flex items-center justify-center">
            <X className="w-3.5 h-3.5" />
          </button>
          {selectedProduct.photo_url
            ? <img src={selectedProduct.photo_url} alt="" onClick={() => setActivePhotoModal(selectedProduct.photo_url!)}
                className="w-12 h-12 object-cover rounded border border-line flex-shrink-0 cursor-pointer hover:opacity-80 transition-opacity" />
            : <div className="w-12 h-12 bg-bg-2 rounded flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-faint" /></div>
          }
          <div className="text-[11px] pr-5 flex-1 min-w-0">
            <p className="text-gold font-mono font-semibold">{selectedProduct.product_code}</p>
            <p className="text-ink font-medium truncate">{selectedProduct.description}</p>
            <p className="text-gold font-bold mt-0.5"><SafePrice value={effectivePrice(selectedProduct, priceProfile)} /></p>
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={handleAddProductToCart}
        disabled={!cartHydrated || !selectedProduct}
        style={{ touchAction: 'manipulation' }}
        className="w-full py-2.5 rounded-lg text-xs font-semibold tracking-wider text-white transition-all bg-gold hover:bg-[#725510] disabled:bg-faint disabled:cursor-not-allowed flex items-center justify-center gap-1.5 shadow-sm active:scale-[0.98]"
      >
        ADICIONAR AO ORÇAMENTO
      </button>
    </div>
  )

  return (
    <div className="min-h-screen bg-bg text-ink">
      {editId && editOrder && (
        <div className="bg-gold text-white px-4 lg:px-8 py-2.5 flex items-center gap-2.5">
          <PenLine className="w-4 h-4 flex-shrink-0" />
          <span className="text-xs font-semibold tracking-wide">
            Editando Pedido: <span className="font-mono">{editOrder.code}</span>
          </span>
          <button
            onClick={() => {
              setSearchParams({})
              setCart([])
              setCartHydrated(true)
              editOrderLoadedRef.current = null
              resetSavedSelections()
              setNotes('')
              localStorage.removeItem('carrinho_orcamento')
            }}
            className="ml-auto text-white/70 hover:text-white text-xs underline"
          >
            Cancelar edição
          </button>
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 lg:px-8 py-4 lg:py-6 grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 pb-28 lg:pb-6">

        {/* ── Mobile: product search card ────────────────────────────────── */}
        <div className="lg:hidden">{productSearchCard}</div>

        {/* ── Items Panel ──────────────────────────────────────────────────── */}
        <main className="bg-white border border-line rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[400px] lg:min-h-[550px]">
          <div className="px-4 lg:px-6 py-3.5 lg:py-4 border-b border-line flex items-center justify-between bg-white flex-shrink-0">
            <h2 className="text-sm font-semibold text-gold uppercase tracking-wider flex items-center gap-2">
              <ShoppingCart className="w-4 h-4" /> Itens do Orçamento
            </h2>
            <div className="flex items-center gap-2">
              {cart.length > 0 && (
                <button
                  onClick={() => { setCart([]); localStorage.removeItem('carrinho_orcamento') }}
                  className="text-xs text-terracotta hover:text-[#8a3a2e] border border-[#f0c8c0] hover:border-terracotta px-2.5 py-1.5 rounded-lg transition-colors"
                  style={{ touchAction: 'manipulation' }}
                >
                  Limpar
                </button>
              )}
              <div className="relative w-36 lg:w-52">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
                <input
                  className="input pl-8 w-full text-xs border border-line rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-gold bg-white"
                  placeholder="Buscar..."
                  value={cartFilter}
                  onChange={(e) => setCartFilter(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {filteredCart.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-muted space-y-3">
                <Clipboard className="w-10 h-10 text-faint stroke-[1.2]" />
                <p className="text-sm font-medium text-[#6b5d55]">Nenhum item adicionado.</p>
              </div>
            ) : (
              <>
                {/* ── Mobile cards ─────────────────────────────── */}
                <div className="flex flex-col gap-3 p-3 lg:hidden">
                  {filteredCart.map((item) => (
                    <MobileCartCard
                      key={item.product_code}
                      item={item}
                      onQtyChange={updateQty}
                      onRemove={removeItem}
                      onPhotoClick={setActivePhotoModal}
                      allOptionals={allOptionals}
                      onOptChange={(cat, val) => updateOptCategory(item.product_code, cat, val)}
                      priceProfile={priceProfile}
                      catLabel={catLabel}
                    />
                  ))}
                </div>

                {/* ── Desktop table ────────────────────────────── */}
                <table className="hidden lg:table w-full text-sm">
                  <thead className="bg-surface-2 text-xs text-muted uppercase font-semibold border-b border-line sticky top-0 z-10">
                    <tr>
                      <th className="px-4 py-3 text-left">Produto</th>
                      <th className="px-4 py-3 text-left w-16">Qtd</th>
                      <th className="px-4 py-3 text-left w-28">Preço Base</th>
                      <th className="px-4 py-3 text-left w-24">Desconto (%)</th>
                      <th className="px-4 py-3 text-right w-28">IPI</th>
                      <th className="px-4 py-3 text-right w-28">Subtotal</th>
                      <th className="px-4 py-3 w-8"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {filteredCart.map((item) => {
                      const pt = productTypes.find(t => t.name === item._product.type)
                      const ipiRate = Number(pt?.group?.ipi ?? 0)
                      const subtotal = item.qty * effectivePrice(item._product, priceProfile) * (1 - (item.discount || 0) / 100)
                      const subtotalWithIpi = subtotal * (1 + ipiRate / 100)
                      return (
                        <tr key={item.product_code} className="hover:bg-[#fcfbf9] align-top transition-colors">
                          <td className="px-4 py-3.5">
                            <div className="flex gap-3">
                              {item._product.photo_url
                                ? <img src={item._product.photo_url} alt="" onClick={() => setActivePhotoModal(item._product.photo_url!)}
                                    className="object-cover rounded-lg border border-line cursor-pointer hover:opacity-80 transition-opacity"
                                    style={{ width: '48px', height: '48px', minWidth: '48px', minHeight: '48px' }} />
                                : <div className="bg-bg-2 rounded-lg flex items-center justify-center"
                                    style={{ width: '48px', height: '48px', minWidth: '48px', minHeight: '48px' }}>
                                    <ImageIcon className="w-5 h-5 text-faint" />
                                  </div>
                              }
                              <div className="flex-1 min-w-0">
                                <span className="text-gold font-mono font-semibold">{item.product_code}</span>
                                <span className="text-ink ml-2 text-xs font-semibold">{item._product.description}</span>
                                {item._product.components.length > 0 && (
                                  <ul className="mt-0.5 space-y-0.5">
                                    {item._product.components.map((comp) => (
                                      <li key={comp.id} className="text-[10px] text-ink-3 leading-snug">
                                        • {comp.qty}x {comp.description} ({comp.is_circular
                                          ? `Ø ${fmtM(comp.largura)} × A ${fmtM(comp.altura)} m`
                                          : `L ${fmtM(comp.largura)} × P ${fmtM(comp.profundidade)} × A ${fmtM(comp.altura)} m`})
                                        {comp.optionals.length > 0 && (
                                          <span className="block text-muted pl-2.5">{compFinishes(comp.optionals, catLabel)}</span>
                                        )}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                                {item._product.observacao && (
                                  <div className="text-[10px] text-gold italic mt-0.5">{item._product.observacao}</div>
                                )}
                                {dimLabel(item._product) && (
                                  <div className="text-[10px] text-muted mt-0.5">{dimLabel(item._product)}</div>
                                )}
                                <OptionalSelectors item={item} allOptionals={allOptionals} onChange={(cat, val) => updateOptCategory(item.product_code, cat, val)} catLabel={catLabel} />
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 align-middle">
                            <input
                              type="number" min={1}
                              className="input w-16 text-center text-xs border border-line rounded-lg py-1 bg-white text-ink"
                              value={item.qty}
                              onChange={(e) => updateQty(item.product_code, Number(e.target.value))}
                            />
                          </td>
                          <td className="px-4 py-3.5 text-ink-2 text-xs font-semibold whitespace-nowrap align-middle">
                            <SafePrice value={effectivePrice(item._product, priceProfile)} />
                          </td>
                          <td className="px-4 py-3.5 align-middle">
                            <input
                              type="number" min={0} max={user?.max_discount ?? 0}
                              className="input w-16 text-center text-xs border border-line rounded-lg px-1.5 py-1 bg-white text-ink"
                              value={item.discount === 0 ? '' : item.discount}
                              placeholder="0"
                              onChange={(e) => {
                                const val = Math.min(user?.max_discount ?? 0, Math.max(0, Number(e.target.value) || 0))
                                setCart((prev) => prev.map((i) => i.product_code === item.product_code ? { ...i, discount: val } : i))
                              }}
                            />
                            {item.discount > 0 && (
                              <p className="text-[9px] text-muted mt-0.5 text-center whitespace-nowrap">
                                <SafePrice value={effectivePrice(item._product, priceProfile) * item.discount / 100} prefix="− R$ " />
                              </p>
                            )}
                          </td>
                          <td className="px-4 py-3.5 text-right align-middle whitespace-nowrap">
                            {ipiRate > 0
                              ? <span className="text-xs font-semibold text-gold">{ipiRate}%</span>
                              : <span className="text-xs text-faint">—</span>
                            }
                          </td>
                          <td className="px-4 py-3.5 text-right text-xs font-bold text-ink align-middle whitespace-nowrap">
                            <SafePrice value={subtotalWithIpi} />
                          </td>
                          <td className="px-4 py-3.5 align-middle text-center">
                            <button onClick={() => removeItem(item.product_code)} className="text-faint hover:text-red-500 transition-colors w-11 h-11 flex items-center justify-center mx-auto">
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>

          {/* Desktop summary footer */}
          {cart.length > 0 && (
            <div className="hidden lg:flex bg-surface-2 border-t border-line px-6 py-4 justify-between items-center flex-shrink-0">
              <div className="flex gap-4 text-xs text-muted-2">
                <div><span>Itens: </span><span className="font-semibold text-ink">{cart.reduce((s, i) => s + i.qty, 0)}</span></div>
                <div><span>Produtos: </span><span className="font-semibold text-ink">{cart.length}</span></div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-ink font-semibold text-xs uppercase tracking-wider">Total do Orçamento:</span>
                <span className="text-gold font-bold text-base"><SafePrice value={totalWithIpi} /></span>
              </div>
            </div>
          )}
        </main>

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
                editMode={!!editId} editCode={editOrder?.code}
              />
            </fieldset>
            {productSearchCard}
          </div>
        </aside>
      </div>

      {/* ── Mobile fixed bottom bar ────────────────────────────────────────── */}
      <div className="lg:hidden fixed bottom-16 inset-x-0 z-30 px-4 pb-2">
        <button
          onClick={() => setDrawerOpen(true)}
          style={{ touchAction: 'manipulation' }}
          className="w-full flex items-center justify-between bg-gold text-white px-5 py-3.5 rounded-xl shadow-xl active:scale-[0.98] active:opacity-90 transition-all"
        >
          <div className="flex items-center gap-2">
            <ChevronUp className="w-4 h-4" />
            <span className="text-sm font-semibold">
              {cart.length > 0
                ? `Ver Resumo (${cart.reduce((s, i) => s + i.qty, 0)} ${cart.reduce((s, i) => s + i.qty, 0) === 1 ? 'item' : 'itens'})`
                : 'Configurar Orçamento'}
            </span>
          </div>
          {cart.length > 0 && (
            <span className="text-sm font-bold"><SafePrice value={total} /></span>
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
            editMode={!!editId} editCode={editOrder?.code}
          />
        </fieldset>
      </BottomDrawer>

      {quickModal === 'client' && (
        <QuickRegisterModal
          title="Novo Cliente"
          onSave={async (data) => { await createClientM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}
      {quickModal === 'rep' && !isRep && (
        <QuickRegisterModal
          title="Novo Representante"
          onSave={async (data) => { await createRepM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}

      {toast && <Toast message={toast.message} variant={toast.variant} onDone={() => setToast(null)} />}
      {activePhotoModal && <PhotoLightbox url={activePhotoModal} onClose={() => setActivePhotoModal(null)} />}

      {/* ── Overlay de Geração Premium ─────────────────────────────── */}
      {isGenerating && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-bg/90 backdrop-blur-sm">
          <div
            className="absolute w-[520px] h-[520px] rounded-full pointer-events-none"
            style={{
              background: 'radial-gradient(circle, rgba(139,105,20,0.18) 0%, transparent 68%)',
              animation: 'pulseRadial 2.2s ease-in-out infinite',
            }}
          />
          <p
            className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none"
            style={{
              fontFamily: "'Cormorant Garamond', Georgia, serif",
              backgroundImage: 'linear-gradient(90deg, #5a4508 0%, #8b6914 25%, #c8952e 50%, #8b6914 75%, #5a4508 100%)',
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
            className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-gold"
            style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}
          >
            Gerando Orçamento
          </p>
          <div className="mt-9 w-52 h-[1px] bg-gold/25 overflow-hidden rounded-full">
            <div
              className="h-full rounded-full"
              style={{
                background: 'linear-gradient(90deg, #5a4508, #c8952e, #5a4508)',
                animation: 'progressLine 3s linear forwards',
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
