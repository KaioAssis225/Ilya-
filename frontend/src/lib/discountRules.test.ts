import { describe, expect, it } from 'vitest'
import type { UserRole } from '../contexts/AuthContext'
import { lineMaxDiscount, orderMaxDiscount } from './discountRules'

describe('orderMaxDiscount', () => {
  it.each<[string, UserRole]>([
    ['lojista', 'admin'],
    ['lojista', 'vendedor'],
    ['lojista', 'representante'],
    ['arquiteto', 'admin'],
    ['arquiteto', 'vendedor'],
    ['arquiteto', 'representante'],
    ['corporativo', 'admin'],
    ['corporativo', 'vendedor'],
    ['corporativo', 'representante'],
  ])('EU %s para %s não permite desconto', (profile, role) => {
    expect(orderMaxDiscount('EU', profile, role, 100)).toBe(0)
  })

  it('pvp admin segue o cadastro (72 vira 72, sem teto de 70)', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'admin', 72)).toBe(72)
    expect(orderMaxDiscount('EU', 'pvp', 'admin', 100)).toBe(100)
  })

  it.each<UserRole>(['representante', 'vendedor', 'admin'])('pvp %s com cadastro 72 aceita 72', (role) => {
    expect(orderMaxDiscount('EU', 'pvp', role, 72)).toBe(72)
  })

  it.each<UserRole>(['representante', 'vendedor'])(
    'pvp %s usa o desconto do cadastro do representante (50)',
    (role) => {
      expect(orderMaxDiscount('EU', 'pvp', role, 50)).toBe(50)
    },
  )

  it.each<UserRole>(['representante', 'vendedor'])(
    'pvp %s com cadastro 5 mantém 5',
    (role) => {
      expect(orderMaxDiscount('EU', 'pvp', role, 5)).toBe(5)
    },
  )

  it('pvp representante com limite negativo fica em 0', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'representante', -3)).toBe(0)
  })

  it('BR usa o cadastro do representante', () => {
    expect(orderMaxDiscount('BR', 'lojista', 'representante', 50)).toBe(50)
  })

  it('pvp cliente não tem desconto', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'cliente', 100, true)).toBe(0)
  })

  it('pvp vendedor com conta de cliente não tem desconto', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'vendedor', 100, true)).toBe(0)
  })

  it('pvp produtos não tem desconto', () => {
    expect(orderMaxDiscount('EU', 'pvp', 'produtos', 100)).toBe(0)
  })

  it('BR preserva o teto configurado do usuário', () => {
    expect(orderMaxDiscount('BR', 'lojista', 'vendedor', 12.5)).toBe(12.5)
  })
})

describe('lineMaxDiscount', () => {
  it('herda desconto maior que o teto', () => {
    expect(lineMaxDiscount(0, 40)).toBe(40)
  })

  it('não usa herança menor que o teto', () => {
    expect(lineMaxDiscount(30, 10)).toBe(30)
  })

  it('sem herança retorna o teto', () => {
    expect(lineMaxDiscount(30)).toBe(30)
  })

  it('herança nula retorna o teto', () => {
    expect(lineMaxDiscount(30, null)).toBe(30)
  })
})
