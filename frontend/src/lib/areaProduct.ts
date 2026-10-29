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

export function previewArea(width: number | null | undefined, depth: number | null | undefined): number | null {
  if (width == null || depth == null) return null
  const numericWidth = Number(width)
  const numericDepth = Number(depth)
  if (!Number.isFinite(numericWidth) || !Number.isFinite(numericDepth) || numericWidth <= 0 || numericDepth <= 0) return null
  return Math.max(0.01, Math.round((numericWidth * numericDepth + Number.EPSILON) * 100) / 100)
}

export function formatMeters(value: number | string, locale = 'pt-BR'): string {
  const numeric = Number(value)
  const safe = Number.isFinite(numeric) ? numeric : 0
  return `${new Intl.NumberFormat(locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(safe)} m`
}

export function formatRugSize(
  width: number | string | null | undefined,
  depth: number | string | null | undefined,
  area: number | string,
  locale = 'pt-BR',
  pieces = 1,
): string {
  const numericWidth = width == null ? 0 : Number(width)
  const numericDepth = depth == null ? 0 : Number(depth)
  const safePieces = normalizeRugPieces(pieces)
  const total = Number(area)
  const hasValidDimensions = Number.isFinite(numericWidth) && Number.isFinite(numericDepth) && numericWidth > 0 && numericDepth > 0

  if (safePieces <= 1) {
    if (!hasValidDimensions) return formatArea(total, locale)
    return `${formatMeters(numericWidth, locale).replace(/ m$/, '')} × ${formatMeters(numericDepth, locale)} = ${formatArea(total, locale)}`
  }

  const areaPerPiece = normalizeAreaQty(total / safePieces)
  const piecesLabel = formatRugPieces(safePieces, locale)
  if (!hasValidDimensions) {
    return `${formatArea(areaPerPiece, locale)} × ${piecesLabel} = ${formatArea(total, locale)}`
  }
  return `${formatMeters(numericWidth, locale).replace(/ m$/, '')} × ${formatMeters(numericDepth, locale)} = ${formatArea(areaPerPiece, locale)} × ${piecesLabel} = ${formatArea(total, locale)}`
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

export function normalizeRugPieces(value: number | string | null | undefined): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 1
  const rounded = Math.round(numeric)
  if (rounded < 1) return 1
  if (rounded > 1000) return 1000
  return rounded
}

export function formatRugPieces(pieces: number, locale = 'pt-BR'): string {
  const safe = normalizeRugPieces(pieces)
  if (locale === 'en-GB') {
    return safe === 1 ? '1 piece' : `${safe} pieces`
  }
  return safe === 1 ? '1 peça' : `${safe} peças`
}
