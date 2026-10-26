import { describe, expect, it } from 'vitest'
import { optionalCategoryLabel, optionalMatchesSearch, optionalName } from './optionalLabels'

describe('optional presentation labels', () => {
  it('preserva nomes canônicos em português e nomes comerciais desconhecidos', () => {
    for (const name of ['AREIA', 'IROKO CARVÃO ÓLEO', 'Branco', 'PANAMÁ BAUNILHA /NEVOA']) {
      expect(optionalName(name, false)).toBe(name)
    }
    for (const name of ['MILANO', 'FENDI', 'JUQUEHY', 'QUARTO', 'Novo acabamento exclusivo']) {
      expect(optionalName(name, true)).toBe(name)
    }
    expect(optionalCategoryLabel('PEDRA_SINTERIZADA', false)).toBe('PEDRA_SINTERIZADA')
  })

  it('traduz cores, materiais compostos e categorias com acentos e códigos legados', () => {
    expect(optionalName('CARVÃO', true)).toBe('CHARCOAL')
    expect(optionalName('Branco', true)).toBe('White')
    expect(optionalName('IROKO CARVÃO ÓLEO', true)).toBe('OILED CHARCOAL IROKO')
    expect(optionalName('PANAMÁ BAUNILHA /NEVOA', true)).toBe('PANAMA VANILLA/MIST')
    expect(optionalCategoryLabel('PEDRA_SINTERIZADA', true)).toBe('SINTERED STONE')
    expect(optionalCategoryLabel('Madeira', true)).toBe('Wood')
    expect(optionalCategoryLabel('couro_soleta', true)).toBe('Saddle Leather')
  })

  it('busca tanto a tradução quanto o nome original, sem acentos', () => {
    expect(optionalMatchesSearch('CARVÃO', 'charcoal', true)).toBe(true)
    expect(optionalMatchesSearch('CARVÃO', 'carvao', true)).toBe(true)
    expect(optionalMatchesSearch('CARVÃO', 'charcoal', false)).toBe(false)
    expect(optionalMatchesSearch('CARVÃO', 'pearl', true)).toBe(false)
  })
})
