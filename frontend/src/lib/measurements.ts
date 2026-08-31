export type MeasurementMarket = 'BR' | 'EU'

interface Dimensions {
  is_circular: boolean
  largura: number
  altura: number
  profundidade: number
}

const METRES_TO_INCHES = 39.3700787402

function number(value: number, locale: string, decimals: number) {
  return Number(value).toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * Formata medidas sem alterar o valor canónico em metros armazenado no banco.
 * Portugal apresenta polegadas; Brasil mantém metros. O locale muda apenas
 * separadores e as letras de largura/profundidade/altura.
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
    const inch = (metres: number) => `${number(metres * METRES_TO_INCHES, locale, 2)}″`
    return dimensions.is_circular
      ? `Ø ${inch(dimensions.largura)} × ${height} ${inch(dimensions.altura)}`
      : `${width} ${inch(dimensions.largura)} × ${depth} ${inch(dimensions.profundidade)} × ${height} ${inch(dimensions.altura)}`
  }

  const metre = (metres: number) => number(metres, locale, 2)
  return dimensions.is_circular
    ? `Ø ${metre(dimensions.largura)} × ${height} ${metre(dimensions.altura)} m`
    : `${width} ${metre(dimensions.largura)} × ${depth} ${metre(dimensions.profundidade)} × ${height} ${metre(dimensions.altura)} m`
}

export function metresToInches(metres: number) {
  return metres * METRES_TO_INCHES
}
