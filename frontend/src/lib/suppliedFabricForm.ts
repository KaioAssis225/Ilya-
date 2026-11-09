import type { SuppliedFabric } from '../types'
import type { SuppliedFabricInput } from '../hooks/useProducts'

/** Campos da seção "Tecido fornecido" da ficha do produto EU (0 = vazio, como o NumberField). */
export interface SuppliedFabricForm {
  linear_meters: number
  lojista: number
  corporativo: number
  pvp: number
  arquiteto: number
}

export const EMPTY_FABRIC_FORM: SuppliedFabricForm = { linear_meters: 0, lojista: 0, corporativo: 0, pvp: 0, arquiteto: 0 }

export function suppliedFabricToForm(fabric: SuppliedFabric | null | undefined): SuppliedFabricForm {
  if (!fabric) return EMPTY_FABRIC_FORM
  const price = (code: string) => Number(fabric.prices?.[code] ?? 0)
  return {
    linear_meters: Number(fabric.linear_meters),
    lojista: price('lojista'), corporativo: price('corporativo'), pvp: price('pvp'), arquiteto: price('arquiteto'),
  }
}

/** empty: nada preenchido (tira a opção); filled: tudo preenchido (grava); partial: falta algo (não salva). */
export function suppliedFabricFormState(form: SuppliedFabricForm): 'empty' | 'filled' | 'partial' {
  const values = Object.values(form)
  if (values.every(value => !(value > 0))) return 'empty'
  return values.every(value => value > 0) ? 'filled' : 'partial'
}

/** Duas casas, como o servidor grava (evita 700,1000000001 de ponto flutuante). */
const cents = (value: number) => Math.round(value * 100) / 100

export function fabricFormToInput(form: SuppliedFabricForm): SuppliedFabricInput {
  return {
    linear_meters: cents(form.linear_meters),
    price_lojista: cents(form.lojista), price_corporativo: cents(form.corporativo),
    price_pvp: cents(form.pvp), price_arquiteto: cents(form.arquiteto),
  }
}
