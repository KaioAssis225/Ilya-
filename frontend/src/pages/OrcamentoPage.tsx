import { useState, useRef, useEffect } from 'react'
import { Search, Plus, X, Trash2, ShoppingCart, CheckCircle, ImageIcon, Clipboard } from 'lucide-react'
import { useProducts } from '../hooks/useProducts'
import { useClients, useCreateClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative } from '../hooks/useRepresentatives'
import { useCreateOrder, useOrders } from '../hooks/useOrders'
import { OptionalWithPreview } from '../components/OptionalWithPreview'
import type { Product, Client, Representative, ClientCreate } from '../types'

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

function fmtM(v: number) { return Number(v).toFixed(2).replace('.', ',') }

function dimLabel(p: Product) {
  return p.is_circular
    ? `Ø ${fmtM(p.largura)} × A ${fmtM(p.altura)} m`
    : `L ${fmtM(p.largura)} × P ${fmtM(p.profundidade)} × A ${fmtM(p.altura)} m`
}

// ── Autocomplete de 2 Etapas (mockup-style) ───────────────────────────────────

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
      {/* Parte 1: Display do valor selecionado */}
      <div className="flex gap-2">
        <div className="input flex items-center justify-between bg-[#fcfbfa] border border-[#e8e0d6] px-3 py-1.5 rounded-lg text-sm flex-1 min-w-0 h-[36px]">
          <span className={`${value ? 'text-[#2c2420] font-medium' : 'text-[#a89a8e]'} truncate flex-1 min-w-0`}>
            {value ? getLabel(value) : displayPlaceholder}
          </span>
          {value && (
            <button type="button" onClick={onClear} className="text-[#9d8d81] hover:text-[#2c2420] transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        {showQuickAdd && onQuickAdd && (
          <button type="button" onClick={onQuickAdd} className="btn-secondary px-2.5 flex-shrink-0 h-[36px] border border-[#e8e0d6] hover:bg-[#f8f6f2] rounded-lg transition-colors flex items-center justify-center">
            <Plus className="w-4 h-4 text-[#9d8d81]" />
          </button>
        )}
      </div>

      {/* Parte 2: Campo de Busca */}
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
              <li key={item.id} className="px-3 py-1.5 text-xs text-[#2c2420] hover:bg-[#f8f6f2] cursor-pointer transition-colors"
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
  unit_price: number // valor final recalculado pós desconto, a ser enviado para a API
  discount: number // desconto percentual (0 a 100)
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

// ── Opcionais estáticos do produto ───────────────────────────────────────────

function StaticOptionals({ item }: { item: CartItem }) {
  const entries = Object.entries(item.opt_categories)
  if (entries.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5 mt-1.5">
      {entries.map(([cat, color]) => {
        const opt = item._product.optionals.find(o => o.category === cat && o.color_name === color)
        return (
          <div key={cat} className="flex items-center gap-1 bg-[#fcfbfa] border border-[#f0ece6] rounded-md px-1.5 py-0.5">
            <span className="text-[10px] text-[#9d8d81] font-medium whitespace-nowrap">{CAT_LABEL[cat] ?? cat}:</span>
            <OptionalWithPreview label={color} swatch={opt?.photo_url ?? null} />
          </div>
        )
      })}
    </div>
  )
}

// ── Lightbox de foto do produto ────────────────────────────────────────────────

function PhotoLightbox({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#1a1410]/75 backdrop-blur-sm"
      onClick={onClose}>
      <div className="relative" onClick={(e) => e.stopPropagation()}>
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

// ── Main ──────────────────────────────────────────────────────────────────────

export default function OrcamentoPage() {
  const { data: products = [] } = useProducts()
  const { data: clients = [] } = useClients()
  const { data: reps = [] } = useRepresentatives()
  const { data: orders = [] } = useOrders()
  const createOrderM = useCreateOrder()
  const createClientM = useCreateClient()
  const createRepM = useCreateRepresentative()

  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
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
    localStorage.setItem('carrinho_orcamento', JSON.stringify(cart))
  }, [cart])

  // Estados para busca e inserção de produtos no card lateral
  const [productQuery, setProductQuery] = useState('')
  const [productOpen, setProductOpen] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [cartFilter, setCartFilter] = useState('')
  
  const [toast, setToast] = useState<string | null>(null)
  const [quickModal, setQuickModal] = useState<'client' | 'rep' | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [activePhotoModal, setActivePhotoModal] = useState<string | null>(null)
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

  // Adiciona ao carrinho o produto que foi selecionado no card lateral
  function handleAddProductToCart() {
    if (!selectedProduct) return
    // Auto-preenche opcionais: primeira cor de cada categoria do produto
    const auto_categories: Partial<Record<string, string>> = {}
    for (const opt of selectedProduct.optionals) {
      if (!(opt.category in auto_categories)) {
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
        unit_price: selectedProduct.price ?? 0,
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

  // Filtragem local de itens adicionados ao carrinho
  const filteredCart = cart.filter((item) =>
    `${item.product_code} ${item._product.description}`.toLowerCase().includes(cartFilter.toLowerCase())
  )

  // Cálculo total considerando o preço de catálogo fixo e o desconto de cada item
  const total = cart.reduce((sum, i) => {
    const subtotal = i.qty * i._product.price * (1 - (i.discount || 0) / 100)
    return sum + subtotal
  }, 0)

  // Cálculo do próximo número de orçamento (ORC-XXXX)
  const nextOrderNumber = orders.length + 1
  const budgetCode = `ORC-${String(nextOrderNumber).padStart(4, '0')}`

  async function handleSubmit() {
    if (!selectedClient || cart.length === 0) return
    setIsGenerating(true)
    try {
      await Promise.all([
        createOrderM.mutateAsync({
          client_id: selectedClient.id,
          rep_id: selectedRep?.id ?? null,
          notes: notes || null,
          items: cart.map(({ product_code, qty, discount, opt_categories, _product }) => {
            const basePrice = _product.price ?? 0
            const finalUnitPrice = basePrice * (1 - (discount || 0) / 100)
            return {
              product_code,
              qty,
              unit_price: finalUnitPrice,
              ...computeOptFields(opt_categories),
            }
          }),
        }),
        new Promise<void>((r) => setTimeout(r, 3000)),
      ])
      setCart([])
      localStorage.removeItem('carrinho_orcamento')
      setSelectedClient(null)
      setSelectedRep(null)
      setNotes('')
      setToast('Orçamento finalizado com sucesso!')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420]">
      <div className="max-w-7xl mx-auto px-8 py-6 grid grid-cols-12 gap-6">
        
        {/* ── Coluna Esquerda: Sidebar (col-span-4) ────────────────────────── */}
        <aside className="col-span-4 space-y-5">
          <div className="bg-white border border-[#e8e0d6] rounded-xl p-5 shadow-sm space-y-4">
            
            {/* Header com Código do Orçamento */}
            <div className="flex items-center justify-between pb-3 border-b border-[#f3ede6]">
              <h2 className="text-base font-semibold text-[#2c2420]">Novo Orçamento</h2>
              <span className="bg-[#648261]15 text-[#648261] px-2 py-0.5 rounded text-xs font-mono font-bold tracking-wider">
                {budgetCode}
              </span>
            </div>

            {/* Representante */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Representante</span>
              <Autocomplete
                searchPlaceholder="Buscar representante..."
                items={reps}
                value={selectedRep}
                getLabel={(r) => `${r.name} — ${r.city}/${r.state}`}
                getSearch={(r) => `${r.name} ${r.email} ${r.city}`}
                onChange={setSelectedRep}
                onClear={() => setSelectedRep(null)}
                displayPlaceholder="Nenhum"
                showQuickAdd
                onQuickAdd={() => setQuickModal('rep')}
              />
            </div>

            {/* Cliente */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Cliente</span>
              <Autocomplete
                searchPlaceholder="Buscar cliente..."
                items={clients}
                value={selectedClient}
                getLabel={(c) => `${c.name} — ${c.city}/${c.state}`}
                getSearch={(c) => `${c.name} ${c.email} ${c.city}`}
                onChange={setSelectedClient}
                onClear={() => setSelectedClient(null)}
                displayPlaceholder="Selecione o cliente..."
                showQuickAdd
                onQuickAdd={() => setQuickModal('client')}
              />
            </div>

            {/* Card de Adição de Produto */}
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
                        onMouseDown={() => {
                          setSelectedProduct(p)
                          setProductQuery('')
                          setProductOpen(false)
                        }}
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

              {/* Box de produto que está selecionado mas ainda não adicionado */}
              {selectedProduct && (
                <div className="bg-white border border-[#e8dccb] rounded-lg p-2.5 flex gap-2.5 shadow-sm relative animate-fadeIn">
                  <button
                    type="button"
                    onClick={() => setSelectedProduct(null)}
                    className="absolute top-1.5 right-1.5 text-[#9d8d81] hover:text-red-500 transition-colors"
                  >
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
                    <p className="text-[#8b6914] font-bold mt-0.5">
                      {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(selectedProduct.price)}
                    </p>
                  </div>
                </div>
              )}

              <button
                type="button"
                onClick={handleAddProductToCart}
                disabled={!selectedProduct}
                className="w-full py-2 rounded-lg text-xs font-semibold tracking-wider text-white transition-all bg-[#8b6914] hover:bg-[#725510] disabled:bg-[#c8bdb5] disabled:cursor-not-allowed flex items-center justify-center gap-1.5 shadow-sm"
              >
                ADICIONAR AO ORÇAMENTO
              </button>
            </div>

            {/* Observações */}
            <div className="space-y-1">
              <span className="text-[10px] font-bold text-[#9d8d81] uppercase tracking-wider block">Observações</span>
              <textarea
                className="input resize-none text-xs"
                rows={3}
                placeholder="Observações do orçamento..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            {/* Botão de Finalizar */}
            <button
              onClick={handleSubmit}
              disabled={!selectedClient || cart.length === 0 || isGenerating}
              className="w-full py-3 rounded-lg text-xs font-bold tracking-widest text-white transition-all bg-[#8b6914] hover:bg-[#725510] disabled:bg-[#c8bdb5] disabled:cursor-not-allowed uppercase shadow-sm"
            >
              Finalizar Orçamento
            </button>
          </div>
        </aside>

        {/* ── Coluna Direita: Painel de Itens (col-span-8) ────────────────── */}
        <main className="col-span-8 bg-white border border-[#e8e0d6] rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[550px]">
          
          {/* Cabeçalho do Painel */}
          <div className="px-6 py-4 border-b border-[#e8e0d6] flex items-center justify-between bg-white flex-shrink-0">
            <h2 className="text-sm font-semibold text-[#8b6914] uppercase tracking-wider flex items-center gap-2">
              <ShoppingCart className="w-4 h-4" /> Itens do Orçamento
            </h2>

            <div className="flex items-center gap-2">
              {cart.length > 0 && (
                <button
                  onClick={() => { setCart([]); localStorage.removeItem('carrinho_orcamento') }}
                  className="text-xs text-[#b25e50] hover:text-[#8a3a2e] border border-[#f0c8c0] hover:border-[#b25e50] px-3 py-1.5 rounded-lg transition-colors"
                >
                  Limpar Orçamento
                </button>
              )}
              {/* Filtro Local */}
              <div className="relative w-52">
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

          {/* Lista de Itens */}
          <div className="flex-1 overflow-y-auto">
            {filteredCart.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-[#9d8d81] space-y-3">
                <Clipboard className="w-12 h-12 text-[#c8bdb5] stroke-[1.2]" />
                <p className="text-sm font-medium text-[#6b5d55]">Nenhum item adicionado ao orçamento.</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-[#fbfaf8] text-xs text-[#9d8d81] uppercase font-semibold border-b border-[#e8e0d6] sticky top-0 z-10">
                  <tr>
                    <th className="px-4 py-3 text-left">Produto</th>
                    <th className="px-4 py-3 text-left w-16">Qtd</th>
                    <th className="px-4 py-3 text-left w-28">Preço Base</th>
                    <th className="px-4 py-3 text-left w-24">Desconto (%)</th>
                    <th className="px-4 py-3 text-right w-28">Subtotal</th>
                    <th className="px-4 py-3 w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e8e0d6]">
                  {filteredCart.map((item) => {
                    const subtotal = item.qty * item._product.price * (1 - (item.discount || 0) / 100)
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
                              <div className="text-[10px] text-[#9d8d81] mt-0.5">{dimLabel(item._product)}</div>
                              <StaticOptionals item={item} />
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <input
                            type="number" min={1}
                            className="input w-12 text-center text-xs border border-[#e8e0d6] rounded-lg py-1 bg-white text-[#2c2420]"
                            value={item.qty}
                            onChange={(e) => updateQty(item.product_code, Number(e.target.value))}
                          />
                        </td>
                        <td className="px-4 py-3.5 text-[#4a3f38] text-xs font-semibold whitespace-nowrap align-middle">
                          R$ {fmt(item._product.price)}
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
                              − R$ {fmt(item._product.price * item.discount / 100)}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-right text-xs font-bold text-[#2c2420] align-middle whitespace-nowrap">
                          R$ {fmt(subtotal)}
                        </td>
                        <td className="px-4 py-3.5 align-middle text-center">
                          <button onClick={() => removeItem(item.product_code)} className="text-[#c8bdb5] hover:text-red-500 transition-colors">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Rodapé de Resumo Geral */}
          {cart.length > 0 && (
            <div className="bg-[#fbfaf8] border-t border-[#e8e0d6] px-6 py-4 flex justify-between items-center flex-shrink-0">
              <div className="flex gap-4 text-xs text-[#8a7a6e]">
                <div>
                  <span>Itens: </span>
                  <span className="font-semibold text-[#2c2420]">{cart.reduce((s, i) => s + i.qty, 0)}</span>
                </div>
                <div>
                  <span>Produtos: </span>
                  <span className="font-semibold text-[#2c2420]">{cart.length}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#2c2420] font-semibold text-xs uppercase tracking-wider">Total do Orçamento:</span>
                <span className="text-[#8b6914] font-bold text-base">R$ {fmt(total)}</span>
              </div>
            </div>
          )}
        </main>
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

      {activePhotoModal && <PhotoLightbox url={activePhotoModal} onClose={() => setActivePhotoModal(null)} />}

      {/* ── Overlay de Geração Premium ─────────────────────────────── */}
      {isGenerating && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#1a1410]/88 backdrop-blur-sm">
          {/* Pulso radial dourado */}
          <div
            className="absolute w-[520px] h-[520px] rounded-full pointer-events-none"
            style={{
              background: 'radial-gradient(circle, rgba(139,105,20,0.28) 0%, transparent 68%)',
              animation: 'pulseRadial 2.2s ease-in-out infinite',
            }}
          />

          {/* Logotipo ILYA com varredura de luz dourada */}
          <p
            className="relative text-[80px] leading-none tracking-[0.35em] font-light select-none"
            style={{
              fontFamily: "'Cormorant Garamond', Georgia, serif",
              backgroundImage:
                'linear-gradient(90deg, #7a5a10 0%, #c8952e 25%, #f5d78e 50%, #c8952e 75%, #7a5a10 100%)',
              backgroundSize: '200% auto',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              animation: 'lightSweep 2.4s linear infinite',
            }}
          >
            ILYA
          </p>

          {/* Subtítulo pulsante */}
          <p
            className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-[#c8952e]"
            style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}
          >
            Gerando Orçamento
          </p>

          {/* Barra de progresso */}
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
