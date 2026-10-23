// Colunas da tabela desktop de produtos (Cadastros) e o encaixe das larguras no
// container. Vive fora de CadastroPage.tsx para poder ser testado em isolamento
// sem quebrar o Fast Refresh (páginas só exportam componentes).

export type ProductColumnKey = 'details' | 'code' | 'description' | 'type' | 'price_lojista' | 'price_corporativo' | 'price_pvp' | 'price_arquiteto' | 'actions'

export const BR_PRODUCT_COLUMN_KEYS: ProductColumnKey[] = [
  'details', 'code', 'description', 'type', 'price_lojista', 'price_corporativo', 'actions',
]

export const EU_PRODUCT_COLUMN_KEYS: ProductColumnKey[] = [
  'details', 'code', 'description', 'type', 'price_lojista', 'price_corporativo', 'price_pvp', 'price_arquiteto', 'actions',
]

// Mínimos: preço comporta "R$ 1.234.567,89" em text-sm; ações comportam
// editar + "Aplicações" + excluir sem transbordar; tipo comporta "POLTRONAS"
// sem partir a palavra. Soma BR 918px, EU 1206px — cabe em 1440 com o menu em
// rail (≈1211px úteis descontando barra de rolagem de 17px).
export const PRODUCT_COLUMN_MIN_WIDTHS: Record<ProductColumnKey, number> = {
  details: 44,
  code: 100,
  description: 210,
  type: 108,
  price_lojista: 144,
  price_corporativo: 144,
  price_pvp: 144,
  price_arquiteto: 144,
  actions: 168,
}

export const INITIAL_PRODUCT_COLUMN_WIDTHS: Record<ProductColumnKey, number> = {
  details: 44,
  code: 128,
  description: 320,
  type: 136,
  price_lojista: 152,
  price_corporativo: 152,
  price_pvp: 152,
  price_arquiteto: 152,
  actions: 176,
}

/**
 * Distribui `availableWidth` entre as colunas visíveis respeitando os mínimos.
 * Quando a largura não comporta os mínimos, devolve os mínimos (a tabela rola
 * na horizontal com a coluna de ações fixa e pista de rolagem).
 */
export function fittedProductColumnWidths(
  columns: ProductColumnKey[],
  availableWidth: number,
  isEurope: boolean,
): Record<ProductColumnKey, number> {
  const fitted = { ...PRODUCT_COLUMN_MIN_WIDTHS }
  const minimumWidth = columns.reduce((total, column) => total + PRODUCT_COLUMN_MIN_WIDTHS[column], 0)
  const usableWidth = Math.floor(availableWidth)
  if (usableWidth <= minimumWidth) return fitted

  const weights: Record<ProductColumnKey, number> = isEurope
    ? { details: 0, code: 0.08, description: 0.28, type: 0.08, price_lojista: 0.10, price_corporativo: 0.10, price_pvp: 0.10, price_arquiteto: 0.10, actions: 0.16 }
    : { details: 0, code: 0.12, description: 0.39, type: 0.11, price_lojista: 0.12, price_corporativo: 0.12, price_pvp: 0, price_arquiteto: 0, actions: 0.14 }
  const extraWidth = usableWidth - minimumWidth
  const totalWeight = columns.reduce((total, column) => total + weights[column], 0)
  let assignedExtra = 0

  columns.forEach((column, index) => {
    const extra = index === columns.length - 1
      ? extraWidth - assignedExtra
      : Math.floor(extraWidth * (weights[column] / totalWeight))
    fitted[column] += extra
    assignedExtra += extra
  })

  return fitted
}
