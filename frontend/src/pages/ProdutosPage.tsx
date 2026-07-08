import { useState } from 'react'
import { X, ShoppingCart, Check, ImageIcon, Search } from 'lucide-react'
import { useProducts } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useProductGroups } from '../hooks/useProductGroups'
import { isConjuntoType } from '../lib/productType'
import type { Product } from '../types'

const CAT_LABEL: Record<string, string> = {
  aluminio: 'Alumínio', corda: 'Corda',
  tecido_faixa_1: 'Tecido F1', tecido_faixa_2: 'Tecido F2',
  madeira_teka: 'Madeira Teka', madeira_freijo: 'Madeira Freijó',
  couro_soleta: 'Couro Soleta', couro_pele: 'Couro Pele',
}

function fmtM(v: number) {
  return Number(v).toFixed(2).replace('.', ',')
}

function dimLabel(p: Product) {
  return p.is_circular
    ? `Ø ${fmtM(p.largura)} × A ${fmtM(p.altura)} m`
    : `L ${fmtM(p.largura)} × P ${fmtM(p.profundidade)} × A ${fmtM(p.altura)} m`
}

function addToCart(product: Product) {
  const raw = localStorage.getItem('carrinho_orcamento')
  const cart = raw ? JSON.parse(raw) : []
  const existing = cart.find((i: { product_code: string }) => i.product_code === product.product_code)
  if (existing) {
    existing.qty += 1
  } else {
    const opt_categories: Record<string, string> = {}
    for (const opt of product.optionals) {
      if (!(opt.category in opt_categories)) {
        opt_categories[opt.category] = opt.color_name
      }
    }
    cart.push({
      product_code: product.product_code,
      qty: 1,
      discount: 0,
      opt_categories,
      _product: product,
    })
  }
  localStorage.setItem('carrinho_orcamento', JSON.stringify(cart))
}

// ── Mini modal para zoom de opcional no mobile ────────────────────────────────

function OptionalZoomModal({ photo_url, label, onClose }: { photo_url: string; label: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="bg-white rounded-2xl shadow-2xl p-4 mx-6 flex flex-col items-center gap-3" onClick={e => e.stopPropagation()}>
        <img src={photo_url} alt={label} className="w-48 h-48 object-cover rounded-xl border border-[#e8e0d6]" />
        <p className="text-sm font-medium text-[#2c2420] text-center">{label}</p>
        <button onClick={onClose} className="text-xs text-[#9d8d81] uppercase tracking-wider py-2 px-4">Fechar</button>
      </div>
    </div>
  )
}

// ── SlideOver (desktop) / Bottom Sheet (mobile) ───────────────────────────────

function SlideOver({ product, onClose }: { product: Product; onClose: () => void }) {
  const [added, setAdded] = useState(false)
  const [mobileOptModal, setMobileOptModal] = useState<{ photo_url: string; label: string } | null>(null)

  function handleAdd() {
    addToCart(product)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  const optCategories = Array.from(new Set(product.optionals.map(o => o.category))).map(cat => ({
    cat,
    opt: product.optionals.find(o => o.category === cat)!,
  }))

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-end md:items-stretch md:justify-end">
        <div className="fixed inset-0 bg-[#1a1410]/40 backdrop-blur-sm" onClick={onClose} />

        {/* Desktop: right panel — Mobile: bottom sheet */}
        <div className="relative z-10 w-full md:w-[400px] bg-white md:h-full h-[90vh] shadow-2xl flex flex-col overflow-y-auto rounded-t-2xl md:rounded-none">
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e0d6] flex-shrink-0">
            <span className="font-mono text-sm font-semibold text-[#8b6914]">{product.product_code}</span>
            <button
              onClick={onClose}
              className="text-[#9d8d81] hover:text-[#2c2420] transition-colors w-11 h-11 flex items-center justify-center"
              style={{ touchAction: 'manipulation' }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {product.photo_url
            ? <img src={product.photo_url} alt={product.description} className="w-full aspect-square object-cover flex-shrink-0" />
            : <div className="w-full aspect-square bg-[#f0ece6] flex items-center justify-center flex-shrink-0">
                <span className="text-[#c8bdb5] text-sm">Sem foto</span>
              </div>
          }

          <div className="px-6 py-5 flex-1 space-y-4">
            <div>
              <p className="text-xs text-[#9d8d81] uppercase tracking-wider font-semibold mb-1">{product.type}</p>
              <h3 className="text-lg font-semibold text-[#2c2420]">{product.description}</h3>
            </div>

            {!isConjuntoType(product.type) && (
              <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-xl p-3">
                <p className="text-xs text-[#9d8d81] font-semibold mb-1">Dimensões</p>
                <p className="text-sm text-[#4a3f38]">{dimLabel(product)}</p>
              </div>
            )}

            {product.observacao && (
              <div className="bg-[#fdf6ec] border border-[#e8d8b8] rounded-xl p-3">
                <p className="text-xs text-[#8b6914] font-semibold mb-1 uppercase tracking-wide">Observação</p>
                <p className="text-sm text-[#5a4a2c] italic leading-snug">{product.observacao}</p>
              </div>
            )}

            {isConjuntoType(product.type) ? (
              <div>
                <p className="text-xs text-[#9d8d81] font-semibold uppercase tracking-wider mb-3">Componentes deste Conjunto</p>
                <div className="space-y-2">
                  {product.components.map((comp, idx) => {
                    const dimStr = comp.is_circular
                      ? `Ø ${fmtM(comp.largura)} × A ${fmtM(comp.altura)} m`
                      : `L ${fmtM(comp.largura)} × P ${fmtM(comp.profundidade)} × A ${fmtM(comp.altura)} m`
                    const catGroups = Array.from(new Set(comp.optionals.map(o => o.category)))
                    return (
                      <div key={idx} className="p-3 rounded-xl border border-[#e8e0d6] bg-[#f8f6f2]">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-[#2c2420]">{comp.description}</p>
                          <span className="text-xs font-semibold text-[#4a3f38] whitespace-nowrap flex-shrink-0">×{comp.qty}</span>
                        </div>
                        <p className="text-[10px] text-[#9d8d81] mt-0.5">{dimStr}</p>
                        {catGroups.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {catGroups.map(cat => {
                              const opt = comp.optionals.find(o => o.category === cat)!
                              return (
                                <div key={cat} className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-[#e8e0d6] bg-white">
                                  {opt.photo_url && <img src={opt.photo_url} alt={opt.color_name} className="w-3 h-3 rounded object-cover" />}
                                  <span className="text-[9px] text-[#4a3f38]">{CAT_LABEL[cat] ?? cat}: {opt.color_name}</span>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                  {product.components.length === 0 && (
                    <p className="text-xs text-[#9d8d81] italic">Nenhum componente registrado.</p>
                  )}
                </div>
              </div>
            ) : product.is_set ? (
              <div>
                <p className="text-xs text-[#9d8d81] font-semibold uppercase tracking-wider mb-3">Componentes deste Conjunto</p>
                <div className="space-y-2">
                  {product.set_items.map((item) => (
                    <div key={item.product_code} className="flex items-center gap-3 p-3 rounded-xl border border-[#e8e0d6] bg-[#f8f6f2]">
                      {item.photo_url
                        ? <img src={item.photo_url} alt={item.description} className="w-10 h-10 rounded-lg object-cover border border-[#e8e0d6] flex-shrink-0" />
                        : <div className="w-10 h-10 rounded-lg bg-[#f0ece6] flex items-center justify-center flex-shrink-0"><ImageIcon className="w-4 h-4 text-[#c8bdb5]" /></div>
                      }
                      <div className="flex-1 min-w-0">
                        <span className="block text-[10px] font-mono font-semibold text-[#8b6914]">{item.product_code}</span>
                        <span className="block text-xs text-[#2c2420] font-medium leading-snug truncate">{item.description}</span>
                      </div>
                      <span className="text-xs font-semibold text-[#4a3f38] whitespace-nowrap flex-shrink-0">×{item.qty}</span>
                    </div>
                  ))}
                  {product.set_items.length === 0 && (
                    <p className="text-xs text-[#9d8d81] italic">Nenhum componente registrado.</p>
                  )}
                </div>
              </div>
            ) : optCategories.length > 0 ? (
              <div>
                <p className="text-xs text-[#9d8d81] font-semibold uppercase tracking-wider mb-3">Opcionais</p>
                <div className="flex flex-wrap gap-4">
                  {optCategories.map(({ cat, opt }) => (
                    <div key={cat} className="flex flex-col items-center gap-1.5">
                      <div className="relative group">
                        {opt.photo_url ? (
                          <>
                            <img
                              src={opt.photo_url}
                              alt={opt.color_name}
                              className="w-10 h-10 rounded-lg object-cover border border-[#e8e0d6] cursor-zoom-in hidden md:block"
                            />
                            <div className="hidden group-hover:block absolute z-50 bottom-12 left-1/2 -translate-x-1/2 w-40 h-40 rounded-xl overflow-hidden shadow-2xl border border-[#e8e0d6] pointer-events-none">
                              <img src={opt.photo_url} alt={opt.color_name} className="w-full h-full object-cover" />
                            </div>
                            <button
                              className="md:hidden w-10 h-10 rounded-lg overflow-hidden border border-[#e8e0d6] active:opacity-70 transition-opacity"
                              style={{ touchAction: 'manipulation' }}
                              onClick={() => setMobileOptModal({ photo_url: opt.photo_url!, label: `${CAT_LABEL[cat] ?? cat}: ${opt.color_name}` })}
                            >
                              <img src={opt.photo_url} alt={opt.color_name} className="w-full h-full object-cover" />
                            </button>
                          </>
                        ) : (
                          <div className="w-10 h-10 rounded-lg bg-[#f0ece6] border border-[#e8e0d6]" />
                        )}
                      </div>
                      <div className="text-center">
                        <span className="block text-[9px] text-[#9d8d81] uppercase tracking-wide">{CAT_LABEL[cat] ?? cat}</span>
                        <span className="text-[10px] text-[#4a3f38] font-medium">{opt.color_name}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="px-6 py-4 border-t border-[#e8e0d6] flex-shrink-0">
            <button
              onClick={handleAdd}
              style={{ touchAction: 'manipulation' }}
              className={`w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-semibold text-sm text-white transition-all active:scale-[0.98] active:opacity-85 ${added ? 'bg-olive' : 'bg-gold'}`}
            >
              {added ? <Check className="w-4 h-4" /> : <ShoppingCart className="w-4 h-4" />}
              {added ? 'Adicionado ao Orçamento!' : 'Adicionar ao Orçamento'}
            </button>
          </div>
        </div>
      </div>

      {mobileOptModal && (
        <OptionalZoomModal
          photo_url={mobileOptModal.photo_url}
          label={mobileOptModal.label}
          onClose={() => setMobileOptModal(null)}
        />
      )}
    </>
  )
}

export default function ProdutosPage() {
  const { data: products = [], isLoading } = useProducts()
  const { data: productTypes = [] } = useProductTypes()
  const { data: productGroups = [] } = useProductGroups()

  const [searchTerm, setSearchTerm] = useState('')
  const [selectedGroupId, setSelectedGroupId] = useState<string>('')
  const [selectedTypeName, setSelectedTypeName] = useState<string>('')
  const [selected, setSelected] = useState<Product | null>(null)

  function handleGroupChange(groupId: string) {
    setSelectedGroupId(groupId)
    setSelectedTypeName('')
  }

  // Types shown in subgroup dropdown cascade from selected group
  const availableTypes = selectedGroupId
    ? productTypes.filter(t => t.group_id === selectedGroupId)
    : productTypes

  // Build a fast lookup: type name → group_id
  const typeGroupMap = new Map(productTypes.map(t => [t.name, t.group_id ?? '']))

  const filtered = products.filter(p => {
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      if (!p.product_code.toLowerCase().includes(q) && !p.description.toLowerCase().includes(q)) return false
    }
    if (selectedGroupId) {
      if (typeGroupMap.get(p.type) !== selectedGroupId) return false
    }
    if (selectedTypeName) {
      if (p.type !== selectedTypeName) return false
    }
    return true
  })

  const hasFilters = searchTerm || selectedGroupId || selectedTypeName

  function clearFilters() {
    setSearchTerm('')
    setSelectedGroupId('')
    setSelectedTypeName('')
  }

  return (
    <div className="min-h-screen bg-[#f8f6f2] pb-24 md:pb-8">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-5 md:mb-6">
          <h2 className="text-xl md:text-2xl font-semibold text-[#2c2420]" style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}>
            Catálogo de Produtos
          </h2>
          <p className="text-sm text-[#9d8d81] mt-1">Selecione um produto para adicionar ao orçamento</p>
        </div>

        {/* ── Barra de Filtros ─────────────────────────────────────────────── */}
        <div className="bg-white border border-[#e8e0d6] rounded-xl px-3 py-3 mb-5 md:mb-6 shadow-sm space-y-2 md:space-y-0 md:flex md:items-center md:gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#a89a8e]" />
            <input
              type="text"
              placeholder="Buscar por código ou descrição..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-8 py-2 text-sm bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg text-[#2c2420] placeholder-[#c8bdb5] focus:outline-none focus:ring-1 focus:ring-[#8b6914] transition-all"
            />
            {searchTerm && (
              <button onClick={() => setSearchTerm('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#9d8d81] hover:text-[#2c2420]">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Group dropdown */}
          <select
            value={selectedGroupId}
            onChange={(e) => handleGroupChange(e.target.value)}
            className="w-full md:w-44 py-2 px-3 text-sm bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg text-[#4a3f38] focus:outline-none focus:ring-1 focus:ring-[#8b6914] transition-all"
          >
            <option value="">Todos os Grupos</option>
            {productGroups.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>

          {/* Subgroup dropdown — cascades from group */}
          <select
            value={selectedTypeName}
            onChange={(e) => setSelectedTypeName(e.target.value)}
            className="w-full md:w-48 py-2 px-3 text-sm bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg text-[#4a3f38] focus:outline-none focus:ring-1 focus:ring-[#8b6914] transition-all disabled:opacity-50"
            disabled={availableTypes.length === 0}
          >
            <option value="">Todos os Subgrupos</option>
            {availableTypes.map(t => (
              <option key={t.id} value={t.name}>{t.name}</option>
            ))}
          </select>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-[#8b6914] border border-[#c8a84b] rounded-lg hover:bg-[#fdf9f0] transition-colors"
              style={{ touchAction: 'manipulation' }}
            >
              <X className="w-3 h-3" /> Limpar
            </button>
          )}
        </div>

        {/* Result count */}
        {hasFilters && !isLoading && (
          <p className="text-xs text-[#9d8d81] mb-3">
            {filtered.length === 0
              ? 'Nenhum produto encontrado.'
              : `${filtered.length} produto${filtered.length !== 1 ? 's' : ''} encontrado${filtered.length !== 1 ? 's' : ''}`}
          </p>
        )}

        {isLoading ? (
          <div className="text-center text-[#9d8d81] py-20">Carregando catálogo…</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center py-20 gap-3">
            <p className="text-[#9d8d81]">Nenhum produto encontrado.</p>
            {hasFilters && (
              <button onClick={clearFilters} className="text-xs text-[#8b6914] underline">Limpar filtros</button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-5">
            {filtered.map(product => (
              <button
                key={product.id}
                onClick={() => setSelected(product)}
                className="bg-white border border-[#e8e0d6] rounded-2xl overflow-hidden text-left shadow-sm hover:shadow-md hover:-translate-y-0.5 active:scale-[0.98] active:opacity-85 transition-all duration-200"
                style={{ touchAction: 'manipulation' }}
              >
                {product.photo_url
                  ? <img src={product.photo_url} alt={product.description} className="w-full aspect-square object-cover" />
                  : <div className="w-full aspect-square bg-[#f0ece6] flex items-center justify-center">
                      <span className="text-[#c8bdb5] text-xs">Sem foto</span>
                    </div>
                }
                <div className="p-3 md:p-3.5">
                  <span className="text-[10px] font-mono font-semibold text-[#8b6914]">{product.product_code}</span>
                  <p className="text-xs md:text-sm font-medium text-[#2c2420] leading-snug mt-0.5 line-clamp-2">{product.description}</p>
                  {selectedGroupId === '' && product.type && (
                    <span className="text-[9px] text-[#9d8d81] mt-1 block">{product.type}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selected && <SlideOver product={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
