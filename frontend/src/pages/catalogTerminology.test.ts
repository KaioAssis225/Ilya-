import { describe, expect, it } from 'vitest'
import { localizeFurnitureTerm } from '../lib/catalogTerminology'


describe('terminologia dos subgrupos EU', () => {
  it('mantém os nomes brasileiros em português', () => {
    expect(localizeFurnitureTerm('BANQUETA ALTA', 'pt-PT')).toBe('BANQUETA ALTA')
    expect(localizeFurnitureTerm('Banqueta', 'pt-PT')).toBe('Banqueta')
    expect(localizeFurnitureTerm('Poltrona', 'pt-PT')).toBe('Poltrona')
    expect(localizeFurnitureTerm('MESA DE JANTAR', 'pt-PT')).toBe('MESA DE JANTAR')
  })

  it('preserva a tradução dos mesmos subgrupos na interface inglesa', () => {
    expect(localizeFurnitureTerm('BANQUETA BAIXA', 'en-GB')).toBe('Low bar stool')
    expect(localizeFurnitureTerm('MESA DE CENTRO', 'en-GB')).toBe('Coffee table')
    expect(localizeFurnitureTerm('MESA LATERAL', 'en-GB')).toBe('Side table')
  })
})
