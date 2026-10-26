import type { OptionalColor } from '../types'
import { optionalCategoryLabel } from './optionalLabels'

// Catalog families only affect display. Category codes remain stable for products,
// allowed applications, cart choices and historical orders.
const fabricFamilies = ['BAETA', 'LONA', 'PANAMA', 'SARJA', 'UNIQUE', 'BOUCLE', 'JACQUARD TEXTURA', 'RATIER RAMI', 'TWEED', 'WAVES', 'TARTAN']

export function optionalBrand(optional: Pick<OptionalColor, 'brand'>) {
  return optional.brand ?? 'ILYA'
}

export function optionalMatchesLegacyName(optional: OptionalColor, name: string) {
  return optional.color_name === name || (
    optional.category === 'CERAMICA_ARTESANAL' && optional.color_name === 'AREIA MESCLA' && name === 'AMARELO MESCLA'
  )
}

export function optionalGroup(optional: OptionalColor, categoryName: string, english: boolean) {
  if (optionalBrand(optional) === 'IBTW' && optional.category === 'TECIDOS_IBTW') {
    const name = optional.color_name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase()
    if (name.startsWith('COURO PELE ')) return { code: 'couro_pele', label: english ? 'Leather' : 'Couro Pele' }
    const family = fabricFamilies.find(prefix => name.startsWith(`${prefix} `))
    if (family) {
      const displayFamily = english && family === 'JACQUARD TEXTURA' ? 'Textured Jacquard' : family === 'PANAMA' ? 'Panamá' : family === 'BOUCLE' ? 'Bouclé' : family.toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase())
      const solar = family === 'JACQUARD TEXTURA' ? '' : ' Solar'
      return { code: `tecido-${family.toLowerCase().replaceAll(' ', '-')}`, label: english ? `${displayFamily}${solar} Fabric` : `Tecido ${displayFamily}${solar}` }
    }
  }
  if (optional.category === 'MADEIRA' && optional.color_name.toUpperCase().startsWith('IROKO ')) {
    return { code: 'madeira-iroko', label: english ? 'Iroko Wood' : 'Madeira Iroko' }
  }
  return { code: optional.category, label: optionalCategoryLabel(categoryName, english) }
}
