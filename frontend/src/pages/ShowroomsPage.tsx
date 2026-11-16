import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowUpRight,
  Boxes,
  Edit3,
  Image as ImageIcon,
  PackagePlus,
  Plus,
  Search,
  Trash2,
  Warehouse,
  X,
} from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import {
  type ShowroomBox,
  type ShowroomItem,
  type ShowroomPriceList,
  useAddShowroomItem,
  useCreateShowroomBox,
  useDeleteShowroomBox,
  useRemoveShowroomItem,
  useShowroomBoxes,
  useShowroomProducts,
  useUpdateShowroomBox,
  useUpdateShowroomItem,
} from '../hooks/useShowrooms'

const PRICE_LABEL: Record<ShowroomPriceList, string> = {
  lojista: 'Lojista',
  arquiteto: 'Arquiteto',
  corporativo: 'Corporativo',
  pvp: 'PVP',
}

const PRICE_OPTIONS = Object.keys(PRICE_LABEL) as ShowroomPriceList[]

function money(value: number | string) {
  return new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number(value))
}

function errorDetail(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: string | Array<{ msg?: string }> } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg).filter(Boolean).join(' ') || fallback
  return fallback
}

function QuantityField({ boxId, item }: { boxId: string; item: ShowroomItem }) {
  const update = useUpdateShowroomItem()
  const [draft, setDraft] = useState<string | null>(null)
  const value = draft ?? String(item.quantity)

  function commit() {
    const quantity = Math.max(1, Math.floor(Number(value) || 1))
    setDraft(null)
    if (quantity !== item.quantity) update.mutate({ boxId, itemId: item.item_id, quantity })
  }

  return (
    <input
      aria-label={`Quantidade de ${item.product_code}`}
      className="input h-10 w-20 text-center tabular-nums"
      type="number"
      min="1"
      max="1000000"
      inputMode="numeric"
      value={value}
      disabled={update.isPending}
      onChange={event => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}
    />
  )
}

function BoxDialog({ box, onClose }: { box?: ShowroomBox; onClose: () => void }) {
  const create = useCreateShowroomBox()
  const update = useUpdateShowroomBox()
  const [name, setName] = useState(box?.name ?? '')
  const [priceList, setPriceList] = useState<ShowroomPriceList>(box?.price_list_code ?? 'lojista')
  const [error, setError] = useState<string | null>(null)
  const pending = create.isPending || update.isPending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      if (box) await update.mutateAsync({ id: box.id, name: name.trim(), price_list_code: priceList })
      else await create.mutateAsync({ name: name.trim(), price_list_code: priceList })
      onClose()
    } catch (requestError) {
      setError(errorDetail(requestError, 'Não foi possível salvar a box.'))
    }
  }

  return (
    <div className="modal-overlay fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" role="presentation">
      <form className="modal-panel w-full max-w-md p-5" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="box-dialog-title">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="box-dialog-title" className="font-display text-2xl font-semibold text-ink">{box ? 'Editar box' : 'Nova box'}</h2>
            <p className="mt-1 text-sm text-muted">A tabela escolhida define todos os valores desta box.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar" className="btn-icon -mr-2 -mt-2"><X className="h-5 w-5" /></button>
        </div>
        <div className="mt-5 space-y-4">
          <label className="flex flex-col gap-1.5">
            <span className="type-label">Nome da box</span>
            <input autoFocus required maxLength={120} className="input" placeholder="Ex.: Estoque Portugal" value={name} onChange={event => setName(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="type-label">Tabela de preço</span>
            <select className="input" value={priceList} onChange={event => setPriceList(event.target.value as ShowroomPriceList)}>
              {PRICE_OPTIONS.map(code => <option key={code} value={code}>{PRICE_LABEL[code]}</option>)}
            </select>
          </label>
          {error && <p role="alert" className="rounded-xl bg-terracotta/10 px-3 py-2 text-sm text-terracotta">{error}</p>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn-primary" disabled={pending || !name.trim()}>{pending ? 'Salvando…' : 'Salvar box'}</button>
        </div>
      </form>
    </div>
  )
}

function BoxCard({ box, onOpen }: { box: ShowroomBox; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Abrir ${box.name}`}
      className="group min-h-64 overflow-hidden rounded-2xl border border-line bg-white text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-gold/35 hover:shadow-lg hover:shadow-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/35"
    >
      <span className="flex h-full flex-col">
        <span className="flex items-start justify-between gap-4 p-5">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-surface-warm text-gold ring-1 ring-gold/10"><Warehouse className="h-5 w-5" /></span>
          <span className="rounded-full bg-gold/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-gold">{PRICE_LABEL[box.price_list_code]}</span>
        </span>
        <span className="flex-1 px-5">
          <strong className="block font-display text-2xl font-semibold leading-tight text-ink">{box.name}</strong>
          <span className="mt-2 block text-sm text-muted">{box.item_count} produtos diferentes</span>
        </span>
        <span className="mt-5 grid grid-cols-[1fr_auto] items-end gap-4 border-t border-line bg-surface-2/70 px-5 py-4">
          <span>
            <span className="type-label block">Valor total</span>
            <span className="mt-1 block font-display text-2xl font-semibold tabular-nums text-ink">{money(box.total_value)}</span>
          </span>
          <span className="flex items-center gap-3">
            <span className="text-right"><span className="block text-xl font-semibold tabular-nums text-ink">{box.total_quantity}</span><span className="type-meta">peças</span></span>
            <span className="grid h-9 w-9 place-items-center rounded-full border border-line bg-white text-gold transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"><ArrowUpRight className="h-4 w-4" /></span>
          </span>
        </span>
      </span>
    </button>
  )
}

export default function ShowroomsPage() {
  const { user } = useAuth()
  const boxesQuery = useShowroomBoxes()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<'create' | 'edit' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const addItem = useAddShowroomItem()
  const removeItem = useRemoveShowroomItem()
  const removeBox = useDeleteShowroomBox()
  const boxes = boxesQuery.data ?? []
  const selected = selectedId ? boxes.find(box => box.id === selectedId) : undefined
  const productsQuery = useShowroomProducts(selected?.price_list_code, search)
  const existing = useMemo(() => new Set(selected?.items.map(item => item.id) ?? []), [selected])

  if (!user?.can_manage_showrooms || user.active_market !== 'EU') return null

  function openBox(id: string) {
    setSearch('')
    setMessage(null)
    setSelectedId(id)
  }

  function closeBox() {
    setSearch('')
    setMessage(null)
    setSelectedId(null)
  }

  async function confirmDeleteBox() {
    if (!selected || !window.confirm(`Excluir a box “${selected.name}” e todos os produtos dela?`)) return
    setMessage(null)
    try {
      await removeBox.mutateAsync(selected.id)
      setSelectedId(null)
    } catch (error) {
      setMessage(errorDetail(error, 'Não foi possível excluir a box.'))
    }
  }

  async function addProduct(productId: string) {
    if (!selected) return
    setMessage(null)
    try {
      await addItem.mutateAsync({ boxId: selected.id, productId })
    } catch (error) {
      setMessage(errorDetail(error, 'Não foi possível adicionar o produto.'))
    }
  }

  async function removeProduct(item: ShowroomItem) {
    if (!selected || !window.confirm(`Remover ${item.product_code} desta box?`)) return
    setMessage(null)
    try {
      await removeItem.mutateAsync({ boxId: selected.id, itemId: item.item_id })
    } catch (error) {
      setMessage(errorDetail(error, 'Não foi possível remover o produto.'))
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 pb-28 md:px-6 md:py-7 md:pb-10 lg:px-8">
      <h1 className="sr-only">Estoque</h1>

      {message && <p role="alert" className="mb-4 rounded-xl border border-terracotta/20 bg-white px-4 py-3 text-sm text-terracotta shadow-sm">{message}</p>}

      {boxesQuery.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Carregando boxes">
          {[0, 1, 2].map(item => <div key={item} className="h-64 animate-pulse rounded-2xl border border-line bg-white shadow-sm" />)}
        </div>
      ) : boxesQuery.isError ? (
        <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-line bg-white p-8 text-center shadow-sm">
          <p className="text-sm text-terracotta">Não foi possível carregar o estoque.</p>
          <button className="btn-secondary mt-4" onClick={() => boxesQuery.refetch()}>Tentar novamente</button>
        </div>
      ) : boxes.length === 0 ? (
        <div className="flex min-h-80 flex-col items-center justify-center rounded-2xl border border-line bg-white p-8 text-center shadow-sm">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-surface-warm text-gold"><Boxes className="h-6 w-6" /></span>
          <h2 className="mt-5 font-display text-2xl font-semibold text-ink">Nenhuma box criada</h2>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">Crie uma box para cada local de estoque, feira ou exposição e adicione os produtos que estão fisicamente ali.</p>
          <button className="btn-primary mt-6 inline-flex items-center gap-2" onClick={() => setDialog('create')}><Plus className="h-4 w-4" /> Criar primeira box</button>
        </div>
      ) : !selected ? (
        <>
          <div className="mb-5 flex justify-end">
            <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setDialog('create')}><Plus className="h-4 w-4" /> Nova box</button>
          </div>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Boxes do estoque">
            {boxes.map(box => <BoxCard key={box.id} box={box} onOpen={() => openBox(box.id)} />)}
          </section>
        </>
      ) : (
        <div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <button type="button" onClick={closeBox} className="btn-secondary inline-flex items-center gap-2"><ArrowLeft className="h-4 w-4" /> Todas as boxes</button>
            <div className="flex items-center gap-2">
              <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => setDialog('edit')}><Edit3 className="h-4 w-4" /> Editar box</button>
              <button type="button" className="grid min-h-11 min-w-11 place-items-center rounded-lg border border-line bg-white text-muted shadow-sm transition-colors hover:border-terracotta/30 hover:bg-terracotta/10 hover:text-terracotta focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta/30" onClick={() => void confirmDeleteBox()} aria-label="Excluir box"><Trash2 className="h-4 w-4" /></button>
            </div>
          </div>

          <section className="overflow-hidden rounded-2xl border border-line bg-white shadow-sm" aria-labelledby="selected-box-title">
            <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-5 sm:px-6">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-warm text-gold"><Warehouse className="h-5 w-5" /></span>
                  <h2 id="selected-box-title" className="font-display text-3xl font-semibold leading-tight text-ink sm:text-4xl">{selected.name}</h2>
                </div>
                <p className="mt-2 text-sm text-muted">Valores calculados pela tabela {PRICE_LABEL[selected.price_list_code]}.</p>
              </div>
              <span className="rounded-full bg-gold/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-gold">{PRICE_LABEL[selected.price_list_code]}</span>
            </div>
            <div className="grid grid-cols-2 border-t border-line bg-surface-2/70 sm:grid-cols-[1fr_1fr_1.5fr]">
              <div className="px-5 py-4 sm:px-6"><span className="type-label block">Produtos</span><strong className="mt-1 block text-2xl font-semibold tabular-nums text-ink">{selected.item_count}</strong></div>
              <div className="border-l border-line px-5 py-4 sm:px-6"><span className="type-label block">Quantidade</span><strong className="mt-1 block text-2xl font-semibold tabular-nums text-ink">{selected.total_quantity}</strong></div>
              <div className="col-span-2 border-t border-line px-5 py-4 sm:col-span-1 sm:border-l sm:border-t-0 sm:px-6 sm:text-right"><span className="type-label block">Valor total</span><strong className="mt-1 block font-display text-3xl font-semibold tabular-nums text-gold">{money(selected.total_value)}</strong></div>
            </div>
          </section>

          <div className="mt-5 grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <section className="overflow-hidden rounded-2xl border border-line bg-white shadow-sm" aria-labelledby="box-products-title">
              <div className="border-b border-line px-5 py-4 sm:px-6"><h3 id="box-products-title" className="font-display text-xl font-semibold text-ink">Produtos nesta box</h3></div>

              {selected.items.length === 0 ? (
                <div className="flex min-h-64 flex-col items-center justify-center px-5 py-12 text-center">
                  <span className="grid h-12 w-12 place-items-center rounded-2xl bg-surface-2 text-muted-3"><PackagePlus className="h-5 w-5" /></span>
                  <p className="mt-4 text-sm font-semibold text-ink">Esta box ainda está vazia</p>
                  <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted">Adicione o primeiro produto usando a busca ao lado.</p>
                </div>
              ) : (
                <>
                  <div className="hidden overflow-x-auto md:block">
                    <table className="w-full text-sm">
                      <thead className="bg-surface-2 text-xs uppercase tracking-wider text-muted"><tr><th className="px-5 py-3 text-left sm:px-6">Produto</th><th className="px-4 py-3 text-center">Quantidade</th><th className="px-4 py-3 text-right">Unitário</th><th className="px-4 py-3 text-right">Total</th><th className="w-14 px-3 py-3"><span className="sr-only">Ações</span></th></tr></thead>
                      <tbody className="divide-y divide-line">
                        {selected.items.map(item => <tr key={item.item_id} className="transition-colors hover:bg-surface-2/60"><td className="px-5 py-3.5 sm:px-6"><div className="flex items-center gap-3"><div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0"><span className="type-code">{item.product_code}</span><p className="max-w-sm truncate font-medium text-ink">{item.description}</p></div></div></td><td className="px-4 py-3.5 text-center"><QuantityField boxId={selected.id} item={item} /></td><td className="px-4 py-3.5 text-right tabular-nums text-ink-2">{money(item.unit_price)}</td><td className="px-4 py-3.5 text-right font-semibold tabular-nums text-ink">{money(item.line_total)}</td><td className="px-3 py-3.5"><button className="grid min-h-11 min-w-11 place-items-center rounded-lg text-muted transition-colors hover:bg-terracotta/10 hover:text-terracotta" aria-label={`Remover ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></td></tr>)}
                      </tbody>
                    </table>
                  </div>
                  <div className="divide-y divide-line md:hidden">
                    {selected.items.map(item => <article key={item.item_id} className="p-4"><div className="flex gap-3"><div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0 flex-1"><p className="type-code">{item.product_code}</p><p className="line-clamp-2 text-sm font-medium text-ink">{item.description}</p></div><button className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:text-terracotta" aria-label={`Remover ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></div><div className="mt-4 grid grid-cols-[auto_1fr] items-end gap-4 border-t border-line pt-3"><QuantityField boxId={selected.id} item={item} /><div className="text-right"><p className="type-meta">{money(item.unit_price)} por unidade</p><p className="mt-0.5 font-semibold tabular-nums text-ink">{money(item.line_total)}</p></div></div></article>)}
                  </div>
                </>
              )}
            </section>

            <section className="rounded-2xl border border-line bg-white p-4 shadow-sm sm:p-5 xl:sticky xl:top-24" aria-labelledby="add-products-title">
              <div><h3 id="add-products-title" className="font-display text-xl font-semibold text-ink">Adicionar produtos</h3><p className="mt-1 text-xs leading-relaxed text-muted">Preços da tabela {PRICE_LABEL[selected.price_list_code]}.</p></div>
              <div className="relative mt-4"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-3" /><input className="input w-full pl-9" type="search" aria-label="Buscar produtos" placeholder="Código ou nome" value={search} onChange={event => setSearch(event.target.value)} /></div>
              <div className="mt-3 max-h-[34rem] divide-y divide-line overflow-y-auto rounded-xl border border-line">
                {productsQuery.isLoading ? <p className="p-5 text-center text-sm text-muted">Buscando produtos…</p> : productsQuery.isError ? <p className="p-5 text-center text-sm text-terracotta">Não foi possível consultar os produtos.</p> : productsQuery.data?.length === 0 ? <p className="p-5 text-center text-sm text-muted">Nenhum produto encontrado.</p> : productsQuery.data?.map(product => {
                  const added = existing.has(product.id)
                  return <div key={product.id} className="p-3"><div className="flex items-start gap-3"><div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-lg bg-bg ring-1 ring-line">{product.thumbnail_url ? <img src={product.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" /> : <ImageIcon className="h-4 w-4 text-muted-3" />}</div><div className="min-w-0 flex-1"><p className="type-code">{product.product_code}</p><p className="line-clamp-2 text-sm font-medium leading-snug text-ink">{product.description}</p><p className="mt-1 text-sm font-semibold tabular-nums text-ink-2">{money(product.unit_price)}</p></div></div><button type="button" disabled={addItem.isPending} className={`mt-3 w-full ${added ? 'btn-secondary' : 'btn-primary'}`} onClick={() => void addProduct(product.id)}>{added ? 'Adicionar mais uma' : 'Adicionar à box'}</button></div>
                })}
              </div>
            </section>
          </div>
        </div>
      )}

      {dialog === 'create' && <BoxDialog onClose={() => setDialog(null)} />}
      {dialog === 'edit' && selected && <BoxDialog box={selected} onClose={() => setDialog(null)} />}
    </div>
  )
}
