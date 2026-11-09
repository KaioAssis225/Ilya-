import { NumberField } from './NumberField'
import { suppliedFabricFormState, type SuppliedFabricForm } from '../lib/suppliedFabricForm'

/**
 * Seção "Tecido fornecido" da ficha do produto EU: metragem linear e o preço
 * "sem tecido" de cada tabela. Tudo preenchido liga a opção TECIDO FORNECIDO no
 * orçamento; tudo vazio tira. O servidor valida e é quem decide o valor.
 */
export function SuppliedFabricSection({ value, onChange, tx, color }: {
  value: SuppliedFabricForm
  onChange: (next: SuppliedFabricForm) => void
  tx: (pt: string) => string
  color: string
}) {
  const state = suppliedFabricFormState(value)
  const set = (patch: Partial<SuppliedFabricForm>) => onChange({ ...value, ...patch })
  const priceField = (label: string, key: 'lojista' | 'corporativo' | 'pvp' | 'arquiteto') => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <NumberField className="input" min="0" step="0.01" value={value[key]} onValueChange={(v) => set({ [key]: v })} />
    </label>
  )
  return (
    <section aria-label={tx('Tecido fornecido')} className="border border-line rounded-xl p-3.5 space-y-3 bg-white shadow-sm">
      <span className="text-xs font-semibold block" style={{ color }}>{tx('TECIDO FORNECIDO')}</span>
      <p className="text-xs text-muted">
        {tx('Preço “sem tecido” e metros lineares de tecido deste produto. Com tudo preenchido, o orçamento passa a oferecer a opção TECIDO FORNECIDO nos tecidos IBTW; com tudo vazio, a opção não aparece.')}
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">{tx('Tecido necessário (m)')}</span>
          <NumberField className="input" min="0" step="0.01" value={value.linear_meters} onValueChange={(v) => set({ linear_meters: v })} />
        </label>
        {priceField(tx('Sem tecido — PVP (€)'), 'pvp')}
        {priceField(tx('Sem tecido — Lojista (€)'), 'lojista')}
        {priceField(tx('Sem tecido — Arquiteto (€)'), 'arquiteto')}
        {priceField(tx('Sem tecido — Corporativo (€)'), 'corporativo')}
      </div>
      {state === 'empty' && (
        <p role="status" className="rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
          {tx('Para oferecer TECIDO FORNECIDO neste produto, preencha a metragem e os quatro preços “sem tecido”. Você pode salvar o produto sem isso.')}
        </p>
      )}
      {state === 'partial' && (
        <p role="alert" className="rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
          {tx('Falta preencher algum campo: informe a metragem e os quatro preços, ou deixe tudo vazio.')}
        </p>
      )}
    </section>
  )
}
