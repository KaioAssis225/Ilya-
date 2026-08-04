import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { X, ShoppingCart, Check, ImageIcon, Search, Plus, Minus, ChevronDown } from 'lucide-react'
import { cartStorageKey, notifyCartChanged } from '../lib/cart'
import { useCartQuantities } from '../hooks/useCart'
import { useAuth } from '../hooks/useAuth'
import { productsPageQueryOptions, useProductsPage } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useProductGroups } from '../hooks/useProductGroups'
import { isConjuntoType } from '../lib/productType'
import { SafePrice } from '../components/SafePrice'
import type { PageResult, Product } from '../types'

const PAGE_SIZE = 24
const FULL_IMAGE_WARMUP_COUNT = 4

const loadedFullImages = new Set<string>()
const pendingFullImages = new Map<string, Promise<void>>()

function preloadFullImage(source: string | null | undefined, priority: 'high' | 'low' = 'low') {
  if (!source || loadedFullImages.has(source)) return Promise.resolve()

  const pending = pendingFullImages.get(source)
  if (pending) return pending

  const request = new Promise<void>((resolve, reject) => {
    const image = new Image()
    image.decoding = 'async'
    image.fetchPriority = priority
    image.onload = () => {
      loadedFullImages.add(source)
      resolve()
    }
    image.onerror = () => reject(new Error(`Não foi possível pré-carregar ${source}`))
    image.src = source
  }).finally(() => {
    pendingFullImages.delete(source)
  })

  pendingFullImages.set(source, request)
  return request
}

function warmProductImage(product: Product, priority: 'high' | 'low' = 'high') {
  if (!product.photo_url || product.photo_url === product.thumbnail_url) return
  void preloadFullImage(product.photo_url, priority).catch(() => undefined)
}

function CatalogImage({ product }: { product: Product }) {
  const frameRef = useRef<HTMLDivElement>(null)
  const [nearViewport, setNearViewport] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [thumbnailFailed, setThumbnailFailed] = useState(false)
  const thumbnail = product.thumbnail_url ?? product.photo_url
  const source = thumbnailFailed ? product.photo_url : thumbnail

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        setNearViewport(true)
        observer.disconnect()
      },
      { rootMargin: '1000px 0px' },
    )
    observer.observe(frame)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={frameRef} className="relative w-full h-full">
      {!loaded && <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-bg via-white to-bg-2" />}
      {nearViewport && source && (
        <img
          src={source}
          alt={product.description}
          width={320}
          height={320}
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => {
            if (!thumbnailFailed && product.photo_url && source !== product.photo_url) {
              setThumbnailFailed(true)
            }
          }}
          className={`w-full h-full object-contain transition-[opacity,transform] duration-500 ease-out group-hover:scale-[1.04] ${loaded ? 'opacity-100' : 'opacity-0'}`}
        />
      )}
    </div>
  )
}

function FullProductImage({ product }: { product: Product }) {
  const preview = product.thumbnail_url ?? product.photo_url
  const original = product.photo_url
  const hasDistinctPreview = Boolean(preview && original && preview !== original)
  const [originalLoaded, setOriginalLoaded] = useState(
    () => Boolean(original && loadedFullImages.has(original)),
  )

  useEffect(() => {
    setOriginalLoaded(Boolean(original && loadedFullImages.has(original)))
    if (original) {
      void preloadFullImage(original, 'high').catch(() => undefined)
    }
  }, [original])

  return (
    <div className="relative w-full h-[40vh] md:h-full overflow-hidden">
      {preview && (
        <img
          src={preview}
          alt=""
          decoding="async"
          aria-hidden="true"
          className={`absolute inset-0 w-full h-full object-contain transition-[opacity,filter,transform] duration-700 ease-out ${
            originalLoaded
              ? 'opacity-0 blur-0 scale-100'
              : hasDistinctPreview
                ? 'opacity-100 blur-[0.4px] scale-[1.008]'
                : 'opacity-100 blur-0 scale-100'
          }`}
        />
      )}
      {original && (
        <img
          src={original}
          alt={product.description}
          decoding="async"
          fetchPriority="high"
          onLoad={() => {
            loadedFullImages.add(original)
            setOriginalLoaded(true)
          }}
          className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-700 ease-out ${
            originalLoaded ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
    </div>
  )
}

// ── Preços do catálogo ────────────────────────────────────────────────────────
// Quem enxerga cada tabela de preço é decidido no servidor (Bloco 96): a API
// devolve `null` no preço que a role logada não pode ver. Operadores internos e
// representantes recebem lojista + corporativo; a conta do cliente-final recebe
// só o preço do próprio perfil de faturamento — por isso aqui não há guard de
// role, só o que veio do servidor.
//
// Quem recebe as DUAS tabelas escolhe qual fica na tela: o representante em
// visita não pode deixar as duas visíveis ao mesmo tempo na frente do cliente.
// "Ambos" continua existindo para comparativo interno, mas é opt-in explícito.
// A escolha é só de EXIBIÇÃO — o valor aplicado no orçamento segue resolvido no
// servidor pelo perfil do cliente, nunca por esse seletor.

type PriceTable = 'lojista' | 'corporativo' | 'ambos'

const PRICE_TABLE_KEY = 'catalogo_tabela_preco'
const PRICE_TABLE_OPTIONS: { value: PriceTable; label: string }[] = [
  { value: 'lojista', label: 'Lojista' },
  { value: 'corporativo', label: 'Corporativo' },
  { value: 'ambos', label: 'Ambos' },
]

// Padrão é uma tabela só: sem escolha salva, o catálogo nunca nasce expondo as
// duas de uma vez.
function readPriceTable(): PriceTable {
  const saved = localStorage.getItem(PRICE_TABLE_KEY)
  return saved === 'corporativo' || saved === 'ambos' ? saved : 'lojista'
}

type VisiblePrice = { key: Exclude<PriceTable, 'ambos'>; label: string; value: number }

function visiblePrices(product: Product, table: PriceTable): VisiblePrice[] {
  const prices: VisiblePrice[] = []
  if (product.price_lojista != null) {
    prices.push({ key: 'lojista', label: 'Lojista', value: product.price_lojista })
  }
  if (product.price_corporativo != null) {
    prices.push({ key: 'corporativo', label: 'Corporativo', value: product.price_corporativo })
  }
  if (table === 'ambos') return prices

  // A conta do cliente-final recebe uma tabela só. Se a escolhida não for a que
  // o servidor liberou, mostra a que existe em vez de esconder o preço: o
  // seletor só restringe quando há de fato duas para escolher.
  const picked = prices.filter(price => price.key === table)
  return picked.length > 0 ? picked : prices
}

function PriceTableToggle({ value, onChange }: { value: PriceTable; onChange: (next: PriceTable) => void }) {
  return (
    <div
      role="group"
      aria-label="Tabela de preço exibida"
      className="flex w-full md:w-auto flex-shrink-0 items-center gap-0.5 p-0.5 bg-bg border border-line rounded-lg"
    >
      {PRICE_TABLE_OPTIONS.map(({ value: option, label }) => {
        const active = option === value
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            aria-pressed={active}
            className={`flex-1 md:flex-none px-2.5 py-1.5 text-[11px] font-medium rounded-md whitespace-nowrap transition-colors ${
              active ? 'bg-white text-ink shadow-sm ring-1 ring-gold-soft' : 'text-muted hover:text-ink'
            }`}
            style={{ touchAction: 'manipulation' }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

// Preço sempre visível, abaixo da descrição — mesmo no desktop e no mobile.
// (Chegou a existir uma versão em que o hover trocava a descrição pelo preço
// no desktop; foi revertida para o preço não depender de passar o mouse,
// igual já era no mobile por não ter hover.)

function CardText({ product, priceTable }: { product: Product; priceTable: PriceTable }) {
  const prices = visiblePrices(product, priceTable)

  return (
    <>
      <h3 className="font-sans font-medium tracking-normal text-[15px] md:text-[17px] text-ink leading-snug mt-1.5 line-clamp-2">
        {product.description}
      </h3>
      {prices.length > 0 && <CardPrice prices={prices} />}
    </>
  )
}

function CardPrice({ prices }: { prices: VisiblePrice[] }) {
  // Uma tabela: o valor em destaque, com o rótulo pequeno embaixo dizendo de
  // qual tabela é — importante quando o produto tem as duas e o representante
  // restringiu a visualização a uma só.
  if (prices.length === 1) {
    return (
      <div className="mt-2">
        <p className="text-[15px] md:text-base font-semibold text-ink tabular-nums leading-tight">
          <SafePrice value={prices[0].value} />
        </p>
        <p className="text-[9px] uppercase tracking-[0.12em] text-muted mt-0.5">{prices[0].label}</p>
      </div>
    )
  }

  // Duas tabelas (comparativo interno): rótulo à esquerda, valor à direita.
  return (
    <dl className="mt-2 space-y-0.5">
      {prices.map(({ label, value }) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <dt className="text-[9px] uppercase tracking-[0.12em] text-muted">{label}</dt>
          <dd className="text-[13px] md:text-sm font-semibold text-ink tabular-nums">
            <SafePrice value={value} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function DetailPrice({ product, priceTable }: { product: Product; priceTable: PriceTable }) {
  const prices = visiblePrices(product, priceTable)
  if (prices.length === 0) return null

  return (
    <div className="py-4 border-y border-[#efe9e1] space-y-2">
      {prices.map(({ label, value }) => (
        <div key={label} className="flex items-baseline justify-between gap-6">
          <span className="text-[10px] uppercase tracking-[0.15em] text-muted font-semibold flex-shrink-0">
            {prices.length === 1 ? 'Preço' : label}
          </span>
          <span className="text-lg text-ink font-semibold tabular-nums">
            <SafePrice value={value} />
          </span>
        </div>
      ))}
    </div>
  )
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

const CAT_LABEL: Record<string, string> = {
  aluminio: 'Alumínio', corda: 'Corda',
  tecido_faixa_1: 'Tecido F1', tecido_faixa_2: 'Tecido F2',
  madeira_teka: 'Madeira Teka', madeira_freijo: 'Madeira Freijó',
  couro_soleta: 'Couro Soleta', couro_pele: 'Couro Pele',
}

function groupOptionalsByCategory(optionals: Product['optionals']) {
  const seen = new Set<string>()
  const groups: Product['optionals'] = []
  for (const opt of optionals) {
    if (seen.has(opt.category)) continue
    seen.add(opt.category)
    groups.push(opt)
  }
  return groups
}

function fmtM(v: number) {
  return Number(v).toFixed(2).replace('.', ',')
}

function dimLabel(p: Product) {
  return p.is_circular
    ? `Ø ${fmtM(p.largura)} × A ${fmtM(p.altura)} m`
    : `L ${fmtM(p.largura)} × P ${fmtM(p.profundidade)} × A ${fmtM(p.altura)} m`
}

function addToCart(product: Product, userId: string) {
  const storageKey = cartStorageKey(userId)
  const raw = localStorage.getItem(storageKey)
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
  localStorage.setItem(storageKey, JSON.stringify(cart))
  notifyCartChanged()
}

// Uma unidade a menos; some do carrinho ao chegar a 0 em vez de deixar qty: 0
// pendurado (o resto do app assume que todo item presente no carrinho tem
// qty > 0 — é o mesmo contrato que readCartQuantities já aplica na leitura).
function decrementCart(product: Product, userId: string) {
  const storageKey = cartStorageKey(userId)
  const raw = localStorage.getItem(storageKey)
  if (!raw) return
  let cart: { product_code: string; qty: number }[]
  try {
    cart = JSON.parse(raw)
  } catch {
    return
  }
  if (!Array.isArray(cart)) return

  const index = cart.findIndex(item => item.product_code === product.product_code)
  if (index === -1) return

  if (cart[index].qty > 1) {
    cart[index].qty -= 1
  } else {
    cart.splice(index, 1)
  }
  localStorage.setItem(storageKey, JSON.stringify(cart))
  notifyCartChanged()
}

// ── Mini modal para zoom de opcional no mobile ────────────────────────────────

function OptionalZoomModal({ photo_url, label, onClose }: { photo_url: string; label: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="bg-white rounded-2xl shadow-2xl p-4 mx-6 flex flex-col items-center gap-3" onClick={e => e.stopPropagation()}>
        <img src={photo_url} alt={label} className="w-48 h-48 object-cover rounded-xl border border-line" />
        <p className="text-sm font-medium text-ink text-center">{label}</p>
        <button onClick={onClose} className="text-xs text-muted uppercase tracking-wider py-2 px-4">Fechar</button>
      </div>
    </div>
  )
}

// ── Detalhe do produto em tela inteira ────────────────────────────────────────
// Desktop: foto grande à esquerda + detalhes à direita. Mobile: coluna única.

function ProductFullView({
  product,
  priceTable,
  userId,
  onClose,
}: { product: Product; priceTable: PriceTable; userId: string; onClose: () => void }) {
  const [added, setAdded] = useState(false)
  const [mobileOptModal, setMobileOptModal] = useState<{ photo_url: string; label: string } | null>(null)

  function handleAdd() {
    addToCart(product, userId)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  const optCategories = Array.from(new Set(product.optionals.map(o => o.category))).map(cat => ({
    cat,
    opt: product.optionals.find(o => o.category === cat)!,
  }))

  return (
    <>
      <div className="fixed inset-0 z-50 bg-white flex flex-col md:flex-row overflow-y-auto md:overflow-hidden" style={{ animation: 'fadeIn 0.25s ease-out' }}>
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 w-11 h-11 flex items-center justify-center rounded-full bg-white/85 backdrop-blur-sm text-muted hover:text-ink shadow-sm transition-colors"
          style={{ touchAction: 'manipulation' }}
          aria-label="Fechar"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Foto: metade esquerda no desktop, topo no mobile */}
        <div className="md:w-[55%] md:h-full flex-shrink-0 bg-bg flex items-center justify-center p-6 md:p-14">
          {product.photo_url
            ? <FullProductImage product={product} />
            : <div className="w-full h-[40vh] md:h-full flex items-center justify-center">
                <span className="text-muted text-sm tracking-widest uppercase">Sem foto</span>
              </div>
          }
        </div>

        {/* Detalhes: coluna direita, conteúdo centrado verticalmente */}
        <div className="flex-1 min-w-0 md:h-full md:overflow-y-auto">
          <div className="min-h-full flex flex-col justify-center max-w-[480px] mx-auto w-full px-6 md:px-12 py-10 md:py-16 space-y-8" style={{ animation: 'slideUp 0.35s ease-out' }}>
            <div className="space-y-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted font-semibold">
                {product.type}
                <span className="mx-2 text-[#d8cfc2]">·</span>
                <span className="font-mono normal-case tracking-normal text-gold">{product.product_code}</span>
              </p>
              <h2 className="text-3xl md:text-[2.4rem] leading-[1.12] text-ink">{product.description}</h2>
              <div className="w-12 h-px bg-gold/50" />
            </div>

            <DetailPrice product={product} priceTable={priceTable} />

            {!isConjuntoType(product.type) && (
              <div className="flex items-baseline gap-6 py-4 border-b border-[#efe9e1]">
                <span className="text-[10px] uppercase tracking-[0.15em] text-muted font-semibold flex-shrink-0">Dimensões</span>
                <span className="text-[15px] text-ink-2 font-mono tabular-nums">{dimLabel(product)}</span>
              </div>
            )}

            {product.observacao && (
              <div className="bg-[#fdf6ec] border border-[#e8d8b8] rounded-xl p-3">
                <p className="text-xs text-gold font-semibold mb-1 uppercase tracking-wide">Observação</p>
                <p className="text-sm text-[#5a4a2c] italic leading-snug">{product.observacao}</p>
              </div>
            )}

            {isConjuntoType(product.type) ? (
              <div>
                <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3">Componentes deste Conjunto</p>
                <div className="space-y-2">
                  {product.components.map((comp, idx) => {
                    const dimStr = comp.is_circular
                      ? `Ø ${fmtM(comp.largura)} × A ${fmtM(comp.altura)} m`
                      : `L ${fmtM(comp.largura)} × P ${fmtM(comp.profundidade)} × A ${fmtM(comp.altura)} m`
                    const catGroups = Array.from(new Set(comp.optionals.map(o => o.category)))
                    return (
                      <div key={idx} className="p-3 rounded-xl border border-line bg-bg">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-ink">{comp.description}</p>
                          <span className="text-xs font-semibold text-ink-2 whitespace-nowrap flex-shrink-0">×{comp.qty}</span>
                        </div>
                        <p className="text-[10px] text-muted mt-0.5 font-mono tabular-nums">{dimStr}</p>
                        {catGroups.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {catGroups.map(cat => {
                              const opt = comp.optionals.find(o => o.category === cat)!
                              return (
                                <div key={cat} className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-line bg-white">
                                  {opt.photo_url && <img src={opt.thumbnail_url ?? opt.photo_url} alt={opt.color_name} decoding="async" className="w-3 h-3 rounded object-cover" />}
                                  <span className="text-[9px] text-ink-2">{CAT_LABEL[cat] ?? cat}: {opt.color_name}</span>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                  {product.components.length === 0 && (
                    <p className="text-xs text-muted italic">Nenhum componente registrado.</p>
                  )}
                </div>
              </div>
            ) : product.is_set ? (
              <div>
                <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3">Componentes deste Conjunto</p>
                <div className="space-y-2">
                  {product.set_items.map((item) => (
                    <div key={item.product_code} className="flex items-center gap-3 p-3 rounded-xl border border-line bg-bg">
                      {item.photo_url
                        ? <img src={item.thumbnail_url ?? item.photo_url} alt={item.description} decoding="async" className="w-10 h-10 rounded-lg object-cover border border-line flex-shrink-0" />
                        : <div className="w-10 h-10 rounded-lg bg-bg-2 flex items-center justify-center flex-shrink-0"><ImageIcon className="w-4 h-4 text-faint" /></div>
                      }
                      <div className="flex-1 min-w-0">
                        <span className="block text-[10px] font-mono font-semibold text-gold">{item.product_code}</span>
                        <span className="block text-xs text-ink font-medium leading-snug truncate">{item.description}</span>
                      </div>
                      <span className="text-xs font-semibold text-ink-2 whitespace-nowrap flex-shrink-0">×{item.qty}</span>
                    </div>
                  ))}
                  {product.set_items.length === 0 && (
                    <p className="text-xs text-muted italic">Nenhum componente registrado.</p>
                  )}
                </div>
              </div>
            ) : optCategories.length > 0 ? (
              <div>
                <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3">Opcionais</p>
                <div className="flex flex-wrap gap-5">
                  {optCategories.map(({ cat, opt }) => (
                    <div key={cat} className="flex flex-col items-center gap-2">
                      <div className="relative group">
                        {opt.photo_url ? (
                          <>
                            <img
                              src={opt.thumbnail_url ?? opt.photo_url}
                              alt={opt.color_name}
                              decoding="async"
                              className="w-14 h-14 rounded-xl object-cover border border-line cursor-zoom-in hidden md:block"
                            />
                            <div className="hidden group-hover:block absolute z-50 bottom-16 left-1/2 -translate-x-1/2 w-44 h-44 rounded-xl overflow-hidden shadow-2xl border border-line pointer-events-none">
                              <img src={opt.photo_url} alt={opt.color_name} decoding="async" className="w-full h-full object-cover" />
                            </div>
                            <button
                              className="md:hidden w-14 h-14 rounded-xl overflow-hidden border border-line active:opacity-70 transition-opacity"
                              style={{ touchAction: 'manipulation' }}
                              onClick={() => setMobileOptModal({ photo_url: opt.photo_url!, label: `${CAT_LABEL[cat] ?? cat}: ${opt.color_name}` })}
                            >
                              <img src={opt.thumbnail_url ?? opt.photo_url} alt={opt.color_name} decoding="async" className="w-full h-full object-cover" />
                            </button>
                          </>
                        ) : (
                          <div className="w-14 h-14 rounded-xl bg-bg-2 border border-line" />
                        )}
                      </div>
                      <div className="text-center">
                        <span className="block text-[9px] text-muted uppercase tracking-wide">{CAT_LABEL[cat] ?? cat}</span>
                        <span className="text-[11px] text-ink-2 font-medium">{opt.color_name}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <button
              onClick={handleAdd}
              style={{ touchAction: 'manipulation' }}
              className={`w-full flex items-center justify-center gap-2.5 py-4 rounded-xl font-semibold text-[13px] uppercase tracking-[0.12em] text-white transition-all active:scale-[0.98] active:opacity-85 ${added ? 'bg-olive' : 'bg-gold'}`}
            >
              {added ? <Check className="w-4 h-4" /> : <ShoppingCart className="w-4 h-4" />}
              {added ? 'Adicionado ao Orçamento' : 'Adicionar ao Orçamento'}
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
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { data: productTypes = [] } = useProductTypes()
  const { data: productGroups = [] } = useProductGroups()

  const [searchTerm, setSearchTerm] = useState('')
  const [selectedGroupId, setSelectedGroupId] = useState<string>('')
  const [selectedTypeName, setSelectedTypeName] = useState<string>('')
  const [selected, setSelected] = useState<Product | null>(null)
  const [priceTable, setPriceTable] = useState<PriceTable>(readPriceTable)
  // Só quem recebe as duas tabelas do servidor vê o seletor. Uma vez detectado,
  // ele fica: sem isso o controle piscaria toda vez que um filtro devolvesse uma
  // página em que nenhum produto tem as duas colunas preenchidas.
  const [hasDualPricing, setHasDualPricing] = useState(false)
  const cartQuantities = useCartQuantities(user?.id)
  // Só um card por vez mostra os opcionais expandidos — evita a grade inteira
  // virando um mosaico de painéis abertos ao mesmo tempo.
  const [expandedOptionalsCode, setExpandedOptionalsCode] = useState<string | null>(null)

  const [page, setPage] = useState(1)
  const debouncedSearch = useDebouncedValue(searchTerm.trim(), 300)
  const { data: productsPage, isLoading } = useProductsPage({
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    q: debouncedSearch || undefined,
    group_id: selectedGroupId || undefined,
    type: selectedTypeName || undefined,
    sort_by: 'product_code',
    sort_dir: 'asc',
  })
  const products = useMemo(() => productsPage?.items ?? [], [productsPage])
  const totalProducts = productsPage?.total ?? 0
  const totalPages = productsPage
    ? Math.max(1, Math.ceil(totalProducts / PAGE_SIZE))
    : Math.max(1, page)

  useEffect(() => {
    localStorage.setItem(PRICE_TABLE_KEY, priceTable)
  }, [priceTable])

  useEffect(() => {
    const hasLojista = products.some(product => product.price_lojista != null)
    const hasCorporativo = products.some(product => product.price_corporativo != null)
    if (hasLojista && hasCorporativo) setHasDualPricing(true)
  }, [products])

  useEffect(() => {
    if (products.length === 0) return

    const connection = (
      navigator as Navigator & {
        connection?: { saveData?: boolean; effectiveType?: string }
      }
    ).connection
    if (connection?.saveData || connection?.effectiveType?.includes('2g')) return

    const timer = window.setTimeout(() => {
      products
        .slice(0, FULL_IMAGE_WARMUP_COUNT)
        .forEach(product => warmProductImage(product, 'low'))
    }, 350)

    return () => window.clearTimeout(timer)
  }, [products])

  useEffect(() => {
    if (productsPage && page > totalPages) setPage(totalPages)
  }, [productsPage, page, totalPages])

  useEffect(() => {
    if (!productsPage || page >= totalPages) return
    const options = productsPageQueryOptions({
      skip: page * PAGE_SIZE,
      limit: PAGE_SIZE,
      q: debouncedSearch || undefined,
      group_id: selectedGroupId || undefined,
      type: selectedTypeName || undefined,
      sort_by: 'product_code',
      sort_dir: 'asc',
    })
    const timer = window.setTimeout(() => {
      void queryClient.prefetchQuery(options).then(() => {
        const nextPage = queryClient.getQueryData<PageResult<Product>>(options.queryKey)
        nextPage?.items.slice(0, 8).forEach((product) => {
          const source = product.thumbnail_url ?? product.photo_url
          if (!source) return
          const image = new Image()
          image.decoding = 'async'
          image.src = source
        })
      })
    }, 600)
    return () => window.clearTimeout(timer)
  }, [
    debouncedSearch,
    page,
    productsPage,
    queryClient,
    selectedGroupId,
    selectedTypeName,
    totalPages,
  ])

  function handleGroupChange(groupId: string) {
    setSelectedGroupId(groupId)
    setSelectedTypeName('')
    setPage(1)
  }

  // Types shown in subgroup dropdown cascade from selected group
  const availableTypes = selectedGroupId
    ? productTypes.filter(t => t.group_id === selectedGroupId)
    : productTypes

  const hasFilters = searchTerm || selectedGroupId || selectedTypeName

  function clearFilters() {
    setSearchTerm('')
    setSelectedGroupId('')
    setSelectedTypeName('')
    setPage(1)
  }

  function changePage(nextPage: number) {
    const boundedPage = Math.min(totalPages, Math.max(1, nextPage))
    if (boundedPage === page) return

    setPage(boundedPage)
    window.requestAnimationFrame(() => {
      window.scrollTo({
        top: 0,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
      })
    })
  }

  return (
    <div className="min-h-screen bg-bg pb-24 md:pb-8">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-5 md:mb-6">
          <h2 className="text-xl md:text-2xl font-semibold text-ink" style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}>
            Catálogo de Produtos
          </h2>
          <p className="text-sm text-muted mt-1">Selecione um produto para adicionar ao orçamento</p>
        </div>

        {/* ── Barra de Filtros ─────────────────────────────────────────────── */}
        <div className="bg-white border border-line rounded-xl px-3 py-3 mb-5 md:mb-6 shadow-sm space-y-2 md:space-y-0 md:flex md:items-center md:gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
            <input
              type="text"
              placeholder="Buscar por código ou descrição..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value)
                setPage(1)
              }}
              className="w-full pl-9 pr-8 py-2 text-sm bg-bg border border-line rounded-lg text-ink placeholder-faint focus:outline-none focus:ring-1 focus:ring-gold transition-all"
            />
            {searchTerm && (
              <button onClick={() => { setSearchTerm(''); setPage(1) }} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Group dropdown */}
          <select
            value={selectedGroupId}
            onChange={(e) => handleGroupChange(e.target.value)}
            className="w-full md:w-44 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all"
          >
            <option value="">Todos os Grupos</option>
            {productGroups.map(g => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>

          {/* Subgroup dropdown — cascades from group */}
          <select
            value={selectedTypeName}
            onChange={(e) => {
              setSelectedTypeName(e.target.value)
              setPage(1)
            }}
            className="w-full md:w-48 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all disabled:opacity-50"
            disabled={availableTypes.length === 0}
          >
            <option value="">Todos os Subgrupos</option>
            {availableTypes.map(t => (
              <option key={t.id} value={t.name}>{t.name}</option>
            ))}
          </select>

          {/* Seletor de tabela: fica sempre à vista para o representante
              conferir o estado de relance ANTES de virar a tela para o cliente. */}
          {hasDualPricing && <PriceTableToggle value={priceTable} onChange={setPriceTable} />}

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-gold border border-gold-soft rounded-lg hover:bg-[#fdf9f0] transition-colors"
              style={{ touchAction: 'manipulation' }}
            >
              <X className="w-3 h-3" /> Limpar
            </button>
          )}
        </div>

        {/* Result count */}
        {hasFilters && !isLoading && (
          <p className="text-xs text-muted mb-3">
            {totalProducts === 0
              ? 'Nenhum produto encontrado.'
              : `${totalProducts} produto${totalProducts !== 1 ? 's' : ''} encontrado${totalProducts !== 1 ? 's' : ''}`}
          </p>
        )}

        {isLoading ? (
          <div className="text-center text-muted py-20">Carregando catálogo…</div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center py-20 gap-3">
            <p className="text-muted">Nenhum produto encontrado.</p>
            {hasFilters && (
              <button onClick={clearFilters} className="text-xs text-gold underline">Limpar filtros</button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8">
            {/* Galeria: fotos são todas 1600×1600, então a imagem sangra até a
                borda do card (sem moldura dupla, sem corte) com zoom sutil no
                hover. O título usa Inter para manter letras, códigos e medidas
                numericamente uniformes no catálogo comercial. */}
            {products.map(product => (
              // Wrapper: o botão de adicionar é IRMÃO do card, não filho —
              // <button> dentro de <button> é HTML inválido. Por isso a sombra e
              // o levantar no hover moram aqui, não no card: como irmão, o botão
              // não acompanharia a transform e os dois se descolariam.
              <div
                key={product.id}
                className="group relative rounded-2xl shadow-sm hover:shadow-lg hover:shadow-ink/8 hover:-translate-y-1 transition-all duration-300"
              >
              <button
                onClick={() => setSelected(product)}
                onPointerEnter={() => warmProductImage(product)}
                onPointerDown={() => warmProductImage(product)}
                onFocus={() => warmProductImage(product)}
                className="w-full bg-white border border-line rounded-2xl overflow-hidden text-left active:scale-[0.99] transition-transform duration-300"
                style={{ touchAction: 'manipulation' }}
              >
                {/* object-contain sobre fundo BRANCO: fotos de estúdio têm fundo
                    branco, então a emenda é invisível e o móvel nunca é cortado,
                    qualquer que seja a proporção real do arquivo. (object-cover
                    cortava fotos não-quadradas; contain sobre linho criava
                    moldura dupla.) O padding dá respiro a móveis que encostam
                    nas bordas da própria foto. */}
                <div className="w-full aspect-square overflow-hidden bg-white p-3 md:p-4">
                  {product.photo_url
                    ? <CatalogImage product={product} />
                    : <div className="w-full h-full flex items-center justify-center">
                        <span className="text-muted text-[11px] uppercase tracking-widest">Sem foto</span>
                      </div>
                  }
                </div>
                <div className="px-4 pt-3.5 pb-4 md:px-5 md:pt-4 md:pb-5 border-t border-line/60">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[10px] font-mono font-semibold text-gold tracking-wide">{product.product_code}</span>
                    {selectedGroupId === '' && product.type && (
                      <span className="text-[9px] text-muted uppercase tracking-[0.14em] whitespace-nowrap">{product.type}</span>
                    )}
                  </div>
                  <CardText product={product} priceTable={priceTable} />
                </div>
              </button>

              {/* Seta de opcionais: irmã do botão pela mesma razão do +/- logo
                  abaixo (botão dentro de botão é inválido). O wrapper replica
                  a caixa cheia da foto (mesmo aspect-square, SEM o padding do
                  <div> interno) para que sua borda inferior caia exatamente na
                  costura entre foto e ficha — é aí que a aba fica ancorada,
                  não solta no meio da imagem. pointer-events-none no wrapper
                  deixa a foto por baixo clicável normalmente. */}
              {product.optionals.length > 0 && (
                <div className="absolute top-0 left-0 right-0 aspect-square pointer-events-none">
                  <div className="relative w-full h-full">
                    {expandedOptionalsCode === product.product_code && (
                      <div
                        className="pointer-events-auto absolute inset-x-0 bottom-0 h-1/2 bg-white/95 backdrop-blur-sm p-3 overflow-y-auto"
                        style={{ animation: 'slideUp 0.18s cubic-bezier(0.25,1,0.5,1)' }}
                      >
                        {/* Grade 2 colunas: rótulo da categoria (mudo, pequeno)
                            em cima e cor embaixo (peso médio, ink) — separar
                            as duas linhas evita o "ALUMÍNIO: TAUPE UNIQUE"
                            corrido que antes virava um bloco só de maiúsculas
                            difícil de escanear. Swatch sempre presente (cor
                            sólida quando não há foto) pra grade não desalinhar
                            entre opcionais com e sem imagem. */}
                        <div className="grid grid-cols-2 gap-1.5 content-start">
                          {groupOptionalsByCategory(product.optionals).map(opt => (
                            <div key={opt.category} className="flex items-center gap-1.5 min-w-0 rounded-lg border border-line bg-white px-1.5 py-1">
                              {opt.photo_url
                                ? <img src={opt.thumbnail_url ?? opt.photo_url} alt={opt.color_name} decoding="async" className="w-5 h-5 rounded-full object-cover border border-line flex-shrink-0" />
                                : <span className="w-5 h-5 rounded-full bg-gold/10 border border-line flex-shrink-0" aria-hidden="true" />
                              }
                              <span className="min-w-0 leading-tight">
                                <span className="block text-[7px] uppercase tracking-wide text-muted truncate">{CAT_LABEL[opt.category] ?? opt.category}</span>
                                <span className="block text-[9.5px] font-medium text-ink truncate">{opt.color_name}</span>
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Aba "puxador": metade sobre a foto, metade sobre a
                        ficha — a costura entre as duas já é uma linha real
                        (border-t do bloco de texto), então a aba fica presa
                        num ponto fixo em vez de flutuar sem referência sobre
                        o fundo branco da foto. */}
                    <button
                      type="button"
                      onClick={() => setExpandedOptionalsCode(current => current === product.product_code ? null : product.product_code)}
                      aria-label={expandedOptionalsCode === product.product_code ? 'Ocultar opcionais' : 'Ver opcionais'}
                      aria-expanded={expandedOptionalsCode === product.product_code}
                      style={{ touchAction: 'manipulation' }}
                      className="pointer-events-auto absolute bottom-0 left-1/2 z-10 flex h-8 w-8 -translate-x-1/2 translate-y-1/2 items-center justify-center
                                 rounded-full border border-line bg-white text-gold shadow-md shadow-ink/10
                                 transition-[transform,box-shadow,border-color] duration-200 [transition-timing-function:cubic-bezier(0.25,1,0.5,1)]
                                 hover:scale-110 hover:border-gold/40 hover:shadow-lg active:scale-90"
                    >
                      <ChevronDown
                        className={`w-4 h-4 transition-transform duration-200 [transition-timing-function:cubic-bezier(0.25,1,0.5,1)] ${expandedOptionalsCode === product.product_code ? 'rotate-180' : ''}`}
                        strokeWidth={2.5}
                      />
                    </button>
                  </div>
                </div>
              )}

              {/* Adicionar sem abrir a ficha: o representante em pé no showroom
                  registra "essa, essa e essa" sem quebrar a conversa. Toque
                  repetido incrementa (é o que addToCart já faz), e o número
                  mostra o que esse produto tem no orçamento — sem ele o
                  incremento seria silencioso. O "-" só nasce quando há
                  quantidade a tirar; flex (não offset calculado) empurra o "+"
                  para a direita sozinho quando o irmão aparece. */}
              <div className="absolute top-2 right-2 flex items-center gap-1.5">
                {cartQuantities[product.product_code] > 0 && (
                  <button
                    type="button"
                    onClick={() => user && decrementCart(product, user.id)}
                    aria-label={`Diminuir quantidade de ${product.description} no orçamento`}
                    style={{ touchAction: 'manipulation' }}
                    className="w-11 h-11 rounded-full bg-white text-ink border border-line shadow-md shadow-ink/10
                               flex items-center justify-center transition-transform duration-150
                               hover:bg-bg active:scale-90"
                  >
                    <Minus className="w-5 h-5" strokeWidth={2.5} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => user && addToCart(product, user.id)}
                  aria-label={`Adicionar ${product.description} ao orçamento`}
                  style={{ touchAction: 'manipulation' }}
                  className="w-11 h-11 rounded-full bg-gold text-white shadow-md shadow-ink/15
                             flex items-center justify-center transition-transform duration-150
                             hover:bg-gold-600 active:scale-90"
                >
                  {cartQuantities[product.product_code] ? (
                    <span className="text-sm font-semibold tabular-nums">{cartQuantities[product.product_code]}</span>
                  ) : (
                    <Plus className="w-5 h-5" strokeWidth={2.5} />
                  )}
                </button>
              </div>
              </div>
            ))}
          </div>
        )}
        {!isLoading && totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 mt-8">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => changePage(page - 1)}
              className="px-4 py-2 text-sm border border-line rounded-lg text-ink-2 disabled:opacity-40"
            >
              Anterior
            </button>
            <span className="text-sm text-muted">
              Página <strong className="text-ink">{page}</strong> de {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => changePage(page + 1)}
              className="px-4 py-2 text-sm border border-line rounded-lg text-ink-2 disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        )}
      </div>

      {selected && user && (
        <ProductFullView
          product={selected}
          priceTable={priceTable}
          userId={user.id}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
