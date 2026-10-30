/** Terminologia comercial do catálogo europeu por idioma de interface. */
export function localizeFurnitureTerm(value: string, locale: 'pt-PT' | 'en-GB') {
  const normalized = value.trim().toLocaleLowerCase('pt-PT')
  // Em português, BR e EU usam os mesmos nomes comerciais cadastrados.
  if (locale === 'pt-PT') return value
  const en: Record<string, string> = {
    banqueta: 'Bar stool', banquetas: 'Bar stools', poltrona: 'Armchair', poltronas: 'Armchairs',
    'banqueta alta': 'High bar stool', 'banqueta baixa': 'Low bar stool',
    cadeira: 'Chair', cadeiras: 'Chairs', sofá: 'Sofa', sofás: 'Sofas', mesa: 'Table', mesas: 'Tables',
    'mesa de jantar': 'Dining table', 'mesa de centro': 'Coffee table',
    'mesa lateral': 'Side table', 'mesa bistrô': 'Bistro table',
    aparador: 'Console table', aparadores: 'Console tables', conjunto: 'Set', conjuntos: 'Sets',
    luminária: 'Lamp', luminárias: 'Lamps', espreguiçadeira: 'Sun lounger', espreguiçadeiras: 'Sun loungers',
    'carrinho bar': 'Bar trolley', chaise: 'Chaise longue', puff: 'Pouf',
  }
  return en[normalized] ?? value
}
