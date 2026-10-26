import { describe, expect, it } from 'vitest'
import { optionalBrand, optionalGroup, optionalMatchesLegacyName } from './optionalGroups'
import type { OptionalColor } from '../types'

describe('marcas e grupos dos opcionais', () => {
  const fabric: OptionalColor = { id: 'opt', category: 'TECIDOS_IBTW', color_name: 'BAETA ARGILA', brand: 'IBTW', photo_url: null }
  it('separa famílias IBTW preservando o grupo cadastrado para ILYA e desconhecidos', () => {
    expect(optionalGroup(fabric, 'TECIDOS IBTW', false).label).toBe('Tecido Baeta Solar')
    expect(optionalGroup({ ...fabric, color_name: 'COURO PELE CINZA' }, 'TECIDOS IBTW', true).label).toBe('Leather')
    expect(optionalGroup({ ...fabric, color_name: 'JACQUARD TEXTURA CRU' }, 'TECIDOS IBTW', true).label).toBe('Textured Jacquard Fabric')
    expect(optionalGroup({ ...fabric, brand: 'ILYA' }, 'Tecidos', false)).toEqual({ code: 'TECIDOS_IBTW', label: 'Tecidos' })
    expect(optionalGroup({ ...fabric, color_name: 'Outra coleção' }, 'Tecidos', false).label).toBe('Tecidos')
    expect(optionalBrand({})).toBe('ILYA')
    expect(fabric.category).toBe('TECIDOS_IBTW')
  })
  it('mantém a foto acessível pelo nome antigo da cerâmica em pedidos legados', () => {
    const ceramic = { ...fabric, category: 'CERAMICA_ARTESANAL', color_name: 'AREIA MESCLA' }
    expect(optionalMatchesLegacyName(ceramic, 'AMARELO MESCLA')).toBe(true)
    expect(optionalMatchesLegacyName(ceramic, 'AREIA MESCLA')).toBe(true)
    expect(optionalMatchesLegacyName(ceramic, 'AREIA')).toBe(false)
    expect(optionalMatchesLegacyName({ ...ceramic, category: 'OUTRA' }, 'AMARELO MESCLA')).toBe(false)
  })
})
