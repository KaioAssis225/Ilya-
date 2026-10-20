import type { OptionalApplicationInput, OptionalColor } from '../types'

interface Props {
  category: { id: string; code: string; name: string }
  optionals: OptionalColor[]
  applications: OptionalApplicationInput[]
  onChange: (applications: OptionalApplicationInput[]) => void
  onFirstAdd: () => void
  initialAllowedIds: string[]
  initialAllowAll: boolean
}

export function OptionalApplicationGroup({ category, optionals, applications, onChange, onFirstAdd, initialAllowedIds, initialAllowAll }: Props) {
  const indexes = applications.map((app, index) => app.category_id === category.id ? index : -1).filter(index => index >= 0)
  const update = (index: number, changes: Partial<OptionalApplicationInput>) =>
    onChange(applications.map((app, current) => current === index ? { ...app, ...changes } : app))
  const add = () => {
    if (indexes.length === 0) onFirstAdd()
    const source = indexes.length ? applications[indexes[indexes.length - 1]] : null
    onChange([...applications, {
      category_id: category.id,
      name: '', name_en: null,
      required: false,
      display_order: applications.length,
      allow_all: source?.allow_all ?? initialAllowAll,
      allow_repeat: source?.allow_repeat ?? true,
      allowed_optional_ids: source ? [...source.allowed_optional_ids] : [...initialAllowedIds],
    }])
  }
  return (
    <section className="mt-3 border-t border-line pt-3" aria-label={`Aplicações do opcional ${category.name}`}>
      <h4 className="text-xs font-semibold text-ink mb-2">Aplicações do opcional</h4>
      {indexes.map(index => {
        const app = applications[index]
        return <div key={app.id ?? `new-${index}`} className="rounded-lg border border-line p-3 mb-2 space-y-2 bg-surface-2">
          <div className="grid sm:grid-cols-2 gap-2">
            <label className="text-xs text-muted">Nome exibido *
              <input className="input w-full mt-1" value={app.name} maxLength={120} onChange={event => update(index, { name: event.target.value })} placeholder="Ex.: Pintura dos pés" />
            </label>
            <label className="text-xs text-muted">Nome em inglês (EU)
              <input className="input w-full mt-1" value={app.name_en ?? ''} maxLength={120} onChange={event => update(index, { name_en: event.target.value || null })} />
            </label>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-ink-2">
            <label><input type="checkbox" checked={app.required} onChange={event => update(index, { required: event.target.checked })} /> Obrigatória</label>
            <label><input type="checkbox" checked={app.allow_repeat} onChange={event => update(index, { allow_repeat: event.target.checked })} /> Permitir repetir a escolha</label>
            <label><input type="checkbox" checked={app.allow_all} onChange={event => update(index, { allow_all: event.target.checked, allowed_optional_ids: event.target.checked ? [] : optionals.map(option => option.id) })} /> Permitir todas as opções</label>
            <label>Ordem <input className="input w-16 ml-1" type="number" min={0} value={app.display_order} onChange={event => update(index, { display_order: Math.max(0, Number(event.target.value)) })} /></label>
          </div>
          {!app.allow_all && <div className="flex flex-wrap gap-2">
            {optionals.map(option => <label key={option.id} className="text-xs border border-line rounded px-2 py-1">
              <input type="checkbox" checked={app.allowed_optional_ids.includes(option.id)} onChange={event => update(index, { allowed_optional_ids: event.target.checked ? [...app.allowed_optional_ids, option.id] : app.allowed_optional_ids.filter(id => id !== option.id) })} /> {option.color_name}
            </label>)}
          </div>}
          <button type="button" className="text-xs text-danger" onClick={() => onChange(applications.filter((_, current) => current !== index))}>Remover aplicação</button>
        </div>
      })}
      <button type="button" className="btn-secondary text-xs" onClick={add} disabled={optionals.length === 0}>Adicionar outra aplicação</button>
    </section>
  )
}
