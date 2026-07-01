import { useState } from 'react'
import { X, ShoppingCart, Check, ImageIcon } from 'lucide-react'
import { useProducts } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
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

            <div className="bg-[#f8f6f2] border border-[#e8e0d6] rounded-xl p-3">
              <p className="text-xs text-[#9d8d81] font-semibold mb-1">Dimensões</p>
              <p className="text-sm text-[#4a3f38]">{dimLabel(product)}</p>
            </div>

            {product.is_set ? (
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
  const [activeTipo, setActiveTipo] = useState('Todos')
  const [selected, setSelected] = useState<Product | null>(null)

  const tipos = ['Todos', ...productTypes.map(t => t.name)]

  const filtered = activeTipo === 'Todos'
    ? products
    : products.filter(p => p.type === activeTipo)

  return (
    <div className="min-h-screen bg-[#f8f6f2] pb-24 md:pb-8">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-5 md:mb-7">
          <h2 className="text-xl md:text-2xl font-semibold text-[#2c2420]" style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}>
            Catálogo de Produtos
          </h2>
          <p className="text-sm text-[#9d8d81] mt-1">Selecione um produto para adicionar ao orçamento</p>
        </div>

        {/* Chips de filtro — scroll horizontal no mobile */}
        <div className="flex gap-2 mb-5 md:mb-7 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0 md:flex-wrap">
          {tipos.map(tipo => (
            <button
              key={tipo}
              onClick={() => setActiveTipo(tipo)}
              style={{ touchAction: 'manipulation' }}
              className={`flex-shrink-0 px-3.5 py-2 rounded-full text-sm font-medium border transition-all active:scale-[0.97] active:opacity-80 ${
                activeTipo === tipo
                  ? 'bg-gold text-white border-gold'
                  : 'bg-white text-[#4a3f38] border-[#e8e0d6] hover:border-[#c8bdb5]'
              }`}
            >
              {tipo}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="text-center text-[#9d8d81] py-20">Carregando catálogo…</div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-[#9d8d81] py-20">Nenhum produto encontrado.</div>
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
