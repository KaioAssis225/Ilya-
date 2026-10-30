// Prévia da linha de produto do orçamento (criação, edição e restauração).
//
// O valor oficial é do servidor (`_calculate_order_line`, em orders.py): o
// preço efetivo NÃO é arredondado e o subtotal da linha é arredondado UMA vez
// (`ROUND_HALF_UP`, centavos). A prévia segue exatamente essa regra.
//
// Os valores por unidade (`unitDiscount` e `netUnitPrice`) são só informativos:
// são arredondados para leitura, e `netUnitPrice × qty` pode diferir 1 centavo
// de `subtotal` quando a quantidade é maior que 1. Ex.: €1.731,18 com 10% e
// qtd 3 → unitário líquido €1.558,06, mas o subtotal oficial é €4.674,19
// (1.558,062 × 3 = 4.674,186), não €4.674,18. O subtotal nunca é recalculado a
// partir do unitário arredondado, nem o desconto é aplicado duas vezes.

export interface LinePricing {
  /** Preço-base unitário do catálogo (por m² no tapete). */
  basePrice: number
  /** Desconto por unidade, arredondado ao centavo. */
  unitDiscount: number
  /** Preço-base − desconto unitário, ambos já em centavos. */
  netUnitPrice: number
  /** Subtotal oficial da linha: qtd × base × (1 − d%), arredondado uma vez. */
  subtotal: number
}

/** Arredonda ao centavo com meio para cima, como o `ROUND_HALF_UP` do servidor. */
export function roundMoney(value: number): number {
  const sign = value < 0 ? -1 : 1
  // O ajuste de 1e-9 cobre o ruído binário de produtos como 4674.185 (±1 ulp).
  return sign * Math.round((Math.abs(value) + 1e-9) * 100) / 100
}

export function calculateLinePricing(basePrice: number, discountPercent: number, qty: number): LinePricing {
  const price = roundMoney(basePrice)
  const discount = discountPercent || 0
  const unitDiscount = roundMoney(price * discount / 100)
  return {
    basePrice: price,
    unitDiscount,
    netUnitPrice: roundMoney(price - unitDiscount),
    subtotal: roundMoney(qty * price * (100 - discount) / 100),
  }
}

/** IVA/IPI de uma linha sobre o subtotal líquido, arredondado como o servidor. */
export function lineTax(subtotal: number, ratePercent: number): number {
  return roundMoney(subtotal * ratePercent / 100)
}
