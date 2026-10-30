import { describe, expect, it } from 'vitest'
import { priceListLabel, priceListLabelFor } from './priceListLabels'

describe('priceListLabel', () => {
  it('mantém os nomes em português fora do inglês', () => {
    expect(priceListLabel('lojista', false)).toBe('Lojista')
    expect(priceListLabel('arquiteto', false)).toBe('Arquiteto')
    expect(priceListLabel('corporativo', false)).toBe('Corporativo')
    expect(priceListLabel('pvp', false)).toBe('PVP')
  })

  it('traduz as três tabelas em inglês e mantém PVP', () => {
    expect(priceListLabel('lojista', true)).toBe('Retailer')
    expect(priceListLabel('arquiteto', true)).toBe('Architect')
    expect(priceListLabel('corporativo', true)).toBe('Corporate')
    expect(priceListLabel('pvp', true)).toBe('PVP')
  })

  it('priceListLabelFor aceita código solto e capitaliza o desconhecido', () => {
    expect(priceListLabelFor('arquiteto', true)).toBe('Architect')
    expect(priceListLabelFor('outra', true)).toBe('Outra')
  })
})
