import { useState, useRef, useEffect } from 'react'
import { Search, Plus, X, Trash2, ShoppingCart, CheckCircle, ImageIcon } from 'lucide-react'
import { useProducts } from '../hooks/useProducts'
import { useClients, useCreateClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative } from '../hooks/useRepresentatives'
import { useCreateOrder } from '../hooks/useOrders'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import type { Product, OptionalColor, Client, Representative, ClientCreate } from '../types'

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

// Pairs that cannot coexist (each pair shares the same DB field)
const EXCLUSIVE_PAIRS: [string, string][] = [
  ['madeira_teka', 'madeira_freijo'],
  ['tecido_faixa_1', 'tecido_faixa_2'],
  ['couro_soleta', 'couro_pele'],
]

// Compute stored DB fields from per-category selections
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

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number) {
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function dimLabel(p: Product) {
  return p.is_circular
    ? `Ø ${p.largura} × A ${p.altura} cm`
    : `L ${p.largura} × P ${p.profundidade} × A ${p.altura} cm`
}

// ── Autocomplete genérico ─────────────────────────────────────────────────────

function Autocomplete<T extends { id: string }>({
  placeholder, items, value, getLabel, getSearch, onChange, onClear,
}: {
  placeholder: string; items: T[]; value: T | null
  getLabel: (item: T) => string; getSearch: (item: T) => string
  onChange: (item: T) => void; onClear: () => void
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

  if (value) {
    return (
      <div className="input flex items-center justify-between">
        <span className="text-[#2c2420] truncate">{getLabel(value)}</span>
        <button type="button" onClick={onClear} className="text-[#9d8d81] hover:text-[#2c2420] ml-2 flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a89a8e]" />
        <input
          className="input pl-9"
          placeholder={placeholder}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
        />
      </div>
      {open && filtered.length > 0 && (
        <ul className="absolute z-30 w-full mt-1 bg-white border border-[#e8e0d6] rounded-xl overflow-hidden shadow-xl max-h-52 overflow-y-auto">
          {filtered.slice(0, 20).map((item) => (
            <li key={item.id} className="px-4 py-2.5 text-sm text-[#2c2420] hover:bg-[#f8f6f2] cursor-pointer"
              onMouseDown={() => { onChange(item); setQuery(''); setOpen(false) }}>
              {getLabel(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Modal de cadastro rápido ──────────────────────────────────────────────────

const EMPTY_PERSON: ClientCreate = {
  name: '', phone: '', email: '', cep: '', numero: '', address: '', city: '', state: '',
}

function QuickRegisterModal({ title, onSave, onClose }: {
  title: string; onSave: (data: ClientCreate) => Promise<void>; onClose: () => void
}) {
  const [form, setForm] = useState<ClientCreate>(EMPTY_PERSON)
  const [saving, setSaving] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)

  async function handleCepBlur() {
    const clean = form.cep.replace(/\D/g, '')
    if (clean.length !== 8) return
    setCepLoading(true)
    try {
      const r = await fetch(`https://viacep.com.br/ws/${clean}/json/`)
      const data = await r.json()
      if (!data.erro) {
        setForm((f) => ({
          ...f,
          address: `${data.logradouro}${data.bairro ? ', ' + data.bairro : ''}`,
          city: data.localidade,
          state: data.uf,
        }))
      }
    } finally { setCepLoading(false) }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setSaving(true)
    try { await onSave(form); onClose() } finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-[#2c2420]">{title}</h3>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420]"><X className="w-5 h-5" /></button>
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
  unit_price: number
  // per-category selections; DB fields derived via computeOptFields() at submit
  opt_categories: Partial<Record<string, string>>
  _product: Product
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000)
    return () => clearTimeout(t)
  }, [onDone])
  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-white border border-green-200 text-green-700 px-5 py-3 rounded-xl shadow-xl toast">
      <CheckCircle className="w-5 h-5" />
      <span className="text-sm font-medium">{message}</span>
    </div>
  )
}

// ── Optional selectors for a cart item ───────────────────────────────────────

function OptionalSelectors({ item, onCategoryChange }: {
  item: CartItem
  onCategoryChange: (category: string, color: string | null) => void
}) {
  // Build per-category map, preserving order of first occurrence
  const catMap: Record<string, OptionalColor[]> = {}
  const catOrder: string[] = []
  for (const opt of item._product.optionals) {
    if (!catMap[opt.category]) { catMap[opt.category] = []; catOrder.push(opt.category) }
    catMap[opt.category].push(opt)
  }
  if (catOrder.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 mt-1.5">
      {catOrder.map((cat) => {
        const opts = catMap[cat]
        const current = item.opt_categories[cat] ?? null
        const selectedOpt = current ? (opts.find(o => o.color_name === current) ?? null) : null
        return (
          <div key={cat} className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] text-[#9d8d81] whitespace-nowrap">{CAT_LABEL[cat] ?? cat}:</span>
            <select
              className="text-xs border border-[#e8e0d6] rounded-lg px-1.5 py-0.5 bg-white text-[#2c2420] focus:outline-none focus:ring-1 focus:ring-[#8b6914]"
              value={current ?? ''}
              onChange={(e) => onCategoryChange(cat, e.target.value || null)}
            >
              <option value="">—</option>
              {opts.map((opt) => (
                <option key={opt.id} value={opt.color_name}>{opt.color_name}</option>
              ))}
            </select>
            {selectedOpt && (
              <OptionalWithPreview label={selectedOpt.color_name} swatch={selectedOpt.photo_url} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function OrcamentoPage() {
  const { data: products = [] } = useProducts()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const createOrderM = useCreateOrder()
  const createClientM = useCreateClient()
  const createRepM = useCreateRepresentative()

  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [selectedRep, setSelectedRep] = useState<Representative | null>(null)
  const [notes, setNotes] = useState('')
  const [cart, setCart] = useState<CartItem[]>([])
  const [productQuery, setProductQuery] = useState('')
  const [productOpen, setProductOpen] = useState(false)
  const [previewProduct, setPreviewProduct] = useState<Product | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [quickModal, setQuickModal] = useState<'client' | 'rep' | null>(null)
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

  function addToCart(p: Product) {
    setCart((prev) => {
      const existing = prev.find((i) => i.product_code === p.product_code)
      if (existing) return prev.map((i) => i.product_code === p.product_code ? { ...i, qty: i.qty + 1 } : i)
      return [...prev, {
        product_code: p.product_code, qty: 1, unit_price: 0,
        opt_categories: {},
        _product: p,
      }]
    })
    setProductQuery('')
    setProductOpen(false)
    setPreviewProduct(p)
  }

  function updateQty(code: string, qty: number) {
    if (qty < 1) return
    setCart((prev) => prev.map((i) => i.product_code === code ? { ...i, qty } : i))
  }

  function updatePrice(code: string, unit_price: number) {
    setCart((prev) => prev.map((i) => i.product_code === code ? { ...i, unit_price } : i))
  }

  function updateOptionalCategory(code: string, category: string, color: string | null) {
    setCart((prev) => prev.map((item) => {
      if (item.product_code !== code) return item
      const cats = { ...item.opt_categories }
      if (color) {
        cats[category] = color
        // Enforce mutual exclusion within the same DB field
        for (const [a, b] of EXCLUSIVE_PAIRS) {
          if (category === a) delete cats[b]
          if (category === b) delete cats[a]
        }
      } else {
        delete cats[category]
      }
      return { ...item, opt_categories: cats }
    }))
  }

  function removeItem(code: string) {
    setCart((prev) => prev.filter((i) => i.product_code !== code))
    if (previewProduct?.product_code === code) setPreviewProduct(null)
  }

  const total = cart.reduce((sum, i) => sum + i.qty * i.unit_price, 0)

  async function handleSubmit() {
    if (!selectedClient || cart.length === 0) return
    await createOrderM.mutateAsync({
      client_id: selectedClient.id,
      rep_id: selectedRep?.id ?? null,
      notes: notes || null,
      items: cart.map(({ product_code, qty, unit_price, opt_categories }) => ({
        product_code, qty, unit_price,
        ...computeOptFields(opt_categories),
      })),
    })
    setCart([])
    setSelectedClient(null)
    setSelectedRep(null)
    setNotes('')
    setPreviewProduct(null)
    setToast('Orçamento finalizado com sucesso!')
  }

  return (
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420]">
      <div className="max-w-7xl mx-auto px-8 py-6 grid grid-cols-3 gap-6">
        {/* ── Coluna esquerda ─────────────────────────────────── */}
        <div className="col-span-2 space-y-6">

          {/* Cliente */}
          <section className="card-section space-y-3">
            <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">Cliente</h2>
            <div className="flex gap-2">
              <div className="flex-1">
                <Autocomplete
                  placeholder="Buscar cliente..."
                  items={clients}
                  value={selectedClient}
                  getLabel={(c) => `${c.name} — ${c.city}/${c.state}`}
                  getSearch={(c) => `${c.name} ${c.email} ${c.city}`}
                  onChange={setSelectedClient}
                  onClear={() => setSelectedClient(null)}
                />
              </div>
              <button type="button" title="Novo cliente" className="btn-secondary px-3" onClick={() => setQuickModal('client')}>
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </section>

          {/* Representante */}
          <section className="card-section space-y-3">
            <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">
              Representante <span className="text-[#c8bdb5] font-normal normal-case">(opcional)</span>
            </h2>
            <div className="flex gap-2">
              <div className="flex-1">
                <Autocomplete
                  placeholder="Buscar representante..."
                  items={reps}
                  value={selectedRep}
                  getLabel={(r) => `${r.name} — ${r.city}/${r.state}`}
                  getSearch={(r) => `${r.name} ${r.email} ${r.city}`}
                  onChange={setSelectedRep}
                  onClear={() => setSelectedRep(null)}
                />
              </div>
              <button type="button" title="Novo representante" className="btn-secondary px-3" onClick={() => setQuickModal('rep')}>
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </section>

          {/* Busca de produto */}
          <section className="card-section space-y-3">
            <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">Adicionar Produto</h2>
            <div ref={productRef} className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a89a8e]" />
              <input
                className="input pl-9"
                placeholder="Código ou descrição do produto..."
                value={productQuery}
                onChange={(e) => { setProductQuery(e.target.value); setProductOpen(true) }}
                onFocus={() => setProductOpen(true)}
              />
              {productOpen && filteredProducts.length > 0 && (
                <ul className="absolute z-30 w-full mt-1 bg-white border border-[#e8e0d6] rounded-xl overflow-hidden shadow-xl max-h-60 overflow-y-auto">
                  {filteredProducts.slice(0, 15).map((p) => (
                    <li
                      key={p.id}
                      className="px-4 py-3 text-sm hover:bg-[#f8f6f2] cursor-pointer flex items-center gap-3"
                      onMouseDown={() => addToCart(p)}
                    >
                      {p.photo_url
                        ? <img src={p.photo_url} alt="" className="w-8 h-8 rounded object-cover border border-[#e8e0d6] flex-shrink-0" />
                        : <ImageIcon className="w-8 h-8 text-[#c8bdb5] flex-shrink-0" />}
                      <div>
                        <span className="text-[#8b6914] font-mono">{p.product_code}</span>
                        <span className="text-[#2c2420] ml-2">{p.description}</span>
                        <div className="text-xs text-[#9d8d81] mt-0.5">{dimLabel(p)}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Preview do produto */}
            {previewProduct && (
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-xl p-4 flex gap-4">
                {previewProduct.photo_url
                  ? <img src={previewProduct.photo_url} alt="" className="w-20 h-20 object-cover rounded-lg border border-[#e8e0d6] flex-shrink-0" />
                  : <div className="w-20 h-20 bg-[#f0ece6] rounded-lg flex items-center justify-center flex-shrink-0"><ImageIcon className="w-8 h-8 text-[#c8bdb5]" /></div>
                }
                <div className="text-sm">
                  <p className="text-[#8b6914] font-mono font-medium">{previewProduct.product_code}</p>
                  <p className="text-[#2c2420] font-medium mt-0.5">{previewProduct.description}</p>
                  <p className="text-[#8a7a6e] mt-1">{dimLabel(previewProduct)}</p>
                  {previewProduct.optionals.length > 0 && (
                    <p className="text-[#9d8d81] text-xs mt-1">
                      {previewProduct.optionals.map((o) => o.color_name).join(' · ')}
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Carrinho */}
          {cart.length > 0 && (
            <section className="bg-white border border-[#e8e0d6] rounded-xl overflow-hidden shadow-sm">
              <div className="px-5 py-4 border-b border-[#e8e0d6] flex items-center gap-2">
                <ShoppingCart className="w-4 h-4 text-[#8b6914]" />
                <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">Itens do Orçamento</h2>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-[#f0ece6]">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs text-[#9d8d81] uppercase">Produto</th>
                    <th className="px-4 py-3 text-left text-xs text-[#9d8d81] uppercase w-16">Qtd</th>
                    <th className="px-4 py-3 text-left text-xs text-[#9d8d81] uppercase w-32">Valor Unit. (R$)</th>
                    <th className="px-4 py-3 text-right text-xs text-[#9d8d81] uppercase w-28">Subtotal</th>
                    <th className="px-4 py-3 w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {cart.map((item) => (
                    <tr key={item.product_code} className="border-t border-[#e8e0d6] hover:bg-[#f8f6f2] align-top">
                      <td className="px-4 py-3">
                        <div>
                          <span className="text-[#8b6914] font-mono">{item.product_code}</span>
                          <span className="text-[#4a3f38] ml-2 text-xs">{item._product.description}</span>
                        </div>
                        <OptionalSelectors
                          item={item}
                          onCategoryChange={(cat, color) => updateOptionalCategory(item.product_code, cat, color)}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="number" min={1}
                          className="input w-16 text-center"
                          value={item.qty}
                          onChange={(e) => updateQty(item.product_code, Number(e.target.value))}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="number" min={0} step={0.01}
                          className="input w-32 text-right"
                          placeholder="0,00"
                          value={item.unit_price === 0 ? '' : item.unit_price}
                          onChange={(e) => updatePrice(item.product_code, Number(e.target.value))}
                        />
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-[#2c2420] align-middle">
                        R$ {fmt(item.qty * item.unit_price)}
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <button onClick={() => removeItem(item.product_code)} className="text-[#c8bdb5] hover:text-red-500 transition-colors">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* Observações */}
          <section className="bg-white border border-[#e8e0d6] rounded-xl p-5 space-y-2 shadow-sm">
            <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">Observações</h2>
            <textarea
              className="input resize-none"
              rows={3}
              placeholder="Informações adicionais sobre o pedido..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </section>
        </div>

        {/* ── Coluna direita: resumo ────────────────────────────── */}
        <div className="space-y-4">
          <div className="bg-white border border-[#e8e0d6] rounded-xl p-5 sticky top-6 space-y-4 shadow-sm">
            <h2 className="text-sm font-semibold text-[#9d8d81] uppercase tracking-wider">Resumo</h2>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between text-[#8a7a6e]">
                <span>Itens</span>
                <span>{cart.reduce((s, i) => s + i.qty, 0)}</span>
              </div>
              <div className="flex justify-between text-[#8a7a6e]">
                <span>Produtos</span>
                <span>{cart.length}</span>
              </div>
              <div className="border-t border-[#e8e0d6] pt-3 flex justify-between">
                <span className="text-[#2c2420] font-semibold">Total</span>
                <span className="text-[#8b6914] font-bold text-lg">R$ {fmt(total)}</span>
              </div>
            </div>

            <button
              className="btn-primary w-full py-3 text-base disabled:opacity-40"
              disabled={!selectedClient || cart.length === 0 || createOrderM.isPending}
              onClick={handleSubmit}
            >
              {createOrderM.isPending ? 'Salvando...' : 'Finalizar Orçamento'}
            </button>

            {!selectedClient && (
              <p className="text-xs text-[#9d8d81] text-center">Selecione um cliente para finalizar</p>
            )}
            {selectedClient && cart.length === 0 && (
              <p className="text-xs text-[#9d8d81] text-center">Adicione pelo menos um produto</p>
            )}
          </div>
        </div>
      </div>

      {quickModal === 'client' && (
        <QuickRegisterModal
          title="Novo Cliente"
          onSave={async (data) => { await createClientM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}
      {quickModal === 'rep' && (
        <QuickRegisterModal
          title="Novo Representante"
          onSave={async (data) => { await createRepM.mutateAsync(data) }}
          onClose={() => setQuickModal(null)}
        />
      )}

      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </div>
  )
}
