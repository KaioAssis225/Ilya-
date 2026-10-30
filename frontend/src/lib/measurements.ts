export type MeasurementMarket = 'BR' | 'EU'

interface Dimensions {
  is_circular: boolean
  largura: number
  altura: number
  profundidade: number
}

const METRES_TO_MILLIMETRES = 1000

function number(value: number, locale: string, decimals: number) {
  return Number(value).toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * Formata medidas sem alterar o valor canónico em metros armazenado no banco.
 * Portugal apresenta milímetros em qualquer idioma (só os rótulos mudam);
 * Brasil mantém metros. O valor canónico armazenado no banco continua em metros.
 */
export function formatDimensions(
  dimensions: Dimensions,
  market: MeasurementMarket,
  locale: 'pt-BR' | 'pt-PT' | 'en-GB',
) {
  const english = locale === 'en-GB'
  const width = english ? 'W' : 'L'
  const depth = english ? 'D' : 'P'
  const height = english ? 'H' : 'A'

  if (market === 'EU') {
    const unit = (metres: number) => `${number(metres * METRES_TO_MILLIMETRES, locale, 0)} mm`
    return dimensions.is_circular
      ? `Ø ${unit(dimensions.largura)} × ${height} ${unit(dimensions.altura)}`
      : `${width} ${unit(dimensions.largura)} × ${depth} ${unit(dimensions.profundidade)} × ${height} ${unit(dimensions.altura)}`
  }

  const metre = (metres: number) => number(metres, locale, 2)
  return dimensions.is_circular
    ? `Ø ${metre(dimensions.largura)} × ${height} ${metre(dimensions.altura)} m`
    : `${width} ${metre(dimensions.largura)} × ${depth} ${metre(dimensions.profundidade)} × ${height} ${metre(dimensions.altura)} m`
}

export function metresToMillimetres(metres: number) {
  return metres * METRES_TO_MILLIMETRES
}
