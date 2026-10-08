import { useState, useRef, useEffect } from 'react'
import { DialogPanel } from '../components/Dialog'
import { useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { isConjuntoType } from '../lib/productType'
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Pencil, Trash2, Plus, X, Upload, ImageIcon, Package, Users, UserCheck, Tag, Eye, UserPlus, CheckCircle, LayoutGrid, Search, Columns3, RotateCcw, BookOpen, GripVertical } from 'lucide-react'
import { useProductsPage, useCreateProduct, useUpdateProduct, useDeleteProduct, useUploadProductPhoto } from '../hooks/useProducts'
import { useClientsPage, useCreateClient, useUpdateClient, useDeleteClient } from '../hooks/useClients'
import { useRepresentativesPage, useCreateRepresentative, useUpdateRepresentative, useDeleteRepresentative } from '../hooks/useRepresentatives'
import { useOptionals, useCreateOptional, useUpdateOptional, useDeleteOptional, useUploadOptionalPhoto } from '../hooks/useOptionals'
import { useProductTypes, useCreateProductType, useUpdateProductType, useDeleteProductType } from '../hooks/useProductTypes'
import { useProductGroups, useCreateProductGroup, useUpdateProductGroup, useDeleteProductGroup } from '../hooks/useProductGroups'
import { useCatalogs, useCreateCatalog, useUpdateCatalog, useDeleteCatalog } from '../hooks/useCatalogs'
import type { Catalog } from '../hooks/useCatalogs'
import type { ProductGroup } from '../hooks/useProductGroups'
import type { ProductType } from '../hooks/useProductTypes'
import { useOptionalCategories, useCreateOptionalCategory, useUpdateOptionalCategory, useDeleteOptionalCategory } from '../hooks/useOptionalCategories'
import type { OptionalCategory } from '../hooks/useOptionalCategories'
import { useCreateUserFromClient, useCreateUserFromRep, useIssueClientInvitation } from '../hooks/useUsers'
import type { ClientVerificationMethod, UserCreateResponse } from '../hooks/useUsers'
import { useAuth } from '../hooks/useAuth'
import { useCadastroText } from '../hooks/useCadastroText'
import { NumberField } from '../components/NumberField'
import { formatBrazilianPhone, PHONE_INPUT_MAX_LENGTH } from '../lib/phone'
import { normalizePersonPayload, parseApiError } from '../lib/personForm'
import { formatDimensions } from '../lib/measurements'
import type { Product, ProductCreate, ProductSetComponentCreate, Client, ClientCreate, Representative, ViaCepResponse, OptionalColor, OptionalColorCreate } from '../types'

type Tab = 'produtos' | 'clientes' | 'representantes' | 'opcionais' | 'tipos' | 'catalogos' | 'importacao'
type SortDir = 'asc' | 'desc'

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

const ESTADOS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
  'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
]

// `parseApiError` e a normalização vivem em lib/personForm — compartilhados com
// o cadastro rápido do Orçamento, que antes tinha a própria lógica (divergente).

// DESIGN.md §Sidebar de Abas: só Produtos, Clientes e Representantes têm
// acento próprio; as abas de apoio usam o café neutro. Valores são variáveis
// CSS (tokens), nunca hexadecimais soltos.
const TAB_PALETTE = {
  produtos:        { color: 'var(--color-terracotta)', label: 'Terracota' },
  clientes:        { color: 'var(--color-olive)',      label: 'Verde Oliva' },
  representantes:  { color: 'var(--color-mineral)',    label: 'Azul Mineral' },
  opcionais:       { color: 'var(--color-muted)',      label: 'Neutro' },
  tipos:           { color: 'var(--color-muted)',      label: 'Neutro' },
  catalogos:       { color: 'var(--color-muted)',      label: 'Neutro' },
  importacao:      { color: 'var(--color-muted)',      label: 'Neutro' },
} as const

// Lavagem translúcida de um acento (substitui o antigo `${hex}12`, que não
// funciona com variáveis CSS).
function tint(color: string, percent: number) {
  return `color-mix(in srgb, ${color} ${percent}%, transparent)`
}

// ── helpers ─────────────────────────────────────────────────────────────────

function SortIcon({ active, dir, color }: { active: boolean; dir: SortDir; color: string }) {
  if (!active) return <ChevronUp className="w-3 h-3 opacity-25" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3" style={{ color }} />
    : <ChevronDown className="w-3 h-3" style={{ color }} />
}

function Th({ label, col, sortKey, sortDir, onSort, color }: {
  label: string; col: string; sortKey: string; sortDir: SortDir; onSort: (k: string) => void; color: string
}) {
  return (
    <th
      className="px-4 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider cursor-pointer select-none transition-colors"
      onClick={() => onSort(col)}
      onMouseEnter={(e) => (e.currentTarget.style.color = color)}
      onMouseLeave={(e) => (e.currentTarget.style.color = '')}
    >
      <span className="flex items-center gap-1">
        {label}
        <SortIcon active={sortKey === col} dir={sortDir} color={color} />
      </span>
    </th>
  )
}

type ProductColumnKey = 'code' | 'description' | 'dimensions' | 'price_lojista' | 'price_corporativo' | 'price_pvp' | 'optionals' | 'photo' | 'actions'

const PRODUCT_COLUMN_MIN_WIDTHS: Record<ProductColumnKey, number> = {
  code: 110,
  description: 180,
  dimensions: 190,
  price_lojista: 120,
  price_corporativo: 120,
  price_pvp: 120,
  optionals: 150,
  photo: 72,
  actions: 72,
}

const INITIAL_PRODUCT_COLUMN_WIDTHS: Record<ProductColumnKey, number> = {
  code: 140,
  description: 320,
  dimensions: 270,
  price_lojista: 140,
  price_corporativo: 140,
  price_pvp: 140,
  optionals: 240,
  photo: 88,
  actions: 80,
}

function ResizableProductTh({
  label,
  column,
  width,
  onResize,
  onAutoFit,
  color,
  sort,
}: {
  label: string
  column: ProductColumnKey
  width: number
  onResize: (column: ProductColumnKey, width: number) => void
  onAutoFit: (column: ProductColumnKey) => void
  color: string
  sort?: { active: boolean; dir: SortDir; onClick: () => void }
}) {
  const tx = useCadastroText()
  function startResize(e: React.MouseEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startWidth = width

    // Um setState por frame, não por evento: mousemove dispara bem acima de
    // 60 Hz e cada atualização re-renderiza a tabela inteira.
    let rafId: number | null = null
    let pendingX = startX

    function handleMove(event: MouseEvent) {
      pendingX = event.clientX
      if (rafId !== null) return
      rafId = requestAnimationFrame(() => {
        rafId = null
        onResize(column, startWidth + pendingX - startX)
      })
    }

    function handleUp() {
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
        onResize(column, startWidth + pendingX - startX)
      }
      document.removeEventListener('mousemove', handleMove)
      document.removeEventListener('mouseup', handleUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', handleMove)
    document.addEventListener('mouseup', handleUp)
  }

  return (
    <th
      data-product-col={column}
      className={`relative px-4 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider select-none ${sort ? 'cursor-pointer' : ''}`}
      style={{ width }}
      onClick={sort?.onClick}
      onMouseEnter={(e) => { if (sort) e.currentTarget.style.color = color }}
      onMouseLeave={(e) => { e.currentTarget.style.color = '' }}
    >
      <span className="flex items-center gap-1">
        {label}
        {sort && <SortIcon active={sort.active} dir={sort.dir} color={color} />}
      </span>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={tx('Redimensionar coluna {label}', { label: label || column })}
        title={tx('Arraste para redimensionar · Duplo clique para autoajustar')}
        className="absolute -right-1 top-0 z-10 h-full w-2 cursor-col-resize group"
        onMouseDown={startResize}
        onDoubleClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onAutoFit(column)
        }}
      >
        <span className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-line group-hover:w-0.5" style={{ '--tw-bg-opacity': 1 } as React.CSSProperties} />
      </div>
    </th>
  )
}

async function fetchCep(cep: string, signal?: AbortSignal): Promise<ViaCepResponse | null> {
  const clean = cep.replace(/\D/g, '')
  if (clean.length !== 8) return null
  try {
    const r = await api.get<ViaCepResponse>(`/utils/cep/${clean}`, { signal })
    return r.data
  } catch {
    return null
  }
}

async function fetchPortugalPostalCode(postalCode: string, signal?: AbortSignal): Promise<ViaCepResponse | null> {
  const clean = postalCode.replace(/\D/g, '')
  if (clean.length !== 7) return null
  try {
    const r = await api.get<ViaCepResponse>(`/utils/postal-code/${clean}`, { signal })
    return r.data
  } catch {
    return null
  }
}

// ── Address form fields ──────────────────────────────────────────────────────

function formatCep(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 8)
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits
}

function formatPortugalPostalCode(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 7)
  return digits.length > 4 ? `${digits.slice(0, 4)}-${digits.slice(4)}` : digits
}

function formatOnlyNumbers(value: string): string {
  return value.replace(/\D/g, '')
}

// Máscara alterna em 11 dígitos: o mesmo campo aceita CPF e CNPJ, e o
// backend guarda só os dígitos (normalize_cpf_cnpj).
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

function AddressFields({ form, setForm, market }: { form: ClientCreate; setForm: (v: ClientCreate) => void; market: 'BR' | 'EU' }) {
  const tx = useCadastroText()
  const [cepLoading, setCepLoading] = useState(false)
  const cepAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => cepAbortRef.current?.abort(), [])

  async function handleCepBlur() {
    if (market !== 'BR' && market !== 'EU') return
    cepAbortRef.current?.abort()
    const controller = new AbortController()
    cepAbortRef.current = controller
    setCepLoading(true)
    const data = market === 'BR'
      ? await fetchCep(form.cep, controller.signal)
      : await fetchPortugalPostalCode(form.cep, controller.signal)
    if (controller.signal.aborted) return
    if (data) {
      setForm({
        ...form,
        address: data.logradouro ? `${data.logradouro}${data.bairro ? ', ' + data.bairro : ''}` : form.address,
        city: data.localidade || form.city,
        state: market === 'BR' ? data.uf : '--',
        region: market === 'EU' ? (data.regiao || form.region) : form.region,
      })
    }
    setCepLoading(false)
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-muted">{tx('Nome *')}</span>
        <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">{tx('Telefone *')}</span>
        <input className="input" value={form.phone} maxLength={market === 'BR' ? PHONE_INPUT_MAX_LENGTH : 20} onChange={(e) => setForm({ ...form, phone: market === 'BR' ? formatBrazilianPhone(e.target.value) : e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">{tx('E-mail')}</span>
        <input className="input" type="email" value={form.email ?? ''} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">{market === 'EU' ? 'VAT / Tax ID' : 'CPF/CNPJ'}</span>
        <input className="input" value={market === 'EU' ? (form.tax_id ?? '') : (form.cpf_cnpj ?? '')} onChange={(e) => market === 'EU' ? setForm({ ...form, tax_id: e.target.value }) : setForm({ ...form, cpf_cnpj: formatCpfCnpj(e.target.value) })} maxLength={market === 'EU' ? 40 : 18} />
      </label>
      <label className="flex flex-col gap-1 relative">
        <span className="text-xs text-muted">{tx(market === 'EU' ? 'Código postal *' : 'CEP *')}</span>
        <input className="input pr-8" value={form.cep} onChange={(e) => setForm({ ...form, cep: market === 'BR' ? formatCep(e.target.value) : formatPortugalPostalCode(e.target.value) })} onBlur={handleCepBlur} maxLength={market === 'BR' ? 9 : 8} required />
        {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-gold animate-pulse">...</span>}
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">{tx('Número')}</span>
        {/* Portugal: porta com letra/andar ("12A", "2.º Esq.") — só dígitos cortava a morada. */}
        <input className="input" value={form.numero ?? ''} maxLength={50} onChange={(e) => setForm({ ...form, numero: market === 'BR' ? formatOnlyNumbers(e.target.value) : e.target.value })} />
      </label>
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-muted">{tx('Endereço *')}</span>
        <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">{tx(market === 'EU' ? 'Localidade *' : 'Cidade *')}</span>
        <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required />
      </label>
      {market === 'BR' ? (
        <label className="flex flex-col gap-1"><span className="text-xs text-muted">Estado *</span><select className="input" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} required><option value="">UF</option>{ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
      ) : (
        <>
          <label className="flex flex-col gap-1"><span className="text-xs text-muted">{tx('País da primeira liberação')}</span><input className="input" value="PT" readOnly aria-readonly="true" /></label>
          <label className="col-span-2 flex flex-col gap-1"><span className="text-xs text-muted">{tx('Região')}</span><input className="input" value={form.region ?? ''} onChange={(e) => setForm({ ...form, region: e.target.value })} maxLength={120} /></label>
        </>
      )}
    </div>
  )
}

// ── Modal wrapper ─────────────────────────────────────────────────────────────

function Modal({ title, onClose, children, accentColor }: {
  title: string; onClose: () => void; children: React.ReactNode; accentColor?: string
}) {
  const tx = useCadastroText()
  return (
    <div className="modal-overlay" onClick={onClose}>
      <DialogPanel onClose={onClose} className="modal-panel w-full max-w-lg mx-4 md:mx-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-line"
          style={accentColor ? { borderLeftColor: accentColor, borderLeftWidth: 3 } : {}}>
          <h3 className="text-base font-semibold text-ink">{title}</h3>
          <button type="button" onClick={onClose} className="btn-icon -mr-2" aria-label={tx('Fechar')}><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 max-h-[80vh] overflow-y-auto">{children}</div>
      </DialogPanel>
    </div>
  )
}

function ConfirmDelete({ name, onConfirm, onCancel }: { name: string; onConfirm: () => void; onCancel: () => void }) {
  const tx = useCadastroText()
  return (
    <Modal title={tx('Confirmar exclusão')} onClose={onCancel}>
      <p className="text-ink-2 mb-6">{tx('Excluir')} <span className="text-ink font-medium">"{name}"</span>{tx('? Esta ação não pode ser desfeita.')}</p>
      <div className="flex justify-end gap-3">
        <button className="btn-secondary" onClick={onCancel}>{tx('Cancelar')}</button>
        <button className="btn-danger" onClick={onConfirm}>{tx('Excluir')}</button>
      </div>
    </Modal>
  )
}

// ── PRODUTOS ──────────────────────────────────────────────────────────────────

const EMPTY_PRODUCT: ProductCreate = {
  product_code: '', description: '', type: 'Outro', catalog_id: null, is_circular: false,
  is_set: false, set_items: [], components: [],
  altura: 0, largura: 0, profundidade: 0, price: 0, price_lojista: 0, price_corporativo: 0, price_pvp: 0, observacao: null,
  all_optionals_categories: null, optional_ids: [],
}

const EMPTY_COMP: ProductSetComponentCreate = {
  description: '', is_circular: false, altura: 0, largura: 0, profundidade: 0, qty: 1, optional_ids: [],
}

/** Agrupa opcionais pelo código de categoria (exato, sem normalização) — o
 * resolver de label vem sempre do que está cadastrado no banco (V-Bloco65-cats),
 * nunca de uma lista fixa no código, para não mascarar categorias divergentes. */
function groupOptionalsByCategory(optionals: OptionalColor[], catLabel: (code: string) => string = (c) => c): { category: string; label: string; items: OptionalColor[] }[] {
  const map = new Map<string, OptionalColor[]>()
  for (const opt of optionals) {
    if (!map.has(opt.category)) map.set(opt.category, [])
    map.get(opt.category)!.push(opt)
  }
  return Array.from(map.entries()).map(([category, items]) => ({
    category,
    label: catLabel(category),
    items,
  }))
}

/** Bloco 75: mescla categorias liberadas via "Permitir todos" (all_optionals_categories)
 * com os opcionais específicos do produto (p.optionals), já que uma categoria marcada
 * como "Permitir todos" não tem itens individuais em p.optionals e ficava invisível
 * na listagem. Categorias globais recebem o sufixo "(Todos)". */
function getProductOptionalsLabel(
  p: Pick<Product, 'optionals' | 'all_optionals_categories'>,
  catLabel: (code: string) => string = (c) => c,
  separator: string = ', ',
  allLabel: string = 'Todos',
): string {
  const specificGroups = groupOptionalsByCategory(p.optionals, catLabel)
  const specificCats = new Set(specificGroups.map(g => g.category))
  const globalCats = (p.all_optionals_categories ?? '').split(',').filter(Boolean)
  const labels = [
    ...globalCats.filter(c => !specificCats.has(c)).map(c => `${catLabel(c)} (${allLabel})`),
    ...specificGroups.map(g => g.label),
  ]
  return labels.join(separator)
}

// ── Paginação ergonômica (Bloco 64) ───────────────────────────────────────────
const ITEMS_PER_PAGE = 10

/** Fatia a lista para a página atual, corrigindo páginas fora do intervalo. */
function paginate<T>(items: T[], page: number): { pageItems: T[]; totalPages: number; safePage: number } {
  const totalPages = Math.max(1, Math.ceil(items.length / ITEMS_PER_PAGE))
  const safePage = Math.min(Math.max(1, page), totalPages)
  const start = (safePage - 1) * ITEMS_PER_PAGE
  return { pageItems: items.slice(start, start + ITEMS_PER_PAGE), totalPages, safePage }
}

function Pagination({ page, totalPages, onPage, color }: {
  page: number; totalPages: number; onPage: (p: number) => void; color: string
}) {
  const tx = useCadastroText()
  if (totalPages <= 1) return null
  const canPrev = page > 1
  const canNext = page < totalPages
  const base = "flex items-center gap-1 px-3.5 py-2 rounded-lg border text-sm font-medium transition-[background-color,color,border-color,transform,opacity] active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
  const ring = (e: React.FocusEvent<HTMLButtonElement>, on: boolean) => { e.currentTarget.style.boxShadow = on ? `0 0 0 3px ${tint(color, 20)}` : '' }
  return (
    <div className="flex items-center justify-center gap-3 mt-4">
      <button type="button" disabled={!canPrev} onClick={() => onPage(page - 1)}
        className={base} style={{ borderColor: 'var(--color-line)', backgroundColor: 'var(--color-surface-quiet)', color: canPrev ? 'var(--color-ink-2)' : 'var(--color-faint)' }}
        onFocus={(e) => ring(e, canPrev)} onBlur={(e) => ring(e, false)}>
        <ChevronLeft className="w-4 h-4" /> {tx('Anterior')}
      </button>
      <span className="text-sm text-ink-3 tabular-nums select-none">{tx('Página')} <span className="font-semibold text-ink">{page}</span> {tx('de')} {totalPages}</span>
      <button type="button" disabled={!canNext} onClick={() => onPage(page + 1)}
        className={base} style={{ borderColor: 'var(--color-line)', backgroundColor: 'var(--color-surface-quiet)', color: canNext ? 'var(--color-ink-2)' : 'var(--color-faint)' }}
        onFocus={(e) => ring(e, canNext)} onBlur={(e) => ring(e, false)}>
        {tx('Próximo')} <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  )
}

// ── Bloco 71: Upload de Fotos em Lote (dropzone + fila concorrente) ───────────

type BatchStatus = 'pending' | 'uploading' | 'success' | 'error'
interface BatchItem { file: File; sku: string; product: Product; status: BatchStatus; error?: string }
interface BatchRejection { key: string; name: string; reason: string }

async function traverseFileTree(entry: FileSystemEntryLike): Promise<File[]> {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file!((file: File) => resolve([file]))
    } else if (entry.isDirectory) {
      const reader = entry.createReader!()
      const collected: File[] = []
      const readBatch = () => {
        reader.readEntries(async (entries: FileSystemEntryLike[]) => {
          if (!entries.length) { resolve(collected); return }
          for (const child of entries) collected.push(...(await traverseFileTree(child)))
          readBatch()
        })
      }
      readBatch()
    } else {
      resolve([])
    }
  })
}

interface FileSystemEntryLike {
  isFile: boolean
  isDirectory: boolean
  file?: (cb: (file: File) => void) => void
  createReader?: () => { readEntries: (cb: (entries: FileSystemEntryLike[]) => void) => void }
}

function skuFromFilename(name: string): string {
  return name.replace(/\.[^./\\]+$/, '').trim().toUpperCase()
}

function BatchPhotoUpload({ color, title = 'Upload de Fotos em Lote', collapsible = true }: {
  color: string; title?: string; collapsible?: boolean
}) {
  const queryClient = useQueryClient()
  const tx = useCadastroText()
  const [open, setOpen] = useState(!collapsible)
  const [items, setItems] = useState<BatchItem[]>([])
  const [rejected, setRejected] = useState<BatchRejection[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const dirInputRef = useRef<HTMLInputElement>(null)
  const filesInputRef = useRef<HTMLInputElement>(null)
  const resolutionGenerationRef = useRef(0)

  useEffect(() => () => {
    resolutionGenerationRef.current += 1
  }, [])

  function beginResolution(): number | null {
    if (uploading || resolving) return null
    const generation = resolutionGenerationRef.current + 1
    resolutionGenerationRef.current = generation
    setItems([])
    setRejected([])
    setLookupError(null)
    setResolving(true)
    return generation
  }

  async function processFiles(files: File[], generation: number) {
    const imageFiles = files.filter((file) =>
      /\.(jpg|jpeg|png|webp)$/i.test(file.name)
    )
    const codes = Array.from(
      new Set(imageFiles.map((file) => skuFromFilename(file.name))),
    )
    try {
      const products: Product[] = []
      for (let offset = 0; offset < codes.length; offset += 100) {
        const response = await api.post<Product[]>('/products/batch', {
          product_codes: codes.slice(offset, offset + 100),
        })
        if (resolutionGenerationRef.current !== generation) return
        products.push(...response.data)
      }
      const bySku = new Map(
        products.map((product) => [
          product.product_code.toUpperCase(),
          product,
        ]),
      )
      const validated: BatchItem[] = []
      const rejectedItems: BatchRejection[] = []
      const skuCounts = new Map<string, number>()
      for (const file of imageFiles) {
        const sku = skuFromFilename(file.name)
        skuCounts.set(sku, (skuCounts.get(sku) ?? 0) + 1)
      }
      for (const [index, file] of imageFiles.entries()) {
        const sku = skuFromFilename(file.name)
        if ((skuCounts.get(sku) ?? 0) > 1) {
          rejectedItems.push({
            key: `duplicate:${sku}:${index}`,
            name: file.name,
            reason: tx('SKU {sku} repetido na seleção', { sku }),
          })
          continue
        }
        const product = bySku.get(sku)
        if (product) validated.push({ file, sku, product, status: 'pending' })
        else {
          rejectedItems.push({
            key: `missing:${sku}:${index}`,
            name: file.name,
            reason: tx('SKU não encontrado'),
          })
        }
      }
      if (resolutionGenerationRef.current !== generation) return
      setItems(validated)
      setRejected(rejectedItems)
    } catch {
      if (resolutionGenerationRef.current !== generation) return
      setItems([])
      setRejected([])
      setLookupError(
        tx('Não foi possível validar os códigos dos arquivos. Tente novamente.'),
      )
    } finally {
      if (resolutionGenerationRef.current === generation) {
        setResolving(false)
      }
    }
  }

  async function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const generation = beginResolution()
    if (generation === null) return
    const dt = e.dataTransfer
    const dtItems = dt.items
    try {
      if (dtItems && dtItems.length > 0 && (dtItems[0] as unknown as { webkitGetAsEntry?: unknown }).webkitGetAsEntry) {
        const entries: FileSystemEntryLike[] = []
        for (let i = 0; i < dtItems.length; i++) {
          const entry = (dtItems[i] as unknown as { webkitGetAsEntry: () => FileSystemEntryLike | null }).webkitGetAsEntry()
          if (entry) entries.push(entry)
        }
        const files = (await Promise.all(entries.map((entry) => traverseFileTree(entry)))).flat()
        await processFiles(files, generation)
      } else {
        await processFiles(Array.from(dt.files), generation)
      }
    } catch {
      if (resolutionGenerationRef.current === generation) {
        setItems([])
        setRejected([])
        setLookupError(tx('Não foi possível ler os arquivos selecionados.'))
        setResolving(false)
      }
    }
  }

  function handleFileSelection(files: File[]) {
    const generation = beginResolution()
    if (generation !== null) void processFiles(files, generation)
  }

  async function startUpload() {
    if (uploading || resolving || items.length === 0) return
    setUploading(true)
    const queue = [...items]
    setItems((prev) => prev.map((i) => ({ ...i, status: 'pending' })))

    async function worker() {
      for (;;) {
        const next = queue.shift()
        if (!next) return
        setItems((prev) => prev.map((i) => (i.file === next.file ? { ...i, status: 'uploading' } : i)))
        try {
          const form = new FormData()
          form.append('file', next.file)
          await api.post(`/products/${next.product.id}/upload-photo`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          setItems((prev) => prev.map((i) => (i.file === next.file ? { ...i, status: 'success' } : i)))
        } catch (err) {
          setItems((prev) => prev.map((i) => (i.file === next.file ? { ...i, status: 'error', error: parseApiError(err) } : i)))
        }
      }
    }

    await Promise.all([worker(), worker(), worker()]) // 3 requisições concorrentes (evita estouro de buffer no Railway)
    queryClient.invalidateQueries({ queryKey: ['products'] })
    setUploading(false)
  }

  const doneCount = items.filter((i) => i.status === 'success' || i.status === 'error').length
  const progress = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 0

  return (
    <div className={collapsible ? 'mb-4 border border-line rounded-xl overflow-hidden' : ''}>
      {collapsible ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-3 bg-surface-quiet text-left"
        >
          <span className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Upload className="w-4 h-4" style={{ color }} /> {tx(title)}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
        </button>
      ) : (
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2 mb-3"><ImageIcon className="w-4 h-4" style={{ color }} /> {tx(title)}</h3>
      )}

      {open && (
        <div className={collapsible ? 'p-4 border-t border-line space-y-4' : 'space-y-4'}>
          <div
            onDragOver={(e) => {
              e.preventDefault()
              if (!uploading && !resolving) setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${uploading || resolving ? 'opacity-60' : ''}`}
            style={{ borderColor: dragOver ? color : 'var(--color-line)', backgroundColor: dragOver ? `${tint(color, 4)}` : 'var(--color-surface-quiet)' }}
          >
            <Upload className="w-6 h-6 mx-auto mb-2" style={{ color: dragOver ? color : 'var(--color-faint)' }} />
            <p className="text-sm text-ink-3">{tx('Arraste uma pasta ou arquivos de fotos aqui')}</p>
            <p className="text-xs text-muted mt-1">{tx('O nome do arquivo deve ser o código do produto (ex.: IML0001.png)')}</p>
            <div className="flex items-center justify-center gap-2 mt-3">
              <button type="button" disabled={uploading || resolving} className="btn-secondary text-xs disabled:opacity-50" onClick={() => dirInputRef.current?.click()}>{tx('Selecionar pasta')}</button>
              <button type="button" disabled={uploading || resolving} className="btn-secondary text-xs disabled:opacity-50" onClick={() => filesInputRef.current?.click()}>{tx('Selecionar arquivos')}</button>
            </div>
            <input
              ref={dirInputRef} type="file" multiple disabled={uploading || resolving} className="hidden"
              {...({ webkitdirectory: 'true', directory: 'true' } as Record<string, string>)}
              onChange={(e) => {
                const files = Array.from(e.currentTarget.files ?? [])
                e.currentTarget.value = ''
                handleFileSelection(files)
              }}
            />
            <input
              ref={filesInputRef} type="file" multiple disabled={uploading || resolving} accept="image/png,image/jpeg,image/webp" className="hidden"
              onChange={(e) => {
                const files = Array.from(e.currentTarget.files ?? [])
                e.currentTarget.value = ''
                handleFileSelection(files)
              }}
            />
          </div>

          {resolving && (
            <p className="text-xs text-muted">{tx('Validando códigos no catálogo…')}</p>
          )}
          {lookupError && (
            <p className="text-xs text-danger">{lookupError}</p>
          )}
          {(items.length > 0 || rejected.length > 0) && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-4 text-xs">
                <span className="flex items-center gap-1.5 text-success"><CheckCircle className="w-3.5 h-3.5" /> {tx('{count} validada(s)', { count: items.length })}</span>
                {rejected.length > 0 && <span className="flex items-center gap-1.5 text-terracotta"><X className="w-3.5 h-3.5" /> {tx('{count} rejeitada(s)', { count: rejected.length })}</span>}
              </div>

              {rejected.length > 0 && (
                <div className="bg-danger-soft border border-danger/25 rounded-lg p-2.5 max-h-24 overflow-y-auto">
                  {rejected.map((item) => (
                    <p key={item.key} className="text-[11px] text-terracotta font-mono">
                      {item.name} — {item.reason}
                    </p>
                  ))}
                </div>
              )}

              {items.length > 0 && (
                <>
                  {uploading && (
                    <div className="w-full h-2 bg-bg-2 rounded-full overflow-hidden">
                      <div className="h-full transition-[width]" style={{ width: `${progress}%`, backgroundColor: color }} />
                    </div>
                  )}
                  <div className="max-h-56 overflow-y-auto border border-line rounded-lg divide-y divide-bg-2">
                    {items.map((item, index) => (
                      <div key={`${item.sku}:${item.file.webkitRelativePath || item.file.name}:${item.file.size}:${item.file.lastModified}:${index}`} className="flex items-center justify-between px-3 py-1.5 text-xs">
                        <span className="font-mono text-ink-2 truncate">{item.sku}</span>
                        <span className="text-muted truncate flex-1 px-2">{item.file.name}</span>
                        {item.status === 'pending' && <span className="text-muted">{tx('Aguardando')}</span>}
                        {item.status === 'uploading' && <span style={{ color }}>{tx('Enviando…')}</span>}
                        {item.status === 'success' && <span className="flex items-center gap-1 text-success"><CheckCircle className="w-3.5 h-3.5" /> {tx('Enviada')}</span>}
                        {item.status === 'error' && <span className="text-terracotta" title={item.error}>{tx('Erro')}</span>}
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={uploading || resolving}
                    onClick={startUpload}
                    className="btn-primary w-full disabled:opacity-60"
                    style={{ backgroundColor: color }}
                  >
                    {uploading ? tx('Enviando… {progress}%', { progress }) : tx('Iniciar Upload ({count})', { count: items.length })}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ProductsTab({ color, page, onPage }: { color: string; page: number; onPage: (p: number) => void }) {
  const { user } = useAuth()
  const tx = useCadastroText()
  const isEurope = user?.active_market === 'EU'
  const canClassifyBr = !isEurope && user?.role === 'admin'
  const locale = isEurope ? 'pt-PT' : 'pt-BR'
  const currency = isEurope ? 'EUR' : 'BRL'
  const money = (value: number | null | undefined) => new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value ?? 0))
  const marketPrice = (product: Product, key: 'lojista' | 'corporativo' | 'pvp') =>
    product.market_prices?.[key] ?? (key === 'lojista' ? product.price_lojista : key === 'corporativo' ? product.price_corporativo : null)
  const [search, setSearch] = useState('')
  const [filterCatalogId, setFilterCatalogId] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), 300)
  const [sortKey, setSortKey] = useState<'product_code' | 'description' | 'price_lojista'>('product_code')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  function toggle(key: 'product_code' | 'description' | 'price_lojista') {
    if (key === sortKey) setSortDir((current) => current === 'asc' ? 'desc' : 'asc')
    else {
      setSortKey(key)
      setSortDir('asc')
    }
    onPage(1)
  }
  const { data: productsPage, isLoading } = useProductsPage({
    skip: (page - 1) * ITEMS_PER_PAGE,
    limit: ITEMS_PER_PAGE,
    q: debouncedSearch || undefined,
    catalog_id: filterCatalogId || undefined,
    sort_by: sortKey,
    sort_dir: sortDir,
  })
  const products = productsPage?.items ?? []
  const totalProducts = productsPage?.total ?? 0
  const totalPages = productsPage
    ? Math.max(1, Math.ceil(totalProducts / ITEMS_PER_PAGE))
    : Math.max(1, page)
  const safePage = productsPage
    ? Math.min(Math.max(1, page), totalPages)
    : page
  useEffect(() => {
    if (productsPage && safePage !== page) onPage(safePage)
  }, [productsPage, safePage, page, onPage])
  const { data: allOptionals = [] } = useOptionals()
  const { data: allTypes = [] } = useProductTypes()
  const { data: allCatalogs = [] } = useCatalogs()
  const { data: optCategories = [] } = useOptionalCategories()
  const createM = useCreateProduct()
  const updateM = useUpdateProduct()
  const deleteM = useDeleteProduct()
  const uploadM = useUploadProductPhoto()
  const createTypeM = useCreateProductType()

  // Categorias de opcionais sempre lidas do banco — nunca de uma lista fixa (V-Bloco65-cats)
  const catLabel = (code: string) => optCategories.find(c => c.code === code)?.name ?? code

  const pageItems = products
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)
  const [deleting, setDeleting] = useState<Product | null>(null)
  const [form, setForm] = useState<ProductCreate>(EMPTY_PRODUCT)
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [allOptCats, setAllOptCats] = useState<Set<string>>(new Set())
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [addItemCode, setAddItemCode] = useState('')
  const [addItemQty, setAddItemQty] = useState(1)
  const [compForm, setCompForm] = useState<ProductSetComponentCreate>(EMPTY_COMP)
  const [compActiveCategories, setCompActiveCategories] = useState<string[]>([])
  const [editingCompIndex, setEditingCompIndex] = useState<number | null>(null)
  const [showNewTypeModal, setShowNewTypeModal] = useState(false)
  const [newTypeName, setNewTypeName] = useState('')
  const [newTypeErr, setNewTypeErr] = useState('')
  const [columnWidths, setColumnWidths] = useState<Record<ProductColumnKey, number>>(INITIAL_PRODUCT_COLUMN_WIDTHS)
  const visibleColumnKeys = (Object.keys(columnWidths) as ProductColumnKey[]).filter(column => isEurope || column !== 'price_pvp')
  const tableContainerRef = useRef<HTMLDivElement>(null)

  function resizeColumn(column: ProductColumnKey, requestedWidth: number) {
    const width = Math.max(PRODUCT_COLUMN_MIN_WIDTHS[column], Math.min(requestedWidth, 1600))
    setColumnWidths((current) => ({ ...current, [column]: width }))
  }

  function autoFitColumn(column: ProductColumnKey) {
    const cells = tableContainerRef.current?.querySelectorAll<HTMLElement>(`[data-product-col="${column}"]`)
    if (!cells) return
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    let contentWidth = PRODUCT_COLUMN_MIN_WIDTHS[column]

    cells.forEach((cell) => {
      const text = cell.innerText.replace(/\s+/g, ' ').trim()
      if (!text) return
      if (context) {
        const style = window.getComputedStyle(cell)
        context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
        contentWidth = Math.max(contentWidth, Math.ceil(context.measureText(text).width) + 36)
      } else {
        contentWidth = Math.max(contentWidth, cell.scrollWidth + 8)
      }
    })

    resizeColumn(column, contentWidth)
  }

  function fitColumnsToContainer() {
    const availableWidth = Math.floor(tableContainerRef.current?.clientWidth ?? 0)
    if (availableWidth <= 0) return

    // Distribuição pensada para leitura: descrição e opcionais recebem mais
    // espaço; todo texto continua visível por quebra de linha, sem reticências.
    const ratios: Record<ProductColumnKey, number> = {
      code: 0.11,
      description: isEurope ? 0.19 : 0.22,
      dimensions: 0.16,
      price_lojista: 0.11,
      price_corporativo: 0.11,
      price_pvp: isEurope ? 0.11 : 0,
      optionals: 0.12,
      photo: 0.05,
      actions: 0.04,
    }
    const fitted = {} as Record<ProductColumnKey, number>
    let assigned = 0
    const columns = visibleColumnKeys
    columns.forEach((column, index) => {
      const width = index === columns.length - 1
        ? availableWidth - assigned
        : Math.floor(availableWidth * ratios[column])
      fitted[column] = width
      assigned += width
    })
    setColumnWidths(fitted)
  }

  function restoreColumnWidths() {
    setColumnWidths({ ...INITIAL_PRODUCT_COLUMN_WIDTHS })
  }

  function openCreate() {
    setForm(EMPTY_PRODUCT); setEditing(null)
    setActiveCategories([]); setAllOptCats(new Set()); setPhotoPreview(null); setPendingFile(null)
    setAddItemCode(''); setAddItemQty(1)
    setCompForm(EMPTY_COMP); setCompActiveCategories([]); setEditingCompIndex(null)
    setShowForm(true)
  }
  function openEdit(p: Product) {
    const isConjunto = isConjuntoType(p.type)
    const cats = isConjunto ? [] : Array.from(new Set(p.optionals.map((o) => o.category)))
    const allCats = isConjunto ? new Set<string>() : new Set<string>(
      (p.all_optionals_categories ?? '').split(',').filter(Boolean)
    )
    setActiveCategories(cats); setAllOptCats(allCats)
    setForm({
      product_code: p.product_code,
      description: p.description,
      description_pt_pt: p.description_pt_pt ?? p.description,
      description_en: p.description_en ?? '',
      type: p.type ?? 'Outro',
      catalog_id: p.catalog_id ?? null,
      is_circular: p.is_circular,
      is_set: p.is_set,
      altura: p.altura,
      largura: p.largura,
      profundidade: p.profundidade,
      price: p.price ?? 0,
      price_lojista: p.price_lojista ?? 0,
      price_corporativo: p.price_corporativo ?? 0,
      price_pvp: p.market_prices?.pvp ?? 0,
      observacao: p.observacao ?? null,
      optional_ids: isConjunto ? [] : p.optionals.map((o) => o.id),
      set_items: p.set_items.map(si => ({ product_code: si.product_code, qty: si.qty })),
      components: p.components.map(comp => ({
        description: comp.description,
        is_circular: comp.is_circular,
        altura: comp.altura,
        largura: comp.largura,
        profundidade: comp.profundidade,
        qty: comp.qty,
        optional_ids: comp.optionals.map(o => o.id),
      })),
    })
    setPhotoPreview(p.photo_url ?? null); setPendingFile(null); setEditing(p)
    setAddItemCode(''); setAddItemQty(1)
    setCompForm(EMPTY_COMP); setCompActiveCategories([]); setEditingCompIndex(null)
    setShowForm(true)
  }

  function addSetItem() {
    const code = addItemCode.trim().toUpperCase()
    if (!code) return
    setForm(prev => {
      const existing = (prev.set_items ?? []).findIndex(i => i.product_code === code)
      if (existing >= 0) {
        return {
          ...prev,
          set_items: (prev.set_items ?? []).map((item, i) =>
            i === existing ? { ...item, qty: item.qty + addItemQty } : item
          ),
        }
      }
      return { ...prev, set_items: [...(prev.set_items ?? []), { product_code: code, qty: addItemQty }] }
    })
    setAddItemCode('')
    setAddItemQty(1)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    const isConjunto = isConjuntoType(form.type)
    const activeCatsSet = new Set(activeCategories)
    // Exclude optionals from "all" categories — those are selected freely in the cart
    const filteredOptionalIds = isConjunto ? [] : (form.optional_ids ?? []).filter((optId) => {
      const opt = allOptionals.find((o) => o.id === optId)
      return opt ? (activeCatsSet.has(opt.category) && !allOptCats.has(opt.category)) : false
    })

    const payload = {
      ...form,
      price: form.price_lojista ?? 0, // mantém a coluna legada coerente com o preço lojista
      optional_ids: filteredOptionalIds,
      all_optionals_categories: isConjunto ? null : (allOptCats.size > 0 ? Array.from(allOptCats).join(',') : null),
      set_items: isConjunto ? [] : (form.set_items ?? []),
      components: isConjunto ? (form.components ?? []) : [],
      profundidade: form.is_circular ? 0 : form.profundidade,
    }
    try {
      if (editing) {
        const updatePayload = isEurope
          ? {
              price_lojista: form.price_lojista ?? 0,
              price_corporativo: form.price_corporativo ?? 0,
              price_pvp: form.price_pvp ?? 0,
              description_pt_pt: form.description_pt_pt?.trim() || undefined,
              description_en: form.description_en?.trim() || undefined,
            }
          : (canClassifyBr ? payload : { ...payload, type: undefined })
        const updated = await updateM.mutateAsync({ id: editing.id, data: updatePayload })
        if (!isEurope && pendingFile) await uploadM.mutateAsync({ id: updated.id, file: pendingFile })
      } else {
        const created = await createM.mutateAsync(payload)
        if (pendingFile) await uploadM.mutateAsync({ id: created.id, file: pendingFile })
      }
      setShowForm(false)
    } catch (err) {
      // Não fecha o modal em falha; mostra o erro ao usuário (V-M5).
      setFormError(parseApiError(err))
    }
  }

  return (
    <div className="min-w-0 max-w-full">
      {!isEurope && <BatchPhotoUpload color={color} />}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <span className="text-sm text-muted whitespace-nowrap">{totalProducts} {tx(totalProducts === 1 ? 'produto' : 'produtos')}</span>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
            <input aria-label={tx('Buscar produtos por código ou descrição')} className="input pl-9" placeholder={tx('Buscar por código ou descrição...')} value={search} onChange={(e) => { setSearch(e.target.value); onPage(1) }} />
          </div>
          <select
            className="input w-full sm:w-44 flex-shrink-0"
            value={filterCatalogId}
            onChange={(e) => { setFilterCatalogId(e.target.value); onPage(1) }}
          >
            <option value="">{tx('Todos os Catálogos')}</option>
            {allCatalogs.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          {(isEurope || canClassifyBr) && (
            <button className="btn-primary flex items-center gap-2 flex-shrink-0" style={{ backgroundColor: color, touchAction: 'manipulation' } as React.CSSProperties} onClick={openCreate}>
              <Plus className="w-4 h-4" /> <span className="hidden sm:inline">{tx('Novo ')}</span>{tx('Produto')}
            </button>
          )}
        </div>
      </div>
      {isEurope && (
        <p className="mb-4 rounded-lg bg-bg-2 px-3 py-2 text-xs text-ink-2">
          {tx('Em Portugal, pode cadastrar produtos exclusivos deste mercado, editar os nomes em português e inglês e os preços em EUR; excluir remove o produto apenas deste catálogo.')}
        </p>
      )}

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">{tx('Carregando...')}</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="lg:hidden flex flex-col gap-3">
            {pageItems.map((p) => (
              <div key={p.id} className="bg-surface-quiet border border-line rounded-xl p-3.5 flex gap-3">
                {p.photo_url
                  ? <img src={p.photo_url} alt="" className="w-14 h-14 object-cover rounded-lg border border-line flex-shrink-0" />
                  : <div className="w-14 h-14 bg-bg-2 rounded-lg flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-faint" /></div>
                }
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <span className="text-[11px] font-mono font-semibold" style={{ color }}>{p.product_code}</span>
                      <p className="text-sm font-medium text-ink leading-snug break-words">{p.description}</p>
                    </div>
                    <div className="flex gap-0 flex-shrink-0">
                      <button onClick={() => openEdit(p)} aria-label={tx('Editar')} className="w-11 h-11 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleting(p)} aria-label={tx('Excluir')} className="w-11 h-11 flex items-center justify-center text-muted active:text-danger transition-colors" style={{ touchAction: 'manipulation' }}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-muted">
                      {isConjuntoType(p.type) ? '' : formatDimensions(p, isEurope ? 'EU' : 'BR', locale)}
                    </span>
                    <span className="space-y-0.5 text-right">
                      <span className="block text-[10px] text-muted">Lojista <strong className="text-sm text-ink">{money(marketPrice(p, 'lojista'))}</strong></span>
                      <span className="block text-[10px] text-muted">Corporativo <strong className="text-ink-2">{money(marketPrice(p, 'corporativo'))}</strong></span>
                      {isEurope && <span className="block text-[10px] text-muted">PVP <strong className="text-gold">{money(marketPrice(p, 'pvp'))}</strong></span>}
                    </span>
                  </div>
                  {(p.optionals.length > 0 || p.all_optionals_categories) && (
                    <p className="text-[10px] text-muted mt-0.5 truncate">{getProductOptionalsLabel(p, catLabel, ' · ', tx('Todos'))}</p>
                  )}
                </div>
              </div>
            ))}
            {pageItems.length === 0 && <p className="text-center text-muted text-sm py-8">{tx(search ? 'Nenhum produto encontrado com este filtro.' : 'Nenhum produto cadastrado.')}</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden lg:flex items-center justify-between gap-4 mb-2">
            <p className="text-[11px] text-muted">
              {tx('Arraste os divisores para redimensionar ou dê duplo clique para autoajustar.')}
            </p>
            <div className="flex items-center rounded-lg border border-line bg-surface-2 p-0.5 flex-shrink-0">
              <button
                type="button"
                onClick={fitColumnsToContainer}
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-ink-2 hover:bg-white hover:text-ink transition-colors"
                title={tx('Distribuir as colunas dentro da largura disponível')}
              >
                <Columns3 className="w-3.5 h-3.5" />
                {tx('Ajustar à tela')}
              </button>
              <span className="h-4 w-px bg-line" aria-hidden="true" />
              <button
                type="button"
                onClick={restoreColumnWidths}
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-muted hover:bg-white hover:text-ink transition-colors"
                title={tx('Voltar às larguras padrão')}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                {tx('Restaurar')}
              </button>
            </div>
          </div>
          <div ref={tableContainerRef} className="hidden lg:block w-full max-w-full min-w-0 overflow-x-auto rounded-xl border border-line overscroll-x-contain">
            <table
              className="table-fixed text-sm"
              style={{ width: visibleColumnKeys.reduce((total, column) => total + columnWidths[column], 0) }}
            >
              <colgroup>
                {visibleColumnKeys.map((column) => (
                  <col key={column} style={{ width: columnWidths[column] }} />
                ))}
              </colgroup>
              <thead style={{ backgroundColor: `${tint(color, 7)}` }}>
                <tr>
                  <ResizableProductTh label={tx('Código')} column="code" width={columnWidths.code} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color}
                    sort={{ active: sortKey === 'product_code', dir: sortDir, onClick: () => toggle('product_code') }} />
                  <ResizableProductTh label={tx('Descrição')} column="description" width={columnWidths.description} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color}
                    sort={{ active: sortKey === 'description', dir: sortDir, onClick: () => toggle('description') }} />
                  <ResizableProductTh label={tx('Dimensões')} column="dimensions" width={columnWidths.dimensions} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />
                  <ResizableProductTh label="Lojista" column="price_lojista" width={columnWidths.price_lojista} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color}
                    sort={{ active: sortKey === 'price_lojista', dir: sortDir, onClick: () => toggle('price_lojista') }} />
                  <ResizableProductTh label="Corporativo" column="price_corporativo" width={columnWidths.price_corporativo} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />
                  {isEurope && <ResizableProductTh label="PVP" column="price_pvp" width={columnWidths.price_pvp} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />}
                  <ResizableProductTh label={tx('Opcionais')} column="optionals" width={columnWidths.optionals} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />
                  <ResizableProductTh label={tx('Foto')} column="photo" width={columnWidths.photo} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />
                  <ResizableProductTh label="" column="actions" width={columnWidths.actions} onResize={resizeColumn} onAutoFit={autoFitColumn} color={color} />
                </tr>
              </thead>
              <tbody>
                {pageItems.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td data-product-col="code" className="px-4 py-3 font-mono text-sm font-medium border-r border-line whitespace-normal break-words align-top" style={{ color }}>{p.product_code}</td>
                    <td data-product-col="description" className="px-4 py-3 text-ink border-r border-line whitespace-normal break-words align-top" title={p.description}>{p.description}</td>
                    <td data-product-col="dimensions" className="px-4 py-3 text-ink-2 text-xs border-r border-line whitespace-normal break-words align-top">
                      {isConjuntoType(p.type) ? '—' : formatDimensions(p, isEurope ? 'EU' : 'BR', locale)}
                    </td>
                    <td data-product-col="price_lojista" className="px-4 py-3 text-sm font-medium text-ink border-r border-line whitespace-normal align-top">{money(marketPrice(p, 'lojista'))}</td>
                    <td data-product-col="price_corporativo" className="px-4 py-3 text-sm text-ink-2 border-r border-line whitespace-normal align-top">{money(marketPrice(p, 'corporativo'))}</td>
                    {isEurope && <td data-product-col="price_pvp" className="px-4 py-3 text-sm font-semibold text-gold border-r border-line whitespace-normal align-top">{money(marketPrice(p, 'pvp'))}</td>}
                    <td data-product-col="optionals" className="px-4 py-3 text-muted-2 text-xs border-r border-line whitespace-normal break-words align-top">
                      {p.optionals.length > 0 || p.all_optionals_categories
                        ? getProductOptionalsLabel(p, catLabel, ', ', tx('Todos'))
                        : '—'}
                    </td>
                    <td data-product-col="photo" className="px-2 py-3 border-r border-line align-top">
                      {p.photo_url
                        ? <img src={p.photo_url} alt="" className="w-10 h-10 object-cover rounded-lg border border-line" />
                        : <ImageIcon className="w-6 h-6 text-faint" />}
                    </td>
                    <td data-product-col="actions" className="px-2 py-3 align-top">
                      <div className="flex gap-2">
                        <button onClick={() => openEdit(p)} aria-label={tx('Editar')} className="btn-icon"><Pencil className="w-4 h-4" /></button>
                        <button onClick={() => setDeleting(p)} aria-label={tx('Excluir')} className="btn-icon hover:text-danger"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {pageItems.length === 0 && (
                  <tr><td colSpan={visibleColumnKeys.length} className="px-4 py-10 text-center text-muted">{tx(search ? 'Nenhum produto encontrado com este filtro.' : 'Nenhum produto cadastrado.')}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </>
      )}

      {showNewTypeModal && (
        <Modal title={tx('Novo Tipo de Móvel')} onClose={() => { setShowNewTypeModal(false); setNewTypeName(''); setNewTypeErr('') }} accentColor={color}>
          <form onSubmit={async (e) => {
            e.preventDefault(); setNewTypeErr('')
            try {
              const created = await createTypeM.mutateAsync({ name: newTypeName.trim() })
              setForm(prev => ({ ...prev, type: created.name }))
              setShowNewTypeModal(false); setNewTypeName('')
            } catch {
              setNewTypeErr(tx('Tipo já existe ou nome inválido.'))
            }
          }} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Nome do Novo Tipo *')}</span>
              <input className="input" value={newTypeName} onChange={(e) => setNewTypeName(e.target.value)} required autoFocus />
            </label>
            {newTypeErr && <p className="text-xs text-danger">{newTypeErr}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={createTypeM.isPending} className="btn-primary flex-1">
                {tx(createTypeM.isPending ? 'Salvando...' : 'Criar e Selecionar')}
              </button>
              <button type="button" onClick={() => { setShowNewTypeModal(false); setNewTypeName('') }} className="btn-secondary px-4">{tx('Cancelar')}</button>
            </div>
          </form>
        </Modal>
      )}

      {showForm && isEurope && editing && (
        <Modal title={tx('Editar Produto em Portugal')} onClose={() => { setFormError(null); setShowForm(false) }} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-5">
            {formError && (
              <div role="alert" className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-xs leading-snug text-danger">
                {formError}
              </div>
            )}
            <div className="rounded-xl bg-bg-2 px-4 py-3">
              <span className="block font-mono text-xs font-semibold" style={{ color }}>{editing.product_code}</span>
              <p className="mt-2 text-xs leading-relaxed text-ink-2">
                {tx('Os nomes e os preços abaixo pertencem apenas a Portugal; o catálogo do Brasil não é alterado.')}
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">{tx('Nome em português (Portugal)')}</span>
                <input className="input" maxLength={20000} value={form.description_pt_pt ?? ''} onChange={(event) => setForm({ ...form, description_pt_pt: event.target.value })} required />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">{tx('Nome em inglês')}</span>
                <input className="input" maxLength={20000} lang="en-GB" value={form.description_en ?? ''} onChange={(event) => setForm({ ...form, description_en: event.target.value })} required />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">Lojista (€)</span>
                <NumberField className="input" min="0" step="0.01" value={form.price_lojista} onValueChange={(value) => setForm({ ...form, price_lojista: value })} required />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">Corporativo (€)</span>
                <NumberField className="input" min="0" step="0.01" value={form.price_corporativo} onValueChange={(value) => setForm({ ...form, price_corporativo: value })} required />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted">PVP (€)</span>
                <NumberField className="input" min="0" step="0.01" value={form.price_pvp} onValueChange={(value) => setForm({ ...form, price_pvp: value })} required />
              </label>
            </div>
            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>{tx('Cancelar')}</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }} disabled={updateM.isPending}>
                {tx(updateM.isPending ? 'A guardar…' : 'Guardar nomes e preços')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {showForm && (!isEurope || !editing) && (
        <Modal title={tx(editing ? 'Editar Produto' : (isEurope ? 'Novo Produto em Portugal' : 'Novo Produto'))} onClose={() => { setFormError(null); setShowForm(false) }} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-4">
            {formError && (
              <div className="flex items-start gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2">
                <span className="text-xs text-danger leading-snug">{formError}</span>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">{tx('Código *')}</span>
                <input className="input" value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">{tx('Preço Lojista ({currency}) *', { currency: isEurope ? '€' : 'R$' })}</span>
                <NumberField className="input" min="0" step="0.01" value={form.price_lojista} onValueChange={(v) => setForm({ ...form, price_lojista: v })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">{tx('Preço Corporativo ({currency}) *', { currency: isEurope ? '€' : 'R$' })}</span>
                <NumberField className="input" min="0" step="0.01" value={form.price_corporativo} onValueChange={(v) => setForm({ ...form, price_corporativo: v })} required />
              </label>
              {isEurope && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">{tx('Preço PVP (€) *')}</span>
                  <NumberField className="input" min="0" step="0.01" value={form.price_pvp} onValueChange={(v) => setForm({ ...form, price_pvp: v })} required />
                </label>
              )}
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-muted">{tx(isEurope ? 'Nome em português (Portugal)' : 'Descrição')} *</span>
                <input
                  className="input"
                  value={isEurope ? (form.description_pt_pt ?? '') : form.description}
                  onChange={(e) => setForm({
                    ...form,
                    description: e.target.value,
                    ...(isEurope ? { description_pt_pt: e.target.value } : {}),
                  })}
                  required
                />
              </label>
              {isEurope && (
                <label className="flex flex-col gap-1 col-span-2">
                  <span className="text-xs text-muted">{tx('Nome em inglês *')}</span>
                  <input className="input" lang="en-GB" value={form.description_en ?? ''} onChange={(e) => setForm({ ...form, description_en: e.target.value })} required />
                </label>
              )}
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-muted">{tx('Observação')}</span>
                <textarea
                  className="input resize-none"
                  rows={2}
                  placeholder={tx('Informações técnicas, restrições, montagem...')}
                  value={form.observacao ?? ''}
                  onChange={(e) => setForm({ ...form, observacao: e.target.value || null })}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">{tx('Tipo')}</span>
                <select className="input" value={form.type ?? 'Outro'} disabled={!isEurope && !canClassifyBr} onChange={(e) => {
                  if (e.target.value === '__new__') { setShowNewTypeModal(true) }
                  else setForm({ ...form, type: e.target.value })
                }}>
                  {/* Tipo é opcional: "Outro" é o "sem tipo" aceito em qualquer mercado. */}
                  <option value="Outro">{tx('Sem tipo')}</option>
                  {(allTypes.length > 0 ? allTypes.map(t => t.name) : ['Poltrona','Sofá','Cadeira','Mesa','Banqueta','Chaise','Aparador'])
                    .filter(t => t !== 'Outro')
                    .map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  {(isEurope || canClassifyBr) && <option value="__new__">{tx('+ Adicionar Novo...')}</option>}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">{tx('Catálogo')}</span>
                <select
                  className="input"
                  value={form.catalog_id ?? ''}
                  onChange={(e) => setForm({ ...form, catalog_id: e.target.value || null })}
                >
                  <option value="">{tx('Sem catálogo')}</option>
                  {allCatalogs.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
            </div>

            {!isConjuntoType(form.type) && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_circular}
                  onChange={(e) => setForm({ ...form, is_circular: e.target.checked, profundidade: e.target.checked ? 0 : form.profundidade })}
                  style={{ accentColor: color }}
                  className="w-4 h-4"
                />
                <span className="text-sm text-ink-2">{tx('Medida Redonda (Ø — circular)')}</span>
              </label>
            )}


            {!isConjuntoType(form.type) && (
              <div className="grid grid-cols-3 gap-3">
                {form.is_circular ? (
                  <>
                    <label className="flex flex-col gap-1 col-span-2">
                      <span className="text-xs text-muted">{tx('Diâmetro Ø (m) *')}</span>
                      <NumberField className="input" min="0" step="0.01" value={form.largura}
                        onValueChange={(v) => setForm({ ...form, largura: v })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">{tx('Altura A (m) *')}</span>
                      <NumberField className="input" min="0" step="0.01" value={form.altura}
                        onValueChange={(v) => setForm({ ...form, altura: v })} required />
                    </label>
                  </>
                ) : (
                  <>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">{tx('Largura L (m) *')}</span>
                      <NumberField className="input" min="0" step="0.01" value={form.largura}
                        onValueChange={(v) => setForm({ ...form, largura: v })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">{tx('Prof. P (m) *')}</span>
                      <NumberField className="input" min="0" step="0.01" value={form.profundidade}
                        onValueChange={(v) => setForm({ ...form, profundidade: v })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">{tx('Altura A (m) *')}</span>
                      <NumberField className="input" min="0" step="0.01" value={form.altura}
                        onValueChange={(v) => setForm({ ...form, altura: v })} required />
                    </label>
                  </>
                )}
              </div>
            )}

            {isConjuntoType(form.type) ? (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">{tx('Componentes do Conjunto')}</span>
                {(form.components ?? []).length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {(form.components ?? []).map((comp, idx) => (
                      <div key={idx} className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-line bg-surface-quiet">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-ink leading-snug">{comp.description}</p>
                          <p className="text-[10px] text-muted mt-0.5">
                            {comp.is_circular
                              ? `Ø ${Number(comp.largura).toFixed(2).replace('.', ',')} × A ${Number(comp.altura).toFixed(2).replace('.', ',')} m`
                              : `L ${Number(comp.largura).toFixed(2).replace('.', ',')} × P ${Number(comp.profundidade).toFixed(2).replace('.', ',')} × A ${Number(comp.altura).toFixed(2).replace('.', ',')} m`
                            } — qty: {comp.qty}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            type="button"
                            onClick={() => {
                              setCompForm(comp)
                              setCompActiveCategories(Array.from(new Set(
                                comp.optional_ids
                                  .map(id => allOptionals.find(o => o.id === id)?.category)
                                  .filter((c): c is string => !!c)
                              )))
                              setEditingCompIndex(idx)
                            }}
                            className="btn-icon -mt-1.5"
                            style={{ color: editingCompIndex === idx ? color : undefined }}
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setForm(prev => ({ ...prev, components: (prev.components ?? []).filter((_, i) => i !== idx) }))}
                            className="btn-icon hover:text-danger -mt-1.5"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="border border-line-warm rounded-xl p-4 bg-surface-note space-y-3">
                  <span className="text-xs font-semibold text-ink-2">{tx(editingCompIndex !== null ? 'Editar Componente' : 'Novo Componente')}</span>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">{tx('Descrição *')}</span>
                    <input className="input" placeholder={tx('ex: Sofá 3 lugares, Poltrona, Mesa...')} value={compForm.description}
                      onChange={e => setCompForm(f => ({ ...f, description: e.target.value }))} />
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={compForm.is_circular}
                      onChange={e => setCompForm(f => ({ ...f, is_circular: e.target.checked, profundidade: e.target.checked ? 0 : f.profundidade }))}
                      style={{ accentColor: color }} className="w-4 h-4" />
                    <span className="text-sm text-ink-2">{tx('Medida Redonda (Ø)')}</span>
                  </label>
                  {compForm.is_circular ? (
                    <div className="grid grid-cols-3 gap-3">
                      <label className="flex flex-col gap-1 col-span-2">
                        <span className="text-xs text-muted">{tx('Diâmetro Ø (m)')}</span>
                        <NumberField className="input" min="0" step="0.01" value={compForm.largura}
                          onValueChange={v => setCompForm(f => ({ ...f, largura: v }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">{tx('Altura A (m)')}</span>
                        <NumberField className="input" min="0" step="0.01" value={compForm.altura}
                          onValueChange={v => setCompForm(f => ({ ...f, altura: v }))} />
                      </label>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-3">
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">{tx('L (m)')}</span>
                        <NumberField className="input" min="0" step="0.01" value={compForm.largura}
                          onValueChange={v => setCompForm(f => ({ ...f, largura: v }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">{tx('P (m)')}</span>
                        <NumberField className="input" min="0" step="0.01" value={compForm.profundidade}
                          onValueChange={v => setCompForm(f => ({ ...f, profundidade: v }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">{tx('A (m)')}</span>
                        <NumberField className="input" min="0" step="0.01" value={compForm.altura}
                          onValueChange={v => setCompForm(f => ({ ...f, altura: v }))} />
                      </label>
                    </div>
                  )}
                  <label className="flex flex-col gap-1 w-24">
                    <span className="text-xs text-muted">{tx('Quantidade')}</span>
                    <input className="input text-center" type="number" min="1" value={compForm.qty}
                      onChange={e => setCompForm(f => ({ ...f, qty: Math.max(1, Number(e.target.value)) }))} />
                  </label>

                  <div>
                    <span className="text-xs text-muted block mb-2">{tx('Opcionais do Componente')}</span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
                      {optCategories.map(({ code: value, name: label }) => {
                        const isActive = compActiveCategories.includes(value)
                        return (
                          <label key={value} className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-line hover:bg-bg cursor-pointer transition-colors">
                            <input type="checkbox" checked={isActive} style={{ accentColor: color }}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setCompActiveCategories(prev => [...prev, value])
                                } else {
                                  setCompActiveCategories(prev => prev.filter(c => c !== value))
                                  const catIds = allOptionals.filter(o => o.category === value).map(o => o.id)
                                  setCompForm(f => ({ ...f, optional_ids: f.optional_ids.filter(id => !catIds.includes(id)) }))
                                }
                              }}
                              className="w-3.5 h-3.5" />
                            <span className="text-xs text-ink-2 select-none">{label}</span>
                          </label>
                        )
                      })}
                      {optCategories.length === 0 && (
                        <p className="col-span-full text-xs text-muted">{tx('Nenhum grupo de opcionais cadastrado. Crie grupos na aba Opcionais.')}</p>
                      )}
                    </div>
                    {compActiveCategories.length > 0 && (
                      <div className="space-y-2.5">
                        {compActiveCategories.map((cat) => (
                          <div key={cat} className="border border-line rounded-lg p-2.5 bg-white">
                            <span className="text-[11px] font-semibold block mb-1.5" style={{ color }}>{catLabel(cat).toUpperCase()}</span>
                            <div className="flex flex-wrap gap-1.5">
                              {allOptionals.filter(o => o.category === cat).map(opt => {
                                const isSel = compForm.optional_ids.includes(opt.id)
                                return (
                                  <button type="button" key={opt.id}
                                    onClick={() => setCompForm(f => {
                                      const ids = f.optional_ids
                                      return { ...f, optional_ids: ids.includes(opt.id) ? ids.filter(id => id !== opt.id) : [...ids, opt.id] }
                                    })}
                                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-[background-color,color,border-color]"
                                    style={isSel ? { backgroundColor: `${tint(color, 13)}`, borderColor: color, color } : { backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-line)', color: 'var(--color-ink-3)' }}
                                  >
                                    {opt.photo_url && <img src={opt.photo_url} alt={opt.color_name} className="w-3.5 h-3.5 rounded object-cover flex-shrink-0" />}
                                    <span>{opt.color_name}</span>
                                  </button>
                                )
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button type="button"
                      onClick={() => {
                        if (!compForm.description.trim()) return
                        setForm(prev => {
                          const components = [...(prev.components ?? [])]
                          if (editingCompIndex !== null) components[editingCompIndex] = compForm
                          else components.push(compForm)
                          return { ...prev, components }
                        })
                        setCompForm(EMPTY_COMP)
                        setCompActiveCategories([])
                        setEditingCompIndex(null)
                      }}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors"
                      style={{ backgroundColor: color }}
                    >
                      <Plus className="w-4 h-4" />
                      {tx(editingCompIndex !== null ? 'Salvar Componente' : 'Adicionar Componente')}
                    </button>
                    {editingCompIndex !== null && (
                      <button type="button"
                        onClick={() => {
                          setCompForm(EMPTY_COMP)
                          setCompActiveCategories([])
                          setEditingCompIndex(null)
                        }}
                        className="px-4 py-2 rounded-lg text-sm font-medium border border-line text-ink-3 hover:bg-bg transition-colors"
                      >
                        {tx('Cancelar')}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ) : form.is_set ? (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">{tx('Componentes do Conjunto')}</span>
                {(form.set_items ?? []).length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {(form.set_items ?? []).map((item, idx) => (
                      <div key={idx} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-line bg-surface-quiet">
                        <span className="font-mono text-xs font-semibold text-gold flex-1">{item.product_code}</span>
                        <span className="text-xs text-muted">×{item.qty}</span>
                        <button
                          type="button"
                          onClick={() => setForm(prev => ({
                            ...prev,
                            set_items: (prev.set_items ?? []).filter((_, i) => i !== idx),
                          }))}
                          className="text-muted hover:text-danger transition-colors ml-1"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    className="input flex-1 font-mono text-sm"
                    placeholder={tx('Código do produto')}
                    value={addItemCode}
                    onChange={(e) => setAddItemCode(e.target.value.toUpperCase())}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addSetItem() } }}
                  />
                  <input
                    className="input w-16 text-center"
                    type="number"
                    min="1"
                    value={addItemQty}
                    onChange={(e) => setAddItemQty(Math.max(1, Number(e.target.value)))}
                  />
                  <button
                    type="button"
                    className="px-3 rounded-lg text-white text-sm font-medium transition-colors flex-shrink-0 flex items-center gap-1"
                    style={{ backgroundColor: color }}
                    onClick={addSetItem}
                  >
                    <Plus className="w-4 h-4" />
                    <span className="hidden sm:inline">Add</span>
                  </button>
                </div>
                <p className="text-[10px] text-muted mt-1.5">{tx('Código deve existir no catálogo. Conjuntos não podem conter outros conjuntos.')}</p>
              </div>
            ) : (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">{tx('Categorias de Opcionais Disponíveis')}</span>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                  {optCategories.map(({ code: value, name: label }) => {
                    const isActive = activeCategories.includes(value)
                    return (
                      <label key={value} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-line hover:bg-bg cursor-pointer transition-colors">
                        <input
                          type="checkbox"
                          checked={isActive}
                          style={{ accentColor: color }}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setActiveCategories([...activeCategories, value])
                            } else {
                              setActiveCategories(activeCategories.filter(c => c !== value))
                              const catOptionalIds = allOptionals.filter(o => o.category === value).map(o => o.id)
                              setForm(prev => ({
                                ...prev,
                                optional_ids: (prev.optional_ids ?? []).filter(id => !catOptionalIds.includes(id))
                              }))
                            }
                          }}
                          className="w-4 h-4"
                        />
                        <span className="text-xs text-ink-2 select-none">{label}</span>
                      </label>
                    )
                  })}
                  {optCategories.length === 0 && (
                    <p className="col-span-full text-xs text-muted">{tx('Nenhum grupo de opcionais cadastrado. Crie grupos na aba Opcionais.')}</p>
                  )}
                </div>

                {activeCategories.length > 0 && (
                  <div className="space-y-3">
                    <span className="text-xs text-muted block font-medium">{tx('Cores e Permissões por Categoria')}</span>
                    {activeCategories.map((catValue) => {
                      const catValueLabel = catLabel(catValue)
                      const catItems = allOptionals.filter(o => o.category === catValue)
                      const isAllowed = allOptCats.has(catValue)
                      const selectedIds = (form.optional_ids ?? []).filter(id => catItems.some(o => o.id === id))
                      return (
                        <div key={catValue} className="border border-line rounded-xl p-3.5 space-y-2.5 bg-white shadow-sm">
                          <div className="flex items-center justify-between pb-1 border-b border-line-soft">
                            <span className="text-xs font-semibold" style={{ color }}>{catValueLabel.toUpperCase()}</span>
                            <label className="flex items-center gap-1.5 cursor-pointer select-none">
                              <input
                                type="checkbox"
                                checked={isAllowed}
                                style={{ accentColor: color }}
                                onChange={(e) => {
                                  setAllOptCats(prev => {
                                    const next = new Set(prev)
                                    if (e.target.checked) {
                                      next.add(catValue)
                                      // Clear individual selections for this category
                                      const catIds = catItems.map(o => o.id)
                                      setForm(f => ({ ...f, optional_ids: (f.optional_ids ?? []).filter(id => !catIds.includes(id)) }))
                                    } else {
                                      next.delete(catValue)
                                    }
                                    return next
                                  })
                                }}
                                className="w-3.5 h-3.5"
                              />
                              <span className="text-[11px] text-ink-3">{tx('Permitir todos')}</span>
                            </label>
                          </div>
                          {isAllowed ? (
                            <p className="text-[11px] text-muted italic">
                              {tx('Todos os opcionais desta categoria estarão disponíveis no carrinho.')}
                            </p>
                          ) : (
                            <div>
                              {catItems.length === 0 ? (
                                <span className="text-xs text-muted italic">{tx('Nenhuma cor cadastrada nesta categoria.')}</span>
                              ) : (
                                <select
                                  multiple
                                  size={Math.min(catItems.length, 5)}
                                  value={selectedIds}
                                  onChange={(e) => {
                                    const chosen = Array.from(e.target.selectedOptions).map(o => o.value)
                                    const otherIds = (form.optional_ids ?? []).filter(id => !catItems.some(o => o.id === id))
                                    setForm(prev => ({ ...prev, optional_ids: [...otherIds, ...chosen] }))
                                  }}
                                  className="w-full border border-line rounded-lg text-xs text-ink bg-white focus:outline-none focus:ring-2 focus:ring-gold/20 focus:border-gold/60 px-2 py-1"
                                >
                                  {catItems.map(opt => (
                                    <option key={opt.id} value={opt.id}>{opt.color_name}</option>
                                  ))}
                                </select>
                              )}
                              <p className="text-[10px] text-muted mt-1">{tx('Ctrl+clique para selecionar múltiplas cores.')}</p>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            <div>
              <span className="text-xs text-muted block mb-1">{tx('Foto')}</span>
              <div
                className="border-2 border-dashed border-line rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
              >
                {photoPreview ? <img src={photoPreview} alt="" className="w-24 h-24 object-cover rounded-lg" /> : <Upload className="w-8 h-8 text-faint" />}
                <span className="text-xs text-muted">{tx(photoPreview ? 'Clique para trocar' : 'JPG, PNG, WEBP — máx. 5MB')}</span>
              </div>
              <input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.webp" className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]; if (!file) return
                  setPendingFile(file); setPhotoPreview(URL.createObjectURL(file))
                }} />
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>{tx('Cancelar')}</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }}
                disabled={createM.isPending || updateM.isPending || uploadM.isPending}>
                {tx(editing ? 'Salvar' : 'Criar')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete name={isEurope ? tx('{name} do catálogo Portugal', { name: deleting.description }) : deleting.description}
          onConfirm={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)} />
      )}
    </div>
  )
}

// ── CLIENTES / REPRESENTANTES ─────────────────────────────────────────────────

const emptyAddress = (market: 'BR' | 'EU'): ClientCreate => ({ name: '', phone: '', email: '', cpf_cnpj: '', tax_id: '', country: market === 'BR' ? 'BR' : 'PT', region: '', cep: '', numero: '', address: '', city: '', state: market === 'BR' ? '' : '--', price_profile: 'lojista' })

function PeopleTab<T extends Client | Representative>({
  label, entityType, onCreate, onUpdate, onDelete, isPending, color, page, onPage,
}: {
  label: string; entityType: 'client' | 'rep'
  onCreate: (data: ClientCreate) => Promise<void>; onUpdate: (id: string, data: Partial<ClientCreate>) => Promise<void>
  onDelete: (id: string) => Promise<void>; isPending: boolean; color: string
  page: number; onPage: (p: number) => void
}) {
  const { user: authUser } = useAuth()
  const tx = useCadastroText()
  const isAdmin = authUser?.role === 'admin'
  const activeMarket = authUser?.active_market ?? 'BR'
  const isRep = authUser?.role === 'representante'
  const canEditDiscount = authUser?.role === 'admin' || authUser?.role === 'cadastros' || authUser?.role === 'produtos'
  const defaultMaxDiscount = entityType === 'client' ? 0 : 30
  const canViewCreator = !isRep && authUser?.role !== 'cliente'

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), 300)
  const [sortKey, setSortKey] = useState<'name' | 'email' | 'phone' | 'city' | 'state' | 'max_discount'>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  function toggle(key: string) {
    const nextKey = key as typeof sortKey
    if (nextKey === sortKey) setSortDir((current) => current === 'asc' ? 'desc' : 'asc')
    else {
      setSortKey(nextKey)
      setSortDir('asc')
    }
    onPage(1)
  }
  const pageParams = {
    skip: (page - 1) * ITEMS_PER_PAGE,
    limit: ITEMS_PER_PAGE,
    q: debouncedSearch || undefined,
    sort_by: sortKey,
    sort_dir: sortDir,
  }
  const clientQuery = useClientsPage(pageParams, entityType === 'client')
  const repQuery = useRepresentativesPage(pageParams, entityType === 'rep')
  const activeQuery = entityType === 'client' ? clientQuery : repQuery
  const pageItems = (activeQuery.data?.items ?? []) as T[]
  const totalItems = activeQuery.data?.total ?? 0
  const totalPages = activeQuery.data
    ? Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE))
    : Math.max(1, page)
  const safePage = activeQuery.data
    ? Math.min(Math.max(1, page), totalPages)
    : page
  const isLoading = activeQuery.isLoading
  useEffect(() => {
    if (activeQuery.data && safePage !== page) onPage(safePage)
  }, [activeQuery.data, safePage, page, onPage])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<T | null>(null)
  const [deleting, setDeleting] = useState<T | null>(null)
  const [viewing, setViewing] = useState<T | null>(null)
  const [createdUser, setCreatedUser] = useState<UserCreateResponse | null>(null)
  const [createUserError, setCreateUserError] = useState<string | null>(null)
  const [confirmedEmail, setConfirmedEmail] = useState('')
  const [verificationMethod, setVerificationMethod] = useState<ClientVerificationMethod>('phone_callback')
  const [inviteSent, setInviteSent] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<ClientCreate>(() => emptyAddress(activeMarket))

  const createFromClient = useCreateUserFromClient()
  const createFromRep = useCreateUserFromRep()
  const issueInvitation = useIssueClientInvitation()

  function openCreate() { setForm(emptyAddress(activeMarket)); setEditing(null); setFormError(null); setShowForm(true) }
  function openEdit(item: T) {
    setForm({ name: item.name, phone: item.phone, email: item.email ?? '', cpf_cnpj: formatCpfCnpj(item.cpf_cnpj ?? ''), tax_id: item.tax_id, country: item.country, region: item.region, cep: item.cep, numero: item.numero ?? '', address: item.address, city: item.city, state: item.state, price_profile: (item as Client).price_profile ?? 'lojista', max_discount: item.max_discount })
    setEditing(item); setFormError(null); setShowForm(true)
  }
  function openView(item: T) {
    setViewing(item); setCreatedUser(null); setCreateUserError(null)
    setConfirmedEmail(''); setInviteSent(false); setInviteError(null)
  }
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    // Normaliza campos antes de enviar — evita 422 por espaços ou UF vazia/minúscula
    const cleaned = normalizePersonPayload(form)
    if (activeMarket === 'BR' && cleaned.state.length !== 2) {
      setFormError('Selecione o estado (UF).')
      return
    }
    setSubmitting(true)
    try {
      if (editing) await onUpdate(editing.id, cleaned); else await onCreate(cleaned)
      setShowForm(false)
    } catch (err) {
      setFormError(parseApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCreateUser() {
    if (!viewing) return
    setCreateUserError(null)
    try {
      let user: UserCreateResponse
      if (entityType === 'client') {
        user = await createFromClient.mutateAsync(viewing.id)
      } else {
        user = await createFromRep.mutateAsync(viewing.id)
      }
      setCreatedUser(user)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCreateUserError(detail ?? tx('Erro ao criar usuário.'))
    }
  }

  async function handleIssueInvitation() {
    if (!viewing || entityType !== 'client') return
    setInviteError(null)
    try {
      await issueInvitation.mutateAsync({
        clientId: viewing.id,
        confirmedEmail: confirmedEmail.trim(),
        verificationMethod,
      })
      setInviteSent(true)
      setConfirmedEmail('')
    } catch (err) {
      setInviteError(parseApiError(err))
    }
  }

  const thProps = { sortKey: String(sortKey), sortDir, onSort: toggle, color }
  const createUserPending = entityType === 'client' ? createFromClient.isPending : createFromRep.isPending

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <span className="text-sm text-muted whitespace-nowrap">{tx('{count} {label} cadastrados', { count: totalItems, label: tx(label).toLowerCase() })}</span>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
            <input className="input pl-9" placeholder={tx('Buscar por nome...')} value={search} onChange={(e) => { setSearch(e.target.value); onPage(1) }} />
          </div>
          <button className="btn-primary flex items-center gap-2 flex-shrink-0" style={{ backgroundColor: color }} onClick={openCreate}>
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">{tx('Novo ')}</span>{tx(label).slice(0, -1)}
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">{tx('Carregando...')}</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="lg:hidden flex flex-col gap-3">
            {pageItems.map((item) => (
              <div key={item.id} className="bg-surface-quiet border border-line rounded-xl p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink">{item.name}</p>
                    <p className="text-xs text-muted mt-0.5">{item.city} / {item.state}</p>
                  </div>
                  <div className="flex gap-0 flex-shrink-0">
                    <button onClick={() => openView(item)} aria-label={tx('Visualizar')} className="w-11 h-11 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Eye className="w-4 h-4" />
                    </button>
                    <button onClick={() => openEdit(item)} aria-label={tx('Editar')} className="w-11 h-11 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => setDeleting(item)} aria-label={tx('Excluir')} className="w-11 h-11 flex items-center justify-center text-muted active:text-danger transition-colors" style={{ touchAction: 'manipulation' }}>
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="mt-2 space-y-0.5 text-xs text-ink-2">
                  <p>{item.phone}</p>
                  <p className="truncate text-muted-2">{item.email || tx('Sem e-mail')}</p>
                  {canViewCreator && (
                    <p className="truncate text-muted-2">
                      {tx('Criado por:')} {item.created_by_name || tx('cadastro anterior')}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {pageItems.length === 0 && <p className="text-center text-muted text-sm py-8">{tx(search ? 'Nenhum registro encontrado com este filtro.' : 'Nenhum registro encontrado.')}</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden lg:block overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead style={{ backgroundColor: `${tint(color, 7)}` }}>
                <tr>
                  <Th label={tx('Nome')} col="name" {...thProps} />
                  <Th label={tx('Telefone')} col="phone" {...thProps} />
                  <Th label={tx('E-mail')} col="email" {...thProps} />
                  <Th label={tx('Cidade')} col="city" {...thProps} />
                  <Th label={tx('UF')} col="state" {...thProps} />
                  <Th label={tx('Desc. Máx.')} col="max_discount" {...thProps} />
                  {canViewCreator && (
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider">
                      {tx('Criado por')}
                    </th>
                  )}
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((item) => (
                  <tr key={item.id} className="table-row">
                    <td className="px-4 py-3 text-ink font-medium">{item.name}</td>
                    <td className="px-4 py-3 text-ink-2">{item.phone}</td>
                    <td className="px-4 py-3 text-ink-2">{item.email || '—'}</td>
                    <td className="px-4 py-3 text-ink-2">{item.city}</td>
                    <td className="px-4 py-3 text-muted-2">{item.state}</td>
                    <td className="px-4 py-3 text-muted-2">{item.max_discount}%</td>
                    {canViewCreator && (
                      <td className="px-4 py-3 text-muted-2">
                        {item.created_by_name || tx('Cadastro anterior')}
                      </td>
                    )}
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openView(item)} title={tx('Visualizar')} aria-label={tx('Visualizar')} className="btn-icon"><Eye className="w-4 h-4" /></button>
                        <button onClick={() => openEdit(item)} title={tx('Editar')} aria-label={tx('Editar')} className="btn-icon"><Pencil className="w-4 h-4" /></button>
                        <button onClick={() => setDeleting(item)} title={tx('Excluir')} aria-label={tx('Excluir')} className="btn-icon hover:text-danger"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {pageItems.length === 0 && (
                  <tr><td colSpan={canViewCreator ? 8 : 7} className="px-4 py-10 text-center text-muted">{tx(search ? 'Nenhum registro encontrado com este filtro.' : 'Nenhum registro encontrado.')}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </>
      )}

      {/* View / Create User modal */}
      {viewing && (
        <Modal title={tx('Detalhes — {name}', { name: viewing.name })} onClose={() => setViewing(null)} accentColor={color}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div><span className="text-xs text-muted block">{tx('Nome')}</span><span className="text-ink font-medium">{viewing.name}</span></div>
              <div><span className="text-xs text-muted block">{tx('Telefone')}</span><span className="text-ink-2">{viewing.phone}</span></div>
              <div className="col-span-2"><span className="text-xs text-muted block">{tx('E-mail')}</span><span className="text-ink-2">{viewing.email || tx('Não informado')}</span></div>
              <div><span className="text-xs text-muted block">{tx('Cidade')}</span><span className="text-ink-2">{viewing.city}</span></div>
              <div><span className="text-xs text-muted block">{tx('Estado')}</span><span className="text-ink-2">{viewing.state}</span></div>
              <div><span className="text-xs text-muted block">CPF/CNPJ</span><span className="text-ink-2">{viewing.cpf_cnpj ? formatCpfCnpj(viewing.cpf_cnpj) : '—'}</span></div>
              <div className="col-span-2"><span className="text-xs text-muted block">{tx('Endereço')}</span><span className="text-ink-2">{viewing.address}{viewing.numero ? `, ${viewing.numero}` : ''} — {tx('CEP')} {viewing.cep}</span></div>
              {canViewCreator && (
                <div className="col-span-2">
                  <span className="text-xs text-muted block">{tx('Criado por')}</span>
                  <span className="text-ink-2">{viewing.created_by_name || tx('Cadastro anterior ao rastreamento')}</span>
                </div>
              )}
            </div>

            {(isAdmin || (isRep && entityType === 'client')) && <div className="border-t border-line pt-4">
              <p className="text-xs font-semibold text-muted-2 uppercase tracking-wider mb-3">{tx('Acesso ao Sistema')}</p>

              {createdUser ? (
                <div className="bg-success-soft border border-success/25 rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2 text-success">
                    <CheckCircle className="w-5 h-5 flex-shrink-0" />
                    <span className="text-sm font-semibold">{tx('Usuário criado com sucesso!')}</span>
                  </div>
                  <div className="text-sm text-ink-2 space-y-1">
                    <p><span className="text-muted">{tx('Usuário:')}</span> <strong>{createdUser.username}</strong></p>
                    {createdUser.temp_password && <p><span className="text-muted">{tx('Senha inicial:')}</span> <strong>{createdUser.temp_password}</strong></p>}
                    <p><span className="text-muted">{tx('Perfil:')}</span> {tx(entityType === 'rep' ? 'Representante' : 'Cliente')}</p>
                  </div>
                  <p className="text-xs text-muted-2 mt-1">{tx(entityType === 'client' ? 'Conta pendente. Um administrador deve confirmar o e-mail do titular e enviar o convite.' : 'O usuário deverá trocar a senha no primeiro acesso.')}</p>
                </div>
              ) : viewing?.has_user ? (
                <div className="flex items-center gap-3">
                  <button
                    disabled
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white opacity-50 cursor-not-allowed"
                    style={{ backgroundColor: color }}
                  >
                    <CheckCircle className="w-4 h-4" />
                    {tx('Usuário já criado')}
                  </button>
                  <span className="text-xs text-muted">{tx(entityType === 'client' && !(viewing as Client).user_validated ? 'Aguardando ativação pelo titular.' : 'Gerencie pela tela Admin.')}</span>
                </div>
              ) : (
                <>
                  {createUserError && (
                    <p className="text-xs text-terracotta mb-2">{createUserError}</p>
                  )}
                  <button
                    onClick={handleCreateUser}
                    disabled={createUserPending}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-colors disabled:opacity-60"
                    style={{ backgroundColor: color }}
                  >
                    <UserPlus className="w-4 h-4" />
                    {tx(createUserPending ? 'Criando…' : 'Criar Usuário')}
                  </button>
                  <p className="text-xs text-muted mt-2">
                    {tx(entityType === 'client' ? 'Solicita a conta. A senha será definida pelo titular após confirmação do e-mail por um administrador.' : 'Cria acesso com usuário gerado pelo nome e senha temporária aleatória.')}
                  </p>
                </>
              )}
              {entityType === 'client' && isAdmin && (createdUser || viewing.has_user) && !(viewing as Client).user_validated && (
                <div className="mt-4 space-y-3 border-t border-line pt-4">
                  <p className="text-xs text-ink-2">{tx('Confirme a identidade do titular fora do sistema antes de enviar. Digite o e-mail que foi verificado; ele deve coincidir com o cadastro.')}</p>
                  <input className="input" type="email" aria-label={tx('E-mail confirmado do titular')} value={confirmedEmail} onChange={event => setConfirmedEmail(event.target.value)} placeholder={tx('E-mail confirmado do titular')} autoComplete="off" />
                  <select className="input" aria-label={tx('Método de verificação')} value={verificationMethod} onChange={event => setVerificationMethod(event.target.value as ClientVerificationMethod)}>
                    <option value="phone_callback">{tx('Retorno telefônico ao titular')}</option>
                    <option value="existing_contract">{tx('Contrato existente')}</option>
                    <option value="in_person">{tx('Verificação presencial')}</option>
                  </select>
                  <button className="btn-primary" onClick={() => void handleIssueInvitation()} disabled={!confirmedEmail.trim() || issueInvitation.isPending || inviteSent}>
                    {tx(issueInvitation.isPending ? 'Enviando…' : 'Confirmar e enviar convite')}
                  </button>
                  {inviteSent && <p role="status" className="text-xs text-success">{tx('Convite enviado ao endereço confirmado.')}</p>}
                  {inviteError && <p role="alert" className="text-xs text-danger">{inviteError}</p>}
                </div>
              )}
            </div>}

            <div className="flex justify-end pt-1">
              <button className="btn-secondary" onClick={() => setViewing(null)}>{tx('Fechar')}</button>
            </div>
          </div>
        </Modal>
      )}

      {showForm && (
        <Modal title={tx(editing ? 'Editar {item}' : 'Novo {item}', { item: tx(label).slice(0, -1) })} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <AddressFields form={form} setForm={setForm} market={activeMarket} />
            {entityType === 'client' && (
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-muted">{tx('Perfil de faturamento *')}</span>
                <div className="flex gap-2">
                  {(activeMarket === 'EU' ? ['lojista', 'corporativo', 'pvp'] as const : ['lojista', 'corporativo'] as const).map((profile) => (
                    <button
                      key={profile}
                      type="button"
                      onClick={() => setForm({ ...form, price_profile: profile })}
                      className={`flex-1 py-2 rounded-lg border text-sm font-medium capitalize transition-colors ${(form.price_profile ?? 'lojista') === profile ? 'text-white' : 'border-line text-ink-3 hover:border-faint'}`}
                      style={(form.price_profile ?? 'lojista') === profile ? { backgroundColor: color, borderColor: color } : undefined}
                    >
                      {profile}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {canEditDiscount && (
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-muted">{tx('Desconto Máximo (%)')}</span>
                <NumberField
                  min={0} max={100} step={0.5} className="input"
                  value={form.max_discount ?? defaultMaxDiscount}
                  onValueChange={(v) => setForm({ ...form, max_discount: v })}
                />
              </div>
            )}
            {formError && (
              <div className="flex items-start gap-2 bg-danger-soft border border-danger/25 rounded-lg px-3 py-2.5">
                <X className="w-4 h-4 text-danger flex-shrink-0 mt-0.5" />
                <span className="text-xs text-danger leading-snug">{formError}</span>
              </div>
            )}
            <p className="text-xs text-muted leading-relaxed pt-1">
              {tx('Os dados coletados neste formulário são processados estritamente para a elaboração de orçamentos e gestão do pedido, conforme a nossa Política de Privacidade.')}
            </p>
            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>{tx('Cancelar')}</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }} disabled={isPending || submitting}>
                {tx(submitting ? 'Salvando...' : editing ? 'Salvar' : 'Criar')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete name={deleting.name}
          onConfirm={async () => { await onDelete(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)} />
      )}
    </div>
  )
}

// ── OPCIONAIS ─────────────────────────────────────────────────────────────────

const EMPTY_OPT: OptionalColorCreate = { category: '', color_name: '' }

function OptionaisTab({ color, readOnly = false }: { color: string; readOnly?: boolean }) {
  const { data: optionals, isLoading } = useOptionals()
  const tx = useCadastroText()
  const { data: categories = [] } = useOptionalCategories()
  const createM = useCreateOptional()
  const updateM = useUpdateOptional()
  const deleteM = useDeleteOptional()
  const uploadOptM = useUploadOptionalPhoto()
  const createCatM = useCreateOptionalCategory()
  const updateCatM = useUpdateOptionalCategory()
  const deleteCatM = useDeleteOptionalCategory()

  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<OptionalColor | null>(null)
  const [deleting, setDeleting] = useState<OptionalColor | null>(null)
  const [form, setForm] = useState<OptionalColorCreate>(EMPTY_OPT)
  const [pendingOptFile, setPendingOptFile] = useState<File | null>(null)
  const [optPhotoPreview, setOptPhotoPreview] = useState<string | null>(null)
  const optFileRef = useRef<HTMLInputElement>(null)

  // Group modal
  const [showGroupForm, setShowGroupForm] = useState(false)
  const [editingGroup, setEditingGroup] = useState<OptionalCategory | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<{ id: string; name: string; count: number } | null>(null)
  const [groupForm, setGroupForm] = useState({ name: '', code: '' })
  const [groupErr, setGroupErr] = useState('')

  // Lightbox
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)

  function openCreate() {
    const defaultCat = categories[0]?.code ?? ''
    setForm({ category: defaultCat, color_name: '' }); setEditing(null)
    setPendingOptFile(null); setOptPhotoPreview(null); setShowForm(true)
  }
  function openEdit(opt: OptionalColor) {
    setForm({ category: opt.category, color_name: opt.color_name })
    setOptPhotoPreview(opt.photo_url ?? null); setPendingOptFile(null)
    setEditing(opt); setShowForm(true)
  }
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    let optId: string
    if (editing) {
      await updateM.mutateAsync({ id: editing.id, data: form })
      optId = editing.id
    } else {
      const created = await createM.mutateAsync(form)
      optId = created.id
    }
    if (pendingOptFile) await uploadOptM.mutateAsync({ id: optId, file: pendingOptFile })
    setPendingOptFile(null); setOptPhotoPreview(null)
    setShowForm(false)
  }

  function openNewGroup() { setEditingGroup(null); setGroupForm({ name: '', code: '' }); setGroupErr(''); setShowGroupForm(true) }
  function openEditGroup(cat: OptionalCategory) {
    setEditingGroup(cat); setGroupForm({ name: cat.name, code: cat.code }); setGroupErr(''); setShowGroupForm(true)
  }
  async function handleGroupSubmit(e: React.FormEvent) {
    e.preventDefault(); setGroupErr('')
    try {
      if (editingGroup) await updateCatM.mutateAsync({ id: editingGroup.id, ...groupForm })
      else await createCatM.mutateAsync(groupForm)
      setShowGroupForm(false)
    } catch {
      setGroupErr(tx('Código já existe ou dados inválidos.'))
    }
  }

  // Categorias sempre lidas do banco — nunca de uma lista fixa (V-Bloco65-cats)
  const catOptions = categories.map(c => ({ value: c.code, label: c.name }))
  const catLabel = (code: string) => categories.find(c => c.code === code)?.name ?? code

  // Agrupa por TODA categoria cadastrada (mesmo sem cores ainda, contador 0),
  // mais qualquer código "órfão" achado nos opcionais sem categoria correspondente
  // — isso torna visível (em vez de mascarar) uma futura divergência de código.
  const optionalsByCode = new Map<string, OptionalColor[]>()
  for (const opt of optionals ?? []) {
    if (!optionalsByCode.has(opt.category)) optionalsByCode.set(opt.category, [])
    optionalsByCode.get(opt.category)!.push(opt)
  }
  const knownCodes = new Set(categories.map(c => c.code))
  const grouped = [
    ...categories.map((c) => ({
      category: c.code, label: c.name, items: optionalsByCode.get(c.code) ?? [], cat: c as OptionalCategory | null,
    })),
    ...Array.from(optionalsByCode.keys())
      .filter((code) => !knownCodes.has(code))
      .map((code) => ({ category: code, label: code, items: optionalsByCode.get(code)!, cat: null })),
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-2">
        <span className="text-sm text-muted">{tx('{count} opcionais cadastrados', { count: optionals?.length ?? 0 })}</span>
        {!readOnly && (
          <div className="flex items-center gap-2">
            <button className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-1.5" onClick={openNewGroup}>
              <Plus className="w-3.5 h-3.5" /> {tx('Adicionar Grupos')}
            </button>
            <button className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: color }} onClick={openCreate} disabled={categories.length === 0}
              title={categories.length === 0 ? tx('Crie um grupo primeiro') : undefined}>
              <Plus className="w-4 h-4" /> {tx('Novo Opcional')}
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">{tx('Carregando...')}</p>
      ) : (
        <div className="space-y-4">
          {grouped.map(({ category, label, items, cat }) => (
            <div key={category} className={`rounded-xl border overflow-hidden ${cat ? 'border-line' : 'border-dashed border-warning/40'}`}>
              <div className="px-4 py-2 flex items-center justify-between gap-2"
                style={{ backgroundColor: cat ? `${tint(color, 7)}` : 'var(--color-warning-soft)' }}>
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-wider truncate" style={{ color: cat ? color : 'var(--color-warning)' }}>
                    {label}
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: cat ? `${tint(color, 13)}` : 'color-mix(in srgb, var(--color-warning) 20%, transparent)', color: cat ? color : 'var(--color-warning)' }}>
                    {items.length}
                  </span>
                  {!cat && <span className="text-[10px] text-warning italic truncate">{tx('grupo não cadastrado')}</span>}
                </div>
                {!readOnly && (
                  <div className="flex gap-2 flex-shrink-0">
                    {cat ? (
                      <>
                        <button onClick={() => openEditGroup(cat)} className="btn-icon" title={tx('Editar grupo')}>
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => setDeletingGroup({ id: cat.id, name: cat.name, count: items.length })}
                          className="btn-icon hover:text-danger" title={tx('Excluir grupo')}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => { setEditingGroup(null); setGroupForm({ name: label, code: category }); setGroupErr(''); setShowGroupForm(true) }}
                        className="text-[10px] font-semibold px-2 py-1 rounded-lg border border-warning/40 text-warning hover:bg-warning-soft transition-colors"
                      >
                        {tx('Cadastrar grupo')}
                      </button>
                    )}
                  </div>
                )}
              </div>
              {items.length === 0 ? (
                <p className="px-4 py-3 text-xs text-muted">{tx('Nenhuma cor cadastrada.')}</p>
              ) : (
              <table className="w-full text-sm">
                <tbody>
                  {items.map((opt) => (
                    <tr key={opt.id} className="table-row">
                      <td className="px-4 py-2.5 w-12">
                        {opt.photo_url
                          ? <button onClick={() => setLightboxUrl(opt.photo_url!)} className="cursor-zoom-in">
                              <img src={opt.photo_url} alt={opt.color_name}
                                className="w-8 h-8 rounded-md object-cover border border-line hover:opacity-80 transition-opacity" />
                            </button>
                          : <div className="w-8 h-8 rounded-md bg-bg-2 border border-line" />}
                      </td>
                      <td className="px-4 py-2.5 text-ink">{opt.color_name}</td>
                      {!readOnly && (
                        <td className="px-4 py-2.5 w-16">
                          <div className="flex gap-2">
                            <button onClick={() => openEdit(opt)} aria-label={tx('Editar')} className="btn-icon">
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setDeleting(opt)} aria-label={tx('Excluir')} className="btn-icon hover:text-danger">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              )}
            </div>
          ))}
          {grouped.length === 0 && (
            <p className="text-muted text-sm py-8 text-center">{tx('Nenhum grupo cadastrado. Clique em "Adicionar Grupos" para começar.')}</p>
          )}
        </div>
      )}

      {/* Lightbox */}
      {lightboxUrl && (
        <div className="fixed inset-0 z-modal-sub flex items-center justify-center bg-scrim/75 backdrop-blur-sm"
          onClick={() => setLightboxUrl(null)}>
          <DialogPanel onClose={() => setLightboxUrl(null)} label={tx('Swatch ampliado')} className="relative">
            <img src={lightboxUrl} alt={tx('Swatch ampliado')}
              className="max-w-[90vw] max-h-[80vh] w-64 h-64 object-cover rounded-2xl shadow-2xl border border-white/20" />
            <button onClick={() => setLightboxUrl(null)}
              type="button" aria-label={tx('Fechar')} className="absolute -top-3 -right-3 w-11 h-11 flex items-center justify-center bg-white rounded-full shadow-lg text-ink hover:bg-bg transition-colors">
              <X className="w-4 h-4" />
            </button>
          </DialogPanel>
        </div>
      )}

      {/* Optional form modal */}
      {showForm && (
        <Modal title={tx(editing ? 'Editar Opcional' : 'Novo Opcional')} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Categoria *')}</span>
              <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
                {catOptions.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Nome da Cor *')}</span>
              <input className="input" value={form.color_name}
                onChange={(e) => setForm({ ...form, color_name: e.target.value })} required />
            </label>

            <div>
              <span className="text-xs text-muted block mb-1">{tx('Imagem de Textura (swatch)')}</span>
              <div
                className="border-2 border-dashed border-line rounded-xl p-3 flex flex-col items-center gap-1.5 cursor-pointer transition-colors"
                onClick={() => optFileRef.current?.click()}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
              >
                {optPhotoPreview
                  ? <img src={optPhotoPreview} alt="" className="w-16 h-16 object-cover rounded-lg" />
                  : <Upload className="w-6 h-6 text-faint" />}
                <span className="text-xs text-muted">
                  {tx(optPhotoPreview ? 'Clique para trocar' : 'PNG, JPG — textura do material')}
                </span>
              </div>
              <input ref={optFileRef} type="file" accept=".jpg,.jpeg,.png,.webp" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]; if (!f) return
                  setPendingOptFile(f); setOptPhotoPreview(URL.createObjectURL(f))
                }} />
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>{tx('Cancelar')}</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }}
                disabled={createM.isPending || updateM.isPending || uploadOptM.isPending}>
                {tx(editing ? 'Salvar' : 'Criar')}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Group form modal */}
      {showGroupForm && (
        <Modal title={tx(editingGroup ? 'Editar Grupo' : 'Novo Grupo de Opcionais')} onClose={() => setShowGroupForm(false)} accentColor={color}>
          <form onSubmit={handleGroupSubmit} className="space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Nome do Grupo *')}</span>
              <input className="input" value={groupForm.name} onChange={(e) => setGroupForm(f => ({ ...f, name: e.target.value }))} required autoFocus placeholder={tx('ex: Alumínio')} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Código (identificador único) *')}</span>
              <input className="input font-mono text-sm" value={groupForm.code} onChange={(e) => setGroupForm(f => ({ ...f, code: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} required placeholder={tx('ex: aluminio')} />
              <span className="text-[10px] text-muted">{tx('Apenas letras minúsculas, números e underscores.')}</span>
            </label>
            {groupErr && <p className="text-xs text-danger">{groupErr}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={createCatM.isPending || updateCatM.isPending} className="btn-primary flex-1" style={{ backgroundColor: color }}>
                {tx(createCatM.isPending || updateCatM.isPending ? 'Salvando...' : editingGroup ? 'Salvar' : 'Criar Grupo')}
              </button>
              <button type="button" className="btn-secondary px-4" onClick={() => setShowGroupForm(false)}>{tx('Cancelar')}</button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete name={`${catLabel(deleting.category)} — ${deleting.color_name}`}
          onConfirm={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)} />
      )}

      {deletingGroup && (
        <ConfirmDelete name={deletingGroup.count > 0 ? `${deletingGroup.name} (${deletingGroup.count} ${tx(deletingGroup.count === 1 ? 'cor' : 'cores')})` : deletingGroup.name}
          onConfirm={async () => { await deleteCatM.mutateAsync(deletingGroup.id); setDeletingGroup(null) }}
          onCancel={() => setDeletingGroup(null)} />
      )}
    </div>
  )
}

// ── GroupsTab ─────────────────────────────────────────────────────────────────

type GroupModal =
  | { kind: 'new-group' }
  | { kind: 'edit-group'; group: ProductGroup }
  | { kind: 'new-type'; groupId: string | null }
  | { kind: 'edit-type'; type: ProductType }

function GroupsTab({ color, page, onPage, canEditGroups, canEditTypes, market }: {
  color: string; page: number; onPage: (p: number) => void
  canEditGroups: boolean; canEditTypes: boolean; market: 'BR' | 'EU'
}) {
  // Vincular subgrupo a grupo define o IPI (regra fiscal brasileira). Em
  // Portugal o backend recusa o vínculo (tipo EU não herda grupo BR), então
  // arrastar só é oferecido no Brasil, para quem pode reclassificar.
  const canAssignGroup = canEditTypes && market === 'BR'
  const { data: groups = [], isLoading: groupsLoading } = useProductGroups()
  const tx = useCadastroText()
  const { data: types = [], isLoading: typesLoading } = useProductTypes()

  const createGroupM = useCreateProductGroup()
  const updateGroupM = useUpdateProductGroup()
  const deleteGroupM = useDeleteProductGroup()
  const createTypeM = useCreateProductType()
  const updateTypeM = useUpdateProductType()
  const deleteTypeM = useDeleteProductType()

  const [modal, setModal] = useState<GroupModal | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<ProductGroup | null>(null)
  const [deletingType, setDeletingType] = useState<ProductType | null>(null)
  const [err, setErr] = useState('')

  // Group form state
  const [gName, setGName] = useState('')
  const [gIpi, setGIpi] = useState('0.00')
  // Type form state
  const [tName, setTName] = useState('')
  const [tGroupId, setTGroupId] = useState<string | null>(null)

  // Campo começa vazio (e não em "0.00") para o zero não grudar na digitação;
  // `handleGroupSubmit` já trata string vazia como 0.
  function openNewGroup() { setGName(''); setGIpi(''); setErr(''); setModal({ kind: 'new-group' }) }
  function openEditGroup(g: ProductGroup) { setGName(g.name); setGIpi(Number(g.ipi).toFixed(2)); setErr(''); setModal({ kind: 'edit-group', group: g }) }
  function openNewType(groupId: string | null) { setTName(''); setTGroupId(groupId); setErr(''); setModal({ kind: 'new-type', groupId }) }
  function openEditType(t: ProductType) { setTName(t.name); setTGroupId(t.group_id); setErr(''); setModal({ kind: 'edit-type', type: t }) }

  async function handleGroupSubmit(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    const ipiNum = parseFloat(gIpi.replace(',', '.')) || 0
    try {
      if (modal?.kind === 'edit-group') {
        await updateGroupM.mutateAsync({ id: modal.group.id, name: gName.trim(), ipi: ipiNum })
      } else {
        await createGroupM.mutateAsync({ name: gName.trim(), ipi: ipiNum })
      }
      setModal(null)
    } catch (ex: unknown) {
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Erro ao salvar grupo.'))
    }
  }

  async function handleTypeSubmit(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    try {
      if (modal?.kind === 'edit-type') {
        await updateTypeM.mutateAsync({ id: modal.type.id, name: tName.trim(), group_id: tGroupId })
      } else {
        await createTypeM.mutateAsync({ name: tName.trim(), group_id: tGroupId })
      }
      setModal(null)
    } catch (ex: unknown) {
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Erro ao salvar subgrupo.'))
    }
  }

  const isGroupPending = createGroupM.isPending || updateGroupM.isPending
  const isTypePending = createTypeM.isPending || updateTypeM.isPending
  const isLoading = groupsLoading || typesLoading

  const orphanTypes = types.filter(t => !t.group_id)
  const { pageItems: pagedGroups, totalPages, safePage } = paginate(groups, page)

  // ── Arrastar subgrupo para um grupo ───────────────────────────────────────
  // Soltar não grava direto: mover muda o IPI dos produtos do subgrupo, então
  // pede confirmação. Sem mouse (tablet/teclado) o lápis abre o mesmo ajuste.
  const [draggingTypeId, setDraggingTypeId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [pendingMove, setPendingMove] = useState<{ type: ProductType; group: ProductGroup | null } | null>(null)
  const [moveErr, setMoveErr] = useState('')
  const NO_GROUP_TARGET = '__none__'

  function dropZoneProps(targetGroup: ProductGroup | null) {
    if (!canAssignGroup) return {}
    const key = targetGroup?.id ?? NO_GROUP_TARGET
    return {
      onDragOver: (e: React.DragEvent) => {
        if (!draggingTypeId) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        if (dropTarget !== key) setDropTarget(key)
      },
      onDragLeave: (e: React.DragEvent) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropTarget(null)
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault()
        const typeId = e.dataTransfer.getData('text/plain') || draggingTypeId
        setDropTarget(null)
        setDraggingTypeId(null)
        const type = types.find(t => t.id === typeId)
        if (!type || (type.group_id ?? null) === (targetGroup?.id ?? null)) return
        setMoveErr('')
        setPendingMove({ type, group: targetGroup })
      },
    }
  }

  function dropHighlight(targetGroup: ProductGroup | null) {
    const key = targetGroup?.id ?? NO_GROUP_TARGET
    if (!draggingTypeId) return ''
    return dropTarget === key ? 'ring-2 ring-gold/50 border-gold/60 bg-gold-wash' : 'border-dashed'
  }

  async function confirmMove() {
    if (!pendingMove) return
    setMoveErr('')
    try {
      await updateTypeM.mutateAsync({
        id: pendingMove.type.id,
        name: pendingMove.type.name,
        group_id: pendingMove.group?.id ?? null,
      })
      setPendingMove(null)
    } catch (ex: unknown) {
      setMoveErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Erro ao salvar subgrupo.'))
    }
  }

  // Função de render (não componente): um componente declarado aqui dentro
  // remontaria a cada setState e o navegador cancelaria o arraste em curso.
  function renderTypeChip(t: ProductType, surface: 'bg-bg' | 'bg-white') {
    return (
      <div
        key={t.id}
        draggable={canAssignGroup}
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', t.id)
          e.dataTransfer.effectAllowed = 'move'
          setDraggingTypeId(t.id)
        }}
        onDragEnd={() => { setDraggingTypeId(null); setDropTarget(null) }}
        title={canAssignGroup ? tx('Arraste para um grupo') : undefined}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-line ${surface} text-xs text-ink ${
          canAssignGroup ? 'cursor-grab active:cursor-grabbing' : ''
        } ${draggingTypeId === t.id ? 'opacity-40' : ''}`}
      >
        {canAssignGroup && <GripVertical className="w-3 h-3 text-muted -ml-1" aria-hidden="true" />}
        <span>{t.name}</span>
        {canEditTypes && <button type="button" onClick={() => openEditType(t)} aria-label={`${tx('Editar')} ${t.name}`} className="text-muted hover:text-gold transition-colors">
          <Pencil className="w-2.5 h-2.5" />
        </button>}
        {canEditTypes && <button type="button" onClick={() => setDeletingType(t)} aria-label={`${tx('Excluir')} ${t.name}`} className="btn-icon hover:text-danger">
          <Trash2 className="w-2.5 h-2.5" />
        </button>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink">{tx('Grupos & Subgrupos')}</h2>
        {canEditGroups && <button onClick={openNewGroup}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors"
          style={{ backgroundColor: color }}>
          <Plus className="w-3.5 h-3.5" /> {tx('Novo Grupo')}
        </button>}
      </div>

      {/* Group form modal */}
      {canEditGroups && (modal?.kind === 'new-group' || modal?.kind === 'edit-group') && (
        <Modal
          title={tx(modal.kind === 'edit-group' ? 'Editar Grupo' : 'Novo Grupo')}
          onClose={() => setModal(null)}
          accentColor={color}
        >
          <form onSubmit={handleGroupSubmit} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Nome do Grupo *')}</span>
              <input className="input" value={gName} onChange={(e) => setGName(e.target.value)} required autoFocus />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Alíquota IPI (%)')}</span>
              <input
                className="input"
                type="number"
                step="0.01"
                min="0"
                max="100"
                value={gIpi}
                onChange={(e) => setGIpi(e.target.value)}
              />
            </label>
            {err && <p className="text-xs text-danger">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={isGroupPending} className="btn-primary flex-1">
                {tx(isGroupPending ? 'Salvando...' : modal.kind === 'edit-group' ? 'Salvar Alterações' : 'Criar Grupo')}
              </button>
              <button type="button" onClick={() => setModal(null)} className="btn-secondary px-4">{tx('Cancelar')}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Type form modal */}
      {canEditTypes && (modal?.kind === 'new-type' || modal?.kind === 'edit-type') && (
        <Modal
          title={tx(modal.kind === 'edit-type' ? 'Editar Subgrupo' : 'Novo Subgrupo')}
          onClose={() => setModal(null)}
          accentColor={color}
        >
          <form onSubmit={handleTypeSubmit} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Nome do Subgrupo *')}</span>
              <input className="input" value={tName} onChange={(e) => setTName(e.target.value)} required autoFocus />
            </label>
            {/* Portugal: grupo fiscal é brasileiro; o backend recusa o vínculo. */}
            {market === 'BR' && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">{tx('Grupo')}</span>
              <select className="input" value={tGroupId ?? ''} onChange={(e) => setTGroupId(e.target.value || null)}>
                <option value="">{tx('Sem grupo')}</option>
                {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </label>
            )}
            {err && <p className="text-xs text-danger">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={isTypePending} className="btn-primary flex-1">
                {tx(isTypePending ? 'Salvando...' : modal.kind === 'edit-type' ? 'Salvar Alterações' : 'Criar Subgrupo')}
              </button>
              <button type="button" onClick={() => setModal(null)} className="btn-secondary px-4">{tx('Cancelar')}</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Delete confirmations */}
      {canEditGroups && deletingGroup && (
        <ConfirmDelete name={deletingGroup.name}
          onConfirm={async () => { await deleteGroupM.mutateAsync(deletingGroup.id); setDeletingGroup(null) }}
          onCancel={() => setDeletingGroup(null)} />
      )}
      {canEditTypes && deletingType && (
        <ConfirmDelete name={deletingType.name}
          onConfirm={async () => { await deleteTypeM.mutateAsync(deletingType.id); setDeletingType(null) }}
          onCancel={() => setDeletingType(null)} />
      )}

      {isLoading ? (
        <p className="text-sm text-muted">{tx('Carregando...')}</p>
      ) : (
        <div className="space-y-3">
          {pagedGroups.map(group => {
            const groupTypes = types.filter(t => t.group_id === group.id)
            return (
              <div key={group.id} {...dropZoneProps(group)}
                className={`border border-line rounded-xl p-4 bg-white space-y-3 transition-[background-color,border-color,box-shadow] ${dropHighlight(group)}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="font-semibold text-sm text-ink">{group.name}</span>
                    {Number(group.ipi) > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-note text-gold border border-line-note">
                        IPI {Number(group.ipi).toFixed(2).replace('.', ',')}%
                      </span>
                    )}
                  </div>
                  {canEditGroups && <div className="flex items-center gap-1">
                    <button type="button" onClick={() => openEditGroup(group)} aria-label={`${tx('Editar')} ${group.name}`} className="btn-icon">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button type="button" onClick={() => setDeletingGroup(group)} aria-label={`${tx('Excluir')} ${group.name}`} className="btn-icon hover:text-danger">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>}
                </div>

                {groupTypes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {groupTypes.map(t => renderTypeChip(t, 'bg-bg'))}
                  </div>
                )}
                {groupTypes.length === 0 && draggingTypeId && (
                  <p className="text-xs text-muted">{tx('Solte aqui para mover para este grupo')}</p>
                )}

                {canAssignGroup && <button
                  onClick={() => openNewType(group.id)}
                  className="flex items-center gap-1 text-xs font-medium transition-colors"
                  style={{ color }}
                >
                  <Plus className="w-3 h-3" /> {tx('Novo Subgrupo')}
                </button>}
              </div>
            )
          })}

          {groups.length === 0 && orphanTypes.length === 0 && (
            <p className="text-sm text-muted">{tx('Nenhum grupo cadastrado.')}</p>
          )}

          {(orphanTypes.length > 0 || (draggingTypeId && canAssignGroup) || (market === 'EU' && canEditTypes)) && (
            <div {...dropZoneProps(null)}
              className={`border border-dashed border-line rounded-xl p-4 space-y-3 transition-[background-color,border-color,box-shadow] ${dropHighlight(null)}`}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-xs font-semibold text-muted uppercase tracking-wider">{tx('Sem grupo')}</span>
                {canAssignGroup && orphanTypes.length > 0 && (
                  <span className="text-xs text-muted">{tx('Arraste um subgrupo até o grupo desejado.')}</span>
                )}
                {market === 'EU' && canEditTypes && (
                  <button type="button" onClick={() => openNewType(null)}
                    className="flex min-h-11 lg:min-h-0 items-center gap-1 text-xs font-medium transition-colors" style={{ color }}>
                    <Plus className="w-3 h-3" /> {tx('Novo Subgrupo')}
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {orphanTypes.map(t => renderTypeChip(t, 'bg-white'))}
              </div>
            </div>
          )}

          {pendingMove && (
            <Modal title={tx('Mover subgrupo')} onClose={() => setPendingMove(null)} accentColor={color}>
              <p className="text-sm text-ink-2 mb-2">
                {pendingMove.group
                  ? tx('Mover "{type}" para o grupo "{group}"?', { type: pendingMove.type.name, group: pendingMove.group.name })
                  : tx('Tirar "{type}" do grupo?', { type: pendingMove.type.name })}
              </p>
              <p className="text-xs text-muted mb-5">
                {pendingMove.group
                  ? tx('Os produtos deste subgrupo passam a usar IPI de {ipi}%.', { ipi: Number(pendingMove.group.ipi).toFixed(2).replace('.', ',') })
                  : tx('Sem grupo, pedidos com produtos deste subgrupo são recusados até reclassificar.')}
              </p>
              {moveErr && <p role="alert" className="text-xs font-medium text-danger mb-3">{moveErr}</p>}
              <div className="flex justify-end gap-3">
                <button type="button" className="btn-secondary" onClick={() => setPendingMove(null)}>{tx('Cancelar')}</button>
                <button type="button" className="btn-primary" disabled={updateTypeM.isPending} onClick={() => void confirmMove()}>
                  {tx(updateTypeM.isPending ? 'Salvando...' : 'Mover')}
                </button>
              </div>
            </Modal>
          )}

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </div>
      )}
    </div>
  )
}

// ── CatalogsTab ───────────────────────────────────────────────────────────────
// Catálogo é a linha comercial (Ilya, IBTW, Cerâmica…), independente de
// Grupo/Subgrupo — grupo carrega o IPI e não descreve a linha comercial.

function CatalogsTab({ color, readOnly }: { color: string; readOnly: boolean }) {
  const { data: catalogs = [], isLoading } = useCatalogs()
  const tx = useCadastroText()
  const createM = useCreateCatalog()
  const updateM = useUpdateCatalog()
  const deleteM = useDeleteCatalog()

  const [modal, setModal] = useState<{ kind: 'new' } | { kind: 'edit'; catalog: Catalog } | null>(null)
  const [deleting, setDeleting] = useState<Catalog | null>(null)
  const [name, setName] = useState('')
  const [err, setErr] = useState('')

  function openNew() { setName(''); setErr(''); setModal({ kind: 'new' }) }
  function openEdit(c: Catalog) { setName(c.name); setErr(''); setModal({ kind: 'edit', catalog: c }) }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    const trimmed = name.trim()
    if (!trimmed) { setErr(tx('Informe o nome do catálogo.')); return }
    try {
      if (modal?.kind === 'edit') await updateM.mutateAsync({ id: modal.catalog.id, name: trimmed })
      else await createM.mutateAsync({ name: trimmed })
      setModal(null)
    } catch (ex: unknown) {
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Erro ao salvar catálogo.'))
    }
  }

  async function handleDelete() {
    if (!deleting) return
    setErr('')
    try {
      await deleteM.mutateAsync(deleting.id)
      setDeleting(null)
    } catch (ex: unknown) {
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Erro ao excluir catálogo.'))
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-medium text-ink">{tx('Catálogos')}</h2>
          <p className="text-sm text-muted mt-0.5">{tx('Linhas comerciais usadas como filtro na tela de Produtos.')}</p>
        </div>
        {!readOnly && (
          <button
            onClick={openNew}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white rounded-lg transition-opacity hover:opacity-90"
            style={{ backgroundColor: color }}
          >
            <Plus className="w-4 h-4" /> {tx('Novo Catálogo')}
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted py-8 text-center">{tx('Carregando…')}</p>
      ) : catalogs.length === 0 ? (
        <p className="text-sm text-muted py-8 text-center">{tx('Nenhum catálogo cadastrado.')}</p>
      ) : (
        <div className="bg-white border border-line rounded-xl overflow-hidden">
          {catalogs.map((c, i) => (
            <div key={c.id} className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-line' : ''}`}>
              <span className="text-sm text-ink font-medium">{c.name}</span>
              {!readOnly && (
                <div className="flex items-center gap-1">
                  <button onClick={() => openEdit(c)} className="btn-icon" title={tx('Editar')}>
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => { setErr(''); setDeleting(c) }} className="btn-icon hover:text-danger" title={tx('Excluir')}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {modal && (
        <Modal onClose={() => setModal(null)} title={tx(modal.kind === 'edit' ? 'Editar Catálogo' : 'Novo Catálogo')}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="block">
              <span className="text-xs text-muted">{tx('Nome')}</span>
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                maxLength={50}
                autoFocus
                className="mt-1 w-full py-2 px-3 text-sm bg-bg border border-line rounded-lg text-ink focus:outline-none focus:ring-1 focus:ring-gold"
                placeholder={tx('Ex.: Cerâmica')}
              />
            </label>
            {err && <p className="text-xs text-terracotta">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="button" onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">{tx('Cancelar')}</button>
              <button type="submit" disabled={createM.isPending || updateM.isPending} className="flex-1 py-2 text-white rounded-lg text-sm disabled:opacity-60" style={{ backgroundColor: color }}>{tx('Salvar')}</button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <Modal onClose={() => setDeleting(null)} title={tx('Excluir Catálogo')}>
          <p className="text-sm text-ink-2">{tx('Excluir o catálogo')} <strong>{deleting.name}</strong>?</p>
          {err && <p className="text-xs text-terracotta mt-2">{err}</p>}
          <div className="flex gap-2 pt-3">
            <button type="button" onClick={() => setDeleting(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">{tx('Cancelar')}</button>
            <button type="button" onClick={handleDelete} disabled={deleteM.isPending} className="flex-1 py-2 bg-terracotta text-white rounded-lg text-sm disabled:opacity-60">{tx('Excluir')}</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────

// ── IMPORTAÇÃO CSV (Bloco 63) ──────────────────────────────────────────────────

type ImportResult = { table: string; processed: number; created: number; updated: number; errors: { row: number; message: string }[]; committed: boolean }

const SUPPORT_TABLES: { value: string; label: string; columns: string }[] = [
  { value: 'product-groups',  label: 'Grupos de Produto',  columns: 'name, ipi' },
  { value: 'product-types',   label: 'Tipos de Produto',   columns: 'name, group' },
  { value: 'catalogs',        label: 'Catálogos',          columns: 'name' },
  { value: 'optionals',       label: 'Opcionais',          columns: 'category, color_name' },
  { value: 'representatives', label: 'Representantes',      columns: 'name, phone, email (opcional), cpf_cnpj (opcional), cep, numero, address, city, state' },
  { value: 'clients',         label: 'Clientes',           columns: 'name, phone, email (opcional), cpf_cnpj (opcional), cep, numero, address, city, state, price_profile, rep_email' },
]

function ImportUploader({ endpoint, label, hint, columns, color }: {
  endpoint: string; label: string; hint?: string; columns: string; color: string
}) {
  const queryClient = useQueryClient()
  const tx = useCadastroText()
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleUpload() {
    if (!file) return
    setLoading(true); setError(null); setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post<ImportResult>(`/import/${endpoint}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setResult(data)
      queryClient.invalidateQueries() // atualiza contadores e tabelas dos cadastros
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tx('Falha ao processar o arquivo. Verifique o formato do CSV.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface-quiet p-4">
      <p className="text-sm font-semibold text-ink">{label}</p>
      {hint && <p className="text-xs text-ink-3 mt-0.5">{hint}</p>}
      <p className="text-xs text-muted mt-1">{tx('Colunas:')} <span className="font-mono text-ink-3">{columns}</span></p>
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        <input
          type="file" accept=".csv,text/csv"
          aria-label={tx('Selecionar arquivo CSV de {label}', { label })}
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null) }}
          className="text-xs text-ink-2 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-bg-2 file:text-ink-2 file:cursor-pointer"
        />
        <button
          onClick={handleUpload} disabled={!file || loading}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-50"
          style={{ backgroundColor: color }}
        >
          <Upload className="w-3.5 h-3.5" /> {tx(loading ? 'Enviando...' : 'Importar')}
        </button>
      </div>
      {error && <p className="text-xs text-danger mt-3">{error}</p>}
      {result && (
        <div className={`mt-3 rounded-lg border p-3 ${result.committed ? 'border-success/25 bg-success-soft' : 'border-danger/25 bg-danger-soft'}`}>
          {result.committed ? (
            <p className="text-xs text-ink">
              ✓ <span className="font-semibold">{result.processed}</span> {tx('linhas processadas')} ·{' '}
              <span className="text-success font-semibold">{result.created}</span> {tx('criadas')} ·{' '}
              <span className="text-gold font-semibold">{result.updated}</span> {tx('atualizadas')}
            </p>
          ) : (
            <p className="text-xs text-danger font-semibold">
              {tx('Arquivo rejeitado — nada foi importado. Corrija {count} {errors} em {rows} linhas e reenvie.', { count: result.errors.length, errors: tx(result.errors.length === 1 ? 'erro' : 'erros'), rows: result.processed })}
            </p>
          )}
          {result.errors.length > 0 && (
            <ul className="mt-2 max-h-40 overflow-y-auto space-y-1">
              {result.errors.map((err, i) => (
                <li key={i} className="text-xs text-danger">{tx('Linha {row}: {message}', { row: err.row, message: err.message })}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function ImportTab({ color, canEditFiscal, market }: {
  color: string; canEditFiscal: boolean; market: 'BR' | 'EU'
}) {
  const tx = useCadastroText()
  const [supportTable, setSupportTable] = useState('catalogs')
  const availableTables = SUPPORT_TABLES.filter(t =>
    t.value === 'product-groups' ? canEditFiscal
      : t.value === 'product-types' ? market === 'EU' || canEditFiscal
        : true
  )
  const current = availableTables.find((t) => t.value === supportTable) ?? availableTables[0]
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-ink">{tx('Importação CSV')}</h2>
        <p className="text-sm text-ink-3 mt-0.5">{tx('Importe cadastros em massa via arquivos .csv (UTF-8; separador vírgula ou ponto-e-vírgula). Reimportações atualizam registros existentes pela chave (nome, SKU ou e-mail).')}</p>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2"><LayoutGrid className="w-4 h-4" style={{ color }} /> {tx('Cadastros de apoio')}</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">{tx('Tabela:')}</span>
          <select value={current.value} onChange={(e) => setSupportTable(e.target.value)} className="input text-sm max-w-[240px]">
            {availableTables.map((t) => <option key={t.value} value={t.value}>{tx(t.label)}</option>)}
          </select>
        </div>
        <ImportUploader key={current.value} endpoint={current.value} label={tx(current.label)} columns={tx(current.columns)} color={color} />
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2"><Package className="w-4 h-4" style={{ color }} /> {tx('Catálogo de produtos — 2 etapas')}</h3>
        {canEditFiscal && <ImportUploader endpoint="products" label={tx('Etapa 1: Subir Tabela de Produtos')} hint={tx('Cria/atualiza produtos pelo SKU (product_code).')} columns="product_code, description, type, is_circular, altura, largura, profundidade, price_lojista, price_corporativo, observacao" color={color} />}
        <ImportUploader endpoint="product-optionals" label={tx('Etapa 2: Subir Tabela de Opcionais do Produto')} hint={tx('Vincula opcionais a cada SKU — rode após a Etapa 1.')} columns="product_code, category, color_name" color={color} />
      </section>

      <section className="space-y-3">
        <p className="text-xs text-ink-3 -mt-1">{tx('Selecione a pasta com as fotos — o nome de cada arquivo deve ser o código do produto (ex.: IML0001.png); a foto é associada automaticamente ao produto correspondente.')}</p>
        <BatchPhotoUpload color={color} title="Importar Foto" collapsible={false} />
      </section>
    </div>
  )
}

const TAB_CONFIG: { key: Tab; label: string; Icon: React.ElementType }[] = [
  { key: 'produtos',       label: 'Produtos',       Icon: Package     },
  { key: 'clientes',       label: 'Clientes',        Icon: Users       },
  { key: 'representantes', label: 'Representantes',  Icon: UserCheck   },
  { key: 'opcionais',      label: 'Opcionais',       Icon: Tag         },
  { key: 'tipos',          label: 'Grupos & Subgrupos', Icon: LayoutGrid  },
  { key: 'catalogos',      label: 'Catálogos',      Icon: BookOpen    },
  { key: 'importacao',     label: 'Importação CSV', Icon: Upload      },
]

// ── Bloco 77: persistência de aba/páginas do Cadastro com TTL de 5 minutos ────

const CADASTRO_STATE_KEY = 'cadastros_ui_state'
const CADASTRO_STATE_TTL_MS = 5 * 60 * 1000

interface PersistedCadastroState {
  tab: Tab
  productPage: number
  clientPage: number
  repPage: number
  groupPage: number
}

function loadPersistedCadastroState(): PersistedCadastroState | null {
  try {
    const raw = localStorage.getItem(CADASTRO_STATE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.ts || Date.now() - parsed.ts > CADASTRO_STATE_TTL_MS) return null
    return parsed
  } catch {
    return null
  }
}

function savePersistedCadastroState(state: PersistedCadastroState) {
  localStorage.setItem(CADASTRO_STATE_KEY, JSON.stringify({ ...state, ts: Date.now() }))
}

export default function CadastroPage() {
  const { user } = useAuth()
  const tx = useCadastroText()
  const activeMarket = user?.active_market ?? 'BR'
  const canEditFiscal = activeMarket === 'BR' && user?.role === 'admin'
  const canEditTypes = activeMarket === 'EU'
    ? ['admin', 'vendedor', 'produtos'].includes(user?.role ?? '')
    : canEditFiscal
  const isRep = user?.role === 'representante'
  const isCliente = user?.role === 'cliente' || (user?.role === 'vendedor' && !!user.linked_id)
  const isLimited = isRep || isCliente

  const visibleTabs = TAB_CONFIG.filter(t => {
    if (isCliente) return false
    if (isRep) return t.key === 'clientes'
    if (t.key === 'importacao') return user?.role === 'admin' || user?.role === 'cadastros'
    return true
  })

  const defaultTab: Tab = isRep ? 'clientes' : 'produtos'

  // Bloco 77: restaura aba e paginação da última visita, com TTL de 5 minutos —
  // depois disso, volta silenciosamente aos valores padrão.
  const persisted = useRef(loadPersistedCadastroState()).current
  const allowedTabs = new Set(visibleTabs.map(t => t.key))
  const initialTab = persisted?.tab && allowedTabs.has(persisted.tab) ? persisted.tab : defaultTab
  const [tab, setTab] = useState<Tab>(initialTab)

  // Estados de página isolados por tabela (Bloco 64) — persistem entre trocas de aba
  const [productPage, setProductPage] = useState(persisted?.productPage ?? 1)
  const [clientPage, setClientPage] = useState(persisted?.clientPage ?? 1)
  const [repPage, setRepPage] = useState(persisted?.repPage ?? 1)
  const [groupPage, setGroupPage] = useState(persisted?.groupPage ?? 1)

  useEffect(() => {
    savePersistedCadastroState({ tab, productPage, clientPage, repPage, groupPage })
  }, [tab, productPage, clientPage, repPage, groupPage])

  const { data: productsCount } = useProductsPage({ skip: 0, limit: 1 })
  const { data: clientsCount } = useClientsPage({ skip: 0, limit: 1 })
  const { data: repsCount } = useRepresentativesPage({ skip: 0, limit: 1 })
  const { data: optionals } = useOptionals()
  const { data: productGroups } = useProductGroups()
  const { data: catalogsCount } = useCatalogs()

  const createClient = useCreateClient(); const updateClient = useUpdateClient(); const deleteClient = useDeleteClient()

  const createRep = useCreateRepresentative(); const updateRep = useUpdateRepresentative(); const deleteRep = useDeleteRepresentative()

  const counts: Record<Tab, number> = {
    produtos:       productsCount?.total ?? 0,
    clientes:       clientsCount?.total  ?? 0,
    representantes: repsCount?.total     ?? 0,
    opcionais:      optionals?.length ?? 0,
    tipos:          productGroups?.length ?? 0,
    catalogos:      catalogsCount?.length ?? 0,
    importacao:     0,
  }

  const activeColor = TAB_PALETTE[tab].color

  return (
    <div className="min-h-screen bg-bg text-ink pb-24 md:pb-0">
      <h1 className="sr-only">{tx('Cadastros')}</h1>
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 md:py-6">

        {/* ── Mobile horizontal tab bar ──────────────────────── */}
        <div className="md:hidden mb-3 flex gap-2 overflow-x-auto pb-1 -mx-4 px-4">
          {visibleTabs.map(({ key, label: rawLabel, Icon }) => {
            const label = tx(rawLabel)
            const { color } = TAB_PALETTE[key]
            const isActive = tab === key
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                className="min-h-11 flex-shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold border transition-[background-color,color,border-color,transform,opacity] active:scale-[0.97] active:opacity-80"
                style={isActive
                  ? { backgroundColor: color, color: 'white', borderColor: color, touchAction: 'manipulation' }
                  : { backgroundColor: 'white', color: 'var(--color-ink-3)', borderColor: 'var(--color-line)', touchAction: 'manipulation' }
                }
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
                <span
                  className="text-[11px] font-bold px-1.5 py-0.5 rounded-full"
                  style={isActive
                    ? { backgroundColor: 'rgba(255,255,255,0.3)', color: 'white' }
                    : { backgroundColor: 'var(--color-bg-2)', color: 'var(--color-muted)' }
                  }
                >
                  {counts[key]}
                </span>
              </button>
            )
          })}
        </div>

        <div className="flex flex-col gap-4 md:grid md:grid-cols-[220px_minmax(0,1fr)] md:gap-6">

          {/* ── Sidebar (desktop only) ──────────────────────────── */}
          <aside className="hidden md:block">
            <div className="bg-white border border-line rounded-xl shadow-sm p-3 sticky top-20 space-y-1">
              <p className="text-xs font-semibold text-muted uppercase tracking-widest px-3 pb-2">{tx('Cadastros')}</p>
              {visibleTabs.map(({ key, label: rawLabel, Icon }) => {
            const label = tx(rawLabel)
                const { color } = TAB_PALETTE[key]
                const isActive = tab === key
                const count = counts[key]
                return (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    type="button"
                    aria-current={isActive ? 'page' : undefined}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-[background-color,color,box-shadow] duration-150 text-left ${isActive ? '' : 'hover:bg-bg'}`}
                    style={isActive
                      ? { backgroundColor: tint(color, 7), color, boxShadow: `inset 0 0 0 1px ${tint(color, 14)}` }
                      : undefined
                    }
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" style={isActive ? { color } : { color: 'var(--color-muted)' }} />
                    <span className="flex-1" style={isActive ? {} : { color: 'var(--color-ink-3)' }}>{label}</span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-full font-semibold min-w-[22px] text-center"
                      style={isActive
                        ? { backgroundColor: tint(color, 13), color }
                        : { backgroundColor: 'var(--color-bg-2)', color: 'var(--color-muted)' }}
                    >
                      {count}
                    </span>
                  </button>
                )
              })}
            </div>
          </aside>

          {/* ── Painel de Dados ───────────────────────────────────── */}
          <section aria-label={tx('Painel de dados')} className="min-w-0 max-w-full bg-white border border-line rounded-xl shadow-sm p-6"
            style={{ borderTop: `3px solid ${activeColor}` }}>
            {tab === 'produtos' && <ProductsTab color={TAB_PALETTE.produtos.color} page={productPage} onPage={setProductPage} />}

            {tab === 'clientes' && (
              <PeopleTab
                label="Clientes"
                entityType="client"
                isPending={createClient.isPending || updateClient.isPending}
                color={TAB_PALETTE.clientes.color}
                onCreate={async (data) => { await createClient.mutateAsync(data) }}
                onUpdate={async (id, data) => { await updateClient.mutateAsync({ id, data }) }}
                onDelete={async (id) => { await deleteClient.mutateAsync(id) }}
                page={clientPage} onPage={setClientPage}
              />
            )}

            {tab === 'representantes' && (
              <PeopleTab
                label="Representantes"
                entityType="rep"
                isPending={createRep.isPending || updateRep.isPending}
                color={TAB_PALETTE.representantes.color}
                onCreate={async (data) => { await createRep.mutateAsync(data) }}
                onUpdate={async (id, data) => { await updateRep.mutateAsync({ id, data }) }}
                onDelete={async (id) => { await deleteRep.mutateAsync(id) }}
                page={repPage} onPage={setRepPage}
              />
            )}

            {tab === 'opcionais' && <OptionaisTab color={TAB_PALETTE.opcionais.color} readOnly={isLimited} />}

            {tab === 'tipos' && <GroupsTab color={TAB_PALETTE.tipos.color} page={groupPage} onPage={setGroupPage} canEditGroups={canEditFiscal} canEditTypes={canEditTypes} market={activeMarket} />}

            {tab === 'catalogos' && <CatalogsTab color={TAB_PALETTE.catalogos.color} readOnly={isLimited} />}

            {tab === 'importacao' && <ImportTab color={TAB_PALETTE.importacao.color} canEditFiscal={canEditFiscal} market={activeMarket} />}
          </section>
        </div>
      </div>
    </div>
  )
}
