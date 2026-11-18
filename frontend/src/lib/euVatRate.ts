// Taxa única de IVA de Portugal: tipos e regras de formatação/validação do campo.

export type EuVatRateEvent = {
  changed_at: string
  old_rate: string | number | null
  new_rate: string | number
  changed_by: string | null
}

export type EuVatRateView = {
  market: 'EU'
  vat_rate: string | number | null
  can_edit: boolean
  history: EuVatRateEvent[]
}

/** Só o admin do mercado europeu vê e altera a taxa na tela (o servidor confere de novo). */
export function canManageEuVat(user: { active_market?: string | null; role?: string | null } | null | undefined): boolean {
  return user?.active_market === 'EU' && user?.role === 'admin'
}

/** "23%" para 23.00 e "7,5%" para 7.50: sem zeros que não dizem nada. */
export function formatRate(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number)
    ? `${number.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}%`
    : '—'
}

/** Mesma regra do servidor: 0–100, no máximo duas casas decimais. */
export function parseRateInput(raw: string): number | null {
  const text = raw.trim().replace(',', '.')
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(text)) return null
  const value = Number(text)
  return value >= 0 && value <= 100 ? value : null
}
