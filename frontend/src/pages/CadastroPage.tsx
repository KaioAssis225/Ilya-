import { useState, useRef } from 'react'
import api from '../lib/api'
import { ChevronUp, ChevronDown, Pencil, Trash2, Plus, X, Upload, ImageIcon, Package, Users, UserCheck, Tag, Eye, UserPlus, CheckCircle, LayoutGrid } from 'lucide-react'
import { useProducts, useCreateProduct, useUpdateProduct, useDeleteProduct, useUploadProductPhoto } from '../hooks/useProducts'
import { useClients, useCreateClient, useUpdateClient, useDeleteClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative, useUpdateRepresentative, useDeleteRepresentative } from '../hooks/useRepresentatives'
import { useOptionals, useCreateOptional, useUpdateOptional, useDeleteOptional, useUploadOptionalPhoto } from '../hooks/useOptionals'
import { useProductTypes, useCreateProductType, useUpdateProductType, useDeleteProductType } from '../hooks/useProductTypes'
import { useOptionalCategories, useCreateOptionalCategory, useUpdateOptionalCategory, useDeleteOptionalCategory } from '../hooks/useOptionalCategories'
import { useCreateUserFromClient, useCreateUserFromRep } from '../hooks/useUsers'
import type { UserCreateResponse } from '../hooks/useUsers'
import { useAuth } from '../hooks/useAuth'
import type { Product, ProductCreate, Client, ClientCreate, Representative, ViaCepResponse, OptionalColor, OptionalColorCreate } from '../types'

type Tab = 'produtos' | 'clientes' | 'representantes' | 'opcionais' | 'tipos'
type SortDir = 'asc' | 'desc'

const ESTADOS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
  'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
]

const CATEGORY_OPTIONS = [
  { value: 'aluminio',       label: 'Alumínio' },
  { value: 'tecido_faixa_1', label: 'Tecido Faixa 1' },
  { value: 'tecido_faixa_2', label: 'Tecido Faixa 2' },
  { value: 'corda',          label: 'Corda' },
  { value: 'madeira_teka',   label: 'Madeira Teka' },
  { value: 'madeira_freijo', label: 'Madeira Freijó' },
  { value: 'couro_soleta',   label: 'Couro Soleta' },
  { value: 'couro_pele',     label: 'Couro Pele' },
]

const CATEGORY_LABEL: Record<string, string> = Object.fromEntries(
  CATEGORY_OPTIONS.map(({ value, label }) => [value, label])
)

const TAB_PALETTE = {
  produtos:        { color: '#b25e50', label: 'Terracota' },
  clientes:        { color: '#648261', label: 'Verde Oliva' },
  representantes:  { color: '#507a9b', label: 'Azul Mineral' },
  opcionais:       { color: '#c47e4a', label: 'Âmbar' },
  tipos:           { color: '#7a5c9b', label: 'Violeta' },
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
      className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase tracking-wider cursor-pointer select-none transition-colors"
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

async function fetchCep(cep: string): Promise<ViaCepResponse | null> {
  const clean = cep.replace(/\D/g, '')
  if (clean.length !== 8) return null
  try {
    const r = await api.get<ViaCepResponse>(`/utils/cep/${clean}`)
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

  async function handleCepBlur() {
    setCepLoading(true)
    const data = await fetchCep(form.cep)
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
        <span className="text-xs text-[#9d8d81]">Nome *</span>
        <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-[#9d8d81]">Telefone *</span>
        <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: formatPhone(e.target.value) })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-[#9d8d81]">E-mail *</span>
        <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1 relative">
        <span className="text-xs text-[#9d8d81]">CEP *</span>
        <input className="input pr-8" value={form.cep} onChange={(e) => setForm({ ...form, cep: formatCep(e.target.value) })} onBlur={handleCepBlur} maxLength={9} required />
        {cepLoading && <span className="absolute right-2 bottom-2 text-xs text-[#8b6914] animate-pulse">...</span>}
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-[#9d8d81]">Número</span>
        <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: formatOnlyNumbers(e.target.value) })} />
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
        <span className="text-xs text-[#9d8d81]">Estado *</span>
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
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e0d6]"
          style={accentColor ? { borderLeftColor: accentColor, borderLeftWidth: 3 } : {}}>
          <h3 className="text-base font-semibold text-[#2c2420]">{title}</h3>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420] transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 max-h-[80vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

function ConfirmDelete({ name, onConfirm, onCancel }: { name: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Modal title="Confirmar exclusão" onClose={onCancel}>
      <p className="text-[#4a3f38] mb-6">Excluir <span className="text-[#2c2420] font-medium">"{name}"</span>? Esta ação não pode ser desfeita.</p>
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
  altura: 0, largura: 0, profundidade: 0, price: 0, optional_ids: [],
}

function groupOptionalsByCategory(optionals: OptionalColor[]): { category: string; label: string; items: OptionalColor[] }[] {
  const map = new Map<string, OptionalColor[]>()
  for (const opt of optionals) {
    if (!map.has(opt.category)) map.set(opt.category, [])
    map.get(opt.category)!.push(opt)
  }
  return Array.from(map.entries()).map(([category, items]) => ({
    category,
    label: CATEGORY_LABEL[category] || category,
    items,
  }))
}

function groupOptionalsByCategoryDynamic(optionals: OptionalColor[], catLabel: (code: string) => string): { category: string; label: string; items: OptionalColor[] }[] {
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

function ProductsTab({ color }: { color: string }) {
  const { data: products, isLoading } = useProducts()
  const { data: allOptionals = [] } = useOptionals()
  const { data: allTypes = [] } = useProductTypes()
  const createM = useCreateProduct()
  const updateM = useUpdateProduct()
  const deleteM = useDeleteProduct()
  const uploadM = useUploadProductPhoto()
  const createTypeM = useCreateProductType()

  const { sorted, sortKey, sortDir, toggle } = useSortedList<Product>(products, 'product_code')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)
  const [deleting, setDeleting] = useState<Product | null>(null)
  const [form, setForm] = useState<ProductCreate>(EMPTY_PRODUCT)
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [showNewTypeModal, setShowNewTypeModal] = useState(false)
  const [newTypeName, setNewTypeName] = useState('')
  const [newTypeErr, setNewTypeErr] = useState('')

  function openCreate() {
    setForm(EMPTY_PRODUCT); setEditing(null)
    setActiveCategories([]); setPhotoPreview(null); setPendingFile(null); setShowForm(true)
  }
  function openEdit(p: Product) {
    const cats = Array.from(new Set(p.optionals.map((o) => o.category)))
    setActiveCategories(cats)
    setForm({
      product_code: p.product_code,
      description: p.description,
      type: p.type ?? 'Outro',
      is_circular: p.is_circular,
      altura: p.altura,
      largura: p.largura,
      profundidade: p.profundidade,
      price: p.price ?? 0,
      optional_ids: p.optionals.map((o) => o.id),
    })
    setPhotoPreview(p.photo_url ?? null); setPendingFile(null); setEditing(p); setShowForm(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const activeCatsSet = new Set(activeCategories)
    const filteredOptionalIds = (form.optional_ids ?? []).filter((optId) => {
      const opt = allOptionals.find((o) => o.id === optId)
      return opt ? activeCatsSet.has(opt.category) : false
    })

    const payload = {
      ...form,
      optional_ids: filteredOptionalIds,
      profundidade: form.is_circular ? 0 : form.profundidade,
    }
    if (editing) {
      const updated = await updateM.mutateAsync({ id: editing.id, data: payload })
      if (pendingFile) await uploadM.mutateAsync({ id: updated.id, file: pendingFile })
    } else {
      const created = await createM.mutateAsync(payload)
      if (pendingFile) await uploadM.mutateAsync({ id: created.id, file: pendingFile })
    }
    setShowForm(false)
  }

  const thProps = { sortKey: String(sortKey), sortDir, onSort: (k: string) => toggle(k as keyof Product), color }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-[#9d8d81]">{products?.length ?? 0} {(products?.length ?? 0) === 1 ? 'produto' : 'produtos'}</span>
        <button className="btn-primary flex items-center gap-2" style={{ backgroundColor: color, touchAction: 'manipulation' } as React.CSSProperties} onClick={openCreate}>
          <Plus className="w-4 h-4" /> <span className="hidden sm:inline">Novo </span>Produto
        </button>
      </div>

      {isLoading ? (
        <p className="text-[#9d8d81] text-sm py-8 text-center">Carregando...</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="md:hidden flex flex-col gap-3">
            {sorted.map((p) => (
              <div key={p.id} className="bg-[#fcfbfa] border border-[#e8e0d6] rounded-xl p-3.5 flex gap-3">
                {p.photo_url
                  ? <img src={p.photo_url} alt="" className="w-14 h-14 object-cover rounded-lg border border-[#e8e0d6] flex-shrink-0" />
                  : <div className="w-14 h-14 bg-[#f0ece6] rounded-lg flex items-center justify-center flex-shrink-0"><ImageIcon className="w-5 h-5 text-[#c8bdb5]" /></div>
                }
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <span className="text-[11px] font-mono font-semibold" style={{ color }}>{p.product_code}</span>
                      <p className="text-sm font-medium text-[#2c2420] leading-snug line-clamp-2">{p.description}</p>
                    </div>
                    <div className="flex gap-0 flex-shrink-0">
                      <button onClick={() => openEdit(p)} className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleting(p)} className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:text-red-500 transition-colors" style={{ touchAction: 'manipulation' }}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-[#9d8d81]">
                      {p.is_circular
                        ? `Ø ${Number(p.largura).toFixed(2).replace('.', ',')} m`
                        : `${Number(p.largura).toFixed(2).replace('.', ',')} × ${Number(p.profundidade).toFixed(2).replace('.', ',')} × ${Number(p.altura).toFixed(2).replace('.', ',')} m`}
                    </span>
                    <span className="text-sm font-bold text-[#2c2420]">{new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price)}</span>
                  </div>
                  {p.optionals.length > 0 && (
                    <p className="text-[10px] text-[#9d8d81] mt-0.5 truncate">{groupOptionalsByCategory(p.optionals).map(g => g.label).join(' · ')}</p>
                  )}
                </div>
              </div>
            ))}
            {sorted.length === 0 && <p className="text-center text-[#9d8d81] text-sm py-8">Nenhum produto cadastrado.</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden md:block overflow-x-auto rounded-xl border border-[#e8e0d6]">
            <table className="w-full text-sm">
              <thead style={{ backgroundColor: `${color}12` }}>
                <tr>
                  <Th label="Código" col="product_code" {...thProps} />
                  <Th label="Descrição" col="description" {...thProps} />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Dimensões</th>
                  <Th label="Preço Base" col="price" {...thProps} />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9d8d81] uppercase">Opcionais</th>
                  <th className="px-4 py-3 text-xs font-semibold text-[#9d8d81] uppercase">Foto</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td className="px-4 py-3 font-mono text-sm font-medium" style={{ color }}>{p.product_code}</td>
                    <td className="px-4 py-3 text-[#2c2420] max-w-[180px] truncate">{p.description}</td>
                    <td className="px-4 py-3 text-[#4a3f38] text-xs whitespace-nowrap">
                      {p.is_circular
                        ? `Ø ${Number(p.largura).toFixed(2).replace('.', ',')} × A ${Number(p.altura).toFixed(2).replace('.', ',')} m`
                        : `L ${Number(p.largura).toFixed(2).replace('.', ',')} × P ${Number(p.profundidade).toFixed(2).replace('.', ',')} × A ${Number(p.altura).toFixed(2).replace('.', ',')} m`}
                    </td>
                    <td className="px-4 py-3 text-[#2c2420] text-sm font-medium whitespace-nowrap">
                      {new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(p.price)}
                    </td>
                    <td className="px-4 py-3 text-[#8a7a6e] text-xs max-w-[160px]">
                      {p.optionals.length > 0
                        ? groupOptionalsByCategory(p.optionals).map(g => g.label).join(', ')
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {p.photo_url
                        ? <img src={p.photo_url} alt="" className="w-10 h-10 object-cover rounded-lg border border-[#e8e0d6]" />
                        : <ImageIcon className="w-6 h-6 text-[#c8bdb5]" />}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openEdit(p)} className="text-[#9d8d81] transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Pencil className="w-4 h-4" /></button>
                        <button onClick={() => setDeleting(p)} className="text-[#9d8d81] hover:text-red-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {sorted.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-[#9d8d81]">Nenhum produto cadastrado.</td></tr>
                )}
              </tbody>
            </table>
          </div>
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
              <span className="text-xs text-[#9d8d81]">Nome do Novo Tipo *</span>
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
        <Modal title={editing ? 'Editar Produto' : 'Novo Produto'} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-[#9d8d81]">Código *</span>
                <input className="input" value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-[#9d8d81]">Preço Base (R$) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} required />
              </label>
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-[#9d8d81]">Descrição *</span>
                <input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-[#9d8d81]">Tipo</span>
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

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_circular}
                onChange={(e) => setForm({ ...form, is_circular: e.target.checked, profundidade: e.target.checked ? 0 : form.profundidade })}
                style={{ accentColor: color }}
                className="w-4 h-4"
              />
              <span className="text-sm text-[#4a3f38]">Medida Redonda (Ø — circular)</span>
            </label>

            <div className="grid grid-cols-3 gap-3">
              {form.is_circular ? (
                <>
                  <label className="flex flex-col gap-1 col-span-2">
                    <span className="text-xs text-[#9d8d81]">Diâmetro Ø (m) *</span>
                    <input className="input" type="number" min="0" step="0.01" value={form.largura}
                      onChange={(e) => setForm({ ...form, largura: Number(e.target.value) })} required />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-[#9d8d81]">Altura A (m) *</span>
                    <input className="input" type="number" min="0" step="0.01" value={form.altura}
                      onChange={(e) => setForm({ ...form, altura: Number(e.target.value) })} required />
                  </label>
                </>
              ) : (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-[#9d8d81]">Largura L (m) *</span>
                    <input className="input" type="number" min="0" step="0.01" value={form.largura}
                      onChange={(e) => setForm({ ...form, largura: Number(e.target.value) })} required />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-[#9d8d81]">Prof. P (m) *</span>
                    <input className="input" type="number" min="0" step="0.01" value={form.profundidade}
                      onChange={(e) => setForm({ ...form, profundidade: Number(e.target.value) })} required />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-[#9d8d81]">Altura A (m) *</span>
                    <input className="input" type="number" min="0" step="0.01" value={form.altura}
                      onChange={(e) => setForm({ ...form, altura: Number(e.target.value) })} required />
                  </label>
                </>
              )}
            </div>

            <div>
              <span className="text-xs text-[#9d8d81] block mb-2 font-medium">Categorias de Opcionais Disponíveis</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                {CATEGORY_OPTIONS.map(({ value, label }) => {
                  const isActive = activeCategories.includes(value)
                  return (
                    <label key={value} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[#e8e0d6] hover:bg-[#f8f6f2] cursor-pointer transition-colors">
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
                      <span className="text-xs text-[#4a3f38] select-none">{label}</span>
                    </label>
                  )
                })}
              </div>

              {activeCategories.length > 0 && (
                <div className="space-y-3">
                  <span className="text-xs text-[#9d8d81] block font-medium">Escolha as Cores para cada Opcional</span>
                  {activeCategories.map((catValue) => {
                    const catLabel = CATEGORY_LABEL[catValue] || catValue
                    const catItems = allOptionals.filter(o => o.category === catValue)
                    return (
                      <div key={catValue} className="border border-[#e8e0d6] rounded-xl p-3.5 space-y-2 bg-[#fdfdfd] shadow-sm">
                        <div className="text-xs font-semibold text-[#2c2420] pb-1 border-b border-[#f3ede6]" style={{ color }}>
                          {catLabel.toUpperCase()}
                        </div>
                        <div className="flex flex-wrap gap-2 pt-1">
                          {catItems.map(opt => {
                            const isSelected = (form.optional_ids ?? []).includes(opt.id)
                            return (
                              <button
                                type="button"
                                key={opt.id}
                                onClick={() => {
                                  setForm(prev => {
                                    const ids = prev.optional_ids ?? []
                                    const has = ids.includes(opt.id)
                                    return {
                                      ...prev,
                                      optional_ids: has ? ids.filter(id => id !== opt.id) : [...ids, opt.id]
                                    }
                                  })
                                }}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border transition-all"
                                style={isSelected
                                  ? { backgroundColor: `${color}20`, borderColor: color, color }
                                  : { backgroundColor: '#f8f6f2', borderColor: '#e8e0d6', color: '#6b5d55' }}
                              >
                                {opt.photo_url && (
                                  <img src={opt.photo_url} alt={opt.color_name}
                                    className="w-4 h-4 rounded-md object-cover flex-shrink-0" />
                                )}
                                <span className="font-medium">{opt.color_name}</span>
                              </button>
                            )
                          })}
                          {catItems.length === 0 && (
                            <span className="text-xs text-[#c8bdb5] italic">Nenhuma cor cadastrada nesta categoria.</span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            <div>
              <span className="text-xs text-[#9d8d81] block mb-1">Foto</span>
              <div
                className="border-2 border-dashed border-[#e8e0d6] rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
              >
                {photoPreview ? <img src={photoPreview} alt="" className="w-24 h-24 object-cover rounded-lg" /> : <Upload className="w-8 h-8 text-[#c8bdb5]" />}
                <span className="text-xs text-[#9d8d81]">{photoPreview ? 'Clique para trocar' : 'JPG, PNG, WEBP — máx. 5MB'}</span>
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

const EMPTY_ADDRESS: ClientCreate = { name: '', phone: '', email: '', cep: '', numero: '', address: '', city: '', state: '' }

function PeopleTab<T extends Client | Representative>({
  label, entityType, items, isLoading, onCreate, onUpdate, onDelete, isPending, color,
}: {
  label: string; entityType: 'client' | 'rep'
  items: T[] | undefined; isLoading: boolean
  onCreate: (data: ClientCreate) => Promise<void>; onUpdate: (id: string, data: Partial<ClientCreate>) => Promise<void>
  onDelete: (id: string) => Promise<void>; isPending: boolean; color: string
}) {
  const { user: authUser } = useAuth()
  const isAdmin = authUser?.role === 'admin'
  const isRep = authUser?.role === 'representante'

  const { sorted, sortKey, sortDir, toggle } = useSortedList<T>(items, 'name' as keyof T)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<T | null>(null)
  const [deleting, setDeleting] = useState<T | null>(null)
  const [viewing, setViewing] = useState<T | null>(null)
  const [createdUser, setCreatedUser] = useState<UserCreateResponse | null>(null)
  const [createUserError, setCreateUserError] = useState<string | null>(null)
  const [form, setForm] = useState<ClientCreate>(EMPTY_ADDRESS)

  const createFromClient = useCreateUserFromClient()
  const createFromRep = useCreateUserFromRep()

  function openCreate() { setForm(EMPTY_ADDRESS); setEditing(null); setShowForm(true) }
  function openEdit(item: T) {
    setForm({ name: item.name, phone: item.phone, email: item.email, cep: item.cep, numero: item.numero ?? '', address: item.address, city: item.city, state: item.state })
    setEditing(item); setShowForm(true)
  }
  function openView(item: T) {
    setViewing(item); setCreatedUser(null); setCreateUserError(null)
  }
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editing) await onUpdate(editing.id, form); else await onCreate(form)
    setShowForm(false)
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
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-[#9d8d81]">{items?.length ?? 0} {label.toLowerCase()} cadastrados</span>
        <button className="btn-primary flex items-center gap-2" style={{ backgroundColor: color }} onClick={openCreate}>
          <Plus className="w-4 h-4" /> Novo {label.slice(0, -1)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-[#9d8d81] text-sm py-8 text-center">Carregando...</p>
      ) : (
        <>
          {/* ── Mobile cards ──────────────────────────────────── */}
          <div className="md:hidden flex flex-col gap-3">
            {sorted.map((item) => (
              <div key={item.id} className="bg-[#fcfbfa] border border-[#e8e0d6] rounded-xl p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[#2c2420]">{item.name}</p>
                    <p className="text-xs text-[#9d8d81] mt-0.5">{item.city} / {item.state}</p>
                  </div>
                  <div className="flex gap-0 flex-shrink-0">
                    <button onClick={() => openView(item)} className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Eye className="w-4 h-4" />
                    </button>
                    <button onClick={() => openEdit(item)} className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:opacity-60 transition-opacity" style={{ touchAction: 'manipulation' }}>
                      <Pencil className="w-4 h-4" />
                    </button>
                    {!(isRep && entityType === 'client') && (
                      <button onClick={() => setDeleting(item)} className="w-9 h-9 flex items-center justify-center text-[#9d8d81] active:text-red-500 transition-colors" style={{ touchAction: 'manipulation' }}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 space-y-0.5 text-xs text-[#4a3f38]">
                  <p>{item.phone}</p>
                  <p className="truncate text-[#8a7a6e]">{item.email}</p>
                </div>
              </div>
            ))}
            {sorted.length === 0 && <p className="text-center text-[#9d8d81] text-sm py-8">Nenhum registro encontrado.</p>}
          </div>

          {/* ── Desktop table ──────────────────────────────────── */}
          <div className="hidden md:block overflow-x-auto rounded-xl border border-[#e8e0d6]">
            <table className="w-full text-sm">
              <thead style={{ backgroundColor: `${color}12` }}>
                <tr>
                  <Th label="Nome" col="name" {...thProps} />
                  <Th label="Telefone" col="phone" {...thProps} />
                  <Th label="E-mail" col="email" {...thProps} />
                  <Th label="Cidade" col="city" {...thProps} />
                  <Th label="UF" col="state" {...thProps} />
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item) => (
                  <tr key={item.id} className="table-row">
                    <td className="px-4 py-3 text-[#2c2420] font-medium">{item.name}</td>
                    <td className="px-4 py-3 text-[#4a3f38]">{item.phone}</td>
                    <td className="px-4 py-3 text-[#4a3f38]">{item.email}</td>
                    <td className="px-4 py-3 text-[#4a3f38]">{item.city}</td>
                    <td className="px-4 py-3 text-[#8a7a6e]">{item.state}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => openView(item)} title="Visualizar" className="text-[#9d8d81] transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Eye className="w-4 h-4" /></button>
                        <button onClick={() => openEdit(item)} title="Editar" className="text-[#9d8d81] transition-colors"
                          onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                          onMouseLeave={(e) => (e.currentTarget.style.color = '')}><Pencil className="w-4 h-4" /></button>
                        {!(isRep && entityType === 'client') && (
                          <button onClick={() => setDeleting(item)} title="Excluir" className="text-[#9d8d81] hover:text-red-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {sorted.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-[#9d8d81]">Nenhum registro encontrado.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* View / Create User modal */}
      {viewing && (
        <Modal title={`Detalhes — ${viewing.name}`} onClose={() => setViewing(null)} accentColor={color}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div><span className="text-xs text-[#9d8d81] block">Nome</span><span className="text-[#2c2420] font-medium">{viewing.name}</span></div>
              <div><span className="text-xs text-[#9d8d81] block">Telefone</span><span className="text-[#4a3f38]">{viewing.phone}</span></div>
              <div className="col-span-2"><span className="text-xs text-[#9d8d81] block">E-mail</span><span className="text-[#4a3f38]">{viewing.email}</span></div>
              <div><span className="text-xs text-[#9d8d81] block">Cidade</span><span className="text-[#4a3f38]">{viewing.city}</span></div>
              <div><span className="text-xs text-[#9d8d81] block">Estado</span><span className="text-[#4a3f38]">{viewing.state}</span></div>
              <div className="col-span-2"><span className="text-xs text-[#9d8d81] block">Endereço</span><span className="text-[#4a3f38]">{viewing.address}{viewing.numero ? `, ${viewing.numero}` : ''} — CEP {viewing.cep}</span></div>
            </div>

            {(isAdmin || (isRep && entityType === 'client')) && <div className="border-t border-[#e8e0d6] pt-4">
              <p className="text-xs font-semibold text-[#8a7a6e] uppercase tracking-wider mb-3">Acesso ao Sistema</p>

              {createdUser ? (
                <div className="bg-[#f0f7f0] border border-[#c5dfc4] rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2 text-[#4a7a47]">
                    <CheckCircle className="w-5 h-5 flex-shrink-0" />
                    <span className="text-sm font-semibold">Usuário criado com sucesso!</span>
                  </div>
                  <div className="text-sm text-[#4a3f38] space-y-1">
                    <p><span className="text-[#9d8d81]">Usuário:</span> <strong>{createdUser.username}</strong></p>
                    <p><span className="text-[#9d8d81]">Senha inicial:</span> <strong>{createdUser.temp_password}</strong></p>
                    <p><span className="text-[#9d8d81]">Perfil:</span> {createdUser.role === 'representante' ? 'Representante' : 'Vendedor'}</p>
                  </div>
                  <p className="text-xs text-[#8a7a6e] mt-1">O usuário deverá trocar a senha no primeiro acesso.</p>
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
                  <span className="text-xs text-[#9d8d81]">Gerencie pela tela Admin.</span>
                </div>
              ) : (
                <>
                  {createUserError && (
                    <p className="text-xs text-[#b25e50] mb-2">{createUserError}</p>
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
                  <p className="text-xs text-[#9d8d81] mt-2">
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
            <p className="text-[10px] text-[#b8b0a6] leading-relaxed pt-1">
              Os dados coletados neste formulário são processados estritamente para a elaboração de orçamentos e gestão do pedido, conforme a nossa Política de Privacidade.
            </p>
            <div className="flex justify-end gap-3 pt-1">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" style={{ backgroundColor: color }} disabled={isPending}>{editing ? 'Salvar' : 'Criar'}</button>
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

const EMPTY_OPT: OptionalColorCreate = { category: 'aluminio', color_name: '' }

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
  const [editingGroup, setEditingGroup] = useState<{ id: string; name: string; code: string } | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<{ id: string; name: string } | null>(null)
  const [groupForm, setGroupForm] = useState({ name: '', code: '' })
  const [groupErr, setGroupErr] = useState('')

  // Lightbox
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)

  function openCreate() {
    const defaultCat = categories[0]?.code ?? CATEGORY_OPTIONS[0]?.value ?? 'aluminio'
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
  function openEditGroup(g: { id: string; name: string; code: string }) { setEditingGroup(g); setGroupForm({ name: g.name, code: g.code }); setGroupErr(''); setShowGroupForm(true) }
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

  // Dynamic category list: prefer API, fall back to static
  const catOptions = categories.length > 0
    ? categories.map(c => ({ value: c.code, label: c.name }))
    : CATEGORY_OPTIONS

  const catLabel = (code: string) => {
    const found = categories.find(c => c.code === code)
    return found?.name ?? CATEGORY_LABEL[code] ?? code
  }

  const grouped = optionals
    ? groupOptionalsByCategoryDynamic(optionals, catLabel)
    : []

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-2">
        <span className="text-sm text-[#9d8d81]">{optionals?.length ?? 0} opcionais cadastrados</span>
        {!readOnly && (
          <div className="flex gap-2">
            <button className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-1.5" onClick={openNewGroup}>
              <Plus className="w-3.5 h-3.5" /> Adicionar Grupos
            </button>
            <button className="btn-primary flex items-center gap-2" style={{ backgroundColor: color }} onClick={openCreate}>
              <Plus className="w-4 h-4" /> Novo Opcional
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <p className="text-[#9d8d81] text-sm py-8 text-center">Carregando...</p>
      ) : (
        <div className="space-y-4">
          {grouped.map(({ category, label, items }) => (
            <div key={category} className="rounded-xl border border-[#e8e0d6] overflow-hidden">
              <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                style={{ backgroundColor: `${color}12`, color }}>
                {label}
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {items.map((opt) => (
                    <tr key={opt.id} className="table-row">
                      <td className="px-4 py-2.5 w-12">
                        {opt.photo_url
                          ? <button onClick={() => setLightboxUrl(opt.photo_url!)} className="cursor-zoom-in">
                              <img src={opt.photo_url} alt={opt.color_name}
                                className="w-8 h-8 rounded-md object-cover border border-[#e8e0d6] hover:opacity-80 transition-opacity" />
                            </button>
                          : <div className="w-8 h-8 rounded-md bg-[#f0ece6] border border-[#e8e0d6]" />}
                      </td>
                      <td className="px-4 py-2.5 text-[#2c2420]">{opt.color_name}</td>
                      {!readOnly && (
                        <td className="px-4 py-2.5 w-16">
                          <div className="flex gap-2">
                            <button onClick={() => openEdit(opt)} className="text-[#9d8d81] transition-colors"
                              onMouseEnter={(e) => (e.currentTarget.style.color = color)}
                              onMouseLeave={(e) => (e.currentTarget.style.color = '')}>
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setDeleting(opt)} className="text-[#9d8d81] hover:text-red-500 transition-colors">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {grouped.length === 0 && (
            <p className="text-[#9d8d81] text-sm py-8 text-center">Nenhum opcional cadastrado.</p>
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
              className="absolute -top-3 -right-3 w-8 h-8 flex items-center justify-center bg-white rounded-full shadow-lg text-[#2c2420] hover:bg-[#f8f6f2] transition-colors">
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
              <span className="text-xs text-[#9d8d81]">Categoria *</span>
              <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
                {catOptions.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[#9d8d81]">Nome da Cor *</span>
              <input className="input" value={form.color_name}
                onChange={(e) => setForm({ ...form, color_name: e.target.value })} required />
            </label>

            <div>
              <span className="text-xs text-[#9d8d81] block mb-1">Imagem de Textura (swatch)</span>
              <div
                className="border-2 border-dashed border-[#e8e0d6] rounded-xl p-3 flex flex-col items-center gap-1.5 cursor-pointer transition-colors"
                onClick={() => optFileRef.current?.click()}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = color)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
              >
                {optPhotoPreview
                  ? <img src={optPhotoPreview} alt="" className="w-16 h-16 object-cover rounded-lg" />
                  : <Upload className="w-6 h-6 text-[#c8bdb5]" />}
                <span className="text-xs text-[#9d8d81]">
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
              <span className="text-xs text-[#9d8d81]">Nome do Grupo *</span>
              <input className="input" value={groupForm.name} onChange={(e) => setGroupForm(f => ({ ...f, name: e.target.value }))} required autoFocus placeholder="ex: Alumínio" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[#9d8d81]">Código (identificador único) *</span>
              <input className="input font-mono text-sm" value={groupForm.code} onChange={(e) => setGroupForm(f => ({ ...f, code: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} required placeholder="ex: aluminio" />
              <span className="text-[10px] text-[#c8bdb5]">Apenas letras minúsculas, números e underscores.</span>
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
        <ConfirmDelete name={deletingGroup.name}
          onConfirm={async () => { await deleteCatM.mutateAsync(deletingGroup.id); setDeletingGroup(null) }}
          onCancel={() => setDeletingGroup(null)} />
      )}
    </div>
  )
}

// ── TypesTab ──────────────────────────────────────────────────────────────────

function TypesTab({ color }: { color: string }) {
  const { data: items = [], isLoading } = useProductTypes()
  const createM = useCreateProductType()
  const updateM = useUpdateProductType()
  const deleteM = useDeleteProductType()

  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  const [name, setName] = useState('')
  const [deleting, setDeleting] = useState<{ id: string; name: string } | null>(null)
  const [err, setErr] = useState('')

  function openNew() { setEditing(null); setName(''); setErr(''); setShowForm(true) }
  function openEdit(item: { id: string; name: string }) { setEditing(item); setName(item.name); setErr(''); setShowForm(true) }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    try {
      if (editing) {
        await updateM.mutateAsync({ id: editing.id, name: name.trim() })
      } else {
        await createM.mutateAsync({ name: name.trim() })
      }
      setShowForm(false)
    } catch (ex: unknown) {
      const detail = (ex as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErr(detail ?? 'Erro ao salvar tipo.')
    }
  }

  const isPending = createM.isPending || updateM.isPending

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-[#2c2420]">Tipos de Móveis</h2>
        <button onClick={openNew} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors"
          style={{ backgroundColor: color }}>
          <Plus className="w-3.5 h-3.5" /> Novo Tipo
        </button>
      </div>

      {showForm && (
        <Modal title={editing ? 'Editar Tipo' : 'Novo Tipo'} onClose={() => setShowForm(false)} accentColor={color}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[#9d8d81]">Nome do Tipo *</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </label>
            {err && <p className="text-xs text-red-500">{err}</p>}
            <div className="flex gap-2 pt-1">
              <button type="submit" disabled={isPending} className="btn-primary flex-1">
                {isPending ? 'Salvando...' : editing ? 'Salvar Alterações' : 'Criar Tipo'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary px-4">Cancelar</button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete name={deleting.name}
          onConfirm={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)} />
      )}

      {isLoading ? (
        <p className="text-sm text-[#9d8d81]">Carregando...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-[#9d8d81]">Nenhum tipo cadastrado.</p>
      ) : (
        <div className="flex flex-wrap gap-2 pt-1">
          {items.map(item => (
            <div key={item.id}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#e8e0d6] bg-white text-sm text-[#2c2420]">
              <span>{item.name}</span>
              <button onClick={() => openEdit(item)} className="text-[#9d8d81] hover:text-[#8b6914] transition-colors">
                <Pencil className="w-3 h-3" />
              </button>
              <button onClick={() => setDeleting(item)} className="text-[#9d8d81] hover:text-red-500 transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────

const TAB_CONFIG: { key: Tab; label: string; Icon: React.ElementType }[] = [
  { key: 'produtos',       label: 'Produtos',       Icon: Package     },
  { key: 'clientes',       label: 'Clientes',        Icon: Users       },
  { key: 'representantes', label: 'Representantes',  Icon: UserCheck   },
  { key: 'opcionais',      label: 'Opcionais',       Icon: Tag         },
  { key: 'tipos',          label: 'Tipos',           Icon: LayoutGrid  },
]

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
  const [tab, setTab] = useState<Tab>(defaultTab)

  const { data: products } = useProducts()
  const { data: clients }  = useClients()
  const { data: reps }     = useRepresentatives()
  const { data: optionals } = useOptionals()
  const { data: tipos }    = useProductTypes()

  const { data: clientsData, isLoading: clientsLoading } = useClients()
  const createClient = useCreateClient(); const updateClient = useUpdateClient(); const deleteClient = useDeleteClient()

  const { data: repsData, isLoading: repsLoading } = useRepresentatives()
  const createRep = useCreateRepresentative(); const updateRep = useUpdateRepresentative(); const deleteRep = useDeleteRepresentative()

  const counts: Record<Tab, number> = {
    produtos:       products?.length ?? 0,
    clientes:       clients?.length  ?? 0,
    representantes: reps?.length     ?? 0,
    opcionais:      optionals?.length ?? 0,
    tipos:          tipos?.length    ?? 0,
  }

  const activeColor = TAB_PALETTE[tab].color

  return (
    <div className="min-h-screen bg-[#f8f6f2] text-[#2c2420] pb-24 md:pb-0">
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
            <div className="bg-white border border-[#e8e0d6] rounded-xl shadow-sm p-3 sticky top-20 space-y-1">
              <p className="text-[10px] font-semibold text-[#c8bdb5] uppercase tracking-widest px-3 pb-2">Cadastros</p>
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
          <main className="bg-white border border-[#e8e0d6] rounded-xl shadow-sm p-6"
            style={{ borderTop: `3px solid ${activeColor}` }}>
            {tab === 'produtos' && <ProductsTab color={TAB_PALETTE.produtos.color} />}

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
              />
            )}

            {tab === 'opcionais' && <OptionaisTab color={TAB_PALETTE.opcionais.color} readOnly={isLimited} />}

            {tab === 'tipos' && <TypesTab color={TAB_PALETTE.tipos.color} />}
          </main>
        </div>
      </div>
    </div>
  )
}
