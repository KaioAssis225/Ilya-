import type { ProductCreate } from '../types'

export function withMarketProductNames<T extends ProductCreate>(payload: T, isEurope: boolean): T {
  if (!isEurope) return payload

  return {
    ...payload,
    description: payload.description.trim(),
    // Portugal usa o mesmo nome principal em português definido no formulário.
    // A API ainda persiste esse valor no campo localizado do mercado EU.
    description_pt_pt: payload.description.trim(),
    description_en: payload.description_en?.trim() || undefined,
  }
}
