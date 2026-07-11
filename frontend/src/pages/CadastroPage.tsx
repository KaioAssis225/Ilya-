import { useState, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api from '../lib/api'
import { isConjuntoType } from '../lib/productType'
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Pencil, Trash2, Plus, X, Upload, ImageIcon, Package, Users, UserCheck, Tag, Eye, UserPlus, CheckCircle, LayoutGrid, Search } from 'lucide-react'
import { useProducts, useCreateProduct, useUpdateProduct, useDeleteProduct, useUploadProductPhoto } from '../hooks/useProducts'
import { useClients, useCreateClient, useUpdateClient, useDeleteClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative, useUpdateRepresentative, useDeleteRepresentative } from '../hooks/useRepresentatives'
import { useOptionals, useCreateOptional, useUpdateOptional, useDeleteOptional, useUploadOptionalPhoto } from '../hooks/useOptionals'
import { useProductTypes, useCreateProductType, useUpdateProductType, useDeleteProductType } from '../hooks/useProductTypes'
import { useProductGroups, useCreateProductGroup, useUpdateProductGroup, useDeleteProductGroup } from '../hooks/useProductGroups'
import type { ProductGroup } from '../hooks/useProductGroups'
import type { ProductType } from '../hooks/useProductTypes'
import { useOptionalCategories, useCreateOptionalCategory, useUpdateOptionalCategory, useDeleteOptionalCategory } from '../hooks/useOptionalCategories'
import type { OptionalCategory } from '../hooks/useOptionalCategories'
import { useCreateUserFromClient, useCreateUserFromRep } from '../hooks/useUsers'
import type { UserCreateResponse } from '../hooks/useUsers'
import { useAuth } from '../hooks/useAuth'
import type { Product, ProductCreate, ProductSetComponentCreate, Client, ClientCreate, Representative, ViaCepResponse, OptionalColor, OptionalColorCreate } from '../types'

type Tab = 'produtos' | 'clientes' | 'representantes' | 'opcionais' | 'tipos' | 'importacao'
type SortDir = 'asc' | 'desc'

const ESTADOS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
  'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
]

// Traduz erros de validação da API (422 do FastAPI vem como array em `detail`)
// para uma mensagem única e amigável em português.
const FIELD_LABEL: Record<string, string> = {
  name: 'Nome', phone: 'Telefone', email: 'E-mail', cep: 'CEP',
  numero: 'Número', address: 'Endereço', city: 'Cidade', state: 'Estado (UF)',
}

function parseApiError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const msgs = detail.map((d: { loc?: (string | number)[]; msg?: string }) => {
      const field = d.loc?.[d.loc.length - 1]
      const label = typeof field === 'string' ? (FIELD_LABEL[field] ?? field) : ''
      if (field === 'email') return 'E-mail inválido. Informe um e-mail válido (ex: nome@dominio.com).'
      if (field === 'state') return 'Selecione o estado (UF).'
      return label ? `${label}: ${d.msg ?? 'valor inválido'}` : (d.msg ?? 'Dados inválidos.')
    })
    return Array.from(new Set(msgs)).join(' ')
  }
  return 'Não foi possível salvar. Verifique os dados e tente novamente.'
}

const TAB_PALETTE = {
  produtos:        { color: '#b25e50', label: 'Terracota' },
  clientes:        { color: '#648261', label: 'Verde Oliva' },
  representantes:  { color: '#507a9b', label: 'Azul Mineral' },
  opcionais:       { color: '#c47e4a', label: 'Âmbar' },
  tipos:           { color: '#7a5c9b', label: 'Violeta' },
  importacao:      { color: '#3f6f6f', label: 'Petróleo' },
} as const

// ── helpers ─────────────────────────────────────────────────────────────────

function useSortedList<T>(items: T[] | undefined, defaultKey: keyof T) {
  const [sortKey, setSortKey] = useState<keyof T>(defaultKey)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  function toggle(key: keyof T) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = [...(items ?? [])].sort((a, b) => {
    const av = a[sortKey]; const bv = b[sortKey]
    const cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'pt-BR', { numeric: true })
    return sortDir === 'asc' ? cmp : -cmp
  })

  return { sorted, sortKey, sortDir, toggle }
}

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

// ── Address form fields ──────────────────────────────────────────────────────

function formatPhone(value: string): string {
  const d = value.replace(/\D/g, '').slice(0, 11)
  if (d.length === 0) return ''
  if (d.length <= 2) return `(${d}`
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

function formatCep(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 8)
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits
}

function formatOnlyNumbers(value: string): string {
  return value.replace(/\D/g, '')
}

function AddressFields({ form, setForm }: { form: ClientCreate; setForm: (v: ClientCreate) => void }) {
  const [cepLoading, setCepLoading] = useState(false)
  const cepAbortRef = useRef<AbortController | null>(null)
  useEffect(() => () => cepAbortRef.current?.abort(), [])

  async function handleCepBlur() {
    cepAbortRef.current?.abort()
    const controller = new AbortController()
    cepAbortRef.current = controller
    setCepLoading(true)
    const data = await fetchCep(form.cep, controller.signal)
    if (controller.signal.aborted) return
    if (data) {
      setForm({
        ...form,
        address: `${data.logradouro}${data.bairro ? ', ' + data.bairro : ''}`,
        city: data.localidade,
        state: data.uf,
      })
    }
    setCepLoading(false)
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-muted">Nome *</span>
        <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Telefone *</span>
        <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: formatPhone(e.target.value) })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">E-mail *</span>
        <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1 relative">
        <span className="text-xs text-muted">CEP *</span>
        <input className="input pr-8" value={form.cep} onChange={(e) => setForm({ ...form, cep: formatCep(e.target.value) })} onBlur={handleCepBlur} maxLength={9} required />
        {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-gold animate-pulse">...</span>}
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Número</span>
        <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: formatOnlyNumbers(e.target.value) })} />
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
        <span className="text-xs text-muted">Estado *</span>
        <select className="input" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} required>
          <option value="">UF</option>
          {ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
    </div>
  )
}

// ── Modal wrapper ─────────────────────────────────────────────────────────────

function Modal({ title, onClose, children, accentColor }: {
  title: string; onClose: () => void; children: React.ReactNode; accentColor?: string
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel w-full max-w-lg mx-4 md:mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-line"
          style={accentColor ? { borderLeftColor: accentColor, borderLeftWidth: 3 } : {}}>
          <h3 className="text-base font-semibold text-ink">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-ink transition-colors" aria-label="Fechar"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 max-h-[80vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

function ConfirmDelete({ name, onConfirm, onCancel }: { name: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Modal title="Confirmar exclusão" onClose={onCancel}>
      <p className="text-ink-2 mb-6">Excluir <span className="text-ink font-medium">"{name}"</span>? Esta ação não pode ser desfeita.</p>
      <div className="flex justify-end gap-3">
        <button className="btn-secondary" onClick={onCancel}>Cancelar</button>
        <button className="btn-danger" onClick={onConfirm}>Excluir</button>
      </div>
    </Modal>
  )
}

// ── PRODUTOS ──────────────────────────────────────────────────────────────────

const EMPTY_PRODUCT: ProductCreate = {
  product_code: '', description: '', type: 'Outro', is_circular: false,
  is_set: false, set_items: [], components: [],
  altura: 0, largura: 0, profundidade: 0, price: 0, price_lojista: 0, price_corporativo: 0, observacao: null,
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
  separator: string = ', '
): string {
  const specificGroups = groupOptionalsByCategory(p.optionals, catLabel)
  const specificCats = new Set(specificGroups.map(g => g.category))
  const globalCats = (p.all_optionals_categories ?? '').split(',').filter(Boolean)
  const labels = [
    ...globalCats.filter(c => !specificCats.has(c)).map(c => `${catLabel(c)} (Todos)`),
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
  if (totalPages <= 1) return null
  const canPrev = page > 1
  const canNext = page < totalPages
  const base = "flex items-center gap-1 px-3.5 py-2 rounded-lg border text-sm font-medium transition-all active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
  const ring = (e: React.FocusEvent<HTMLButtonElement>, on: boolean) => { e.currentTarget.style.boxShadow = on ? `0 0 0 3px ${color}33` : '' }
  return (
    <div className="flex items-center justify-center gap-3 mt-4">
      <button type="button" disabled={!canPrev} onClick={() => onPage(page - 1)}
        className={base} style={{ borderColor: '#e8e0d6', backgroundColor: '#faf8f4', color: canPrev ? '#4a3f38' : '#c8bdb5' }}
        onFocus={(e) => ring(e, canPrev)} onBlur={(e) => ring(e, false)}>
        <ChevronLeft className="w-4 h-4" /> Anterior
      </button>
      <span className="text-sm text-ink-3 tabular-nums select-none">Página <span className="font-semibold text-ink">{page}</span> de {totalPages}</span>
      <button type="button" disabled={!canNext} onClick={() => onPage(page + 1)}
        className={base} style={{ borderColor: '#e8e0d6', backgroundColor: '#faf8f4', color: canNext ? '#4a3f38' : '#c8bdb5' }}
        onFocus={(e) => ring(e, canNext)} onBlur={(e) => ring(e, false)}>
        Próximo <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  )
}

// ── Bloco 71: Upload de Fotos em Lote (dropzone + fila concorrente) ───────────

type BatchStatus = 'pending' | 'uploading' | 'success' | 'error'
interface BatchItem { file: File; sku: string; product: Product; status: BatchStatus; error?: string }

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

function BatchPhotoUpload({ products, color, title = 'Upload de Fotos em Lote', collapsible = true }: {
  products: Product[]; color: string; title?: string; collapsible?: boolean
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(!collapsible)
  const [items, setItems] = useState<BatchItem[]>([])
  const [rejected, setRejected] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const dirInputRef = useRef<HTMLInputElement>(null)
  const filesInputRef = useRef<HTMLInputElement>(null)

  function processFiles(files: File[]) {
    const bySku = new Map(products.map((p) => [p.product_code.toUpperCase(), p]))
    const validated: BatchItem[] = []
    const rejectedNames: string[] = []
    for (const file of files) {
      if (!/\.(jpg|jpeg|png|webp)$/i.test(file.name)) continue
      const sku = skuFromFilename(file.name)
      const product = bySku.get(sku)
      if (product) validated.push({ file, sku, product, status: 'pending' })
      else rejectedNames.push(file.name)
    }
    setItems(validated)
    setRejected(rejectedNames)
  }

  async function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const dt = e.dataTransfer
    const dtItems = dt.items
    if (dtItems && dtItems.length > 0 && (dtItems[0] as unknown as { webkitGetAsEntry?: unknown }).webkitGetAsEntry) {
      const entries: FileSystemEntryLike[] = []
      for (let i = 0; i < dtItems.length; i++) {
        const entry = (dtItems[i] as unknown as { webkitGetAsEntry: () => FileSystemEntryLike | null }).webkitGetAsEntry()
        if (entry) entries.push(entry)
      }
      const files = (await Promise.all(entries.map((entry) => traverseFileTree(entry)))).flat()
      processFiles(files)
    } else {
      processFiles(Array.from(dt.files))
    }
  }

  async function startUpload() {
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
          className="w-full flex items-center justify-between px-4 py-3 bg-[#fcfbfa] text-left"
        >
          <span className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Upload className="w-4 h-4" style={{ color }} /> {title}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
        </button>
      ) : (
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2 mb-3"><ImageIcon className="w-4 h-4" style={{ color }} /> {title}</h3>
      )}

      {open && (
        <div className={collapsible ? 'p-4 border-t border-line space-y-4' : 'space-y-4'}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className="border-2 border-dashed rounded-xl p-6 text-center transition-colors"
            style={{ borderColor: dragOver ? color : '#e8e0d6', backgroundColor: dragOver ? `${color}0a` : '#faf8f4' }}
          >
            <Upload className="w-6 h-6 mx-auto mb-2" style={{ color: dragOver ? color : '#c8bdb5' }} />
            <p className="text-sm text-ink-3">Arraste uma pasta ou arquivos de fotos aqui</p>
            <p className="text-xs text-muted mt-1">O nome do arquivo deve ser o código do produto (ex.: IML0001.png)</p>
            <div className="flex items-center justify-center gap-2 mt-3">
              <button type="button" className="btn-secondary text-xs" onClick={() => dirInputRef.current?.click()}>Selecionar pasta</button>
              <button type="button" className="btn-secondary text-xs" onClick={() => filesInputRef.current?.click()}>Selecionar arquivos</button>
            </div>
            <input
              ref={dirInputRef} type="file" multiple className="hidden"
              {...({ webkitdirectory: 'true', directory: 'true' } as Record<string, string>)}
              onChange={(e) => processFiles(Array.from(e.target.files ?? []))}
            />
            <input
              ref={filesInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" className="hidden"
              onChange={(e) => processFiles(Array.from(e.target.files ?? []))}
            />
          </div>

          {(items.length > 0 || rejected.length > 0) && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-4 text-xs">
                <span className="flex items-center gap-1.5 text-[#4a7a47]"><CheckCircle className="w-3.5 h-3.5" /> {items.length} validada(s)</span>
                {rejected.length > 0 && <span className="flex items-center gap-1.5 text-terracotta"><X className="w-3.5 h-3.5" /> {rejected.length} rejeitada(s) — SKU não encontrado</span>}
              </div>

              {rejected.length > 0 && (
                <div className="bg-[#fef3f2] border border-red-200 rounded-lg p-2.5 max-h-24 overflow-y-auto">
                  {rejected.map((name) => <p key={name} className="text-[11px] text-terracotta font-mono">{name}</p>)}
                </div>
              )}

              {items.length > 0 && (
                <>
                  {uploading && (
                    <div className="w-full h-2 bg-bg-2 rounded-full overflow-hidden">
                      <div className="h-full transition-all" style={{ width: `${progress}%`, backgroundColor: color }} />
                    </div>
                  )}
                  <div className="max-h-56 overflow-y-auto border border-line rounded-lg divide-y divide-bg-2">
                    {items.map((item) => (
                      <div key={item.file.name} className="flex items-center justify-between px-3 py-1.5 text-xs">
                        <span className="font-mono text-ink-2 truncate">{item.sku}</span>
                        <span className="text-muted truncate flex-1 px-2">{item.file.name}</span>
                        {item.status === 'pending' && <span className="text-muted">Aguardando</span>}
                        {item.status === 'uploading' && <span style={{ color }}>Enviando…</span>}
                        {item.status === 'success' && <span className="flex items-center gap-1 text-[#4a7a47]"><CheckCircle className="w-3.5 h-3.5" /> Enviada</span>}
                        {item.status === 'error' && <span className="text-terracotta" title={item.error}>Erro</span>}
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={startUpload}
                    className="btn-primary w-full disabled:opacity-60"
                    style={{ backgroundColor: color }}
                  >
                    {uploading ? `Enviando… ${progress}%` : `Iniciar Upload (${items.length})`}
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
  const { data: products, isLoading } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const { data: allTypes = [] } = useProductTypes()
  const { data: optCategories = [] } = useOptionalCategories()
  const createM = useCreateProduct()
  const updateM = useUpdateProduct()
  const deleteM = useDeleteProduct()
  const uploadM = useUploadProductPhoto()
  const createTypeM = useCreateProductType()

  // Categorias de opcionais sempre lidas do banco — nunca de uma lista fixa (V-Bloco65-cats)
  const catLabel = (code: string) => optCategories.find(c => c.code === code)?.name ?? code

  const { sorted, sortKey, sortDir, toggle } = useSortedList<Product>(products, 'product_code')
  const [search, setSearch] = useState('')
  const filtered = sorted.filter((p) =>
    `${p.product_code} ${p.description}`.toLowerCase().includes(search.toLowerCase())
  )
  const { pageItems, totalPages, safePage } = paginate(filtered, page)
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
      type: p.type ?? 'Outro',
      is_circular: p.is_circular,
      is_set: p.is_set,
      altura: p.altura,
      largura: p.largura,
      profundidade: p.profundidade,
      price: p.price ?? 0,
      price_lojista: p.price_lojista ?? 0,
      price_corporativo: p.price_corporativo ?? 0,
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
        const updated = await updateM.mutateAsync({ id: editing.id, data: payload })
        if (pendingFile) await uploadM.mutateAsync({ id: updated.id, file: pendingFile })
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

  const thProps = { sortKey: String(sortKey), sortDir, onSort: (k: string) => toggle(k as keyof Product), color }

  return (
    <div>
      <BatchPhotoUpload products={products ?? []} color={color} />

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <span className="text-sm text-muted whitespace-nowrap">{products?.length ?? 0} {(products?.length ?? 0) === 1 ? 'produto' : 'produtos'}</span>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
            <input className="input pl-9" placeholder="Buscar por código ou descrição..." value={search} onChange={(e) => { setSearch(e.target.value); onPage(1) }} />
          </div>
          <button className="btn-primary flex items-center gap-2 flex-shrink-0" style={{ backgroundColor: color, touchAction: 'manipulation' } as React.CSSProperties} onClick={openCreate}>
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Novo </span>Produto
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">Carregando...</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="md:hidden flex flex-col gap-3">
            {pageItems.map((p) => (
              <div key={p.id} className="bg-[#fcfbfa] border border-line rounded-xl p-3.5 flex gap-3">
                {p.photo_url
                  ? <img src={p.photo_url} alt="" className="w-14 h-14 object-cover rounded-lg border border-line flex-shrink-0" />
                  : <div className="w-14 h-14 bg-bg-2 rounded-lg flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-faint" /></div>
                }
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <span className="text-[11px] font-mono font-semibold" style={{ color }}>{p.product_code}</span>
                      <p className="text-sm font-medium text-ink leading-snug line-clamp-2">{p.description}</p>
                    </div>
                    <div className="flex gap-0 flex-shrink-0">
                      <button onClick={() => openEdit(p)} aria-label="Editar" className="w-9 h-9 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleting(p)} aria-label="Excluir" className="w-9 h-9 flex items-center justify-center text-muted active:text-red-500 transition-colors" style={{ touchAction: 'manipulation' }}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-muted">
                      {isConjuntoType(p.type) ? '' : p.is_circular
                        ? `Ø ${Number(p.largura).toFixed(2).replace('.', ',')} m`
                        : `${Number(p.largura).toFixed(2).replace('.', ',')} × ${Number(p.profundidade).toFixed(2).replace('.', ',')} × ${Number(p.altura).toFixed(2).replace('.', ',')} m`}
                    </span>
                    <span className="text-right">
                      <span className="block text-sm font-bold text-ink">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price_lojista)}</span>
                      <span className="block text-[10px] text-ink-3">Corp.: {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price_corporativo)}</span>
                    </span>
                  </div>
                  {(p.optionals.length > 0 || p.all_optionals_categories) && (
                    <p className="text-[10px] text-muted mt-0.5 truncate">{getProductOptionalsLabel(p, catLabel, ' · ')}</p>
                  )}
                </div>
              </div>
            ))}
            {filtered.length === 0 && <p className="text-center text-muted text-sm py-8">{search ? 'Nenhum produto encontrado com este filtro.' : 'Nenhum produto cadastrado.'}</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden md:block overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead style={{ backgroundColor: `${color}12` }}>
                <tr>
                  <Th label="Código" col="product_code" {...thProps} />
                  <Th label="Descrição" col="description" {...thProps} />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-muted uppercase">Dimensões</th>
                  <Th label="Preço" col="price_lojista" {...thProps} />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-muted uppercase">Opcionais</th>
                  <th className="px-4 py-3 text-xs font-semibold text-muted uppercase">Foto</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td className="px-4 py-3 font-mono text-sm font-medium" style={{ color }}>{p.product_code}</td>
                    <td className="px-4 py-3 text-ink max-w-[180px] truncate">{p.description}</td>
                    <td className="px-4 py-3 text-ink-2 text-xs whitespace-nowrap">
                      {isConjuntoType(p.type) ? '—' : p.is_circular
                        ? `Ø ${Number(p.largura).toFixed(2).replace('.', ',')} × A ${Number(p.altura).toFixed(2).replace('.', ',')} m`
                        : `L ${Number(p.largura).toFixed(2).replace('.', ',')} × P ${Number(p.profundidade).toFixed(2).replace('.', ',')} × A ${Number(p.altura).toFixed(2).replace('.', ',')} m`}
                    </td>
                    <td className="px-4 py-3 text-sm whitespace-nowrap">
                      <div className="text-ink font-medium">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price_lojista)}</div>
                      <div className="text-[10px] text-ink-3">Corp.: {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price_corporativo)}</div>
                    </td>
                    <td className="px-4 py-3 text-muted-2 text-xs max-w-[160px]">
                      {p.optionals.length > 0 || p.all_optionals_categories
                        ? getProductOptionalsLabel(p, catLabel, ', ')
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {p.photo_url
                        ? <img src={p.photo_url} alt="" className="w-10 h-10 object-cover rounded-lg border border-line" />
                        : <ImageIcon className="w-6 h-6 text-faint" />}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openEdit(p)} aria-label="Editar" className="text-muted transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Pencil className="w-4 h-4" /></button>
                        <button onClick={() => setDeleting(p)} aria-label="Excluir" className="text-muted hover:text-red-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-muted">{search ? 'Nenhum produto encontrado com este filtro.' : 'Nenhum produto cadastrado.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </>
      )}

      {showNewTypeModal && (
        <Modal title="Novo Tipo de Móvel" onClose={() => { setShowNewTypeModal(false); setNewTypeName(''); setNewTypeErr('') }} accentColor={color}>
          <form onSubmit={async (e) => {
            e.preventDefault(); setNewTypeErr('')
            try {
              const created = await createTypeM.mutateAsync({ name: newTypeName.trim() })
              setForm(prev => ({ ...prev, type: created.name }))
              setShowNewTypeModal(false); setNewTypeName('')
            } catch {
              setNewTypeErr('Tipo já existe ou nome inválido.')
            }
          }} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Nome do Novo Tipo *</span>
              <input className="input" value={newTypeName} onChange={(e) => setNewTypeName(e.target.value)} required autoFocus />
            </label>
            {newTypeErr && <p className="text-xs text-red-500">{newTypeErr}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={createTypeM.isPending} className="btn-primary flex-1">
                {createTypeM.isPending ? 'Salvando...' : 'Criar e Selecionar'}
              </button>
              <button type="button" onClick={() => { setShowNewTypeModal(false); setNewTypeName('') }} className="btn-secondary px-4">Cancelar</button>
            </div>
          </form>
        </Modal>
      )}

      {showForm && (
        <Modal title={editing ? 'Editar Produto' : 'Novo Produto'} onClose={() => { setFormError(null); setShowForm(false) }} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-4">
            {formError && (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                <span className="text-xs text-red-700 leading-snug">{formError}</span>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Código *</span>
                <input className="input" value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Preço Lojista (R$) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.price_lojista ?? 0} onChange={(e) => setForm({ ...form, price_lojista: Number(e.target.value) })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Preço Corporativo (R$) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.price_corporativo ?? 0} onChange={(e) => setForm({ ...form, price_corporativo: Number(e.target.value) })} required />
              </label>
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-muted">Descrição *</span>
                <input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-muted">Observação</span>
                <textarea
                  className="input resize-none"
                  rows={2}
                  placeholder="Informações técnicas, restrições, montagem..."
                  value={form.observacao ?? ''}
                  onChange={(e) => setForm({ ...form, observacao: e.target.value || null })}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-muted">Tipo</span>
                <select className="input" value={form.type ?? 'Outro'} onChange={(e) => {
                  if (e.target.value === '__new__') { setShowNewTypeModal(true) }
                  else setForm({ ...form, type: e.target.value })
                }}>
                  {(allTypes.length > 0 ? allTypes.map(t => t.name) : ['Poltrona','Sofá','Cadeira','Mesa','Banqueta','Chaise','Aparador','Outro']).map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                  <option value="__new__">+ Adicionar Novo...</option>
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
                <span className="text-sm text-ink-2">Medida Redonda (Ø — circular)</span>
              </label>
            )}


            {!isConjuntoType(form.type) && (
              <div className="grid grid-cols-3 gap-3">
                {form.is_circular ? (
                  <>
                    <label className="flex flex-col gap-1 col-span-2">
                      <span className="text-xs text-muted">Diâmetro Ø (m) *</span>
                      <input className="input" type="number" min="0" step="0.01" value={form.largura}
                        onChange={(e) => setForm({ ...form, largura: Number(e.target.value) })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">Altura A (m) *</span>
                      <input className="input" type="number" min="0" step="0.01" value={form.altura}
                        onChange={(e) => setForm({ ...form, altura: Number(e.target.value) })} required />
                    </label>
                  </>
                ) : (
                  <>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">Largura L (m) *</span>
                      <input className="input" type="number" min="0" step="0.01" value={form.largura}
                        onChange={(e) => setForm({ ...form, largura: Number(e.target.value) })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">Prof. P (m) *</span>
                      <input className="input" type="number" min="0" step="0.01" value={form.profundidade}
                        onChange={(e) => setForm({ ...form, profundidade: Number(e.target.value) })} required />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs text-muted">Altura A (m) *</span>
                      <input className="input" type="number" min="0" step="0.01" value={form.altura}
                        onChange={(e) => setForm({ ...form, altura: Number(e.target.value) })} required />
                    </label>
                  </>
                )}
              </div>
            )}

            {isConjuntoType(form.type) ? (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">Componentes do Conjunto</span>
                {(form.components ?? []).length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {(form.components ?? []).map((comp, idx) => (
                      <div key={idx} className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-line bg-[#fcfbfa]">
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
                            className="text-muted hover:opacity-70 transition-colors mt-0.5"
                            style={{ color: editingCompIndex === idx ? color : undefined }}
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setForm(prev => ({ ...prev, components: (prev.components ?? []).filter((_, i) => i !== idx) }))}
                            className="text-muted hover:text-red-500 transition-colors mt-0.5"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="border border-[#e8dccb] rounded-xl p-4 bg-[#fdf8f2] space-y-3">
                  <span className="text-xs font-semibold text-ink-2">{editingCompIndex !== null ? 'Editar Componente' : 'Novo Componente'}</span>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Descrição *</span>
                    <input className="input" placeholder="ex: Sofá 3 lugares, Poltrona, Mesa..." value={compForm.description}
                      onChange={e => setCompForm(f => ({ ...f, description: e.target.value }))} />
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={compForm.is_circular}
                      onChange={e => setCompForm(f => ({ ...f, is_circular: e.target.checked, profundidade: e.target.checked ? 0 : f.profundidade }))}
                      style={{ accentColor: color }} className="w-4 h-4" />
                    <span className="text-sm text-ink-2">Medida Redonda (Ø)</span>
                  </label>
                  {compForm.is_circular ? (
                    <div className="grid grid-cols-3 gap-3">
                      <label className="flex flex-col gap-1 col-span-2">
                        <span className="text-xs text-muted">Diâmetro Ø (m)</span>
                        <input className="input" type="number" min="0" step="0.01" value={compForm.largura}
                          onChange={e => setCompForm(f => ({ ...f, largura: Number(e.target.value) }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">Altura A (m)</span>
                        <input className="input" type="number" min="0" step="0.01" value={compForm.altura}
                          onChange={e => setCompForm(f => ({ ...f, altura: Number(e.target.value) }))} />
                      </label>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-3">
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">L (m)</span>
                        <input className="input" type="number" min="0" step="0.01" value={compForm.largura}
                          onChange={e => setCompForm(f => ({ ...f, largura: Number(e.target.value) }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">P (m)</span>
                        <input className="input" type="number" min="0" step="0.01" value={compForm.profundidade}
                          onChange={e => setCompForm(f => ({ ...f, profundidade: Number(e.target.value) }))} />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-xs text-muted">A (m)</span>
                        <input className="input" type="number" min="0" step="0.01" value={compForm.altura}
                          onChange={e => setCompForm(f => ({ ...f, altura: Number(e.target.value) }))} />
                      </label>
                    </div>
                  )}
                  <label className="flex flex-col gap-1 w-24">
                    <span className="text-xs text-muted">Quantidade</span>
                    <input className="input text-center" type="number" min="1" value={compForm.qty}
                      onChange={e => setCompForm(f => ({ ...f, qty: Math.max(1, Number(e.target.value)) }))} />
                  </label>

                  <div>
                    <span className="text-xs text-muted block mb-2">Opcionais do Componente</span>
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
                        <p className="col-span-full text-xs text-faint">Nenhum grupo de opcionais cadastrado. Crie grupos na aba Opcionais.</p>
                      )}
                    </div>
                    {compActiveCategories.length > 0 && (
                      <div className="space-y-2.5">
                        {compActiveCategories.map((cat) => (
                          <div key={cat} className="border border-line rounded-lg p-2.5 bg-[#fdfdfd]">
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
                                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-all"
                                    style={isSel ? { backgroundColor: `${color}20`, borderColor: color, color } : { backgroundColor: '#f8f6f2', borderColor: '#e8e0d6', color: '#6b5d55' }}
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
                      {editingCompIndex !== null ? 'Salvar Componente' : 'Adicionar Componente'}
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
                        Cancelar
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ) : form.is_set ? (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">Componentes do Conjunto</span>
                {(form.set_items ?? []).length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {(form.set_items ?? []).map((item, idx) => (
                      <div key={idx} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-line bg-[#fcfbfa]">
                        <span className="font-mono text-xs font-semibold text-gold flex-1">{item.product_code}</span>
                        <span className="text-xs text-muted">×{item.qty}</span>
                        <button
                          type="button"
                          onClick={() => setForm(prev => ({
                            ...prev,
                            set_items: (prev.set_items ?? []).filter((_, i) => i !== idx),
                          }))}
                          className="text-muted hover:text-red-500 transition-colors ml-1"
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
                    placeholder="Código do produto"
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
                <p className="text-[10px] text-faint mt-1.5">Código deve existir no catálogo. Conjuntos não podem conter outros conjuntos.</p>
              </div>
            ) : (
              <div>
                <span className="text-xs text-muted block mb-2 font-medium">Categorias de Opcionais Disponíveis</span>
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
                    <p className="col-span-full text-xs text-faint">Nenhum grupo de opcionais cadastrado. Crie grupos na aba Opcionais.</p>
                  )}
                </div>

                {activeCategories.length > 0 && (
                  <div className="space-y-3">
                    <span className="text-xs text-muted block font-medium">Cores e Permissões por Categoria</span>
                    {activeCategories.map((catValue) => {
                      const catValueLabel = catLabel(catValue)
                      const catItems = allOptionals.filter(o => o.category === catValue)
                      const isAllowed = allOptCats.has(catValue)
                      const selectedIds = (form.optional_ids ?? []).filter(id => catItems.some(o => o.id === id))
                      return (
                        <div key={catValue} className="border border-line rounded-xl p-3.5 space-y-2.5 bg-[#fdfdfd] shadow-sm">
                          <div className="flex items-center justify-between pb-1 border-b border-[#f3ede6]">
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
                              <span className="text-[11px] text-[#6b5d55]">Permitir todos</span>
                            </label>
                          </div>
                          {isAllowed ? (
                            <p className="text-[11px] text-muted italic">
                              Todos os opcionais desta categoria estarão disponíveis no carrinho.
                            </p>
                          ) : (
                            <div>
                              {catItems.length === 0 ? (
                                <span className="text-xs text-faint italic">Nenhuma cor cadastrada nesta categoria.</span>
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
                              <p className="text-[10px] text-faint mt-1">Ctrl+clique para selecionar múltiplas cores.</p>
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
              <span className="text-xs text-muted block mb-1">Foto</span>
              <div
                className="border-2 border-dashed border-line rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
              >
                {photoPreview ? <img src={photoPreview} alt="" className="w-24 h-24 object-cover rounded-lg" /> : <Upload className="w-8 h-8 text-faint" />}
                <span className="text-xs text-muted">{photoPreview ? 'Clique para trocar' : 'JPG, PNG, WEBP — máx. 5MB'}</span>
              </div>
              <input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.webp" className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]; if (!file) return
                  setPendingFile(file); setPhotoPreview(URL.createObjectURL(file))
                }} />
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }}
                disabled={createM.isPending || updateM.isPending || uploadM.isPending}>
                {editing ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete name={deleting.description}
          onConfirm={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)} />
      )}
    </div>
  )
}

// ── CLIENTES / REPRESENTANTES ─────────────────────────────────────────────────

const EMPTY_ADDRESS: ClientCreate = { name: '', phone: '', email: '', cep: '', numero: '', address: '', city: '', state: '', price_profile: 'lojista' }

function PeopleTab<T extends Client | Representative>({
  label, entityType, items, isLoading, onCreate, onUpdate, onDelete, isPending, color, page, onPage,
}: {
  label: string; entityType: 'client' | 'rep'
  items: T[] | undefined; isLoading: boolean
  onCreate: (data: ClientCreate) => Promise<void>; onUpdate: (id: string, data: Partial<ClientCreate>) => Promise<void>
  onDelete: (id: string) => Promise<void>; isPending: boolean; color: string
  page: number; onPage: (p: number) => void
}) {
  const { user: authUser } = useAuth()
  const isAdmin = authUser?.role === 'admin'
  const isRep = authUser?.role === 'representante'
  const canEditDiscount = authUser?.role === 'admin' || authUser?.role === 'cadastros' || authUser?.role === 'produtos'
  const defaultMaxDiscount = entityType === 'client' ? 0 : 15

  const { sorted, sortKey, sortDir, toggle } = useSortedList<T>(items, 'name' as keyof T)
  const [search, setSearch] = useState('')
  const filtered = sorted.filter((item) =>
    `${item.name} ${item.email} ${item.phone}`.toLowerCase().includes(search.toLowerCase())
  )
  const { pageItems, totalPages, safePage } = paginate(filtered, page)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<T | null>(null)
  const [deleting, setDeleting] = useState<T | null>(null)
  const [viewing, setViewing] = useState<T | null>(null)
  const [createdUser, setCreatedUser] = useState<UserCreateResponse | null>(null)
  const [createUserError, setCreateUserError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<ClientCreate>(EMPTY_ADDRESS)

  const createFromClient = useCreateUserFromClient()
  const createFromRep = useCreateUserFromRep()

  function openCreate() { setForm(EMPTY_ADDRESS); setEditing(null); setFormError(null); setShowForm(true) }
  function openEdit(item: T) {
    setForm({ name: item.name, phone: item.phone, email: item.email, cep: item.cep, numero: item.numero ?? '', address: item.address, city: item.city, state: item.state, price_profile: (item as Client).price_profile ?? 'lojista', max_discount: item.max_discount })
    setEditing(item); setFormError(null); setShowForm(true)
  }
  function openView(item: T) {
    setViewing(item); setCreatedUser(null); setCreateUserError(null)
  }
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    // Normaliza campos antes de enviar — evita 422 por espaços ou UF vazia/minúscula
    const cleaned: ClientCreate = {
      ...form,
      name: form.name.trim(),
      email: form.email.trim(),
      city: form.city.trim(),
      address: form.address.trim(),
      state: form.state.trim().toUpperCase(),
      numero: form.numero?.trim() || null,
    }
    if (cleaned.state.length !== 2) {
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
      setCreateUserError(detail ?? 'Erro ao criar usuário.')
    }
  }

  const thProps = { sortKey: String(sortKey), sortDir, onSort: (k: string) => toggle(k as keyof T), color }
  const createUserPending = entityType === 'client' ? createFromClient.isPending : createFromRep.isPending

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <span className="text-sm text-muted whitespace-nowrap">{items?.length ?? 0} {label.toLowerCase()} cadastrados</span>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-3" />
            <input className="input pl-9" placeholder="Buscar por nome, e-mail ou telefone..." value={search} onChange={(e) => { setSearch(e.target.value); onPage(1) }} />
          </div>
          <button className="btn-primary flex items-center gap-2 flex-shrink-0" style={{ backgroundColor: color }} onClick={openCreate}>
            <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Novo </span>{label.slice(0, -1)}
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">Carregando...</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="md:hidden flex flex-col gap-3">
            {pageItems.map((item) => (
              <div key={item.id} className="bg-[#fcfbfa] border border-line rounded-xl p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink">{item.name}</p>
                    <p className="text-xs text-muted mt-0.5">{item.city} / {item.state}</p>
                  </div>
                  <div className="flex gap-0 flex-shrink-0">
                    <button onClick={() => openView(item)} aria-label="Visualizar" className="w-9 h-9 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Eye className="w-4 h-4" />
                    </button>
                    <button onClick={() => openEdit(item)} aria-label="Editar" className="w-9 h-9 flex items-center justify-center text-muted active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Pencil className="w-4 h-4" />
                    </button>
                    {!(isRep && entityType === 'client') && (
                      <button onClick={() => setDeleting(item)} aria-label="Excluir" className="w-9 h-9 flex items-center justify-center text-muted active:text-red-500 transition-colors" style={{ touchAction: 'manipulation' }}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 space-y-0.5 text-xs text-ink-2">
                  <p>{item.phone}</p>
                  <p className="truncate text-muted-2">{item.email}</p>
                </div>
              </div>
            ))}
            {filtered.length === 0 && <p className="text-center text-muted text-sm py-8">{search ? 'Nenhum registro encontrado com este filtro.' : 'Nenhum registro encontrado.'}</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden md:block overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead style={{ backgroundColor: `${color}12` }}>
                <tr>
                  <Th label="Nome" col="name" {...thProps} />
                  <Th label="Telefone" col="phone" {...thProps} />
                  <Th label="E-mail" col="email" {...thProps} />
                  <Th label="Cidade" col="city" {...thProps} />
                  <Th label="UF" col="state" {...thProps} />
                  <Th label="Desc. Máx." col="max_discount" {...thProps} />
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((item) => (
                  <tr key={item.id} className="table-row">
                    <td className="px-4 py-3 text-ink font-medium">{item.name}</td>
                    <td className="px-4 py-3 text-ink-2">{item.phone}</td>
                    <td className="px-4 py-3 text-ink-2">{item.email}</td>
                    <td className="px-4 py-3 text-ink-2">{item.city}</td>
                    <td className="px-4 py-3 text-muted-2">{item.state}</td>
                    <td className="px-4 py-3 text-muted-2">{item.max_discount}%</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openView(item)} title="Visualizar" aria-label="Visualizar" className="text-muted transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Eye className="w-4 h-4" /></button>
                        <button onClick={() => openEdit(item)} title="Editar" aria-label="Editar" className="text-muted transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Pencil className="w-4 h-4" /></button>
                        {!(isRep && entityType === 'client') && (
                          <button onClick={() => setDeleting(item)} title="Excluir" aria-label="Excluir" className="text-muted hover:text-red-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-muted">{search ? 'Nenhum registro encontrado com este filtro.' : 'Nenhum registro encontrado.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </>
      )}

      {/* View / Create User modal */}
      {viewing && (
        <Modal title={`Detalhes — ${viewing.name}`} onClose={() => setViewing(null)} accentColor={color}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div><span className="text-xs text-muted block">Nome</span><span className="text-ink font-medium">{viewing.name}</span></div>
              <div><span className="text-xs text-muted block">Telefone</span><span className="text-ink-2">{viewing.phone}</span></div>
              <div className="col-span-2"><span className="text-xs text-muted block">E-mail</span><span className="text-ink-2">{viewing.email}</span></div>
              <div><span className="text-xs text-muted block">Cidade</span><span className="text-ink-2">{viewing.city}</span></div>
              <div><span className="text-xs text-muted block">Estado</span><span className="text-ink-2">{viewing.state}</span></div>
              <div className="col-span-2"><span className="text-xs text-muted block">Endereço</span><span className="text-ink-2">{viewing.address}{viewing.numero ? `, ${viewing.numero}` : ''} — CEP {viewing.cep}</span></div>
            </div>

            {(isAdmin || (isRep && entityType === 'client')) && <div className="border-t border-line pt-4">
              <p className="text-xs font-semibold text-muted-2 uppercase tracking-wider mb-3">Acesso ao Sistema</p>

              {createdUser ? (
                <div className="bg-[#f0f7f0] border border-[#c5dfc4] rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2 text-[#4a7a47]">
                    <CheckCircle className="w-5 h-5 flex-shrink-0" />
                    <span className="text-sm font-semibold">Usuário criado com sucesso!</span>
                  </div>
                  <div className="text-sm text-ink-2 space-y-1">
                    <p><span className="text-muted">Usuário:</span> <strong>{createdUser.username}</strong></p>
                    <p><span className="text-muted">Senha inicial:</span> <strong>{createdUser.temp_password}</strong></p>
                    <p><span className="text-muted">Perfil:</span> {createdUser.role === 'representante' ? 'Representante' : 'Vendedor'}</p>
                  </div>
                  <p className="text-xs text-muted-2 mt-1">O usuário deverá trocar a senha no primeiro acesso.</p>
                </div>
              ) : viewing?.has_user ? (
                <div className="flex items-center gap-3">
                  <button
                    disabled
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white opacity-50 cursor-not-allowed"
                    style={{ backgroundColor: color }}
                  >
                    <CheckCircle className="w-4 h-4" />
                    Usuário já criado
                  </button>
                  <span className="text-xs text-muted">Gerencie pela tela Admin.</span>
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
                    {createUserPending ? 'Criando…' : 'Criar Usuário'}
                  </button>
                  <p className="text-xs text-muted mt-2">
                    Cria acesso com usuário gerado pelo nome e senha temporária aleatória.
                  </p>
                </>
              )}
            </div>}

            <div className="flex justify-end pt-1">
              <button className="btn-secondary" onClick={() => setViewing(null)}>Fechar</button>
            </div>
          </div>
        </Modal>
      )}

      {showForm && (
        <Modal title={editing ? `Editar ${label.slice(0, -1)}` : `Novo ${label.slice(0, -1)}`} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <AddressFields form={form} setForm={setForm} />
            {entityType === 'client' && (
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-muted">Perfil de faturamento *</span>
                <div className="flex gap-2">
                  {(['lojista', 'corporativo'] as const).map((profile) => (
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
                <span className="text-xs text-muted">Desconto Máximo (%)</span>
                <input
                  type="number" min={0} max={100} step={0.5} className="input"
                  value={form.max_discount ?? defaultMaxDiscount}
                  onChange={(e) => setForm({ ...form, max_discount: e.target.value === '' ? undefined : Number(e.target.value) })}
                />
              </div>
            )}
            {formError && (
              <div className="flex items-start gap-2 bg-[#fef3f2] border border-red-200 rounded-lg px-3 py-2.5">
                <X className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <span className="text-xs text-red-700 leading-snug">{formError}</span>
              </div>
            )}
            <p className="text-[10px] text-[#b8b0a6] leading-relaxed pt-1">
              Os dados coletados neste formulário são processados estritamente para a elaboração de orçamentos e gestão do pedido, conforme a nossa Política de Privacidade.
            </p>
            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }} disabled={isPending || submitting}>
                {submitting ? 'Salvando...' : editing ? 'Salvar' : 'Criar'}
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
      setGroupErr('Código já existe ou dados inválidos.')
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
        <span className="text-sm text-muted">{optionals?.length ?? 0} opcionais cadastrados</span>
        {!readOnly && (
          <div className="flex items-center gap-2">
            <button className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-1.5" onClick={openNewGroup}>
              <Plus className="w-3.5 h-3.5" /> Adicionar Grupos
            </button>
            <button className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: color }} onClick={openCreate} disabled={categories.length === 0}
              title={categories.length === 0 ? 'Crie um grupo primeiro' : undefined}>
              <Plus className="w-4 h-4" /> Novo Opcional
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <p className="text-muted text-sm py-8 text-center">Carregando...</p>
      ) : (
        <div className="space-y-4">
          {grouped.map(({ category, label, items, cat }) => (
            <div key={category} className={`rounded-xl border overflow-hidden ${cat ? 'border-line' : 'border-dashed border-[#e0b88a]'}`}>
              <div className="px-4 py-2 flex items-center justify-between gap-2"
                style={{ backgroundColor: cat ? `${color}12` : '#fdf6ec' }}>
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-wider truncate" style={{ color: cat ? color : '#a3690f' }}>
                    {label}
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: cat ? `${color}20` : '#f3ddb8', color: cat ? color : '#a3690f' }}>
                    {items.length}
                  </span>
                  {!cat && <span className="text-[10px] text-[#a3690f] italic truncate">grupo não cadastrado</span>}
                </div>
                {!readOnly && (
                  <div className="flex gap-2 flex-shrink-0">
                    {cat ? (
                      <>
                        <button onClick={() => openEditGroup(cat)} className="text-muted transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')} title="Editar grupo">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => setDeletingGroup({ id: cat.id, name: cat.name, count: items.length })}
                          className="text-muted hover:text-red-500 transition-colors" title="Excluir grupo">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => { setEditingGroup(null); setGroupForm({ name: label, code: category }); setGroupErr(''); setShowGroupForm(true) }}
                        className="text-[10px] font-semibold px-2 py-1 rounded-lg border border-[#e0b88a] text-[#a3690f] hover:bg-[#fdf6ec] transition-colors"
                      >
                        Cadastrar grupo
                      </button>
                    )}
                  </div>
                )}
              </div>
              {items.length === 0 ? (
                <p className="px-4 py-3 text-xs text-faint">Nenhuma cor cadastrada.</p>
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
                            <button onClick={() => openEdit(opt)} aria-label="Editar" className="text-muted transition-colors"
                              onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                              onMouseLeave={(e) => (e.currentTarget.style.color = '')}>
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setDeleting(opt)} aria-label="Excluir" className="text-muted hover:text-red-500 transition-colors">
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
            <p className="text-muted text-sm py-8 text-center">Nenhum grupo cadastrado. Clique em "Adicionar Grupos" para começar.</p>
          )}
        </div>
      )}

      {/* Lightbox */}
      {lightboxUrl && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setLightboxUrl(null)}>
          <div className="relative" onClick={(e) => e.stopPropagation()}>
            <img src={lightboxUrl} alt="Swatch ampliado"
              className="max-w-[90vw] max-h-[80vh] w-64 h-64 object-cover rounded-2xl shadow-2xl border border-white/20" />
            <button onClick={() => setLightboxUrl(null)}
              className="absolute -top-3 -right-3 w-8 h-8 flex items-center justify-center bg-white rounded-full shadow-lg text-ink hover:bg-bg transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Optional form modal */}
      {showForm && (
        <Modal title={editing ? 'Editar Opcional' : 'Novo Opcional'} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Categoria *</span>
              <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
                {catOptions.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Nome da Cor *</span>
              <input className="input" value={form.color_name}
                onChange={(e) => setForm({ ...form, color_name: e.target.value })} required />
            </label>

            <div>
              <span className="text-xs text-muted block mb-1">Imagem de Textura (swatch)</span>
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
                  {optPhotoPreview ? 'Clique para trocar' : 'PNG, JPG — textura do material'}
                </span>
              </div>
              <input ref={optFileRef} type="file" accept=".jpg,.jpeg,.png,.webp" className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]; if (!f) return
                  setPendingOptFile(f); setOptPhotoPreview(URL.createObjectURL(f))
                }} />
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }}
                disabled={createM.isPending || updateM.isPending || uploadOptM.isPending}>
                {editing ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Group form modal */}
      {showGroupForm && (
        <Modal title={editingGroup ? 'Editar Grupo' : 'Novo Grupo de Opcionais'} onClose={() => setShowGroupForm(false)} accentColor={color}>
          <form onSubmit={handleGroupSubmit} className="space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Nome do Grupo *</span>
              <input className="input" value={groupForm.name} onChange={(e) => setGroupForm(f => ({ ...f, name: e.target.value }))} required autoFocus placeholder="ex: Alumínio" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Código (identificador único) *</span>
              <input className="input font-mono text-sm" value={groupForm.code} onChange={(e) => setGroupForm(f => ({ ...f, code: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} required placeholder="ex: aluminio" />
              <span className="text-[10px] text-faint">Apenas letras minúsculas, números e underscores.</span>
            </label>
            {groupErr && <p className="text-xs text-red-500">{groupErr}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={createCatM.isPending || updateCatM.isPending} className="btn-primary flex-1" style={{ backgroundColor: color }}>
                {createCatM.isPending || updateCatM.isPending ? 'Salvando...' : editingGroup ? 'Salvar' : 'Criar Grupo'}
              </button>
              <button type="button" className="btn-secondary px-4" onClick={() => setShowGroupForm(false)}>Cancelar</button>
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
        <ConfirmDelete name={deletingGroup.count > 0 ? `${deletingGroup.name} (${deletingGroup.count} ${deletingGroup.count === 1 ? 'cor' : 'cores'})` : deletingGroup.name}
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
  | { kind: 'new-type'; groupId: string }
  | { kind: 'edit-type'; type: ProductType }

function GroupsTab({ color, page, onPage }: { color: string; page: number; onPage: (p: number) => void }) {
  const { data: groups = [], isLoading: groupsLoading } = useProductGroups()
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

  function openNewGroup() { setGName(''); setGIpi('0.00'); setErr(''); setModal({ kind: 'new-group' }) }
  function openEditGroup(g: ProductGroup) { setGName(g.name); setGIpi(Number(g.ipi).toFixed(2)); setErr(''); setModal({ kind: 'edit-group', group: g }) }
  function openNewType(groupId: string) { setTName(''); setTGroupId(groupId); setErr(''); setModal({ kind: 'new-type', groupId }) }
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
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro ao salvar grupo.')
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
      setErr((ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro ao salvar subgrupo.')
    }
  }

  const isGroupPending = createGroupM.isPending || updateGroupM.isPending
  const isTypePending = createTypeM.isPending || updateTypeM.isPending
  const isLoading = groupsLoading || typesLoading

  const orphanTypes = types.filter(t => !t.group_id)
  const { pageItems: pagedGroups, totalPages, safePage } = paginate(groups, page)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink">Grupos & Subgrupos</h2>
        <button onClick={openNewGroup}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors"
          style={{ backgroundColor: color }}>
          <Plus className="w-3.5 h-3.5" /> Novo Grupo
        </button>
      </div>

      {/* Group form modal */}
      {(modal?.kind === 'new-group' || modal?.kind === 'edit-group') && (
        <Modal
          title={modal.kind === 'edit-group' ? 'Editar Grupo' : 'Novo Grupo'}
          onClose={() => setModal(null)}
          accentColor={color}
        >
          <form onSubmit={handleGroupSubmit} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Nome do Grupo *</span>
              <input className="input" value={gName} onChange={(e) => setGName(e.target.value)} required autoFocus />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Alíquota IPI (%)</span>
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
            {err && <p className="text-xs text-red-500">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={isGroupPending} className="btn-primary flex-1">
                {isGroupPending ? 'Salvando...' : modal.kind === 'edit-group' ? 'Salvar Alterações' : 'Criar Grupo'}
              </button>
              <button type="button" onClick={() => setModal(null)} className="btn-secondary px-4">Cancelar</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Type form modal */}
      {(modal?.kind === 'new-type' || modal?.kind === 'edit-type') && (
        <Modal
          title={modal.kind === 'edit-type' ? 'Editar Subgrupo' : 'Novo Subgrupo'}
          onClose={() => setModal(null)}
          accentColor={color}
        >
          <form onSubmit={handleTypeSubmit} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Nome do Subgrupo *</span>
              <input className="input" value={tName} onChange={(e) => setTName(e.target.value)} required autoFocus />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Grupo</span>
              <select className="input" value={tGroupId ?? ''} onChange={(e) => setTGroupId(e.target.value || null)}>
                <option value="">Sem grupo</option>
                {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </label>
            {err && <p className="text-xs text-red-500">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={isTypePending} className="btn-primary flex-1">
                {isTypePending ? 'Salvando...' : modal.kind === 'edit-type' ? 'Salvar Alterações' : 'Criar Subgrupo'}
              </button>
              <button type="button" onClick={() => setModal(null)} className="btn-secondary px-4">Cancelar</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Delete confirmations */}
      {deletingGroup && (
        <ConfirmDelete name={deletingGroup.name}
          onConfirm={async () => { await deleteGroupM.mutateAsync(deletingGroup.id); setDeletingGroup(null) }}
          onCancel={() => setDeletingGroup(null)} />
      )}
      {deletingType && (
        <ConfirmDelete name={deletingType.name}
          onConfirm={async () => { await deleteTypeM.mutateAsync(deletingType.id); setDeletingType(null) }}
          onCancel={() => setDeletingType(null)} />
      )}

      {isLoading ? (
        <p className="text-sm text-muted">Carregando...</p>
      ) : (
        <div className="space-y-3">
          {pagedGroups.map(group => {
            const groupTypes = types.filter(t => t.group_id === group.id)
            return (
              <div key={group.id} className="border border-line rounded-xl p-4 bg-white space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="font-semibold text-sm text-ink">{group.name}</span>
                    {Number(group.ipi) > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#fdf6ec] text-gold border border-[#e8d8b8]">
                        IPI {Number(group.ipi).toFixed(2).replace('.', ',')}%
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => openEditGroup(group)} className="p-1 text-muted hover:text-gold transition-colors">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setDeletingGroup(group)} className="p-1 text-muted hover:text-red-500 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {groupTypes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {groupTypes.map(t => (
                      <div key={t.id}
                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-line bg-bg text-xs text-ink">
                        <span>{t.name}</span>
                        <button onClick={() => openEditType(t)} className="text-muted hover:text-gold transition-colors">
                          <Pencil className="w-2.5 h-2.5" />
                        </button>
                        <button onClick={() => setDeletingType(t)} className="text-muted hover:text-red-500 transition-colors">
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => openNewType(group.id)}
                  className="flex items-center gap-1 text-xs font-medium transition-colors"
                  style={{ color }}
                >
                  <Plus className="w-3 h-3" /> Novo Subgrupo
                </button>
              </div>
            )
          })}

          {groups.length === 0 && orphanTypes.length === 0 && (
            <p className="text-sm text-muted">Nenhum grupo cadastrado. Crie um grupo para organizar os tipos de produto.</p>
          )}

          {orphanTypes.length > 0 && (
            <div className="border border-dashed border-line rounded-xl p-4 space-y-3">
              <span className="text-xs font-semibold text-muted uppercase tracking-wider">Sem grupo</span>
              <div className="flex flex-wrap gap-1.5">
                {orphanTypes.map(t => (
                  <div key={t.id}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-line bg-white text-xs text-ink">
                    <span>{t.name}</span>
                    <button onClick={() => openEditType(t)} className="text-muted hover:text-gold transition-colors">
                      <Pencil className="w-2.5 h-2.5" />
                    </button>
                    <button onClick={() => setDeletingType(t)} className="text-muted hover:text-red-500 transition-colors">
                      <Trash2 className="w-2.5 h-2.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Pagination page={safePage} totalPages={totalPages} onPage={onPage} color={color} />
        </div>
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
  { value: 'optionals',       label: 'Opcionais',          columns: 'category, color_name' },
  { value: 'representatives', label: 'Representantes',      columns: 'name, phone, email, cep, numero, address, city, state' },
  { value: 'clients',         label: 'Clientes',           columns: 'name, phone, email, cep, numero, address, city, state, price_profile, rep_email' },
]

function ImportUploader({ endpoint, label, hint, columns, color }: {
  endpoint: string; label: string; hint?: string; columns: string; color: string
}) {
  const queryClient = useQueryClient()
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
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Falha ao processar o arquivo. Verifique o formato do CSV.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-line bg-[#fcfbfa] p-4">
      <p className="text-sm font-semibold text-ink">{label}</p>
      {hint && <p className="text-xs text-ink-3 mt-0.5">{hint}</p>}
      <p className="text-[11px] text-muted mt-1">Colunas: <span className="font-mono text-ink-3">{columns}</span></p>
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        <input
          type="file" accept=".csv,text/csv"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null) }}
          className="text-xs text-ink-2 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-bg-2 file:text-ink-2 file:cursor-pointer"
        />
        <button
          onClick={handleUpload} disabled={!file || loading}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-50"
          style={{ backgroundColor: color }}
        >
          <Upload className="w-3.5 h-3.5" /> {loading ? 'Enviando...' : 'Importar'}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 mt-3">{error}</p>}
      {result && (
        <div className={`mt-3 rounded-lg border p-3 ${result.committed ? 'border-green-200 bg-green-50/40' : 'border-red-200 bg-red-50/40'}`}>
          {result.committed ? (
            <p className="text-xs text-ink">
              ✓ <span className="font-semibold">{result.processed}</span> linhas processadas ·{' '}
              <span className="text-green-700 font-semibold">{result.created}</span> criadas ·{' '}
              <span className="text-gold font-semibold">{result.updated}</span> atualizadas
            </p>
          ) : (
            <p className="text-xs text-red-700 font-semibold">
              Arquivo rejeitado — nada foi importado. Corrija {result.errors.length} {result.errors.length === 1 ? 'erro' : 'erros'} em {result.processed} linhas e reenvie.
            </p>
          )}
          {result.errors.length > 0 && (
            <ul className="mt-2 max-h-40 overflow-y-auto space-y-1">
              {result.errors.map((err, i) => (
                <li key={i} className="text-[11px] text-red-600">Linha {err.row}: {err.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function ImportTab({ color }: { color: string }) {
  const [supportTable, setSupportTable] = useState('product-groups')
  const current = SUPPORT_TABLES.find((t) => t.value === supportTable)!
  const { data: products = [] } = useProducts()
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-ink">Importação CSV</h2>
        <p className="text-sm text-ink-3 mt-0.5">Importe cadastros em massa via arquivos .csv (UTF-8; separador vírgula ou ponto-e-vírgula). Reimportações atualizam registros existentes pela chave (nome, SKU ou e-mail).</p>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2"><LayoutGrid className="w-4 h-4" style={{ color }} /> Cadastros de apoio</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">Tabela:</span>
          <select value={supportTable} onChange={(e) => setSupportTable(e.target.value)} className="input text-sm max-w-[240px]">
            {SUPPORT_TABLES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <ImportUploader key={supportTable} endpoint={supportTable} label={current.label} columns={current.columns} color={color} />
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-ink flex items-center gap-2"><Package className="w-4 h-4" style={{ color }} /> Catálogo de produtos — 2 etapas</h3>
        <ImportUploader endpoint="products" label="Etapa 1: Subir Tabela de Produtos" hint="Cria/atualiza produtos pelo SKU (product_code)." columns="product_code, description, type, is_circular, altura, largura, profundidade, price_lojista, price_corporativo, observacao" color={color} />
        <ImportUploader endpoint="product-optionals" label="Etapa 2: Subir Tabela de Opcionais do Produto" hint="Vincula opcionais a cada SKU — rode após a Etapa 1." columns="product_code, category, color_name" color={color} />
      </section>

      <section className="space-y-3">
        <p className="text-xs text-ink-3 -mt-1">Selecione a pasta com as fotos — o nome de cada arquivo deve ser o código do produto (ex.: IML0001.png); a foto é associada automaticamente ao produto correspondente.</p>
        <BatchPhotoUpload products={products} color={color} title="Importar Foto" collapsible={false} />
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
  const isRep = user?.role === 'representante'
  const isCliente = user?.role === 'vendedor' && !!user.linked_id
  const isLimited = isRep || isCliente

  const visibleTabs = TAB_CONFIG.filter(t => {
    if (isCliente) return t.key === 'opcionais'
    if (isRep) return t.key === 'clientes' || t.key === 'opcionais'
    return true
  })

  const defaultTab: Tab = isCliente ? 'opcionais' : isRep ? 'clientes' : 'produtos'

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

  const { data: products } = useProducts()
  const { data: clients }  = useClients()
  const { data: reps }     = useRepresentatives()
  const { data: optionals } = useOptionals()
  const { data: productGroups } = useProductGroups()

  const { data: clientsData, isLoading: clientsLoading } = useClients()
  const createClient = useCreateClient(); const updateClient = useUpdateClient(); const deleteClient = useDeleteClient()

  const { data: repsData, isLoading: repsLoading } = useRepresentatives()
  const createRep = useCreateRepresentative(); const updateRep = useUpdateRepresentative(); const deleteRep = useDeleteRepresentative()

  const counts: Record<Tab, number> = {
    produtos:       products?.length ?? 0,
    clientes:       clients?.length  ?? 0,
    representantes: reps?.length     ?? 0,
    opcionais:      optionals?.length ?? 0,
    tipos:          productGroups?.length ?? 0,
    importacao:     0,
  }

  const activeColor = TAB_PALETTE[tab].color

  return (
    <div className="min-h-screen bg-bg text-ink pb-24 md:pb-0">
      <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 md:py-6">

        {/* ── Mobile horizontal tab bar ──────────────────────── */}
        <div className="md:hidden mb-3 flex gap-2 overflow-x-auto pb-1 -mx-4 px-4">
          {visibleTabs.map(({ key, label, Icon }) => {
            const { color } = TAB_PALETTE[key]
            const isActive = tab === key
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                className="flex-shrink-0 flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold border transition-all active:scale-[0.97] active:opacity-80"
                style={isActive
                  ? { backgroundColor: color, color: 'white', borderColor: color, touchAction: 'manipulation' }
                  : { backgroundColor: 'white', color: '#6b5d55', borderColor: '#e8e0d6', touchAction: 'manipulation' }
                }
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
                <span
                  className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
                  style={isActive
                    ? { backgroundColor: 'rgba(255,255,255,0.3)', color: 'white' }
                    : { backgroundColor: '#f0ece6', color: '#9d8d81' }
                  }
                >
                  {counts[key]}
                </span>
              </button>
            )
          })}
        </div>

        <div className="flex flex-col gap-4 md:grid md:gap-6" style={{ gridTemplateColumns: '220px 1fr' }}>

          {/* ── Sidebar (desktop only) ──────────────────────────── */}
          <aside className="hidden md:block">
            <div className="bg-white border border-line rounded-xl shadow-sm p-3 sticky top-20 space-y-1">
              <p className="text-[10px] font-semibold text-faint uppercase tracking-widest px-3 pb-2">Cadastros</p>
              {visibleTabs.map(({ key, label, Icon }) => {
                const { color } = TAB_PALETTE[key]
                const isActive = tab === key
                const count = counts[key]
                return (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-left"
                    style={isActive
                      ? { backgroundColor: `${color}12`, color, borderLeft: `3px solid ${color}`, paddingLeft: '9px' }
                      : { borderLeft: '3px solid transparent', paddingLeft: '9px' }
                    }
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = '#f8f6f2' }}
                    onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.backgroundColor = '' }}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" style={isActive ? { color } : { color: '#9d8d81' }} />
                    <span className="flex-1" style={isActive ? {} : { color: '#6b5d55' }}>{label}</span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-full font-semibold min-w-[22px] text-center"
                      style={isActive
                        ? { backgroundColor: `${color}20`, color }
                        : { backgroundColor: '#f0ece6', color: '#9d8d81' }}
                    >
                      {count}
                    </span>
                  </button>
                )
              })}
            </div>
          </aside>

          {/* ── Painel de Dados ───────────────────────────────────── */}
          <main className="bg-white border border-line rounded-xl shadow-sm p-6"
            style={{ borderTop: `3px solid ${activeColor}` }}>
            {tab === 'produtos' && <ProductsTab color={TAB_PALETTE.produtos.color} page={productPage} onPage={setProductPage} />}

            {tab === 'clientes' && (
              <PeopleTab
                label="Clientes"
                entityType="client"
                items={clientsData}
                isLoading={clientsLoading}
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
                items={repsData}
                isLoading={repsLoading}
                isPending={createRep.isPending || updateRep.isPending}
                color={TAB_PALETTE.representantes.color}
                onCreate={async (data) => { await createRep.mutateAsync(data) }}
                onUpdate={async (id, data) => { await updateRep.mutateAsync({ id, data }) }}
                onDelete={async (id) => { await deleteRep.mutateAsync(id) }}
                page={repPage} onPage={setRepPage}
              />
            )}

            {tab === 'opcionais' && <OptionaisTab color={TAB_PALETTE.opcionais.color} readOnly={isLimited} />}

            {tab === 'tipos' && <GroupsTab color={TAB_PALETTE.tipos.color} page={groupPage} onPage={setGroupPage} />}

            {tab === 'importacao' && <ImportTab color={TAB_PALETTE.importacao.color} />}
          </main>
        </div>
      </div>
    </div>
  )
}
