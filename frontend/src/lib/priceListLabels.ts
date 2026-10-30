/**
 * Nome exibido de cada tabela de preço. O código (`lojista`, `arquiteto`,
 * `corporativo`, `pvp`) é o que trafega na API e fica no banco; só o rótulo na
 * tela muda por idioma. Em inglês traduzimos Lojista/Arquiteto/Corporativo; PVP
 * segue "PVP" (o equivalente inglês usual seria "RRP").
 */
export type PriceListLabelCode = 'lojista' | 'arquiteto' | 'corporativo' | 'pvp'

const PT: Record<PriceListLabelCode, string> = {
  lojista: 'Lojista',
  arquiteto: 'Arquiteto',
  corporativo: 'Corporativo',
  pvp: 'PVP',
}

const EN: Record<PriceListLabelCode, string> = {
  lojista: 'Retailer',
  arquiteto: 'Architect',
  corporativo: 'Corporate',
  pvp: 'PVP',
}

export function priceListLabel(code: PriceListLabelCode, english: boolean): string {
  return (english ? EN : PT)[code]
}

/** Aceita um código vindo da API sem tipo estrito; código desconhecido volta capitalizado. */
export function priceListLabelFor(code: string, english: boolean): string {
  if (code in PT) return priceListLabel(code as PriceListLabelCode, english)
  return code.charAt(0).toUpperCase() + code.slice(1)
}
