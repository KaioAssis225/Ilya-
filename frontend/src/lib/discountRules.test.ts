import { describe, expect, it } from 'vitest'
import { orderMaxDiscount } from './discountRules'

describe('orderMaxDiscount', () => {
  it.each([
    ['lojista', 50],
    ['arquiteto', 35],
    ['corporativo', 25],
  ])('usa o teto da tabela EU %s', (profile, expected) => {
    expect(orderMaxDiscount('EU', profile, 'vendedor', 3)).toBe(expected)
  })

  it('limita PVP a 10% para admin', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'admin', 100)).toBe(10)
  })

  it('impede desconto PVP para outros papéis', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'vendedor', 100)).toBe(0)
  })

  it('preserva o teto configurado por usuário no Brasil', () => {
    expect(orderMaxDiscount('BR', 'lojista', 'vendedor', 12.5)).toBe(12.5)
  })
})
