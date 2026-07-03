import { useState, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../lib/api'
import { Search, Plus, X, Trash2, ShoppingCart, CheckCircle, ImageIcon, Clipboard, Minus, ChevronUp, Lock, PenLine } from 'lucide-react'
import { useProducts } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useClients, useCreateClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative } from '../hooks/useRepresentatives'
import { useCreateOrder, useOrders, useUpdateOrder, useOrder } from '../hooks/useOrders'
import { useOptionals } from '../hooks/useOptionals'
import { SafePrice } from '../components/SafePrice'
import { useAuth } from '../hooks/useAuth'
import type { Product, Client, Representative, ClientCreate, OptionalColor } from '../types'

// ── Category display labels ───────────────────────────────────────────────────

const CAT_LABEL: Record<string, string> = {
  aluminio:       'Alumínio',
  madeira_teka:   'Madeira Teka',
  madeira_freijo: 'Madeira Freijó',
  tecido_faixa_1: 'Tecido Faixa 1',
  tecido_faixa_2: 'Tecido Faixa 2',
  couro_soleta:   'Couro Soleta',
  couro_pele:     'Couro Pele',
  corda:          'Corda',
}

function computeOptFields(cats: Partial<Record<string, string>>) {
  return {
    opt_aluminio: cats.aluminio ?? null,
    opt_madeira:  cats.madeira_teka   ? `madeira_teka/${cats.madeira_teka}`
                : cats.madeira_freijo ? `madeira_freijo/${cats.madeira_freijo}`
                : null,
    opt_tecido:   cats.tecido_faixa_1 ? `tecido_faixa_1/${cats.tecido_faixa_1}`
                : cats.tecido_faixa_2 ? `tecido_faixa_2/${cats.tecido_faixa_2}`
                : null,
    opt_couro:    cats.couro_soleta   ? `couro_soleta/${cats.couro_soleta}`
                : cats.couro_pele     ? `couro_pele/${cats.couro_pele}`
                : null,
    opt_corda:    cats.corda ?? null,
  }
}

function parseOptFields(item: { opt_aluminio: string | null; opt_madeira: string | null; opt_tecido: string | null; opt_couro: string | null; opt_corda: string | null }): Partial<Record<string, string>> {
  const cats: Partial<Record<string, string>> = {}
  if (item.opt_aluminio) cats.aluminio = item.opt_aluminio
  if (item.opt_corda) cats.corda = item.opt_corda
  if (item.opt_madeira) {
    const [cat, color] = item.opt_madeira.split('/')
    if (cat && color) cats[cat] = color
  }
  if (item.opt_tecido) {
    const [cat, color] = item.opt_tecido.split('/')
    if (cat && color) cats[cat] = color
  }
  if (item.opt_couro) {
    const [cat, color] = item.opt_couro.split('/')
    if (cat && color) cats[cat] = color
  }
  return cats
}

function fmtM(v: number) { return Number(v).toFixed(2).replace('.', ',') }

function dimLabel(p: Product) {
  return p.is_circular
    ? `Ø ${fmtM(p.largura)} × A ${fmtM(p.altura)} m`
    : `L ${fmtM(p.largura)} × P ${fmtM(p.profundidade)} × A ${fmtM(p.altura)} m`
}

// ── Autocomplete ──────────────────────────────────────────────────────────────

function Autocomplete<T extends { id: string }>({
  searchPlaceholder, items, value, getLabel, getSearch, onChange, onClear, displayPlaceholder = "Nenhum", showQuickAdd, onQuickAdd
}: {
  searchPlaceholder: string; items: T[]; value: T | null
  getLabel: (item: T) => string; getSearch: (item: T) => string
  onChange: (item: T) => void; onClear: () => void; displayPlaceholder?: string
  showQuickAdd?: boolean; onQuickAdd?: () => void
}) {
  const [query, setQuery] = useState('')
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
        <div className="input flex items-center justify-between bg-[#fcfbfa] border border-[#e8e0d6] px-3 py-1.5 rounded-lg text-sm flex-1 min-w-0 h-[36px]">
          <span className={`${value ? 'text-[#2c2420] font-medium' : 'text-[#a89a8e]'} truncate flex-1 min-w-0`}>
            {value ? getLabel(value) : displayPlaceholder}
          </span>
          {value && (
            <button type="button" onClick={onClear} className="text-[#9d8d81] hover:text-[#2c2420] transition-colors w-7 h-7 flex items-center justify-center">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        {showQuickAdd && onQuickAdd && (
          <button type="button" onClick={onQuickAdd} className="btn-secondary px-2.5 flex-shrink-0 h-[36px] border border-[#e8e0d6] hover:bg-[#f8f6f2] rounded-lg transition-colors flex items-center justify-center min-w-[44px]">
            <Plus className="w-4 h-4 text-[#9d8d81]" />
          </button>
        )}
      </div>
      <div className="relative">
        <input
          className="input w-full text-xs placeholder:text-[#c8bdb5] border border-[#e8e0d6] rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#8b6914] bg-white"
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
        {open && filtered.length > 0 && (
          <ul className="absolute z-30 w-full mt-1 bg-white border border-[#e8e0d6] rounded-xl overflow-hidden shadow-xl max-h-48 overflow-y-auto">
            {filtered.slice(0, 15).map((item) => (
              <li key={item.id} className="px-3 py-2 text-xs text-[#2c2420] hover:bg-[#f8f6f2] cursor-pointer transition-colors"
                onMouseDown={() => { onChange(item); setQuery(''); setOpen(false) }}>
                {getLabel(item)}
              </li>
            ))}
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
          <h3 className="text-lg font-semibold text-[#2c2420]">{title}</h3>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420] w-11 h-11 flex items-center justify-center"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">Nome *</span>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">Telefone *</span>
            <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">E-mail *</span>
            <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1 relative">
            <span className="text-xs text-[#9d8d81]">CEP *</span>
            <input className="input" value={form.cep} onChange={(e) => setForm({ ...form, cep: e.target.value })} onBlur={handleCepBlur} maxLength={9} required />
            {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-[#8b6914] animate-pulse">...</span>}
            {cepError && <span className="text-[10px] text-red-500">CEP não encontrado ou serviço indisponível.</span>}
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">Número</span>
            <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: e.target.value })} />
          </label>
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">Endereço *</span>
            <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">Cidade *</span>
            <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9d8d81]">UF *</span>
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

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDone, variant = 'success' }: { message: string; onDone: () => void; variant?: 'success' | 'error' }) {
  useEffect(() => {
    const t = setTimeout(onDone, 4000)
    return () => clearTimeout(t)
  }, [onDone])
  return variant === 'error' ? (
    <div className="fixed bottom-24 lg:bottom-6 right-4 lg:right-6 z-50 flex items-center gap-3 bg-white border border-red-200 text-red-700 px-5 py-3 rounded-xl shadow-xl toast max-w-sm">
      <X className="w-5 h-5 flex-shrink-0" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  ) : (
    <div className="fixed bottom-24 lg:bottom-6 right-4 lg:right-6 z-50 flex items-center gap-3 bg-white border border-green-200 text-green-700 px-5 py-3 rounded-xl shadow-xl toast">
      <CheckCircle className="w-5 h-5" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}

// ── Opcionais interativos no carrinho ─────────────────────────────────────────

function OptionalSelectors({ item, allOptionals, onChange }: {
  item: CartItem
  allOptionals: OptionalColor[]
  onChange: (cat: string, value: string | null) => void
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
          <div key={cat} className="flex items-center gap-1 bg-[#fcfbfa] border border-[#f0ece6] rounded-md px-1.5 py-0.5">
            <span className="text-[10px] text-[#9d8d81] font-medium whitespace-nowrap">{CAT_LABEL[cat] ?? cat}:</span>
            {currentOpt?.photo_url && (
              <img src={currentOpt.photo_url} alt="" className="w-3.5 h-3.5 rounded object-cover flex-shrink-0" />
            )}
            <select
              value={currentValue}
              onChange={(e) => onChange(cat, e.target.value || null)}
              className="text-[10px] text-[#2c2420] bg-transparent border-none outline-none cursor-pointer"
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
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#1a1410]/75 backdrop-blur-sm"
      onClick={onClose}>
      <div className="relative mx-4" onClick={(e) => e.stopPropagation()}>
        <img src={url} alt="" className="max-w-[480px] max-h-[480px] w-auto h-auto object-contain rounded-2xl shadow-2xl border border-[#e8e0d6]" />
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 bg-white border border-[#e8e0d6] rounded-full w-8 h-8 flex items-center justify-center shadow-md text-[#9d8d81] hover:text-[#2c2420] transition-colors"
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
  item, onQtyChange, onRemove, onPhotoClick, allOptionals, onOptChange, priceProfile
}: {
  item: CartItem
  onQtyChange: (code: string, qty: number) => void
  onRemove: (code: string) => void
  onPhotoClick: (url: string) => void
  allOptionals: OptionalColor[]
  onOptChange: (cat: string, value: string | null) => void
  priceProfile: string
}) {
  const subtotal = item.qty * effectivePrice(item._product, priceProfile) * (1 - (item.discount || 0) / 100)
  const hasDiscount = item.discount > 0

  return (
    <div className="bg-white border border-[#e8e0d6] rounded-xl p-3.5 shadow-sm">
      {/* Top: thumbnail + info + trash */}
      <div className="flex gap-3">
        {item._product.photo_url
          ? <img
              src={item._product.photo_url} alt=""
              onClick={() => onPhotoClick(item._product.photo_url!)}
              className="w-14 h-14 object-cover rounded-lg border border-[#e8e0d6] flex-shrink-0 cursor-pointer active:opacity-70 transition-opacity"
              style={{ minWidth: '56px', minHeight: '56px' }}
            />
          : <div className="w-14 h-14 bg-[#f0ece6] rounded-lg flex items-center justify-center flex-shrink-0">
              <ImageIcon className="w-5 h-5 text-[#c8bdb5]" />
            </div>
        }
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="text-[11px] text-[#8b6914] font-mono font-semibold">{item.product_code}</span>
              <p className="text-xs font-semibold text-[#2c2420] leading-snug mt-0.5 line-clamp-2">{item._product.description}</p>
              {item._product.observacao && (
                <p className="text-[10px] text-[#8b6914] italic mt-0.5 line-clamp-2">{item._product.observacao}</p>
              )}
            </div>
            <button
              onClick={() => onRemove(item.product_code)}
              className="text-[#c8bdb5] active:text-red-500 transition-colors w-11 h-11 flex items-center justify-center flex-shrink-0"
              style={{ touchAction: 'manipulation' }}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
          <OptionalSelectors item={item} allOptionals={allOptionals} onChange={onOptChange} />
        </div>
      </div>

      {/* Bottom: qty +/- | price / discount / subtotal */}
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#f0ece6]">
        {/* Qty stepper */}
        <div className="flex items-center gap-0 border border-[#e8e0d6] rounded-lg overflow-hidden">
          <button
            onClick={() => onQtyChange(item.product_code, Math.max(1, item.qty - 1))}
            className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:bg-[#f0ece6] transition-colors"
            style={{ touchAction: 'manipulation' }}
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <span className="w-9 text-center text-sm font-semibold text-[#2c2420]">{item.qty}</span>
          <button
            onClick={() => onQtyChange(item.product_code, item.qty + 1)}
            className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:bg-[#f0ece6] transition-colors"
            style={{ touchAction: 'manipulation' }}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Pricing */}
        <div className="text-right">
          {hasDiscount && (
            <p className="text-[10px] text-[#c8bdb5] line-through"><SafePrice value={effectivePrice(item._product, priceProfile) * item.qty} /></p>
          )}
          {hasDiscount && (
            <span className="text-[10px] bg-[#8b6914]/10 text-[#8b6914] font-semibold px-1.5 py-0.5 rounded-full">
              -{item.discount}%
            </span>
          )}
          <p className="text-sm font-bold text-[#2c2420] mt-0.5"><SafePrice value={subtotal} /></p>
        </div>
      </div>
    </div>
  )
}

// ── Formulário de configuração (usado no aside e no drawer) ───────────────────

function LockedField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">{label}</span>
      <div className="flex items-center gap-2 bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg px-3 py-2 h-[36px]">
        <Lock className="w-3 h-3 text-[#c8bdb5] flex-shrink-0" />
        <span className="text-sm font-medium text-[#2c2420] truncate flex-1">{value}</span>
      </div>
    </div>
  )
}

function OrderForm({
  reps, clients, selectedRep, selectedClient, notes,
  onRepChange, onClientChange, onNotesChange,
  onQuickAddRep, onQuickAddClient,
  budgetCode, cart, onSubmit, isGenerating,
  repLocked, clientLocked,
  editMode, editCode,
}: {
  reps: Representative[]; clients: Client[]
  selectedRep: Representative | null; selectedClient: Client | null; notes: string
  onRepChange: (r: Representative | null) => void
  onClientChange: (c: Client | null) => void
  onNotesChange: (n: string) => void
  onQuickAddRep: () => void; onQuickAddClient: () => void
  budgetCode: string; cart: CartItem[]
  onSubmit: () => void; isGenerating: boolean
  repLocked?: boolean; clientLocked?: boolean
  editMode?: boolean; editCode?: string
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-[#f3ede6]">
        <h2 className="text-base font-semibold text-[#2c2420]">{editMode ? 'Editar Pedido' : 'Novo Orçamento'}</h2>
        <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold tracking-wider ${editMode ? 'bg-[#8b6914]/10 text-[#8b6914]' : 'bg-[#648261]/10 text-[#648261]'}`}>
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
          <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Representante</span>
          <Autocomplete
            searchPlaceholder="Buscar representante..."
            items={reps}
            value={selectedRep}
            getLabel={(r) => `${r.name} — ${r.city}/${r.state}`}
            getSearch={(r) => `${r.name} ${r.email} ${r.city}`}
            onChange={onRepChange}
            onClear={() => onRepChange(null)}
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
          <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Cliente</span>
          {repLocked && clients.length === 0 ? (
            <div className="flex items-start gap-2 bg-[#fef3f2] border border-red-200 rounded-lg px-3 py-2.5">
              <span className="text-[11px] text-red-700 leading-snug">Nenhum cliente vinculado à sua conta. Solicite ao administrador para associar clientes ao seu perfil.</span>
            </div>
          ) : (
            <Autocomplete
              searchPlaceholder="Buscar cliente..."
              items={clients}
              value={selectedClient}
              getLabel={(c) => `${c.name} — ${c.city}/${c.state}`}
              getSearch={(c) => `${c.name} ${c.email} ${c.city}`}
              onChange={onClientChange}
              onClear={() => onClientChange(null)}
              displayPlaceholder="Selecione o cliente..."
              showQuickAdd
              onQuickAdd={onQuickAddClient}
            />
          )}
        </div>
      )}

      <div className="space-y-1">
        <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Observações</span>
        <textarea
          className="input resize-none text-xs"
          rows={3}
          placeholder="Observações do orçamento..."
          value={notes}
          onChange={(e) => onNotesChange(e.target.value)}
        />
      </div>


      {(!selectedClient || cart.length === 0) && !isGenerating && (
        <p className="text-[10px] text-[#9d8d81] text-center -mt-1">
          {cart.length === 0 ? 'Adicione ao menos um produto ao orçamento.' : 'Selecione um cliente para continuar.'}
        </p>
      )}
      <button
        onClick={onSubmit}
        disabled={!selectedClient || cart.length === 0 || isGenerating}
        style={{ touchAction: 'manipulation' }}
        className="w-full py-3.5 rounded-lg text-xs font-bold tracking-widest text-white transition-all bg-[#8b6914] hover:bg-[#725510] disabled:bg-[#c8bdb5] disabled:cursor-not-allowed uppercase shadow-sm active:scale-[0.98] active:opacity-85"
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
      <div className="fixed inset-0 bg-[#1a1410]/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full bg-white rounded-t-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#e8e0d6]">
          <span className="text-sm font-semibold text-[#2c2420]">Configurar Orçamento</span>
          <button onClick={onClose} className="w-11 h-11 flex items-center justify-center text-[#9d8d81]">
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
  const { data: products = [] } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: orders = [] } = useOrders()
  const { data: editOrder } = useOrder(editId ?? '')
  const createOrderM = useCreateOrder()
  const updateOrderM = useUpdateOrder()
  const createClientM = useCreateClient()
  const createRepM = useCreateRepresentative()

  // Locking flags
  const isRep = user?.role === 'representante'
  // vendedor criado de um cliente tem linked_id preenchido
  const isClientUser = user?.role === 'vendedor' && !!user?.linked_id
  const repLocked = isRep || isClientUser
  const clientLocked = isClientUser

  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  // Perfil de faturamento do cliente selecionado; sem cliente, usa lojista (Bloco 62)
  const priceProfile = selectedClient?.price_profile ?? 'lojista'
  const [selectedRep, setSelectedRep] = useState<Representative | null>(null)
  const [notes, setNotes] = useState('')
  const [cart, setCart] = useState<CartItem[]>(() => {
    try {
      const raw = localStorage.getItem('carrinho_orcamento')
      if (!raw) return []
      const parsed = JSON.parse(raw) as CartItem[]
      const productMap = new Map(products.map(p => [p.product_code, p]))
      return parsed.filter(i => productMap.has(i.product_code)).map(i => ({
        ...i,
        _product: productMap.get(i.product_code)!,
      }))
    } catch { return [] }
  })

  useEffect(() => {
    // Persiste apenas os dados próprios do carrinho; _product é derivado de products
    // e re-hidratado no load — não deve ser a fonte da verdade persistida (V-M8).
    const serializable = cart.map(({ _product, ...rest }) => rest)
    localStorage.setItem('carrinho_orcamento', JSON.stringify(serializable))
  }, [cart])

  // Sincroniza _product com dados frescos da API (garante observacao e preço atualizados)
  useEffect(() => {
    if (products.length === 0) return
    const productMap = new Map(products.map(p => [p.product_code, p]))
    setCart(prev => prev.map(item => ({
      ...item,
      _product: productMap.get(item.product_code) ?? item._product,
    })))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [products])

  // Pré-preenche e trava campos conforme papel do usuário logado
  useEffect(() => {
    if (!user) return

    if (isRep && user.rep_id && reps.length > 0) {
      const myRep = reps.find(r => r.id === user.rep_id)
      if (myRep) setSelectedRep(myRep)
    }

    if (isClientUser && user.linked_id && clients.length > 0) {
      const myClient = clients.find(c => c.id === user.linked_id)
      if (myClient) {
        setSelectedClient(myClient)
        if (myClient.rep_id && reps.length > 0) {
          const myRep = reps.find(r => r.id === myClient.rep_id)
          if (myRep) setSelectedRep(myRep)
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, reps, clients])

  // Pre-populate cart + client + rep when editing an existing order
  useEffect(() => {
    if (!editOrder || products.length === 0 || clients.length === 0) return
    const productMap = new Map(products.map(p => [p.product_code, p]))
    const cartItems: CartItem[] = editOrder.items
      .map(item => {
        const product = productMap.get(item.product_code)
        if (!product) return null
        return {
          product_code: item.product_code,
          qty: item.qty,
          discount: Number(item.discount),
          opt_categories: parseOptFields(item),
          _product: product,
        }
      })
      .filter(Boolean) as CartItem[]
    setCart(cartItems)
    const client = clients.find(c => c.id === editOrder.client_id)
    if (client) setSelectedClient(client)
    if (editOrder.rep_id) {
      const rep = reps.find(r => r.id === editOrder.rep_id)
      if (rep) setSelectedRep(rep)
    }
    setNotes(editOrder.notes ?? '')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editOrder, products, clients, reps])

  const [productQuery, setProductQuery] = useState('')
  const [productOpen, setProductOpen] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [cartFilter, setCartFilter] = useState('')
  const [toast, setToast] = useState<{ message: string; variant: 'success' | 'error' } | null>(null)
  const [quickModal, setQuickModal] = useState<'client' | 'rep' | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const productRef = useRef<HTMLDivElement>(null)

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
    if (!selectedProduct) return
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

  const nextOrderNumber = orders.length + 1
  const budgetCode = `ORC-${String(nextOrderNumber).padStart(4, '0')}`

  const itemsPayload = cart.map(({ product_code, qty, discount, opt_categories }) => ({
    product_code,
    qty,
    discount: discount || 0,
    ...computeOptFields(opt_categories),
  }))

  async function handleSubmit() {
    if (!selectedClient || cart.length === 0) return
    setIsGenerating(true)
    try {
      if (editId) {
        await Promise.all([
          updateOrderM.mutateAsync({
            id: editId,
            data: {
              rep_id: selectedRep?.id ?? null,
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
            rep_id: selectedRep?.id ?? null,
            notes: notes || null,
            items: itemsPayload,
          }),
          new Promise<void>((r) => setTimeout(r, 3000)),
        ])
        setToast({ message: 'Orçamento finalizado com sucesso!', variant: 'success' })
      }
      setCart([])
      localStorage.removeItem('carrinho_orcamento')
      setSelectedClient(null)
      setSelectedRep(null)
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
      <span className="text-[10px] font-bold text-[#8b6914] uppercase tracking-wider block">Adicionar Produto</span>
      <div ref={productRef} className="relative">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#a89a8e]" />
          <input
            className="input pl-8 w-full text-xs bg-white border border-[#e8e0d6] rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#8b6914]"
            placeholder="Buscar produto por codigo ou desc"
            value={productQuery}
            onChange={(e) => { setProductQuery(e.target.value); setProductOpen(true) }}
            onFocus={() => setProductOpen(true)}
          />
        </div>
        {productOpen && filteredProducts.length > 0 && (
          <ul className="absolute left-0 right-0 z-30 mt-1 bg-white border border-[#e8e0d6] rounded-xl overflow-hidden shadow-xl max-h-52 overflow-y-auto">
            {filteredProducts.slice(0, 15).map((p) => (
              <li
                key={p.id}
                className="px-3 py-2 text-xs hover:bg-[#f8f6f2] cursor-pointer flex items-center gap-2 transition-colors border-b border-[#fbfaf9]"
                onMouseDown={() => { setSelectedProduct(p); setProductQuery(''); setProductOpen(false) }}
              >
                {p.photo_url
                  ? <img src={p.photo_url} alt="" className="w-8 h-8 rounded object-cover border border-[#e8e0d6] flex-shrink-0" />
                  : <ImageIcon className="w-8 h-8 text-[#c8bdb5] flex-shrink-0" />}
                <div className="truncate">
                  <span className="text-[#8b6914] font-mono font-medium">{p.product_code}</span>
                  <span className="text-[#2c2420] ml-1.5 font-medium">{p.description}</span>
                  <div className="text-[9px] text-[#9d8d81]">{dimLabel(p)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {selectedProduct && (
        <div className="bg-white border border-[#e8dccb] rounded-lg p-2.5 flex gap-2.5 shadow-sm relative">
          <button type="button" onClick={() => setSelectedProduct(null)}
            className="absolute top-1.5 right-1.5 text-[#9d8d81] hover:text-red-500 transition-colors w-7 h-7 flex items-center justify-center">
            <X className="w-3.5 h-3.5" />
          </button>
          {selectedProduct.photo_url
            ? <img src={selectedProduct.photo_url} alt="" onClick={() => setActivePhotoModal(selectedProduct.photo_url!)}
                className="w-12 h-12 object-cover rounded border border-[#e8e0d6] flex-shrink-0 cursor-pointer hover:opacity-80 transition-opacity" />
            : <div className="w-12 h-12 bg-[#f0ece6] rounded flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-[#c8bdb5]" /></div>
          }
          <div className="text-[11px] pr-5 flex-1 min-w-0">
            <p className="text-[#8b6914] font-mono font-semibold">{selectedProduct.product_code}</p>
            <p className="text-[#2c2420] font-medium truncate">{selectedProduct.description}</p>
            <p className="text-[#8b6914] font-bold mt-0.5"><SafePrice value={selectedProduct.price} /></p>
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={handleAddProductToCart}
        disabled={!selectedProduct}
        style={{ touchAction: 'manipulation' }}
        className="w-full py-2.5 rounded-lg text-xs font-semibold tracking-wider text-white transition-all bg-[#8b6914] hover:bg-[#725510] disabled:bg-[#c8bdb5] disabled:cursor-not-allowed flex items-center justify-center gap-1.5 shadow-sm active:scale-[0.98]"
      >
        ADICIONAR AO ORÇAMENTO
      </button>
    </div>
  )

  return (
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420]">
      {editId && editOrder && (
        <div className="bg-[#8b6914] text-white px-4 lg:px-8 py-2.5 flex items-center gap-2.5">
          <PenLine className="w-4 h-4 flex-shrink-0" />
          <span className="text-xs font-semibold tracking-wide">
            Editando Pedido: <span className="font-mono">{editOrder.code}</span>
          </span>
          <button
            onClick={() => { setSearchParams({}); setCart([]); localStorage.removeItem('carrinho_orcamento') }}
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
        <main className="bg-white border border-[#e8e0d6] rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[400px] lg:min-h-[550px]">
          <div className="px-4 lg:px-6 py-3.5 lg:py-4 border-b border-[#e8e0d6] flex items-center justify-between bg-white flex-shrink-0">
            <h2 className="text-sm font-semibold text-[#8b6914] uppercase tracking-wider flex items-center gap-2">
              <ShoppingCart className="w-4 h-4" /> Itens do Orçamento
            </h2>
            <div className="flex items-center gap-2">
              {cart.length > 0 && (
                <button
                  onClick={() => { setCart([]); localStorage.removeItem('carrinho_orcamento') }}
                  className="text-xs text-[#b25e50] hover:text-[#8a3a2e] border border-[#f0c8c0] hover:border-[#b25e50] px-2.5 py-1.5 rounded-lg transition-colors"
                  style={{ touchAction: 'manipulation' }}
                >
                  Limpar
                </button>
              )}
              <div className="relative w-36 lg:w-52">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#a89a8e]" />
                <input
                  className="input pl-8 w-full text-xs border border-[#e8e0d6] rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#8b6914] bg-white"
                  placeholder="Buscar..."
                  value={cartFilter}
                  onChange={(e) => setCartFilter(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {filteredCart.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-[#9d8d81] space-y-3">
                <Clipboard className="w-10 h-10 text-[#c8bdb5] stroke-[1.2]" />
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
                    />
                  ))}
                </div>

                {/* ── Desktop table ────────────────────────────── */}
                <table className="hidden lg:table w-full text-sm">
                  <thead className="bg-[#fbfaf8] text-xs text-[#9d8d81] uppercase font-semibold border-b border-[#e8e0d6] sticky top-0 z-10">
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
                  <tbody className="divide-y divide-[#e8e0d6]">
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
                                    className="object-cover rounded-lg border border-[#e8e0d6] cursor-pointer hover:opacity-80 transition-opacity"
                                    style={{ width: '48px', height: '48px', minWidth: '48px', minHeight: '48px' }} />
                                : <div className="bg-[#f0ece6] rounded-lg flex items-center justify-center"
                                    style={{ width: '48px', height: '48px', minWidth: '48px', minHeight: '48px' }}>
                                    <ImageIcon className="w-5 h-5 text-[#c8bdb5]" />
                                  </div>
                              }
                              <div className="flex-1 min-w-0">
                                <span className="text-[#8b6914] font-mono font-semibold">{item.product_code}</span>
                                <span className="text-[#2c2420] ml-2 text-xs font-semibold">{item._product.description}</span>
                                {item._product.observacao && (
                                  <div className="text-[10px] text-[#8b6914] italic mt-0.5">{item._product.observacao}</div>
                                )}
                                <div className="text-[10px] text-[#9d8d81] mt-0.5">{dimLabel(item._product)}</div>
                                <OptionalSelectors item={item} allOptionals={allOptionals} onChange={(cat, val) => updateOptCategory(item.product_code, cat, val)} />
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 align-middle">
                            <input
                              type="number" min={1}
                              className="input w-16 text-center text-xs border border-[#e8e0d6] rounded-lg py-1 bg-white text-[#2c2420]"
                              value={item.qty}
                              onChange={(e) => updateQty(item.product_code, Number(e.target.value))}
                            />
                          </td>
                          <td className="px-4 py-3.5 text-[#4a3f38] text-xs font-semibold whitespace-nowrap align-middle">
                            <SafePrice value={effectivePrice(item._product, priceProfile)} />
                          </td>
                          <td className="px-4 py-3.5 align-middle">
                            <input
                              type="number" min={0} max={100}
                              className="input w-16 text-center text-xs border border-[#e8e0d6] rounded-lg px-1.5 py-1 bg-white text-[#2c2420]"
                              value={item.discount === 0 ? '' : item.discount}
                              placeholder="0"
                              onChange={(e) => {
                                const val = Math.min(100, Math.max(0, Number(e.target.value) || 0))
                                setCart((prev) => prev.map((i) => i.product_code === item.product_code ? { ...i, discount: val } : i))
                              }}
                            />
                            {item.discount > 0 && (
                              <p className="text-[9px] text-[#9d8d81] mt-0.5 text-center whitespace-nowrap">
                                <SafePrice value={effectivePrice(item._product, priceProfile) * item.discount / 100} prefix="− R$ " />
                              </p>
                            )}
                          </td>
                          <td className="px-4 py-3.5 text-right align-middle whitespace-nowrap">
                            {ipiRate > 0
                              ? <span className="text-xs font-semibold text-[#8b6914]">{ipiRate}%</span>
                              : <span className="text-xs text-[#c8bdb5]">—</span>
                            }
                          </td>
                          <td className="px-4 py-3.5 text-right text-xs font-bold text-[#2c2420] align-middle whitespace-nowrap">
                            <SafePrice value={subtotalWithIpi} />
                          </td>
                          <td className="px-4 py-3.5 align-middle text-center">
                            <button onClick={() => removeItem(item.product_code)} className="text-[#c8bdb5] hover:text-red-500 transition-colors w-8 h-8 flex items-center justify-center mx-auto">
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
            <div className="hidden lg:flex bg-[#fbfaf8] border-t border-[#e8e0d6] px-6 py-4 justify-between items-center flex-shrink-0">
              <div className="flex gap-4 text-xs text-[#8a7a6e]">
                <div><span>Itens: </span><span className="font-semibold text-[#2c2420]">{cart.reduce((s, i) => s + i.qty, 0)}</span></div>
                <div><span>Produtos: </span><span className="font-semibold text-[#2c2420]">{cart.length}</span></div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#2c2420] font-semibold text-xs uppercase tracking-wider">Total do Orçamento:</span>
                <span className="text-[#8b6914] font-bold text-base"><SafePrice value={totalWithIpi} /></span>
              </div>
            </div>
          )}
        </main>

        {/* ── Desktop Sidebar (hidden on mobile) ───────────────────────── */}
        <aside className="hidden lg:block space-y-5">
          <div className="bg-white border border-[#e8e0d6] rounded-xl p-5 shadow-sm space-y-4">
            <OrderForm
              reps={reps} clients={clients}
              selectedRep={selectedRep} selectedClient={selectedClient} notes={notes}
              onRepChange={setSelectedRep} onClientChange={setSelectedClient} onNotesChange={setNotes}
              onQuickAddRep={() => setQuickModal('rep')} onQuickAddClient={() => setQuickModal('client')}
              budgetCode={budgetCode} cart={cart}
              onSubmit={handleSubmit} isGenerating={isGenerating}
              repLocked={repLocked} clientLocked={clientLocked}
              editMode={!!editId} editCode={editOrder?.code}
            />
            {productSearchCard}
          </div>
        </aside>
      </div>

      {/* ── Mobile fixed bottom bar ────────────────────────────────────────── */}
      <div className="lg:hidden fixed bottom-16 inset-x-0 z-30 px-4 pb-2">
        <button
          onClick={() => setDrawerOpen(true)}
          style={{ touchAction: 'manipulation' }}
          className="w-full flex items-center justify-between bg-[#8b6914] text-white px-5 py-3.5 rounded-xl shadow-xl active:scale-[0.98] active:opacity-90 transition-all"
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
        <OrderForm
          reps={reps} clients={clients}
          selectedRep={selectedRep} selectedClient={selectedClient} notes={notes}
          onRepChange={setSelectedRep} onClientChange={setSelectedClient} onNotesChange={setNotes}
          onQuickAddRep={() => { setDrawerOpen(false); setQuickModal('rep') }}
          onQuickAddClient={() => { setDrawerOpen(false); setQuickModal('client') }}
          budgetCode={budgetCode} cart={cart}
          onSubmit={handleSubmit} isGenerating={isGenerating}
          repLocked={repLocked} clientLocked={clientLocked}
          editMode={!!editId} editCode={editOrder?.code}
        />
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
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#1a1410]/88 backdrop-blur-sm">
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
            Gerando Orçamento
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
    </div>
  )
}
