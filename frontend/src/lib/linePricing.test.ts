import { describe, expect, it } from 'vitest'
import { calculateLinePricing, lineTax, roundMoney } from './linePricing'

describe('roundMoney', () => {
  it('arredonda meio centavo para cima, como ROUND_HALF_UP do servidor', () => {
    expect(roundMoney(4674.185)).toBe(4674.19)
    expect(roundMoney(173.118)).toBe(173.12)
    expect(roundMoney(0.005)).toBe(0.01)
    expect(roundMoney(1.004)).toBe(1)
  })
})

describe('calculateLinePricing', () => {
  it('quantidade 1 sem desconto: unitário líquido = preço-base = subtotal', () => {
    expect(calculateLinePricing(1731.18, 0, 1)).toEqual({
      basePrice: 1731.18, unitDiscount: 0, netUnitPrice: 1731.18, subtotal: 1731.18,
    })
  })

  it('quantidade > 1 sem desconto: subtotal = preço-base × quantidade', () => {
    const pricing = calculateLinePricing(1731.18, 0, 3)
    expect(pricing.netUnitPrice).toBe(1731.18)
    expect(pricing.subtotal).toBe(5193.54)
  })

  it('exemplo da especificação (EUR): qtd 2 com 10%', () => {
    expect(calculateLinePricing(1731.18, 10, 2)).toEqual({
      basePrice: 1731.18, unitDiscount: 173.12, netUnitPrice: 1558.06, subtotal: 3116.12,
    })
  })

  it('o valor unitário é o preço-base menos o desconto unitário exibido', () => {
    const { basePrice, unitDiscount, netUnitPrice } = calculateLinePricing(1731.18, 10, 5)
    expect(roundMoney(basePrice - unitDiscount)).toBe(netUnitPrice)
  })

  it('não aplica o desconto duas vezes: subtotal parte do preço-base, não do unitário líquido', () => {
    const pricing = calculateLinePricing(1000, 20, 4)
    expect(pricing.netUnitPrice).toBe(800)
    expect(pricing.subtotal).toBe(3200)
  })

  // Regra mantida do servidor (decisão do usuário): o subtotal oficial é a linha
  // arredondada UMA vez. Com qtd 3, 1.558,062 × 3 = 4.674,186 → 4.674,19, e o
  // unitário informativo (1.558,06) × 3 daria 4.674,18: 1 centavo de diferença.
  it('qtd 3 com 10%: subtotal oficial difere em 1 centavo do unitário arredondado × qtd', () => {
    const pricing = calculateLinePricing(1731.18, 10, 3)
    expect(pricing.netUnitPrice).toBe(1558.06)
    expect(pricing.subtotal).toBe(4674.19)
    expect(roundMoney(pricing.netUnitPrice * 3)).toBe(4674.18)
  })

  it('tapete: preço por m² e quantidade em m² totais', () => {
    expect(calculateLinePricing(100, 10, 4.2)).toMatchObject({ netUnitPrice: 90, subtotal: 378 })
  })

  it('tolera desconto vazio (NaN/0) como sem desconto', () => {
    expect(calculateLinePricing(80, 0, 2).subtotal).toBe(160)
  })
})

describe('lineTax', () => {
  it('IVA incide sobre o subtotal líquido e arredonda por linha', () => {
    expect(lineTax(4674.19, 23)).toBe(1075.06)
    expect(lineTax(3116.12, 23)).toBe(716.71)
  })

  it('taxa zero não gera imposto', () => {
    expect(lineTax(100, 0)).toBe(0)
  })
})
