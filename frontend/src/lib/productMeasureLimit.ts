/**
 * Limite plausível das medidas de produto (altura, largura, profundidade), em
 * METROS. Espelha `MAX_PRODUCT_DIMENSION_M` do backend
 * (backend/app/core/product_dimensions.py): milímetros digitados como metros
 * (470 em vez de 0,47) aparecem no EU como "470000 mm".
 */
export const MAX_PRODUCT_DIMENSION_M = 20

export const PRODUCT_DIMENSION_LIMIT_MESSAGE =
  'Medida acima de 20 m — as medidas são em metros (ex.: 470 mm = 0,47).'

/** Verdadeiro quando a medida passa de 20 m (20 exato é aceito). */
export function exceedsDimensionLimit(value: unknown): boolean {
  const measure = Number(value)
  return Number.isFinite(measure) && measure > MAX_PRODUCT_DIMENSION_M
}

interface DimensionFields {
  altura?: unknown
  largura?: unknown
  profundidade?: unknown
}

/** Verifica altura, largura e (fora dos redondos) profundidade de um produto ou componente. */
export function hasDimensionOverLimit(item: DimensionFields, isCircular: boolean): boolean {
  return (
    exceedsDimensionLimit(item.altura)
    || exceedsDimensionLimit(item.largura)
    || (!isCircular && exceedsDimensionLimit(item.profundidade))
  )
}
