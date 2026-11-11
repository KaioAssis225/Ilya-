import { useMemo, useState } from 'react'
import { Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { OptionalApplicationGroup } from '../components/OptionalApplicationGroup'
import { ProductPhotosManager } from '../components/ProductPhotosManager'
import { useAuth } from '../hooks/useAuth'
import { useCatalogs } from '../hooks/useCatalogs'
import { useOptionalCategories } from '../hooks/useOptionalCategories'
import { useOptionalsForCategories } from '../hooks/useOptionals'
import { useProductTypes } from '../hooks/useProductTypes'
import {
  PROTOTYPES_PATH,
  useCreatePrototype,
  useDeletePrototype,
  usePrototypeOptionalGroups,
  usePrototypesPage,
  useSavePrototypeOptionalGroup,
  useDeletePrototypeOptionalGroup,
  useUpdatePrototype,
  type PrototypeInput,
  type PrototypeOptionalGroup,
} from '../hooks/usePrototypes'
import { parseApiError } from '../lib/personForm'
import type { OptionalApplicationInput, Product } from '../types'

const PAGE_SIZE = 24
const NO_TYPE = 'Outro'
const EU_GREEN = '#2f7d5b'
const DEFAULT_VAT = '23'

interface FormState {
  description_pt_pt: string
  description_en: string
  summary: string
  type: string
  catalog_id: string
  is_circular: boolean
  altura: string
  largura: string
  profundidade: string
  price_lojista: string
  price_corporativo: string
  price_pvp: string
  price_arquiteto: string
  vat_rate: string
  observacao: string
  optional_applications: OptionalApplicationInput[]
}

const EMPTY_FORM: FormState = {
  description_pt_pt: '', description_en: '', summary: '', type: NO_TYPE, catalog_id: '',
  is_circular: false, altura: '', largura: '', profundidade: '0',
  price_lojista: '0', price_corporativo: '0', price_pvp: '0', price_arquiteto: '0',
  vat_rate: DEFAULT_VAT, observacao: '', optional_applications: [],
}

const asText = (value: number | string | null | undefined, fallback = '') =>
  value === null || value === undefined ? fallback : String(value)

function applicationsOf(prototype: Product): OptionalApplicationInput[] {
  return (prototype.optional_applications ?? []).map(app => ({
    id: app.id,
    category_id: app.category_id,
    name: app.name,
    name_en: app.name_en,
    required: app.required,
    display_order: app.display_order,
    allow_all: app.allow_all,
    allow_repeat: app.allow_repeat,
    allowed_optional_ids: app.allow_all ? [] : app.allowed_optionals.map(option => option.id),
  }))
}

function formOf(prototype: Product): FormState {
  const prices = prototype.market_prices ?? {}
  return {
    description_pt_pt: prototype.description_pt_pt ?? prototype.description,
    description_en: prototype.description_en ?? '',
    summary: prototype.summary ?? '',
    type: prototype.type,
    catalog_id: prototype.catalog_id ?? '',
    is_circular: prototype.is_circular,
    altura: asText(prototype.altura),
    largura: asText(prototype.largura),
    profundidade: asText(prototype.profundidade, '0'),
    price_lojista: asText(prices.lojista, '0'),
    price_corporativo: asText(prices.corporativo, '0'),
    price_pvp: asText(prices.pvp, '0'),
    price_arquiteto: asText(prices.arquiteto, '0'),
    vat_rate: asText(prototype.vat_rate, DEFAULT_VAT),
    observacao: prototype.observacao ?? '',
    optional_applications: applicationsOf(prototype),
  }
}

function payloadOf(form: FormState): PrototypeInput {
  return {
    description_pt_pt: form.description_pt_pt.trim(),
    description_en: form.description_en.trim(),
    summary: form.summary.trim() || null,
    type: form.type,
    catalog_id: form.catalog_id,
    is_circular: form.is_circular,
    altura: Number(form.altura),
    largura: Number(form.largura),
    profundidade: Number(form.profundidade || 0),
    price_lojista: Number(form.price_lojista || 0),
    price_corporativo: Number(form.price_corporativo || 0),
    price_pvp: Number(form.price_pvp || 0),
    price_arquiteto: Number(form.price_arquiteto || 0),
    vat_rate: Number(form.vat_rate),
    observacao: form.observacao.trim() || null,
    optional_applications: form.optional_applications.map(app => ({
      ...app,
      name: app.name.trim(),
      allowed_optional_ids: app.allow_all ? [] : app.allowed_optional_ids,
    })),
  }
}

function formError(form: FormState): string | null {
  if (!form.description_pt_pt.trim() || !form.description_en.trim()) return 'Informe o nome em português e em inglês.'
  if (!form.catalog_id) return 'Escolha o catálogo.'
  if (form.altura === '' || form.largura === '') return 'Informe altura e largura (em metros).'
  const vat = Number(form.vat_rate)
  if (form.vat_rate === '' || Number.isNaN(vat) || vat < 0 || vat > 100) return 'IVA deve estar entre 0 e 100.'
  if (form.optional_applications.some(app => !app.name.trim())) return 'Dê um nome a cada aplicação de opcional.'
  return null
}

function money(value: number | string | undefined) {
  return value === undefined ? '—' : `${Number(value).toFixed(2)} €`
}

// ── Grupos de opcionais só deste protótipo ────────────────────────────────────

function LocalGroups({ prototype, applications, onApplications }: {
  prototype: Product
  applications: OptionalApplicationInput[]
  onApplications: (applications: OptionalApplicationInput[], saved: Product) => void
}) {
  const groups = usePrototypeOptionalGroups(prototype.id)
  const saveGroup = useSavePrototypeOptionalGroup()
  const removeGroup = useDeletePrototypeOptionalGroup()
  const update = useUpdatePrototype()
  const [editing, setEditing] = useState<{ id?: string; name: string; options: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!editing) return
    const names = editing.options.split('\n').map(line => line.trim()).filter(Boolean)
    if (!editing.name.trim() || names.length === 0) {
      setError('Informe o nome do grupo e ao menos uma opção (uma por linha).')
      return
    }
    setError(null)
    try {
      const existing = editing.id ? groups.data?.find(group => group.id === editing.id) : undefined
      const kept = new Map((existing?.options ?? []).map(option => [option.name.toLowerCase(), option.id]))
      const saved = await saveGroup.mutateAsync({
        prototypeId: prototype.id,
        groupId: editing.id,
        data: {
          name: editing.name.trim(),
          options: names.map(name => ({ id: kept.get(name.toLowerCase()), name })),
        },
      })
      if (!editing.id) {
        // Grupo novo: já entra no protótipo como uma aplicação com todas as opções.
        const next: OptionalApplicationInput[] = [...applications, {
          category_id: saved.id, name: saved.name, name_en: null, required: false,
          display_order: applications.length, allow_all: true, allow_repeat: true, allowed_optional_ids: [],
        }]
        const response = await update.mutateAsync({ id: prototype.id, data: { optional_applications: next } })
        onApplications(applicationsOf(response), response)
      }
      setEditing(null)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  async function remove(group: PrototypeOptionalGroup) {
    if (!window.confirm(`Apagar o grupo "${group.name}"? Orçamentos já feitos não mudam.`)) return
    setError(null)
    try {
      await removeGroup.mutateAsync({ prototypeId: prototype.id, groupId: group.id })
      onApplications(applications.filter(app => app.category_id !== group.id), prototype)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  return (
    <section aria-label="Grupos só deste protótipo" className="rounded-xl border border-line p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">Grupos só deste protótipo</h3>
          <p className="text-xs text-muted">Ficam salvos neste protótipo e não aparecem na lista geral de opcionais.</p>
        </div>
        <button type="button" className="btn-secondary inline-flex items-center gap-1 text-xs"
          onClick={() => { setEditing({ name: '', options: '' }); setError(null) }}>
          <Plus className="h-4 w-4" aria-hidden="true" /> Novo grupo
        </button>
      </div>
      {error && <p role="alert" className="text-xs font-medium text-danger">{error}</p>}
      {(groups.data ?? []).map(group => (
        <div key={group.id} className="rounded-lg border border-line bg-surface-2 p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">{group.name}</p>
              <p className="text-xs text-muted">{group.options.map(option => option.name).join(' · ')}</p>
            </div>
            <div className="flex shrink-0 gap-1">
              <button type="button" className="btn-icon" aria-label={`Editar grupo ${group.name}`}
                onClick={() => { setEditing({ id: group.id, name: group.name, options: group.options.map(option => option.name).join('\n') }); setError(null) }}>
                <Pencil className="h-4 w-4" aria-hidden="true" />
              </button>
              <button type="button" className="btn-icon text-danger" aria-label={`Apagar grupo ${group.name}`} onClick={() => void remove(group)}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      ))}
      {editing && (
        <div className="space-y-2 rounded-lg border border-line p-3">
          <label className="block text-xs text-muted">Nome do grupo *
            <input className="input mt-1 w-full" maxLength={100} value={editing.name}
              onChange={event => setEditing({ ...editing, name: event.target.value })} placeholder="Ex.: Acabamento do tampo" />
          </label>
          <label className="block text-xs text-muted">Opções * (uma por linha)
            <textarea className="input mt-1 w-full" rows={4} value={editing.options}
              onChange={event => setEditing({ ...editing, options: event.target.value })} />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary text-xs" onClick={() => setEditing(null)}>Cancelar</button>
            <button type="button" className="btn-primary text-xs" disabled={saveGroup.isPending || update.isPending} onClick={() => void submit()}>
              {saveGroup.isPending || update.isPending ? 'Salvando…' : 'Salvar grupo'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Formulário ────────────────────────────────────────────────────────────────

function PrototypeForm({ initial, onClose }: { initial: Product | null; onClose: () => void }) {
  const { data: catalogs = [] } = useCatalogs()
  const { data: types = [] } = useProductTypes()
  const { data: categories = [] } = useOptionalCategories()
  const create = useCreatePrototype()
  const update = useUpdatePrototype()
  const [saved, setSaved] = useState<Product | null>(initial)
  const [form, setForm] = useState<FormState>(initial ? formOf(initial) : EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const generalIds = useMemo(() => new Set(categories.map(category => category.id)), [categories])
  const usedGeneral = categories.filter(category => form.optional_applications.some(app => app.category_id === category.id))
  const freeGeneral = categories.filter(category => !usedGeneral.includes(category))
  const { data: allOptionals = [] } = useOptionalsForCategories(usedGeneral.map(category => category.code), usedGeneral.length > 0)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm(previous => ({ ...previous, [key]: value }))
  const field = (key: keyof FormState, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="block text-xs text-muted">{label}
      <input className="input mt-1 w-full" value={String(form[key])} onChange={event => set(key, event.target.value as never)} {...props} />
    </label>
  )

  function addGeneralCategory(categoryId: string) {
    const category = categories.find(candidate => candidate.id === categoryId)
    if (!category) return
    set('optional_applications', [...form.optional_applications, {
      category_id: category.id, name: category.name, name_en: null, required: false,
      display_order: form.optional_applications.length, allow_all: true, allow_repeat: true, allowed_optional_ids: [],
    }])
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const problem = formError(form)
    if (problem) { setError(problem); return }
    setError(null)
    setNotice(null)
    try {
      const response = saved
        ? await update.mutateAsync({ id: saved.id, data: payloadOf(form) })
        : await create.mutateAsync(payloadOf(form))
      setSaved(response)
      setForm(formOf(response))
      setNotice(saved ? 'Protótipo atualizado.' : `Protótipo ${response.product_code} criado. Agora você pode adicionar fotos e grupos de opcionais.`)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  const busy = create.isPending || update.isPending
  const localApplications = form.optional_applications.filter(app => !generalIds.has(app.category_id))

  return (
    <form onSubmit={submit} className="space-y-5 rounded-2xl border border-line bg-white p-5 shadow-sm" aria-label="Formulário de protótipo">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">{saved ? 'Editar protótipo' : 'Novo protótipo'}</h2>
          <p className="text-xs text-muted">Código: <strong className="text-ink">{saved?.product_code ?? 'PROT-xxxx (automático)'}</strong></p>
        </div>
        <button type="button" className="btn-icon" aria-label="Fechar" onClick={onClose}><X className="h-5 w-5" aria-hidden="true" /></button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {field('description_pt_pt', 'Nome em português *', { maxLength: 20000, required: true })}
        {field('description_en', 'Nome em inglês *', { maxLength: 20000, required: true })}
        <label className="block text-xs text-muted sm:col-span-2">Resumo
          <input className="input mt-1 w-full" maxLength={1000} value={form.summary} onChange={event => set('summary', event.target.value)} />
        </label>
        <label className="block text-xs text-muted">Tipo
          <select className="input mt-1 w-full" value={form.type} onChange={event => set('type', event.target.value)}>
            <option value={NO_TYPE}>Sem tipo</option>
            {types.map(type => <option key={type.id} value={type.name}>{type.name}</option>)}
          </select>
        </label>
        <label className="block text-xs text-muted">Catálogo *
          <select className="input mt-1 w-full" value={form.catalog_id} onChange={event => set('catalog_id', event.target.value)} required>
            <option value="">Escolha…</option>
            {catalogs.map(catalog => <option key={catalog.id} value={catalog.id}>{catalog.name}</option>)}
          </select>
        </label>
      </div>

      <fieldset className="grid gap-3 sm:grid-cols-4">
        <legend className="mb-1 text-xs font-semibold text-ink">Medidas (em metros)</legend>
        {field('altura', 'Altura *', { type: 'number', step: '0.01', min: 0, max: 20, required: true })}
        {field('largura', 'Largura *', { type: 'number', step: '0.01', min: 0, max: 20, required: true })}
        {field('profundidade', 'Profundidade', { type: 'number', step: '0.01', min: 0, max: 20 })}
        <label className="flex items-end gap-2 pb-2 text-xs text-ink-2">
          <input type="checkbox" checked={form.is_circular} onChange={event => set('is_circular', event.target.checked)} /> Circular
        </label>
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-5">
        <legend className="mb-1 text-xs font-semibold text-ink">Preços (EUR) e IVA</legend>
        {field('price_lojista', 'Lojista', { type: 'number', step: '0.01', min: 0 })}
        {field('price_corporativo', 'Corporativo', { type: 'number', step: '0.01', min: 0 })}
        {field('price_pvp', 'PVP', { type: 'number', step: '0.01', min: 0 })}
        {field('price_arquiteto', 'Arquiteto', { type: 'number', step: '0.01', min: 0 })}
        {field('vat_rate', 'IVA (%)', { type: 'number', step: '0.01', min: 0, max: 100, required: true })}
      </fieldset>

      <label className="block text-xs text-muted">Observação
        <textarea className="input mt-1 w-full" rows={2} maxLength={20000} value={form.observacao} onChange={event => set('observacao', event.target.value)} />
      </label>

      <section aria-label="Opcionais já cadastrados" className="space-y-2 rounded-xl border border-line p-4">
        <h3 className="text-sm font-semibold text-ink">Opcionais já cadastrados</h3>
        <p className="text-xs text-muted">Opcional: escolha grupos que já existem e quais opções valem neste protótipo.</p>
        {freeGeneral.length > 0 && (
          <label className="block text-xs text-muted">Adicionar grupo
            <select className="input mt-1 w-full sm:w-72" value="" onChange={event => addGeneralCategory(event.target.value)}>
              <option value="">Escolha um grupo…</option>
              {freeGeneral.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
          </label>
        )}
        {usedGeneral.map(category => (
          <div key={category.id}>
            <p className="text-xs font-semibold text-ink-2">{category.name}</p>
            <OptionalApplicationGroup
              category={category}
              optionals={allOptionals.filter(option => option.category === category.code)}
              applications={form.optional_applications}
              onChange={applications => set('optional_applications', applications)}
              onFirstAdd={() => undefined}
              initialAllowedIds={[]}
              initialAllowAll
            />
          </div>
        ))}
      </section>

      {error && <p role="alert" className="text-sm font-medium text-danger">{error}</p>}
      {notice && <p role="status" className="text-sm text-emerald-800">{notice}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onClose}>Fechar</button>
        <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Salvando…' : saved ? 'Salvar alterações' : 'Criar protótipo'}</button>
      </div>

      {saved ? (
        <>
          <ProductPhotosManager key={saved.id} product={saved} color={EU_GREEN} basePath={PROTOTYPES_PATH}
            onUpdated={updated => setSaved(updated)} />
          <LocalGroups prototype={saved} applications={form.optional_applications}
            onApplications={(applications, response) => { set('optional_applications', applications); setSaved(response) }} />
          {localApplications.length > 0 && (
            <p className="text-[11px] text-muted">
              {localApplications.length} aplicação(ões) de grupos próprios ficam neste protótipo e vão junto ao salvar.
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-muted">Salve o protótipo para adicionar fotos e criar grupos de opcionais só dele.</p>
      )}
    </form>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function PrototiposPage() {
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Product | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const remove = useDeletePrototype()
  const list = usePrototypesPage({ skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE, q: search.trim() || undefined })
  const items = list.data?.items ?? []
  const totalPages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE))

  if (!user?.can_manage_prototypes) return null

  async function confirmRemove(prototype: Product) {
    if (!window.confirm(`Desativar o protótipo ${prototype.product_code}? Orçamentos já feitos não mudam e o código não volta a ser usado.`)) return
    setError(null)
    try {
      await remove.mutateAsync(prototype.id)
      if (editing !== 'new' && editing?.id === prototype.id) setEditing(null)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  return (
    <div className="min-h-screen bg-bg pb-24 md:pb-8">
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 md:px-6 md:py-8">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-ink md:text-2xl">Protótipos</h1>
            <p className="mt-1 text-sm text-muted">Só você vê estes itens. Eles entram nos seus orçamentos e não aparecem no catálogo dos outros.</p>
          </div>
          <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setEditing('new')}>
            <Plus className="h-4 w-4" aria-hidden="true" /> Novo protótipo
          </button>
        </header>

        {editing && (
          <PrototypeForm key={editing === 'new' ? 'new' : editing.id} initial={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
        )}

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
          <input className="input w-full pl-9" placeholder="Buscar por código ou nome" aria-label="Buscar protótipos"
            value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} />
        </div>

        {error && <p role="alert" className="text-sm font-medium text-danger">{error}</p>}
        {list.isError && <p role="alert" className="text-sm font-medium text-danger">Não foi possível carregar os protótipos.</p>}
        {list.isLoading && <p className="text-sm text-muted">Carregando…</p>}
        {!list.isLoading && !list.isError && items.length === 0 && (
          <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
            {search.trim() ? 'Nenhum protótipo encontrado.' : 'Você ainda não criou protótipos.'}
          </p>
        )}

        <ul className="grid gap-3 sm:grid-cols-2" aria-label="Meus protótipos">
          {items.map(prototype => (
            <li key={prototype.id} className="flex gap-3 rounded-xl border border-line bg-white p-3 shadow-sm">
              <div className="h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-surface-2">
                {(prototype.thumbnail_url ?? prototype.photo_url)
                  ? <img src={prototype.thumbnail_url ?? prototype.photo_url ?? ''} alt="" className="h-full w-full object-cover" loading="lazy" />
                  : null}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold tracking-wider text-gold">{prototype.product_code}</p>
                <p className="truncate text-sm font-medium text-ink">{prototype.description}</p>
                <p className="text-xs text-muted">PVP {money(prototype.market_prices?.pvp)} · Lojista {money(prototype.market_prices?.lojista)}</p>
                <div className="mt-2 flex gap-2">
                  <button type="button" className="btn-secondary inline-flex items-center gap-1 text-xs" onClick={() => setEditing(prototype)}>
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Editar
                  </button>
                  <button type="button" className="inline-flex items-center gap-1 text-xs text-danger" onClick={() => void confirmRemove(prototype)}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Desativar
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>

        {totalPages > 1 && (
          <nav className="flex items-center justify-center gap-3 text-sm" aria-label="Paginação">
            <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
            <span className="text-muted">Página {page} de {totalPages}</span>
            <button type="button" className="btn-secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Seguinte</button>
          </nav>
        )}
      </div>
    </div>
  )
}
