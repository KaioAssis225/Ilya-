import { useState, useRef } from 'react'
import { ChevronUp, ChevronDown, Pencil, Trash2, Plus, X, Upload, ImageIcon } from 'lucide-react'
import { useProducts, useCreateProduct, useUpdateProduct, useDeleteProduct, useUploadProductPhoto } from '../hooks/useProducts'
import { useClients, useCreateClient, useUpdateClient, useDeleteClient } from '../hooks/useClients'
import { useRepresentatives, useCreateRepresentative, useUpdateRepresentative, useDeleteRepresentative } from '../hooks/useRepresentatives'
import type { Product, ProductCreate, Client, ClientCreate, Representative, ViaCepResponse } from '../types'

type Tab = 'produtos' | 'clientes' | 'representantes'
type SortDir = 'asc' | 'desc'

const OPT_ALUMINIO = ['Natural', 'Escovado', 'Preto']
const OPT_TECIDO = ['Camomila', 'Canela', 'Areia', 'Taupe']
const OPT_CORDA = ['Natural', 'Grafite', 'Areia']

const ESTADOS = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
  'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO',
]

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

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ChevronUp className="w-3 h-3 opacity-30" />
  return dir === 'asc'
    ? <ChevronUp className="w-3 h-3 text-yellow-400" />
    : <ChevronDown className="w-3 h-3 text-yellow-400" />
}

function Th({ label, col, sortKey, sortDir, onSort }: {
  label: string; col: string; sortKey: string; sortDir: SortDir; onSort: (k: string) => void
}) {
  return (
    <th
      className="px-4 py-3 text-left text-xs font-semibold text-stone-400 uppercase tracking-wider cursor-pointer select-none hover:text-yellow-400 transition-colors"
      onClick={() => onSort(col)}
    >
      <span className="flex items-center gap-1">
        {label}
        <SortIcon active={sortKey === col} dir={sortDir} />
      </span>
    </th>
  )
}

async function fetchCep(cep: string): Promise<ViaCepResponse | null> {
  const clean = cep.replace(/\D/g, '')
  if (clean.length !== 8) return null
  try {
    const r = await fetch(`https://viacep.com.br/ws/${clean}/json/`)
    const data: ViaCepResponse = await r.json()
    return data.erro ? null : data
  } catch {
    return null
  }
}

// ── Address form fields (shared by Client + Rep) ─────────────────────────────

function AddressFields({ form, setForm }: {
  form: ClientCreate
  setForm: (v: ClientCreate) => void
}) {
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
        <span className="text-xs text-stone-400">Nome *</span>
        <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-stone-400">Telefone *</span>
        <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-stone-400">E-mail *</span>
        <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1 relative">
        <span className="text-xs text-stone-400">CEP *</span>
        <input
          className="input pr-8"
          value={form.cep}
          onChange={(e) => setForm({ ...form, cep: e.target.value })}
          onBlur={handleCepBlur}
          maxLength={9}
          required
        />
        {cepLoading && (
          <span className="absolute right-2 bottom-2 text-xs text-yellow-400 animate-pulse">...</span>
        )}
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-stone-400">Número</span>
        <input className="input" value={form.numero ?? ''} onChange={(e) => setForm({ ...form, numero: e.target.value })} />
      </label>
      <label className="col-span-2 flex flex-col gap-1">
        <span className="text-xs text-stone-400">Endereço *</span>
        <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-stone-400">Cidade *</span>
        <input className="input" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-stone-400">Estado *</span>
        <select className="input" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} required>
          <option value="">UF</option>
          {ESTADOS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
    </div>
  )
}

// ── Modal wrapper ─────────────────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold text-stone-100">{title}</h3>
          <button onClick={onClose} className="text-stone-400 hover:text-white transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Confirm delete dialog ─────────────────────────────────────────────────────

function ConfirmDelete({ name, onConfirm, onCancel }: { name: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Modal title="Confirmar exclusão" onClose={onCancel}>
      <p className="text-stone-300 mb-6">Excluir <span className="text-white font-medium">"{name}"</span>? Esta ação não pode ser desfeita.</p>
      <div className="flex justify-end gap-3">
        <button className="btn-secondary" onClick={onCancel}>Cancelar</button>
        <button className="btn-danger" onClick={onConfirm}>Excluir</button>
      </div>
    </Modal>
  )
}

// ── PRODUTOS ──────────────────────────────────────────────────────────────────

const EMPTY_PRODUCT: ProductCreate = {
  product_code: '', description: '',
  altura: 0, largura: 0, profundidade: 0,
  opt_aluminio: null, opt_tecido: null, opt_corda: null,
}

function ProductsTab() {
  const { data: products, isLoading } = useProducts()
  const createM = useCreateProduct()
  const updateM = useUpdateProduct()
  const deleteM = useDeleteProduct()
  const uploadM = useUploadProductPhoto()

  const { sorted, sortKey, sortDir, toggle } = useSortedList<Product>(products, 'product_code')

  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)
  const [deleting, setDeleting] = useState<Product | null>(null)
  const [form, setForm] = useState<ProductCreate>(EMPTY_PRODUCT)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  function openCreate() {
    setForm(EMPTY_PRODUCT); setEditing(null); setPhotoPreview(null); setPendingFile(null); setShowForm(true)
  }

  function openEdit(p: Product) {
    setForm({
      product_code: p.product_code, description: p.description,
      altura: p.altura, largura: p.largura, profundidade: p.profundidade,
      opt_aluminio: p.opt_aluminio, opt_tecido: p.opt_tecido, opt_corda: p.opt_corda,
    })
    setPhotoPreview(p.photo_url ?? null)
    setPendingFile(null)
    setEditing(p)
    setShowForm(true)
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPendingFile(file)
    setPhotoPreview(URL.createObjectURL(file))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editing) {
      const updated = await updateM.mutateAsync({ id: editing.id, data: form })
      if (pendingFile) await uploadM.mutateAsync({ id: updated.id, file: pendingFile })
    } else {
      const created = await createM.mutateAsync(form)
      if (pendingFile) await uploadM.mutateAsync({ id: created.id, file: pendingFile })
    }
    setShowForm(false)
  }

  const thProps = { sortKey: String(sortKey), sortDir, onSort: (k: string) => toggle(k as keyof Product) }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-200 font-medium">
          Produtos <span className="ml-2 text-xs bg-stone-700 text-yellow-400 px-2 py-0.5 rounded-full">{products?.length ?? 0}</span>
        </h2>
        <button className="btn-primary flex items-center gap-2" onClick={openCreate}>
          <Plus className="w-4 h-4" /> Novo Produto
        </button>
      </div>

      {isLoading ? (
        <p className="text-stone-500 text-sm">Carregando...</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-800">
          <table className="w-full text-sm">
            <thead className="bg-stone-800/60">
              <tr>
                <Th label="Código" col="product_code" {...thProps} />
                <Th label="Descrição" col="description" {...thProps} />
                <Th label="Alt (cm)" col="altura" {...thProps} />
                <Th label="Larg (cm)" col="largura" {...thProps} />
                <Th label="Prof (cm)" col="profundidade" {...thProps} />
                <th className="px-4 py-3 text-xs font-semibold text-stone-400 uppercase">Opcionais</th>
                <th className="px-4 py-3 text-xs font-semibold text-stone-400 uppercase">Foto</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => (
                <tr key={p.id} className="table-row">
                  <td className="px-4 py-3 font-mono text-yellow-400">{p.product_code}</td>
                  <td className="px-4 py-3 text-stone-200 max-w-[200px] truncate">{p.description}</td>
                  <td className="px-4 py-3 text-stone-300">{p.altura}</td>
                  <td className="px-4 py-3 text-stone-300">{p.largura}</td>
                  <td className="px-4 py-3 text-stone-300">{p.profundidade}</td>
                  <td className="px-4 py-3 text-stone-400 text-xs">
                    {[p.opt_aluminio, p.opt_tecido, p.opt_corda].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-3">
                    {p.photo_url
                      ? <img src={p.photo_url} alt="" className="w-10 h-10 object-cover rounded-lg border border-stone-700" />
                      : <ImageIcon className="w-6 h-6 text-stone-600" />}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => openEdit(p)} className="text-stone-400 hover:text-yellow-400 transition-colors">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleting(p)} className="text-stone-400 hover:text-red-400 transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-stone-500">Nenhum produto cadastrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal title={editing ? 'Editar Produto' : 'Novo Produto'} onClose={() => setShowForm(false)}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Código *</span>
                <input className="input" value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1 col-span-2">
                <span className="text-xs text-stone-400">Descrição *</span>
                <input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Altura (cm) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.altura} onChange={(e) => setForm({ ...form, altura: Number(e.target.value) })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Largura (cm) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.largura} onChange={(e) => setForm({ ...form, largura: Number(e.target.value) })} required />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Profundidade (cm) *</span>
                <input className="input" type="number" min="0" step="0.01" value={form.profundidade} onChange={(e) => setForm({ ...form, profundidade: Number(e.target.value) })} required />
              </label>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Alumínio</span>
                <select className="input" value={form.opt_aluminio ?? ''} onChange={(e) => setForm({ ...form, opt_aluminio: e.target.value || null })}>
                  <option value="">—</option>
                  {OPT_ALUMINIO.map((o) => <option key={o}>{o}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Tecido</span>
                <select className="input" value={form.opt_tecido ?? ''} onChange={(e) => setForm({ ...form, opt_tecido: e.target.value || null })}>
                  <option value="">—</option>
                  {OPT_TECIDO.map((o) => <option key={o}>{o}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-stone-400">Corda</span>
                <select className="input" value={form.opt_corda ?? ''} onChange={(e) => setForm({ ...form, opt_corda: e.target.value || null })}>
                  <option value="">—</option>
                  {OPT_CORDA.map((o) => <option key={o}>{o}</option>)}
                </select>
              </label>
            </div>

            {/* Photo upload */}
            <div>
              <span className="text-xs text-stone-400 block mb-1">Foto</span>
              <div
                className="border-2 border-dashed border-stone-700 rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer hover:border-yellow-500/50 transition-colors"
                onClick={() => fileRef.current?.click()}
              >
                {photoPreview
                  ? <img src={photoPreview} alt="" className="w-24 h-24 object-cover rounded-lg" />
                  : <Upload className="w-8 h-8 text-stone-600" />}
                <span className="text-xs text-stone-500">{photoPreview ? 'Clique para trocar' : 'Clique para enviar (JPG, PNG, WEBP, max 5MB)'}</span>
              </div>
              <input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.webp" className="hidden" onChange={handleFileChange} />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" disabled={createM.isPending || updateM.isPending || uploadM.isPending}>
                {editing ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete
          name={deleting.description}
          onConfirm={async () => { await deleteM.mutateAsync(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  )
}

// ── CLIENTES ──────────────────────────────────────────────────────────────────

const EMPTY_ADDRESS: ClientCreate = {
  name: '', phone: '', email: '', cep: '', numero: '', address: '', city: '', state: '',
}

function PeopleTab<T extends Client | Representative>({
  label,
  items,
  isLoading,
  onCreate,
  onUpdate,
  onDelete,
  isPending,
}: {
  label: string
  items: T[] | undefined
  isLoading: boolean
  onCreate: (data: ClientCreate) => Promise<void>
  onUpdate: (id: string, data: Partial<ClientCreate>) => Promise<void>
  onDelete: (id: string) => Promise<void>
  isPending: boolean
}) {
  const { sorted, sortKey, sortDir, toggle } = useSortedList<T>(items, 'name' as keyof T)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<T | null>(null)
  const [deleting, setDeleting] = useState<T | null>(null)
  const [form, setForm] = useState<ClientCreate>(EMPTY_ADDRESS)

  function openCreate() { setForm(EMPTY_ADDRESS); setEditing(null); setShowForm(true) }
  function openEdit(item: T) {
    setForm({
      name: item.name, phone: item.phone, email: item.email,
      cep: item.cep, numero: item.numero ?? '', address: item.address,
      city: item.city, state: item.state,
    })
    setEditing(item); setShowForm(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (editing) await onUpdate(editing.id, form)
    else await onCreate(form)
    setShowForm(false)
  }

  const thProps = { sortKey: String(sortKey), sortDir, onSort: (k: string) => toggle(k as keyof T) }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-200 font-medium">
          {label} <span className="ml-2 text-xs bg-stone-700 text-yellow-400 px-2 py-0.5 rounded-full">{items?.length ?? 0}</span>
        </h2>
        <button className="btn-primary flex items-center gap-2" onClick={openCreate}>
          <Plus className="w-4 h-4" /> Novo {label.slice(0, -1)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-stone-500 text-sm">Carregando...</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-800">
          <table className="w-full text-sm">
            <thead className="bg-stone-800/60">
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
                  <td className="px-4 py-3 text-stone-200 font-medium">{item.name}</td>
                  <td className="px-4 py-3 text-stone-300">{item.phone}</td>
                  <td className="px-4 py-3 text-stone-300">{item.email}</td>
                  <td className="px-4 py-3 text-stone-300">{item.city}</td>
                  <td className="px-4 py-3 text-stone-400">{item.state}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => openEdit(item)} className="text-stone-400 hover:text-yellow-400 transition-colors">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleting(item)} className="text-stone-400 hover:text-red-400 transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-stone-500">Nenhum registro encontrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <Modal title={editing ? `Editar ${label.slice(0, -1)}` : `Novo ${label.slice(0, -1)}`} onClose={() => setShowForm(false)}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <AddressFields form={form} setForm={setForm} />
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
              <button type="submit" className="btn-primary" disabled={isPending}>
                {editing ? 'Salvar' : 'Criar'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDelete
          name={deleting.name}
          onConfirm={async () => { await onDelete(deleting.id); setDeleting(null) }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  )
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────

export default function CadastroPage() {
  const [tab, setTab] = useState<Tab>('produtos')

  const { data: products } = useProducts()
  const { data: clients } = useClients()
  const { data: reps } = useRepresentatives()

  const { data: clientsData, isLoading: clientsLoading } = useClients()
  const createClient = useCreateClient()
  const updateClient = useUpdateClient()
  const deleteClient = useDeleteClient()

  const { data: repsData, isLoading: repsLoading } = useRepresentatives()
  const createRep = useCreateRepresentative()
  const updateRep = useUpdateRepresentative()
  const deleteRep = useDeleteRepresentative()

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'produtos', label: 'Produtos', count: products?.length ?? 0 },
    { key: 'clientes', label: 'Clientes', count: clients?.length ?? 0 },
    { key: 'representantes', label: 'Representantes', count: reps?.length ?? 0 },
  ]

  return (
    <div className="min-h-screen bg-stone-950 text-stone-100">
      <div className="max-w-7xl mx-auto px-8 py-6">
        {/* Tabs */}
        <nav className="flex gap-1 mb-6 border-b border-stone-800">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
                tab === t.key
                  ? 'text-yellow-400 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-yellow-400'
                  : 'text-stone-400 hover:text-stone-200'
              }`}
            >
              {t.label}
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${tab === t.key ? 'bg-yellow-400/20 text-yellow-400' : 'bg-stone-800 text-stone-500'}`}>
                {t.count}
              </span>
            </button>
          ))}
        </nav>

        {/* Content */}
        {tab === 'produtos' && <ProductsTab />}

        {tab === 'clientes' && (
          <PeopleTab
            label="Clientes"
            items={clientsData}
            isLoading={clientsLoading}
            isPending={createClient.isPending || updateClient.isPending}
            onCreate={async (data) => { await createClient.mutateAsync(data) }}
            onUpdate={async (id, data) => { await updateClient.mutateAsync({ id, data }) }}
            onDelete={async (id) => { await deleteClient.mutateAsync(id) }}
          />
        )}

        {tab === 'representantes' && (
          <PeopleTab
            label="Representantes"
            items={repsData}
            isLoading={repsLoading}
            isPending={createRep.isPending || updateRep.isPending}
            onCreate={async (data) => { await createRep.mutateAsync(data) }}
            onUpdate={async (id, data) => { await updateRep.mutateAsync({ id, data }) }}
            onDelete={async (id) => { await deleteRep.mutateAsync(id) }}
          />
        )}
      </div>
    </div>
  )
}
