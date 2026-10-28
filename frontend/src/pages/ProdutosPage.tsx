import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { optionalName, optionalCategoryLabel, optionalMatchesSearch } from '../lib/optionalLabels'
import { optionalBrand } from '../lib/optionalGroups'
import { useQueryClient } from '@tanstack/react-query'
import { X, ShoppingCart, Check, ImageIcon, Search, Plus, Minus, ChevronDown, ZoomIn, PenLine, SlidersHorizontal } from 'lucide-react'
import { cartStorageKey, configureProductPath, notifyCartChanged, writeCartPriceList } from '../lib/cart'
import { useCartQuantities } from '../hooks/useCart'
import { useAuth } from '../hooks/useAuth'
import { useImageRetry } from '../hooks/useImageRetry'
import { useLocale } from '../hooks/useLocale'
import { productsPageQueryOptions, useProductsPage } from '../hooks/useProducts'
import { useProductTypes } from '../hooks/useProductTypes'
import { useCatalogs } from '../hooks/useCatalogs'
import { useProductGroups } from '../hooks/useProductGroups'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { isConjuntoType } from '../lib/productType'
import { SafePrice } from '../components/SafePrice'
import { OptionalSwatchImage } from '../components/OptionalSwatchImage'
import { OptionalZoomDialog } from '../components/OptionalZoomDialog'
import type { OptionalChoiceInput, OptionalColor, PageResult, Product } from '../types'
import { formatDimensions } from '../lib/measurements'
import { areaLimit, formatArea, isAreaProduct } from '../lib/areaProduct'
import { hasOptionalPhoto } from '../lib/optionalMedia'
import {
  allowedForApplication,
  allowsCustomFor,
  allowsCustomOption,
  applicationName,
  CUSTOM_LEGACY_VALUE,
  CUSTOM_OPTION,
  customOptionLabel,
  productApplications,
  requiredApplicationProgress,
  validateApplicationChoices,
} from '../lib/optionalApplications'

type CatalogSort = 'description_asc' | 'description_desc' | 'code_asc' | 'code_desc'

const CATALOG_SORTS: Record<CatalogSort, { sort_by: 'description' | 'product_code'; sort_dir: 'asc' | 'desc'; pt: string; en: string }> = {
  description_asc: { sort_by: 'description', sort_dir: 'asc', pt: 'Descrição A–Z', en: 'Description A–Z' },
  description_desc: { sort_by: 'description', sort_dir: 'desc', pt: 'Descrição Z–A', en: 'Description Z–A' },
  code_asc: { sort_by: 'product_code', sort_dir: 'asc', pt: 'Código crescente', en: 'Code ascending' },
  code_desc: { sort_by: 'product_code', sort_dir: 'desc', pt: 'Código decrescente', en: 'Code descending' },
}

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
  const { locale } = useLocale()
  const frameRef = useRef<HTMLDivElement>(null)
  const [nearViewport, setNearViewport] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const image = useImageRetry(product.thumbnail_url ?? product.photo_url)

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
      {!loaded && !image.failed && <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-bg via-white to-bg-2" />}
      {image.failed && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-muted text-[11px] uppercase tracking-widest">{locale === 'en-GB' ? 'Image being updated' : 'Imagem em atualização'}</span>
        </div>
      )}
      {nearViewport && image.src && (
        <img
          src={image.src}
          alt={product.description}
          width={320}
          height={320}
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={image.onError}
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
  // Qual `original` já está carregado (cache do módulo) é derivado no render:
  // quando a prop muda, a comparação `loadedSource === original` resolve sem
  // precisar de setState dentro do efeito.
  const [loadedSource, setLoadedSource] = useState<string | null>(
    () => (original != null && loadedFullImages.has(original) ? original : null),
  )
  const originalLoaded = original != null && loadedSource === original

  useEffect(() => {
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
            setLoadedSource(original)
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
// Quem recebe mais de uma tabela escolhe qual fica na tela: o representante em
// visita nunca deixa vários preços visíveis ao mesmo tempo na frente do cliente.
// No EU, a escolha acompanha o carrinho e passa a ser o contrato comercial do
// orçamento. O backend continua sendo a autoridade sobre acesso e descontos.

type PriceKey = 'lojista' | 'corporativo' | 'pvp' | 'arquiteto'
type PriceTable = PriceKey

const PRICE_TABLE_KEY = 'catalogo_tabela_preco'
const PRICE_TABLE_OPTIONS: { value: PriceTable; label: string }[] = [
  { value: 'lojista', label: 'Lojista' },
  { value: 'arquiteto', label: 'Arquiteto' },
  { value: 'corporativo', label: 'Corporativo' },
  { value: 'pvp', label: 'PVP' },
]

// Sem escolha salva ou com um valor legado inválido, usa Lojista.
function readPriceTable(): PriceTable {
  const saved = localStorage.getItem(PRICE_TABLE_KEY)
  if (saved === 'corporativo' || saved === 'pvp' || saved === 'arquiteto') return saved
  return 'lojista'
}

type VisiblePrice = { key: PriceKey; label: string; value: number }

function visiblePrices(product: Product, table: PriceTable): VisiblePrice[] {
  const source = product.market_prices ?? {
    ...(product.price_lojista != null ? { lojista: product.price_lojista } : {}),
    ...(product.price_corporativo != null ? { corporativo: product.price_corporativo } : {}),
  }
  const prices: VisiblePrice[] = PRICE_TABLE_OPTIONS
    .flatMap(option => source[option.value] != null
      ? [{ key: option.value, label: option.label, value: Number(source[option.value]) }]
      : [])

  // Uma tabela selecionada nunca pode exibir o valor de outra. Isso também
  // permite mostrar Arquiteto antes de todos os produtos receberem esse preço:
  // os itens ainda não preenchidos ficam sem valor em vez de cair em Lojista.
  return prices.filter(price => price.key === table)
}

function PriceTableToggle({ value, onChange, available }: { value: PriceTable; onChange: (next: PriceTable) => void; available: PriceKey[] }) {
  const { locale } = useLocale()
  const options = PRICE_TABLE_OPTIONS.filter(option => available.includes(option.value))
  return (
    <div
      role="group"
      aria-label={locale === 'en-GB' ? 'Displayed price list' : 'Tabela de preço apresentada'}
      className="flex w-full md:w-auto flex-shrink-0 items-center gap-0.5 p-0.5 bg-bg border border-line rounded-lg"
    >
      {options.map(({ value: option, label }) => {
        const active = option === value
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            aria-pressed={active}
            className={`flex-1 md:flex-none min-h-11 lg:min-h-0 px-2.5 py-1.5 text-[11px] font-medium rounded-md whitespace-nowrap transition-colors ${
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
  const { locale } = useLocale()
  const prices = visiblePrices(product, priceTable)
  const maximumArea = areaLimit(product)

  return (
    <>
      <h3 className="font-sans font-medium tracking-normal text-[15px] md:text-[17px] text-ink leading-snug mt-1.5 line-clamp-2">
        {product.description}
      </h3>
      {isAreaProduct(product) && (
        <p className="type-meta mt-1.5">
          {locale === 'en-GB' ? 'Sold per m²' : 'Vendido por m²'}
          {maximumArea !== null && <span className="block">{locale === 'en-GB' ? 'Max.' : 'Máx.'} {formatArea(maximumArea, locale)} {locale === 'en-GB' ? 'per item' : 'por item'}</span>}
        </p>
      )}
      {prices.length > 0 && <CardPrice prices={prices} currency={product.currency} locale={product.market_code === 'EU' ? locale : 'pt-BR'} />}
    </>
  )
}

function CardPrice({ prices, currency, locale }: { prices: VisiblePrice[]; currency?: string; locale?: string }) {
  // Uma tabela: o valor em destaque, com o rótulo pequeno embaixo dizendo de
  // qual tabela é — importante quando o produto tem as duas e o representante
  // restringiu a visualização a uma só.
  if (prices.length === 1) {
    return (
      <div className="mt-2">
        <p className="text-[15px] md:text-base font-semibold text-ink tabular-nums leading-tight">
          <SafePrice value={prices[0].value} currency={currency} locale={locale} />
        </p>
        <p className="type-label mt-1">{prices[0].label}</p>
      </div>
    )
  }

  // Duas tabelas (comparativo interno): rótulo à esquerda, valor à direita.
  return (
    <dl className="mt-2 space-y-0.5">
      {prices.map(({ label, value }) => (
        <div key={label} className="flex items-baseline justify-between gap-2">
          <dt className="type-label">{label}</dt>
          <dd className="text-[13px] md:text-sm font-semibold text-ink tabular-nums">
            <SafePrice value={value} currency={currency} locale={locale} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function DetailPrice({ product, priceTable }: { product: Product; priceTable: PriceTable }) {
  const { locale } = useLocale()
  const prices = visiblePrices(product, priceTable)
  if (prices.length === 0) return null

  return (
    <div className="py-4 border-y border-line-soft space-y-2">
      {prices.map(({ label, value }) => (
        <div key={label} className="flex items-baseline justify-between gap-6">
          <span className="type-label flex-shrink-0">
            {prices.length === 1 ? (locale === 'en-GB' ? 'Price' : 'Preço') : label}
          </span>
          <span className="text-lg text-ink font-semibold tabular-nums">
            <SafePrice value={value} currency={product.currency} locale={product.market_code === 'EU' ? locale : 'pt-BR'} />
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

function categoryLabel(category: string, english = false) {
  return optionalCategoryLabel(CAT_LABEL[category] ?? CAT_LABEL[category.toLocaleLowerCase('pt-PT')] ?? category, english)
}

function freeOptionalCategories(product: Product): string[] {
  return (product.all_optionals_categories ?? '')
    .split(',')
    .map(category => category.trim())
    .filter(Boolean)
}

function localizeFurnitureTerm(value: string, locale: 'pt-PT' | 'en-GB') {
  const normalized = value.trim().toLocaleLowerCase('pt-PT')
  const pt: Record<string, string> = {
    banqueta: 'Banco alto', banquetas: 'Bancos altos', poltrona: 'Cadeirão', poltronas: 'Cadeirões',
  }
  const en: Record<string, string> = {
    banqueta: 'Bar stool', banquetas: 'Bar stools', poltrona: 'Armchair', poltronas: 'Armchairs',
    cadeira: 'Chair', cadeiras: 'Chairs', sofá: 'Sofa', sofás: 'Sofas', mesa: 'Table', mesas: 'Tables',
    aparador: 'Console table', aparadores: 'Console tables', conjunto: 'Set', conjuntos: 'Sets',
    luminária: 'Lamp', luminárias: 'Lamps', espreguiçadeira: 'Sun lounger', espreguiçadeiras: 'Sun loungers',
    'carrinho bar': 'Bar trolley', chaise: 'Chaise longue', puff: 'Pouf',
  }
  return (locale === 'en-GB' ? en : pt)[normalized] ?? value
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

function dimLabel(p: Product, locale: 'pt-PT' | 'en-GB' = 'pt-PT') {
  return formatDimensions(p, p.market_code === 'EU' ? 'EU' : 'BR', locale)
}

interface CartSelections {
  opt_categories: Record<string, string>
  optional_choices: OptionalChoiceInput[]
}

interface StoredProductLine extends CartSelections {
  product_code: string
  qty: number
  discount: number
  sold_by_area?: boolean
  area_width_m?: number | null
  area_depth_m?: number | null
  line_id?: string
  _product: Product
}

function sortedChoices(choices: OptionalChoiceInput[] | undefined) {
  return [...(choices ?? [])].sort((left, right) =>
    left.application_id.localeCompare(right.application_id)
      || (left.optional_id ?? '').localeCompare(right.optional_id ?? '')
      || (left.custom_text ?? '').localeCompare(right.custom_text ?? ''),
  )
}

function sameSelections(line: Partial<CartSelections>, selections: CartSelections) {
  const sortedCategories = (categories: Record<string, string> | undefined) =>
    Object.entries(categories ?? {}).sort(([left], [right]) => left.localeCompare(right))

  return JSON.stringify(sortedCategories(line.opt_categories)) === JSON.stringify(sortedCategories(selections.opt_categories))
    && JSON.stringify(sortedChoices(line.optional_choices)) === JSON.stringify(sortedChoices(selections.optional_choices))
}

function addToCart(
  product: Product,
  userId: string,
  market: 'BR' | 'EU',
  priceTable: PriceTable,
  configure: (code: string) => void,
  selected?: CartSelections,
) {
  if (market === 'EU') writeCartPriceList(userId, market, priceTable)
  if (!selected && productApplications(product).length > 0) {
    configure(product.product_code)
    return
  }
  const storageKey = cartStorageKey(userId, market)
  const raw = localStorage.getItem(storageKey)
  let cart: StoredProductLine[] = []
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) cart = parsed as StoredProductLine[]
  } catch {
    cart = []
  }

  const selections: CartSelections = selected ?? {
    opt_categories: product.optionals.reduce<Record<string, string>>((categories, option) => {
      if (!(option.category in categories)) categories[option.category] = option.color_name
      return categories
    }, {}),
    optional_choices: [],
  }
  const areaProduct = isAreaProduct(product)
  if (areaProduct) {
    cart.push({
      line_id: crypto.randomUUID(),
      product_code: product.product_code,
      qty: 1,
      discount: 0,
      sold_by_area: true,
      area_width_m: null,
      area_depth_m: null,
      opt_categories: selections.opt_categories,
      optional_choices: sortedChoices(selections.optional_choices),
      _product: product,
    })
  } else {
    const existing = cart.find(line =>
      line.product_code === product.product_code
        && line.discount === 0
        && sameSelections(line, selections),
    )
    if (existing) {
      existing.qty = existing.qty + 1
    } else {
      cart.push({
        line_id: crypto.randomUUID(),
        product_code: product.product_code,
        qty: 1,
        discount: 0,
        sold_by_area: false,
        opt_categories: selections.opt_categories,
        optional_choices: sortedChoices(selections.optional_choices),
        _product: product,
      })
    }
  }
  localStorage.setItem(storageKey, JSON.stringify(cart))
  notifyCartChanged()
}

// Uma unidade a menos; some do carrinho ao chegar a 0 em vez de deixar qty: 0
// pendurado (o resto do app assume que todo item presente no carrinho tem
// qty > 0 — é o mesmo contrato que readCartQuantities já aplica na leitura).
function decrementCart(product: Product, userId: string, market: 'BR' | 'EU') {
  const storageKey = cartStorageKey(userId, market)
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

function OptionalCatalogGroup({
  id,
  label,
  options,
  selectedId,
  canDeselect,
  english,
  onSelect,
  onZoom,
  allowCustom,
  customSelected,
  onToggleCustom,
}: {
  id: string
  label: string
  options: OptionalColor[]
  selectedId?: string
  canDeselect: boolean
  english: boolean
  onSelect: (optionalId: string | undefined) => void
  onZoom: (optional: OptionalColor, type: string) => void
  /** Mostra a opção "Customizado" (só em Portugal). */
  allowCustom: boolean
  customSelected: boolean
  onToggleCustom: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLocaleLowerCase(english ? 'en-GB' : 'pt-PT')
  const filtered = normalizedQuery
    ? options.filter(option => optionalMatchesSearch(option.color_name, normalizedQuery, english))
    : options
  const visible = normalizedQuery || expanded ? filtered : filtered.slice(0, 12)
  const hasMany = options.length > 12

  return (
    <fieldset className="min-w-0 space-y-3" aria-labelledby={`${id}-label`}>
      <legend id={`${id}-label`} className="text-sm font-semibold text-ink break-words">
        {label}
      </legend>
      {hasMany && (
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
          <span className="sr-only">{english ? `Search in ${label}` : `Buscar em ${label}`}</span>
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder={english ? 'Search by name' : 'Buscar por nome'}
            className="input pl-9 text-base md:text-sm"
          />
        </label>
      )}
      {visible.length > 0 || (allowCustom && !normalizedQuery) ? (
        <div className="flex flex-wrap gap-3">
          {visible.map(option => {
            const selected = option.id === selectedId
            const optionLabel = `${label}: ${optionalName(option.color_name, english)}`
            return (
              <div key={option.id} className="relative w-20">
                <button
                  type="button"
                  aria-pressed={selected}
                  aria-label={optionLabel}
                  onClick={() => onSelect(selected && canDeselect ? undefined : option.id)}
                  className={`group flex w-20 flex-col items-center gap-1.5 rounded-xl border bg-white p-1.5 text-center transition-[border-color,box-shadow,transform] active:scale-[0.98] ${
                    selected ? 'border-gold ring-2 ring-gold' : 'border-line hover:border-gold/60'
                  }`}
                >
                  <span className="relative block h-16 w-16">
                    <OptionalSwatchImage optional={option} variant="thumb" displaySize={64} decorative className="h-16 w-16 rounded-lg border border-line" />
                    {selected && (
                      <span className="absolute bottom-1 left-1 flex h-5 w-5 items-center justify-center rounded-full bg-gold text-white shadow-sm" aria-hidden="true">
                        <Check className="h-3.5 w-3.5" strokeWidth={3} />
                      </span>
                    )}
                  </span>
                  <span className="min-h-8 w-full overflow-hidden text-xs font-medium leading-4 text-ink-2 [overflow-wrap:anywhere]">
                    {optionalName(option.color_name, english)}
                  </span>
                  <span className="text-[10px] text-muted">{optionalBrand(option)}</span>
                </button>
                {hasOptionalPhoto(option) && (
                  <button
                    type="button"
                    onClick={() => onZoom(option, label)}
                    aria-label={english ? `Enlarge ${optionLabel}` : `Ampliar ${optionLabel}`}
                    className="absolute right-1.5 top-1.5 z-10 flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-white/95 text-ink shadow-sm transition-colors hover:border-gold hover:text-gold"
                  >
                    <ZoomIn className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
              </div>
            )
          })}
          {allowCustom && <button
            type="button"
            aria-pressed={customSelected}
            aria-label={`${label}: ${customOptionLabel(english)}`}
            onClick={onToggleCustom}
            className={`flex w-20 flex-col items-center gap-1.5 rounded-xl border bg-white p-1.5 text-center transition-[border-color,box-shadow,transform] active:scale-[0.98] ${
              customSelected ? 'border-gold ring-2 ring-gold' : 'border-line hover:border-gold/60'
            }`}
          >
            <span className="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed border-line text-gold">
              <PenLine className="h-6 w-6" aria-hidden="true" />
            </span>
            <span className="min-h-8 w-full text-xs font-medium leading-4 text-ink-2">{customOptionLabel(english)}</span>
          </button>}
        </div>
      ) : (
        <p className="text-sm text-muted">
          {english ? 'No finishes match this search.' : 'Nenhum acabamento corresponde à busca.'}
        </p>
      )}
      {hasMany && !normalizedQuery && (
        <button
          type="button"
          className="text-sm font-semibold text-gold underline decoration-gold/40 underline-offset-4 hover:text-gold-700"
          onClick={() => setExpanded(current => !current)}
          aria-expanded={expanded}
        >
          {expanded
            ? (english ? 'Show fewer' : 'Mostrar menos')
            : (english ? `View all (${options.length})` : `Ver todas (${options.length})`)}
        </button>
      )}
    </fieldset>
  )
}

// ── Detalhe do produto em tela inteira ────────────────────────────────────────
// Desktop: foto grande à esquerda + detalhes à direita. Mobile: coluna única.

function ProductFullView({
  product,
  priceTable,
  userId,
  market,
  onClose,
}: { product: Product; priceTable: PriceTable; userId: string; market: 'BR' | 'EU'; onClose: () => void }) {
  const [added, setAdded] = useState(false)
  const [validationAlert, setValidationAlert] = useState<string | null>(null)
  const navigate = useNavigate()
  const { locale } = useLocale()
  const english = locale === 'en-GB'
  const [mobileOptModal, setMobileOptModal] = useState<{ optional: OptionalColor; type: string } | null>(null)
  const applications = useMemo(() => productApplications(product), [product])
  const freeCategories = useMemo(() => freeOptionalCategories(product), [product])
  const freeCategorySet = useMemo(() => new Set(freeCategories), [freeCategories])
  const fixedCategories = useMemo(() => Array.from(new Set(
    product.optionals.map(option => option.category).filter(category => !freeCategorySet.has(category)),
  )), [product.optionals, freeCategorySet])
  const fetchedCategories = useMemo(() => Array.from(new Set([
    ...freeCategories,
    ...applications.map(({ application }) => application.category_code),
  ])), [applications, freeCategories])
  const { data: fetchedOptionals = [], isLoading: optionalsLoading, isSuccess: optionalsLoaded } = useOptionalsForCategories(fetchedCategories)
  // Sem a lista do servidor não dá para saber se há acabamento ILYA, então
  // Customizado só aparece depois que ela carrega.
  const fetchedCustom = allowsCustomOption(market) && (fetchedCategories.length === 0 || optionalsLoaded)
  const [categorySelections, setCategorySelections] = useState<Record<string, string>>(() =>
    Object.fromEntries(fixedCategories.flatMap(category => {
      const first = product.optionals.find(option => option.category === category)
      return first ? [[category, first.id]] : []
    })),
  )
  const [applicationSelections, setApplicationSelections] = useState<Record<string, OptionalChoiceInput>>({})
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  const mobileOptModalRef = useRef(mobileOptModal)

  useEffect(() => {
    onCloseRef.current = onClose
    mobileOptModalRef.current = mobileOptModal
  }, [onClose, mobileOptModal])

  useEffect(() => {
    const returnFocus = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (mobileOptModalRef.current) setMobileOptModal(null)
      else onCloseRef.current()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
      returnFocus?.focus()
    }
  }, [])

  const applicationChoices = useMemo<OptionalChoiceInput[]>(() => Object.values(applicationSelections), [applicationSelections])

  function selectCategory(category: string, optionalId: string | undefined) {
    setValidationAlert(null)
    setCategorySelections(current => {
      const next = { ...current }
      if (optionalId) next[category] = optionalId
      else delete next[category]
      return next
    })
  }

  function toggleCategoryCustom(category: string) {
    selectCategory(category, categorySelections[category] === CUSTOM_OPTION ? undefined : CUSTOM_OPTION)
  }

  function toggleApplicationCustom(applicationId: string) {
    selectApplication(applicationId, applicationSelections[applicationId]?.custom_text != null
      ? null
      : { application_id: applicationId, custom_text: '' })
  }

  function selectApplication(applicationId: string, choice: OptionalChoiceInput | null) {
    setValidationAlert(null)
    setApplicationSelections(current => {
      const next = { ...current }
      if (choice) next[applicationId] = choice
      else delete next[applicationId]
      return next
    })
  }
  const progress = requiredApplicationProgress(product, applicationChoices, fetchedOptionals)

  function handleAdd() {
    const errors = validateApplicationChoices(product, applicationChoices, fetchedOptionals)
    if (errors.length > 0 || progress.missing > 0) {
      setValidationAlert(english
        ? 'Choose every required finish before adding this product.'
        : 'Escolha todos os acabamentos obrigatórios antes de adicionar este produto.')
      return
    }

    const optionsByCategory = new Map<string, OptionalColor[]>([
      ...fixedCategories.map(category => [category, product.optionals.filter(option => option.category === category)] as const),
      ...freeCategories.map(category => [category, fetchedOptionals.filter(option => option.category === category)] as const),
    ])
    const opt_categories = Object.entries(categorySelections).reduce<Record<string, string>>((selected, [category, optionalId]) => {
      if (optionalId === CUSTOM_OPTION) {
        selected[category] = CUSTOM_LEGACY_VALUE
        return selected
      }
      const option = optionsByCategory.get(category)?.find(candidate => candidate.id === optionalId)
      if (option) selected[category] = option.color_name
      return selected
    }, {})

    addToCart(
      product,
      userId,
      market,
      priceTable,
      code => navigate(configureProductPath(code)),
      { opt_categories, optional_choices: applicationChoices },
    )
    setValidationAlert(null)
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-white flex flex-col md:flex-row overflow-y-auto md:overflow-hidden"
        style={{ animation: 'fadeIn 0.25s ease-out' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-detail-title"
      >
        <button
          ref={closeButtonRef}
          onClick={onClose}
          className="absolute top-4 right-4 z-20 w-11 h-11 flex items-center justify-center rounded-full bg-white/85 backdrop-blur-sm text-muted hover:text-ink shadow-sm transition-colors"
          style={{ touchAction: 'manipulation' }}
          aria-label={english ? 'Close' : 'Fechar'}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Foto: metade esquerda no desktop, topo no mobile */}
        <div className="md:w-[55%] md:h-full flex-shrink-0 bg-bg flex items-center justify-center p-6 md:p-14">
          {product.photo_url
            ? <FullProductImage product={product} />
            : <div className="w-full h-[40vh] md:h-full flex items-center justify-center">
                <span className="text-muted text-sm tracking-widest uppercase">{english ? 'No photo' : 'Sem foto'}</span>
              </div>
          }
        </div>

        {/* Detalhes: coluna direita, conteúdo centrado verticalmente */}
        <div className="flex-1 min-w-0 md:h-full md:overflow-y-auto">
          <div className="min-h-full flex flex-col justify-center max-w-[480px] mx-auto w-full px-6 md:px-12 py-10 md:py-16 space-y-8" style={{ animation: 'slideUp 0.35s ease-out' }}>
            <div className="space-y-3">
              <p className="type-label">
                {localizeFurnitureTerm(product.type, locale)}
                <span className="mx-2 text-faint">·</span>
                <span className="font-mono normal-case tracking-normal text-gold">{product.product_code}</span>
              </p>
              <h2 id="product-detail-title" className="text-3xl md:text-[2.4rem] leading-[1.12] text-ink text-balance break-words">{product.description}</h2>
              <div className="w-12 h-px bg-gold/50" />
            </div>

            <DetailPrice product={product} priceTable={priceTable} />

            {!isConjuntoType(product.type) && (
              <div className="flex items-baseline gap-6 py-4 border-b border-line-soft">
                <span className="type-label flex-shrink-0">{isAreaProduct(product) ? (english ? 'Sale' : 'Venda') : (english ? 'Dimensions' : 'Dimensões')}</span>
                {isAreaProduct(product) ? (
                  <span className="text-[15px] text-ink-2">
                    {english ? 'Sold per m²' : 'Vendido por m²'}
                    {areaLimit(product) !== null && <span className="block text-xs text-muted mt-1">{english ? 'Max.' : 'Máx.'} {formatArea(areaLimit(product)!, locale)} {english ? 'per item' : 'por item'}</span>}
                  </span>
                ) : (
                  <span className="text-[15px] text-ink-2 font-mono tabular-nums">{dimLabel(product, locale)}</span>
                )}
              </div>
            )}

            {product.observacao && (
              <div className="bg-surface-note border border-line-note rounded-xl p-3">
                <p className="text-xs text-gold font-semibold mb-1 uppercase tracking-wide">{english ? 'Note' : 'Observação'}</p>
                <p className="text-sm text-note-ink italic leading-snug">{product.observacao}</p>
              </div>
            )}

            {isConjuntoType(product.type) ? (
              <div>
                <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3">{english ? 'Items in this set' : 'Componentes deste conjunto'}</p>
                <div className="space-y-2">
                  {product.components.map((comp, idx) => {
                    const dimStr = formatDimensions(comp, market, locale)
                    const catGroups = Array.from(new Set(comp.optionals.map(o => o.category)))
                    return (
                      <div key={idx} className="p-3 rounded-xl border border-line bg-bg">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-ink">{comp.description}</p>
                          <span className="text-xs font-semibold text-ink-2 whitespace-nowrap flex-shrink-0">×{comp.qty}</span>
                        </div>
                        <p className="type-meta mt-1 font-mono tabular-nums">{dimStr}</p>
                        {catGroups.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {catGroups.map(cat => {
                              const opt = comp.optionals.find(o => o.category === cat)!
                              return (
                                <div key={cat} className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-line bg-white">
                                  <OptionalSwatchImage optional={opt} variant="thumb" displaySize={12} decorative className="h-3 w-3 rounded" />
                                  <span className="text-[11px] leading-snug text-ink-2">{categoryLabel(cat, english)}: {optionalName(opt.color_name, english)}</span>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                  {product.components.length === 0 && (
                    <p className="text-xs text-muted italic">{english ? 'No items registered.' : 'Nenhum componente registado.'}</p>
                  )}
                </div>
              </div>
            ) : product.is_set ? (
              <div>
                <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3">{english ? 'Items in this set' : 'Componentes deste conjunto'}</p>
                <div className="space-y-2">
                  {product.set_items.map((item) => (
                    <div key={item.product_code} className="flex items-center gap-3 p-3 rounded-xl border border-line bg-bg">
                      {item.photo_url
                        ? <img src={item.thumbnail_url ?? item.photo_url} alt={item.description} decoding="async" className="w-10 h-10 rounded-lg object-cover border border-line flex-shrink-0" />
                        : <div className="w-10 h-10 rounded-lg bg-bg-2 flex items-center justify-center flex-shrink-0"><ImageIcon className="w-4 h-4 text-faint" /></div>
                      }
                      <div className="flex-1 min-w-0">
                        <span className="type-code block">{item.product_code}</span>
                        <span className="block text-xs text-ink font-medium leading-snug truncate">{item.description}</span>
                      </div>
                      <span className="text-xs font-semibold text-ink-2 whitespace-nowrap flex-shrink-0">×{item.qty}</span>
                    </div>
                  ))}
                  {product.set_items.length === 0 && (
                    <p className="text-xs text-muted italic">{english ? 'No items registered.' : 'Nenhum componente registado.'}</p>
                  )}
                </div>
              </div>
            ) : null}

            {(fixedCategories.length > 0 || freeCategories.length > 0 || applications.length > 0) && (
              <section className="space-y-5 border-t border-line-soft pt-5" aria-labelledby="finish-picker-title">
                <div className="space-y-1.5">
                  <h3 id="finish-picker-title" className="text-xl text-ink">
                    {english ? 'Choose finishes' : 'Escolha os acabamentos'}
                  </h3>
                  {progress.missing > 0 && (
                    <p className="text-sm leading-relaxed text-muted">
                      {english
                        ? `${progress.missing} of ${progress.total} required finishes still ${progress.missing === 1 ? 'needs' : 'need'} a choice.`
                        : `${progress.missing} de ${progress.total} ${progress.missing === 1 ? 'acabamento obrigatório ainda precisa' : 'acabamentos obrigatórios ainda precisam'} de escolha.`}
                    </p>
                  )}
                </div>

                {optionalsLoading && (
                  <p className="text-sm text-muted" role="status">
                    {english ? 'Loading finishes…' : 'A carregar acabamentos…'}
                  </p>
                )}

                {fixedCategories.map(category => {
                  const options = product.optionals.filter(option => option.category === category)
                  return (
                    <OptionalCatalogGroup
                      key={`category-${category}`}
                      id={`category-${category}`}
                      label={categoryLabel(category, english)}
                      options={options}
                      selectedId={categorySelections[category]}
                      canDeselect={options.length > 1}
                      english={english}
                      onSelect={optionalId => selectCategory(category, optionalId)}
                      allowCustom={allowsCustomOption(market) && allowsCustomFor(options)} customSelected={categorySelections[category] === CUSTOM_OPTION}
                      onToggleCustom={() => toggleCategoryCustom(category)}
                      onZoom={(optional, type) => setMobileOptModal({ optional, type })}
                    />
                  )
                })}

                {freeCategories.map(category => {
                  const options = fetchedOptionals.filter(option => option.category === category)
                  return (
                    <OptionalCatalogGroup
                      key={`free-category-${category}`}
                      id={`free-category-${category}`}
                      label={categoryLabel(category, english)}
                      options={options}
                      selectedId={categorySelections[category]}
                      canDeselect
                      english={english}
                      onSelect={optionalId => selectCategory(category, optionalId)}
                      allowCustom={fetchedCustom && allowsCustomFor(options)} customSelected={categorySelections[category] === CUSTOM_OPTION}
                      onToggleCustom={() => toggleCategoryCustom(category)}
                      onZoom={(optional, type) => setMobileOptModal({ optional, type })}
                    />
                  )
                })}

                {applications.map(({ application, componentName }) => {
                  const label = `${componentName ? `${componentName} — ` : ''}${applicationName(application, english)}${application.required ? ' *' : ''}`
                  const options = allowedForApplication(application, fetchedOptionals)
                  return (
                    <OptionalCatalogGroup
                      key={`application-${application.id}`}
                      id={`application-${application.id}`}
                      label={label}
                      options={options}
                      selectedId={applicationSelections[application.id]?.optional_id ?? undefined}
                      canDeselect
                      english={english}
                      onSelect={optionalId => selectApplication(application.id, optionalId ? { application_id: application.id, optional_id: optionalId } : null)}
                      allowCustom={fetchedCustom && allowsCustomFor(options)}
                      customSelected={applicationSelections[application.id]?.custom_text != null}
                      onToggleCustom={() => toggleApplicationCustom(application.id)}
                      onZoom={(optional, type) => setMobileOptModal({ optional, type })}
                    />
                  )
                })}
              </section>
            )}

            {validationAlert && (
              <div role="alert" className="rounded-xl border border-line-note bg-surface-note p-3 text-sm leading-relaxed text-note-ink">
                {validationAlert}
              </div>
            )}

            <div className="space-y-3">
              <button
                onClick={handleAdd}
                style={{ touchAction: 'manipulation' }}
                className={`w-full flex items-center justify-center gap-2.5 py-4 rounded-xl font-semibold text-[13px] uppercase tracking-[0.12em] text-white transition-all active:scale-[0.98] active:opacity-85 ${added ? 'bg-olive' : 'bg-gold'}`}
              >
                {added ? <Check className="w-4 h-4" /> : <ShoppingCart className="w-4 h-4" />}
                {added
                  ? (english ? 'Added to quote' : 'Adicionado ao orçamento')
                  : (english ? 'Add to quote' : 'Adicionar ao orçamento')}
              </button>
              {applications.length > 0 && (
                <button
                  type="button"
                  className="btn-secondary w-full"
                  onClick={() => navigate(configureProductPath(product.product_code))}
                >
                  {english ? 'Configure in quote' : 'Configurar no orçamento'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {mobileOptModal && (
        <OptionalZoomDialog
          optional={mobileOptModal.optional}
          type={mobileOptModal.type}
          onClose={() => setMobileOptModal(null)}
        />
      )}
    </>
  )
}

export default function ProdutosPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { locale, t } = useLocale()
  const english = locale === 'en-GB'
  const queryClient = useQueryClient()
  const { data: productTypes = [] } = useProductTypes()
  const { data: productGroups = [] } = useProductGroups()
  const { data: catalogs = [] } = useCatalogs()

  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCatalogId, setSelectedCatalogId] = useState<string>('')
  const [selectedGroupId, setSelectedGroupId] = useState<string>('')
  const [selectedTypeName, setSelectedTypeName] = useState<string>('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sort, setSort] = useState<CatalogSort>('description_asc')
  const [selected, setSelected] = useState<Product | null>(null)
  const [priceTable, setPriceTable] = useState<PriceTable>(readPriceTable)
  // Só quem recebe as duas tabelas do servidor vê o seletor. Uma vez detectado,
  // ele fica: sem isso o controle piscaria toda vez que um filtro devolvesse uma
  // página em que nenhum produto tem as duas colunas preenchidas.
  const [availablePriceTables, setAvailablePriceTables] = useState<PriceKey[]>([])
  // Tabela de preço efetivamente exibida. Se a escolhida não estiver disponível
  // (ex.: a página atual não trouxe preço corporativo), cai na primeira que
  // estiver — derivado no render, sem efeito para corrigir o estado.
  const activePriceTable: PriceTable =
    availablePriceTables.length === 0 || availablePriceTables.includes(priceTable)
      ? priceTable
      : availablePriceTables[0]
  const cartQuantities = useCartQuantities(user?.id, user?.active_market)
  // Só um card por vez mostra os opcionais expandidos — evita a grade inteira
  // virando um mosaico de painéis abertos ao mesmo tempo.
  const [expandedOptionalsCode, setExpandedOptionalsCode] = useState<string | null>(null)
  const [zoomOptional, setZoomOptional] = useState<{ optional: OptionalColor; type: string } | null>(null)

  const [page, setPage] = useState(1)
  const debouncedSearch = useDebouncedValue(searchTerm.trim(), 300)
  const { data: productsPage, isLoading, isError, refetch, isFetching } = useProductsPage({
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    q: debouncedSearch || undefined,
    catalog_id: selectedCatalogId || undefined,
    group_id: selectedGroupId || undefined,
    type: selectedTypeName || undefined,
    sort_by: CATALOG_SORTS[sort].sort_by,
    sort_dir: CATALOG_SORTS[sort].sort_dir,
    language: locale,
  })
  const products = useMemo(() => productsPage?.items ?? [], [productsPage])
  const totalProducts = productsPage?.total ?? 0
  const totalPages = productsPage
    ? Math.max(1, Math.ceil(totalProducts / PAGE_SIZE))
    : Math.max(1, page)
  // Página fora do intervalo (o total pode encolher entre refetches): corrige
  // durante o render — estado derivado, sem efeito a disparar renders em
  // cascata. A condição é idempotente, então o loop termina na primeira troca.
  if (productsPage && page > totalPages) setPage(totalPages)

  useEffect(() => {
    localStorage.setItem(PRICE_TABLE_KEY, activePriceTable)
  }, [activePriceTable])

  // Operadores podem preparar a nova tabela mesmo enquanto produtos antigos
  // ainda não possuem valor Arquiteto cadastrado.
  const operatorOnEU = user?.active_market === 'EU' && user.role !== 'cliente'
  const priceTableDiscovery = useMemo(() => {
    const discovered = (['lojista', 'corporativo', 'pvp', 'arquiteto'] as PriceKey[]).filter(key =>
      products.some(product => product.market_prices?.[key] != null ||
        (key === 'lojista' && product.price_lojista != null) ||
        (key === 'corporativo' && product.price_corporativo != null))
    )
    const allowed: PriceKey[] = operatorOnEU
      ? ['lojista', 'corporativo', 'pvp', 'arquiteto']
      : user?.active_market === 'BR'
        ? ['lojista', 'corporativo']
        : discovered
    return { discovered, allowed }
  }, [products, operatorOnEU, user?.active_market])
  // Ajuste de estado durante o render (estado derivado, padrão do React — não
  // um efeito): mantém o caráter sticky do que já foi detectado e combina com
  // o que esta página trouxe, sem cascata de renders.
  const [appliedPriceTableDiscovery, setAppliedPriceTableDiscovery] = useState<typeof priceTableDiscovery | null>(null)
  if (appliedPriceTableDiscovery !== priceTableDiscovery) {
    setAppliedPriceTableDiscovery(priceTableDiscovery)
    setAvailablePriceTables(operatorOnEU
      ? (['lojista', 'corporativo', 'pvp', 'arquiteto'] as PriceKey[])
      : Array.from(new Set([
        ...availablePriceTables.filter(key => priceTableDiscovery.allowed.includes(key)),
        ...priceTableDiscovery.discovered,
      ])))
  }

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
    if (!productsPage || page >= totalPages) return
    const options = productsPageQueryOptions({
      skip: page * PAGE_SIZE,
      limit: PAGE_SIZE,
      q: debouncedSearch || undefined,
      catalog_id: selectedCatalogId || undefined,
      group_id: selectedGroupId || undefined,
      type: selectedTypeName || undefined,
      sort_by: CATALOG_SORTS[sort].sort_by,
      sort_dir: CATALOG_SORTS[sort].sort_dir,
      language: locale,
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
    selectedCatalogId,
    selectedGroupId,
    selectedTypeName,
    totalPages,
    locale,
    sort,
  ])

  function handleGroupChange(groupId: string) {
    setSelectedGroupId(groupId)
    setSelectedTypeName('')
    setPage(1)
  }

  const availableGroups = useMemo(() =>
    [...productGroups].sort((a, b) =>
      localizeFurnitureTerm(a.name, locale).localeCompare(
        localizeFurnitureTerm(b.name, locale),
        locale === 'en-GB' ? 'en' : 'pt-BR',
        { sensitivity: 'base' },
      ),
    ),
  [locale, productGroups])

  // Types shown in subgroup dropdown cascade from selected group. Sort after
  // every data refresh so types created later also follow the displayed locale.
  const availableTypes = useMemo(() => {
    const types = selectedGroupId
      ? productTypes.filter(t => t.group_id === selectedGroupId)
      : productTypes

    return [...types].sort((a, b) =>
      localizeFurnitureTerm(a.name, locale).localeCompare(
        localizeFurnitureTerm(b.name, locale),
        locale === 'en-GB' ? 'en' : 'pt-BR',
        { sensitivity: 'base' },
      ),
    )
  }, [locale, productTypes, selectedGroupId])

  const hasFilters = searchTerm || selectedCatalogId || selectedGroupId || selectedTypeName
  const activeFilterCount = [selectedCatalogId, selectedGroupId, selectedTypeName].filter(Boolean).length

  function clearFilters() {
    setSearchTerm('')
    setSelectedCatalogId('')
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
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-5 md:mb-6">
          <h1 className="text-xl md:text-2xl font-semibold text-ink text-balance">
            {t('catalogTitle')}
          </h1>
          <p className="text-sm text-muted mt-1">{t('catalogSubtitle')}</p>
        </div>

        <div className="lg:grid lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-8 lg:items-start">
          <aside
            id="catalog-filters"
            aria-label={english ? 'Filters' : 'Filtros'}
            className={`${filtersOpen ? 'block' : 'hidden'} lg:block lg:sticky lg:top-20 mb-4 lg:mb-0 bg-white border border-line rounded-xl p-4 shadow-sm space-y-4`}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              {english ? 'Filters' : 'Filtros'}
            </p>

            <div>
              <label className="block text-xs font-medium text-muted mb-1" htmlFor="filter-catalog">
                {english ? 'Catalogue' : 'Catálogo'}
              </label>
              <select
                id="filter-catalog"
                value={selectedCatalogId}
                onChange={(e) => {
                  setSelectedCatalogId(e.target.value)
                  setPage(1)
                }}
                className="w-full min-h-11 lg:min-h-0 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all"
              >
                <option value="">{(english ? 'All catalogues' : 'Todos os catálogos').toLocaleUpperCase(locale)}</option>
                {catalogs.map(c => (
                  <option key={c.id} value={c.id}>{c.name.toLocaleUpperCase(locale)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1" htmlFor="filter-group">
                {english ? 'Group' : 'Grupo'}
              </label>
              <select
                id="filter-group"
                value={selectedGroupId}
                onChange={(e) => handleGroupChange(e.target.value)}
                className="w-full min-h-11 lg:min-h-0 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all"
              >
                <option value="">{t('allGroups').toLocaleUpperCase(locale)}</option>
                {availableGroups.map(g => (
                  <option key={g.id} value={g.id}>{localizeFurnitureTerm(g.name, locale).toLocaleUpperCase(locale)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1" htmlFor="filter-type">
                {english ? 'Subgroup' : 'Subgrupo'}
              </label>
              <select
                id="filter-type"
                value={selectedTypeName}
                onChange={(e) => {
                  setSelectedTypeName(e.target.value)
                  setPage(1)
                }}
                className="w-full min-h-11 lg:min-h-0 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all disabled:opacity-50"
                disabled={availableTypes.length === 0}
              >
                <option value="">{t('allSubgroups').toLocaleUpperCase(locale)}</option>
                {availableTypes.map(t => (
                  <option key={t.id} value={t.name}>{localizeFurnitureTerm(t.name, locale).toLocaleUpperCase(locale)}</option>
                ))}
              </select>
            </div>

            {hasFilters && (
              <button
                onClick={clearFilters}
                className="w-full min-h-11 lg:min-h-0 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-gold border border-gold-soft rounded-lg hover:bg-gold-wash transition-colors"
                style={{ touchAction: 'manipulation' }}
              >
                <X className="w-3 h-3" /> {t('clear')}
              </button>
            )}
          </aside>

          <div className="min-w-0">
            <div className="bg-white border border-line rounded-xl px-3 py-3 mb-4 shadow-sm space-y-3">
              {/* Busca */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-3" />
                <input
                  type="text"
                  aria-label={t('searchProducts')}
                  placeholder={t('searchPlaceholder')}
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value)
                    setPage(1)
                  }}
                  className="w-full min-h-11 lg:min-h-0 pl-9 pr-12 lg:pr-8 py-2 text-sm bg-bg border border-line rounded-lg text-ink placeholder:text-muted-3 focus:outline-none focus:ring-1 focus:ring-gold transition-all"
                />
                {searchTerm && (
                  <button aria-label={t('clearSearch')} onClick={() => { setSearchTerm(''); setPage(1) }} className="absolute right-0 top-1/2 h-11 w-11 lg:right-1 lg:h-8 lg:w-8 -translate-y-1/2 flex items-center justify-center text-muted hover:text-ink">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 md:gap-3">
                <button
                  type="button"
                  aria-expanded={filtersOpen}
                  aria-controls="catalog-filters"
                  onClick={() => setFiltersOpen(current => !current)}
                  className="lg:hidden min-h-11 lg:min-h-0 inline-flex items-center gap-2 px-3 py-2 text-xs font-medium text-ink border border-line rounded-lg hover:bg-bg transition-colors"
                  style={{ touchAction: 'manipulation' }}
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" aria-hidden="true" />
                  {english ? 'Filters' : 'Filtros'}
                  {activeFilterCount > 0 && (
                    <span className="rounded-full bg-gold text-white px-1.5 py-0.5 text-[10px] leading-none">
                      {activeFilterCount}
                    </span>
                  )}
                </button>

                {!isLoading && (
                  <p className="text-xs text-muted" aria-live="polite">
                    {totalProducts === 0
                      ? t('noProducts')
                      : locale === 'en-GB'
                        ? `${totalProducts} product${totalProducts !== 1 ? 's' : ''} found`
                        : `${totalProducts} produto${totalProducts !== 1 ? 's' : ''} encontrado${totalProducts !== 1 ? 's' : ''}`}
                  </p>
                )}

                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <label className="text-xs text-muted" htmlFor="catalog-sort">
                    {english ? 'Sort by' : 'Ordenar por'}
                  </label>
                  <select
                    id="catalog-sort"
                    value={sort}
                    onChange={(e) => {
                      setSort(e.target.value as CatalogSort)
                      setPage(1)
                    }}
                    className="min-h-11 lg:min-h-0 py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink-2 focus:outline-none focus:ring-1 focus:ring-gold transition-all"
                  >
                    {Object.entries(CATALOG_SORTS).map(([value, option]) => (
                      <option key={value} value={value}>{english ? option.en : option.pt}</option>
                    ))}
                  </select>
                  {availablePriceTables.length > 1 && <PriceTableToggle value={activePriceTable} onChange={setPriceTable} available={availablePriceTables} />}
                </div>
              </div>

              {activeFilterCount > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {selectedCatalogId && (
                    <button
                      type="button"
                      onClick={() => { setSelectedCatalogId(''); setPage(1) }}
                      className="inline-flex min-h-11 lg:min-h-0 items-center gap-1 rounded-full border border-gold-soft bg-gold-wash px-3 py-1 text-xs text-ink hover:border-gold transition-colors"
                      style={{ touchAction: 'manipulation' }}
                    >
                      {english ? 'Catalogue: ' : 'Catálogo: '}
                      {(catalogs.find(c => c.id === selectedCatalogId)?.name ?? '').toLocaleUpperCase(locale)}
                      <span className="sr-only">{english ? '(remove filter)' : '(remover filtro)'}</span>
                      <X className="w-3 h-3 text-muted" aria-hidden="true" />
                    </button>
                  )}
                  {selectedGroupId && (
                    <button
                      type="button"
                      onClick={() => handleGroupChange('')}
                      className="inline-flex min-h-11 lg:min-h-0 items-center gap-1 rounded-full border border-gold-soft bg-gold-wash px-3 py-1 text-xs text-ink hover:border-gold transition-colors"
                      style={{ touchAction: 'manipulation' }}
                    >
                      {english ? 'Group: ' : 'Grupo: '}
                      {localizeFurnitureTerm(productGroups.find(g => g.id === selectedGroupId)?.name ?? '', locale).toLocaleUpperCase(locale)}
                      <span className="sr-only">{english ? '(remove filter)' : '(remover filtro)'}</span>
                      <X className="w-3 h-3 text-muted" aria-hidden="true" />
                    </button>
                  )}
                  {selectedTypeName && (
                    <button
                      type="button"
                      onClick={() => { setSelectedTypeName(''); setPage(1) }}
                      className="inline-flex min-h-11 lg:min-h-0 items-center gap-1 rounded-full border border-gold-soft bg-gold-wash px-3 py-1 text-xs text-ink hover:border-gold transition-colors"
                      style={{ touchAction: 'manipulation' }}
                    >
                      {english ? 'Subgroup: ' : 'Subgrupo: '}
                      {localizeFurnitureTerm(selectedTypeName, locale).toLocaleUpperCase(locale)}
                      <span className="sr-only">{english ? '(remove filter)' : '(remover filtro)'}</span>
                      <X className="w-3 h-3 text-muted" aria-hidden="true" />
                    </button>
                  )}
                </div>
              )}
            </div>

        {isLoading ? (
          // Esqueleto no formato da grade final: sem salto de layout ao carregar.
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8" role="status" aria-live="polite">
            <span className="sr-only">{t('loadingCatalog')}</span>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} aria-hidden="true" className="rounded-2xl border border-line bg-white overflow-hidden">
                <div className="aspect-square animate-pulse bg-gradient-to-br from-bg via-white to-bg-2" />
                <div className="p-4 space-y-2">
                  <div className="h-3 w-20 rounded bg-line-soft animate-pulse" />
                  <div className="h-4 w-3/4 rounded bg-line-soft animate-pulse" />
                  <div className="h-3 w-1/2 rounded bg-line-soft animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        ) : isError && products.length === 0 ? (
          // Falha de rede não pode virar um falso "nenhum produto cadastrado".
          <div role="alert" className="flex flex-col items-center gap-3 rounded-2xl border border-danger/25 bg-danger-soft px-6 py-12 text-center">
            <p className="text-sm font-medium text-danger">
              {locale === 'en-GB' ? 'The catalogue could not be loaded.' : 'Não foi possível carregar o catálogo.'}
            </p>
            <p className="text-xs text-muted">
              {locale === 'en-GB' ? 'Check your connection and try again.' : 'Verifique a conexão e tente novamente.'}
            </p>
            <button type="button" onClick={() => void refetch()} disabled={isFetching} className="btn-secondary">
              {isFetching
                ? (locale === 'en-GB' ? 'Retrying…' : 'Tentando…')
                : (locale === 'en-GB' ? 'Try again' : 'Tentar novamente')}
            </button>
          </div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center py-20 gap-3">
            <p className="text-muted">{t('noProducts')}</p>
            {hasFilters && (
              <button onClick={clearFilters} className="btn-secondary min-h-11 px-4 text-xs">{t('clearFilters')}</button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8">
            {/* Coluna única abaixo de 640px: em 2 colunas o card ficava com ~163px,
                o stepper cobria metade da foto e a gaveta truncava os acabamentos. */}
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
                className="w-full h-full flex flex-col bg-white border border-line rounded-2xl overflow-hidden text-left active:scale-[0.99] transition-transform duration-300"
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
                        <span className="text-muted text-[11px] uppercase tracking-widest">{locale === 'en-GB' ? 'No photo' : 'Sem foto'}</span>
                      </div>
                  }
                </div>
                <div className="w-full flex-1 px-4 pt-3.5 pb-4 md:px-5 md:pt-4 md:pb-5 border-t border-line/60">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="type-code">{product.product_code}</span>
                    {selectedGroupId === '' && product.type && (
                      <span className="type-label whitespace-nowrap">{localizeFurnitureTerm(product.type, locale)}</span>
                    )}
                  </div>
                  <CardText product={product} priceTable={activePriceTable} />
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
                          {groupOptionalsByCategory(product.optionals).map(opt => {
                            const label = `${categoryLabel(opt.category, english)}: ${optionalName(opt.color_name, english)}`
                            const swatch = <OptionalSwatchImage optional={opt} variant="thumb" displaySize={20} decorative className="h-5 w-5 flex-shrink-0 rounded border border-line" />
                            const text = (
                              <span className="min-w-0 leading-tight">
                                <span className="block text-[10px] uppercase tracking-wide text-muted truncate">{categoryLabel(opt.category, english)}</span>
                                <span className="block text-[11px] leading-tight font-medium text-ink truncate">{optionalName(opt.color_name, english)}</span>
                              </span>
                            )
                            // Só vira botão quando há foto pra ampliar — sem
                            // isso não há o que mostrar num zoom maior que o
                            // próprio swatch já exibe.
                            return hasOptionalPhoto(opt) ? (
                              <button
                                key={opt.category}
                                type="button"
                                onClick={() => setZoomOptional({ optional: opt, type: categoryLabel(opt.category, english) })}
                                aria-label={`Ampliar ${label}`}
                                style={{ touchAction: 'manipulation' }}
                                className="flex min-h-11 items-center gap-1.5 min-w-0 rounded-lg border border-line bg-white px-2 py-1.5 text-left
                                           transition-[transform,border-color] duration-150 hover:border-gold/40 active:scale-95"
                              >
                                {swatch}
                                {text}
                              </button>
                            ) : (
                              <div key={opt.category} className="flex items-center gap-1.5 min-w-0 rounded-lg border border-line bg-white px-1.5 py-1">
                                {swatch}
                                {text}
                              </div>
                            )
                          })}
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
                      aria-label={expandedOptionalsCode === product.product_code
                        ? (locale === 'en-GB' ? 'Hide options' : 'Ocultar opcionais')
                        : (locale === 'en-GB' ? 'View options' : 'Ver opcionais')}
                      aria-expanded={expandedOptionalsCode === product.product_code}
                      style={{ touchAction: 'manipulation' }}
                      className="pointer-events-auto absolute bottom-0 left-1/2 z-10 flex h-11 w-11 -translate-x-1/2 translate-y-1/2 items-center justify-center
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
                {(cartQuantities[product.product_code]?.qty ?? 0) > 0 && (
                  <button
                    type="button"
                    onClick={() => user && decrementCart(product, user.id, user.active_market)}
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
                  onClick={() => user && addToCart(product, user.id, user.active_market, activePriceTable, code => navigate(configureProductPath(code)))}
                  aria-label={locale === 'en-GB' ? `Add ${product.description} to quote` : `Adicionar ${product.description} ao orçamento`}
                  style={{ touchAction: 'manipulation' }}
                  className="w-11 h-11 rounded-full bg-gold text-white shadow-md shadow-ink/15
                             flex items-center justify-center transition-transform duration-150
                             hover:bg-gold-600 active:scale-90"
                >
                  {cartQuantities[product.product_code] ? (
                    <span className="text-sm font-semibold tabular-nums">{cartQuantities[product.product_code].qty}</span>
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
              className="min-h-11 lg:min-h-0 px-4 py-2 text-sm border border-line rounded-lg text-ink-2 disabled:opacity-40"
            >
              {locale === 'en-GB' ? 'Previous' : 'Anterior'}
            </button>
            <span className="text-sm text-muted">
              {locale === 'en-GB' ? 'Page' : 'Página'} <strong className="text-ink">{page}</strong> {locale === 'en-GB' ? 'of' : 'de'} {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => changePage(page + 1)}
              className="min-h-11 lg:min-h-0 px-4 py-2 text-sm border border-line rounded-lg text-ink-2 disabled:opacity-40"
            >
              {locale === 'en-GB' ? 'Next' : 'Próxima'}
            </button>
          </div>
        )}
          </div>
        </div>
      </div>

      {selected && user && (
        <ProductFullView
          key={selected.id}
          product={selected}
          priceTable={activePriceTable}
          userId={user.id}
          market={user.active_market}
          onClose={() => setSelected(null)}
        />
      )}

      {zoomOptional && (
        <OptionalZoomDialog
          optional={zoomOptional.optional}
          type={zoomOptional.type}
          onClose={() => setZoomOptional(null)}
        />
      )}
    </div>
  )
}
