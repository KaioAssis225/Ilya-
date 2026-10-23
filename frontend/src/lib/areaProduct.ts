import type { Product } from '../types'

type AreaProduct = Pick<Product, 'catalog' | 'area_limit_enabled' | 'max_area_m2'>

export function isAreaCatalogName(name: string | null | undefined): boolean {
  const normalized = (name ?? '')
    .trim()
    .toLocaleLowerCase('pt-BR')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')

  return normalized === 'tapete' || normalized === 'tapetes'
}

export function isAreaProduct(product: Pick<Product, 'catalog'> | null | undefined): boolean {
  return isAreaCatalogName(product?.catalog?.name)
}

export function areaLimit(product: AreaProduct | null | undefined): number | null {
  if (!product?.area_limit_enabled) return null
  const maximum = Number(product.max_area_m2)
  return Number.isFinite(maximum) && maximum > 0 ? maximum : null
}

export function normalizeAreaQty(value: number | string): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0.01
  return Math.max(0.01, Math.round((numeric + Number.EPSILON) * 100) / 100)
}

export function formatArea(qty: number | string, locale: string = 'pt-BR'): string {
  const numeric = Number(qty)
  const safeQty = Number.isFinite(numeric) ? numeric : 0
  return `${new Intl.NumberFormat(locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(safeQty)} m²`
}
