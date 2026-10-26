import { Layers3, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Dialog } from '../components/Dialog'
import { OptionalBenchPanel } from '../components/OptionalBenchPanel'
import { OptionalSwatchImage } from '../components/OptionalSwatchImage'
import { OptionalZoomDialog } from '../components/OptionalZoomDialog'
import { useAuth } from '../hooks/useAuth'
import { useLocale } from '../hooks/useLocale'
import { useOptionalBench } from '../hooks/useOptionalBench'
import { useOptionalCategories, type OptionalCategory } from '../hooks/useOptionalCategories'
import { useOptionals } from '../hooks/useOptionals'
import { hasOptionalPhoto } from '../lib/optionalMedia'
import type { OptionalColor } from '../types'

function normalizeSearch(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim()
}

function anchorId(code: string) {
  return `categoria-${normalizeSearch(code).replace(/[^a-z0-9]+/g, '-')}`
}

interface OptionalGroup {
  code: string
  label: string
  items: OptionalColor[]
  category: OptionalCategory | null
}

export default function OpcionaisPage() {
  const { user } = useAuth()
  const { locale } = useLocale()
  const english = locale === 'en-GB'
  const { data: optionals, isLoading: loadingOptionals, isError: optionalsError, refetch: refetchOptionals } = useOptionals(undefined, 5000)
  const { data: categories, isLoading: loadingCategories, isError: categoriesError, refetch: refetchCategories } = useOptionalCategories()
  const [query, setQuery] = useState('')
  const [zoomed, setZoomed] = useState<OptionalColor | null>(null)
  const [pendingReplacement, setPendingReplacement] = useState<OptionalColor | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [benchExpanded, setBenchExpanded] = useState(true)
  const bench = useOptionalBench(user?.id ?? '', user?.active_market ?? 'BR', optionals)

  const groups = useMemo<OptionalGroup[]>(() => {
    if (!categories || !optionals) return []
    const sortedCategories = [...categories].sort((left, right) =>
      left.display_order - right.display_order || left.name.localeCompare(right.name),
    )
    const knownCodes = new Set(sortedCategories.map(category => category.code))
    const registered = sortedCategories.map(category => ({
      code: category.code,
      label: category.name,
      category,
      items: optionals.filter(optional => optional.category === category.code),
    }))
    const orphaned = optionals.filter(optional => !knownCodes.has(optional.category))
    return orphaned.length > 0
      ? [...registered, { code: '__other__', label: english ? 'Other' : 'Outros', category: null, items: orphaned }]
      : registered
  }, [categories, english, optionals])

  const normalizedQuery = normalizeSearch(query)
  const visibleGroups = useMemo(() => groups
    .map(group => ({
      ...group,
      items: normalizedQuery
        ? group.items.filter(optional => normalizeSearch(optional.color_name).includes(normalizedQuery))
        : group.items,
    }))
    .filter(group => !normalizedQuery || group.items.length > 0), [groups, normalizedQuery])
  const resultCount = visibleGroups.reduce((total, group) => total + group.items.length, 0)
  const priorityIds = useMemo(() => new Set(
    visibleGroups.flatMap(group => group.items).slice(0, 5).map(optional => optional.id),
  ), [visibleGroups])
  const showType = Boolean(normalizedQuery && visibleGroups.length > 1)
  const isLoading = loadingOptionals || loadingCategories
  const isError = optionalsError || categoriesError
  const categoryName = (code: string) => categories?.find(category => category.code === code)?.name
    ?? (english ? 'Other' : 'Outros')

  function addToBench(optional: OptionalColor) {
    const result = bench.add(optional.id)
    if (result === 'full') {
      setPendingReplacement(optional)
      return
    }
    setAnnouncement(result === 'duplicate'
      ? (english ? `${optional.color_name} is already on the bench.` : `${optional.color_name} já está na bancada.`)
      : (english ? `${optional.color_name} added to the bench.` : `${optional.color_name} adicionada à bancada.`))
  }

  if (!user) return null

  return (
    <div className={`min-h-screen bg-bg px-4 py-6 md:px-8 md:py-9 ${bench.items.length > 0 ? (benchExpanded ? 'pb-[24rem] md:pb-[32rem]' : 'pb-24 md:pb-20') : ''}`}>
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-col gap-5 border-b border-line pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="font-display text-4xl leading-none text-ink md:text-5xl">{english ? 'Finishes' : 'Opcionais'}</h1>
            <p className="mt-2 text-sm text-muted">
              {user.active_market === 'EU' ? 'IBTW · Portugal' : 'ILYA · Brasil'}
            </p>
          </div>
          <label className="relative block w-full md:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <span className="sr-only">{english ? 'Search finishes by name' : 'Buscar opcionais por nome'}</span>
            <input
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder={english ? 'Search by name…' : 'Buscar por nome…'}
              className="input pl-9"
            />
          </label>
        </header>

        {!isLoading && !isError && groups.length > 0 && (
          <nav aria-label={english ? 'Finish categories' : 'Categorias de opcionais'} className="my-6 flex gap-2 overflow-x-auto pb-2">
            {groups.map(group => (
              <a key={group.code} href={`#${anchorId(group.code)}`} className="btn-secondary shrink-0 text-xs">
                {group.label}
                <span className="rounded-full bg-bg-2 px-1.5 py-0.5 text-[11px] font-semibold text-muted">{group.items.length}</span>
              </a>
            ))}
          </nav>
        )}

        {isLoading && (
          <div aria-label={english ? 'Loading finishes' : 'Carregando opcionais'} className="mt-7 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {Array.from({ length: 10 }, (_, index) => (
              <div key={index} className="animate-pulse">
                <div className="aspect-square rounded-xl bg-swatch-bg" />
                <div className="mt-3 h-4 w-3/4 rounded bg-bg-2" />
              </div>
            ))}
          </div>
        )}

        {isError && (
          <div className="mx-auto mt-16 max-w-md text-center" role="alert">
            <Layers3 className="mx-auto h-8 w-8 text-muted" aria-hidden="true" />
            <p className="mt-3 text-sm text-ink">{english ? 'The finishes could not be loaded.' : 'Não foi possível carregar os opcionais.'}</p>
            <button type="button" className="btn-secondary mt-4" onClick={() => { void refetchOptionals(); void refetchCategories() }}>
              {english ? 'Try again' : 'Tentar novamente'}
            </button>
          </div>
        )}

        {!isLoading && !isError && normalizedQuery && resultCount === 0 && (
          <div className="py-20 text-center">
            <p className="text-base font-medium text-ink">{english ? 'No finishes match this search.' : 'Nenhum opcional corresponde à busca.'}</p>
            <button type="button" onClick={() => setQuery('')} className="mt-3 text-sm font-semibold text-gold underline underline-offset-4">
              {english ? 'Clear search' : 'Limpar busca'}
            </button>
          </div>
        )}

        {!isLoading && !isError && !normalizedQuery && groups.length === 0 && (
          <p className="py-20 text-center text-sm text-muted">{english ? 'No finish categories registered.' : 'Nenhuma categoria de opcionais cadastrada.'}</p>
        )}

        {!isLoading && !isError && (!normalizedQuery || resultCount > 0) && (
          <div className="space-y-12 pb-10">
            {visibleGroups.map(group => (
              <section key={group.code} id={anchorId(group.code)} className="scroll-mt-24" aria-labelledby={`${anchorId(group.code)}-title`}>
                <div className="mb-4 flex items-baseline justify-between gap-3 border-b border-line pb-2">
                  <h2 id={`${anchorId(group.code)}-title`} className="text-2xl text-ink md:text-3xl">{group.label}</h2>
                  <span className="text-xs text-muted">{group.items.length}</span>
                </div>
                {group.items.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
                    {english ? 'No finishes in this category yet.' : 'Nenhum opcional nesta categoria.'}
                  </p>
                ) : (
                  <div className="grid grid-cols-2 gap-x-3 gap-y-7 sm:grid-cols-3 md:gap-x-5 lg:grid-cols-4 xl:grid-cols-5">
                    {group.items.map(optional => {
                      const hasPhoto = hasOptionalPhoto(optional)
                      return (
                        <article key={optional.id} className="min-w-0">
                          <button
                            type="button"
                            onClick={() => hasPhoto && setZoomed(optional)}
                            disabled={!hasPhoto}
                            className="group block w-full rounded-xl text-left disabled:cursor-default"
                            aria-label={hasPhoto ? (english ? `Enlarge ${optional.color_name}` : `Ampliar ${optional.color_name}`) : undefined}
                          >
                            <OptionalSwatchImage
                              optional={optional}
                              variant="gallery"
                              displaySize={320}
                              priority={priorityIds.has(optional.id)}
                              className="w-full rounded-xl border border-line transition-[border-color,box-shadow] group-enabled:hover:border-gold/50 group-enabled:hover:shadow-md"
                            />
                          </button>
                          <h3 className="mt-3 font-sans text-sm font-semibold leading-snug text-ink [overflow-wrap:anywhere]">{optional.color_name}</h3>
                          {showType && <p className="mt-1 text-xs text-muted">{categoryName(optional.category)}</p>}
                          <button
                            type="button"
                            onClick={() => addToBench(optional)}
                            disabled={!hasPhoto}
                            className="btn-secondary mt-3 w-full px-2 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {english ? 'Place side by side' : 'Colocar lado a lado'}
                          </button>
                        </article>
                      )
                    })}
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </div>

      <div className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>

      <OptionalBenchPanel
        items={bench.items}
        categoryLabel={categoryName}
        onRemove={optional => {
          bench.remove(optional.id)
          setAnnouncement(english ? `${optional.color_name} removed from the bench.` : `${optional.color_name} removida da bancada.`)
        }}
        onMove={(optional, direction) => bench.move(optional.id, direction)}
        onClear={() => {
          bench.clear()
          setAnnouncement(english ? 'Comparison bench cleared.' : 'Bancada limpa.')
        }}
        expanded={benchExpanded}
        onExpandedChange={setBenchExpanded}
      />

      {zoomed && <OptionalZoomDialog optional={zoomed} type={categoryName(zoomed.category)} onClose={() => setZoomed(null)} />}

      {pendingReplacement && (
        <Dialog
          title={english ? 'Choose a finish to replace' : 'Escolha qual amostra substituir'}
          onClose={() => setPendingReplacement(null)}
          layer="sub"
          className="max-w-lg"
        >
          <p className="mb-4 text-sm leading-relaxed text-muted">
            {english ? 'The bench holds up to four finishes. Nothing will be removed until you choose.' : 'A bancada comporta até quatro amostras. Nada será removido sem a sua escolha.'}
          </p>
          <div className="grid grid-cols-2 gap-3">
            {bench.items.map(optional => (
              <button
                key={optional.id}
                type="button"
                className="rounded-xl border border-line p-2 text-left transition-colors hover:border-gold"
                onClick={() => {
                  bench.replace(optional.id, pendingReplacement.id)
                  setAnnouncement(english
                    ? `${optional.color_name} replaced by ${pendingReplacement.color_name}.`
                    : `${optional.color_name} substituída por ${pendingReplacement.color_name}.`)
                  setPendingReplacement(null)
                }}
              >
                <OptionalSwatchImage optional={optional} variant="thumb" displaySize={120} decorative className="w-full rounded-lg" />
                <span className="mt-2 block text-xs font-semibold leading-snug text-ink [overflow-wrap:anywhere]">{optional.color_name}</span>
              </button>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  )
}
