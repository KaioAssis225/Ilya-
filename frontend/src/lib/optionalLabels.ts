// Presentation only: keep Portuguese names and category codes in API payloads,
// cart choices and order snapshots. Unknown commercial names stay unchanged.
const names: Record<string, string> = {
  AREIA: 'Sand', 'AREIA UNIQUE': 'Unique Sand', CAFE: 'Coffee', CHAMPANHE: 'Champagne',
  MARROM: 'Brown', PRETO: 'Black', 'PRETO ONIX': 'Onyx Black',
  'AZUL MARINHO': 'Navy Blue', CAMOMILA: 'Chamomile', CANELA: 'Cinnamon',
  CHUMBO: 'Lead Grey', CIDREIRA: 'Lemongrass', CRIDREIRA: 'Lemongrass',
  'ERVA DOCE': 'Fennel', GRAFITE: 'Graphite', TERRACOTA: 'Terracotta',
  'BASE B8': 'B8 Base', 'AMARELO MESCLA': 'Mottled Yellow',
  'AREIA FERRUGEM': 'Rust Sand', 'AREIA OCEANO': 'Ocean Sand', 'AZUL ROYAL': 'Royal Blue',
  BAUNILHA: 'Vanilla', CAMURCA: 'Suede', ESMERALDA: 'Emerald', SAFIRA: 'Sapphire',
  CROMO: 'Chrome', CRU: 'Ecru', NEBLINA: 'Fog', OPALA: 'Opal',
  BRANCO: 'White', 'BRANCO FOSCO': 'Matt White', CARAMELO: 'Caramel', CINZA: 'Grey',
  BAMBU: 'Bamboo', 'IROKO CARVAO OLEO': 'Oiled Charcoal Iroko',
  'IROKO NATURAL OLEO': 'Oiled Natural Iroko', 'IROKO PATINA OLEO': 'Oiled Patinated Iroko',
  'IROKO TAUPE OLEO': 'Oiled Taupe Iroko', CARVAO: 'Charcoal', CONCRETO: 'Concrete', PEROLA: 'Pearl',
  'CHENILLE ALPINO CRU': 'Alpino Ecru Chenille', 'FLAME AREIA/TAUPE': 'Flamé Sand/Taupe',
  'RATIER AREIA/TAUPE': 'Ratier Sand/Taupe', 'TRAMA AREIA/TAUPE': 'Sand/Taupe Weave',
  'BAETA ARGILA': 'Baeta Clay', 'BAETA SISAL': 'Baeta Sisal', 'BAETA TOPAZIO': 'Baeta Topaz',
  'BOUCLE DESERTO': 'Desert Bouclé', 'BOUCLE INDIGO': 'Indigo Bouclé',
  'BOUCLE JADE': 'Jade Bouclé', 'BOUCLE PLATINA': 'Platinum Bouclé',
  'BOUCLE SISAL': 'Sisal Bouclé', 'BOUCLE TOPAZIO': 'Topaz Bouclé',
  'COURO PELE BRANCO FOSCO': 'Matt White Leather', 'COURO PELE CARAMELO': 'Caramel Leather',
  'COURO PELE CHUMBO': 'Lead Grey Leather', 'COURO PELE CIDREIRA': 'Lemongrass Leather',
  'COURO PELE CINZA': 'Grey Leather',
  'JACQUARD TEXTURA AREIA/CRU': 'Textured Jacquard Sand/Ecru',
  'JACQUARD TEXTURA CRU': 'Textured Ecru Jacquard', 'LONA COBALTO': 'Cobalt Canvas',
  'PANAMA BAUNILHA/NEVOA': 'Panama Vanilla/Mist', 'PANAMA DESERTO': 'Panama Desert',
  'PANAMA INDIGO': 'Panama Indigo', 'PANAMA JADE': 'Panama Jade', 'PANAMA NEVOA': 'Panama Mist',
  'PANAMA SISAL': 'Panama Sisal', 'PANAMA SISAL/ARGILA': 'Panama Sisal/Clay',
  'PANAMA SISAL/INDIGO': 'Panama Sisal/Indigo', 'PANAMA SISAL/JADE': 'Panama Sisal/Jade',
  'PANAMA TOPAZIO': 'Panama Topaz', 'RATIER RAMI AMENDOA': 'Ratier Ramie Almond',
  'RATIER RAMI NEVOA': 'Ratier Ramie Mist', 'SARJA AVELA': 'Hazelnut Twill',
  'SARJA COBALTO': 'Cobalt Twill', 'SARJA LAZULI': 'Lapis Lazuli Twill',
  'SARJA MARFIN': 'Ivory Twill', 'SARJA MARFIM': 'Ivory Twill', 'SARJA MENTA': 'Mint Twill',
  'TARTAN CIDREIRA/ARGILA': 'Tartan Lemongrass/Clay',
  'TWEED CANELA/TERRACOTA': 'Tweed Cinnamon/Terracotta',
  'TWEED CIDREIRA/AREIA': 'Tweed Lemongrass/Sand', 'TWEED CRU': 'Ecru Tweed',
  'TWEED NEBLINA/CROMO': 'Tweed Fog/Chrome', 'UNIQUE COBALTO': 'Unique Cobalt',
  'UNIQUE DESERTO': 'Unique Desert', 'UNIQUE DESERTO/SISAL': 'Unique Desert/Sisal',
  'UNIQUE MARFIM': 'Unique Ivory', 'UNIQUE MUSGO': 'Unique Moss', 'UNIQUE SISAL': 'Unique Sisal',
  'UNIQUE SISAL/ARGILA': 'Unique Sisal/Clay', 'WAVES AVELA': 'Waves Hazelnut',
  'WAVES COBALTO': 'Waves Cobalt', 'WAVES MARFIN': 'Waves Ivory', 'WAVES MENTA': 'Waves Mint',
  BEGE: 'Beige', CARBONO: 'Carbon', 'AREIA MESCLA': 'Mottled Sand',
  'GRAFITE UNIQUE': 'Unique Graphite', 'KHAKI FECHADO': 'Khaki (Closed Weave)',
  MENTA: 'Mint', VIDRO: 'Glass', CARVALHO: 'Oak', NOGUEIRA: 'Walnut', LATAO: 'Brass',
  'NOGUEIRA NATURAL': 'Natural Walnut', 'LINHO AREIA': 'Sand Linen',
}

const categories: Record<string, string> = {
  ALUMINIO: 'Aluminium', 'ALUMINIO IBTW': 'IBTW Aluminium', ALW: 'Aluwood',
  BASE: 'Parasol Base', 'BASE OMBRELONE': 'Parasol Base', CERAMICA: 'Ceramic',
  'CERAMICA ARTESANAL': 'Handcrafted Ceramic', COBERTURA: 'Canopy',
  'CORDA BOUCLE': 'Bouclé Rope', 'CORDA SINTETICA': 'Synthetic Rope',
  'CORDA SINTETICA (100% PVC)': 'Synthetic Rope (100% PVC)', CORTINA: 'Curtain',
  'COURO SOLETA': 'Saddle Leather', 'COURO PELE': 'Leather',
  'FIBRA DE VIDRO': 'Fibreglass', 'FIBRA SINTETICA': 'Synthetic Fibre', HASTE: 'Pole',
  MADEIRA: 'Wood', MARMORE: 'Marble', 'PALHA SINTETICA': 'Synthetic Thatch',
  'PEDRA COMPOSTA': 'Composite Stone', 'PEDRA SINTERIZADA': 'Sintered Stone',
  'PEDRA SINTERISADA': 'Sintered Stone', TAPETE: 'Carpet', THM: 'Hammock Fabric',
  'TECIDO HAMMOCK': 'Hammock Fabric', TCI: 'Indoor Fabric', 'TECIDO INDOOR': 'Indoor Fabric',
  'TECIDO OUTDOOR': 'Outdoor Fabric', 'TECIDOS IBTW': 'IBTW Fabrics',
  TEKA: 'Teak', TELA: 'Mesh', 'TELA IBTW': 'IBTW Mesh', TRICOT: 'Knit', URDUME: 'Warp',
  VIDRO: 'Glass', CORDA: 'Rope', TECIDO: 'Fabric', METAL: 'Metal',
  'TECIDO FAIXA 1': 'Fabric F1', 'TECIDO FAIXA 2': 'Fabric F2',
  'TECIDO F1': 'Fabric F1', 'TECIDO F2': 'Fabric F2', ACABAMENTO: 'Finish',
  'MADEIRA TEKA': 'Teak Wood', 'MADEIRA FREIJO': 'Freijó Wood',
}

function normalize(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase()
    .replace(/\s*\/\s*/g, '/').replace(/\s+/g, ' ').trim()
}

function displayTranslation(original: string, translation?: string) {
  if (!translation) return original
  return original === original.toUpperCase() ? translation.toUpperCase() : translation
}

export function optionalName(name: string, english: boolean): string {
  return english ? displayTranslation(name, names[normalize(name)]) : name
}

export function optionalCategoryLabel(category: string, english: boolean): string {
  return english ? displayTranslation(category, categories[normalize(category).replaceAll('_', ' ')]) : category
}

export function optionalMatchesSearch(name: string, query: string, english: boolean): boolean {
  const search = normalize(query)
  return normalize(name).includes(search) || normalize(optionalName(name, english)).includes(search)
}
