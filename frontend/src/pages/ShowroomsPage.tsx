import { useMemo, useState } from 'react'
import { Boxes, ChevronRight, Edit3, Image as ImageIcon, PackagePlus, Plus, Search, Trash2, Warehouse, X } from 'lucide-react'
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
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">Nome da box</span>
            <input autoFocus required maxLength={120} className="input" placeholder="Ex.: Estoque Portugal" value={name} onChange={event => setName(event.target.value)} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">Tabela de preço</span>
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
  const selected = boxes.find(box => box.id === selectedId) ?? boxes[0]
  const productsQuery = useShowroomProducts(selected?.price_list_code, search)
  const existing = useMemo(() => new Set(selected?.items.map(item => item.id) ?? []), [selected])

  if (!user?.can_manage_showrooms || user.active_market !== 'EU') return null

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
      <header className="flex justify-end">
        <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => setDialog('create')}><Plus className="h-4 w-4" /> Nova box</button>
      </header>

      {message && <p role="alert" className="mt-4 rounded-xl border border-terracotta/20 bg-white px-4 py-3 text-sm text-terracotta">{message}</p>}

      {boxesQuery.isLoading ? (
        <div className="mt-6 rounded-2xl bg-white p-8 text-center text-sm text-muted shadow-sm">Carregando boxes…</div>
      ) : boxesQuery.isError ? (
        <div className="mt-6 rounded-2xl bg-white p-8 text-center shadow-sm"><p className="text-sm text-terracotta">Não foi possível carregar o estoque.</p><button className="btn-secondary mt-4" onClick={() => boxesQuery.refetch()}>Tentar novamente</button></div>
      ) : boxes.length === 0 ? (
        <div className="mt-6 flex min-h-64 flex-col items-center justify-center rounded-2xl border border-line bg-white p-8 text-center shadow-sm">
          <Boxes className="h-9 w-9 text-gold" />
          <h2 className="mt-4 font-display text-2xl font-semibold text-ink">Nenhuma box criada</h2>
          <p className="mt-1 max-w-md text-sm text-muted">Crie uma box para cada local de estoque, feira ou exposição e adicione os produtos que estão fisicamente ali.</p>
          <button className="btn-primary mt-5" onClick={() => setDialog('create')}>Criar primeira box</button>
        </div>
      ) : selected && (
        <div className="mt-6 grid items-start gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-line">
            <div className="flex items-center gap-2 border-b border-line px-4 py-3"><Warehouse className="h-4 w-4 text-gold" /><h2 className="text-sm font-semibold text-ink">Boxes</h2></div>
            <div className="divide-y divide-line">
              {boxes.map(box => {
                const active = box.id === selected.id
                return <button key={box.id} type="button" onClick={() => { setSelectedId(box.id); setSearch('') }} className={`flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors ${active ? 'bg-gold/10' : 'hover:bg-surface-2'}`}>
                  <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${active ? 'bg-gold text-white' : 'bg-surface-warm text-gold'}`}><Boxes className="h-4 w-4" /></span>
                  <span className="min-w-0 flex-1"><strong className="block truncate text-sm text-ink">{box.name}</strong><span className="block text-xs text-muted">{box.total_quantity} peças · {PRICE_LABEL[box.price_list_code]}</span></span>
                  <ChevronRight className={`h-4 w-4 ${active ? 'text-gold' : 'text-muted-3'}`} />
                </button>
              })}
            </div>
          </aside>

          <main className="min-w-0 space-y-5">
            <section className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-line">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-5">
                <div>
                  <div className="flex flex-wrap items-center gap-2"><h2 className="font-display text-2xl font-semibold text-ink">{selected.name}</h2><span className="rounded-full bg-gold/10 px-2.5 py-1 text-xs font-semibold text-gold">{PRICE_LABEL[selected.price_list_code]}</span></div>
                  <p className="mt-1 text-xs text-muted">{selected.item_count} produtos diferentes · {selected.total_quantity} peças</p>
                </div>
                <div className="flex items-center gap-1">
                  <button type="button" className="btn-secondary inline-flex items-center gap-2" onClick={() => setDialog('edit')}><Edit3 className="h-4 w-4" /> Editar</button>
                  <button type="button" className="grid min-h-11 min-w-11 place-items-center rounded-lg text-terracotta hover:bg-terracotta/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta/30" onClick={() => void confirmDeleteBox()} aria-label="Excluir box"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>

              {selected.items.length === 0 ? (
                <div className="px-5 py-12 text-center"><PackagePlus className="mx-auto h-8 w-8 text-muted-3" /><p className="mt-3 text-sm font-medium text-ink">Esta box ainda está vazia.</p><p className="mt-1 text-xs text-muted">Use a busca abaixo para adicionar produtos de Portugal.</p></div>
              ) : (
                <>
                  <div className="hidden overflow-x-auto md:block">
                    <table className="w-full text-sm">
                      <thead className="bg-surface-2 text-xs uppercase tracking-wider text-muted"><tr><th className="px-5 py-3 text-left">Produto</th><th className="px-4 py-3 text-center">Quantidade</th><th className="px-4 py-3 text-right">Valor unitário</th><th className="px-4 py-3 text-right">Total</th><th className="w-14 px-3 py-3"><span className="sr-only">Ações</span></th></tr></thead>
                      <tbody className="divide-y divide-line">
                        {selected.items.map(item => <tr key={item.item_id} className="hover:bg-surface-2/60"><td className="px-5 py-3"><div className="flex items-center gap-3"><div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0"><span className="font-mono text-xs font-semibold text-gold">{item.product_code}</span><p className="max-w-xl truncate font-medium text-ink">{item.description}</p></div></div></td><td className="px-4 py-3 text-center"><QuantityField boxId={selected.id} item={item} /></td><td className="px-4 py-3 text-right tabular-nums text-ink-2">{money(item.unit_price)}</td><td className="px-4 py-3 text-right font-semibold tabular-nums text-ink">{money(item.line_total)}</td><td className="px-3 py-3"><button className="grid min-h-11 min-w-11 place-items-center rounded-lg text-muted hover:bg-terracotta/10 hover:text-terracotta" aria-label={`Remover ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></td></tr>)}
                      </tbody>
                    </table>
                  </div>
                  <div className="divide-y divide-line md:hidden">
                    {selected.items.map(item => <article key={item.item_id} className="p-4"><div className="flex gap-3"><div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-bg ring-1 ring-line">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <ImageIcon className="h-5 w-5 text-muted-3" />}</div><div className="min-w-0 flex-1"><p className="font-mono text-xs font-semibold text-gold">{item.product_code}</p><p className="line-clamp-2 text-sm font-medium text-ink">{item.description}</p></div><button className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-muted hover:text-terracotta" aria-label={`Remover ${item.product_code}`} onClick={() => void removeProduct(item)}><Trash2 className="h-4 w-4" /></button></div><div className="mt-3 grid grid-cols-[auto_1fr] items-end gap-4"><QuantityField boxId={selected.id} item={item} /><div className="text-right"><p className="text-xs text-muted">{money(item.unit_price)} por unidade</p><p className="font-semibold tabular-nums text-ink">{money(item.line_total)}</p></div></div></article>)}
                  </div>
                </>
              )}

              <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-4"><span className="text-xs font-semibold uppercase tracking-wider text-muted">Valor total da box</span><strong className="font-display text-3xl font-semibold tabular-nums text-gold">{money(selected.total_value)}</strong></footer>
            </section>

            <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-line sm:p-5">
              <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="font-display text-xl font-semibold text-ink">Adicionar produtos</h2><p className="mt-0.5 text-xs text-muted">Os valores abaixo usam a tabela {PRICE_LABEL[selected.price_list_code]}.</p></div><div className="relative w-full sm:w-80"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-3" /><input className="input w-full pl-9" type="search" placeholder="Buscar por código ou nome" value={search} onChange={event => setSearch(event.target.value)} /></div></div>
              <div className="mt-4 divide-y divide-line overflow-hidden rounded-xl border border-line">
                {productsQuery.isLoading ? <p className="p-5 text-center text-sm text-muted">Buscando produtos…</p> : productsQuery.isError ? <p className="p-5 text-center text-sm text-terracotta">Não foi possível consultar os produtos.</p> : productsQuery.data?.length === 0 ? <p className="p-5 text-center text-sm text-muted">Nenhum produto encontrado.</p> : productsQuery.data?.map(product => {
                  const added = existing.has(product.id)
                  return <div key={product.id} className="flex items-center gap-3 px-3 py-3 sm:px-4"><div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-lg bg-bg ring-1 ring-line">{product.thumbnail_url ? <img src={product.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" /> : <ImageIcon className="h-4 w-4 text-muted-3" />}</div><div className="min-w-0 flex-1"><p className="font-mono text-[11px] font-semibold text-gold">{product.product_code}</p><p className="truncate text-sm font-medium text-ink">{product.description}</p></div><span className="hidden text-sm tabular-nums text-ink-2 sm:block">{money(product.unit_price)}</span><button type="button" disabled={addItem.isPending} className={added ? 'btn-secondary min-w-24' : 'btn-primary min-w-24'} onClick={() => void addProduct(product.id)}>{added ? 'Somar +1' : 'Adicionar'}</button></div>
                })}
              </div>
            </section>
          </main>
        </div>
      )}

      {dialog === 'create' && <BoxDialog onClose={() => setDialog(null)} />}
      {dialog === 'edit' && selected && <BoxDialog box={selected} onClose={() => setDialog(null)} />}
    </div>
  )
}
